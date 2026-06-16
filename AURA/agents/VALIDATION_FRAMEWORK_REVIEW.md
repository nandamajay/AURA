# VALIDATION_FRAMEWORK_REVIEW

Scope: Static audit of `VALIDATION_PLAN.md` and scripts under `validation/`.
Method: File inspection only; no runtime execution on DUT.

Severity scale:
- CRITICAL: can invalidate conclusions or make framework unusable on common targets
- HIGH: likely to produce materially wrong pass/fail outcomes
- MEDIUM: meaningful quality/portability risk, but usually recoverable
- LOW: minor robustness/documentation issue

---

## 1) `VALIDATION_PLAN.md`

### 1. Missing dependencies
- `arecord`, `timeout`, `python3`, root shell are assumed in runbook but not hard-gated with preflight checks. **Severity: MEDIUM**

### 2. Broken paths
- Plan assumes tracefs at `/sys/kernel/tracing` only; no documented fallback to `/sys/kernel/debug/tracing`. **Severity: HIGH**
- Example regression command uses placeholder path `/sys/devices/.../power/control`, not executable as-is. **Severity: MEDIUM**
- Repository path is hardcoded (`/local/mnt/workspace/AURA_V1_upstream/AURA/agents`). **Severity: LOW**

### 3. Missing tracepoints
- Required list omits lifecycle-adjacent instrumentation (e.g. function-level PM ordering in automated path), leaving ordering bugs under-observed unless manual function-graph mode is enabled. **Severity: MEDIUM**

### 4. Linux compatibility issues
- Assumes `tracefs` mount is available and writable for all environments.
- Assumes `dmesg` is readable (affected by `kernel.dmesg_restrict`). **Severity: HIGH**

### 5. Qualcomm-specific assumptions
- Stress example hardcodes ALSA device `hw:0,0`; many Qualcomm boards expose different card/device indices.
- VA-centric test matrix may not map directly across Qualcomm SKUs. **Severity: MEDIUM**

### 6. Risk of false-positive results
- Item #1 criterion allows PASS on "any" sensor with >=3% reduction, which can be unrelated to VA audio workload/noisy rails. **Severity: HIGH**

### 7. Risk of false-negative results
- Functional matrix starts with `TODO`; if not populated correctly, framework can report failure without indicating data-quality root cause. **Severity: MEDIUM**

---

## 2) `validation/collect_power.sh`

### 1. Missing dependencies
- Uses `awk`, GNU-like `date` (`%s%N`, `%s%3N`), `find`, `sort`; no dependency checks. **Severity: MEDIUM**

### 2. Broken paths
- Sensor discovery is best-effort and tolerates missing sysfs roots.
- No hard failure from missing specific path except "no sensors found" exit 2. **Severity: LOW**

### 3. Missing tracepoints
- Not tracepoint-based; N/A for event coverage.

### 4. Linux compatibility issues
- `date +%s%N`/`+%s%3N` portability is not universal (non-GNU userspace variants). **Severity: MEDIUM**

### 5. Qualcomm-specific assumptions
- None hardcoded, but collection is generic and not scoped to Qualcomm audio rails by default. **Severity: LOW**

### 6. Risk of false-positive results
- Collects all available power sensors (battery/charger/thermal rails may dominate), so non-audio sensor drift can satisfy item #1 threshold downstream in parser. **Severity: HIGH**

### 7. Risk of false-negative results
- If relevant VA rail is absent/unreadable but unrelated sensors exist, meaningful power regression may be masked. **Severity: MEDIUM**

---

## 3) `validation/collect_runtime_pm.sh`

### 1. Missing dependencies
- Requires `dmesg`, tracefs write permissions, `grep`, `find`, and root privileges.
- No explicit preflight for these requirements. **Severity: HIGH**

### 2. Broken paths
- Hardcoded `TRACEFS=/sys/kernel/tracing`; script later writes to `$TRACEFS/tracing_on` unconditionally.
- On systems exposing only `/sys/kernel/debug/tracing`, script will fail or collect nothing. **Severity: CRITICAL**

### 3. Missing tracepoints
- Enables only `pm_runtime_{suspend,resume,idle}` for mandatory PM events; does not verify that these events were actually enabled/recorded.
- Missing explicit checks for zero-event runs. **Severity: HIGH**

### 4. Linux compatibility issues
- `dmesg | wc -l` under `set -euo pipefail` can fail in restricted environments.
- Runtime PM sysfs field set varies by kernel/device; script is tolerant but coverage quality varies. **Severity: HIGH**

### 5. Qualcomm-specific assumptions
- Device filter regex (`lpass|va.*macro|qcom.*va|snd.*soc.*va`) may miss real Qualcomm paths with different naming. **Severity: MEDIUM**

### 6. Risk of false-positive results
- Kernel warning counts are global (entire system), not scoped to tested subsystem.
- If trace collection fails and summary file is still produced with low/empty evidence, downstream parser may still mark pass (see parser section). **Severity: HIGH**

### 7. Risk of false-negative results
- Unrelated kernel warnings during run can fail item #2 even when VA path is healthy.
- Regex scoping can miss target devices, hiding real runtime PM sequencing problems. **Severity: HIGH**

---

## 4) `validation/collect_clock_traces.sh`

### 1. Missing dependencies
- Requires tracefs, debugfs snapshots, `grep`, root privileges.
- No preflight checks. **Severity: HIGH**

### 2. Broken paths
- Hardcoded `TRACEFS=/sys/kernel/tracing`; unconditional writes/reads later.
- Same failure mode as runtime script on alternate tracing mount locations. **Severity: CRITICAL**

### 3. Missing tracepoints
- Captures `clk_enable/disable/set_rate/set_parent` but no verification that required clk events are present.
- Missing fallback strategy if `clk` event group unavailable. **Severity: HIGH**

### 4. Linux compatibility issues
- Clock debugfs files (`clk_summary`) and trace event names are kernel-config dependent.
- Behavior degrades silently when unavailable. **Severity: HIGH**

### 5. Qualcomm-specific assumptions
- Captures global clock events, not Qualcomm-VA-scoped clocks by default.
- SoundWire debugfs path assumed at `/sys/kernel/debug/soundwire`. **Severity: MEDIUM**

### 6. Risk of false-positive results
- Unrelated subsystem clock imbalance can appear as violation if parser interprets global trace as target-specific. **Severity: MEDIUM**

### 7. Risk of false-negative results
- If no clk events are captured, parser currently treats zero violations as PASS.
- This can mark item #4 PASS with missing evidence. **Severity: CRITICAL**

---

## 5) `validation/parse_results.py`

### 1. Missing dependencies
- Requires Python 3 stdlib only; dependency burden is low.
- No explicit check for malformed/missing input trees beyond permissive defaults. **Severity: LOW**

### 2. Broken paths
- Assumes fixed layout: `baseline/power`, `baseline/runtime_pm`, `baseline/clock` and candidate equivalents.
- Missing files are often treated as empty/zero rather than hard errors. **Severity: HIGH**

### 3. Missing tracepoints
- No data-quality gate requiring minimum trace evidence (e.g., non-zero PM/clock event counts).
- Therefore cannot distinguish "no issue" from "no data." **Severity: CRITICAL**

### 4. Linux compatibility issues
- Parser is platform-agnostic, but log-format assumptions exist:
  - clock parser expects `name=<clock>` token in trace lines.
  - format drift maps many entries to `UNKNOWN`. **Severity: HIGH**

### 5. Qualcomm-specific assumptions
- No hard Qualcomm logic; depends on upstream scripts and regression matrix content. **Severity: LOW**

### 6. Risk of false-positive results
- **Critical**: Item #2 can PASS when `runtime_pm_summary.txt` is missing because defaults become zeros.
- **Critical**: Item #4 can PASS when `clock_trace.txt` is missing/empty because violations remain zero.
- Item #1 can PASS based on any single sensor improvement regardless of relevance. **Severity: CRITICAL**

### 7. Risk of false-negative results
- Warning regexes may miss some fatal signatures not matching `WARNING|WARN|Oops|BUG|Call Trace`.
- Clock imbalance rule (`disable > enable + 1`) may miss real lifecycle errors with matched counts but wrong sequencing. **Severity: HIGH**

---

## 6) Cross-framework critical findings (most likely to break production use)

1. Tracefs path rigidity (`/sys/kernel/tracing` only) across collection scripts. **CRITICAL**
2. PASS-with-missing-evidence behavior in parser for item #2 and item #4. **CRITICAL**
3. Item #1 "any sensor" threshold vulnerable to unrelated rail noise. **HIGH**
4. Global dmesg and global clk signals can contaminate subsystem-specific conclusions. **HIGH**

---

## 7) Confidence estimate

Framework confidence (static audit): **58/100 (Moderate-Low)**

Rationale:
- Positive: artifact set is coherent, scripts are executable, and output schema is clear.
- Negative: two CRITICAL correctness risks (missing-evidence treated as PASS), plus portability risk around tracefs path and high contamination risk from global signals.
- Result: usable as a starting harness, but not yet reliable for upstream-go/no-go decisions without stronger evidence gating.
