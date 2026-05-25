# Runtime Equivalence Matrix

| Target | Structural Evidence | Runtime Observability | Equivalence | Confidence | Classification |
|---|---|---|---|---:|---|
| SoundWire transport topology | SWR hits downstream / SDW hits upstream | Missing runtime transport trace | UNKNOWN | 0.26 | advisory_only, runtime_unverified, escalation_required |
| MBHC semantic behavior | MBHC symbol overlap and JACK tokens present | Missing jack/interrupt hardware traces | UNKNOWN | 0.24 | advisory_only, runtime_unverified, escalation_required |
| DAPM route integrity | DAPM tokens visible both sides | Missing full downstream route graph | UNKNOWN | 0.21 | advisory_only, runtime_unverified, escalation_required |
| ALSA control surface | Upstream controls extracted; downstream surface partial | Missing downstream full control inventory | UNKNOWN | 0.19 | advisory_only, runtime_unverified, escalation_required |
| Calibration ownership flow | wcdcal present downstream, absent upstream | Missing transition runtime instrumentation | NOT_ESTABLISHED | 0.12 | advisory_only, runtime_unverified, escalation_required |
| Regulator sequencing behavior | Regulator APIs present both sides | Missing ordering/timing traces | UNKNOWN | 0.18 | advisory_only, runtime_unverified, escalation_required |
| Probe/remove lifecycle | Probe/remove hooks present structurally | Missing ordered runtime lifecycle comparison | UNKNOWN | 0.31 | advisory_only, runtime_unverified |
| Runtime PM sequencing | pm_runtime present both sides with count asymmetry | Missing suspend/resume trace parity | UNKNOWN | 0.22 | advisory_only, runtime_unverified, escalation_required |
| Downstream abstraction removal impact | msm_cdc/qti/wcdcal unresolved mappings | Missing replacement behavior evidence | NOT_ESTABLISHED | 0.11 | advisory_only, runtime_unverified, escalation_required |

## Governance Note
- Compile closure was achieved in the continuation run, but semantic confidence was **not** increased from compile success alone.
