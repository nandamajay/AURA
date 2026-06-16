# lessons

1. Core upstreaming path is evidenced by superseded->accepted Patchwork states.
2. `commit_ref` gives merged commit linkage.
3. Missing comment bodies are explicitly marked `INSUFFICIENT_EVIDENCE`.


## Blind Reproduction Campaign Validation
- Campaign run `20260613_235158` overall similarity: 74.0%.


## Failure Analysis Pass (Validated)
- Reproduction error was driven mostly by abstraction-level gaps (callback/file-layout parity), reviewer-model sparsity, and scoring-rule misfit for macro drivers.
- Key validated fix direction: driver-type-aware reconstruction/scoring plus explicit SWR->SDW and split-file pattern enforcement.

## WCD938X Generalization Validation (2026-06-14)
- Validation run: `AURA_KB/validation/real_reconstruction_validation/20260614_004452_wcd938x/`.
- Result: `PARTIALLY` generalized beyond WSA-family assumptions.
- Validated transfer:
  - SDW-native transport lifecycle and split ownership (`wcd938x.c` + `wcd938x-sdw.c`) are reproducible.
  - DT split modeling (codec binding + SDW endpoint binding) is reproducible.
- Validated non-transfer:
  - WSA-style DAPM simplification does not cleanly transfer to WCD938x family complexity.
  - Reviewer prediction remains constrained by `INSUFFICIENT_EVIDENCE` for direct wcd938x comment bodies.
