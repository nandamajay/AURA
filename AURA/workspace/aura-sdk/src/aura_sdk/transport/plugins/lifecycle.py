"""Plugin lifecycle orchestration for portable runtime stabilization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.plugins.contracts import PluginNegotiationRequest
from aura_sdk.transport.plugins.loader import TargetPluginLoader


@dataclass(frozen=True)
class PluginLifecycleResult:
    target_id: str
    classification: str
    transitions: list[dict[str, Any]]
    quarantine: list[dict[str, Any]]
    replay_restore: dict[str, Any]


class PluginLifecycleOrchestrator:
    """Deterministic lifecycle manager: load->negotiate->validate->activate->..."""

    def __init__(self, loader: TargetPluginLoader):
        self._loader = loader

    def _transition(self, transitions: list[dict[str, Any]], state: str, **details: Any) -> None:
        transitions.append({"state": state, "details": details})

    def execute(
        self,
        *,
        fingerprint: Mapping[str, Any],
        target_profile: Mapping[str, Any],
        capability_registry: Mapping[str, Any],
        governance_state: Mapping[str, Any],
        replay_contract: Mapping[str, Any],
    ) -> PluginLifecycleResult:
        transitions: list[dict[str, Any]] = []
        selected_target_id = str(target_profile.get("target_id", "")).strip()

        self._transition(transitions, "load", requested_target=selected_target_id)
        try:
            if selected_target_id:
                self._loader.load_plugin(selected_target_id)
                self._transition(transitions, "load_complete", target_id=selected_target_id)
        except Exception as exc:
            self._loader._quarantine_plugin(  # noqa: SLF001
                target_id=selected_target_id or "unknown",
                reason=f"load_failed:{type(exc).__name__}",
            )
            self._transition(transitions, "quarantine", reason=f"load_failed:{exc}")
            return PluginLifecycleResult(
                target_id=selected_target_id,
                classification="FAIL_CLOSED",
                transitions=transitions,
                quarantine=self._loader.quarantine,
                replay_restore={"status": "SKIPPED"},
            )

        self._transition(transitions, "negotiate")
        negotiation = self._loader.negotiate(
            PluginNegotiationRequest(
                fingerprint=dict(fingerprint),
                target_profile=dict(target_profile),
                capability_registry=dict(capability_registry),
                governance_state=dict(governance_state),
            )
        )
        self._transition(
            transitions,
            "negotiate_complete",
            classification=negotiation.classification,
            selected_target_id=negotiation.selected_target_id,
            confidence=negotiation.confidence,
        )

        selected = str(negotiation.selected_target_id or selected_target_id).strip()
        if not selected:
            self._transition(transitions, "quarantine", reason="no_selected_target")
            return PluginLifecycleResult(
                target_id="",
                classification="FAIL_CLOSED",
                transitions=transitions,
                quarantine=self._loader.quarantine,
                replay_restore={"status": "SKIPPED"},
            )

        self._transition(transitions, "validate")
        replay_validation = self._loader.validate_replay_compatibility(
            target_id=selected,
            replay_contract=dict(replay_contract),
        )
        self._transition(
            transitions,
            "validate_complete",
            replay_compatibility=replay_validation.get("compatibility_level", "INCOMPATIBLE"),
        )

        if str(negotiation.classification) != "COMPATIBLE" or str(replay_validation.get("compatibility_level", "")) == "INCOMPATIBLE":
            self._loader._quarantine_plugin(  # noqa: SLF001
                target_id=selected,
                reason="validation_failed_or_negotiation_incompatible",
            )
            self._transition(transitions, "quarantine", target_id=selected, reason="validation_failed")
            self._loader.unload_plugin(selected)
            self._transition(transitions, "unload", target_id=selected)
            replay_restore = {
                "status": "FAIL_CLOSED",
                "reason": "incompatible_for_replay_restore",
            }
            self._transition(transitions, "replay_restore", **replay_restore)
            return PluginLifecycleResult(
                target_id=selected,
                classification="FAIL_CLOSED",
                transitions=transitions,
                quarantine=self._loader.quarantine,
                replay_restore=replay_restore,
            )

        self._transition(transitions, "activate", target_id=selected)
        replay_restore = {
            "status": "RESTORED",
            "target_id": selected,
            "replay_compatibility": replay_validation.get("compatibility_level", "UNKNOWN"),
        }
        self._transition(transitions, "replay_restore", **replay_restore)

        return PluginLifecycleResult(
            target_id=selected,
            classification="COMPATIBLE",
            transitions=transitions,
            quarantine=self._loader.quarantine,
            replay_restore=replay_restore,
        )

    @staticmethod
    def build_lifecycle_graph(transitions: list[dict[str, Any]]) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        for index, item in enumerate(transitions):
            state = str(item.get("state", "unknown"))
            node_id = f"{index}:{state}"
            nodes.append({"id": node_id, "state": state, "details": item.get("details", {})})
            if index > 0:
                prev = transitions[index - 1]
                edges.append(
                    {
                        "from": f"{index - 1}:{str(prev.get('state', 'unknown'))}",
                        "to": node_id,
                        "relation": "lifecycle_step",
                    }
                )

        return {
            "schema_version": "1.0",
            "graph_name": "plugin_lifecycle_graph",
            "nodes": nodes,
            "edges": edges,
            "deterministic": True,
        }
