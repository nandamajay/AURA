"""Semantic entity extraction for Kernel Semantic Knowledge Layer."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class SemanticEntityExtractionResult:
    semantic_entity_graph: dict[str, Any]
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _dedupe(items: list[str]) -> list[str]:
    return sorted({str(item).strip() for item in items if str(item).strip()})


def _section_text(document: Mapping[str, Any]) -> list[str]:
    sections = [item for item in _as_list(_as_dict(document).get("sections")) if isinstance(item, dict)]
    return [
        " ".join(
            [
                str(_as_dict(section).get("heading", "")),
                " ".join(str(item) for item in _as_list(_as_dict(section).get("text_chunks"))),
            ]
        ).strip()
        for section in sections
    ]


def _extract_keywords(text: str, patterns: list[str]) -> list[str]:
    lowered = str(text).lower()
    out: list[str] = []
    for pattern in patterns:
        token = str(pattern).strip()
        if not token:
            continue
        if token.lower() in lowered:
            out.append(token)
    return out


def _extract_regex(text: str, regex: str) -> list[str]:
    return [str(item).strip() for item in re.findall(regex, text) if str(item).strip()]


def _default_taxonomy() -> dict[str, list[str]]:
    return {
        "alsa_entities": [
            "ALSA",
            "pcm",
            "aplay",
            "arecord",
            "snd_pcm",
            "hw_params",
            "period_size",
            "buffer_size",
            "substream",
        ],
        "asoc_entities": [
            "ASoC",
            "snd_soc",
            "component",
            "codec",
            "cpu_dai",
            "platform_dai",
            "machine driver",
            "dai_link",
        ],
        "fe_be_topology_concepts": [
            "frontend",
            "backend",
            "FE",
            "BE",
            "dai-link",
            "multi-be",
            "audio path",
            "routing",
        ],
        "dpcm_concepts": [
            "DPCM",
            "dynamic pcm",
            "snd_soc_dpcm",
            "trigger",
            "fe be link",
            "path domain",
        ],
        "dapm_graph_semantics": [
            "DAPM",
            "widget",
            "route",
            "mixer",
            "mux",
            "kcontrol",
            "power event",
        ],
        "pcm_lifecycle_semantics": [
            "open",
            "hw_params",
            "prepare",
            "trigger",
            "pointer",
            "close",
            "drain",
            "xrun",
        ],
        "soundwire_concepts": [
            "SoundWire",
            "soundwire",
            "sdw",
            "swr",
            "master",
            "slave",
            "stream",
        ],
        "qcom_downstream_abstractions": [
            "msm_",
            "qcom_",
            "lpass",
            "bolero",
            "wcd",
            "q6_",
            "apr_",
            "gpr_",
        ],
        "upstream_equivalence_mappings": [
            "snd_soc_component",
            "snd_soc_dai_link",
            "snd_soc_dapm_route",
            "snd_pcm",
            "soundwire",
        ],
        "runtime_lifecycle_relationships": [
            "init",
            "probe",
            "bind",
            "start",
            "stop",
            "suspend",
            "resume",
            "shutdown",
        ],
        "known_portability_blockers": [
            "downstream only",
            "vendor hook",
            "wrapper",
            "non-upstream",
            "proprietary",
            "timing dependency",
            "autonomous mutation forbidden",
        ],
        "migration_equivalence_rules": [
            "equivalence",
            "mapping",
            "translate",
            "normalize",
            "compatible",
            "upstream",
            "downstream",
        ],
        "vendor_workaround_patterns": [
            "workaround",
            "quirk",
            "fallback",
            "special case",
            "compat mode",
            "vendor path",
        ],
        "kernel_subsystem_vocabulary_graph": [
            "driver",
            "topology",
            "runtime",
            "regression",
            "governance",
            "replay",
            "lineage",
            "portability",
            "migration",
        ],
    }


def extract_semantic_entities(
    *,
    source_id: str,
    source_version: str,
    parsed_document: Mapping[str, Any],
    adapter_payload: Mapping[str, Any] | None,
) -> SemanticEntityExtractionResult:
    adapter = _as_dict(adapter_payload)

    taxonomy = _default_taxonomy()
    overrides = _as_dict(adapter.get("taxonomy_overrides"))
    for key, value in overrides.items():
        if key in taxonomy and isinstance(value, list):
            taxonomy[key] = _dedupe([str(item) for item in taxonomy[key]] + [str(item) for item in value])

    section_text = _section_text(parsed_document)
    all_text = "\n".join(section_text)

    entities: dict[str, list[str]] = {}
    for category, patterns in taxonomy.items():
        values = _extract_keywords(all_text, patterns)
        entities[category] = _dedupe(values)

    # Entity enrichments from regex patterns.
    entities["asoc_entities"] = _dedupe(
        entities["asoc_entities"] + _extract_regex(all_text, r"\b(snd_soc_[A-Za-z0-9_]+)\b")
    )
    entities["alsa_entities"] = _dedupe(
        entities["alsa_entities"] + _extract_regex(all_text, r"\b(snd_pcm_[A-Za-z0-9_]+)\b")
    )
    entities["soundwire_concepts"] = _dedupe(
        entities["soundwire_concepts"] + _extract_regex(all_text, r"\b((?:sdw|swr)_[A-Za-z0-9_]+)\b")
    )
    entities["qcom_downstream_abstractions"] = _dedupe(
        entities["qcom_downstream_abstractions"]
        + _extract_regex(all_text, r"\b((?:msm|qcom|wcd|lpass|bolero|q6|apr|gpr)_[A-Za-z0-9_]+)\b")
    )

    nodes: list[dict[str, Any]] = [
        {
            "id": f"source:{source_id}",
            "kind": "knowledge_source",
            "version": str(source_version),
        }
    ]
    edges: list[dict[str, Any]] = []

    for category in sorted(entities.keys()):
        category_id = f"category:{category}"
        nodes.append({"id": category_id, "kind": "entity_category", "name": category})
        edges.append({"from": f"source:{source_id}", "to": category_id, "relation": "contains_category"})

        for entity in entities[category]:
            entity_id = f"entity:{category}:{entity}"
            nodes.append({"id": entity_id, "kind": "semantic_entity", "name": entity, "category": category})
            edges.append({"from": category_id, "to": entity_id, "relation": "contains_entity"})

    counts = {category: len(values) for category, values in sorted(entities.items())}
    total_entities = sum(counts.values())

    payload = {
        "schema_version": "1.0",
        "graph_name": "semantic_entity_graph",
        "source_id": str(source_id),
        "source_version": str(source_version),
        "entity_categories": entities,
        "entity_counts": counts,
        "total_entities": total_entities,
        "nodes": nodes,
        "edges": edges,
        "classification": "PASS" if total_entities > 0 else "ADVISORY_ONLY_EMPTY_ENTITY_SET",
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return SemanticEntityExtractionResult(
        semantic_entity_graph=payload,
        deterministic_fingerprint=fingerprint,
    )
