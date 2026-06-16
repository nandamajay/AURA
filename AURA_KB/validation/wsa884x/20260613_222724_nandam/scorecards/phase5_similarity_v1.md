# Phase 5 - Ground Truth Comparison Scorecard (v1)

## Similarity Metrics

| Dimension | Score | Evidence |
|---|---:|---|
| Architecture similarity | 90% | Blind model matched codec+SDW split; upstream uses `sdw_driver` + ASoC component/DAI objects. |
| Registration similarity | 92% | Matching component/DAI/ops patterns and SDW module registration. |
| Runtime PM similarity | 88% | Blind design included autosuspend and resume/suspend hooks; upstream confirms these flows. |
| DAPM similarity | 95% | Blind DAPM model `IN -> SPKR` matches upstream core graph style. |
| DT similarity | 62% | Blind schema compatible/properties diverged from upstream (`compatible` constant and required supplies/oneOf specifics). |
| SoundWire similarity | 93% | Blind stream lifecycle and SDW ownership closely matched upstream. |
| Patch splitting similarity | 55% | Blind plan used 7 patches; actual initial accepted core was compact 2-patch DT+codec series. |
| Maintainer expectation similarity | 74% | Predictions aligned for control/PM/DT themes but lacked direct wsa884x reviewer transcript grounding. |

Overall v1 similarity: **81.1%**
