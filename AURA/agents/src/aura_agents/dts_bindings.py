"""DTS Bindings Agent — maps downstream DTS bindings to upstream schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aura_agents.base import BaseAgent


class DTSBindingsAgent(BaseAgent):
    """Device-tree bindings analysis agent."""

    AGENT_TYPE = "dts_bindings"
    DEFAULT_TIMEOUT = 600

    async def execute(self) -> dict[str, Any]:
        await self._send_progress(5, "starting", "Loading DTS conversion context")

        context = self._load_context()
        downstream_bindings = self._extract_bindings(context)
        await self._send_progress(
            20,
            "context_loaded",
            f"Prepared {len(downstream_bindings)} downstream binding(s)",
        )

        rules = self._load_rule_mappings()
        mapping = await self._build_mapping(downstream_bindings, rules)
        await self._send_progress(
            70,
            "mapping_built",
            f"Generated {len(mapping['mappings'])} DTS conversion mapping(s)",
        )

        map_path = self.output_dir / "dts_conversion_map.json"
        report_path = self.output_dir / "dts_bindings_report.md"
        map_path.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
        self._write_report(report_path, mapping)

        await self._send_progress(
            95,
            "artifacts_written",
            f"Artifacts written: {map_path.name}, {report_path.name}",
        )

        return {
            "downstream_bindings": len(downstream_bindings),
            "mapping_count": len(mapping["mappings"]),
            "rule_count": len(rules),
            "map_path": str(map_path),
            "report_path": str(report_path),
        }

    def _load_context(self) -> dict[str, Any]:
        raw = getattr(self, "input_json", "")
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        return {}

    def _extract_bindings(self, context: dict[str, Any]) -> list[str]:
        bindings: list[str] = []
        for key in ("downstream_bindings", "bindings", "items", "drivers"):
            value = context.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item.strip():
                        bindings.append(item.strip())
        if not bindings:
            bindings = [
                "qcom,wcd934x-codec",
                "qcom,msm-audio-card",
                "qcom,sa8155-audio",
            ]
        dedup: dict[str, None] = {}
        for item in bindings:
            dedup[item] = None
        return list(dedup.keys())[:40]

    def _load_rule_mappings(self) -> list[dict[str, Any]]:
        """Load DTS conversion mappings from rules path when available."""
        rules_file = Path(self.rules_path) / "dts_conversion.json"
        if rules_file.exists():
            try:
                data = json.loads(rules_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return [d for d in data if isinstance(d, dict)]
            except Exception:
                pass
        # Conservative default from phase docs.
        return [
            {
                "downstream_binding": "qcom,wcd934x-codec",
                "upstream_binding": "cirrus,cs42l42",
                "yaml_schema": "sound/cirrus,cs42l42.yaml",
            },
            {
                "downstream_binding": "qcom,msm-audio-card",
                "upstream_binding": "qcom,sm8250-sndcard",
                "yaml_schema": "sound/qcom,sm8250.yaml",
            },
        ]

    async def _build_mapping(
        self,
        downstream_bindings: list[str],
        rules: list[dict[str, Any]],
    ) -> dict[str, Any]:
        mappings: list[dict[str, Any]] = []
        indexed = {
            str(rule.get("downstream_binding", "")).strip(): rule
            for rule in rules
            if str(rule.get("downstream_binding", "")).strip()
        }

        for binding in downstream_bindings:
            rule = indexed.get(binding)
            if rule is not None:
                mappings.append(
                    {
                        "downstream_binding": binding,
                        "upstream_binding": str(rule.get("upstream_binding", "unknown")),
                        "yaml_schema": str(rule.get("yaml_schema", "")),
                        "confidence": 0.95,
                        "source": "rule",
                    }
                )
                continue

            # Try LLM fallback for unknown binding.
            mapping = await self._llm_binding_fallback(binding)
            mappings.append(mapping)

        return {
            "agent_type": self.AGENT_TYPE,
            "mappings": mappings,
            "summary": {
                "downstream_bindings": len(downstream_bindings),
                "mapped": len([m for m in mappings if m["upstream_binding"] != "unknown"]),
                "rule_backed": len([m for m in mappings if m["source"] == "rule"]),
                "llm_inferred": len([m for m in mappings if m["source"] == "llm"]),
                "unmapped": len([m for m in mappings if m["upstream_binding"] == "unknown"]),
            },
        }

    async def _llm_binding_fallback(self, binding: str) -> dict[str, Any]:
        try:
            response = await self.call_llm(
                [
                    {
                        "role": "system",
                        "content": (
                            "Map downstream Qualcomm device-tree binding names to likely upstream binding and YAML schema. "
                            "Return JSON only: "
                            '{"upstream_binding":"...","yaml_schema":"...","confidence":0.0}'
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Downstream binding: {binding}",
                    },
                ],
                max_tokens=400,
            )
            parsed = json.loads(response)
            return {
                "downstream_binding": binding,
                "upstream_binding": str(parsed.get("upstream_binding", "unknown")),
                "yaml_schema": str(parsed.get("yaml_schema", "")),
                "confidence": float(parsed.get("confidence", 0.5)),
                "source": "llm",
            }
        except Exception:
            return {
                "downstream_binding": binding,
                "upstream_binding": "unknown",
                "yaml_schema": "",
                "confidence": 0.0,
                "source": "heuristic",
            }

    def _write_report(self, path: Path, mapping: dict[str, Any]) -> None:
        summary = mapping["summary"]
        with path.open("w", encoding="utf-8") as f:
            f.write("# DTS Bindings Conversion Report\n\n")
            f.write(f"- Downstream bindings: {summary['downstream_bindings']}\n")
            f.write(f"- Mapped: {summary['mapped']}\n")
            f.write(f"- Rule-backed: {summary['rule_backed']}\n")
            f.write(f"- LLM-inferred: {summary['llm_inferred']}\n")
            f.write(f"- Unmapped: {summary['unmapped']}\n\n")
            f.write("## Conversion Entries\n\n")
            for entry in mapping["mappings"]:
                f.write(f"- `{entry['downstream_binding']}` -> `{entry['upstream_binding']}`")
                if entry["yaml_schema"]:
                    f.write(f" ({entry['yaml_schema']})")
                f.write(f", source={entry['source']}, confidence={entry['confidence']}\n")


if __name__ == "__main__":
    DTSBindingsAgent.main()
