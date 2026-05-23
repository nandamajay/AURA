from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.kernel_structural_cognition import (  # noqa: E402
    KernelStructuralCognitionPlanner,
    KernelStructuralCognitionRegistry,
)
from aura_sdk.transport.plugins import TargetPluginLoader, build_simulation_registry_payload  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _loader(tmp_path: Path) -> TargetPluginLoader:
    path = tmp_path / "simulation_registry.json"
    _write_json(path, build_simulation_registry_payload())
    return TargetPluginLoader(registry_path=path)


def _fixture_downstream(tmp_path: Path) -> Path:
    root = tmp_path / "downstream"
    (root / "sound/soc/qcom").mkdir(parents=True, exist_ok=True)
    (root / "arch/arm64/boot/dts/qcom").mkdir(parents=True, exist_ok=True)

    (root / "sound/soc/qcom/Kconfig").write_text(
        """
        config SND_SOC_TEST_MACHINE
            tristate "Test machine"
        source "sound/soc/codecs/Kconfig"
        """,
        encoding="utf-8",
    )

    (root / "sound/soc/qcom/Makefile").write_text(
        """
        obj-$(CONFIG_SND_SOC_TEST_MACHINE) += test_machine.o
        test_machine-y := test_machine_core.o test_machine_routes.o
        """,
        encoding="utf-8",
    )

    (root / "arch/arm64/boot/dts/qcom/test-board-audio.dtsi").write_text(
        """
        #include "test-codec.dtsi"

        sound: sound {
            compatible = "qcom,test-audio";
            audio-routing = "RX0", "SPK";
            qcom,dai-link@0 {
                link-name = "test_fe_link";
            };
        };

        swr-master@0 {
            compatible = "qcom,swr-master";
        };
        """,
        encoding="utf-8",
    )

    (root / "sound/soc/qcom/test_machine.c").write_text(
        """
        #include <sound/soc.h>
        #include <soc/soundwire.h>

        static int test_startup(struct snd_pcm_substream *substream) { return 0; }
        static int test_hw_params(struct snd_pcm_substream *substream, struct snd_pcm_hw_params *params) { return 0; }
        static int test_trigger(struct snd_pcm_substream *substream, int cmd) { return 0; }
        static int test_shutdown(struct snd_pcm_substream *substream) { return 0; }

        static const struct snd_soc_ops test_machine_be_ops = {
            .startup = test_startup,
            .hw_params = test_hw_params,
            .trigger = test_trigger,
            .shutdown = test_shutdown,
        };

        static int test_component_probe(struct snd_soc_component *component) { return 0; }
        static void test_component_remove(struct snd_soc_component *component) {}

        static const struct snd_soc_component_driver test_component_driver = {
            .probe = test_component_probe,
            .remove = test_component_remove,
        };

        static struct snd_soc_dai_link test_machine_fe_dai_links[] = { {0}, };
        static struct snd_soc_dai_link test_machine_be_dai_links[] = { {0}, };

        static const struct snd_soc_dapm_widget test_widgets[] = {
            SND_SOC_DAPM_SPK("SPK", NULL),
        };

        static const struct snd_soc_dapm_route test_routes[] = {
            { "SPK", NULL, "RX0" },
        };

        static int vendor_hook_audio_fixup(void) { return 0; }
        static int trace_android_vh_audio_path(void) { return 0; }

        static int test_machine_probe(struct platform_device *pdev)
        {
            devm_snd_soc_register_component(&pdev->dev, &test_component_driver, NULL, 0);
            snd_soc_register_card(NULL);
            return 0;
        }

        module_platform_driver(test_machine_driver);
        """,
        encoding="utf-8",
    )

    return root


def _fixture_upstream(tmp_path: Path) -> Path:
    root = tmp_path / "upstream"
    (root / "sound/soc").mkdir(parents=True, exist_ok=True)
    (root / "include/sound").mkdir(parents=True, exist_ok=True)
    (root / "drivers/soundwire").mkdir(parents=True, exist_ok=True)

    (root / "sound/soc/soc-core.c").write_text(
        """
        struct snd_soc_component { int dummy; };
        struct snd_soc_component_driver { int dummy; };
        struct snd_soc_dai_link { int dummy; };
        struct snd_soc_ops { int dummy; };
        int snd_soc_register_component(void) { return 0; }
        int snd_soc_register_card(void) { return 0; }
        """,
        encoding="utf-8",
    )

    (root / "include/sound/soc-dapm.h").write_text(
        """
        struct snd_soc_dapm_widget { int dummy; };
        struct snd_soc_dapm_route { int dummy; };
        """,
        encoding="utf-8",
    )

    (root / "drivers/soundwire/bus.c").write_text(
        """
        int soundwire_bus_init(void) { return 0; }
        """,
        encoding="utf-8",
    )

    return root


def _runtime_payload() -> dict:
    return {
        "run_id": "run-structural-1",
        "process_success": True,
        "playback_completion": True,
        "classification": "PASS",
        "playback_runtime_seconds": 25.0,
        "expected_runtime_seconds": 25.0,
        "route_fingerprint": "route-fp-structural-1",
        "command_sequence": [
            "collect_runtime_evidence",
            "resolve_pcm",
            "validate_route",
        ],
        "deterministic_event_ordering": True,
        "deterministic_replay_fingerprint": "replay-fp-structural-1",
    }


def _governance_payload() -> dict:
    return {
        "fail_closed_posture": True,
        "autonomous_patching_allowed": False,
        "autonomous_topology_rewrite_allowed": False,
        "autonomous_runtime_mutation_allowed": False,
        "autonomous_upstream_generation_allowed": False,
    }


def test_kernel_structural_cognition_required_artifacts_and_determinism(tmp_path: Path) -> None:
    planner = KernelStructuralCognitionPlanner(_loader(tmp_path))
    downstream = _fixture_downstream(tmp_path)
    upstream = _fixture_upstream(tmp_path)

    args = {
        "target_id": "fake_target_alpha",
        "downstream_root": downstream,
        "upstream_root": upstream,
        "runtime_evidence": _runtime_payload(),
        "governance_state": _governance_payload(),
        "lineage_id": "kernel-structural-v1",
        "evidence_references": ["test://structural/v1"],
    }

    first = planner.analyze(**args).structural_bundle
    second = planner.analyze(**args).structural_bundle

    assert first["structural_fingerprint"] == second["structural_fingerprint"]

    artifacts = first["artifacts"]
    required = {
        "structural_graph",
        "driver_registration_graph",
        "topology_structure_graph",
        "runtime_source_correlation",
        "downstream_hook_inventory",
        "upstream_equivalence_trace",
        "portability_blocker_graph",
        "callback_chain_graph",
        "deterministic_structural_fingerprint",
    }
    assert required.issubset(set(artifacts.keys()))

    assert artifacts["driver_registration_graph"]["summary"]["registration_calls"] >= 1
    assert artifacts["topology_structure_graph"]["summary"]["frontend_count"] >= 1
    assert artifacts["upstream_equivalence_trace"]["summary"]["total"] >= 1


def test_kernel_structural_registry_replay(tmp_path: Path) -> None:
    planner = KernelStructuralCognitionPlanner(_loader(tmp_path))
    bundle = planner.analyze(
        target_id="fake_target_alpha",
        downstream_root=_fixture_downstream(tmp_path),
        upstream_root=_fixture_upstream(tmp_path),
        runtime_evidence=_runtime_payload(),
        governance_state=_governance_payload(),
        lineage_id="kernel-structural-replay-v1",
        evidence_references=["test://structural/replay"],
    ).structural_bundle

    registry = KernelStructuralCognitionRegistry(
        cognition_registry_path=tmp_path / "registry.json",
        output_dir=tmp_path / "ops",
    )

    persisted = registry.persist(bundle)
    replay_one = registry.replay(lineage_id="kernel-structural-replay-v1")
    replay_two = registry.replay(lineage_id="kernel-structural-replay-v1")

    assert persisted["lineage_id"] == "kernel-structural-replay-v1"
    assert replay_one["deterministic_replay_fingerprint"] == replay_two["deterministic_replay_fingerprint"]
    assert (tmp_path / "ops" / "structural_graph.json").exists()
    assert (tmp_path / "ops" / "deterministic_structural_fingerprint.json").exists()


def test_kernel_structural_governance_fail_closed(tmp_path: Path) -> None:
    planner = KernelStructuralCognitionPlanner(_loader(tmp_path))

    governance = _governance_payload()
    governance["autonomous_patching_allowed"] = True

    bundle = planner.analyze(
        target_id="fake_target_alpha",
        downstream_root=_fixture_downstream(tmp_path),
        upstream_root=_fixture_upstream(tmp_path),
        runtime_evidence=_runtime_payload(),
        governance_state=governance,
        lineage_id="kernel-structural-governance-v1",
        evidence_references=["test://structural/governance"],
    ).structural_bundle

    assert bundle["governance_boundaries"]["classification"] == "FAIL_CLOSED"
    assert bundle["artifacts"]["deterministic_structural_fingerprint"]["classification"] == "FAIL_CLOSED"


def test_kernel_structural_core_plugin_isolation() -> None:
    src = (SRC_DIR / "aura_sdk/transport/kernel_structural_cognition.py").read_text(encoding="utf-8").lower()

    assert "if target ==" not in src
    assert "rb3" not in src
    assert ".structural_cognition_adapter(" in src
