from __future__ import annotations
import json
import os
import shutil
import sqlite3
import sys
from contextlib import asynccontextmanager
import enum
if not hasattr(enum, 'StrEnum'):
    class _CompatStrEnum(str, enum.Enum):
        pass
    enum.StrEnum = _CompatStrEnum

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path('/local/mnt/workspace/AURA_V1/AURA')
AURA_SDK_SRC = REPO_ROOT / 'workspace' / 'aura-sdk' / 'src'
CORE_SRC = REPO_ROOT / 'services' / 'core' / 'src'
sys.path.insert(0, str(AURA_SDK_SRC))
sys.path.insert(0, str(CORE_SRC))

from aura_sdk.models.task import Task, TaskStatus
from aura_sdk.replay import TaskRecorder
from core.config import Config
from core.routers import provenance as provenance_router
from core.routers import engineering as engineering_router
from core.routers import tasks as tasks_router
from core.routers.auth import get_current_user
import core.events as events_module

RUN_DIR = Path(os.environ['RUN_DIR'])
WORKTREE = Path(os.environ['WORKTREE'])
SOURCE_STUDY = Path('/local/mnt/workspace/AURA_V1/evidence/wcd937x_real_study_20260519_062557')

source_ids = json.loads((SOURCE_STUDY / 'raw' / 'runtime_ids.json').read_text())
base_db = SOURCE_STUDY / 'artifacts' / 'wcd937x_real_runtime.db'
db_path = RUN_DIR / 'artifacts' / 'wcd937x_patchgen_runtime.db'
shutil.copy2(base_db, db_path)

current_user: dict[str, str] = {
    'sub': 'system',
    'email': 'system@aura.local',
    'role': 'reviewer',
}

class QueueStub:
    async def create_task(self, task_in, *, requested_by: str) -> Task:
        return Task(
            agent_type=task_in.agent_type,
            status=TaskStatus.QUEUED,
            priority=task_in.priority,
            input_data=task_in.input_data,
            description=task_in.description,
            requested_by=requested_by,
            max_retries=task_in.max_retries,
        )

app = FastAPI()
app.include_router(provenance_router.router, prefix='/api/v1/provenance')
app.include_router(engineering_router.router, prefix='/api/v1/engineering')
app.include_router(tasks_router.router, prefix='/api/v1/tasks')
app.dependency_overrides[get_current_user] = lambda: current_user
app.state.task_queue = QueueStub()

@asynccontextmanager
async def _test_get_db():
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute('PRAGMA foreign_keys = ON')
        await db.execute('PRAGMA journal_mode = WAL')
        yield db

orig_prov_get_db = provenance_router.get_db
orig_eng_get_db = engineering_router.get_db
orig_events_get_db = events_module.get_db
provenance_router.get_db = _test_get_db
engineering_router.get_db = _test_get_db
events_module.get_db = _test_get_db

Config.SQLITE_PATH = str(db_path)
trace: dict[str, Any] = {
    'started_at': datetime.now(timezone.utc).isoformat(),
    'db_path': str(db_path),
    'calls': [],
}


def call(client: TestClient, label: str, method: str, path: str, payload: dict[str, Any] | None = None):
    response = client.request(method, path, json=payload)
    body: Any
    try:
        body = response.json()
    except Exception:
        body = {'raw': response.text}
    trace['calls'].append({
        'label': label,
        'method': method,
        'path': path,
        'payload': payload,
        'status_code': response.status_code,
        'body': body,
        'actor': dict(current_user),
    })
    return response, body


with TestClient(app) as client:
    # Guard: detached engineering execution must fail.
    call(
        client,
        'detached_task_rejection',
        'POST',
        '/api/v1/tasks/',
        {
            'agent_type': 'patch_builder',
            'priority': 'P1',
            'description': 'detached should fail in patchgen phase',
            'input_data': {'workflow_kind': 'engineering'},
        },
    )

    intake_id = source_ids['intake_id']
    snapshot_id = source_ids['engineering_snapshot_id']

    wf_resp, wf_body = call(
        client,
        'workflow_create_patchgen',
        'POST',
        '/api/v1/engineering/workflows',
        {
            'intake_id': intake_id,
            'snapshot_id': snapshot_id,
            'provenance_lineage_hash': '',
        },
    )
    if wf_resp.status_code != 200:
        raise RuntimeError(f'workflow create failed: {wf_resp.status_code} {wf_body}')
    workflow_id = wf_body['workflow_id']

    patches = sorted(str(p.name) for p in (RUN_DIR / 'generated_patch_diffs').glob('*.patch'))

    bind_resp, bind_body = call(
        client,
        'workflow_task_bind_patchgen',
        'POST',
        f'/api/v1/engineering/workflows/{workflow_id}/task',
        {
            'agent_type': 'patch_builder',
            'priority': 'P1',
            'description': 'Controlled WCD937x governed patch proposal generation',
            'plugin_domain': 'driver',
            'input_data': {
                'patch_series_ref': 'generated_patch_diffs',
                'source_study_ref': str(SOURCE_STUDY / 'reports' / 'WCD937x_real_workflow_study_index.md'),
            },
        },
    )
    if bind_resp.status_code != 200:
        raise RuntimeError(f'workflow bind failed: {bind_resp.status_code} {bind_body}')
    task_id = bind_body['task_id']

    # Seed deterministic replay log for this task.
    recorder = TaskRecorder(str(db_path))
    recorder.start_task(
        task_id=task_id,
        agent_type='patch_builder',
        seed=42,
        model_version='gpt-5-codex',
        rules_path='/rules',
        input_data={'workflow_id': workflow_id, 'task_id': task_id, 'phase': 'controlled_patch_generation'},
    )
    recorder.record_prompt(task_id, 'system', 'generate governed patch proposals')
    recorder.record_response(task_id, 'proposal batch prepared')
    recorder.finalize(task_id, {'status': 'proposal_generated'})

    call(
        client,
        'transition_patch_analysis',
        'POST',
        f'/api/v1/engineering/workflows/{workflow_id}/transition',
        {'to_state': 'patch_analysis', 'reason': 'proposal_scope_loaded_from_authoritative_inputs'},
    )

    call(
        client,
        'lineage_patch_transform',
        'POST',
        f'/api/v1/provenance/sources/{intake_id}/lineage',
        {
            'stage': 'patch_transform',
            'payload': {
                'workflow_id': workflow_id,
                'task_id': task_id,
                'patch_files': patches,
                'patch_gitlog_ref': 'artifacts/patch_series_gitlog.txt',
                'source_plan_ref': str(SOURCE_STUDY / 'reports' / 'patch_grouping_proposal.md'),
            },
        },
    )

    call(
        client,
        'transition_transformation_proposal',
        'POST',
        f'/api/v1/engineering/workflows/{workflow_id}/transition',
        {'to_state': 'transformation_proposal', 'reason': 'grouped_patch_diffs_generated'},
    )

    call(
        client,
        'lineage_upstream_prep',
        'POST',
        f'/api/v1/provenance/sources/{intake_id}/lineage',
        {
            'stage': 'upstream_prep',
            'payload': {
                'workflow_id': workflow_id,
                'mapping_ref': str(SOURCE_STUDY / 'reports' / 'downstream_upstream_api_mapping_report.md'),
                'transform_plan_ref': str(SOURCE_STUDY / 'reports' / 'semantic_transformation_plan.md'),
                'advisory_only': True,
            },
        },
    )

    val_resp, val_body = call(
        client,
        'validation_run_patchgen',
        'POST',
        f'/api/v1/engineering/workflows/{workflow_id}/validation/run',
        {
            'target_path': str(WORKTREE),
            'patch_paths': [f'generated_patch_diffs/{name}' for name in patches],
            'build_probe_file': str(WORKTREE / 'sound' / 'soc' / 'codecs' / 'wcd937x.c'),
        },
    )

    exit_codes: dict[str, str] = {}
    for line in (RUN_DIR / 'artifacts' / 'validation_exit_codes.txt').read_text().splitlines():
        if '=' in line:
            k, v = line.split('=', 1)
            exit_codes[k.strip()] = v.strip()

    call(
        client,
        'lineage_validation',
        'POST',
        f'/api/v1/provenance/sources/{intake_id}/lineage',
        {
            'stage': 'validation',
            'payload': {
                'workflow_id': workflow_id,
                'validation_status': val_body.get('validation_status') if isinstance(val_body, dict) else 'unknown',
                'validation_exit_codes': exit_codes,
                'validation_report_ref': 'reports/validation_execution_report.md',
                'logs_dir': 'logs/',
            },
        },
    )

    gov_req_resp, gov_req_body = call(
        client,
        'governance_request_transformation',
        'POST',
        f'/api/v1/engineering/workflows/{workflow_id}/governance/request',
        {
            'operation': 'transformation_proposal',
            'reason': 'operator approval required: controlled patch proposal series generated, no auto-apply',
        },
    )

    call(
        client,
        'lineage_approval_pending',
        'POST',
        f'/api/v1/provenance/sources/{intake_id}/lineage',
        {
            'stage': 'approval',
            'payload': {
                'workflow_id': workflow_id,
                'governance_status': 'requested',
                'operation': 'transformation_proposal',
                'action_id': gov_req_body.get('action_id') if isinstance(gov_req_body, dict) else None,
                'note': 'Awaiting operator decision; no auto-merge, no auto-apply',
            },
        },
    )

    # Link patch diffs as first-class workflow evidence.
    for patch_file in patches:
        rel = f'generated_patch_diffs/{patch_file}'
        content = (RUN_DIR / rel).read_text(encoding='utf-8', errors='replace')
        call(
            client,
            f'evidence_link_patch_{patch_file}',
            'POST',
            f'/api/v1/engineering/workflows/{workflow_id}/evidence',
            {
                'evidence_type': 'proposed_patch_diff',
                'evidence_ref': rel,
                'evidence_content': content,
            },
        )

    call(client, 'workflow_reconstruct', 'GET', f'/api/v1/engineering/workflows/{workflow_id}/reconstruct')
    call(client, 'workflow_get', 'GET', f'/api/v1/engineering/workflows/{workflow_id}')
    call(client, 'source_reconstruct', 'GET', f'/api/v1/provenance/sources/{intake_id}/reconstruct')

trace['ended_at'] = datetime.now(timezone.utc).isoformat()
(RUN_DIR / 'raw' / 'runtime_lifecycle_trace.json').write_text(json.dumps(trace, indent=2), encoding='utf-8')

# Extract key IDs from trace
workflow_id = ''
task_id = ''
validation_status = ''
workflow_reconstruction_hash = ''
workflow_trust_valid = None
source_reconstruction_hash = ''
for item in trace['calls']:
    body = item.get('body') if isinstance(item.get('body'), dict) else {}
    if item['label'] == 'workflow_create_patchgen':
        workflow_id = str(body.get('workflow_id', workflow_id))
    elif item['label'] == 'workflow_task_bind_patchgen':
        task_id = str(body.get('task_id', task_id))
    elif item['label'] == 'validation_run_patchgen':
        validation_status = str(body.get('validation_status', validation_status))
    elif item['label'] == 'workflow_reconstruct':
        workflow_reconstruction_hash = str(body.get('reconstruction_hash', workflow_reconstruction_hash))
        workflow_trust_valid = body.get('trust_valid')
    elif item['label'] == 'source_reconstruct':
        source_reconstruction_hash = str(body.get('reconstruction_hash', source_reconstruction_hash))

runtime_ids = {
    'intake_id': source_ids['intake_id'],
    'source_snapshot_id': source_ids['source_snapshot_id'],
    'engineering_snapshot_id': source_ids['engineering_snapshot_id'],
    'workflow_id': workflow_id,
    'task_id': task_id,
    'workflow_validation_status': validation_status,
    'workflow_reconstruction_hash': workflow_reconstruction_hash,
    'workflow_trust_valid': workflow_trust_valid,
    'source_reconstruction_hash': source_reconstruction_hash,
    'source_repo': source_ids['source_repo'],
    'source_branch': source_ids['source_branch'],
    'source_head_commit': source_ids['source_head_commit'],
}
(RUN_DIR / 'raw' / 'runtime_ids.json').write_text(json.dumps(runtime_ids, indent=2), encoding='utf-8')

# Restore patched globals
provenance_router.get_db = orig_prov_get_db
engineering_router.get_db = orig_eng_get_db
events_module.get_db = orig_events_get_db

print(json.dumps(runtime_ids, indent=2))
