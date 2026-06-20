# WCD Rule-Pack Checker Prototype 01 Design

Generated: 2026-06-20

## Purpose
Prototype an executable governance checker that evaluates whether a WCD-family conversion/run directory aligns with promoted LA-to-LE rules.

The checker is report-only and deterministic:
- It reads rule artifacts and run artifacts.
- It emits a compliance JSON report.
- It does not modify kernel source, driver source, or canonical gate/scorer outputs.

## Inputs
Required:
- `--rules`: promoted rules JSON.
- `--run-dir`: conversion/run artifact directory.
- `--output`: output compliance report path.

Optional:
- `--strict`: escalate selected warnings/missing states to failures.
- `--driver-family`: report label (default `wcd`).
- `--terminology`: mappings like `LA=downstream LE=upstream`.

## Outputs
Primary output:
- JSON compliance report using `wcd_rule_pack_compliance_report` schema.

Contains:
- overall verdict,
- per-check findings,
- rule-to-check coverage mapping,
- known limitations and heuristic boundaries.

## Rule Classes Supported in Prototype
Implemented check classes:
1. Rule file parse/schema integrity.
2. Run artifact presence inventory.
3. Lineage entry inference (schema-tolerant).
4. Runtime-sensitive rule evidence/fail-closed posture.
5. Vendor-token heuristic scan over converted files/patches.
6. Hidden-target allowlist discipline audit.
7. Downstream derivation risk surfacing from existing verifier/audit outputs.
8. LA/LE terminology presence scan in governance docs.
9. Build/gate/scoring status summarization (read-only).

## Enforced Now vs Report-Only
Enforced now (prototype-level verdict impact):
- Rule file parse failures.
- Missing/invalid run directory.
- Strict-mode escalations for critical warnings.

Report-only / heuristic:
- Vendor token scan.
- Runtime claim phrase scan.
- Terminology usage scan.
- Hidden-target inference when artifacts are incomplete.

## Known Limitations
- Vendor elimination scan is token-based and may over/under-report.
- Runtime evidence detection is artifact-name based; it does not validate evidence quality.
- DAPM/regmap/MBHC/Class-H correctness is not semantically re-verified.
- Derivation risk is surfaced from existing artifacts; full similarity is not recomputed.
- Terminology check inspects md/json governance artifacts only.

## Future Integration with Canonical Gate
Planned integration path:
1. Keep checker standalone as a pre-gate/post-gate audit companion.
2. Promote stable checks into canonical gate/verifier modules after threshold tuning.
3. Use rule-mapping coverage to decide what can be auto-enforced vs PM/manual review.
4. Add confidence penalties for downstream derivation warnings and vendor-regression signals.

## False-Claim Avoidance
The checker explicitly avoids runtime claims by design:
- Runtime-sensitive rules are evaluated against fail-closed artifacts.
- Missing runtime evidence defaults to `FAIL_CLOSED_OK` or warning, not readiness.
- Build/gate summaries are read-only and never interpreted as runtime readiness proof.
