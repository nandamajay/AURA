#!/usr/bin/env python3
"""Start a phase."""

import json
import sys
from datetime import datetime
from pathlib import Path


def start_phase(phase_id: str) -> None:
    """Mark a phase as started."""
    progress_file = Path("PRODUCTION_PROGRESS.json")
    data = json.loads(progress_file.read_text())
    
    phase_found = False
    for phase in data["phases"]:
        if phase["id"] == phase_id:
            phase["status"] = "IN_PROGRESS"
            phase["start_date"] = datetime.utcnow().isoformat() + "Z"
            phase_found = True
            print(f"✅ Phase {phase_id} marked as IN_PROGRESS")
            print(f"   Name: {phase['name']}")
            print(f"   Weeks: {phase['weeks']}")
            print(f"   Tasks: {phase['progress']['total_tasks']}")
            break
    
    if not phase_found:
        print(f"❌ Error: Phase {phase_id} not found", file=sys.stderr)
        sys.exit(1)
    
    data["status"] = "IN_PROGRESS"
    data["current_phase"] = phase_id
    data["last_updated"] = datetime.utcnow().isoformat() + "Z"
    
    progress_file.write_text(json.dumps(data, indent=2) + "\n")
    print(f"\n✅ Updated PRODUCTION_PROGRESS.json")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: start_phase.py <phase_id>")
        print("Example: start_phase.py phase_0")
        sys.exit(1)
    
    phase_id = sys.argv[1]
    start_phase(phase_id)


if __name__ == "__main__":
    main()
