"""Learning Agent — discovers upstreamed drivers and extracts patterns."""

from pathlib import Path
from aura_agents.base import BaseAgent


class LearningAgent(BaseAgent):
    """Discovers upstreamed Qualcomm Audio drivers and extracts migration patterns."""

    AGENT_TYPE = "learning"
    DEFAULT_TIMEOUT = 600  # 10 minutes

    async def execute(self) -> dict:
        await self._send_progress(0, "starting", "Loading rules...")

        # Load rules
        rules = self._load_rules()
        await self._send_progress(10, "rules_loaded", f"Loaded {len(rules)} rules")

        # Phase 1: Discover upstreamed drivers
        upstreamed = await self._discover_upstreamed()
        await self._send_progress(30, "discovery", f"Found {len(upstreamed)} upstreamed drivers")

        # Phase 2: Extract patterns
        patterns = await self._extract_patterns(upstreamed)
        await self._send_progress(60, "pattern_extraction", f"Extracted {len(patterns)} patterns")

        # Phase 3: Write findings
        findings_path = self.output_dir / "findings.md"
        self._write_findings(findings_path, patterns)
        await self._send_progress(90, "writing", f"Findings written to {findings_path}")

        return {
            "patterns_found": len(patterns),
            "upstreamed_drivers": upstreamed,
            "findings_path": str(findings_path),
        }

    def _load_rules(self) -> list[dict]:
        """Load migration rules from the rules directory."""
        import yaml, json, os
        rules = []
        rules_dir = Path(self.rules_path)
        if rules_dir.exists():
            for f in rules_dir.iterdir():
                if f.suffix in ('.yaml', '.yml'):
                    try:
                        with open(f) as fh:
                            data = yaml.safe_load(fh)
                            if data and isinstance(data, dict):
                                rules.extend(data.get("rules", []))
                    except Exception:
                        pass
                elif f.suffix == '.json':
                    try:
                        with open(f) as fh:
                            data = json.load(fh)
                            if isinstance(data, list):
                                rules.extend(data)
                            elif isinstance(data, dict):
                                rules.extend(data.get("rules", []))
                    except Exception:
                        pass
        return rules

    async def _discover_upstreamed(self) -> list[str]:
        """Discover upstreamed Qualcomm Audio drivers."""
        # Query LLM for upstreamed driver list
        try:
            resp = await self.call_llm([
                {"role": "system", "content": "List upstreamed Qualcomm audio drivers in the Linux kernel. Return one driver per line, format: driver_name - subsystem."},
                {"role": "user", "content": "Discover upstreamed Qualcomm Audio drivers"},
            ])
            return [line.strip() for line in resp.split('\n') if line.strip()]
        except Exception as e:
            return [f"Error discovering drivers: {e}"]

    async def _extract_patterns(self, upstreamed: list[str]) -> list[dict]:
        """Extract migration patterns from upstreamed drivers."""
        patterns = []
        for driver in upstreamed[:20]:  # Limit to first 20
            try:
                resp = await self.call_llm([
                    {"role": "system", "content": f"Analyze {driver} and extract key migration patterns for Qualcomm audio upstreaming."},
                    {"role": "user", "content": "Extract patterns"},
                ], max_tokens=1000)
                patterns.append({
                    "driver": driver,
                    "pattern": resp[:500],  # Truncate
                    "confidence": 0.8,
                })
            except Exception:
                patterns.append({
                    "driver": driver,
                    "pattern": "Pattern extraction failed",
                    "confidence": 0.0,
                })
        return patterns

    def _write_findings(self, path: Path, patterns: list[dict]) -> None:
        """Write findings to markdown file."""
        with open(path, "w") as f:
            f.write("# AURA Learning Agent — Findings\n\n")
            f.write(f"## Patterns Found: {len(patterns)}\n\n")
            for p in patterns:
                f.write(f"### {p['driver']}\n")
                f.write(f"- Pattern: {p['pattern'][:200]}\n")
                f.write(f"- Confidence: {p['confidence']}\n\n")


if __name__ == "__main__":
    LearningAgent.main()
