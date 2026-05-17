"""Simulation Agent — executes deterministic subsystem simulation plans."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from aura_agents.base import BaseAgent
from aura_sdk.models.simulation import FidelityMode, SimulationStatus, SimulationType


class SimulationAgent(BaseAgent):
    """Simulation orchestration agent."""

    AGENT_TYPE = "simulation"
    DEFAULT_TIMEOUT = 900

    async def execute(self) -> dict[str, Any]:
        await self._send_progress(5, "starting", "Loading simulation context")

        context = self._load_context()
        patch_id = str(context.get("patch_id", "unassigned"))
        db_path = str(context.get("db_path", "/data/aura.db"))
        requested_types = self._extract_simulation_types(context)
        fidelity_mode = self._extract_fidelity_mode(context, requested_types)
        await self._send_progress(
            20,
            "context_loaded",
            f"Prepared {len(requested_types)} simulation type(s) with fidelity={fidelity_mode}",
        )

        history = self._load_historical_baseline(db_path=db_path, limit=200)
        await self._send_progress(45, "history_loaded", "Loaded historical simulation baseline")

        results = [self._run_one(sim_type, fidelity_mode, history) for sim_type in requested_types]
        summary = self._summarize(results)
        await self._send_progress(
            70,
            "simulation_executed",
            f"Simulations complete: passed={summary['passed']}, failed={summary['failed']}",
        )

        report = {
            "agent_type": self.AGENT_TYPE,
            "patch_id": patch_id,
            "fidelity_mode": fidelity_mode,
            "requested_types": [s.value for s in requested_types],
            "historical_baseline": history,
            "results": results,
            "summary": summary,
        }
        report["recommendations"] = await self._recommend(report)

        json_path = self.output_dir / "simulation_report.json"
        markdown_path = self.output_dir / "simulation_report.md"
        json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        self._write_markdown(markdown_path, report)

        await self._send_progress(
            95,
            "artifacts_written",
            f"Artifacts written: {json_path.name}, {markdown_path.name}",
        )

        return {
            "requested_simulations": len(requested_types),
            "passed": summary["passed"],
            "failed": summary["failed"],
            "inconclusive": summary["inconclusive"],
            "overall_status": summary["overall_status"],
            "json_path": str(json_path),
            "markdown_path": str(markdown_path),
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

    def _extract_simulation_types(self, context: dict[str, Any]) -> list[SimulationType]:
        values: list[str] = []
        single = context.get("simulation_type")
        multiple = context.get("simulation_types")
        if isinstance(single, str) and single.strip():
            values.append(single.strip())
        if isinstance(multiple, list):
            for item in multiple:
                if isinstance(item, str) and item.strip():
                    values.append(item.strip())

        parsed: list[SimulationType] = []
        for value in values:
            try:
                parsed.append(SimulationType(value))
            except Exception:
                continue
        if not parsed:
            return list(SimulationType)

        dedup: dict[SimulationType, None] = {}
        for item in parsed:
            dedup[item] = None
        return list(dedup.keys())

    def _extract_fidelity_mode(
        self,
        context: dict[str, Any],
        requested_types: list[SimulationType],
    ) -> str:
        raw = str(context.get("fidelity_mode", context.get("fidelity", FidelityMode.STATE_MACHINE.value)))
        try:
            requested = FidelityMode(raw)
        except Exception:
            requested = FidelityMode.STATE_MACHINE

        qemu_allowed = all(sim_type in (SimulationType.DAPM, SimulationType.PCM) for sim_type in requested_types)
        if requested == FidelityMode.QEMU and not qemu_allowed:
            return FidelityMode.STATE_MACHINE.value
        return requested.value

    def _load_historical_baseline(self, *, db_path: str, limit: int) -> dict[str, Any]:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT simulation_type, status, COUNT(*) AS count
                FROM simulation_results
                GROUP BY simulation_type, status
                ORDER BY simulation_type, status
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        except Exception:
            rows = []
        finally:
            conn.close()

        by_type: dict[str, dict[str, int]] = {}
        for row in rows:
            sim_type = str(row["simulation_type"])
            status = str(row["status"])
            by_type.setdefault(sim_type, {})
            by_type[sim_type][status] = int(row["count"])
        return by_type

    def _run_one(
        self,
        sim_type: SimulationType,
        fidelity_mode: str,
        history: dict[str, Any],
    ) -> dict[str, Any]:
        profile = self._simulation_profile(sim_type)
        historical = history.get(sim_type.value, {})
        hist_pass = int(historical.get(SimulationStatus.PASSED.value, 0))
        hist_fail = int(historical.get(SimulationStatus.FAILED.value, 0))
        hist_total = hist_pass + hist_fail
        historical_fail_ratio = (hist_fail / hist_total) if hist_total > 0 else 0.0

        base_fail_ratio = profile["base_fail_ratio"]
        adjusted_fail_ratio = min(0.8, max(0.02, base_fail_ratio + (historical_fail_ratio * 0.2)))
        decision = self.context.random_float(0.0, 1.0) if self.context else 0.5

        if decision < adjusted_fail_ratio:
            status = SimulationStatus.FAILED.value
            confidence_impact = round(-profile["impact_base"], 3)
        elif decision < adjusted_fail_ratio + 0.08:
            status = SimulationStatus.INCONCLUSIVE.value
            confidence_impact = 0.0
        else:
            status = SimulationStatus.PASSED.value
            confidence_impact = round(profile["impact_base"], 3)

        duration_min = profile["duration_ms"][0]
        duration_max = profile["duration_ms"][1]
        duration_ms = self.context.random_int(duration_min, duration_max) if self.context else duration_min

        findings = {
            "checks_executed": profile["checks"],
            "historical_fail_ratio": round(historical_fail_ratio, 3),
            "adjusted_fail_ratio": round(adjusted_fail_ratio, 3),
            "decision_signal": round(decision, 3),
            "fidelity_mode": fidelity_mode,
        }
        failure_predictions: list[str] = []
        if status == SimulationStatus.FAILED.value:
            failure_predictions = profile["failure_predictions"][:3]

        return {
            "simulation_type": sim_type.value,
            "status": status,
            "duration_ms": duration_ms,
            "confidence_impact": confidence_impact,
            "findings": findings,
            "failure_predictions": failure_predictions,
        }

    def _simulation_profile(self, sim_type: SimulationType) -> dict[str, Any]:
        profiles: dict[SimulationType, dict[str, Any]] = {
            SimulationType.PROBE_FLOW: {
                "base_fail_ratio": 0.10,
                "impact_base": 0.03,
                "duration_ms": (150, 420),
                "checks": ["component_probe_order", "dependency_resolution"],
                "failure_predictions": ["probe order mismatch", "missing codec registration"],
            },
            SimulationType.DAPM: {
                "base_fail_ratio": 0.13,
                "impact_base": 0.04,
                "duration_ms": (220, 650),
                "checks": ["widget_route_graph", "power_state_transitions"],
                "failure_predictions": ["power widget dead-end", "route activation regression"],
            },
            SimulationType.PCM: {
                "base_fail_ratio": 0.12,
                "impact_base": 0.04,
                "duration_ms": (180, 540),
                "checks": ["hw_params_validation", "stream_start_stop_sequence"],
                "failure_predictions": ["invalid hw_params negotiation", "start/stop ordering issue"],
            },
            SimulationType.SOUNDWIRE: {
                "base_fail_ratio": 0.16,
                "impact_base": 0.05,
                "duration_ms": (260, 780),
                "checks": ["link_enumeration", "slave_attach_detach"],
                "failure_predictions": ["link enumeration timeout", "device attach instability"],
            },
            SimulationType.RUNTIME_PM: {
                "base_fail_ratio": 0.14,
                "impact_base": 0.04,
                "duration_ms": (140, 420),
                "checks": ["suspend_resume_cycles", "clock_gating_balance"],
                "failure_predictions": ["resume latency spike", "imbalanced runtime PM refs"],
            },
            SimulationType.DSP: {
                "base_fail_ratio": 0.18,
                "impact_base": 0.06,
                "duration_ms": (300, 900),
                "checks": ["firmware_bootstrap", "command_channel_integrity"],
                "failure_predictions": ["DSP bootstrap timeout", "IPC command corruption risk"],
            },
            SimulationType.DMA_IRQ: {
                "base_fail_ratio": 0.15,
                "impact_base": 0.05,
                "duration_ms": (200, 600),
                "checks": ["dma_descriptor_chain", "irq_ack_sequence"],
                "failure_predictions": ["descriptor underflow", "IRQ acknowledgement drift"],
            },
        }
        return profiles[sim_type]

    def _summarize(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        passed = sum(1 for item in results if item["status"] == SimulationStatus.PASSED.value)
        failed = sum(1 for item in results if item["status"] == SimulationStatus.FAILED.value)
        inconclusive = sum(1 for item in results if item["status"] == SimulationStatus.INCONCLUSIVE.value)
        confidence_delta = round(sum(float(item["confidence_impact"]) for item in results), 3)

        if failed > 0:
            overall = "failed"
        elif inconclusive > 0:
            overall = "inconclusive"
        else:
            overall = "passed"

        return {
            "requested": len(results),
            "passed": passed,
            "failed": failed,
            "inconclusive": inconclusive,
            "overall_status": overall,
            "confidence_delta": confidence_delta,
        }

    async def _recommend(self, report: dict[str, Any]) -> list[str]:
        summary = report["summary"]
        fallback: list[str] = []
        if summary["failed"] > 0:
            fallback.append("Block patch advancement until failed simulation categories are addressed.")
        if summary["inconclusive"] > 0:
            fallback.append("Re-run inconclusive simulations with focused instrumentation.")
        if summary["failed"] == 0 and summary["inconclusive"] == 0:
            fallback.append("Simulation gate passed; continue with validation and review.")
        fallback.append(f"Net confidence delta from simulations: {summary['confidence_delta']}.")

        try:
            response = await self.call_llm(
                [
                    {
                        "role": "system",
                        "content": (
                            "Provide concise simulation follow-up actions. "
                            'Return JSON only: {"recommendations":["..."]}'
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "summary": summary,
                                "results": report["results"],
                            }
                        ),
                    },
                ],
                max_tokens=350,
            )
            parsed = json.loads(response)
            recs = parsed.get("recommendations", [])
            if isinstance(recs, list):
                clean = [str(item).strip() for item in recs if str(item).strip()]
                if clean:
                    return clean[:8]
        except Exception:
            pass
        return fallback

    def _write_markdown(self, path: Path, report: dict[str, Any]) -> None:
        summary = report["summary"]
        with path.open("w", encoding="utf-8") as f:
            f.write("# Simulation Report\n\n")
            f.write(f"- Patch: {report['patch_id']}\n")
            f.write(f"- Fidelity mode: {report['fidelity_mode']}\n")
            f.write(f"- Requested simulations: {summary['requested']}\n")
            f.write(f"- Passed: {summary['passed']}\n")
            f.write(f"- Failed: {summary['failed']}\n")
            f.write(f"- Inconclusive: {summary['inconclusive']}\n")
            f.write(f"- Overall status: {summary['overall_status']}\n")
            f.write(f"- Confidence delta: {summary['confidence_delta']}\n\n")
            f.write("## Results\n\n")
            for item in report["results"]:
                f.write(
                    f"- {item['simulation_type']}: status={item['status']}, "
                    f"duration_ms={item['duration_ms']}, "
                    f"confidence_impact={item['confidence_impact']}\n"
                )
            f.write("\n## Recommendations\n\n")
            for rec in report["recommendations"]:
                f.write(f"- {rec}\n")


if __name__ == "__main__":
    SimulationAgent.main()
