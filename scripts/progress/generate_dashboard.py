#!/usr/bin/env python3
"""Generate visual progress dashboard."""

import json
from pathlib import Path


def load_progress() -> dict:
    """Load progress JSON."""
    return json.loads(Path("PRODUCTION_PROGRESS.json").read_text())


def progress_bar(percentage: int, width: int = 20) -> str:
    """Generate ASCII progress bar."""
    filled = int((percentage / 100) * width)
    empty = width - filled
    return f"[{'█' * filled}{'░' * empty}] {percentage}%"


def generate_dashboard() -> str:
    """Generate dashboard markdown."""
    data = load_progress()
    overall = data["overall_progress"]

    lines = [
        "# 🚀 AURA Production Roadmap Dashboard",
        "",
        f"**Last Updated:** {data['last_updated']}  ",
        f"**Status:** `{data['status']}`  ",
        f"**Current Phase:** {data['current_phase']}",
        "",
        "---",
        "",
        "## 📊 Overall Progress",
        "",
        f"**{overall['completed_tasks']}/{overall['total_tasks']} tasks completed**",
        "",
        progress_bar(overall["percentage"], 40),
        "",
        "---",
        "",
        "## 📋 Phase Progress",
        "",
    ]

    for phase in data["phases"]:
        progress = phase["progress"]
        status_icon = {
            "COMPLETED": "✅",
            "IN_PROGRESS": "🔄",
            "NOT_STARTED": "⏸️",
            "BLOCKED": "🚫",
        }.get(phase["status"], "❓")

        lines.extend([
            f"### {status_icon} {phase['name']}",
            "",
            f"- **Weeks:** {phase['weeks']}",
            f"- **Status:** `{phase['status']}`",
            f"- **Progress:** {progress['completed_tasks']}/{progress['total_tasks']} tasks",
            "",
            progress_bar(progress["percentage"], 30),
            "",
        ])

    lines.extend([
        "---",
        "",
        "## 🎯 Success Metrics",
        "",
        "### Reliability",
        f"- **Uptime Target:** {data['success_metrics']['reliability']['uptime_target']}",
        f"- **Data Loss Incidents:** {data['success_metrics']['reliability']['data_loss_incidents']}",
        f"- **Governance Bypass Incidents:** {data['success_metrics']['reliability']['governance_bypass_incidents']}",
        "",
        "### Performance",
        f"- **Concurrent Agents Target:** {data['success_metrics']['performance']['concurrent_agents_target']}",
        f"- **Tasks/Day Target:** {data['success_metrics']['performance']['tasks_per_day_target']}",
        f"- **API Latency Target (p95):** {data['success_metrics']['performance']['api_latency_p95_target_ms']}ms",
        "",
        "### Safety",
        f"- **Charter Compliance Target:** {data['success_metrics']['safety']['charter_compliance_target']}",
        f"- **PII Leak Incidents:** {data['success_metrics']['safety']['pii_leak_incidents']}",
        f"- **Prompt Injection Incidents:** {data['success_metrics']['safety']['prompt_injection_incidents']}",
        "",
        "### Developer Experience",
        f"- **Onboarding Time Target:** {data['success_metrics']['developer_experience']['onboarding_time_target_minutes']} min",
        f"- **First Task Time Target:** {data['success_metrics']['developer_experience']['first_task_time_target_minutes']} min",
        f"- **API Documentation Coverage Target:** {data['success_metrics']['developer_experience']['api_documentation_coverage_target']}",
        "",
        "---",
        "",
        "## 🔗 Quick Links",
        "",
        "- [Full Roadmap](PRODUCTION_ROADMAP.md)",
        "- [Progress JSON](PRODUCTION_PROGRESS.json)",
        "- [Gap Matrix](PRODUCTION_GAP_MATRIX.md) *(Phase 0)*",
        "- [Baseline Lock](BASELINE_LOCK_v2.md) *(Phase 0)*",
        "",
        "---",
        "",
        f"*Generated automatically from `PRODUCTION_PROGRESS.json` on {data['last_updated']}*",
    ])

    return "\n".join(lines)


def main():
    """Main entry point."""
    dashboard = generate_dashboard()
    output_file = Path("PRODUCTION_DASHBOARD.md")
    output_file.write_text(dashboard)
    print(f"Generated {output_file}")
    print("\nPreview:")
    print(dashboard)


if __name__ == "__main__":
    main()
