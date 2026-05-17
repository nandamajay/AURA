"""Dependency Agent — constructs a dependency map for audio driver migration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aura_agents.base import BaseAgent


class DependencyAgent(BaseAgent):
    """Driver dependency analysis agent."""

    AGENT_TYPE = "dependency"
    DEFAULT_TIMEOUT = 600

    async def execute(self) -> dict[str, Any]:
        await self._send_progress(5, "starting", "Loading dependency analysis context")

        context = self._load_context()
        seeds = self._extract_seed_items(context)
        await self._send_progress(
            20,
            "context_loaded",
            f"Prepared {len(seeds)} seed item(s) for dependency analysis",
        )

        graph = await self._build_dependency_graph(seeds)
        await self._send_progress(
            70,
            "graph_built",
            f"Dependency graph built with {len(graph['nodes'])} nodes and {len(graph['edges'])} edges",
        )

        graph_path = self.output_dir / "dependency_graph.json"
        summary_path = self.output_dir / "dependency_summary.md"
        graph_path.write_text(json.dumps(graph, indent=2), encoding="utf-8")
        self._write_summary(summary_path, graph)

        await self._send_progress(
            95,
            "artifacts_written",
            f"Artifacts written: {graph_path.name}, {summary_path.name}",
        )

        return {
            "seed_items": len(seeds),
            "node_count": len(graph["nodes"]),
            "edge_count": len(graph["edges"]),
            "graph_path": str(graph_path),
            "summary_path": str(summary_path),
        }

    def _load_context(self) -> dict[str, Any]:
        """Load optional context from input JSON passed through --input."""
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

    def _extract_seed_items(self, context: dict[str, Any]) -> list[str]:
        """Extract seed items from known input fields."""
        seeds: list[str] = []
        for key in ("drivers", "upstreamed_drivers", "files", "components", "items"):
            value = context.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item.strip():
                        seeds.append(item.strip())
        if not seeds:
            seeds = [
                "sound/soc/qcom/common.c",
                "sound/soc/qcom/qdsp6/qdsp6.c",
                "sound/soc/qcom/sm8250.c",
            ]
        # Stable de-duplication preserving order.
        dedup: dict[str, None] = {}
        for item in seeds:
            dedup[item] = None
        return list(dedup.keys())[:25]

    async def _build_dependency_graph(self, seeds: list[str]) -> dict[str, Any]:
        """Build dependency graph using deterministic fallback + optional LLM enrichment."""
        nodes: dict[str, dict[str, str]] = {}
        edges: list[dict[str, str]] = []

        # Deterministic baseline graph so the agent succeeds even if LLM is unavailable.
        for item in seeds:
            nodes[item] = {"id": item, "kind": "driver_or_file"}
            for dep in self._heuristic_dependencies(item):
                nodes[dep] = {"id": dep, "kind": "dependency"}
                edges.append({"from": item, "to": dep, "type": "depends_on"})

        # Attempt targeted enrichment from LLM, but never fail the agent on LLM errors.
        for item in seeds[:10]:
            try:
                response = await self.call_llm(
                    [
                        {
                            "role": "system",
                            "content": (
                                "You analyze Linux kernel audio driver dependencies. "
                                "Return only JSON object: "
                                '{"dependencies":["..."],"subsystem":"..."}'
                            ),
                        },
                        {
                            "role": "user",
                            "content": f"Analyze dependencies for: {item}",
                        },
                    ],
                    max_tokens=500,
                )
                parsed = json.loads(response)
                deps = parsed.get("dependencies", [])
                subsystem = parsed.get("subsystem", "audio")
                if isinstance(deps, list):
                    for dep in deps[:8]:
                        if not isinstance(dep, str) or not dep.strip():
                            continue
                        dep_name = dep.strip()
                        nodes.setdefault(dep_name, {"id": dep_name, "kind": "dependency"})
                        edges.append({"from": item, "to": dep_name, "type": "depends_on"})
                        nodes[item]["subsystem"] = str(subsystem)
            except Exception:
                continue

        return {
            "agent_type": self.AGENT_TYPE,
            "nodes": list(nodes.values()),
            "edges": edges,
            "summary": {
                "seed_items": len(seeds),
                "node_count": len(nodes),
                "edge_count": len(edges),
            },
        }

    def _heuristic_dependencies(self, item: str) -> list[str]:
        item_l = item.lower()
        deps = ["snd-soc-core", "regmap", "clk", "pm_runtime"]
        if "qdsp" in item_l or "q6" in item_l:
            deps.extend(["apr", "q6afe", "q6asm"])
        if "sm8" in item_l or "sc8" in item_l:
            deps.extend(["interconnect", "pinctrl", "dmaengine"])
        if "dai" in item_l:
            deps.append("snd-soc-dai")
        return deps

    def _write_summary(self, path: Path, graph: dict[str, Any]) -> None:
        summary = graph["summary"]
        with path.open("w", encoding="utf-8") as f:
            f.write("# Dependency Agent Summary\n\n")
            f.write(f"- Nodes: {summary['node_count']}\n")
            f.write(f"- Edges: {summary['edge_count']}\n")
            f.write(f"- Seed items: {summary['seed_items']}\n\n")
            f.write("## Top Dependencies\n\n")
            dep_counts: dict[str, int] = {}
            for edge in graph["edges"]:
                dep = edge["to"]
                dep_counts[dep] = dep_counts.get(dep, 0) + 1
            for dep, count in sorted(dep_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:20]:
                f.write(f"- {dep}: {count}\n")


if __name__ == "__main__":
    DependencyAgent.main()
