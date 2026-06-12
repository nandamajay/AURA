"""Reusable deterministic confidence computation primitives."""

from __future__ import annotations

import math
from typing import Any


class ConfidenceComputationError(RuntimeError):
    """Fail-closed confidence computation error."""


def _as_non_empty_text(value: Any, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ConfidenceComputationError(f"{field} must be non-empty")
    return text


def _as_unit_interval(value: Any, *, field: str) -> float:
    if not isinstance(value, (int, float)):
        raise ConfidenceComputationError(f"{field} must be numeric")
    score = float(value)
    if not math.isfinite(score):
        raise ConfidenceComputationError(f"{field} must be finite")
    if score < 0.0 or score > 1.0:
        raise ConfidenceComputationError(f"{field} must be within [0.0, 1.0]")
    return score


def _as_positive_weight(value: Any, *, field: str) -> float:
    if not isinstance(value, (int, float)):
        raise ConfidenceComputationError(f"{field} must be numeric")
    weight = float(value)
    if not math.isfinite(weight):
        raise ConfidenceComputationError(f"{field} must be finite")
    if weight <= 0.0:
        raise ConfidenceComputationError(f"{field} must be > 0")
    return weight


def _normalize_required_signals(required_signals: list[str] | tuple[str, ...] | None) -> list[str]:
    if required_signals is None:
        return []
    if not isinstance(required_signals, (list, tuple)):
        raise ConfidenceComputationError("required_signals must be a list/tuple when provided")
    normalized: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(required_signals):
        signal_id = _as_non_empty_text(item, field=f"required_signals[{index}]")
        if signal_id in seen:
            raise ConfidenceComputationError(f"required_signals contains duplicate signal_id={signal_id!r}")
        seen.add(signal_id)
        normalized.append(signal_id)
    return normalized


def compute_weighted_confidence(
    *,
    stage_id: str,
    signal_scores: dict[str, Any],
    signal_weights: dict[str, Any] | None = None,
    required_signals: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Compute deterministic weighted confidence for a stage.

    The caller owns signal semantics. This utility only validates and computes.
    """

    normalized_stage_id = _as_non_empty_text(stage_id, field="stage_id").upper()
    if not isinstance(signal_scores, dict) or not signal_scores:
        raise ConfidenceComputationError("signal_scores must be a non-empty object")

    normalized_scores: dict[str, float] = {}
    for signal_id, raw_score in signal_scores.items():
        signal_name = _as_non_empty_text(signal_id, field="signal_scores key")
        if signal_name in normalized_scores:
            raise ConfidenceComputationError(f"duplicate signal id in signal_scores: {signal_name!r}")
        normalized_scores[signal_name] = _as_unit_interval(
            raw_score,
            field=f"signal_scores[{signal_name}]",
        )

    required = _normalize_required_signals(required_signals)
    if not required:
        required = sorted(normalized_scores.keys())
    if not required:
        raise ConfidenceComputationError("required_signals resolved to empty set")

    missing_required = [name for name in required if name not in normalized_scores]
    if missing_required:
        raise ConfidenceComputationError(
            "required_signals missing in signal_scores: " + ", ".join(sorted(missing_required))
        )

    weights_input = signal_weights or {}
    if not isinstance(weights_input, dict):
        raise ConfidenceComputationError("signal_weights must be an object when provided")

    unknown_weights = sorted(
        [
            _as_non_empty_text(name, field="signal_weights key")
            for name in weights_input.keys()
            if _as_non_empty_text(name, field="signal_weights key") not in required
        ]
    )
    if unknown_weights:
        raise ConfidenceComputationError(
            "signal_weights contains unknown signal ids: " + ", ".join(unknown_weights)
        )

    normalized_weights: dict[str, float] = {}
    for signal_name in required:
        if signal_name in weights_input:
            normalized_weights[signal_name] = _as_positive_weight(
                weights_input[signal_name],
                field=f"signal_weights[{signal_name}]",
            )
        else:
            normalized_weights[signal_name] = 1.0

    total_weight = sum(normalized_weights[name] for name in required)
    if total_weight <= 0.0:
        raise ConfidenceComputationError("total_weight must be > 0")

    weighted_sum = 0.0
    signal_details: list[dict[str, Any]] = []
    for signal_name in required:
        score = normalized_scores[signal_name]
        weight = normalized_weights[signal_name]
        weighted_sum += score * weight
        signal_details.append(
            {
                "signal_id": signal_name,
                "score": round(score, 6),
                "weight": round(weight, 6),
                "weighted_score": round(score * weight, 6),
            }
        )

    stage_score = round(weighted_sum / total_weight, 4)
    return {
        "stage_id": normalized_stage_id,
        "score": stage_score,
        "required_signals": list(required),
        "signals": signal_details,
        "total_weight": round(total_weight, 6),
    }
