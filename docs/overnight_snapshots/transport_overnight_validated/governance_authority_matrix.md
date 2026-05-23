# Governance Authority Matrix

| Capability | Linux AURA Governance | Windows Worker |
|---|---|---|
| Command approval | AUTHORITATIVE | NONE |
| Allowlist validation | AUTHORITATIVE | NONE |
| Forbidden pattern detection | AUTHORITATIVE | NONE |
| Runtime policy enforcement | AUTHORITATIVE | NONE |
| Protocol syntax validation | AUTHORITATIVE + VERIFY | BASIC INPUT VALIDATION |
| Request integrity generation | AUTHORITATIVE | ECHO ONLY |
| Response integrity verification | AUTHORITATIVE | GENERATE ONLY |
| Semantic/runtime classification | AUTHORITATIVE | NONE |
| Evidence interpretation | AUTHORITATIVE | RAW CAPTURE ONLY |
| Merge-readiness governance | AUTHORITATIVE | NONE |

## Governance result constraints
- No runtime parity claim without replay-backed evidence.
- No merge readiness from transport layer alone.
- Unknown outcomes remain unknown.
