"""Portable target plugin loader and deterministic negotiation engine."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.plugins.contracts import (
    PluginNegotiationRequest,
    PluginNegotiationResult,
    TargetPluginContract,
    assert_plugin_contract,
)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _load_registry(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("plugin_registry_invalid")
    return payload


def _split_entrypoint(entrypoint: str) -> tuple[str, str]:
    if ":" not in entrypoint:
        raise ValueError("plugin_entrypoint_invalid")
    module_name, symbol_name = entrypoint.split(":", 1)
    module_name = module_name.strip()
    symbol_name = symbol_name.strip()
    if not module_name or not symbol_name:
        raise ValueError("plugin_entrypoint_invalid")
    return module_name, symbol_name


class TargetPluginLoader:
    """Registry-driven loader for target plugins.

    The loader is generic and never hard-codes target-specific branch logic.
    """

    def __init__(self, registry_path: str | Path | None = None):
        if registry_path is None:
            registry_path = Path(__file__).with_name("target_plugin_registry.json")
        self._registry_path = Path(registry_path)
        self._registry = _load_registry(self._registry_path)
        self._cache: dict[str, TargetPluginContract] = {}

    @property
    def registry(self) -> dict[str, Any]:
        return dict(self._registry)

    def available_targets(self) -> list[str]:
        plugins = _as_list(self._registry.get("plugins"))
        return sorted(
            {
                str(entry.get("target_id", "")).strip()
                for entry in plugins
                if isinstance(entry, dict) and str(entry.get("target_id", "")).strip()
            }
        )

    def _registry_entry(self, target_id: str) -> dict[str, Any]:
        for entry in _as_list(self._registry.get("plugins")):
            if not isinstance(entry, dict):
                continue
            if str(entry.get("target_id", "")).strip() == target_id:
                return entry
        raise KeyError(f"plugin_target_not_registered:{target_id}")

    def load_plugin(self, target_id: str) -> TargetPluginContract:
        key = str(target_id).strip()
        if not key:
            raise ValueError("plugin_target_id_invalid")
        if key in self._cache:
            return self._cache[key]

        entry = self._registry_entry(key)
        module_name, symbol_name = _split_entrypoint(str(entry.get("entrypoint", "")))
        module = importlib.import_module(module_name)
        symbol = getattr(module, symbol_name)
        plugin = symbol() if callable(symbol) else symbol
        assert_plugin_contract(plugin)
        plugin_target = str(getattr(plugin, "target_id", "")).strip()
        if plugin_target != key:
            raise TypeError(f"plugin_target_id_mismatch:{key}!={plugin_target}")
        self._cache[key] = plugin
        return plugin

    def _score_entry(
        self,
        entry: Mapping[str, Any],
        request: PluginNegotiationRequest,
    ) -> dict[str, Any]:
        target_id = str(entry.get("target_id", "")).strip()
        plugin = self.load_plugin(target_id)

        fingerprint = _as_dict(request.fingerprint)
        target_profile = _as_dict(request.target_profile)
        capabilities = _as_dict(fingerprint.get("capabilities"))
        discovery = _as_dict(fingerprint.get("audio_discovery"))
        detection = _as_dict(entry.get("detection"))

        corpus = json.dumps(fingerprint, sort_keys=True).lower()

        marker_list = [str(item).lower() for item in _as_list(detection.get("text_markers")) if str(item).strip()]
        marker_hits = [item for item in marker_list if item in corpus]

        flag_list = [str(item) for item in _as_list(detection.get("audio_discovery_flags")) if str(item).strip()]
        flag_hits = [flag for flag in flag_list if bool(discovery.get(flag))]

        required_caps = [str(item) for item in _as_list(detection.get("required_capabilities")) if str(item).strip()]
        cap_hits = [cap for cap in required_caps if str(capabilities.get(cap, "UNKNOWN")) == "SUPPORTED"]

        plugin_cap = _as_dict(plugin.capability_provider({"fingerprint": fingerprint}))
        plugin_supported = bool(plugin_cap.get("supported", False))
        plugin_conf = _to_float(plugin_cap.get("confidence", 0.0))

        profile_target_id = str(target_profile.get("target_id", "")).strip()
        target_id_match = profile_target_id == target_id if profile_target_id else False

        marker_ratio = (len(marker_hits) / len(marker_list)) if marker_list else 0.0
        flag_ratio = (len(flag_hits) / len(flag_list)) if flag_list else 0.0
        cap_ratio = (len(cap_hits) / len(required_caps)) if required_caps else 0.0

        score = 0.0
        if target_id_match:
            score += 0.35
        score += 0.20 * marker_ratio
        score += 0.15 * flag_ratio
        score += 0.15 * cap_ratio
        score += 0.15 * plugin_conf
        if not plugin_supported:
            score *= 0.25

        score = round(min(1.0, score), 3)

        return {
            "target_id": target_id,
            "score": score,
            "priority": int(entry.get("priority", 0)),
            "target_id_match": target_id_match,
            "plugin_supported": plugin_supported,
            "marker_hits": marker_hits,
            "flag_hits": flag_hits,
            "capability_hits": cap_hits,
            "plugin_confidence": plugin_conf,
        }

    def negotiate(self, request: PluginNegotiationRequest) -> PluginNegotiationResult:
        governance = _as_dict(request.governance_state)
        fail_closed = bool(governance.get("fail_closed_posture", True))

        entries = [entry for entry in _as_list(self._registry.get("plugins")) if isinstance(entry, dict)]
        if not entries:
            return PluginNegotiationResult(
                classification="FAIL_CLOSED_NO_PLUGINS_REGISTERED",
                selected_target_id="",
                confidence=0.0,
                reasons=["plugin_registry_empty"],
                candidate_scores=[],
                governance_posture="FAIL_CLOSED",
            )

        scored = [self._score_entry(entry, request) for entry in entries]
        scored.sort(key=lambda item: (item["score"], item["priority"]), reverse=True)

        selected = scored[0] if scored else None
        if not selected:
            return PluginNegotiationResult(
                classification="FAIL_CLOSED_NO_CANDIDATE",
                selected_target_id="",
                confidence=0.0,
                reasons=["no_candidate"],
                candidate_scores=scored,
                governance_posture="FAIL_CLOSED",
            )

        if not bool(selected.get("plugin_supported", False)):
            reasons = ["selected_plugin_not_supported_by_evidence"]
            return PluginNegotiationResult(
                classification="FAIL_CLOSED_UNSUPPORTED_TARGET" if fail_closed else "ADVISORY_UNSUPPORTED_TARGET",
                selected_target_id=str(selected.get("target_id", "")),
                confidence=float(selected.get("score", 0.0)),
                reasons=reasons,
                candidate_scores=scored,
                governance_posture="FAIL_CLOSED" if fail_closed else "ADVISORY_ONLY",
            )

        threshold = 0.55 if fail_closed else 0.35
        confidence = float(selected.get("score", 0.0))
        if confidence < threshold:
            return PluginNegotiationResult(
                classification="FAIL_CLOSED_LOW_CONFIDENCE" if fail_closed else "ADVISORY_LOW_CONFIDENCE",
                selected_target_id=str(selected.get("target_id", "")),
                confidence=confidence,
                reasons=[f"confidence_below_threshold:{threshold}"],
                candidate_scores=scored,
                governance_posture="FAIL_CLOSED" if fail_closed else "ADVISORY_ONLY",
            )

        return PluginNegotiationResult(
            classification="COMPATIBLE",
            selected_target_id=str(selected.get("target_id", "")),
            confidence=confidence,
            reasons=["evidence_backed_plugin_selection"],
            candidate_scores=scored,
            governance_posture="ADVISORY_ONLY_OR_GOVERNED_ONLY",
        )

    def validate_replay_compatibility(
        self,
        *,
        target_id: str,
        replay_contract: Mapping[str, Any],
    ) -> dict[str, Any]:
        plugin = self.load_plugin(target_id)
        result = plugin.validation_provider(
            {
                "mode": "replay_compatibility",
                "replay_contract": dict(replay_contract),
            }
        )
        result = _as_dict(result)
        result["target_id"] = target_id
        result["validation_type"] = "deterministic_plugin_replay_compatibility"
        return result
