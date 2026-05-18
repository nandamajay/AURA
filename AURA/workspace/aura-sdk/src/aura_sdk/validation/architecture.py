"""Architecture enforcement checks for frozen AURA boundaries.

These checks are intentionally explicit and conservative:
- forbidden infra imports
- service layer boundary violations
- plugin isolation
- core observability baseline
- mandatory replay hook presence
"""

from __future__ import annotations

import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ArchitectureViolation:
    rule_id: str
    severity: str
    file_path: str
    line: int
    message: str


class ArchitectureEnforcer:
    """Deterministic architecture compliance validator."""

    FORBIDDEN_IMPORT_ROOTS = frozenset(
        {
            "redis",
            "kafka",
            "pika",
            "kombu",
            "celery",
            "kubernetes",
            "psycopg2",
            "asyncpg",
            "pymongo",
            "motor",
        }
    )

    LAYER_FORBIDDEN_IMPORTS: dict[str, frozenset[str]] = {
        "sdk": frozenset({"core", "llm_gateway", "ws_server", "aura_agents"}),
        "core": frozenset({"llm_gateway", "ws_server"}),
        "llm_gateway": frozenset({"core", "ws_server", "aura_agents"}),
        "ws_server": frozenset({"core", "llm_gateway", "aura_agents"}),
        "agents": frozenset({"core", "llm_gateway", "ws_server"}),
        "plugins": frozenset({"core", "llm_gateway", "ws_server", "aura_agents"}),
    }

    CORE_OBSERVABILITY_EXEMPT = frozenset({"__init__.py", "config.py"})

    def __init__(self, aura_root: str | Path):
        self.aura_root = Path(aura_root).resolve()
        self._stdlib_roots = set(getattr(sys, "stdlib_module_names", set()))

    def run(self) -> dict[str, object]:
        violations: list[ArchitectureViolation] = []
        checked_files = 0

        for py_file in self._iter_scoped_python_files():
            checked_files += 1
            layer = self._layer_for_file(py_file)
            text = py_file.read_text(encoding="utf-8", errors="ignore")
            imports = list(self._extract_imports(py_file, text))
            violations.extend(self._check_forbidden_imports(py_file, imports))
            violations.extend(self._check_layer_boundaries(py_file, layer, imports))
            if layer == "plugins":
                violations.extend(self._check_plugin_isolation(py_file, imports))
            if layer == "core":
                violations.extend(self._check_observability(py_file, text))

        violations.extend(self._check_replay_hooks())
        ordered = sorted(violations, key=lambda v: (v.file_path, v.line, v.rule_id))
        payload = {
            "passed": len(ordered) == 0,
            "checked_files": checked_files,
            "violation_count": len(ordered),
            "violations": [asdict(v) for v in ordered],
        }
        return payload

    def _iter_scoped_python_files(self) -> Iterable[Path]:
        scopes = [
            self.aura_root / "workspace" / "aura-sdk" / "src" / "aura_sdk",
            self.aura_root / "services" / "core" / "src" / "core",
            self.aura_root / "services" / "llm-gateway" / "src" / "llm_gateway",
            self.aura_root / "services" / "ws-server" / "src" / "ws_server",
            self.aura_root / "agents" / "src" / "aura_agents",
            self.aura_root / "plugins",
        ]
        for scope in scopes:
            if not scope.exists():
                continue
            for py_file in scope.rglob("*.py"):
                yield py_file

    def _layer_for_file(self, py_file: Path) -> str | None:
        rel = self._relpath(py_file)
        if rel.startswith("workspace/aura-sdk/src/aura_sdk/"):
            return "sdk"
        if rel.startswith("services/core/src/core/"):
            return "core"
        if rel.startswith("services/llm-gateway/src/llm_gateway/"):
            return "llm_gateway"
        if rel.startswith("services/ws-server/src/ws_server/"):
            return "ws_server"
        if rel.startswith("agents/src/aura_agents/"):
            return "agents"
        if rel.startswith("plugins/"):
            return "plugins"
        return None

    def _extract_imports(
        self, py_file: Path, text: str
    ) -> Iterable[tuple[str, int]]:
        try:
            tree = ast.parse(text, filename=str(py_file))
        except SyntaxError as exc:
            yield ("__syntax_error__", exc.lineno or 1)
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root:
                        yield (root, node.lineno)
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0 and node.module is None:
                    continue
                module = (node.module or "").strip()
                if not module:
                    continue
                root = module.split(".", 1)[0]
                if root:
                    yield (root, node.lineno)

    def _check_forbidden_imports(
        self, py_file: Path, imports: Iterable[tuple[str, int]]
    ) -> list[ArchitectureViolation]:
        violations: list[ArchitectureViolation] = []
        for root, line in imports:
            if root in self.FORBIDDEN_IMPORT_ROOTS:
                violations.append(
                    ArchitectureViolation(
                        rule_id="ARCH_FORBIDDEN_IMPORT",
                        severity="high",
                        file_path=self._relpath(py_file),
                        line=line,
                        message=f"forbidden import root '{root}'",
                    )
                )
        return violations

    def _check_layer_boundaries(
        self,
        py_file: Path,
        layer: str | None,
        imports: Iterable[tuple[str, int]],
    ) -> list[ArchitectureViolation]:
        if layer is None:
            return []
        forbidden = self.LAYER_FORBIDDEN_IMPORTS.get(layer, frozenset())
        violations: list[ArchitectureViolation] = []
        for root, line in imports:
            if root in forbidden:
                violations.append(
                    ArchitectureViolation(
                        rule_id="ARCH_LAYER_BOUNDARY",
                        severity="high",
                        file_path=self._relpath(py_file),
                        line=line,
                        message=f"layer '{layer}' cannot import '{root}'",
                    )
                )
        return violations

    def _check_plugin_isolation(
        self, py_file: Path, imports: Iterable[tuple[str, int]]
    ) -> list[ArchitectureViolation]:
        violations: list[ArchitectureViolation] = []
        for root, line in imports:
            if root in {"aura_sdk", "plugins"}:
                continue
            if root in self._stdlib_roots:
                continue
            violations.append(
                ArchitectureViolation(
                    rule_id="ARCH_PLUGIN_ISOLATION",
                    severity="medium",
                    file_path=self._relpath(py_file),
                    line=line,
                    message=f"plugin import '{root}' is not allowed (only stdlib + aura_sdk)",
                )
            )
        return violations

    def _check_observability(self, py_file: Path, text: str) -> list[ArchitectureViolation]:
        if py_file.name in self.CORE_OBSERVABILITY_EXEMPT:
            return []
        if "logger = get_logger(" in text:
            return []
        return [
            ArchitectureViolation(
                rule_id="ARCH_OBSERVABILITY",
                severity="medium",
                file_path=self._relpath(py_file),
                line=1,
                message="core module missing module-level logger via get_logger",
            )
        ]

    def _check_replay_hooks(self) -> list[ArchitectureViolation]:
        violations: list[ArchitectureViolation] = []
        base_py = self.aura_root / "agents" / "src" / "aura_agents" / "base.py"
        runtime_py = self.aura_root / "services" / "core" / "src" / "core" / "services" / "agent_runtime.py"

        base_tokens = [
            "TaskRecorder",
            ".start_task(",
            ".record_prompt(",
            ".record_response(",
            ".finalize(",
        ]
        runtime_tokens = ["--db-path", "--seed", "--model-version"]

        if not base_py.exists():
            violations.append(
                ArchitectureViolation(
                    rule_id="ARCH_REPLAY_HOOKS",
                    severity="critical",
                    file_path=self._relpath(base_py),
                    line=1,
                    message="missing agents base module for replay instrumentation",
                )
            )
        else:
            text = base_py.read_text(encoding="utf-8", errors="ignore")
            for token in base_tokens:
                if token not in text:
                    violations.append(
                        ArchitectureViolation(
                            rule_id="ARCH_REPLAY_HOOKS",
                            severity="critical",
                            file_path=self._relpath(base_py),
                            line=1,
                            message=f"missing replay hook token '{token}' in base agent",
                        )
                    )

        if runtime_py.exists():
            runtime_text = runtime_py.read_text(encoding="utf-8", errors="ignore")
            for token in runtime_tokens:
                if token not in runtime_text:
                    violations.append(
                        ArchitectureViolation(
                            rule_id="ARCH_REPLAY_HOOKS",
                            severity="high",
                            file_path=self._relpath(runtime_py),
                            line=1,
                            message=f"agent runtime spawn missing deterministic replay flag '{token}'",
                        )
                    )

        agents_root = self.aura_root / "agents" / "src" / "aura_agents"
        if agents_root.exists():
            for py_file in agents_root.glob("*.py"):
                if py_file.name in {"__init__.py", "__main__.py", "base.py", "cli.py"}:
                    continue
                text = py_file.read_text(encoding="utf-8", errors="ignore")
                try:
                    tree = ast.parse(text, filename=str(py_file))
                except SyntaxError:
                    continue
                for node in tree.body:
                    if not isinstance(node, ast.ClassDef):
                        continue
                    if not node.name.endswith("Agent"):
                        continue
                    bases = [self._base_name(base) for base in node.bases]
                    if "BaseAgent" not in bases:
                        violations.append(
                            ArchitectureViolation(
                                rule_id="ARCH_REPLAY_HOOKS",
                                severity="high",
                                file_path=self._relpath(py_file),
                                line=node.lineno,
                                message=f"{node.name} must inherit BaseAgent to enforce replay hooks",
                            )
                        )

        return violations

    def _base_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return ""

    def _relpath(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.aura_root))
        except Exception:
            return str(path)


def run_enforcement(aura_root: str | Path) -> dict[str, object]:
    return ArchitectureEnforcer(aura_root).run()


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run AURA architecture compliance enforcement")
    parser.add_argument(
        "--aura-root",
        default=".",
        help="Path to AURA project root (directory containing services/, agents/, workspace/)",
    )
    parser.add_argument(
        "--format",
        default="text",
        choices=("text", "json"),
        help="Output format",
    )
    args = parser.parse_args(argv)

    report = run_enforcement(args.aura_root)
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(
            f"checked_files={report['checked_files']} "
            f"violations={report['violation_count']} passed={report['passed']}"
        )
        for item in report["violations"]:
            print(
                f"{item['rule_id']} {item['severity']} {item['file_path']}:{item['line']} "
                f"{item['message']}"
            )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
