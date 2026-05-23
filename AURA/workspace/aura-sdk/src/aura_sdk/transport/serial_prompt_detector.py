"""Prompt detection helpers for serial console execution."""

from __future__ import annotations

import re
from dataclasses import dataclass


PANIC_PATTERNS = (
    "kernel panic",
    "unable to handle kernel",
    "watchdog bite",
    "segmentation fault",
)


@dataclass(frozen=True)
class PromptDetectionResult:
    prompt_seen: bool
    panic_detected: bool
    prompt_match: str | None


class SerialPromptDetector:
    """Detects prompt readiness and panic signatures from serial output."""

    def __init__(self, prompt_regex: str):
        self._prompt_regex = re.compile(prompt_regex, re.MULTILINE)

    def analyze(self, output: str) -> PromptDetectionResult:
        prompt_match: re.Match[str] | None = None
        for prompt_match in self._prompt_regex.finditer(output):
            pass

        lowered = output.lower()
        panic_detected = any(token in lowered for token in PANIC_PATTERNS)
        return PromptDetectionResult(
            prompt_seen=prompt_match is not None,
            panic_detected=panic_detected,
            prompt_match=prompt_match.group(0) if prompt_match else None,
        )

    def strip_prompt_lines(self, output: str) -> str:
        lines = output.splitlines()
        filtered = [line for line in lines if not self._prompt_regex.search(line)]
        return "\n".join(filtered).strip()
