"""Architecture enforcement regression tests."""

from __future__ import annotations

from pathlib import Path

from aura_sdk.validation.architecture import ArchitectureEnforcer


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed_valid_repo(root: Path) -> None:
    _write(
        root / "workspace/aura-sdk/src/aura_sdk/validation/sample.py",
        "from aura_sdk.logging.logger import get_logger\nlogger = get_logger('sample')\n",
    )
    _write(
        root / "services/core/src/core/ok.py",
        "from aura_sdk.logging.logger import get_logger\nlogger = get_logger('core.ok')\n",
    )
    _write(
        root / "services/llm-gateway/src/llm_gateway/ok.py",
        "from aura_sdk.logging.logger import get_logger\nlogger = get_logger('llm.ok')\n",
    )
    _write(
        root / "services/ws-server/src/ws_server/ok.py",
        "from aura_sdk.logging.logger import get_logger\nlogger = get_logger('ws.ok')\n",
    )
    _write(
        root / "plugins/audio-qualcomm/plugin.py",
        "from pathlib import Path\nfrom aura_sdk.plugins.interface import SubsystemPlugin\n",
    )
    _write(
        root / "agents/src/aura_agents/base.py",
        "\n".join(
            [
                "from aura_sdk.replay.recorder import TaskRecorder",
                "",
                "class BaseAgent:",
                "    def run(self):",
                "        self.recorder = TaskRecorder('/tmp/aura.db')",
                "        self.recorder.start_task('t','a',42,'m','r',{})",
                "        self.recorder.record_prompt('t','user','x')",
                "        self.recorder.record_response('t','y')",
                "        self.recorder.finalize('t', {'ok': True})",
                "",
            ]
        ),
    )
    _write(
        root / "agents/src/aura_agents/learning.py",
        "from aura_agents.base import BaseAgent\n\nclass LearningAgent(BaseAgent):\n    pass\n",
    )
    _write(
        root / "services/core/src/core/services/agent_runtime.py",
        "\n".join(
            [
                "from aura_sdk.logging.logger import get_logger",
                "logger = get_logger('core.runtime')",
                "cmd = ['--db-path', '/data/aura.db', '--seed', '42', '--model-version', 'gpt-test']",
                "",
            ]
        ),
    )


def _run(root: Path) -> dict[str, object]:
    return ArchitectureEnforcer(root).run()


def _has_rule(report: dict[str, object], rule_id: str) -> bool:
    return any(v["rule_id"] == rule_id for v in report["violations"])


def test_valid_layout_passes(tmp_path):
    _seed_valid_repo(tmp_path)
    report = _run(tmp_path)
    assert report["passed"] is True
    assert report["violation_count"] == 0


def test_forbidden_import_is_detected(tmp_path):
    _seed_valid_repo(tmp_path)
    _write(tmp_path / "services/core/src/core/bad_import.py", "import redis\n")

    report = _run(tmp_path)
    assert report["passed"] is False
    assert _has_rule(report, "ARCH_FORBIDDEN_IMPORT")


def test_layer_boundary_violation_is_detected(tmp_path):
    _seed_valid_repo(tmp_path)
    _write(tmp_path / "services/core/src/core/bad_layer.py", "from llm_gateway.client import call\n")

    report = _run(tmp_path)
    assert report["passed"] is False
    assert _has_rule(report, "ARCH_LAYER_BOUNDARY")


def test_plugin_isolation_violation_is_detected(tmp_path):
    _seed_valid_repo(tmp_path)
    _write(tmp_path / "plugins/audio-qualcomm/bad_plugin.py", "import requests\n")

    report = _run(tmp_path)
    assert report["passed"] is False
    assert _has_rule(report, "ARCH_PLUGIN_ISOLATION")


def test_core_observability_requirement_is_detected(tmp_path):
    _seed_valid_repo(tmp_path)
    _write(tmp_path / "services/core/src/core/no_logger.py", "def x():\n    return 1\n")

    report = _run(tmp_path)
    assert report["passed"] is False
    assert _has_rule(report, "ARCH_OBSERVABILITY")


def test_replay_hook_requirement_detects_non_base_agent(tmp_path):
    _seed_valid_repo(tmp_path)
    _write(tmp_path / "agents/src/aura_agents/bad_agent.py", "class BadAgent:\n    pass\n")

    report = _run(tmp_path)
    assert report["passed"] is False
    assert _has_rule(report, "ARCH_REPLAY_HOOKS")
