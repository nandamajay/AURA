#!/usr/bin/env python3
"""Run architecture enforcement for the AURA codebase."""

from __future__ import annotations

from pathlib import Path

from aura_sdk.validation.architecture import main


def _default_aura_root() -> str:
    return str(Path(__file__).resolve().parents[1])


if __name__ == "__main__":
    raise SystemExit(main(["--aura-root", _default_aura_root()]))
