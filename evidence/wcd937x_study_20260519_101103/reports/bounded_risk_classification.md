# Bounded Risk Classification

## Guaranteed (evidence-backed in this run)
- Immutable source intake + canonical hash recorded (`b334e703415d05923d7f6ecbad9a36d0cb88da92f1ece2737d4529639fb84284`).
- Source snapshot + engineering snapshot frozen with hashes.
- Detached engineering task creation rejection enforced.
- Governance actions and audit ledger rows persisted.
- Replay reconstruction for workflow succeeded (`402680bab41f15d7298db8fdbb1f1c999caeda77deb020b2590284d20892078c`).

## Bounded
- Downstream->upstream API mapping is advisory and based on static/source comparison.
- Transformation plan is governance-approved but validation-complete status is not achieved.
- Dependency graph covers discovered file/symbol/build edges in scoped snapshot; not whole BSP tree.
- Compile and DT validation attempts were executed but environment gaps limit signal quality.

## Non-guaranteed (in current environment)
- Full sparse analysis (tool unavailable/permission issue).
- Clang warning/build analysis (clang unavailable).
- Full DT binding validation (`dt-doc-validate` missing).
- End-to-end kernel compile success for touched subsystem (host/kernel env mismatch).
- Upstream merge-readiness claim.

## Truthfulness Guardrails Applied
- no autonomous learning/self-training claim
- no full-upstream-readiness claim
- explicit failed validation status retained
- operator-gated approval model preserved
