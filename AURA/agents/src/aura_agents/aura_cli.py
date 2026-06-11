"""Public `aura` CLI entrypoint."""

from __future__ import annotations

from aura_agents.aura_facade import main as facade_main


def main(argv: list[str] | None = None) -> int:
    return facade_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
