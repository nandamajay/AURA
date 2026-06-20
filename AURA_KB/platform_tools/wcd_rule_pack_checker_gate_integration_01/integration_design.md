# WCD Rule-Pack Checker Canonical Gate Integration Design

Generated: 2026-06-20
Scope: proposal only (no production code changes)

## Integration Goals
- Keep `conversion_gate` generic and family-agnostic.
- Allow optional rule-pack execution for family-specific governance signals.
- Preserve deterministic/replayable gate artifacts.
- Keep runtime-sensitive decisions fail-closed by policy.

## Proposed CLI Flags
- `--rule-pack <path>`: rule-pack JSON file path.
- `--rule-pack-family <name>`: rule-pack family identifier (`wcd` initially).
- `--rule-pack-mode off|advisory|warn|blocking`: policy mode.
- `--rule-pack-output <path>`: explicit compliance report path.

### Suggested Defaults
- `--rule-pack-mode advisory` when `--rule-pack` is provided.
- `--rule-pack-family` required only when `--rule-pack` is set.
- Default output path: `<run-dir>/rule_pack/<family>_rule_pack_compliance_report.json`.

## Invocation Model
1. Run existing gate flow unchanged through scorer/verifier execution.
2. If `--rule-pack` is set and mode != `off`, invoke checker as an internal module call (preferred) or subprocess (fallback policy).
3. Persist checker report path in gate verdict extension fields.
4. Apply policy mapping (`off|advisory|warn|blocking`) to determine gate effect.

## Embedding/Linking Strategy
- Always store checker JSON as standalone artifact.
- Add additive verdict extension:
  - `rule_pack_summary` for single pack.
  - `rule_packs[]` for multi-pack future.
- Keep current fields (`verdict`, `reasons`, `score_summary`, `verifier_summary`) unchanged.

## Artifact Path Management
- Primary convention: `<run-dir>/rule_pack/`.
- `--rule-pack-output` allows deterministic override.
- Store absolute path in verdict for replay.
- Include file hash in `inputs_manifest` extension for provenance.

## Keeping Generic Gate Family-Agnostic
- No hardcoded WCD rule logic inside `conversion_gate`.
- `conversion_gate` only handles generic plugin lifecycle:
  - validate plugin input,
  - call checker,
  - apply mode policy,
  - record summary.
- Family-specific semantics remain in rule-pack checker module and rule data.

## Future Rule-Pack Extensibility
- Support multiple families by repeating invocation contract:
  - `--rule-pack-family <family>`
  - `--rule-pack <rules.json>`
- Future aggregator merges gate effects by severity (`NONE < INFO < WARN < BLOCK`).

## Failure Handling
### Missing Rule Pack
- `off`: ignore.
- `advisory`: record INFO diagnostic, no verdict change.
- `warn`: add gate warning.
- `blocking`: block only if checker returns FAIL (policy-mapped), otherwise warn.

### Checker Crash
- Do not crash canonical gate process.
- Emit checker diagnostic artifact and policy-mapped gate effect.
- In advisory/warn modes: non-blocking WARN/INFO.
- In blocking mode: proposal recommends WARN_ONLY initially until crash taxonomy matures.

### No Converted Directory
- Checker returns FAIL for missing run-dir or UNKNOWN/MISSING checks as applicable.
- Policy mapping decides gate effect; default advisory prevents accidental blocking.

### No-target / New-driver Mode
- Preserve current gate behavior (`scoring_skipped_no_upstream_dir` -> WARN).
- Rule-pack output is additive and should not reinterpret scorer skip as runtime failure.

## Deterministic/Replayable Requirements
- Pin rule-pack file path and hash in gate manifest extension.
- Emit deterministic output paths and stable JSON key ordering where practical.
- Ensure checker outputs are generated from artifacts only (no network/time-variant dependencies beyond timestamp field).

## Recommended First Integration Step
- Implement `advisory` mode only behind explicit `--rule-pack` flags.
- No default-on behavior until regression suite in `regression_test_plan.json` passes.
