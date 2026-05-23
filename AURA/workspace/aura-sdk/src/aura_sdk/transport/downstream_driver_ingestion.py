"""Real downstream kernel driver ingestion cognition.

Parses downstream kernel driver trees and extracts machine-readable audio
cognition signals for deterministic, governance-safe conversion reasoning.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


_ALLOWED_EXTENSIONS = {".c", ".h", ".dts", ".dtsi"}
_IGNORED_DIR_NAMES = {".git", ".repo", "out", "build", "Documentation"}

_OPS_RE = re.compile(r"\b(?:const\s+)?struct\s+snd_soc_ops\s+([A-Za-z_][A-Za-z0-9_]*)")
_DAI_LINK_RE = re.compile(r"\b(?:const\s+)?struct\s+snd_soc_dai_link\s+([A-Za-z_][A-Za-z0-9_]*)")
_DAPM_ROUTE_RE = re.compile(r"\b(?:const\s+)?struct\s+snd_soc_dapm_route\s+([A-Za-z_][A-Za-z0-9_]*)")
_PCM_STRING_RE = re.compile(r'"([^"\n]*(?:PCM|MultiMedia|Playback|Capture)[^"\n]*)"')
_VENDOR_TOKEN_RE = re.compile(
    r"\b(?:msm_[A-Za-z0-9_]+|qcom_[A-Za-z0-9_]+|wcd[A-Za-z0-9_]*|lpass_[A-Za-z0-9_]+|"
    r"bolero_[A-Za-z0-9_]+|swr_[A-Za-z0-9_]+|q6_[A-Za-z0-9_]+|spf_[A-Za-z0-9_]+)\b"
)
_PROPRIETARY_HOOK_RE = re.compile(
    r"\b(?:vendor_hook_[A-Za-z0-9_]+|msm_audio_[A-Za-z0-9_]+|qcom_snd_[A-Za-z0-9_]+|"
    r"apr_[A-Za-z0-9_]+|gpr_[A-Za-z0-9_]+|audio_prm_[A-Za-z0-9_]+)\b"
)


@dataclass(frozen=True)
class DownstreamDriverIngestionResult:
    downstream_driver_graph: dict[str, Any]
    ingestion_confidence: float
    deterministic_fingerprint: str


@dataclass(frozen=True)
class _ScanExtraction:
    ops_structures: list[str]
    dai_links: list[str]
    routing_structures: list[str]
    pcm_paths: list[str]
    vendor_extensions: list[str]
    proprietary_runtime_hooks: list[str]
    dependency_clocks: bool
    dependency_regulators: bool
    dependency_gpios: bool
    dependency_soundwire: bool
    timing_dependencies: bool


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _dedupe_sorted(items: Iterable[str]) -> list[str]:
    return sorted({str(item).strip() for item in items if str(item).strip()})


def _iter_source_files(root: Path, max_files: int) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if len(files) >= max_files:
            break
        if not path.is_file():
            continue
        if path.suffix.lower() not in _ALLOWED_EXTENSIONS:
            continue
        if any(part in _IGNORED_DIR_NAMES for part in path.parts):
            continue
        files.append(path)
    files.sort(key=lambda p: str(p))
    return files


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _extract_from_text(text: str) -> _ScanExtraction:
    lower = text.lower()

    ops_structures = [str(item) for item in _OPS_RE.findall(text)]
    dai_links = [str(item) for item in _DAI_LINK_RE.findall(text)]
    routing_structures = [str(item) for item in _DAPM_ROUTE_RE.findall(text)]
    pcm_paths = [str(item).strip() for item in _PCM_STRING_RE.findall(text) if str(item).strip()]
    vendor_extensions = [str(item) for item in _VENDOR_TOKEN_RE.findall(text)]
    proprietary_runtime_hooks = [str(item) for item in _PROPRIETARY_HOOK_RE.findall(text)]

    dependency_clocks = bool(
        any(token in lower for token in ("devm_clk_get", "clk_get", "clk_prepare_enable", "clock-names", "clocks"))
    )
    dependency_regulators = bool(
        any(
            token in lower
            for token in ("devm_regulator_get", "regulator_get", "regulator_enable", "regulator_disable", "regulator-")
        )
    )
    dependency_gpios = bool(
        any(token in lower for token in ("gpiod_get", "gpio_request", "gpio_set_value", "gpio_direction", "gpios"))
    )
    dependency_soundwire = bool(any(token in lower for token in ("soundwire", "swr_", "sdw_")))
    timing_dependencies = bool(any(token in lower for token in ("msleep", "usleep", "udelay", "mdelay")))

    return _ScanExtraction(
        ops_structures=ops_structures,
        dai_links=dai_links,
        routing_structures=routing_structures,
        pcm_paths=pcm_paths,
        vendor_extensions=vendor_extensions,
        proprietary_runtime_hooks=proprietary_runtime_hooks,
        dependency_clocks=dependency_clocks,
        dependency_regulators=dependency_regulators,
        dependency_gpios=dependency_gpios,
        dependency_soundwire=dependency_soundwire,
        timing_dependencies=timing_dependencies,
    )


def _split_fe_be(dai_links: list[str]) -> tuple[list[str], list[str]]:
    fe: list[str] = []
    be: list[str] = []
    for name in dai_links:
        token = str(name).strip().lower()
        if not token:
            continue
        if "_fe_" in token or token.endswith("_fe_dai_links") or token.endswith("_fe_links"):
            fe.append(name)
            continue
        if "_be_" in token or token.endswith("_be_dai_links") or token.endswith("_be_links"):
            be.append(name)
            continue
        if "frontend" in token:
            fe.append(name)
        elif "backend" in token:
            be.append(name)
    return _dedupe_sorted(fe), _dedupe_sorted(be)


def _name_tokens(name: str) -> set[str]:
    filtered = {
        item
        for item in re.split(r"[^a-z0-9]+", str(name).lower())
        if item
        and item
        not in {
            "msm",
            "audio",
            "common",
            "dai",
            "links",
            "link",
            "be",
            "fe",
            "tx",
            "rx",
        }
    }
    return filtered


def _infer_fe_be_links(fe_links: list[str], be_links: list[str]) -> list[dict[str, Any]]:
    if not fe_links or not be_links:
        return []
    inferred: list[dict[str, Any]] = []
    be_sorted = sorted(be_links)
    for fe in sorted(fe_links):
        fe_tokens = _name_tokens(fe)
        matches = [be for be in be_sorted if fe_tokens.intersection(_name_tokens(be))]
        if not matches:
            matches = be_sorted[:1]
        inferred.append(
            {
                "frontend": fe,
                "backend_candidates": matches[:3],
                "confidence": 0.8 if fe_tokens and matches and matches[0] in be_sorted else 0.5,
            }
        )
    return inferred


def ingest_downstream_driver_tree(
    *,
    target_id: str,
    downstream_root: str | Path,
    adapter_payload: Mapping[str, Any] | None,
    evidence_references: list[str] | None,
    max_files: int = 5000,
) -> DownstreamDriverIngestionResult:
    adapter = _as_dict(adapter_payload)
    source_root = Path(downstream_root)

    if not source_root.exists() or not source_root.is_dir():
        graph = {
            "schema_version": "1.0",
            "graph_name": "downstream_driver_graph",
            "target_id": str(target_id),
            "downstream_root": str(source_root),
            "classification": "FAIL_CLOSED_NO_SOURCE",
            "reason": "downstream_root_missing_or_invalid",
            "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
        }
        graph["deterministic_fingerprint"] = stable_fingerprint(graph)
        return DownstreamDriverIngestionResult(
            downstream_driver_graph=graph,
            ingestion_confidence=0.0,
            deterministic_fingerprint=str(graph["deterministic_fingerprint"]),
        )

    max_scan = int(adapter.get("max_ingestion_files", max_files) or max_files)
    files = _iter_source_files(source_root, max_files=max(1, max_scan))

    all_ops: list[str] = []
    all_dai_links: list[str] = []
    all_routes: list[str] = []
    all_pcm_paths: list[str] = []
    all_vendor_extensions: list[str] = []
    all_hooks: list[str] = []

    dependency_clocks = False
    dependency_regulators = False
    dependency_gpios = False
    dependency_soundwire = False
    timing_dependencies = False

    scanned_file_summaries: list[dict[str, Any]] = []

    for path in files:
        text = _read_text(path)
        if not text:
            continue
        extracted = _extract_from_text(text)

        all_ops.extend(extracted.ops_structures)
        all_dai_links.extend(extracted.dai_links)
        all_routes.extend(extracted.routing_structures)
        all_pcm_paths.extend(extracted.pcm_paths)
        all_vendor_extensions.extend(extracted.vendor_extensions)
        all_hooks.extend(extracted.proprietary_runtime_hooks)

        dependency_clocks = dependency_clocks or extracted.dependency_clocks
        dependency_regulators = dependency_regulators or extracted.dependency_regulators
        dependency_gpios = dependency_gpios or extracted.dependency_gpios
        dependency_soundwire = dependency_soundwire or extracted.dependency_soundwire
        timing_dependencies = timing_dependencies or extracted.timing_dependencies

        rel = str(path.relative_to(source_root))
        file_summary = {
            "file": rel,
            "ops_structures": len(extracted.ops_structures),
            "dai_links": len(extracted.dai_links),
            "routes": len(extracted.routing_structures),
            "pcm_strings": len(extracted.pcm_paths),
            "vendor_tokens": len(extracted.vendor_extensions),
        }
        if any(file_summary[key] > 0 for key in ("ops_structures", "dai_links", "routes", "pcm_strings", "vendor_tokens")):
            scanned_file_summaries.append(file_summary)

    ops_structures = _dedupe_sorted(all_ops)
    dai_links = _dedupe_sorted(all_dai_links)
    routing_structures = _dedupe_sorted(all_routes)
    pcm_paths = _dedupe_sorted(all_pcm_paths)
    vendor_extensions = _dedupe_sorted(all_vendor_extensions)
    proprietary_runtime_hooks = _dedupe_sorted(all_hooks)

    fe_links, be_links = _split_fe_be(dai_links)
    inferred_links = _infer_fe_be_links(fe_links, be_links)

    confidence = 0.0
    confidence += 0.2 if ops_structures else 0.0
    confidence += 0.2 if dai_links else 0.0
    confidence += 0.15 if routing_structures else 0.0
    confidence += 0.15 if fe_links and be_links else 0.0
    confidence += 0.1 if vendor_extensions else 0.0
    confidence += 0.1 if proprietary_runtime_hooks else 0.0
    confidence += 0.1 if any([dependency_clocks, dependency_regulators, dependency_gpios]) else 0.0
    confidence = round(min(1.0, confidence), 3)

    graph = {
        "schema_version": "1.0",
        "graph_name": "downstream_driver_graph",
        "target_id": str(target_id),
        "downstream_root": str(source_root.resolve()),
        "classification": "PASS" if confidence >= 0.45 else "ADVISORY_ONLY",
        "ingestion_confidence": confidence,
        "scanned_files": {
            "total": len(files),
            "non_empty_evidence_files": len(scanned_file_summaries),
            "sample": scanned_file_summaries[:120],
        },
        "extracted": {
            "ops_structures": ops_structures,
            "dai_links": {
                "all": dai_links,
                "frontend": fe_links,
                "backend": be_links,
                "inferred_fe_be_links": inferred_links,
            },
            "pcm_dpcm_paths": pcm_paths,
            "routing_structures": routing_structures,
            "vendor_extensions": vendor_extensions,
            "proprietary_runtime_hooks": proprietary_runtime_hooks,
            "dependencies": {
                "clocks": dependency_clocks,
                "regulators": dependency_regulators,
                "gpios": dependency_gpios,
                "soundwire": dependency_soundwire,
                "timing_dependencies": timing_dependencies,
            },
        },
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }

    fingerprint = stable_fingerprint(
        {
            "target_id": str(target_id),
            "downstream_root": graph["downstream_root"],
            "ops_structures": ops_structures,
            "dai_links": dai_links,
            "frontend": fe_links,
            "backend": be_links,
            "routing_structures": routing_structures,
            "vendor_extensions": vendor_extensions,
            "proprietary_runtime_hooks": proprietary_runtime_hooks,
            "dependencies": graph["extracted"]["dependencies"],
            "classification": graph["classification"],
        }
    )
    graph["deterministic_fingerprint"] = fingerprint

    return DownstreamDriverIngestionResult(
        downstream_driver_graph=graph,
        ingestion_confidence=confidence,
        deterministic_fingerprint=fingerprint,
    )
