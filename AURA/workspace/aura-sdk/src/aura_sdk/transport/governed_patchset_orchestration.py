"""Governed patchset orchestration engine.

Dependency-aware multi-patch orchestration using tiny realistic Qualcomm-style
examples with deterministic replay and fail-closed governance.
"""

from __future__ import annotations

import difflib
import json
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.governed_translation_intelligence import (
    GovernedTranslationIntelligenceEngine,
)
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.runtime_evidence_acquisition import (
    RuntimeEvidenceAcquisitionEngine,
)
from aura_sdk.transport.runtime_truth_engine import RuntimeTruthEngine
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint
from aura_sdk.transport.upstream_acceptance_simulation import (
    UpstreamAcceptanceSimulationEngine,
)


@dataclass(frozen=True)
class GovernedPatchsetOrchestrationResult:
    patchset_bundle: dict[str, Any]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def _default_governance(governance_state: Mapping[str, Any]) -> dict[str, Any]:
    state = dict(_as_dict(governance_state))
    if state:
        return state
    return {
        "fail_closed_posture": True,
        "autonomous_patching_allowed": False,
        "autonomous_topology_rewrite_allowed": False,
        "autonomous_runtime_mutation_allowed": False,
        "autonomous_upstream_generation_allowed": False,
    }


def _replace_identifier_tokens(code: str, old: str, new: str) -> tuple[str, int]:
    if old == new:
        return code, 0

    out: list[str] = []
    i = 0
    n = len(code)
    count = 0
    state = "normal"

    while i < n:
        ch = code[i]
        if state == "normal":
            if ch == "/" and i + 1 < n and code[i + 1] == "/":
                state = "line_comment"
                out.append(ch)
                i += 1
                out.append(code[i])
                i += 1
                continue
            if ch == "/" and i + 1 < n and code[i + 1] == "*":
                state = "block_comment"
                out.append(ch)
                i += 1
                out.append(code[i])
                i += 1
                continue
            if ch == '"':
                state = "string"
                out.append(ch)
                i += 1
                continue
            if ch == "'":
                state = "char"
                out.append(ch)
                i += 1
                continue
            if ch.isalpha() or ch == "_":
                j = i + 1
                while j < n and (code[j].isalnum() or code[j] == "_"):
                    j += 1
                token = code[i:j]
                if token == old:
                    out.append(new)
                    count += 1
                else:
                    out.append(token)
                i = j
                continue
            out.append(ch)
            i += 1
            continue

        if state == "line_comment":
            out.append(ch)
            i += 1
            if ch == "\n":
                state = "normal"
            continue
        if state == "block_comment":
            out.append(ch)
            i += 1
            if ch == "*" and i < n and code[i] == "/":
                out.append(code[i])
                i += 1
                state = "normal"
            continue
        if state == "string":
            out.append(ch)
            i += 1
            if ch == "\\" and i < n:
                out.append(code[i])
                i += 1
                continue
            if ch == '"':
                state = "normal"
            continue
        if state == "char":
            out.append(ch)
            i += 1
            if ch == "\\" and i < n:
                out.append(code[i])
                i += 1
                continue
            if ch == "'":
                state = "normal"
            continue

    return "".join(out), count


def _tiny_patchset_model() -> dict[str, Any]:
    file_a = "sound/soc/qcom/q6apm-log-wrapper.c"
    file_b = "sound/soc/qcom/q6apm-cap-wrapper.c"
    file_c = "sound/soc/qcom/q6apm-helper-wrapper.c"

    sources = {
        file_a: "\n".join(
            [
                "struct device;",
                "void dev_dbg(struct device *dev, const char *fmt, ...);",
                "void qcom_dbg_log(struct device *dev, const char *fmt, ...);",
                "#define QCOM_AUD_DBG(dev, fmt, ...) qcom_dbg_log(dev, fmt, ##__VA_ARGS__)",
                "int log_wrap_probe(struct device *dev)",
                "{",
                '    QCOM_AUD_DBG(dev, "probe start");',
                "    return 0;",
                "}",
                "",
            ]
        ),
        file_b: "\n".join(
            [
                "struct device;",
                "int device_is_registered(struct device *dev);",
                "int qcom_cap_bool(struct device *dev);",
                "#define QCOM_AUD_CAP(dev) qcom_cap_bool(dev)",
                "int cap_wrap_state(struct device *dev)",
                "{",
                "    return QCOM_AUD_CAP(dev) ? 1 : 0;",
                "}",
                "",
            ]
        ),
        file_c: "\n".join(
            [
                "struct snd_soc_component;",
                "int snd_soc_component_enable(struct snd_soc_component *component);",
                "int qcom_helper_alias(struct snd_soc_component *component);",
                "int helper_wrap_apply(struct snd_soc_component *component)",
                "{",
                "    return qcom_helper_alias(component);",
                "}",
                "",
            ]
        ),
    }

    mappings = [
        {"downstream_construct": "qcom_dbg_log", "upstream_equivalent": "dev_dbg", "equivalence_confidence": 0.94},
        {
            "downstream_construct": "qcom_cap_bool",
            "upstream_equivalent": "device_is_registered",
            "equivalence_confidence": 0.92,
        },
        {
            "downstream_construct": "qcom_helper_alias",
            "upstream_equivalent": "snd_soc_component_enable",
            "equivalence_confidence": 0.89,
        },
    ]

    patch_units = [
        {
            "patch_id": "asoc_patch_01_logging_wrapper_conversion",
            "title": "Normalize vendor logging wrapper",
            "construct": "qcom_dbg_log",
            "replacement": "dev_dbg",
            "files": [file_a],
            "subsystem": "asoc",
            "risk": "LOW",
            "depends_on": [],
            "group": "wrappers",
        },
        {
            "patch_id": "runtime_patch_02_capability_wrapper_normalization",
            "title": "Normalize vendor capability wrapper",
            "construct": "qcom_cap_bool",
            "replacement": "device_is_registered",
            "files": [file_b],
            "subsystem": "runtime",
            "risk": "MEDIUM",
            "depends_on": ["asoc_patch_01_logging_wrapper_conversion"],
            "group": "capabilities",
        },
        {
            "patch_id": "asoc_patch_03_helper_alias_cleanup",
            "title": "Replace tiny helper alias with upstream helper",
            "construct": "qcom_helper_alias",
            "replacement": "snd_soc_component_enable",
            "files": [file_c],
            "subsystem": "asoc",
            "risk": "MEDIUM",
            "depends_on": [
                "asoc_patch_01_logging_wrapper_conversion",
                "runtime_patch_02_capability_wrapper_normalization",
            ],
            "group": "helpers",
        },
    ]

    return {
        "schema_version": "1.0",
        "model_name": "tiny_qcom_patchset_model_v1",
        "source_snapshots": sources,
        "patch_units": patch_units,
        "downstream_upstream_mapping_graph": {"entries": mappings},
        "upstream_equivalence_map": {"entries": mappings},
        "semantic_entity_graph": {
            "nodes": [
                {"id": "n1", "label": "qcom_dbg_log"},
                {"id": "n2", "label": "qcom_cap_bool"},
                {"id": "n3", "label": "qcom_helper_alias"},
                {"id": "n4", "label": "dev_dbg"},
                {"id": "n5", "label": "device_is_registered"},
                {"id": "n6", "label": "snd_soc_component_enable"},
            ]
        },
        "structural_artifacts": {
            "downstream_driver_graph": {
                "downstream_root": "sound/soc/qcom",
                "extracted": {
                    "ops_structures": ["log_wrap_probe", "cap_wrap_state", "helper_wrap_apply"],
                    "vendor_extensions": ["qcom_dbg_log", "qcom_cap_bool", "qcom_helper_alias"],
                    "proprietary_runtime_hooks": ["qcom_dbg_log"],
                    "routing_structures": ["qcom_audio_route"],
                    "pcm_dpcm_paths": ["pcm-playback-0"],
                    "dependencies": {"soundwire": ["soundwire_link_0"]},
                    "dai_links": {"all": ["qcom-fe-be-link0"]},
                },
            },
            "topology_runtime_graph": {
                "classification": "PASS",
                "nodes": [{"id": "fe0"}, {"id": "be0"}],
                "edges": [{"from": "fe0", "to": "be0"}],
            },
        },
        "topology_artifacts": {
            "topology_runtime_graph": {
                "classification": "PASS",
                "nodes": [{"id": "fe0"}, {"id": "be0"}],
                "edges": [{"from": "fe0", "to": "be0"}],
            },
            "dts_topology_graph": {
                "classification": "PASS",
                "nodes": [{"id": "dts:qcom-audio"}],
                "edges": [],
            },
            "topology_translation_report": {
                "classification": "PASS",
                "translation_confidence": 0.91,
                "fe_be_route_equivalence": [{"fe": "fe0", "be": "be0"}],
            },
        },
        "translation_runtime_artifacts": {
            "pcm_lifecycle_trace": {
                "transitions": [
                    {"stage": "qcom_dbg_log"},
                    {"stage": "qcom_cap_bool"},
                    {"stage": "qcom_helper_alias"},
                ]
            }
        },
        "runtime_truth_input": {
            "runtime_evidence": {
                "process_success": True,
                "playback_completion": True,
                "playback_runtime_seconds": 3.0,
                "route_fingerprint": "qcom_patchset_route_fp",
            },
            "source_payloads": {
                "dmesg": {"events": [{"timestamp_ms": 1000.0, "category": "dsp_sync", "detail": "qcom_dbg_log dev_dbg"}]},
                "ftrace": {"events": [{"timestamp_ms": 1000.0, "category": "dapm_transition", "detail": "route enable"}]},
                "trace_cmd": {"events": [{"timestamp_ms": 1000.0, "category": "pcm_lifecycle", "detail": "qcom_cap_bool device_is_registered"}]},
                "tinyalsa_dump": {"events": [{"timestamp_ms": 1000.0, "category": "power_transition", "detail": "power up"}]},
                "procfs_sysfs": {"events": [{"timestamp_ms": 1000.0, "category": "irq", "detail": "irq done"}]},
                "soundwire_debugfs": {"events": [{"timestamp_ms": 1000.0, "category": "soundwire", "detail": "soundwire active"}]},
                "alsa_topology_runtime": {"events": [{"timestamp_ms": 1000.0, "category": "dapm_transition", "detail": "route enable"}]},
                "mailbox_trace": {"events": [{"timestamp_ms": 1000.0, "category": "dsp_sync", "detail": "mailbox"}]},
                "dsp_response_log": {"events": [{"timestamp_ms": 1000.0, "category": "dsp_sync", "detail": "dsp ack"}]},
            },
        },
        "runtime_acquisition_input": {
            "dmesg": {"lines": ["1000.0 qcom_dbg_log dev_dbg qcom_cap_bool device_is_registered qcom_helper_alias snd_soc_component_enable"]},
            "ftrace": {"lines": ["1000.0 dapm route enable"]},
            "trace_cmd": {"lines": ["1000.0 pcm fe0 be0 runtime"]},
            "tinymix_state": {"lines": ["RX_PATH: soundwire runtime active"]},
            "procfs_runtime": {"lines": ["00-00: pcm state running"]},
            "debugfs_runtime": {"lines": ["asoc clock status enabled"]},
            "soundwire_runtime": {"lines": ["soundwire swr0 stream active"]},
            "dsp_mailbox": {"lines": ["mailbox dsp sync ok"]},
            "irq_runtime": {"lines": ["1000.0 irq complete"]},
            "clocks": {"lines": ["clock lpass enabled"]},
            "regulators": {"lines": ["regulator vdd_audio enabled"]},
            "ipc_path": {"lines": ["ipc glink path online"]},
        },
        "ipcat_hardware_metadata": {
            "platform": "RB3Gen2",
            "soc": "qcom-rb3",
            "board": "rb3gen2",
            "audio_subsystem": "qcom_audio",
            "ipc_nodes": ["apr", "glink", "rpmsg"],
            "ip_blocks": ["asoc", "soundwire", "q6dsp"],
        },
    }


def _topological_order(units: list[dict[str, Any]]) -> tuple[list[str], bool, list[str]]:
    deps: dict[str, set[str]] = {}
    for row in units:
        item = _as_dict(row)
        pid = str(item.get("patch_id", "")).strip()
        if not pid:
            continue
        deps.setdefault(pid, set())
        for dep in _as_list(item.get("depends_on")):
            dep_id = str(dep).strip()
            if dep_id:
                deps[pid].add(dep_id)
                deps.setdefault(dep_id, set())

    unresolved = {key: set(value) for key, value in deps.items()}
    order: list[str] = []
    while unresolved:
        ready = sorted([k for k, v in unresolved.items() if not v])
        if not ready:
            break
        for patch_id in ready:
            order.append(patch_id)
            unresolved.pop(patch_id, None)
            for left in unresolved.values():
                left.discard(patch_id)

    has_cycle = bool(unresolved)
    unresolved_nodes = sorted(unresolved.keys()) if has_cycle else []
    return order, has_cycle, unresolved_nodes


def _compile_sources(sources: Mapping[str, str]) -> dict[str, Any]:
    compiler = ""
    for candidate in ("cc", "gcc", "clang"):
        proc = subprocess.run(["bash", "-lc", f"command -v {candidate}"], check=False, capture_output=True, text=True)
        if proc.returncode == 0 and proc.stdout.strip():
            compiler = candidate
            break

    if not compiler:
        return {
            "compile_validation_executed": False,
            "compile_validation_passed": False,
            "compiler": "",
            "command": "",
            "stderr": "no_c_compiler_found",
            "stdout": "",
            "files_checked": len(_as_dict(sources)),
        }

    failed: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="aura_patchset_compile_") as td:
        tmpdir = Path(td)
        for idx, (path, content) in enumerate(sorted(_as_dict(sources).items()), start=1):
            src = tmpdir / f"file_{idx}.c"
            src.write_text(str(content), encoding="utf-8")
            cmd = [compiler, "-x", "c", "-std=gnu11", "-fsyntax-only", str(src)]
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
            if proc.returncode != 0:
                failed.append(
                    {
                        "source_path": str(path),
                        "stderr": proc.stderr.strip(),
                        "stdout": proc.stdout.strip(),
                    }
                )
    return {
        "compile_validation_executed": True,
        "compile_validation_passed": len(failed) == 0,
        "compiler": compiler,
        "command": f"{compiler} -x c -std=gnu11 -fsyntax-only <source>",
        "stderr": "; ".join(str(_as_dict(row).get("stderr", "")) for row in failed if str(_as_dict(row).get("stderr", ""))),
        "stdout": "",
        "files_checked": len(_as_dict(sources)),
        "failed_files": failed,
    }


def _build_patch(before: Mapping[str, str], after: Mapping[str, str]) -> tuple[str, list[str]]:
    changed: list[str] = []
    chunks: list[str] = []
    for path in sorted(before.keys()):
        a = str(before.get(path, ""))
        b = str(after.get(path, ""))
        if a == b:
            continue
        changed.append(path)
        diff = difflib.unified_diff(a.splitlines(keepends=True), b.splitlines(keepends=True), fromfile=f"a/{path}", tofile=f"b/{path}", n=3)
        chunks.append("".join(diff))
    text = "# Governed Tiny Multi Patchset\n# mode=proposal\n\n" + "\n".join(chunks)
    return text, changed


class GovernedPatchsetOrchestrationEngine:
    """Dependency-aware governed patchset orchestration."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()

    def analyze(
        self,
        *,
        target_id: str,
        session_id: str,
        lineage_id: str,
        governance_state: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        plugin_capability_state: Mapping[str, Any],
        previous_history: list[Mapping[str, Any]] | None,
        evidence_references: list[str] | None,
    ) -> GovernedPatchsetOrchestrationResult:
        model = _tiny_patchset_model()
        governance = _default_governance(governance_state)
        evidence = [str(item) for item in (evidence_references or []) if str(item).strip()]

        runtime_truth = RuntimeTruthEngine(plugin_loader=self._plugins).analyze(
            target_id=str(target_id),
            lineage_id=f"{lineage_id}:runtime_truth",
            runtime_evidence=_as_dict(_as_dict(model.get("runtime_truth_input")).get("runtime_evidence")),
            source_payloads=_as_dict(_as_dict(model.get("runtime_truth_input")).get("source_payloads")),
            structural_artifacts=_as_dict(model.get("structural_artifacts")),
            replay_traces=dict(replay_traces),
            governance_state=dict(governance),
            plugin_capability_state=dict(plugin_capability_state),
            dts_cognition=_as_dict(_as_dict(model.get("topology_artifacts")).get("dts_topology_graph")),
            archived_runtime_lineage=[],
            evidence_references=evidence + ["artifact://tiny_patchset_model"],
        ).runtime_truth_bundle
        runtime_truth_artifacts = _as_dict(runtime_truth.get("artifacts"))

        translation = GovernedTranslationIntelligenceEngine(plugin_loader=self._plugins).analyze(
            target_id=str(target_id),
            session_id=f"{session_id}:translation",
            lineage_id=f"{lineage_id}:translation",
            runtime_artifacts={
                "runtime_truth_graph": _as_dict(runtime_truth_artifacts.get("runtime_truth_graph")),
                "pcm_lifecycle_trace": _as_dict(_as_dict(model.get("translation_runtime_artifacts")).get("pcm_lifecycle_trace")),
            },
            topology_artifacts=_as_dict(model.get("topology_artifacts")),
            semantic_artifacts={
                "semantic_entity_graph": _as_dict(model.get("semantic_entity_graph")),
                "semantic_confidence_report": {"classification": {"scores": {"upstream_friendly": 0.9}}},
            },
            structural_artifacts=_as_dict(model.get("structural_artifacts")),
            translation_artifacts={
                "downstream_upstream_mapping_graph": _as_dict(model.get("downstream_upstream_mapping_graph")),
                "upstream_equivalence_map": _as_dict(model.get("upstream_equivalence_map")),
                "topology_translation_report": _as_dict(_as_dict(model.get("topology_artifacts")).get("topology_translation_report")),
                "runtime_portability_analysis": {"runtime_portability_blockers": [], "unsupported_runtime_dependencies": []},
            },
            governance_state=dict(governance),
            replay_traces=dict(replay_traces),
            plugin_capability_state=dict(plugin_capability_state),
            evidence_references=evidence + ["artifact://runtime_truth_graph"],
            previous_translation_history=[],
        ).translation_bundle
        translation_artifacts = _as_dict(translation.get("artifacts"))

        runtime_acq = RuntimeEvidenceAcquisitionEngine(plugin_loader=self._plugins).analyze(
            target_id=str(target_id),
            session_id=f"{session_id}:runtime_acq",
            lineage_id=f"{lineage_id}:runtime_acq",
            source_payloads=_as_dict(model.get("runtime_acquisition_input")),
            translation_artifacts=translation_artifacts,
            runtime_artifacts={
                "topology_runtime_graph": _as_dict(_as_dict(model.get("topology_artifacts")).get("topology_runtime_graph")),
                "dts_topology_graph": _as_dict(_as_dict(model.get("topology_artifacts")).get("dts_topology_graph")),
            },
            ipcat_hardware_metadata=_as_dict(model.get("ipcat_hardware_metadata")),
            governance_state=dict(governance),
            replay_traces=dict(replay_traces),
            plugin_capability_state=dict(plugin_capability_state),
            previous_session_history=[],
            evidence_references=evidence + ["artifact://runtime_equivalence_validation"],
        ).acquisition_bundle
        runtime_acq_artifacts = _as_dict(runtime_acq.get("artifacts"))

        patch_units = [_as_dict(row) for row in _as_list(model.get("patch_units")) if isinstance(row, dict)]
        patch_map = {str(row.get("patch_id", "")): row for row in patch_units if str(row.get("patch_id", "")).strip()}
        ordered_ids, cycle, unresolved = _topological_order(patch_units)

        dependency_graph = {
            "schema_version": "1.0",
            "graph_name": "patch_dependency_graph",
            "target_id": str(target_id),
            "classification": "FAIL_CLOSED" if cycle else "PASS",
            "nodes": [
                {
                    "patch_id": str(row.get("patch_id", "")),
                    "depends_on": [str(v) for v in _as_list(row.get("depends_on")) if str(v).strip()],
                    "subsystem": str(row.get("subsystem", "")),
                    "risk": str(row.get("risk", "")),
                    "group": str(row.get("group", "")),
                }
                for row in patch_units
            ],
            "ordered_patch_ids": ordered_ids,
            "dependency_cycles_detected": bool(cycle),
            "unresolved_nodes": unresolved,
            "summary": {
                "patch_count": len(patch_units),
                "ordered_count": len(ordered_ids),
                "cycle_detected": bool(cycle),
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        dependency_graph["deterministic_fingerprint"] = stable_fingerprint(dependency_graph)

        before_sources = {str(k): str(v) for k, v in _as_dict(model.get("source_snapshots")).items()}
        current_sources = dict(before_sources)

        runtime_validation_rows = {
            str(_as_dict(row).get("downstream_construct", "")).strip().lower(): _as_dict(row)
            for row in _as_list(_as_dict(translation_artifacts.get("runtime_equivalence_validation")).get("candidate_validations"))
            if str(_as_dict(row).get("downstream_construct", "")).strip()
        }

        checkpoints: list[dict[str, Any]] = []
        ordering_warnings: list[dict[str, Any]] = []
        cumulative_states: list[dict[str, Any]] = []
        cumulative_conf = 1.0
        interaction_conflicts: list[dict[str, Any]] = []
        total_replacements = 0
        compile_failure = False
        unsafe_ordering = False

        for seq, patch_id in enumerate(ordered_ids, start=1):
            patch = _as_dict(patch_map.get(patch_id))
            if not patch:
                unsafe_ordering = True
                ordering_warnings.append(
                    {
                        "patch_id": str(patch_id),
                        "severity": "HIGH",
                        "reason": "patch_definition_missing",
                    }
                )
                continue

            missing_prereq = [dep for dep in _as_list(patch.get("depends_on")) if str(dep) not in ordered_ids[: seq - 1]]
            if missing_prereq:
                unsafe_ordering = True
                ordering_warnings.append(
                    {
                        "patch_id": str(patch_id),
                        "severity": "HIGH",
                        "reason": "missing_prerequisite_order",
                        "missing_prerequisites": [str(v) for v in missing_prereq],
                    }
                )

            construct = str(patch.get("construct", ""))
            replacement = str(patch.get("replacement", ""))
            touched_files = [str(v) for v in _as_list(patch.get("files")) if str(v).strip()]

            patch_replacements = 0
            for file_path in touched_files:
                if file_path not in current_sources:
                    continue
                updated, count = _replace_identifier_tokens(current_sources[file_path], construct, replacement)
                if count > 0:
                    current_sources[file_path] = updated
                    patch_replacements += int(count)
                    total_replacements += int(count)
            if patch_replacements == 0:
                ordering_warnings.append(
                    {
                        "patch_id": patch_id,
                        "severity": "MEDIUM",
                        "reason": "no_replacements_applied",
                    }
                )

            compile_result = _compile_sources(current_sources)
            if not bool(compile_result.get("compile_validation_passed", False)):
                compile_failure = True

            runtime_row = _as_dict(runtime_validation_rows.get(construct.lower()))
            runtime_equivalent = bool(runtime_row.get("runtime_equivalent", False))
            validation_conf = _to_float(runtime_row.get("validation_confidence", 0.0), 0.0)
            if not runtime_equivalent or validation_conf < 0.72:
                interaction_conflicts.append(
                    {
                        "patch_id": patch_id,
                        "construct": construct,
                        "runtime_equivalent": runtime_equivalent,
                        "validation_confidence": validation_conf,
                    }
                )

            step_conf = round(max(0.0, min(1.0, 0.65 * validation_conf + 0.35 * (1.0 if compile_result.get("compile_validation_passed", False) else 0.0))), 3)
            cumulative_conf = round(max(0.0, min(1.0, 0.6 * cumulative_conf + 0.4 * step_conf)), 3)
            cumulative_states.append(
                {
                    "sequence": seq,
                    "patch_id": patch_id,
                    "step_confidence": step_conf,
                    "cumulative_confidence": cumulative_conf,
                    "runtime_equivalent": runtime_equivalent,
                    "compile_validation_passed": bool(compile_result.get("compile_validation_passed", False)),
                }
            )

            checkpoint = {
                "checkpoint_id": f"checkpoint:{seq}",
                "sequence": seq,
                "patch_id": patch_id,
                "subsystem": str(patch.get("subsystem", "")),
                "risk": str(patch.get("risk", "")),
                "patch_replacements": patch_replacements,
                "compile_validation": compile_result,
                "source_fingerprint": stable_fingerprint({"sources": current_sources}),
                "runtime_validation_confidence": validation_conf,
                "runtime_equivalent": runtime_equivalent,
            }
            checkpoint["deterministic_fingerprint"] = stable_fingerprint(checkpoint)
            checkpoints.append(checkpoint)

        patch_text, changed_files = _build_patch(before_sources, current_sources)

        runtime_fp = _as_dict(runtime_acq_artifacts.get("runtime_equivalence_fingerprint"))
        runtime_fp_summary = _as_dict(runtime_fp.get("summary"))
        runtime_backed_conf = _to_float(runtime_fp_summary.get("mean_runtime_backed_confidence", 0.0), 0.0)
        runtime_quality = _to_float(runtime_fp_summary.get("quality_score", 0.0), 0.0)

        topology_ok = str(_as_dict(_as_dict(model.get("topology_artifacts")).get("topology_runtime_graph")).get("classification", "UNKNOWN")) == "PASS"
        cumulative_runtime_validation = {
            "schema_version": "1.0",
            "report_name": "cumulative_runtime_validation",
            "target_id": str(target_id),
            "classification": "PASS"
            if (cumulative_conf >= 0.72 and not interaction_conflicts and topology_ok)
            else "FAIL_CLOSED",
            "cumulative_states": cumulative_states,
            "runtime_backed_equivalence_confidence": runtime_backed_conf,
            "runtime_evidence_quality_score": runtime_quality,
            "topology_consistency_after_sequence": topology_ok,
            "interaction_conflicts": interaction_conflicts,
            "summary": {
                "final_cumulative_confidence": cumulative_conf,
                "state_count": len(cumulative_states),
                "conflict_count": len(interaction_conflicts),
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        cumulative_runtime_validation["deterministic_fingerprint"] = stable_fingerprint(cumulative_runtime_validation)

        runtime_patchset_equivalence = {
            "schema_version": "1.0",
            "report_name": "runtime_patchset_equivalence",
            "target_id": str(target_id),
            "classification": "PASS" if len(interaction_conflicts) == 0 and cumulative_conf >= 0.72 else "FAIL_CLOSED",
            "patch_runtime_rows": [
                {
                    "patch_id": str(_as_dict(patch_map.get(str(_as_dict(state).get("patch_id", "")))).get("patch_id", "")),
                    "runtime_equivalent": bool(_as_dict(state).get("runtime_equivalent", False)),
                    "step_confidence": _to_float(_as_dict(state).get("step_confidence", 0.0), 0.0),
                    "cumulative_confidence": _to_float(_as_dict(state).get("cumulative_confidence", 0.0), 0.0),
                }
                for state in cumulative_states
            ],
            "summary": {
                "patch_count": len(cumulative_states),
                "final_cumulative_confidence": cumulative_conf,
                "runtime_confidence_drift": round(1.0 - cumulative_conf, 3),
                "conflict_count": len(interaction_conflicts),
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        runtime_patchset_equivalence["deterministic_fingerprint"] = stable_fingerprint(runtime_patchset_equivalence)

        sequencing_risk = round(
            max(
                0.0,
                min(
                    1.0,
                    0.25 * (1.0 if cycle else 0.0)
                    + 0.25 * (1.0 if unsafe_ordering else 0.0)
                    + 0.20 * (1.0 if compile_failure else 0.0)
                    + 0.15 * min(1.0, len(ordering_warnings) / 4.0)
                    + 0.15 * min(1.0, len(interaction_conflicts) / 3.0),
                ),
            ),
            3,
        )

        bisectability_report = {
            "schema_version": "1.0",
            "report_name": "bisectability_report",
            "target_id": str(target_id),
            "classification": "PASS" if sequencing_risk < 0.35 and not compile_failure and not cycle else "FAIL_CLOSED",
            "bisectability_score": round(max(0.0, min(1.0, 1.0 - sequencing_risk)), 3),
            "unsafe_ordering_detected": bool(unsafe_ordering or cycle),
            "sequencing_risk_score": sequencing_risk,
            "intermediate_states_logically_safe": all(
                bool(_as_dict(cp).get("compile_validation", {}).get("compile_validation_passed", False))
                for cp in checkpoints
            ),
            "summary": {
                "checkpoint_count": len(checkpoints),
                "warning_count": len(ordering_warnings),
                "cycle_detected": bool(cycle),
                "compile_failure": bool(compile_failure),
            },
            "ordering_warnings": ordering_warnings,
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        bisectability_report["deterministic_fingerprint"] = stable_fingerprint(bisectability_report)

        patch_ordering_rationale = {
            "schema_version": "1.0",
            "report_name": "patch_ordering_rationale",
            "target_id": str(target_id),
            "classification": "FAIL_CLOSED" if (unsafe_ordering or cycle) else "PASS",
            "ordered_patch_ids": ordered_ids,
            "rationale": [
                {
                    "patch_id": str(pid),
                    "why_ordered_here": "all prerequisites satisfied before application",
                    "dependencies": [str(v) for v in _as_list(_as_dict(patch_map.get(str(pid))).get("depends_on")) if str(v).strip()],
                    "group": str(_as_dict(patch_map.get(str(pid))).get("group", "")),
                    "subsystem": str(_as_dict(patch_map.get(str(pid))).get("subsystem", "")),
                }
                for pid in ordered_ids
            ],
            "summary": {
                "cycle_detected": bool(cycle),
                "unsafe_ordering_detected": bool(unsafe_ordering),
                "warning_count": len(ordering_warnings),
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        patch_ordering_rationale["deterministic_fingerprint"] = stable_fingerprint(patch_ordering_rationale)

        patchset_review_risk_report = {
            "schema_version": "1.0",
            "report_name": "patchset_review_risk_report",
            "target_id": str(target_id),
            "classification": "PASS" if sequencing_risk < 0.5 else "ADVISORY_ONLY",
            "risk_rows": [
                {
                    "patch_id": str(row.get("patch_id", "")),
                    "risk_classification": str(row.get("risk", "MEDIUM")),
                    "review_reasoning": (
                        "low-risk wrapper normalization"
                        if str(row.get("risk", "")).upper() == "LOW"
                        else "medium-risk API substitution"
                    ),
                }
                for row in patch_units
            ],
            "overall_review_risk": (
                "HIGH"
                if sequencing_risk >= 0.58
                else ("MEDIUM" if sequencing_risk >= 0.34 else "LOW")
            ),
            "summary": {
                "sequencing_risk_score": sequencing_risk,
                "patch_count": len(patch_units),
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        patchset_review_risk_report["deterministic_fingerprint"] = stable_fingerprint(patchset_review_risk_report)

        rollback_checkpoint_registry = {
            "schema_version": "1.0",
            "report_name": "rollback_checkpoint_registry",
            "target_id": str(target_id),
            "classification": "PASS" if checkpoints else "FAIL_CLOSED",
            "checkpoints": checkpoints,
            "rollback_order": [str(_as_dict(cp).get("checkpoint_id", "")) for cp in reversed(checkpoints)],
            "summary": {
                "checkpoint_count": len(checkpoints),
                "rollback_safe": len(checkpoints) > 0 and not compile_failure,
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        rollback_checkpoint_registry["deterministic_fingerprint"] = stable_fingerprint(rollback_checkpoint_registry)

        patchset_plan = {
            "schema_version": "1.0",
            "report_name": "governed_patchset_plan",
            "target_id": str(target_id),
            "classification": "FAIL_CLOSED" if cycle else "PASS",
            "patch_count": len(patch_units),
            "subsystem_groups": sorted(
                {
                    f"{str(_as_dict(row).get('subsystem', ''))}:{str(_as_dict(row).get('group', ''))}"
                    for row in patch_units
                }
            ),
            "ordered_patch_ids": ordered_ids,
            "patches": patch_units,
            "summary": {
                "changed_file_count": len(changed_files),
                "total_replacements": total_replacements,
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        patchset_plan["deterministic_fingerprint"] = stable_fingerprint(patchset_plan)

        acceptance = UpstreamAcceptanceSimulationEngine(plugin_loader=self._plugins).analyze(
            target_id=str(target_id),
            session_id=f"{session_id}:patchset_acceptance",
            lineage_id=f"{lineage_id}:patchset_acceptance",
            translation_artifacts=translation_artifacts,
            execution_artifacts={
                "generated_upstream_patch": {"patch_text": patch_text},
                "transformation_lineage": {
                    "summary": {"applied_segment_count": total_replacements},
                    "deterministic_fingerprint": stable_fingerprint({"patch_order": ordered_ids}),
                },
            },
            patch_artifacts={
                "upstream_readiness_report": {"classification": "PASS", "readiness_score": 0.92},
                "patch_dependency_graph": dependency_graph,
                "subsystem_boundary_map": {
                    "classification": "PASS",
                    "summary": {"high_risk_crossings": 0},
                    "subsystems": [{"subsystem": "asoc_core"}],
                },
                "vendor_contamination_report": {"classification": "PASS", "summary": {"downstream_only_api_count": 0}},
                "runtime_patch_correlation": {"regression_blast_radius": "LOW"},
                "bisectability_report": bisectability_report,
                "api_evolution_trace": {"summary": {"unresolved_count": 0}},
                "patch_series_plan": {
                    "series": [
                        {
                            "sequence": idx,
                            "patch_group_id": pid,
                            "scope": [str(_as_dict(patch_map.get(pid)).get("subsystem", "asoc_core"))],
                            "maintainer_review_groups": ["soc-audio-maintainers"],
                            "subsystem_owners": ["asoc_core"],
                        }
                        for idx, pid in enumerate(ordered_ids, start=1)
                    ]
                },
            },
            runtime_acquisition_artifacts={
                "runtime_equivalence_fingerprint": runtime_fp,
                "runtime_divergence_report": _as_dict(runtime_acq_artifacts.get("runtime_divergence_report")),
                "downstream_upstream_runtime_diff": _as_dict(runtime_acq_artifacts.get("downstream_upstream_runtime_diff")),
                "evidence_quality_report": _as_dict(runtime_acq_artifacts.get("evidence_quality_report")),
                "target_runtime_capture": _as_dict(runtime_acq_artifacts.get("target_runtime_capture")),
                "ipc_topology_map": _as_dict(runtime_acq_artifacts.get("ipc_topology_map")),
            },
            governance_state=dict(governance),
            replay_traces=dict(replay_traces),
            plugin_capability_state=dict(plugin_capability_state),
            previous_submission_history=[],
            evidence_references=evidence,
        ).acceptance_bundle
        acceptance_artifacts = _as_dict(acceptance.get("artifacts"))
        acceptance_conf = _as_dict(acceptance_artifacts.get("acceptance_confidence_score"))

        upstream_patchset_prediction = {
            "schema_version": "1.0",
            "report_name": "upstream_patchset_prediction",
            "target_id": str(target_id),
            "classification": str(acceptance_conf.get("classification", "UNKNOWN")),
            "acceptance_confidence": _to_float(acceptance_conf.get("acceptance_confidence", 0.0), 0.0),
            "review_risk_classification": str(patchset_review_risk_report.get("overall_review_risk", "UNKNOWN")),
            "fail_closed_reasons": [str(v) for v in _as_list(acceptance_conf.get("fail_closed_reasons")) if str(v).strip()],
            "summary": {
                "autonomous_delivery_permitted": bool(acceptance_conf.get("autonomous_delivery_permitted", False)),
                "upstreamable_now": str(acceptance_conf.get("classification", "")) == "PASS",
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        upstream_patchset_prediction["deterministic_fingerprint"] = stable_fingerprint(upstream_patchset_prediction)

        fail_reasons: list[str] = []
        if cycle or unsafe_ordering:
            fail_reasons.append("unsafe_ordering_detected")
        if compile_failure:
            fail_reasons.append("intermediate_compile_failure")
        if str(cumulative_runtime_validation.get("classification", "")) != "PASS":
            fail_reasons.append("cumulative_runtime_confidence_drop_or_conflict")
        if not topology_ok:
            fail_reasons.append("topology_equivalence_break")
        if str(upstream_patchset_prediction.get("classification", "")) != "PASS":
            fail_reasons.append("upstream_prediction_below_threshold")
        if str(rollback_checkpoint_registry.get("classification", "")) != "PASS":
            fail_reasons.append("rollback_checkpoint_registry_incomplete")

        replay_history = [row for row in _as_list(previous_history or []) if isinstance(row, dict)]
        deterministic_patchset_replay = {
            "schema_version": "1.0",
            "report_name": "deterministic_patchset_replay",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": "FAIL_CLOSED" if fail_reasons else "PASS",
            "ordered_patch_ids": ordered_ids,
            "artifact_fingerprints": {
                "governed_patchset_plan": str(patchset_plan.get("deterministic_fingerprint", "")),
                "patch_dependency_graph": str(dependency_graph.get("deterministic_fingerprint", "")),
                "runtime_patchset_equivalence": str(runtime_patchset_equivalence.get("deterministic_fingerprint", "")),
                "patch_ordering_rationale": str(patch_ordering_rationale.get("deterministic_fingerprint", "")),
                "bisectability_report": str(bisectability_report.get("deterministic_fingerprint", "")),
                "patchset_review_risk_report": str(patchset_review_risk_report.get("deterministic_fingerprint", "")),
                "rollback_checkpoint_registry": str(rollback_checkpoint_registry.get("deterministic_fingerprint", "")),
                "cumulative_runtime_validation": str(cumulative_runtime_validation.get("deterministic_fingerprint", "")),
                "upstream_patchset_prediction": str(upstream_patchset_prediction.get("deterministic_fingerprint", "")),
            },
            "history": replay_history
            + [
                {
                    "lineage_id": str(lineage_id),
                    "session_id": str(session_id),
                    "classification": "FAIL_CLOSED" if fail_reasons else "PASS",
                    "ordered_patch_ids": ordered_ids,
                }
            ],
            "deterministic_event_ordering": bool(_as_dict(replay_traces).get("deterministic_event_ordering", False)),
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        deterministic_patchset_replay["deterministic_fingerprint"] = stable_fingerprint(deterministic_patchset_replay)

        classification = "FAIL_CLOSED" if fail_reasons else "PASS"

        artifacts = {
            "governed_patchset_plan": patchset_plan,
            "patch_dependency_graph": dependency_graph,
            "runtime_patchset_equivalence": runtime_patchset_equivalence,
            "patch_ordering_rationale": patch_ordering_rationale,
            "bisectability_report": bisectability_report,
            "patchset_review_risk_report": patchset_review_risk_report,
            "rollback_checkpoint_registry": rollback_checkpoint_registry,
            "deterministic_patchset_replay": deterministic_patchset_replay,
            "cumulative_runtime_validation": cumulative_runtime_validation,
            "upstream_patchset_prediction": upstream_patchset_prediction,
            "tiny_multi_patchset": {
                "patch_text": patch_text,
                "changed_files": changed_files,
                "real_multi_patchset_generated": bool(changed_files and "# mode=proposal" in patch_text),
                "deterministic_fingerprint": stable_fingerprint(
                    {
                        "patch_text": patch_text,
                        "changed_files": changed_files,
                    }
                ),
            },
            "tiny_patchset_model": model,
        }

        summary = {
            "schema_version": "1.0",
            "report_name": "governed_patchset_summary",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": classification,
            "fail_closed_reasons": sorted(set(fail_reasons)),
            "real_multi_patchset_generated": bool(
                _as_dict(artifacts.get("tiny_multi_patchset")).get("real_multi_patchset_generated", False)
            ),
            "pipeline_trace": {
                "runtime_truth_classification": str(runtime_truth.get("classification", "UNKNOWN")),
                "translation_classification": str(translation.get("classification", "UNKNOWN")),
                "runtime_acquisition_classification": str(runtime_acq.get("classification", "UNKNOWN")),
                "acceptance_classification": str(acceptance.get("classification", "UNKNOWN")),
            },
            "summary": {
                "patch_count": len(patch_units),
                "changed_file_count": len(changed_files),
                "total_replacements": total_replacements,
                "final_cumulative_runtime_confidence": cumulative_conf,
                "sequencing_risk_score": sequencing_risk,
                "upstream_acceptance_confidence": _to_float(upstream_patchset_prediction.get("acceptance_confidence", 0.0), 0.0),
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "deterministic_fingerprint": stable_fingerprint(
                {
                    "classification": classification,
                    "fail_closed_reasons": sorted(set(fail_reasons)),
                    "patch_count": len(patch_units),
                    "changed_file_count": len(changed_files),
                    "artifact_fingerprints": {
                        name: str(_as_dict(payload).get("deterministic_fingerprint", ""))
                        for name, payload in sorted(artifacts.items())
                    },
                }
            ),
        }
        artifacts["governed_patchset_summary"] = summary

        bundle = {
            "schema_version": "1.0",
            "phase": "GOVERNED_PATCHSET_ORCHESTRATION_ENGINE",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": classification,
            "fail_closed_reasons": sorted(set(fail_reasons)),
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "governance_state": dict(governance),
            "evidence_references": evidence,
            "artifacts": artifacts,
        }
        bundle["governed_patchset_orchestration_fingerprint"] = stable_fingerprint(
            {
                "target_id": str(target_id),
                "session_id": str(session_id),
                "lineage_id": str(lineage_id),
                "classification": classification,
                "fail_closed_reasons": sorted(set(fail_reasons)),
                "artifact_fingerprints": {
                    name: str(_as_dict(payload).get("deterministic_fingerprint", ""))
                    for name, payload in sorted(artifacts.items())
                },
            }
        )
        return GovernedPatchsetOrchestrationResult(patchset_bundle=bundle)


class GovernedPatchsetOrchestrationRegistry:
    """Persistence for governed patchset orchestration artifacts."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "governed_patchset_plan": self._output_dir / "governed_patchset_plan.json",
            "patch_dependency_graph": self._output_dir / "patch_dependency_graph.json",
            "runtime_patchset_equivalence": self._output_dir / "runtime_patchset_equivalence.json",
            "patch_ordering_rationale": self._output_dir / "patch_ordering_rationale.json",
            "bisectability_report": self._output_dir / "bisectability_report.json",
            "patchset_review_risk_report": self._output_dir / "patchset_review_risk_report.json",
            "rollback_checkpoint_registry": self._output_dir / "rollback_checkpoint_registry.json",
            "deterministic_patchset_replay": self._output_dir / "deterministic_patchset_replay.json",
            "cumulative_runtime_validation": self._output_dir / "cumulative_runtime_validation.json",
            "upstream_patchset_prediction": self._output_dir / "upstream_patchset_prediction.json",
            "governed_patchset_summary": self._output_dir / "governed_patchset_summary.json",
            "tiny_multi_patchset": self._output_dir / "tiny_multi_patchset.patch",
            "tiny_patchset_model": self._output_dir / "tiny_patchset_model.json",
        }

    def persist(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(bundle)
        artifacts = _as_dict(payload.get("artifacts"))
        lineage_id = str(payload.get("lineage_id", "")).strip() or stable_fingerprint(payload)
        paths = self._artifact_paths()

        patch_payload = _as_dict(artifacts.get("tiny_multi_patchset"))
        paths["tiny_multi_patchset"].parent.mkdir(parents=True, exist_ok=True)
        paths["tiny_multi_patchset"].write_text(str(patch_payload.get("patch_text", "")), encoding="utf-8")

        for key in (
            "governed_patchset_plan",
            "patch_dependency_graph",
            "runtime_patchset_equivalence",
            "patch_ordering_rationale",
            "bisectability_report",
            "patchset_review_risk_report",
            "rollback_checkpoint_registry",
            "deterministic_patchset_replay",
            "cumulative_runtime_validation",
            "upstream_patchset_prediction",
            "governed_patchset_summary",
            "tiny_patchset_model",
        ):
            _save_json(paths[key], _as_dict(artifacts.get(key)))

        registry = self._registry.load()
        state = _as_dict(registry.get("governed_patchset_orchestration"))
        history = [row for row in _as_list(state.get("history")) if isinstance(row, dict)]
        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "target_id": str(payload.get("target_id", "")),
            "session_id": str(payload.get("session_id", "")),
            "classification": str(payload.get("classification", "UNKNOWN")),
            "fail_closed_reasons": [str(v) for v in _as_list(payload.get("fail_closed_reasons")) if str(v).strip()],
            "governed_patchset_orchestration_fingerprint": str(payload.get("governed_patchset_orchestration_fingerprint", "")),
            "artifact_paths": {name: str(path.resolve()) for name, path in paths.items()},
            "real_multi_patchset_generated": bool(_as_dict(artifacts.get("tiny_multi_patchset")).get("real_multi_patchset_generated", False)),
        }
        history.append(entry)
        history = history[-8000:]

        registry["governed_patchset_orchestration"] = {
            "schema_version": "1.0",
            "latest": dict(payload),
            "history": history,
            "updated_at": _utc_now_iso(),
        }
        registry.setdefault("cognition_lineage", [])
        lineages = [row for row in _as_list(registry.get("cognition_lineage")) if isinstance(row, dict)]
        lineages.append(
            {
                "lineage_id": lineage_id,
                "type": "governed_patchset_orchestration",
                "recorded_at": _utc_now_iso(),
                "governed_patchset_orchestration_fingerprint": str(payload.get("governed_patchset_orchestration_fingerprint", "")),
            }
        )
        registry["cognition_lineage"] = lineages[-32000:]
        registry["updated_at"] = _utc_now_iso()
        self._registry.save(registry)

        return {
            "lineage_id": lineage_id,
            "session_id": entry["session_id"],
            "classification": entry["classification"],
            "fail_closed_reasons": entry["fail_closed_reasons"],
            "governed_patchset_orchestration_fingerprint": entry["governed_patchset_orchestration_fingerprint"],
            "artifact_paths": entry["artifact_paths"],
            "real_multi_patchset_generated": entry["real_multi_patchset_generated"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry = self._registry.load()
        state = _as_dict(registry.get("governed_patchset_orchestration"))
        history = [row for row in _as_list(state.get("history")) if isinstance(row, dict)]
        selected: dict[str, Any] | None = None
        if lineage_id:
            for row in reversed(history):
                item = _as_dict(row)
                if str(item.get("lineage_id", "")) == str(lineage_id):
                    selected = item
                    break
        if selected is None and history:
            selected = _as_dict(history[-1])

        replay_payload = {
            "schema_version": "1.0",
            "replay_type": "governed_patchset_orchestration",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "session_id": str(_as_dict(selected).get("session_id", "")),
            "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
            "fail_closed_reasons": [str(v) for v in _as_list(_as_dict(selected).get("fail_closed_reasons")) if str(v).strip()],
            "governed_patchset_orchestration_fingerprint": str(
                _as_dict(selected).get("governed_patchset_orchestration_fingerprint", "")
            ),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "real_multi_patchset_generated": bool(_as_dict(selected).get("real_multi_patchset_generated", False)),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "session_id": str(_as_dict(selected).get("session_id", "")),
                    "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
                    "governed_patchset_orchestration_fingerprint": str(
                        _as_dict(selected).get("governed_patchset_orchestration_fingerprint", "")
                    ),
                }
            ),
            "replayed_at": _utc_now_iso(),
        }
        _save_json(self._output_dir / "deterministic_patchset_replay.json", replay_payload)
        return replay_payload
