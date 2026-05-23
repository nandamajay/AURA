# Scope and Evidence Baseline

Date: 2026-05-18
Branch context: `stabilization/p1-runtime-reliability`

## Phase Scope
This phase anchors AURA architecture to the first real target domain:
Audio downstream-to-upstream engineering workflow orchestration.

This phase does:
- reclassification against real engineering runtime requirements
- architecture alignment of layers, plugin boundaries, replay/governance semantics
- trust boundary clarification

This phase does not:
- implement new runtime features
- change replay semantics
- change governance semantics
- add distributed infrastructure

## Evidence Sources (Runtime)
- `evidence/runtime-isolation/2026-05-18-bounded-runtime-isolation-stabilization-report.md`
- `evidence/runtime-isolation/2026-05-18-coexistence-delta-report.md`
- `evidence/runtime-isolation/2026-05-18-runtime-isolation-confidence-summary.json`
- `evidence/endurance/2026-05-18-endurance-soak-validation-report.md`

## Evidence Sources (Code Path)
- Task lifecycle and orchestration:
  - `AURA/workspace/aura-sdk/src/aura_sdk/models/task.py`
  - `AURA/services/core/src/core/services/task_queue.py`
- Replay boundaries:
  - `AURA/knowledge/schema/018_task_logs_replay_boundaries.sql`
  - `AURA/services/core/src/core/routers/tasks.py`
- Governance and audit transition behavior:
  - `AURA/services/core/src/core/routers/governance.py`
  - `AURA/services/core/src/core/routers/charter.py`
  - `AURA/services/core/src/core/events.py`
- Patch domain baseline:
  - `AURA/workspace/aura-sdk/src/aura_sdk/models/patch.py`
  - `AURA/knowledge/schema/005_patches.sql`
  - `AURA/services/core/src/core/routers/patches.py`
- Plugin contract baseline:
  - `AURA/workspace/aura-sdk/src/aura_sdk/plugins/interface.py`
  - `AURA/plugins/audio-qualcomm/__init__.py`

## Truth Baseline for This Domain
- Core deterministic kernel (task orchestration, replay finalization boundaries, governance conflict handling) is implemented and evidence-backed.
- Domain-specific patch workflow execution is partially implemented:
  - patch schema/model exist
  - patch API endpoints currently return placeholder/stub responses for list/get/diff/evidence.
- Plugin system contract exists and one real plugin (`audio-qualcomm`) exists, but broader engineering plugin set in this document is a domain boundary definition, not proof of current full implementation.
