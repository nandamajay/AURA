#!/usr/bin/env python3
"""Deterministic execution gate used by CI stabilization checks."""

from __future__ import annotations

import asyncio
import random
import sys

from aura_sdk.validation.detectors import NondeterminismDetector


def _deterministic_sample() -> dict[str, object]:
    return {"status": "ok", "values": [1, 2, 3]}


def _nondeterministic_sample() -> float:
    return random.random()


async def _run() -> int:
    detector = NondeterminismDetector(trials=12)
    deterministic = await detector.detect_in_function(_deterministic_sample)
    nondeterministic = await detector.detect_in_function(_nondeterministic_sample)

    print(
        "deterministic_check",
        {
            "is_deterministic": deterministic["is_deterministic"],
            "unique_outputs": deterministic["unique_outputs"],
        },
    )
    print(
        "nondeterminism_check",
        {
            "is_deterministic": nondeterministic["is_deterministic"],
            "unique_outputs": nondeterministic["unique_outputs"],
        },
    )

    if not deterministic["is_deterministic"]:
        print("FAIL: deterministic sample was reported nondeterministic", file=sys.stderr)
        return 1
    if nondeterministic["is_deterministic"]:
        print("FAIL: nondeterministic sample was not detected", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
