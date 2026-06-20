# AURA Production Gap Matrix

Generated: 2026-06-20T20:21:53.811699+00:00
Production target: `/local/mnt/workspace/AURA`

## Summary

| Metric | Count |
|---|---:|
| Total gaps | 12 |
| HIGH severity | 10 |
| MEDIUM severity | 2 |
| LOW severity | 0 |

## Counts By Category

| Category | Count |
|---|---:|
| `ADVERSARIAL_VALIDATION` | 1 |
| `CONTRACT_TEST_COVERAGE` | 4 |
| `IMPLICIT_CONTRACT` | 6 |
| `TECH_DEBT_COMPLETENESS` | 1 |

## Top 5 Critical Gaps Blocking Phase 1

| Gap ID | Category | Component | File:Line | Description | Remediation | Effort |
|---|---|---|---|---|---|---|
| GAP-009 | `CONTRACT_TEST_COVERAGE` | Orchestrator._run_agent → agent run.sh | `/local/mnt/workspace/AURA/aura/core/orchestrator.py:95` | Contract IC-002 is PARTIALLY_TESTED with missing edge cases: malformed input, missing required fields, invalid output shape, fail-closed behavior. | Add tests for malformed input, missing required fields, invalid output shape, and fail-closed behavior. | L |
| GAP-012 | `CONTRACT_TEST_COVERAGE` | Orchestrator → approval gate artifact | `/local/mnt/workspace/AURA/aura/core/orchestrator.py:432` | Contract IC-007 is PARTIALLY_TESTED with missing edge cases: malformed input, missing required fields, invalid output shape, fail-closed behavior. | Add tests for malformed input, missing required fields, invalid output shape, and fail-closed behavior. | L |
| GAP-010 | `CONTRACT_TEST_COVERAGE` | rule_engine.py → rules YAML | `/local/mnt/workspace/AURA/aura/core/rule_engine.py:1` | Contract IC-004 is PARTIALLY_TESTED with missing edge cases: malformed input, missing required fields, invalid output shape, fail-closed behavior. | Add tests for malformed input, missing required fields, invalid output shape, and fail-closed behavior. | L |
| GAP-011 | `CONTRACT_TEST_COVERAGE` | state.py → orchestration.db | `/local/mnt/workspace/AURA/aura/core/state.py:12` | Contract IC-005 is PARTIALLY_TESTED with missing edge cases: malformed input, missing required fields, invalid output shape, fail-closed behavior. | Add tests for malformed input, missing required fields, invalid output shape, and fail-closed behavior. | L |
| GAP-003 | `IMPLICIT_CONTRACT` | cli.py → Orchestrator.run_module | `/local/mnt/workspace/AURA/aura/cli.py:85` | Implicit unformalized contract: module: str, dry_run: bool; return dict containing status and run_id-like fields. | Create a JSON Schema/Pydantic v1 contract and enforce it at the caller/callee boundary. | L |

## Full Gap Matrix

| Gap ID | Category | Severity | Status | Component | File:Line | Description | Remediation | Effort |
|---|---|---|---|---|---|---|---|---|
| GAP-001 | `ADVERSARIAL_VALIDATION` | MEDIUM | OPEN | tests | `/local/mnt/workspace/AURA/tests:0` | No scorer component was found in the bounded AURA tree, so scorer edge-case coverage is not applicable and should be treated as TOOL_MISSING for this target. | If scoring is expected in this AURA version, add or link the scorer module and tests for empty files, zero-line diffs, and missing upstream references. | M |
| GAP-002 | `TECH_DEBT_COMPLETENESS` | HIGH | OPEN | source | `/local/mnt/workspace/AURA/README.md:92` | - If `patch_text` is missing, AURA attempts source-based diff synthesis from resolved downstream/upstream files. | Convert marker into tracked issue or resolve before/while implementing the owning Phase 1 subsystem. | M |
| GAP-003 | `IMPLICIT_CONTRACT` | HIGH | OPEN | cli.py → Orchestrator.run_module | `/local/mnt/workspace/AURA/aura/cli.py:85` | Implicit unformalized contract: module: str, dry_run: bool; return dict containing status and run_id-like fields. | Create a JSON Schema/Pydantic v1 contract and enforce it at the caller/callee boundary. | L |
| GAP-004 | `IMPLICIT_CONTRACT` | HIGH | OPEN | Orchestrator._run_agent → agent run.sh | `/local/mnt/workspace/AURA/aura/core/orchestrator.py:95` | Implicit unformalized contract: Agent process must accept --task/--module/--round and emit JSON on stdout. | Create a JSON Schema/Pydantic v1 contract and enforce it at the caller/callee boundary. | L |
| GAP-005 | `IMPLICIT_CONTRACT` | HIGH | OPEN | rule_engine.py → rules YAML | `/local/mnt/workspace/AURA/aura/core/rule_engine.py:1` | Implicit unformalized contract: YAML file must contain expected rule layer/list fields consumed by rule validation. | Create a JSON Schema/Pydantic v1 contract and enforce it at the caller/callee boundary. | L |
| GAP-006 | `IMPLICIT_CONTRACT` | HIGH | OPEN | state.py → orchestration.db | `/local/mnt/workspace/AURA/aura/core/state.py:12` | Implicit unformalized contract: runs/events/approvals tables with id, run_id, status, payload_json and timestamp columns. | Create a JSON Schema/Pydantic v1 contract and enforce it at the caller/callee boundary. | L |
| GAP-007 | `IMPLICIT_CONTRACT` | MEDIUM | OPEN | dashboard.py → orchestration.db queries | `/local/mnt/workspace/AURA/aura/core/dashboard.py:597` | Implicit unformalized contract: Dashboard assumes runs/events payload_json contains structured JSON with latest patch and score fields. | Create a JSON Schema/Pydantic v1 contract and enforce it at the caller/callee boundary. | M |
| GAP-008 | `IMPLICIT_CONTRACT` | HIGH | OPEN | Orchestrator → approval gate artifact | `/local/mnt/workspace/AURA/aura/core/orchestrator.py:432` | Implicit unformalized contract: Patch artifact quality dict must include approval_gate_passed boolean and status PASS/FAIL. | Create a JSON Schema/Pydantic v1 contract and enforce it at the caller/callee boundary. | L |
| GAP-009 | `CONTRACT_TEST_COVERAGE` | HIGH | OPEN | Orchestrator._run_agent → agent run.sh | `/local/mnt/workspace/AURA/aura/core/orchestrator.py:95` | Contract IC-002 is PARTIALLY_TESTED with missing edge cases: malformed input, missing required fields, invalid output shape, fail-closed behavior. | Add tests for malformed input, missing required fields, invalid output shape, and fail-closed behavior. | L |
| GAP-010 | `CONTRACT_TEST_COVERAGE` | HIGH | OPEN | rule_engine.py → rules YAML | `/local/mnt/workspace/AURA/aura/core/rule_engine.py:1` | Contract IC-004 is PARTIALLY_TESTED with missing edge cases: malformed input, missing required fields, invalid output shape, fail-closed behavior. | Add tests for malformed input, missing required fields, invalid output shape, and fail-closed behavior. | L |
| GAP-011 | `CONTRACT_TEST_COVERAGE` | HIGH | OPEN | state.py → orchestration.db | `/local/mnt/workspace/AURA/aura/core/state.py:12` | Contract IC-005 is PARTIALLY_TESTED with missing edge cases: malformed input, missing required fields, invalid output shape, fail-closed behavior. | Add tests for malformed input, missing required fields, invalid output shape, and fail-closed behavior. | L |
| GAP-012 | `CONTRACT_TEST_COVERAGE` | HIGH | OPEN | Orchestrator → approval gate artifact | `/local/mnt/workspace/AURA/aura/core/orchestrator.py:432` | Contract IC-007 is PARTIALLY_TESTED with missing edge cases: malformed input, missing required fields, invalid output shape, fail-closed behavior. | Add tests for malformed input, missing required fields, invalid output shape, and fail-closed behavior. | L |

## Mitigated Or Passing Areas

- Architecture enforcement passed earlier with zero violations in `evidence/p0_w1_t1_architecture_enforcement_report.json`.
- Existing bounded target test suite passed: 15/15 tests.
- Contract registry and five draft-07 schemas parse successfully under `contracts/`.
