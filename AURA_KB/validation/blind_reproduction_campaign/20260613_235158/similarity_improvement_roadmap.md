# Similarity Improvement Roadmap (>90%)

## Baseline
- Current campaign overall: 79.2%

## Target
- Overall similarity: >90% without reproducing new drivers.

## Phase A (Week 1): Scoring and template corrections
1. Implement driver-type-aware scoring weights (remove inappropriate SoundWire penalty for macro drivers).
2. Enforce mandatory symbol parity checklist for reconstruction outputs.
3. Add split-file parity check for WCD family.

Expected uplift: +4 to +6 points overall.

## Phase B (Week 1-2): Pattern/rule injection into reconstruction packs
1. Inject SWR->SDW transformation pattern card into WSA/WCD reconstruction templates.
2. Inject codec-vs-macro registration-path parity rules (`component_driver` + probe layering).
3. Add callback-level minimum matrix for PM and stream lifecycle.

Expected uplift: +6 to +8 points overall.

## Phase C (Week 2): Reviewer prediction calibration
1. Replace generic reviewer block with driver-evidence-weighted reviewer matrix.
2. Score reviewer accuracy in two tracks:
   - raw
   - confidence-weighted
3. Mark low-evidence reviewer predictions as constrained rather than hard misses.

Expected uplift: +2 to +4 points overall (larger in confidence-weighted track).

## Phase D (Week 2): Patch strategy tuning
1. Apply family-specific patch-shape priors from existing patch histories.
2. Validate predicted patch decomposition against known accepted-series ranges before final scoring.

Expected uplift: +1 to +3 points overall.

## Measurable actions and thresholds
| Action | Metric | Baseline | Target |
|---|---:|---:|---:|
| Codec architecture parity checklist | Avg architecture (3 codec drivers) | 50.6% | >=85% |
| Macro scoring profile fix | Avg macro overall | 84.2% | >=89% |
| Reviewer model calibration | Reviewer metric | 52.3% | >=70% raw / >=80% confidence-weighted |
| Patch-shape priors | Min patch similarity | 76% | >=90% |
| Campaign overall | Overall similarity | 79.2% | >90% |

## Exit criteria
- All six drivers >=88% overall.
- Campaign weighted average >90%.
- No driver has reviewer confidence-unqualified score below 65%.
