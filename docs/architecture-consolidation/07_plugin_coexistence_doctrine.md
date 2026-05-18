# Plugin Coexistence Doctrine

Date: 2026-05-18

## Coexistence Objective
Support bounded multi-domain workloads safely inside a shared single-node control plane.

## Plugin Execution Model
- Plugins are loaded by registry and executed through shared orchestrator/runtime services.
- Plugin domain identity is propagated via `plugin_domain` and `runtime_cell_scope` markers.
- Agents remain CLI subprocesses; plugins do not own scheduler/governance/replay kernels.

## Isolation Doctrine
### Proven Safe
- replay namespace bleed detection (safe in latest coexistence evidence)
- governance phase cross-contamination (safe)
- retry-order interaction contamination (safe in latest run)

### Bounded
- queue starvation sensitivity
- websocket shared-channel pressure behavior
- replay-buffer pressure and eviction
- watchdog cross-domain effects
- plugin failure containment (load-time, not trust boundary)

### Not Guaranteed
- hard process isolation per plugin
- trust sandbox boundaries
- independent infrastructure partitions

## Shared Infrastructure Boundaries
Shared and canonical:
- task scheduler
- event bus + ws/sse delivery path
- audit ledger
- replay storage backend

## Runtime Cell Preparation (Current)
Current runtime cell is a logical boundary model:
- domain tagging
- scoped routing
- scoped retry lineage
- derived per-domain observability

No runtime-cell process partitioning is currently implemented.
