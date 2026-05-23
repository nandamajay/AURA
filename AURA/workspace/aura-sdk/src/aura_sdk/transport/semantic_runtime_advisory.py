"""Runtime advisory engine for Kernel Semantic Knowledge Layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class SemanticRuntimeAdvisoryResult:
    semantic_runtime_advisories: dict[str, Any]
    deterministic_fingerprint: str
    adapter_payload: dict[str, Any]


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "ok", "pass", "success"}
    return False


def _build_advisories(
    *,
    target_id: str,
    runtime_evidence: Mapping[str, Any],
    semantic_entity_graph: Mapping[str, Any],
    semantic_portability_rules: Mapping[str, Any],
    semantic_governance_boundary: Mapping[str, Any],
) -> dict[str, Any]:
    runtime = _as_dict(runtime_evidence)
    entities = _as_dict(_as_dict(semantic_entity_graph).get("entity_categories"))
    portability = _as_dict(semantic_portability_rules)
    governance = _as_dict(semantic_governance_boundary)

    advisories: list[dict[str, Any]] = []

    if not _is_true(runtime.get("process_success", runtime.get("playback_completion", False))):
        advisories.append(
            {
                "code": "runtime_process_not_successful",
                "severity": "HIGH",
                "advisory": "Runtime process indicates failure; semantic recommendations remain advisory and cannot execute runtime changes.",
            }
        )

    if str(portability.get("classification", "")) == "FAIL_CLOSED":
        advisories.append(
            {
                "code": "portability_fail_closed",
                "severity": "HIGH",
                "advisory": "Portability reasoning failed closed; migration guidance must stop at diagnostic advisory output.",
            }
        )

    blockers = _as_list(_as_dict(portability.get("rules")).get("blocked_unsafe"))
    if blockers:
        advisories.append(
            {
                "code": "blocked_unsafe_patterns",
                "severity": "HIGH",
                "advisory": "Detected blocked semantic portability patterns requiring manual engineering review.",
                "evidence": blockers,
            }
        )

    if str(governance.get("classification", "")) == "FAIL_CLOSED":
        advisories.append(
            {
                "code": "governance_fail_closed",
                "severity": "HIGH",
                "advisory": "Governance boundary violation detected; semantic layer must remain read-only and advisory-only.",
            }
        )

    lifecycle_entities = [str(item) for item in _as_list(entities.get("runtime_lifecycle_relationships")) if str(item).strip()]
    if lifecycle_entities:
        advisories.append(
            {
                "code": "runtime_lifecycle_context",
                "severity": "INFO",
                "advisory": "Runtime lifecycle vocabulary extracted for correlation with evidence transitions.",
                "entities": lifecycle_entities[:30],
            }
        )

    if not advisories:
        advisories.append(
            {
                "code": "semantic_advisory_ready",
                "severity": "INFO",
                "advisory": "Semantic knowledge layer is ready for governed advisory reasoning.",
            }
        )

    classification = "PASS"
    if any(str(_as_dict(item).get("severity", "")).upper() == "HIGH" for item in advisories):
        classification = "FAIL_CLOSED" if str(governance.get("classification", "PASS")) == "FAIL_CLOSED" else "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "semantic_runtime_advisories",
        "target_id": str(target_id),
        "classification": classification,
        "advisory_only": True,
        "runtime_state_mutation_allowed": False,
        "runtime_execution_permitted_from_semantics": False,
        "advisories": advisories,
        "runtime_summary": {
            "run_id": str(runtime.get("run_id", "")),
            "process_success": bool(runtime.get("process_success", False)),
            "playback_completion": bool(runtime.get("playback_completion", False)),
            "classification": str(runtime.get("classification", "UNKNOWN")),
        },
    }

    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


class SemanticRuntimeAdvisoryEngine:
    """Plugin-safe runtime advisory builder for semantic knowledge cognition."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()

    def analyze(
        self,
        *,
        target_id: str,
        source_id: str,
        source_version: str,
        runtime_evidence: Mapping[str, Any],
        semantic_entity_graph: Mapping[str, Any],
        semantic_portability_rules: Mapping[str, Any],
        semantic_governance_boundary: Mapping[str, Any],
    ) -> SemanticRuntimeAdvisoryResult:
        plugin = self._plugins.load_plugin(target_id)
        adapter_payload = _as_dict(
            plugin.semantic_knowledge_adapter(
                {
                    "source_id": str(source_id),
                    "source_version": str(source_version),
                    "runtime_evidence": dict(runtime_evidence),
                    "semantic_entity_graph": dict(semantic_entity_graph),
                }
            )
        )

        advisory = _build_advisories(
            target_id=target_id,
            runtime_evidence=runtime_evidence,
            semantic_entity_graph=semantic_entity_graph,
            semantic_portability_rules=semantic_portability_rules,
            semantic_governance_boundary=semantic_governance_boundary,
        )

        return SemanticRuntimeAdvisoryResult(
            semantic_runtime_advisories=advisory,
            deterministic_fingerprint=str(advisory.get("deterministic_fingerprint", "")),
            adapter_payload=adapter_payload,
        )
