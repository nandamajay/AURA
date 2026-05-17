"""Maintainer intelligence interface (P2 baseline).

P2 scope:
- profile retrieval from SQLite-backed maintainer_profiles
- simple heuristic acceptance prediction
- interface stub for LKML thread analysis
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from aura_sdk.db.connection import get_db
from aura_sdk.models.knowledge import MaintainerProfile
from aura_sdk.models.patch import Patch


@dataclass(slots=True)
class NAKReason:
    reason: str
    count: int = 1


class MaintainerIntelligenceEngine:
    """Tier-2 maintainer intelligence engine (P2 interface + basic heuristics)."""

    async def get_profile(self, email: str) -> MaintainerProfile:
        """Load one maintainer profile by email.

        Returns an empty profile shell when not found.
        """
        email_normalized = email.strip().lower()
        if not email_normalized:
            return MaintainerProfile()

        async with get_db() as db:
            cursor = await db.execute(
                """
                SELECT id, name, email, subsystem_id, acceptance_rate, review_count,
                       common_nak_reasons, preferred_patterns, personality_summary,
                       last_analyzed_at
                FROM maintainer_profiles
                WHERE lower(email) = ?
                LIMIT 1
                """,
                (email_normalized,),
            )
            row = await cursor.fetchone()
            if row is None:
                return MaintainerProfile(email=email_normalized)

        return MaintainerProfile(
            id=str(row["id"]),
            name=str(row["name"] or ""),
            email=str(row["email"] or email_normalized),
            subsystem_id=str(row["subsystem_id"] or ""),
            acceptance_rate=float(row["acceptance_rate"]) if row["acceptance_rate"] is not None else None,
            review_count=int(row["review_count"] or 0),
            common_nak_reasons=self._parse_json_list(row["common_nak_reasons"]),
            preferred_patterns=self._parse_json_list(row["preferred_patterns"]),
            personality_summary=str(row["personality_summary"] or ""),
            last_analyzed_at=row["last_analyzed_at"],
        )

    async def predict_acceptance(self, patch: Patch, maintainer_email: str) -> float:
        """Predict acceptance probability (0..1) using P2 heuristic baseline."""
        profile = await self.get_profile(maintainer_email)
        score = profile.acceptance_rate if profile.acceptance_rate is not None else 0.5

        review_count = int(profile.review_count or 0)
        if review_count >= 25:
            score += 0.08
        elif review_count >= 10:
            score += 0.04

        score += (float(patch.confidence_score or 0.0) - 0.5) * 0.25
        score -= min(len(profile.common_nak_reasons), 4) * 0.02

        return max(0.0, min(1.0, round(score, 4)))

    async def analyze_lkml_thread(self, thread_url: str) -> list[NAKReason]:
        """Extract NAK reasons from LKML thread.

        P2 status: interface-only placeholder. Full mining is P3+.
        """
        normalized = thread_url.strip()
        if not normalized:
            return []
        return [
            NAKReason(
                reason="P2 interface active: LKML mining deferred to P3+",
                count=1,
            )
        ]

    @staticmethod
    def _parse_json_list(raw: Any) -> list[str]:
        if raw is None:
            return []
        if isinstance(raw, list):
            return [str(item) for item in raw if str(item).strip()]
        if not isinstance(raw, str):
            return [str(raw)]

        text = raw.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if str(item).strip()]
        except Exception:
            pass
        return [part.strip() for part in text.split(",") if part.strip()]
