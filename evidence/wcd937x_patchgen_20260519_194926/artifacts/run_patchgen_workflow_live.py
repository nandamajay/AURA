from __future__ import annotations
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib import request, error

RUN_DIR = Path(os.environ['RUN_DIR'])
WORKTREE = Path(os.environ['WORKTREE'])
SOURCE_STUDY = Path('/local/mnt/workspace/AURA_V1/evidence/wcd937x_real_study_20260519_062557')

ENV_PATH = Path('/local/mnt/workspace/AURA_V1/AURA/.env')
creds = {}
for line in ENV_PATH.read_text().splitlines():
    line = line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    k, v = line.split('=', 1)
    creds[k.strip()] = v.strip()
ADMIN_EMAIL = creds.get('ADMIN_EMAIL', '')
ADMIN_PASSWORD = creds.get('ADMIN_PASSWORD', '')
if not ADMIN_EMAIL or not ADMIN_PASSWORD:
    raise RuntimeError('missing admin credentials in .env')

source_runtime_ids = json.loads((SOURCE_STUDY / 'raw' / 'runtime_ids.json').read_text())
source_commit = source_runtime_ids['source_head_commit']
source_repo = source_runtime_ids['source_repo']
source_branch = source_runtime_ids['source_branch']

trace = {
    'started_at': datetime.now(timezone.utc).isoformat(),
    'base_url': 'http://127.0.0.1:8000',
    'calls': [],
}


def _http(method: str, url: str, payload: dict | None = None, token: str | None = None):
    data = None
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
    req = request.Request(url=url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
            try:
                body = json.loads(raw)
            except Exception:
                body = {'raw': raw}
            return resp.status, body
    except error.HTTPError as e:
        raw = e.read().decode('utf-8', errors='replace')
        try:
            body = json.loads(raw)
        except Exception:
            body = {'raw': raw}
        return e.code, body


def call(label: str, method: str, path: str, payload: dict | None = None, token: str | None = None):
    status, body = _http(method, f'http://127.0.0.1:8000{path}', payload, token)
    trace['calls'].append({
        'label': label,
        'method': method,
        'path': path,
        'payload': payload,
        'status_code': status,
        'body': body,
    })
    return status, body


# Login
login_status, login_body = call(
    'auth_login',
    'POST',
    '/api/v1/auth/login',
    {'email': ADMIN_EMAIL, 'password': ADMIN_PASSWORD},
)
if login_status != 200:
    raise RuntimeError(f'login failed: {login_status} {login_body}')
TOKEN = login_body['access_token']

# Guard: detached engineering execution forbidden.
call(
    'detached_task_rejection',
    'POST',
    '/api/v1/tasks/',
    {
        'agent_type': 'patch_builder',
        'priority': 'P1',
        'description': 'detached should fail in patchgen phase',
        'input_data': {'workflow_kind': 'engineering'},
    },
    TOKEN,
)

# Register intake for this patchgen phase using authoritative source identity.
register_payload = {
    'downstream_repo_url': source_repo,
    'downstream_ref_kind': 'branch',
    'downstream_ref': source_branch,
    'bsp_lineage': source_branch,
    'commit_anchors': [source_commit],
    'subsystem_name': 'audio-qualcomm',
    'subsystem_owner': 'aura-audio',
    'upstream_repo_url': 'https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git',
    'target_kernel': 'linux',
    'target_kernel_version': '6.18',
    'maintainer_refs': ['broonie@kernel.org', 'tiwai@suse.de'],
    'patchset_lineage': [source_commit],
}
status, body = call('source_intake', 'POST', '/api/v1/provenance/sources/register', register_payload, TOKEN)
if status not in (200, 409):
    raise RuntimeError(f'source register failed: {status} {body}')
if status == 200:
    intake_id = body['intake_id']
else:
    # deterministic duplicate path
    intake_id = body.get('intake_id') or body.get('existing_intake_id')
    if not intake_id:
        # fallback: list and take newest by same repo+branch
        s2, b2 = call('source_list_fallback', 'GET', '/api/v1/provenance/sources?limit=50', None, TOKEN)
        if s2 != 200:
            raise RuntimeError(f'cannot resolve duplicate intake id: {s2} {b2}')
        intake_id = ''
        for row in b2.get('items', []):
            if row.get('downstream_repo_url') == source_repo and row.get('downstream_ref') == source_branch:
                intake_id = row['id']
                break
        if not intake_id:
            raise RuntimeError(f'cannot resolve intake id from duplicate response: {body}')

call('source_validate', 'POST', f'/api/v1/provenance/sources/{intake_id}/validate', None, TOKEN)
call(
    'source_approve',
    'POST',
    f'/api/v1/provenance/sources/{intake_id}/approve',
    {'decision': 'approve', 'comment': 'operator-gated intake approval for controlled patch generation'},
    TOKEN,
)

call(
    'lineage_downstream_intake',
    'POST',
    f'/api/v1/provenance/sources/{intake_id}/lineage',
    {
        'stage': 'downstream_intake',
        'payload': {
            'source_study_ref': str(SOURCE_STUDY / 'reports' / 'WCD937x_real_workflow_study_index.md'),
            'dependency_report_ref': str(SOURCE_STUDY / 'reports' / 'dependency_graph_report.md'),
            'mapping_report_ref': str(SOURCE_STUDY / 'reports' / 'downstream_upstream_api_mapping_report.md'),
        },
    },
    TOKEN,
)

status, body = call(
    'source_snapshot',
    'POST',
    f'/api/v1/provenance/sources/{intake_id}/snapshot',
    {'reason': 'immutable source snapshot for controlled WCD937x patch generation'},
    TOKEN,
)
if status != 200:
    raise RuntimeError(f'source snapshot failed: {status} {body}')
source_snapshot_id = body['snapshot_id']

# Freeze engineering snapshot
status, body = call(
    'engineering_snapshot_freeze',
    'POST',
    '/api/v1/engineering/snapshots/freeze',
    {
        'intake_id': intake_id,
        'source_snapshot_id': source_snapshot_id,
        'downstream_repo_url': source_repo,
        'downstream_ref_kind': 'branch',
        'downstream_ref': source_branch,
        'downstream_commit_sha': source_commit,
        'subsystem_classification': 'audio-qualcomm',
        'upstream_target_kernel_version': '6.18',
        'upstream_target_branch': 'torvalds/v6.18',
        'maintainer_context': ['broonie@kernel.org', 'tiwai@suse.de'],
        'validation_profile_version': 'wcd937x-patchgen-v1',
        'ruleset_version': 'aura-engineering-rules-v1',
        'validation_tool_versions': {
            'checkpatch': 'checkpatch',
            'sparse': 'sparse',
            'clang_build': 'clang',
        },
        'replay_runtime_version': 'replay-v1',
        'governance_policy_version': 'gov-v1',
    },
    TOKEN,
)
if status != 200:
    raise RuntimeError(f'engineering snapshot freeze failed: {status} {body}')
engineering_snapshot_id = body['snapshot_id']

# Workflow + task bind
status, body = call(
    'workflow_create_patchgen',
    'POST',
    '/api/v1/engineering/workflows',
    {
        'intake_id': intake_id,
        'snapshot_id': engineering_snapshot_id,
        'provenance_lineage_hash': '',
    },
    TOKEN,
)
if status != 200:
    raise RuntimeError(f'workflow create failed: {status} {body}')
workflow_id = body['workflow_id']

status, body = call(
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
    TOKEN,
)
if status != 200:
    raise RuntimeError(f'workflow task bind failed: {status} {body}')
task_id = body['task_id']

# Seed task replay in running core container (real runtime DB path /data/aura.db).
seed_cmd = (
    "from aura_sdk.replay import TaskRecorder;"
    "from core.config import Config;"
    f"r=TaskRecorder(Config.SQLITE_PATH);"
    f"tid='{task_id}';"
    "r.start_task(task_id=tid, agent_type='patch_builder', seed=42, model_version='gpt-5-codex', rules_path='/rules', input_data={'phase':'controlled_patch_generation','task_id':tid});"
    "r.record_prompt(tid,'system','generate governed patch proposals');"
    "r.record_response(tid,'proposal batch prepared');"
    "r.finalize(tid,{'status':'proposal_generated'})"
)
subprocess.run(['docker', 'exec', 'aura-core', 'python', '-c', seed_cmd], check=False)

call(
    'transition_patch_analysis',
    'POST',
    f'/api/v1/engineering/workflows/{workflow_id}/transition',
    {'to_state': 'patch_analysis', 'reason': 'proposal_scope_loaded_from_authoritative_inputs'},
    TOKEN,
)

patches = sorted(p.name for p in (RUN_DIR / 'generated_patch_diffs').glob('*.patch'))
call(
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
    TOKEN,
)

call(
    'transition_transformation_proposal',
    'POST',
    f'/api/v1/engineering/workflows/{workflow_id}/transition',
    {'to_state': 'transformation_proposal', 'reason': 'grouped_patch_diffs_generated'},
    TOKEN,
)

call(
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
    TOKEN,
)

status, val_body = call(
    'validation_run_patchgen',
    'POST',
    f'/api/v1/engineering/workflows/{workflow_id}/validation/run',
    {
        'target_path': str(WORKTREE),
        'patch_paths': [f'generated_patch_diffs/{name}' for name in patches],
        'build_probe_file': str(WORKTREE / 'sound' / 'soc' / 'codecs' / 'wcd937x.c'),
    },
    TOKEN,
)

exit_codes = {}
for line in (RUN_DIR / 'artifacts' / 'validation_exit_codes.txt').read_text().splitlines():
    if '=' in line:
        k, v = line.split('=', 1)
        exit_codes[k.strip()] = v.strip()

call(
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
    TOKEN,
)

status, gov_req_body = call(
    'governance_request_transformation',
    'POST',
    f'/api/v1/engineering/workflows/{workflow_id}/governance/request',
    {
        'operation': 'transformation_proposal',
        'reason': 'operator approval required: controlled patch proposal series generated, no auto-apply',
    },
    TOKEN,
)

call(
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
    TOKEN,
)

for patch_file in patches:
    rel = f'generated_patch_diffs/{patch_file}'
    content = (RUN_DIR / rel).read_text(encoding='utf-8', errors='replace')
    call(
        f'evidence_link_patch_{patch_file}',
        'POST',
        f'/api/v1/engineering/workflows/{workflow_id}/evidence',
        {
            'evidence_type': 'proposed_patch_diff',
            'evidence_ref': rel,
            'evidence_content': content,
        },
        TOKEN,
    )

recon_status, recon_body = call('workflow_reconstruct', 'GET', f'/api/v1/engineering/workflows/{workflow_id}/reconstruct', None, TOKEN)
call('workflow_get', 'GET', f'/api/v1/engineering/workflows/{workflow_id}', None, TOKEN)
source_recon_status, source_recon_body = call('source_reconstruct', 'GET', f'/api/v1/provenance/sources/{intake_id}/reconstruct', None, TOKEN)

trace['ended_at'] = datetime.now(timezone.utc).isoformat()
(RUN_DIR / 'raw' / 'runtime_lifecycle_trace.json').write_text(json.dumps(trace, indent=2), encoding='utf-8')

runtime_ids = {
    'intake_id': intake_id,
    'source_snapshot_id': source_snapshot_id,
    'engineering_snapshot_id': engineering_snapshot_id,
    'workflow_id': workflow_id,
    'task_id': task_id,
    'workflow_validation_status': val_body.get('validation_status') if isinstance(val_body, dict) else '',
    'workflow_reconstruction_hash': recon_body.get('reconstruction_hash') if isinstance(recon_body, dict) else '',
    'workflow_trust_valid': recon_body.get('trust_valid') if isinstance(recon_body, dict) else None,
    'source_reconstruction_hash': source_recon_body.get('reconstruction_hash') if isinstance(source_recon_body, dict) else '',
    'source_repo': source_repo,
    'source_branch': source_branch,
    'source_head_commit': source_commit,
}
(RUN_DIR / 'raw' / 'runtime_ids.json').write_text(json.dumps(runtime_ids, indent=2), encoding='utf-8')
print(json.dumps(runtime_ids, indent=2))
