# WCD9378 Iteration Learning Log

This directory tracks issue-to-solution learning in a replayable format.

## Files
- `iteration_record_schema.json`: required fields for each iteration record.
- `iteration_record_template.json`: template for a new record.
- `iteration_change_log.jsonl`: append-only line-delimited history.
- `issue_solution_map.json`: aggregated issue status and applied solutions.
- `tools/append_iteration_record.py`: validator+append helper for JSONL.

## Append Workflow
1. Copy `iteration_record_template.json` to a temporary file and fill all fields.
2. Append with validation:

```bash
python3 AURA_KB/drivers/wcd9378/learning_issue_solution_01/tools/append_iteration_record.py \
  --record-file /tmp/new_iteration_record.json
```

3. Update `issue_solution_map.json` status/evidence for affected issue IDs.

## Rules
- Do not edit existing JSONL lines in place (append-only).
- Runtime-class issues must not be marked `RESOLVED` without runtime evidence.
- Evidence references should point to deterministic sources (log line, file path, command result).
