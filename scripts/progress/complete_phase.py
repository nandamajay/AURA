#!/usr/bin/env python3
"""Complete a phase."""

import json
import sys
from datetime import datetime
from pathlib import Path


def complete_phase(phase_id: str) -> None:
    """Mark a phase as completed."""
    progress_file = Path("PRODUCTION_PROGRESS.json")
    data = json.loads(progress_file.read_text())
    
    phase_found = False
    phase_index = -1
    for i, phase in enumerate(data["phases"]):
        if phase["id"] == phase_id:
            phase["status"] = "COMPLETED"
            phase["end_date"] = datetime.utcnow().isoformat() + "Z"
            phase_found = True
            phase_index = i
            print(f"✅ Phase {phase_id} marked as COMPLETED")
            print(f"   Name: {phase['name']}")
            print(f"   Completed: {phase['progress']['completed_tasks']}/{phase['progress']['total_tasks']} tasks")
            break
    
    if not phase_found:
        print(f"❌ Error: Phase {phase_id} not found", file=sys.stderr)
        sys.exit(1)
    
    # Move to next phase
    if phase_index + 1 < len(data["phases"]):
        next_phase = data["phases"][phase_index + 1]
        data["current_phase"] = next_phase["id"]
        print(f"\n➡️  Moving to next phase: {next_phase['id']}")
        print(f"   Name: {next_phase['name']}")
        print(f"   Weeks: {next_phase['weeks']}")
    else:
        print(f"\n🎉 All phases completed!")
        data["status"] = "COMPLETED"
    
    data["last_updated"] = datetime.utcnow().isoformat() + "Z"
    
    progress_file.write_text(json.dumps(data, indent=2) + "\n")
    print(f"\n✅ Updated PRODUCTION_PROGRESS.json")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: complete_phase.py <phase_id>")
        print("Example: complete_phase.py phase_0")
        sys.exit(1)
    
    phase_id = sys.argv[1]
    complete_phase(phase_id)


if __name__ == "__main__":
    main()
