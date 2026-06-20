# Risk Analysis: WCD Rule-Pack Checker Gate Integration

Generated: 2026-06-20

## Vendor-token heuristic false positives
- Risk: token scans (`msm_`, `bolero`) can match benign identifiers or comments.
- Impact: unnecessary WARN noise and potential blocker risk if prematurely promoted.
- Control: keep WARN-only until symbol-aware detection is implemented.

## Terminology check false positives
- Risk: LA/LE terms may be absent in concise artifacts while governance quality is still good.
- Impact: low-severity noise.
- Control: keep as advisory signal; exclude logs/large files and allow per-run opt-out.

## Runtime evidence detection false negatives
- Risk: runtime evidence may exist but not match filename/phrase heuristics.
- Impact: incorrect WARN or missed runtime misuse detection.
- Control: require evidence-ID schema integration before any blocking policy.

## Lineage schema variation
- Risk: lineage appears under different paths (`patch_lineage.json` vs `patches/patch_lineage.json`) and schema structures.
- Impact: MISSING/WARN despite valid lineage data.
- Control: preserve schema-tolerant parsing and add explicit adapters before blocking.

## Missing converted directory cases
- Risk: some runs are planning-only or artifact-incomplete by design.
- Impact: checker may emit UNKNOWN/MISSING states.
- Control: policy mapping should keep these non-blocking outside strict/blocking mode.

## Family-specific rule overreach
- Risk: WCD-specific heuristics in generic gate can hurt other families.
- Impact: cross-family false warnings, governance coupling debt.
- Control: plugin/rule-pack architecture with explicit `--rule-pack-family` and mode gating.

## Risk of blocking good patches
- Highest drivers: heuristic vendor/token checks and runtime phrase checks.
- Mitigation: advisory/warn rollout, threshold tuning on historical runs, PM override workflow.

## Risk of allowing bad patches
- Highest drivers: hidden-target violations, derivation risk, runtime blocker relaxation.
- Mitigation: mature deterministic checks promoted to blocking only after targeted regression coverage.

## PM interpretation guidance
- Treat checker as governance context, not runtime proof.
- Prioritize deterministic signals (rule parse, lineage existence, derivation warnings from verifier artifacts).
- Interpret heuristic warnings as review prompts unless corroborated by stronger evidence.
- Keep WCD9378 runtime-sensitive decisions fail-closed until hardware evidence arrives.
