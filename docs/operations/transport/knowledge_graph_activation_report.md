# Knowledge Graph Activation Report

Generated: 2026-05-24T14:14:57.478699+00:00

## Data Sources
- `GET /api/v1/knowledge/rules?limit=60` -> 200
- `GET /api/v1/knowledge/search?q=audio&limit=20` -> 200
- `GET /api/v1/knowledge/evidence/index?limit=120&max_depth=4` -> 200

## Activation Outcome
- Rules loaded: 0
- Search results (`audio`): 0
- Evidence sections loaded: 6
- Evidence files indexed: 270

## Graph Entity Projection
- Rule entities: downstream pattern / upstream equivalent / subsystem/category links
- Evidence entities: section nodes + file nodes (path/size/mtime metadata)
- Relations currently rendered:
  - `applies_to`
  - `scoped_to`
  - `supports`
  - `depends_on`

## Operational Status
- Graph ingestion endpoints are live and reachable.
- Graph is evidence-backed and does not use synthetic data injection.
- Under sparse rule state, graph remains operational via real evidence-section/file entities.

## Blockers
- Rule corpus is currently empty, limiting maintainer/patch/review relationship richness.
