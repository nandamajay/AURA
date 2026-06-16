# UPSTREAM_ACCEPTANCE_CHECKLIST

Purpose: determine whether VA runtime PM LPI-aware sequencing is worth upstreaming (assuming code is technically correct).

Scope: evidence-only package for concerns raised by Mark Brown, Srinivas Kandagatla, and Liam Girdwood.

Ordering: highest ROI first (largest acceptance gain per validation effort).

---

## 1) Quantified power benefit vs upstream baseline
- Concern owners: Mark Brown, Srinivas Kandagatla
- Classification: REQUIRED_FOR_UPSTREAM
- Evidence required:
  - A/B power data showing meaningful reduction from the change.
- How to collect:
  - Compare baseline kernel vs candidate kernel on same hardware/firmware.
  - Use board power rails or external power meter + software counters.
- Exact test procedure:
  1. Boot baseline; run idle-audio scenario (no capture stream, runtime PM active) for 10 min.
  2. Record average and p95 power for audio-related rails and total platform power.
  3. Repeat with candidate kernel under identical thermal/governor conditions.
  4. Run with/without NPL clock paths where applicable.
- Expected success criteria:
  - Statistically significant power reduction (target >= 3-5% on relevant rail or measurable system-level gain) with no regressions.
- Metrics to capture:
  - Mean/p95 power (mW), standard deviation, sample count, thermal state, CPUfreq governor, residency times.
- Upstream acceptance impact:
  - Converts “policy-only parity” into measurable user/platform value; directly addresses “why upstream this?”.

---

## 2) Runtime PM stability under stress (no regressions)
- Concern owners: Liam Girdwood, Mark Brown
- Classification: REQUIRED_FOR_UPSTREAM
- Evidence required:
  - No PM/runtime instability with aggressive transitions.
- How to collect:
  - Stress runtime suspend/resume, stream start/stop, DAPM route toggles.
- Exact test procedure:
  1. Loop 10,000 cycles of start/stop capture stream with random inter-arrival.
  2. Loop 10,000 forced runtime suspend/resume opportunities.
  3. Include concurrent background CPU/memory load.
  4. Capture kernel logs and PM tracepoints.
- Expected success criteria:
  - Zero kernel warnings/oops; zero stuck states; zero unrecoverable stream failures.
- Metrics to capture:
  - Failure count, WARN/OOPS count, recoverable error count, suspend/resume latency distribution.
- Upstream acceptance impact:
  - Addresses sequencing-risk objections and proves operational safety.

---

## 3) Functional audio regression matrix
- Concern owners: Srinivas Kandagatla, Liam Girdwood
- Classification: REQUIRED_FOR_UPSTREAM
- Evidence required:
  - No functional audio regressions in VA use cases.
- How to collect:
  - A/B functional test matrix over supported sample rates/routes.
- Exact test procedure:
  1. Validate capture paths (DMIC variants) across rates used by VA.
  2. Repeated open/close, pause/resume, route changes.
  3. Suspend/resume while stream inactive and active (if supported).
- Expected success criteria:
  - 100% pass of existing VA functional suite; no new xruns/glitches beyond baseline.
- Metrics to capture:
  - Pass/fail matrix, xrun counts, stream bring-up failure rate, glitch incidents.
- Upstream acceptance impact:
  - Demonstrates no feature breakage despite PM sequencing changes.

---

## 4) Clock vote/unvote correctness proof
- Concern owners: Liam Girdwood
- Classification: REQUIRED_FOR_UPSTREAM
- Evidence required:
  - No clock refcount imbalance or invalid ordering side effects.
- How to collect:
  - Trace clk APIs and PM transitions; verify balanced enables/disables.
- Exact test procedure:
  1. Enable ftrace/events for clock + runtime PM paths.
  2. Run stress scenarios from items #2 and #3.
  3. Post-process traces for unmatched enable/disable and forbidden orderings.
- Expected success criteria:
  - Zero imbalance events; expected ordering invariant holds in all transitions.
- Metrics to capture:
  - Clock enable/disable counts per clock, imbalance count, invalid-order count.
- Upstream acceptance impact:
  - Removes primary technical risk argument against accepting PM policy change.

---

## 5) Wake/resume latency impact
- Concern owners: Mark Brown, Liam Girdwood
- Classification: STRONGLY_RECOMMENDED
- Evidence required:
  - Latency cost is acceptable relative to power gain.
- How to collect:
  - A/B measure resume-to-first-valid-sample and runtime resume latency.
- Exact test procedure:
  1. Measure 1,000 capture starts from runtime-suspended state on baseline/candidate.
  2. Record end-to-end latency and jitter.
- Expected success criteria:
  - No material regression beyond agreed tolerance (example: <= 5% median increase).
- Metrics to capture:
  - Median/p95/p99 latency (ms), jitter, timeout/failure count.
- Upstream acceptance impact:
  - Balances power claim with responsiveness costs.

---

## 6) Cross-platform validation coverage
- Concern owners: Srinivas Kandagatla
- Classification: STRONGLY_RECOMMENDED
- Evidence required:
  - Behavior confirmed on multiple relevant Qualcomm targets.
- How to collect:
  - Run required tests (#1-#4) on at least two SoC/platform variants.
- Exact test procedure:
  1. Execute full required evidence suite on Platform A and Platform B.
  2. Include one variant with NPL and one without (if available).
- Expected success criteria:
  - Consistent pass and power trend across tested platforms.
- Metrics to capture:
  - Per-platform pass rates, power deltas, latency deltas, anomalies.
- Upstream acceptance impact:
  - Reduces maintainer concern about board-specific tuning being upstreamed globally.

---

## 7) SoundWire/graph interaction non-regression
- Concern owners: Srinivas Kandagatla
- Classification: STRONGLY_RECOMMENDED
- Evidence required:
  - No side effects on SoundWire/lpass graph sequencing during PM transitions.
- How to collect:
  - Capture SDW and DAPM logs around runtime PM and stream lifecycle.
- Exact test procedure:
  1. Run stream start/stop + runtime PM stress with SDW tracing enabled.
  2. Verify no link bring-up failures, stale route states, or timeouts.
- Expected success criteria:
  - Zero SDW timeout/recovery anomalies beyond baseline.
- Metrics to capture:
  - SDW error count, recovery attempts, route activation failures.
- Upstream acceptance impact:
  - Prevents cross-subsystem regressions from blocking acceptance.

---

## 8) Long-run soak and thermal drift behavior
- Concern owners: Liam Girdwood
- Classification: OPTIONAL
- Evidence required:
  - Stability and benefit persist over long duration.
- How to collect:
  - 24-48 hour soak with periodic stream activity + idle windows.
- Exact test procedure:
  1. Alternate active/idle windows every 5-10 minutes.
  2. Monitor PM state transitions, logs, and power trend drift.
- Expected success criteria:
  - No cumulative failures; power benefit does not collapse under thermal drift.
- Metrics to capture:
  - Error rate over time, power trend by hour, thermal profile.
- Upstream acceptance impact:
  - Improves confidence but usually not gating if required evidence is strong.

---

## 9) Upstream policy rationale document
- Concern owners: Mark Brown
- Classification: STRONGLY_RECOMMENDED
- Evidence required:
  - Clear rationale that this is not random downstream replay.
- How to collect:
  - Concise engineering note mapping behavior to measurable outcomes and risk controls.
- Exact test procedure:
  1. Summarize findings from #1-#7.
  2. State tradeoffs (power vs latency) and why chosen policy is justified.
- Expected success criteria:
  - Reviewer can trace claim -> metric -> conclusion without ambiguity.
- Metrics to capture:
  - N/A (documentation artifact with referenced metrics).
- Upstream acceptance impact:
  - Increases review throughput and reduces request-for-revision loops.

---

## 10) Submission readiness gate (go/no-go)
- Concern owners: Panel-wide
- Classification: REQUIRED_FOR_UPSTREAM
- Evidence required:
  - All required items complete with reproducible logs and scripts.
- How to collect:
  - One gate report aggregating pass/fail and deltas vs baseline.
- Exact test procedure:
  1. Verify items #1-#4 are complete and passing.
  2. Verify no user-visible ABI additions were introduced.
  3. Attach artifacts (raw logs, metrics CSV, environment manifest).
- Expected success criteria:
  - 100% pass of required items and no unresolved high-severity anomalies.
- Metrics to capture:
  - Checklist completion status, anomaly counts by severity.
- Upstream acceptance impact:
  - Provides objective basis for “worth upstreaming” decision.

---

## Quick ROI Summary
1. Power delta proof (#1) — highest acceptance leverage.
2. PM stability stress (#2) — highest risk reduction.
3. Functional regression matrix (#3) — baseline safety proof.
4. Clock correctness proof (#4) — sequencing confidence.
5. Latency tradeoff (#5) — policy balance.
6. Cross-platform coverage (#6) — generalization confidence.
7. SDW interaction checks (#7) — subsystem confidence.
8. Rationale write-up (#9) — review efficiency.
9. Soak test (#8) — additional confidence.
10. Gate report (#10) — release decision artifact.
