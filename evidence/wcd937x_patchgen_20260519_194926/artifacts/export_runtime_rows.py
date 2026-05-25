from __future__ import annotations
import json
import sqlite3
from pathlib import Path

run_dir = Path('/local/mnt/workspace/AURA_V1/evidence/wcd937x_patchgen_20260519_194926')
raw_dir = run_dir / 'raw'
raw_dir.mkdir(parents=True, exist_ok=True)
runtime_ids = json.loads((raw_dir / 'runtime_ids.json').read_text())
intake_id = runtime_ids['intake_id']
workflow_id = runtime_ids['workflow_id']
task_id = runtime_ids['task_id']

DB = Path('/local/mnt/workspace/AURA_V1/AURA/data/aura.db')
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

queries = {
    'source_intake_rows.json': ("SELECT * FROM source_intakes WHERE id = ?", (intake_id,)),
    'source_intake_event_rows.json': ("SELECT * FROM source_intake_events WHERE intake_id = ? ORDER BY id", (intake_id,)),
    'source_snapshot_rows.json': ("SELECT * FROM source_replay_snapshots WHERE intake_id = ? ORDER BY id", (intake_id,)),
    'engineering_snapshot_rows.json': ("SELECT * FROM engineering_snapshots WHERE intake_id = ? ORDER BY id", (intake_id,)),
    'workflow_rows.json': ("SELECT * FROM engineering_workflows WHERE id = ?", (workflow_id,)),
    'workflow_events_rows.json': ("SELECT * FROM engineering_workflow_events WHERE workflow_id = ? ORDER BY id", (workflow_id,)),
    'validation_runs_rows.json': ("SELECT * FROM engineering_validation_runs WHERE workflow_id = ? ORDER BY run_sequence, tool_name", (workflow_id,)),
    'governance_actions_rows.json': ("SELECT * FROM engineering_governance_actions WHERE workflow_id = ? ORDER BY id", (workflow_id,)),
    'engineering_evidence_links_rows.json': ("SELECT * FROM engineering_evidence_links WHERE workflow_id = ? ORDER BY id", (workflow_id,)),
    'source_lineage_rows.json': ("SELECT * FROM source_lineage_entries WHERE intake_id = ? ORDER BY created_at, rowid", (intake_id,)),
    'audit_ledger_rows.json': (
        "SELECT * FROM audit_ledger WHERE target_id IN (?, ?, ?) ORDER BY id",
        (workflow_id, intake_id, task_id),
    ),
}

for filename, (sql, params) in queries.items():
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    (raw_dir / filename).write_text(json.dumps(rows, indent=2), encoding='utf-8')

conn.close()
print('exported')
