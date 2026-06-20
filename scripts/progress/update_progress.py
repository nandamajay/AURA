#!/usr/bin/env python3
"""Update production progress tracking."""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def load_progress() -> dict:
    """Load progress JSON."""
    progress_file = Path("PRODUCTION_PROGRESS.json")
    if not progress_file.exists():
        print(f"Error: {progress_file} not found", file=sys.stderr)
        sys.exit(1)
    return json.loads(progress_file.read_text())


def save_progress(data: dict) -> None:
    """Save progress JSON."""
    progress_file = Path("PRODUCTION_PROGRESS.json")
    data["last_updated"] = datetime.utcnow().isoformat() + "Z"
    progress_file.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Updated {progress_file}")


def update_task_status(
    data: dict, task_id: str, status: str, evidence: Optional[list] = None
) -> None:
    """Update task status."""
    for phase in data["phases"]:
        if "weeks_detail" not in phase:
            continue
        for week in phase["weeks_detail"]:
            for task in week["tasks"]:
                if task["id"] == task_id:
                    task["status"] = status
                    if status == "COMPLETED":
                        task["completed_date"] = datetime.utcnow().isoformat() + "Z"
                    if evidence:
                        task["evidence"].extend(evidence)
                    print(f"Updated task {task_id}: {status}")
                    return
    print(f"Warning: Task {task_id} not found", file=sys.stderr)


def update_deliverable_status(data: dict, deliverable_path: str, status: str) -> None:
    """Update deliverable status."""
    for phase in data["phases"]:
        if "weeks_detail" not in phase:
            continue
        for week in phase["weeks_detail"]:
            for deliverable in week["deliverables"]:
                if deliverable["path"] == deliverable_path:
                    deliverable["status"] = status
                    print(f"Updated deliverable {deliverable_path}: {status}")
                    return
    print(f"Warning: Deliverable {deliverable_path} not found", file=sys.stderr)


def recalculate_progress(data: dict) -> None:
    """Recalculate all progress percentages."""
    total_completed = 0
    total_tasks = 0

    for phase in data["phases"]:
        phase_completed = 0
        phase_total = 0

        if "weeks_detail" in phase:
            for week in phase["weeks_detail"]:
                for task in week["tasks"]:
                    phase_total += 1
                    if task["status"] == "COMPLETED":
                        phase_completed += 1

        phase["progress"]["total_tasks"] = phase_total
        phase["progress"]["completed_tasks"] = phase_completed
        phase["progress"]["percentage"] = (
            int((phase_completed / phase_total) * 100) if phase_total > 0 else 0
        )

        total_tasks += phase_total
        total_completed += phase_completed

    data["overall_progress"]["total_tasks"] = total_tasks
    data["overall_progress"]["completed_tasks"] = total_completed
    data["overall_progress"]["percentage"] = (
        int((total_completed / total_tasks) * 100) if total_tasks > 0 else 0
    )


def generate_progress_report() -> None:
    """Generate human-readable progress report."""
    data = load_progress()
    recalculate_progress(data)

    print("\n" + "=" * 80)
    print("AURA PRODUCTION ROADMAP - PROGRESS REPORT")
    print("=" * 80)
    print(f"Last Updated: {data['last_updated']}")
    print(f"Status: {data['status']}")
    print(f"Current Phase: {data['current_phase']}")
    print()

    overall = data["overall_progress"]
    print(f"Overall Progress: {overall['completed_tasks']}/{overall['total_tasks']} tasks ({overall['percentage']}%)")
    print()

    for phase in data["phases"]:
        progress = phase["progress"]
        status_icon = {
            "COMPLETED": "✅",
            "IN_PROGRESS": "🔄",
            "NOT_STARTED": "⏸️",
            "BLOCKED": "🚫",
        }.get(phase["status"], "❓")

        print(f"{status_icon} Phase {phase['id']}: {phase['name']}")
        print(f"   Weeks: {phase['weeks']}")
        print(f"   Progress: {progress['completed_tasks']}/{progress['total_tasks']} ({progress['percentage']}%)")
        print(f"   Status: {phase['status']}")
        print()


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  update_progress.py report")
        print("  update_progress.py task <task_id> <status> [evidence_file...]")
        print("  update_progress.py deliverable <path> <status>")
        sys.exit(1)

    command = sys.argv[1]

    if command == "report":
        generate_progress_report()
    elif command == "task":
        if len(sys.argv) < 4:
            print("Usage: update_progress.py task <task_id> <status> [evidence_file...]")
            sys.exit(1)
        task_id = sys.argv[2]
        status = sys.argv[3]
        evidence = sys.argv[4:] if len(sys.argv) > 4 else None
        data = load_progress()
        update_task_status(data, task_id, status, evidence)
        recalculate_progress(data)
        save_progress(data)
    elif command == "deliverable":
        if len(sys.argv) < 4:
            print("Usage: update_progress.py deliverable <path> <status>")
            sys.exit(1)
        deliverable_path = sys.argv[2]
        status = sys.argv[3]
        data = load_progress()
        update_deliverable_status(data, deliverable_path, status)
        save_progress(data)
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
