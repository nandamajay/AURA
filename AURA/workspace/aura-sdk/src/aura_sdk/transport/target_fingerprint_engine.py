"""Target runtime capability fingerprinting engine with evidence preservation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.environment_classifier import classify_target_environment
from aura_sdk.transport.runtime_capability_graph import build_runtime_capability_graph

CAP_SUPPORTED = "SUPPORTED"
CAP_UNSUPPORTED = "UNSUPPORTED"
CAP_UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class FingerprintResult:
    fingerprint: dict[str, Any]


def _read_registry(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("capability_registry_must_be_object")
    return payload


def _status_from_trace(trace: Mapping[str, Any]) -> str:
    exit_code = int(trace.get("exit_code", 1))
    status = str(trace.get("execution_status", "")).lower()
    stdout = str(trace.get("stdout", "")).lower()
    stderr = str(trace.get("stderr", "")).lower()
    combined = f"{stdout}\n{stderr}"

    if status in {"timeout", "transport_disconnected", "invalid", "rejected"}:
        return CAP_UNSUPPORTED
    if "not found" in combined or "not recognized as an internal" in combined:
        return CAP_UNSUPPORTED
    if exit_code == 0 and status == "executed":
        return CAP_SUPPORTED
    if status == "failed" or exit_code != 0:
        return CAP_UNSUPPORTED
    return CAP_UNKNOWN


def _parse_alsa_cards(raw: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for line in raw.splitlines():
        match = re.match(r"^\s*(\d+)\s+\[(.+?)\s*\]:\s*(.+)$", line)
        if not match:
            continue
        cards.append(
            {
                "card_index": int(match.group(1)),
                "card_id": match.group(2).strip(),
                "descriptor": match.group(3).strip(),
            }
        )
    return cards


def _parse_pcm(raw: str) -> list[dict[str, Any]]:
    pcms: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        match = re.match(r"^(\S+):\s*(.*?)\s*:\s*(.*?)\s*:\s*(playback|capture)\s+(\d+)\s*$", line)
        if not match:
            continue
        pcms.append(
            {
                "pcm_id": match.group(1),
                "name": match.group(2).strip(),
                "interface": match.group(3).strip(),
                "direction": match.group(4).strip(),
                "streams": int(match.group(5)),
            }
        )
    return pcms


def _parse_tinymix_controls(raw: str) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^(\d+)\s+(.+?)\s+(\d+)\s*$", line)
        if match:
            controls.append(
                {
                    "control_id": int(match.group(1)),
                    "name": match.group(2).strip(),
                    "value": match.group(3).strip(),
                }
            )
            continue
        if line and line[0].isdigit():
            controls.append(
                {
                    "control_id": int(line.split(maxsplit=1)[0]),
                    "name": line,
                    "value": "UNKNOWN",
                }
            )
    return controls


def _parse_amixer_controls(raw: str) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.search(r"Simple mixer control '([^']+)',\s*(\d+)", line)
        if match:
            controls.append(
                {
                    "name": match.group(1),
                    "index": int(match.group(2)),
                }
            )
    return controls


def _parse_dapm_widgets(raw: str) -> list[dict[str, str]]:
    widgets: list[dict[str, str]] = []
    for line in raw.splitlines():
        value = line.strip()
        if not value:
            continue
        lowered = value.lower()
        if any(token in lowered for token in (" on", " off", "[on]", "[off]", "widget")):
            widgets.append({"raw": value})
    return widgets


def _parse_debugfs_listing(raw: str) -> list[str]:
    nodes: list[str] = []
    for line in raw.splitlines():
        value = line.strip()
        if value:
            nodes.append(value)
    return nodes


def _detect_rb3gen2(cards: list[dict[str, Any]], combined_text: str) -> bool:
    lowered = combined_text.lower()
    if "rb3gen2" in lowered or "qcs6490" in lowered:
        return True
    for card in cards:
        text = f"{card.get('card_id', '')} {card.get('descriptor', '')}".lower()
        if "rb3gen2" in text or "qcs6490" in text:
            return True
    return False


def _detect_qdsp(combined_text: str) -> bool:
    lowered = combined_text.lower()
    markers = ["qdsp", "adsp", "hexagon", "q6", "dsp"]
    return any(marker in lowered for marker in markers)


class TargetFingerprintEngine:
    def __init__(self, registry_path: str | Path | None = None):
        if registry_path is None:
            registry_path = Path(__file__).with_name("capability_registry.json")
        self._registry_path = Path(registry_path)
        self._registry = _read_registry(self._registry_path)

    def build_fingerprint(self, response_payload: Mapping[str, Any]) -> FingerprintResult:
        command_trace = response_payload.get("executor_command_trace")
        if not isinstance(command_trace, list):
            command_trace = []

        probe_outputs: dict[str, dict[str, Any]] = {}
        unsupported_evidence: list[dict[str, Any]] = []
        combined_chunks: list[str] = []

        response_raw_output = str(response_payload.get("raw_output", ""))
        response_stderr = str(response_payload.get("stderr", ""))
        combined_chunks.append(response_raw_output)
        combined_chunks.append(response_stderr)

        for item in command_trace:
            if not isinstance(item, dict):
                continue
            command = str(item.get("normalized_command", "")).strip()
            if not command:
                continue

            probe_outputs[command] = {
                "exit_code": int(item.get("exit_code", 1)),
                "execution_status": str(item.get("execution_status", "")),
                "stdout": str(item.get("stdout", "")),
                "stderr": str(item.get("stderr", "")),
                "raw_executor_invocation": str(item.get("raw_executor_invocation", "")),
            }
            combined_chunks.append(str(item.get("stdout", "")))
            combined_chunks.append(str(item.get("stderr", "")))

            status = _status_from_trace(item)
            if status == CAP_UNSUPPORTED:
                unsupported_evidence.append(
                    {
                        "normalized_command": command,
                        "exit_code": int(item.get("exit_code", 1)),
                        "stdout": str(item.get("stdout", "")),
                        "stderr": str(item.get("stderr", "")),
                    }
                )

        capabilities: dict[str, str] = {}
        for capability, config in self._registry.items():
            if not isinstance(config, dict):
                capabilities[capability] = CAP_UNKNOWN
                continue
            commands = config.get("probe_commands", [])
            mode = str(config.get("mode", "any_success"))
            statuses: list[str] = []
            for command in commands:
                probe = probe_outputs.get(str(command))
                if probe is None:
                    statuses.append(CAP_UNKNOWN)
                else:
                    statuses.append(_status_from_trace(probe))

            if not statuses:
                capabilities[capability] = CAP_UNKNOWN
            elif mode == "all_success":
                if all(value == CAP_SUPPORTED for value in statuses):
                    capabilities[capability] = CAP_SUPPORTED
                elif any(value == CAP_UNSUPPORTED for value in statuses):
                    capabilities[capability] = CAP_UNSUPPORTED
                else:
                    capabilities[capability] = CAP_UNKNOWN
            else:  # any_success
                if any(value == CAP_SUPPORTED for value in statuses):
                    capabilities[capability] = CAP_SUPPORTED
                elif all(value == CAP_UNSUPPORTED for value in statuses):
                    capabilities[capability] = CAP_UNSUPPORTED
                else:
                    capabilities[capability] = CAP_UNKNOWN

        combined_text = "\n".join(combined_chunks)
        environment = classify_target_environment(probe_outputs)

        cards_text = str(probe_outputs.get("cat /proc/asound/cards", {}).get("stdout", ""))
        pcm_text = str(probe_outputs.get("cat /proc/asound/pcm", {}).get("stdout", ""))
        tinymix_text = str(probe_outputs.get("tinymix", {}).get("stdout", ""))
        amixer_text = str(probe_outputs.get("amixer", {}).get("stdout", ""))
        dmesg_text = str(probe_outputs.get("dmesg", {}).get("stdout", ""))
        debugfs_text = str(probe_outputs.get("ls /sys/kernel/debug", {}).get("stdout", ""))
        debugfs_asoc_text = str(probe_outputs.get("ls /sys/kernel/debug/asoc", {}).get("stdout", ""))
        dapm_text = str(probe_outputs.get("cat /sys/kernel/debug/asoc/*/dapm", {}).get("stdout", ""))
        if not cards_text.strip():
            cards_text = response_raw_output
        if not pcm_text.strip():
            pcm_text = response_raw_output

        cards = _parse_alsa_cards(cards_text)
        pcm = _parse_pcm(pcm_text)
        tinymix_controls = _parse_tinymix_controls(tinymix_text)
        amixer_controls = _parse_amixer_controls(amixer_text)
        dapm_widgets = _parse_dapm_widgets(dapm_text)
        debugfs_nodes = _parse_debugfs_listing(debugfs_text)
        debugfs_asoc_nodes = _parse_debugfs_listing(debugfs_asoc_text)

        audio_discovery = {
            "alsa_topology_cards": cards,
            "pcm_entries": pcm,
            "tinymix_controls": tinymix_controls,
            "amixer_controls": amixer_controls,
            "dapm_widgets": dapm_widgets,
            "debugfs_nodes": debugfs_nodes,
            "debugfs_asoc_nodes": debugfs_asoc_nodes,
            "rb3gen2_detected": _detect_rb3gen2(cards, combined_text),
            "qdsp_present": _detect_qdsp("\n".join([combined_text, dmesg_text])),
            "audio_subsystem_evidence_graph": {
                "cards": cards,
                "pcm": pcm,
                "tinymix_controls": tinymix_controls,
                "amixer_controls": amixer_controls,
                "dapm_widgets": dapm_widgets,
                "debugfs": {
                    "root": debugfs_nodes,
                    "asoc": debugfs_asoc_nodes,
                },
            },
        }

        fingerprint: dict[str, Any] = {
            "target_id": str(response_payload.get("request_id", "unknown_target")),
            "environment": {
                "primary_environment": environment.primary_environment,
                "detected_environments": environment.detected_environments,
                "confidence": environment.confidence,
                "evidence": environment.evidence,
            },
            "capabilities": capabilities,
            "probe_outputs": probe_outputs,
            "unsupported_command_evidence": unsupported_evidence,
            "audio_discovery": audio_discovery,
            "governance_posture": "ADVISORY_ONLY",
            "claims": {
                "runtime_parity": "NOT_CLAIMED",
                "behavioral_equivalence": "NOT_CLAIMED",
                "merge_readiness": "NOT_CLAIMED",
            },
        }
        fingerprint["runtime_capability_graph"] = build_runtime_capability_graph(fingerprint)
        return FingerprintResult(fingerprint=fingerprint)
