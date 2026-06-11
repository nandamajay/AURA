"""Reusable deterministic stage execution primitives."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


class StageExecutionError(RuntimeError):
    """Fail-closed stage execution error."""


@dataclass(frozen=True)
class StageDefinition:
    """Single stage definition used by deterministic stage engine."""

    stage_id: str
    artifact_name: str
    artifact_filename: str
    required_evidence_types: tuple[str, ...]
    build: Callable[[dict[str, Any], dict[str, dict[str, Any]]], dict[str, Any]]
    validate: Callable[[dict[str, Any]], list[str]]


def canonical_json_text(payload: dict[str, Any]) -> str:
    """Return canonical compact JSON text for deterministic hashing."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_json_sha256(payload: dict[str, Any]) -> str:
    """Return deterministic SHA256 for a JSON payload."""
    return hashlib.sha256(canonical_json_text(payload).encode("utf-8")).hexdigest()


def write_json_deterministic(path: Path, payload: dict[str, Any]) -> str:
    """Write stable JSON and return canonical SHA256 digest."""
    path.parent.mkdir(parents=True, exist_ok=True)
    canonical_hash = canonical_json_sha256(payload)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return canonical_hash


class DeterministicStageEngine:
    """Reusable explicit state machine executor."""

    def __init__(self, stages: list[StageDefinition]):
        if not stages:
            raise ValueError("stages cannot be empty")

        seen: set[str] = set()
        for stage in stages:
            stage_id = stage.stage_id.strip().upper()
            if not stage_id:
                raise ValueError("stage_id cannot be empty")
            if stage_id in seen:
                raise ValueError(f"duplicate stage_id: {stage.stage_id}")
            seen.add(stage_id)

        self._stages = stages
        self._index = {stage.stage_id.strip().upper(): idx for idx, stage in enumerate(stages)}

    def execute(
        self,
        *,
        initial_stage: str,
        target_stage: str,
        context: dict[str, Any],
        output_dir: Path,
    ) -> dict[str, Any]:
        initial = str(initial_stage or "").strip().upper()
        target = str(target_stage or "").strip().upper()
        if initial not in self._index:
            raise StageExecutionError(f"unknown initial_stage={initial!r}")
        if target not in self._index:
            raise StageExecutionError(f"unknown target_stage={target!r}")

        start_idx = self._index[initial]
        end_idx = self._index[target]
        if end_idx < start_idx:
            raise StageExecutionError(
                f"illegal transition order: initial_stage={initial} cannot transition to target_stage={target}"
            )

        output_dir.mkdir(parents=True, exist_ok=True)

        stage_payloads: dict[str, dict[str, Any]] = {}
        stage_artifacts: list[dict[str, Any]] = []
        transitions: list[dict[str, Any]] = []
        stage_confidence: dict[str, float] = {}

        for idx in range(start_idx, end_idx + 1):
            stage = self._stages[idx]
            stage_id = stage.stage_id.strip().upper()
            payload = stage.build(context, dict(stage_payloads))

            schema_errors = stage.validate(payload)
            if schema_errors:
                joined = "; ".join(schema_errors)
                raise StageExecutionError(f"schema validation failed for stage={stage_id}: {joined}")

            artifact_path = output_dir / stage.artifact_filename
            artifact_sha = write_json_deterministic(artifact_path, payload)

            stage_payloads[stage_id] = payload
            stage_artifacts.append(
                {
                    "stage_id": stage_id,
                    "artifact_name": stage.artifact_name,
                    "artifact_path": stage.artifact_filename,
                    "artifact_sha256": artifact_sha,
                    "required_evidence_types": list(stage.required_evidence_types),
                }
            )

            stage_confidence[stage_id] = self._stage_confidence(stage.required_evidence_types, payload)

            if idx > start_idx:
                previous = self._stages[idx - 1].stage_id.strip().upper()
                transitions.append(
                    {
                        "seq": len(transitions) + 1,
                        "from_stage": previous,
                        "to_stage": stage_id,
                        "status": "PASS",
                        "artifact_name": stage.artifact_name,
                        "artifact_path": stage.artifact_filename,
                        "artifact_sha256": artifact_sha,
                    }
                )

        return {
            "classification": "PASS",
            "initial_stage": initial,
            "target_stage": target,
            "terminal_stage": target,
            "stage_payloads": stage_payloads,
            "stage_artifacts": stage_artifacts,
            "transitions": transitions,
            "stage_confidence": stage_confidence,
        }

    @staticmethod
    def _stage_confidence(required_types: tuple[str, ...], payload: dict[str, Any]) -> float:
        if not required_types:
            return 1.0
        evidence = payload.get("evidence", {})
        if not isinstance(evidence, dict):
            return 0.0
        satisfied = evidence.get("required_evidence_types_satisfied", [])
        if not isinstance(satisfied, list):
            return 0.0
        satisfied_set = {str(item).strip() for item in satisfied if str(item).strip()}
        matched = sum(1 for req in required_types if req in satisfied_set)
        return round(float(matched) / float(len(required_types)), 4)
