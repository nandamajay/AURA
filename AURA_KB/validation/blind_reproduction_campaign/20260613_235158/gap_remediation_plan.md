# Gap Remediation Plan

## Constraints
- No new driver reproduction.
- No new driver corpus mining.
- Remediation uses existing training-driver artifacts and already-indexed sources only.

## Gap 1: KNOWLEDGE_GAP
### Problem
Blind reconstructions are too high-level and miss callback-level parity (ops wiring, event sequencing, helper placement).

### Remediation
1. Create per-family reconstruction checklists from existing upstream files already in corpus:
   - codec checklist: required callbacks/ops (`hw_params`, `hw_free`, `set_stream`, `mute_stream`, PM hooks, bus hooks).
   - macro checklist: component_probe + platform_probe/remove layering, runtime callbacks.
2. Add "minimum required symbol parity" gates before accepting reconstruction drafts.
3. Add per-driver file-layout parity templates (single-file vs split-file expectations).

### Success metric
- Architecture similarity for codec drivers rises from 46.7/46.7/58.3 to >=80.

## Gap 2: RULE_GAP
### Problem
Campaign scoring logic contains non-applicable dimensions (e.g., SoundWire penalty for LPASS macro drivers).

### Remediation
1. Introduce driver-type-aware scoring profile:
   - `codec_sdw`: include SoundWire heavily.
   - `macro`: reduce SoundWire weight to 0 or mark N/A.
   - `codec_split`: explicitly include split-file parity criterion.
2. Add registration-path parity checks for `snd_soc_component_driver` presence and component-probe layering.

### Success metric
- Macro overall similarity increases by >=5 points without changing generated reconstructions.

## Gap 3: PATTERN_GAP
### Problem
SWR->SDW migration pattern and split-file transport pattern were not encoded strongly enough.

### Remediation
1. Add validated pattern cards (local remediation pack):
   - SWR downstream abstraction -> SDW upstream abstraction mapping steps.
   - WCD split transport pattern (`core file` + `sdw side file`).
2. Require these pattern cards in reconstruction prompt/input for codec families.

### Success metric
- `wsa883x`, `wsa884x`, `wcd938x` architecture similarity each >=85.

## Gap 4: MAINTAINER_MODEL_GAP
### Problem
Reviewer prediction misses are driven by low direct review evidence for 5/6 drivers and over-generic prediction templates.

### Remediation
1. Build driver-scoped reviewer expectation matrices using only existing lore/patch/review artifacts currently in KB.
2. Use confidence-qualified predictions (HIGH only where direct driver evidence exists).
3. Score reviewer predictions with confidence weighting to avoid hard-penalizing low-evidence reviewers.

### Success metric
- Reviewer prediction metric rises from 52.3% to >=70% (or >=80% confidence-weighted).

## Gap 5: PATCH_STRATEGY_GAP
### Problem
Patch decomposition model underfit wsa883x history.

### Remediation
1. Add patch-shape heuristics per driver family from existing patch_history files:
   - WSA codec: DT+core initial, controls/DAPM and PM fixes as follow-ups.
   - WCD: larger staged multi-patch series.
   - LPASS macros: core + DAPM/route split.
2. Validate predicted patch count against historical ranges before scoring.

### Success metric
- Patch similarity >=90 for all 6 drivers (currently one at 76).
