#!/usr/bin/env python3
import argparse
import csv
import math
import os
import re
import statistics
from collections import defaultdict
from pathlib import Path

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_INVALID = "INVALID_DATA"


def read_power_csv(path: Path):
    data = defaultdict(list)
    if not path.exists():
        return data
    with path.open() as f:
        r = csv.DictReader(f)
        for row in r:
            sensor = row.get("sensor_path", "")
            v = row.get("value_raw", "")
            try:
                fv = float(v)
            except ValueError:
                continue
            data[sensor].append(fv)
    return data


def stats(vals):
    if not vals:
        return None
    vals_sorted = sorted(vals)
    n = len(vals_sorted)
    p95_idx = max(0, min(n - 1, int(math.ceil(0.95 * n)) - 1))
    return {
        "n": n,
        "mean": statistics.fmean(vals_sorted),
        "stddev": statistics.pstdev(vals_sorted) if n > 1 else 0.0,
        "p95": vals_sorted[p95_idx],
    }


def parse_kv_file(path: Path):
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(errors="ignore").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def parse_clock_trace(trace_path: Path):
    enable_counts = defaultdict(int)
    disable_counts = defaultdict(int)
    if not trace_path.exists():
        return enable_counts, disable_counts

    name_re = re.compile(r"name=([^\s,]+)")
    for line in trace_path.read_text(errors="ignore").splitlines():
        if "clk_enable" in line:
            m = name_re.search(line)
            name = m.group(1) if m else "UNKNOWN"
            enable_counts[name] += 1
        elif "clk_disable" in line:
            m = name_re.search(line)
            name = m.group(1) if m else "UNKNOWN"
            disable_counts[name] += 1
    return enable_counts, disable_counts


def parse_regression_csv(path: Path):
    required = []
    if not path.exists():
        return required
    with path.open() as f:
        r = csv.DictReader(f)
        for row in r:
            required.append(row)
    return required


def safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def parse_num(x):
    try:
        return float(x)
    except Exception:
        return None


def file_has_data(path: Path):
    return path.exists() and path.is_file() and path.stat().st_size > 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--regression-csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--power-reduction-threshold-pct", type=float, default=3.0)
    args = ap.parse_args()

    b = Path(args.baseline)
    c = Path(args.candidate)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if not b.exists() or not b.is_dir():
        raise SystemExit(f"Missing baseline directory: {b}")
    if not c.exists() or not c.is_dir():
        raise SystemExit(f"Missing candidate directory: {c}")

    # ITEM1 power
    b_power_csv = b / "power" / "power_samples.csv"
    c_power_csv = c / "power" / "power_samples.csv"
    b_power = read_power_csv(b_power_csv)
    c_power = read_power_csv(c_power_csv)

    power_rows = []
    candidate_pass_any = False
    item1_status = STATUS_FAIL
    item1_notes = ""

    sensors = sorted(set(b_power.keys()) | set(c_power.keys()))
    for s in sensors:
        bs = stats(b_power.get(s, []))
        cs = stats(c_power.get(s, []))
        if not bs or not cs:
            continue
        delta = ((cs["mean"] - bs["mean"]) / bs["mean"]) * 100.0 if bs["mean"] else 0.0
        pass_this = delta <= -args.power_reduction_threshold_pct
        if pass_this:
            candidate_pass_any = True
        power_rows.append({
            "sensor": s,
            "baseline_mean": f"{bs['mean']:.6f}",
            "candidate_mean": f"{cs['mean']:.6f}",
            "delta_pct": f"{delta:.4f}",
            "baseline_p95": f"{bs['p95']:.6f}",
            "candidate_p95": f"{cs['p95']:.6f}",
        })

    if not file_has_data(b_power_csv) or not file_has_data(c_power_csv):
        item1_status = STATUS_INVALID
        item1_notes = "missing power_samples.csv in baseline or candidate"
    elif len(power_rows) == 0:
        item1_status = STATUS_INVALID
        item1_notes = "no comparable numeric sensor samples"
    else:
        item1_status = STATUS_PASS if candidate_pass_any else STATUS_FAIL
        item1_notes = f"sensor_rows={len(power_rows)}"

    with (out / "power_stats.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["sensor", "baseline_mean", "candidate_mean", "delta_pct", "baseline_p95", "candidate_p95"])
        w.writeheader()
        for r in power_rows:
            w.writerow(r)

    # ITEM2 runtime PM stability
    b_rt_summary = b / "runtime_pm" / "runtime_pm_summary.txt"
    c_rt_summary = c / "runtime_pm" / "runtime_pm_summary.txt"
    b_rt = parse_kv_file(b_rt_summary)
    c_rt = parse_kv_file(c_rt_summary)

    b_warn = parse_num(b_rt.get("WARN_COUNT"))
    b_oops = parse_num(b_rt.get("OOPS_COUNT"))
    b_bug = parse_num(b_rt.get("BUG_COUNT"))
    b_ct = parse_num(b_rt.get("CALL_TRACE_COUNT"))
    b_suspend_events = parse_num(b_rt.get("PM_RUNTIME_SUSPEND_EVENTS"))
    b_resume_events = parse_num(b_rt.get("PM_RUNTIME_RESUME_EVENTS"))

    c_warn = parse_num(c_rt.get("WARN_COUNT"))
    c_oops = parse_num(c_rt.get("OOPS_COUNT"))
    c_bug = parse_num(c_rt.get("BUG_COUNT"))
    c_ct = parse_num(c_rt.get("CALL_TRACE_COUNT"))
    c_suspend_events = parse_num(c_rt.get("PM_RUNTIME_SUSPEND_EVENTS"))
    c_resume_events = parse_num(c_rt.get("PM_RUNTIME_RESUME_EVENTS"))

    item2_status = STATUS_FAIL
    item2_notes = "candidate kernel error counts"

    required_rt_values = [
        b_warn, b_oops, b_bug, b_ct, b_suspend_events, b_resume_events,
        c_warn, c_oops, c_bug, c_ct, c_suspend_events, c_resume_events,
    ]
    if not file_has_data(b_rt_summary) or not file_has_data(c_rt_summary):
        item2_status = STATUS_INVALID
        item2_notes = "missing runtime_pm_summary.txt in baseline or candidate"
    elif any(v is None for v in required_rt_values):
        item2_status = STATUS_INVALID
        item2_notes = "runtime_pm_summary.txt missing required numeric keys"
    elif (b_suspend_events + b_resume_events) <= 0 or (c_suspend_events + c_resume_events) <= 0:
        item2_status = STATUS_INVALID
        item2_notes = "no runtime PM trace evidence (suspend/resume events == 0)"
    else:
        item2_status = STATUS_PASS if (c_warn == 0 and c_oops == 0 and c_bug == 0 and c_ct == 0) else STATUS_FAIL

    # ITEM3 regression matrix
    reg_path = Path(args.regression_csv)
    reg = parse_regression_csv(reg_path)
    required_rows = [r for r in reg if r.get("test_id")]
    item3_status = STATUS_PASS
    pending = 0
    if not file_has_data(reg_path):
        item3_status = STATUS_INVALID
    elif len(required_rows) == 0:
        item3_status = STATUS_INVALID
    else:
        for r in required_rows:
            br = (r.get("baseline_result") or "").strip().upper()
            cr = (r.get("candidate_result") or "").strip().upper()
            if br == "TODO" or cr == "TODO" or not br or not cr:
                pending += 1
                item3_status = STATUS_INVALID
                continue
            if br != "PASS" or cr != "PASS":
                if item3_status != STATUS_INVALID:
                    item3_status = STATUS_FAIL

    # ITEM4 clock correctness
    b_clock_trace = b / "clock" / "clock_trace.txt"
    c_clock_trace = c / "clock" / "clock_trace.txt"
    b_clk_en, b_clk_dis = parse_clock_trace(b_clock_trace)
    c_clk_en, c_clk_dis = parse_clock_trace(c_clock_trace)

    all_clks = sorted(set(c_clk_en.keys()) | set(c_clk_dis.keys()))
    violations = 0
    item4_status = STATUS_FAIL
    item4_notes = "disable_count <= enable_count + 1 per clock"
    c_total_events = sum(c_clk_en.values()) + sum(c_clk_dis.values())
    b_total_events = sum(b_clk_en.values()) + sum(b_clk_dis.values())

    with (out / "clock_balance.csv").open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["clock_name", "enable_count", "disable_count", "net_enable_minus_disable", "violation"],
        )
        w.writeheader()
        for name in all_clks:
            en = c_clk_en.get(name, 0)
            dis = c_clk_dis.get(name, 0)
            net = en - dis
            violation = dis > (en + 1)
            if violation:
                violations += 1
            w.writerow({
                "clock_name": name,
                "enable_count": en,
                "disable_count": dis,
                "net_enable_minus_disable": net,
                "violation": "YES" if violation else "NO",
            })

    if not file_has_data(b_clock_trace) or not file_has_data(c_clock_trace):
        item4_status = STATUS_INVALID
        item4_notes = "missing clock_trace.txt in baseline or candidate"
    elif b_total_events <= 0 or c_total_events <= 0:
        item4_status = STATUS_INVALID
        item4_notes = "no clock trace evidence (enable/disable events == 0)"
    else:
        item4_status = STATUS_PASS if violations == 0 else STATUS_FAIL

    # Overall summaries
    b_warn_out = "N/A" if b_warn is None else str(int(b_warn))
    b_oops_out = "N/A" if b_oops is None else str(int(b_oops))
    b_bug_out = "N/A" if b_bug is None else str(int(b_bug))
    b_ct_out = "N/A" if b_ct is None else str(int(b_ct))
    c_warn_out = "N/A" if c_warn is None else str(int(c_warn))
    c_oops_out = "N/A" if c_oops is None else str(int(c_oops))
    c_bug_out = "N/A" if c_bug is None else str(int(c_bug))
    c_ct_out = "N/A" if c_ct is None else str(int(c_ct))

    summary_rows = [
        {
            "item_id": "ITEM1_POWER",
            "metric": "power_reduction_any_sensor_pct",
            "baseline_value": "N/A",
            "candidate_value": "N/A",
            "delta_pct": "N/A",
            "threshold": f"<= -{args.power_reduction_threshold_pct}%",
            "pass_fail": item1_status,
            "notes": item1_notes,
        },
        {
            "item_id": "ITEM2_RUNTIME_PM",
            "metric": "WARN/OOPS/BUG/CALL_TRACE",
            "baseline_value": f"{b_warn_out}/{b_oops_out}/{b_bug_out}/{b_ct_out}",
            "candidate_value": f"{c_warn_out}/{c_oops_out}/{c_bug_out}/{c_ct_out}",
            "delta_pct": "N/A",
            "threshold": "all zero",
            "pass_fail": item2_status,
            "notes": item2_notes,
        },
        {
            "item_id": "ITEM3_REGRESSION",
            "metric": "functional_matrix",
            "baseline_value": "from regression_matrix.csv",
            "candidate_value": "from regression_matrix.csv",
            "delta_pct": "N/A",
            "threshold": "all required tests PASS",
            "pass_fail": item3_status,
            "notes": f"pending_rows={pending}",
        },
        {
            "item_id": "ITEM4_CLOCK",
            "metric": "clock_disable_over_enable_violation_count",
            "baseline_value": "N/A",
            "candidate_value": str(violations),
            "delta_pct": "N/A",
            "threshold": "0 violations",
            "pass_fail": item4_status,
            "notes": item4_notes,
        },
    ]

    with (out / "validation_summary.csv").open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["item_id", "metric", "baseline_value", "candidate_value", "delta_pct", "threshold", "pass_fail", "notes"],
        )
        w.writeheader()
        for r in summary_rows:
            w.writerow(r)

    statuses = [r["pass_fail"] for r in summary_rows]
    if any(s == STATUS_INVALID for s in statuses):
        overall_status = STATUS_INVALID
    elif all(s == STATUS_PASS for s in statuses):
        overall_status = STATUS_PASS
    else:
        overall_status = STATUS_FAIL

    final_report = out / "final_report.md"
    with final_report.open("w") as f:
        f.write("# Validation Final Report\n\n")
        f.write(f"Overall: {overall_status}\n\n")
        f.write("## Item Summary\n")
        for r in summary_rows:
            f.write(f"- {r['item_id']}: {r['pass_fail']} ({r['metric']}, threshold={r['threshold']})\n")
        f.write("\n## Output Files\n")
        f.write("- validation_summary.csv\n")
        f.write("- power_stats.csv\n")
        f.write("- clock_balance.csv\n")

    print(f"Wrote: {out / 'validation_summary.csv'}")
    print(f"Wrote: {out / 'power_stats.csv'}")
    print(f"Wrote: {out / 'clock_balance.csv'}")
    print(f"Wrote: {final_report}")


if __name__ == "__main__":
    main()
