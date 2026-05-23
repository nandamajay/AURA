# Runtime Transport Confidence Matrix

| Transport | Confidence | Notes |
|---|---|---|
| adb | UNKNOWN | No live connectivity verified. Governance scan found no hardcoded adb usage outside adapters. |
| serial | UNKNOWN | No live connectivity verified. Governance scan found no serial usage outside adapters. |
| ssh | UNKNOWN | No live connectivity verified. Governance scan found no ssh command execution outside adapters. |
| local | TRANSPORT_READY | Adapter available only. No runtime evidence captured. |
| remote_serial | ADVISORY_ONLY | Distributed bridge implementation exists; live endpoint validation missing. |
| future_diag | UNKNOWN | Placeholder only. |
