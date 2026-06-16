# lessons

1. Core upstreaming path is evidenced by superseded->accepted Patchwork states.
2. `commit_ref` gives merged commit linkage.
3. Missing comment bodies are explicitly marked `INSUFFICIENT_EVIDENCE`.


## Blind Reproduction Campaign Validation
- Campaign run `20260613_235158` overall similarity: 73.8%.


## Failure Analysis Pass (Validated)
- Reproduction error was driven mostly by abstraction-level gaps (callback/file-layout parity), reviewer-model sparsity, and scoring-rule misfit for macro drivers.
- Key validated fix direction: driver-type-aware reconstruction/scoring plus explicit SWR->SDW and split-file pattern enforcement.

## Experience Campaign v1 (2026-06-14) - validated
1. Removing standalone cleanup patches and folding changes into ownership patches improved simulated review-survival.
2. Integrating PM+SDW safety in the core patch reduced request-change density in second review round.
3. Combining controls + minimal DAPM in one ownership patch improved review tractability versus micro-splitting.
Evidence:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/experience_campaign/wsa884x/experience_v1/03_review_cycle_v1.md`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/experience_campaign/wsa884x/experience_v1/05_review_cycle_v2.md`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/experience_campaign/wsa884x/experience_v1/07_validated_experience.md`
