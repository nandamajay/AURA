# AURA Production Progress Tracking

This directory contains tools for tracking AURA's production hardening progress.

## Files

### Core Tracking Files
- `PRODUCTION_ROADMAP.md` - Human-readable roadmap with all phases, weeks, and tasks
- `PRODUCTION_PROGRESS.json` - Machine-readable progress data
- `PRODUCTION_DASHBOARD.md` - Auto-generated visual dashboard

### Scripts
- `update_progress.py` - Update task/deliverable status
- `generate_dashboard.py` - Generate visual dashboard

## Usage

### View Current Progress

```bash
# Generate and view dashboard
python3 scripts/progress/generate_dashboard.py

# View progress report
python3 scripts/progress/update_progress.py report
```

### Update Task Status

```bash
# Mark task as in progress
python3 scripts/progress/update_progress.py task p0_w1_t1 IN_PROGRESS

# Mark task as completed with evidence
python3 scripts/progress/update_progress.py task p0_w1_t1 COMPLETED \
  evidence/architecture_enforcement_report.json

# Mark task as blocked
python3 scripts/progress/update_progress.py task p0_w1_t2 BLOCKED
```

### Update Deliverable Status

```bash
# Mark deliverable as completed
python3 scripts/progress/update_progress.py deliverable \
  PRODUCTION_GAP_MATRIX.md COMPLETED

# Mark deliverable as in progress
python3 scripts/progress/update_progress.py deliverable \
  contracts/registry.json IN_PROGRESS
```

### Regenerate Dashboard

```bash
# After updating tasks/deliverables, regenerate dashboard
python3 scripts/progress/generate_dashboard.py
```

## Task Status Values

- `NOT_STARTED` - Task not yet begun
- `IN_PROGRESS` - Task currently being worked on
- `COMPLETED` - Task finished with evidence
- `BLOCKED` - Task blocked by dependency or issue

## Deliverable Status Values

- `NOT_STARTED` - Deliverable not yet created
- `IN_PROGRESS` - Deliverable being created
- `COMPLETED` - Deliverable finished and reviewed

## Workflow

### Daily
1. Update task status as work progresses
2. Add evidence files to completed tasks
3. Regenerate dashboard

### Weekly
1. Review progress report
2. Update roadmap if needed
3. Document blockers and risks
4. Generate weekly summary

### Phase Completion
1. Verify all tasks completed
2. Verify all deliverables completed
3. Run phase validation suite
4. Update phase status to COMPLETED
5. Generate phase completion report

## Integration with Git

```bash
# After updating progress
git add PRODUCTION_PROGRESS.json PRODUCTION_DASHBOARD.md
git commit -m "progress: update Phase 0 Week 1 tasks"
```

## Automation

Add to `.github/workflows/progress-tracking.yml`:

```yaml
name: Update Progress Dashboard

on:
  push:
    paths:
      - 'PRODUCTION_PROGRESS.json'

jobs:
  update-dashboard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Generate Dashboard
        run: python3 scripts/progress/generate_dashboard.py
      - name: Commit Dashboard
        run: |
          git config user.name "AURA Bot"
          git config user.email "bot@aura.local"
          git add PRODUCTION_DASHBOARD.md
          git commit -m "chore: auto-update progress dashboard" || true
          git push
```

## Example: Complete Phase 0 Week 1

```bash
# Mark all Week 1 tasks as completed
python3 scripts/progress/update_progress.py task p0_w1_t1 COMPLETED evidence/arch_enforcement.json
python3 scripts/progress/update_progress.py task p0_w1_t2 COMPLETED evidence/validation_suite.json
python3 scripts/progress/update_progress.py task p0_w1_t3 COMPLETED evidence/router_audit.json
python3 scripts/progress/update_progress.py task p0_w1_t4 COMPLETED evidence/agent_audit.json
python3 scripts/progress/update_progress.py task p0_w1_t5 COMPLETED evidence/migration_audit.json
python3 scripts/progress/update_progress.py task p0_w1_t6 COMPLETED evidence/code_audit.json

# Mark deliverables as completed
python3 scripts/progress/update_progress.py deliverable PRODUCTION_GAP_MATRIX.md COMPLETED
python3 scripts/progress/update_progress.py deliverable BASELINE_LOCK_v2.md COMPLETED
python3 scripts/progress/update_progress.py deliverable PHASE_0_AUDIT_REPORT.json COMPLETED

# Regenerate dashboard
python3 scripts/progress/generate_dashboard.py

# View progress
python3 scripts/progress/update_progress.py report
```

## Tips

- Always add evidence files when marking tasks as completed
- Update progress daily to keep dashboard current
- Use descriptive evidence file names
- Document blockers immediately
- Review progress weekly with team
- Celebrate phase completions!
