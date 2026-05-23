"""Upstream semantic matcher for real downstream kernel ingestion cognition."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


_ALLOWED_EXTENSIONS = {".c", ".h", ".dts", ".dtsi"}


@dataclass(frozen=True)
class UpstreamSemanticMatcherResult:
    upstream_equivalence_map: dict[str, Any]
    semantic_equivalence_confidence: float
    deterministic_fingerprint: str


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


def _dedupe_sorted(items: Iterable[str]) -> list[str]:
    return sorted({str(item).strip() for item in items if str(item).strip()})


def _iter_files(root: Path, max_files: int) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if len(files) >= max_files:
            break
        if not path.is_file():
            continue
        if path.suffix.lower() not in _ALLOWED_EXTENSIONS:
            continue
        files.append(path)
    files.sort(key=lambda p: str(p))
    return files


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _tokenize(text: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text)
        if len(token) <= 96
    }


def _derive_constructs(downstream_graph: Mapping[str, Any]) -> list[str]:
    graph = _as_dict(downstream_graph)
    extracted = _as_dict(graph.get("extracted"))
    dai_links = _as_dict(extracted.get("dai_links"))

    constructs: list[str] = []
    constructs.extend(str(item) for item in _as_list(extracted.get("ops_structures")))
    constructs.extend(str(item) for item in _as_list(dai_links.get("all")))
    constructs.extend(str(item) for item in _as_list(extracted.get("vendor_extensions")))
    constructs.extend(str(item) for item in _as_list(extracted.get("proprietary_runtime_hooks")))
    constructs.extend(str(item) for item in _as_list(extracted.get("routing_structures")))

    return _dedupe_sorted(constructs)


def _manual_match(construct: str, hints: Mapping[str, Any]) -> tuple[str, float]:
    hints_map = _as_dict(hints)
    exact = str(hints_map.get(construct, "")).strip()
    if exact:
        return exact, 0.88

    lower = construct.lower()
    prefix_hints = _as_dict(hints_map.get("prefix", {}))
    for key, value in prefix_hints.items():
        prefix = str(key).strip().lower()
        if prefix and lower.startswith(prefix):
            return str(value).strip(), 0.8
    return "", 0.0


def _heuristic_match(construct: str) -> tuple[str, float]:
    lower = construct.lower()

    if lower.startswith("msm_"):
        return "snd_soc_component", 0.72
    if lower.startswith("qcom_"):
        return "snd_soc_qcom", 0.7
    if "snd_soc" in lower:
        return "snd_soc", 0.85
    if "dpcm" in lower or "_be_" in lower or "_fe_" in lower:
        return "snd_soc_dpcm", 0.76
    if "dapm" in lower or "route" in lower:
        return "snd_soc_dapm", 0.74
    if "soundwire" in lower or lower.startswith("swr_") or lower.startswith("sdw_"):
        return "soundwire", 0.8
    if "pcm" in lower:
        return "snd_pcm", 0.68
    if lower.startswith("wcd"):
        return "wcd93xx", 0.58
    if lower.startswith("apr_") or lower.startswith("gpr_"):
        return "mailbox_or_soundwire_control", 0.42
    return "UNRESOLVED", 0.2


def _candidate_presence(candidate: str, token_index: set[str], path_index: list[str]) -> tuple[bool, list[str]]:
    token = str(candidate).strip().lower()
    if not token or token == "unresolved":
        return False, []

    terms = [part for part in re.split(r"[^a-z0-9_]+", token) if part]
    if not terms:
        return False, []

    matched_terms = [term for term in terms if term in token_index]
    matched = bool(matched_terms)

    matched_paths: list[str] = []
    if matched:
        for path in path_index:
            lower = path.lower()
            if any(term in lower for term in matched_terms[:3]):
                matched_paths.append(path)
            if len(matched_paths) >= 5:
                break

    return matched, matched_paths


def match_upstream_semantics(
    *,
    target_id: str,
    upstream_root: str | Path,
    downstream_driver_graph: Mapping[str, Any],
    adapter_payload: Mapping[str, Any] | None,
    evidence_references: list[str] | None,
    max_upstream_files: int = 5000,
) -> UpstreamSemanticMatcherResult:
    adapter = _as_dict(adapter_payload)
    root = Path(upstream_root)
    evidence = [str(item) for item in (evidence_references or []) if str(item).strip()]

    if not root.exists() or not root.is_dir():
        payload = {
            "schema_version": "1.0",
            "graph_name": "upstream_equivalence_map",
            "target_id": str(target_id),
            "upstream_root": str(root),
            "classification": "FAIL_CLOSED_NO_UPSTREAM_REFERENCE",
            "entries": [],
            "semantic_equivalence_confidence": 0.0,
            "evidence_references": evidence,
        }
        payload["deterministic_fingerprint"] = stable_fingerprint(payload)
        return UpstreamSemanticMatcherResult(
            upstream_equivalence_map=payload,
            semantic_equivalence_confidence=0.0,
            deterministic_fingerprint=str(payload["deterministic_fingerprint"]),
        )

    scan_limit = int(adapter.get("max_upstream_scan_files", max_upstream_files) or max_upstream_files)
    files = _iter_files(root, max_files=max(1, scan_limit))

    token_index: set[str] = set()
    path_index: list[str] = []
    for path in files:
        text = _read_text(path)
        if not text:
            continue
        token_index.update(_tokenize(text))
        path_index.append(str(path.relative_to(root)))

    constructs = _derive_constructs(downstream_driver_graph)
    mapping_hints = _as_dict(adapter.get("upstream_equivalent_hints"))
    confidence_hints = _as_dict(adapter.get("equivalence_confidence_hints"))

    entries: list[dict[str, Any]] = []
    exact = 0
    partial = 0

    for construct in constructs:
        manual_candidate, manual_conf = _manual_match(construct, mapping_hints)
        if manual_candidate:
            candidate = manual_candidate
            base_conf = manual_conf
            reasoning = "plugin_hint"
        else:
            candidate, base_conf = _heuristic_match(construct)
            reasoning = "heuristic"

        hinted = _to_float(confidence_hints.get(construct, 0.0))
        if hinted > 0.0:
            base_conf = max(base_conf, min(1.0, hinted))

        matched, matched_paths = _candidate_presence(candidate, token_index, path_index)

        if candidate == "UNRESOLVED":
            status = "UNRESOLVED"
            confidence = 0.2
        elif matched:
            status = "EXACT" if base_conf >= 0.7 else "PARTIAL"
            confidence = min(1.0, base_conf + 0.1)
        else:
            status = "PARTIAL"
            confidence = min(0.69, base_conf)

        if status == "EXACT":
            exact += 1
        elif status == "PARTIAL":
            partial += 1

        entries.append(
            {
                "downstream_construct": construct,
                "upstream_equivalent": candidate,
                "equivalence_status": status,
                "equivalence_confidence": round(confidence, 3),
                "reasoning": reasoning,
                "evidence_paths": matched_paths,
            }
        )

    unresolved = sum(1 for row in entries if str(row.get("equivalence_status", "")) == "UNRESOLVED")
    confidence = 0.0
    if entries:
        confidence = round(
            sum(float(row.get("equivalence_confidence", 0.0)) for row in entries) / len(entries),
            3,
        )

    coverage = {
        "alsa": bool("snd_pcm" in token_index),
        "asoc": bool("snd_soc" in token_index),
        "dapm": bool("snd_soc_dapm" in token_index or "dapm" in token_index),
        "soundwire": bool("soundwire" in token_index or "sdw" in token_index),
        "generic_linux_abstractions": bool("platform_device" in token_index and "devm_kzalloc" in token_index),
    }

    payload = {
        "schema_version": "1.0",
        "graph_name": "upstream_equivalence_map",
        "target_id": str(target_id),
        "upstream_root": str(root.resolve()),
        "classification": "PASS" if confidence >= 0.55 else "ADVISORY_ONLY",
        "semantic_equivalence_confidence": confidence,
        "summary": {
            "constructs_evaluated": len(entries),
            "exact_matches": exact,
            "partial_matches": partial,
            "unresolved": unresolved,
            "upstream_coverage": coverage,
            "scanned_files": len(files),
        },
        "entries": entries,
        "evidence_references": evidence,
    }

    fingerprint = stable_fingerprint(
        {
            "target_id": str(target_id),
            "upstream_root": payload["upstream_root"],
            "entries": entries,
            "summary": payload["summary"],
            "classification": payload["classification"],
        }
    )
    payload["deterministic_fingerprint"] = fingerprint

    return UpstreamSemanticMatcherResult(
        upstream_equivalence_map=payload,
        semantic_equivalence_confidence=confidence,
        deterministic_fingerprint=fingerprint,
    )
