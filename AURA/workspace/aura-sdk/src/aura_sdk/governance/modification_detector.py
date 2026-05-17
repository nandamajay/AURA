"""SelfModificationDetector — detects unauthorized changes to critical systems.

Monitors for silent rewrites of governance rules, replay semantics,
architecture compliance, audit systems, validation logic, and security policies.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from aura_sdk.governance.charter import CharterViolation, SelfModificationRule
from aura_sdk.logging.logger import get_logger

logger = get_logger("governance.modification_detector")


class SelfModificationDetector:
    """Detects attempts to silently modify critical platform components.

    Maintains known-good hashes of critical files/rules.
    Alerts when modifications occur without explicit approval.
    """

    def __init__(self):
        self._known_hashes: dict[str, str] = {}  # path -> hash
        self._detections: list[dict[str, Any]] = []

    def register_file(self, path: str, content: str) -> None:
        """Register a file's known-good hash."""
        h = hashlib.sha256(content.encode()).hexdigest()
        self._known_hashes[path] = h
        logger.info("file_registered_for_integrity", path=path, hash=h[:16])

    def register_rule(self, rule_name: str, rule_content: dict[str, Any]) -> None:
        """Register a governance rule's known-good hash."""
        h = hashlib.sha256(
            json.dumps(rule_content, sort_keys=True).encode()
        ).hexdigest()
        self._known_hashes[rule_name] = h

    def check_integrity(self, path: str, current_content: str) -> tuple[bool, dict[str, Any]]:
        """Check if a file has been modified from its known-good state.

        Returns:
            (is_valid, details)
        """
        known_hash = self._known_hashes.get(path)
        if known_hash is None:
            return False, {"error": "File not registered", "path": path}

        current_hash = hashlib.sha256(current_content.encode()).hexdigest()
        is_valid = current_hash == known_hash

        result = {
            "path": path,
            "known_hash": known_hash[:16],
            "current_hash": current_hash[:16],
            "is_valid": is_valid,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

        if not is_valid:
            result["alert"] = f"INTEGRITY VIOLATION: {path} has been modified without authorization"
            self._detections.append(result)
            logger.critical(
                "integrity_violation_detected",
                path=path,
                expected=known_hash[:16],
                actual=current_hash[:16],
            )

        return is_valid, result

    def detect_modification_attempt(
        self,
        action: str,
        target: str,
        actor: str,
        context: dict[str, Any] | None = None,
    ) -> CharterViolation | None:
        """Detect if an action constitutes unauthorized self-modification.

        Checks against the 6 self-modification prohibitions.
        """
        ctx = context or {}
        action_lower = action.lower()
        target_lower = target.lower()

        # Define patterns for each prohibition
        prohibition_patterns = {
            SelfModificationRule.NO_SILENT_GOVERNANCE_REWRITE: {
                "keywords": ["governance", "rule", "policy", "permission", "role", "rbac"],
                "targets": ["governance", "rules", "policies", "permissions"],
            },
            SelfModificationRule.NO_SILENT_REPLAY_REWRITE: {
                "keywords": ["replay", "snapshot", "task_log", "output_hash", "seed"],
                "targets": ["replay", "task_logs", "snapshots", "seeds"],
            },
            SelfModificationRule.NO_SILENT_ARCHITECTURE_BYPASS: {
                "keywords": ["architecture", "constitution", "contract", "subsystem", "interface"],
                "targets": ["architecture", "constitution", "contracts", "subsystems"],
            },
            SelfModificationRule.NO_SILENT_AUDIT_BYPASS: {
                "keywords": ["audit", "ledger", "audit_log", "tamper", "chain_hash"],
                "targets": ["audit", "ledgers", "audit_logs"],
            },
            SelfModificationRule.NO_SILENT_VALIDATION_CHANGE: {
                "keywords": ["validation", "test", "check", "verify", "sanity"],
                "targets": ["validation", "tests", "checks"],
            },
            SelfModificationRule.NO_SILENT_SECURITY_CHANGE: {
                "keywords": ["security", "auth", "jwt", "password", "secret", "encrypt", "sandbox"],
                "targets": ["security", "auth", "secrets", "sandbox"],
            },
        }

        for rule, patterns in prohibition_patterns.items():
            action_matches = any(kw in action_lower for kw in patterns["keywords"])
            target_matches = any(kw in target_lower for kw in patterns["targets"])

            if action_matches and target_matches:
                # Check if explicitly approved
                if not ctx.get("explicitly_approved", False):
                    return CharterViolation(
                        principle="observable",
                        rule=rule.value,
                        action=action,
                        actor=actor,
                        details={
                            "target": target,
                            "keywords_matched": [k for k in patterns["keywords"] if k in action_lower],
                            "silent": True,
                            "explicitly_approved": False,
                        },
                        blocked=True,
                        severity="critical",
                    )

        return None

    def get_detections(self) -> list[dict[str, Any]]:
        return list(self._detections)

    @property
    def detection_count(self) -> int:
        return len(self._detections)

    def generate_integrity_report(self) -> dict[str, Any]:
        """Generate a report of all registered items and their integrity status."""
        return {
            "registered_items": len(self._known_hashes),
            "detections": len(self._detections),
            "all_registered": list(self._known_hashes.keys()),
            "violations": self._detections,
            "recommendation": (
                f"{len(self._detections)} integrity violation(s) detected. "
                "Review all modifications. Ensure explicit approval was recorded."
                if self._detections else
                "All registered items have valid integrity. Continue monitoring."
            ),
        }
