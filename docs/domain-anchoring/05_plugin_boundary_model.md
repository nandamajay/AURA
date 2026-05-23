# Plugin Boundary Model for Engineering Runtime

Date: 2026-05-18

## 1) Domain Plugin Definitions (Target Set)
This section defines boundary roles for domain plugins. It does not claim full current implementation of each plugin.

1. Patch ingestion plugin
- role: normalize downstream intake metadata and task descriptors

2. Diff analysis plugin
- role: structural/code-level delta analysis and tagging

3. Upstream compliance plugin
- role: coding/process compliance checks (checkpatch/sparse/clang/etc wrappers)

4. Validation orchestration plugin
- role: build validation plans and map test categories to execution tasks

5. CI/review plugin
- role: integrate CI verdict surfaces and reviewer signal normalization

6. Artifact/evidence plugin
- role: collect and index engineering artifacts and evidence pointers

7. Operator approval plugin
- role: proposal generation for approval packs (without decision authority)

## 2) What MUST remain in `aura-core`
- queue ownership and dispatch policy
- retry scheduling semantics
- governance transition enforcement
- replay finalization and integrity verification
- audit persistence and chronology integrity
- persistence-before-broadcast guarantees

## 3) What MUST remain operator-controlled
- final approve/reject decisions
- overrides/rollback/interventions
- acceptance of bounded-risk outcomes
- release/go-live decisions based on evidence

## 4) What plugins are allowed to do
- generate domain analysis outputs
- suggest decisions with confidence annotations
- emit evidence references via controlled APIs
- request governance actions (not execute unilaterally)

## 5) What plugins are forbidden from doing
- direct writes to audit/replay/governance tables
- mutating queue/retry policy
- mutating governance rules
- bypassing operator authority
- hiding failure/retry/fallback behavior

## 6) Engineering Runtime Trust Boundaries
Engineering-runtime trust assumptions:
- core orchestration/replay/governance paths are the only authority for deterministic control state
- plugin outputs are advisory/execution inputs until governance/operator acceptance
- evidence lineage, not plugin claims, determines trust in outcomes

Plugin trust assumptions:
- cooperative bounded actors
- no hard sandbox trust boundary claim

Operator trust assumptions:
- operator remains final authority for irreversible/high-risk decisions
- operator actions are auditable and justifiable

CI/runtime trust assumptions:
- CI signals are informative but not autonomous authority
- CI parity checks must remain deterministic and hard-fail capable

## 7) GOOD vs BAD Engineering Plugin Patterns
GOOD:
- plugin emits `patch_lineage_suggestion` as task output + evidence refs, then requests approval workflow
- plugin failure produces explicit task failure and preserved evidence

BAD:
- plugin auto-approves patch stage progression by directly updating `approvals` table
- plugin hides retry bursts and returns synthetic success to appear stable
- plugin rewrites finalized replay artifacts to match expected outputs
