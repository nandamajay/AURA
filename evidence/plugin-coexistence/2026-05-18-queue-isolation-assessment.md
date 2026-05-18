# Queue Isolation Assessment

Run ID: `plugin-coexist-20260518T102218Z-yuhxd7`

## Per-Domain Start-Lag
- `driver`: p50=0.349s, p95=0.64s, max=0.673s
- `media`: p50=1.163s, p95=1.621s, max=1.644s
- `automation`: p50=16.77s, p95=17.539s, max=17.604s
- `research`: p50=0.858s, p95=1.21s, max=2.323s

## Queue Sampling
- poll_samples: `12`
- queue before: `{'P0_critical': 0, 'P1_normal': 0, 'P2_background': 0, 'running': 0, 'completed_today': 630, 'failed_today': 0}`
- queue after: `{'P0_critical': 0, 'P1_normal': 0, 'P2_background': 0, 'running': 0, 'completed_today': 686, 'failed_today': 0}`

## Interpretation
- Shared scheduler behavior is deterministic but not domain-isolated.
- `P2` domain (`automation`) experienced significantly higher lag, indicating starvation risk under coexistence pressure.
- Classification: bounded-to-unsafe depending on workload mix and priority skew.
