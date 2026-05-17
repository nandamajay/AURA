"""Patch Builder Agent — composes deterministic patch manifests and cover letters."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from aura_agents.base import BaseAgent


class PatchBuilderAgent(BaseAgent):
    """Patch construction support agent."""

    AGENT_TYPE = "patch_builder"
    DEFAULT_TIMEOUT = 600

    async def execute(self) -> dict[str, Any]:
        await self._send_progress(5, "starting", "Loading patch construction context")

        context = self._load_context()
        db_path = str(context.get("db_path", "/data/aura.db"))
        patch_title = str(context.get("patch_title", "ALSA: qcom: deterministic upstream prep"))
        changed_files = self._extract_changed_files(context)
        description = str(
            context.get(
                "description",
                "Incremental upstream alignment for Qualcomm audio paths with deterministic traceability.",
            )
        )
        await self._send_progress(
            20,
            "context_loaded",
            f"Prepared {len(changed_files)} file target(s) for patch construction",
        )

        rule_hints = self._load_rule_hints(db_path=db_path, limit=20)
        manifest = self._build_manifest(
            patch_title=patch_title,
            description=description,
            changed_files=changed_files,
            rule_hints=rule_hints,
        )
        await self._send_progress(
            70,
            "manifest_built",
            f"Manifest has {len(manifest['files'])} file entries and {len(manifest['validation_plan'])} validation steps",
        )

        cover_notes = await self._generate_cover_notes(manifest)
        manifest["cover_notes"] = cover_notes

        manifest_path = self.output_dir / "patch_manifest.json"
        cover_path = self.output_dir / "cover_letter.md"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        self._write_cover_letter(cover_path, manifest)

        await self._send_progress(
            95,
            "artifacts_written",
            f"Artifacts written: {manifest_path.name}, {cover_path.name}",
        )

        return {
            "patch_title": manifest["patch_title"],
            "file_count": len(manifest["files"]),
            "rule_hints_used": len(manifest["rule_hints"]),
            "manifest_path": str(manifest_path),
            "cover_letter_path": str(cover_path),
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

    def _extract_changed_files(self, context: dict[str, Any]) -> list[str]:
        files: list[str] = []
        raw = context.get("changed_files")
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str) and item.strip():
                    files.append(item.strip())
        if not files:
            files = [
                "sound/soc/qcom/common.c",
                "sound/soc/qcom/qdsp6/qdsp6.c",
                "sound/soc/qcom/sm8250.c",
            ]
        dedup: dict[str, None] = {}
        for item in files:
            dedup[item] = None
        return list(dedup.keys())[:40]

    def _load_rule_hints(self, *, db_path: str, limit: int) -> list[dict[str, Any]]:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT category, downstream_pattern, upstream_equivalent, confidence
                FROM migration_rules
                ORDER BY confidence DESC, created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]
        except Exception:
            return []
        finally:
            conn.close()

    def _build_manifest(
        self,
        *,
        patch_title: str,
        description: str,
        changed_files: list[str],
        rule_hints: list[dict[str, Any]],
    ) -> dict[str, Any]:
        file_entries: list[dict[str, Any]] = []
        for index, path in enumerate(changed_files, start=1):
            impact = "high" if "qdsp6" in path else "medium" if "qcom" in path else "low"
            file_entries.append(
                {
                    "sequence": index,
                    "path": path,
                    "change_intent": "upstream_alignment",
                    "impact": impact,
                    "review_focus": self._review_focus(path),
                }
            )

        validation_plan = [
            {"step": "checkpatch", "required": True},
            {"step": "sparse", "required": True},
            {"step": "clang", "required": True},
            {"step": "dtbs_check", "required": True},
        ]

        return {
            "agent_type": self.AGENT_TYPE,
            "patch_title": patch_title,
            "description": description,
            "files": file_entries,
            "rule_hints": rule_hints[:10],
            "validation_plan": validation_plan,
            "governance_flags": {
                "requires_human_review": True,
                "approval_dimensions": ["lifecycle", "subsystem", "quality"],
            },
        }

    def _review_focus(self, path: str) -> list[str]:
        focus = ["API parity with upstream"]
        if "qdsp6" in path:
            focus.append("DSP command/response ordering")
        if "sm8" in path or "sc8" in path:
            focus.append("SoC-specific power and clock bindings")
        if path.endswith(".dts") or path.endswith(".dtsi"):
            focus.append("DT binding compliance")
        return focus

    async def _generate_cover_notes(self, manifest: dict[str, Any]) -> list[str]:
        fallback = [
            f"Patch touches {len(manifest['files'])} file(s) with incremental upstream-safe changes.",
            "Validation plan includes checkpatch, sparse, clang, and dtbs_check.",
            "Human review is required before final approval.",
        ]
        try:
            response = await self.call_llm(
                [
                    {
                        "role": "system",
                        "content": (
                            "Write concise Linux patch cover letter bullets. "
                            'Return JSON only: {"notes":["..."]}'
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "patch_title": manifest["patch_title"],
                                "files": [item["path"] for item in manifest["files"]],
                                "validation_plan": manifest["validation_plan"],
                            }
                        ),
                    },
                ],
                max_tokens=350,
            )
            parsed = json.loads(response)
            notes = parsed.get("notes", [])
            if isinstance(notes, list):
                clean = [str(note).strip() for note in notes if str(note).strip()]
                if clean:
                    return clean[:8]
        except Exception:
            pass
        return fallback

    def _write_cover_letter(self, path: Path, manifest: dict[str, Any]) -> None:
        with path.open("w", encoding="utf-8") as f:
            f.write(f"# {manifest['patch_title']}\n\n")
            f.write(f"{manifest['description']}\n\n")
            f.write("## Changed Files\n\n")
            for item in manifest["files"]:
                f.write(
                    f"- {item['path']} "
                    f"[impact={item['impact']}, focus={', '.join(item['review_focus'])}]\n"
                )
            f.write("\n## Validation Plan\n\n")
            for step in manifest["validation_plan"]:
                f.write(f"- {step['step']} (required={step['required']})\n")
            f.write("\n## Cover Notes\n\n")
            for note in manifest.get("cover_notes", []):
                f.write(f"- {note}\n")


if __name__ == "__main__":
    PatchBuilderAgent.main()
