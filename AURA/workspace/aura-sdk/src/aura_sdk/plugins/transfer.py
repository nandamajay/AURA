"""Cross-subsystem pattern transfer (Tier-3 learning bridge).

P2 scope:
- deterministic, rule-based transfer only
- no ML arbitration
- intended for future multi-subsystem activation
"""

from __future__ import annotations

import json
from typing import Any

from aura_sdk.db.connection import get_db


class CrossSubsystemTransfer:
    """Transfer common validated patterns to a newly-enabled subsystem."""

    COMMON_PATTERNS: list[dict[str, Any]] = [
        {
            "category": "pattern",
            "downstream_pattern": "pm_runtime_get_sync",
            "upstream_equivalent": "pm_runtime_resume_and_get",
            "description": "Prefer upstream-managed runtime PM helper.",
            "confidence_boost": 0.10,
        },
        {
            "category": "api_mapping",
            "downstream_pattern": "regmap_write",
            "upstream_equivalent": "regmap_write",
            "description": "Regmap access pattern shared across codec/DSP drivers.",
            "applies_to": ["audio", "dsp"],
        },
        {
            "category": "pattern",
            "downstream_pattern": "devm_kzalloc",
            "upstream_equivalent": "devm_kzalloc",
            "description": "Managed resource allocation pattern check.",
            "confidence_boost": 0.05,
        },
    ]

    async def transfer_to(self, new_subsystem_id: str) -> int:
        """Transfer applicable common patterns. Returns number inserted."""
        subsystem = new_subsystem_id.strip().lower()
        if not subsystem:
            return 0

        async with get_db() as db:
            cursor = await db.execute(
                "SELECT id, name FROM subsystems WHERE lower(name) = ? OR id = ? LIMIT 1",
                (subsystem, subsystem),
            )
            row = await cursor.fetchone()
            if row is None:
                return 0
            subsystem_pk = str(row["id"])
            subsystem_name = str(row["name"]).lower()

            inserted = 0
            for pattern in self.COMMON_PATTERNS:
                if not self._applies_to(pattern, subsystem_name):
                    continue
                created = await self._insert_rule(db, subsystem_pk, subsystem_name, pattern)
                if created:
                    inserted += 1

            await db.commit()
            return inserted

    @staticmethod
    def _applies_to(pattern: dict[str, Any], subsystem_name: str) -> bool:
        targets = pattern.get("applies_to")
        if not targets:
            return True
        if not isinstance(targets, list):
            return False
        lowered = subsystem_name.lower()
        return any(str(target).lower() in lowered for target in targets)

    @staticmethod
    async def _insert_rule(
        db,
        subsystem_pk: str,
        subsystem_name: str,
        pattern: dict[str, Any],
    ) -> bool:
        downstream_pattern = str(pattern.get("downstream_pattern") or "").strip()
        if not downstream_pattern:
            return False

        exists_cursor = await db.execute(
            """
            SELECT id FROM migration_rules
            WHERE subsystem_id = ? AND downstream_pattern = ?
            LIMIT 1
            """,
            (subsystem_pk, downstream_pattern),
        )
        exists = await exists_cursor.fetchone()
        if exists is not None:
            return False

        base_confidence = 0.5
        confidence = min(
            0.99,
            base_confidence + float(pattern.get("confidence_boost", 0.0) or 0.0),
        )
        source_refs = json.dumps(
            [
                {
                    "source": "cross_subsystem_transfer",
                    "subsystem": subsystem_name,
                    "pattern": downstream_pattern,
                }
            ],
            separators=(",", ":"),
        )
        await db.execute(
            """
            INSERT INTO migration_rules
                (subsystem_id, category, downstream_pattern, upstream_equivalent, description, confidence, source_refs)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                subsystem_pk,
                str(pattern.get("category") or "pattern"),
                downstream_pattern,
                str(pattern.get("upstream_equivalent") or ""),
                str(pattern.get("description") or ""),
                confidence,
                source_refs,
            ),
        )
        return True
