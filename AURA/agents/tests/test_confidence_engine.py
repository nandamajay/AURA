"""Tests for reusable confidence computation primitives."""

from __future__ import annotations

import pytest

from aura_agents.confidence_engine import ConfidenceComputationError, compute_weighted_confidence


def test_compute_weighted_confidence_is_deterministic():
    first = compute_weighted_confidence(
        stage_id="indexed",
        signal_scores={
            "static_input_integrity": 0.5,
            "file_family_index_integrity": 1.0,
        },
        signal_weights={
            "file_family_index_integrity": 1.0,
            "static_input_integrity": 2.0,
        },
        required_signals=(
            "file_family_index_integrity",
            "static_input_integrity",
        ),
    )
    second = compute_weighted_confidence(
        stage_id="INDEXED",
        signal_scores={
            "file_family_index_integrity": 1.0,
            "static_input_integrity": 0.5,
        },
        signal_weights={
            "static_input_integrity": 2.0,
            "file_family_index_integrity": 1.0,
        },
        required_signals=(
            "file_family_index_integrity",
            "static_input_integrity",
        ),
    )

    assert first == second
    assert first["stage_id"] == "INDEXED"
    assert first["score"] == 0.6667
    assert first["required_signals"] == [
        "file_family_index_integrity",
        "static_input_integrity",
    ]


def test_compute_weighted_confidence_rejects_invalid_score():
    with pytest.raises(ConfidenceComputationError, match="within \\[0.0, 1.0\\]"):
        compute_weighted_confidence(
            stage_id="DISCOVERED",
            signal_scores={"source_locator_integrity": 2.0},
        )


def test_compute_weighted_confidence_rejects_unknown_weight():
    with pytest.raises(ConfidenceComputationError, match="unknown signal ids"):
        compute_weighted_confidence(
            stage_id="STATIC_ANALYZED",
            signal_scores={"symbol_inventory_integrity": 1.0},
            signal_weights={"unexpected": 1.0},
            required_signals=("symbol_inventory_integrity",),
        )
