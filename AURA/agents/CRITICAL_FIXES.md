# CRITICAL_FIXES

Scope: Implemented only CRITICAL-class remediations requested for the validation framework.

## Fixed CRITICAL Issue 1: Tracefs path rigidity

### Problem
Collection scripts assumed tracefs existed only at `/sys/kernel/tracing`.

### Implementation
- Added tracefs auto-detection in:
  - `validation/collect_runtime_pm.sh`
  - `validation/collect_clock_traces.sh`
- Detection order:
  1. `${TRACEFS}` if pre-set and valid
  2. `/sys/kernel/tracing`
  3. `/sys/kernel/debug/tracing`
- Scripts now hard-fail with explicit error if no valid tracefs path is found.

### Critical impact
Prevents silent/non-portable trace collection failures on kernels that expose tracing under debugfs path.

---

## Fixed CRITICAL Issue 2: Missing evidence incorrectly passing validation

### Problem
`validation/parse_results.py` could mark items PASS when required evidence files were absent/empty.

### Implementation
- Added strict evidence gates:
  - `ITEM1_POWER` => `INVALID_DATA` if power CSV missing or no comparable numeric sensors
  - `ITEM2_RUNTIME_PM` => `INVALID_DATA` if summary missing, required keys missing, or PM suspend/resume evidence is zero
  - `ITEM3_REGRESSION` => `INVALID_DATA` if matrix missing/empty or TODO/pending entries exist
  - `ITEM4_CLOCK` => `INVALID_DATA` if clock trace missing/empty or no enable/disable evidence
- Added `file_has_data()` and numeric parsing checks to prevent default-zero masking.

### Critical impact
Missing/insufficient evidence can no longer be misclassified as PASS.

---

## Fixed CRITICAL Issue 3: PASS/FAIL ambiguity when evidence quality is invalid

### Problem
Parser output was binary (`PASS`/`FAIL`) and could not distinguish bad evidence from real failure.

### Implementation
- Introduced tri-state statuses in parser:
  - `PASS`
  - `FAIL`
  - `INVALID_DATA`
- `validation_summary.csv` now emits tri-state per item.
- Overall result in generated `final_report.md` now resolves as:
  - `INVALID_DATA` if any item is `INVALID_DATA`
  - `PASS` if all items are `PASS`
  - otherwise `FAIL`

### Critical impact
Validation now explicitly fails closed on data quality issues.

---

## Fixed CRITICAL Issue 4: Missing explicit preflight dependency checks

### Problem
Scripts did not fail early when key runtime dependencies/permissions were missing.

### Implementation
- Added preflight command checks:
  - `validation/collect_power.sh`
  - `validation/collect_runtime_pm.sh`
  - `validation/collect_clock_traces.sh`
- Added runtime preflight checks for tracing controls writability in runtime/clock scripts.
- Added dmesg accessibility preflight in runtime PM collector.
- Added baseline/candidate directory preflight checks in parser.

### Critical impact
Prevents running invalid collection pipelines that would produce unusable or misleading outputs.

---

## Report template update

Updated:
- `validation/final_report_template.md`

Changes:
- Added tri-state status definitions (`PASS`, `FAIL`, `INVALID_DATA`).
- Added explicit evidence-quality gate checklist for runtime PM and clock evidence presence.
- Clarified that missing evidence is non-pass.

---

## Files modified
- `validation/collect_power.sh`
- `validation/collect_runtime_pm.sh`
- `validation/collect_clock_traces.sh`
- `validation/parse_results.py`
- `validation/final_report_template.md`
- `CRITICAL_FIXES.md`

## Verification executed
- `bash -n validation/collect_power.sh`
- `bash -n validation/collect_runtime_pm.sh`
- `bash -n validation/collect_clock_traces.sh`
- `python3 -m py_compile validation/parse_results.py`
- `validation/collect_power.sh --help`
- `validation/collect_runtime_pm.sh --help`
- `validation/collect_clock_traces.sh --help`
- `python3 validation/parse_results.py --help`
- Dry-run parser check with missing inputs confirms `INVALID_DATA` status and overall `INVALID_DATA`.
