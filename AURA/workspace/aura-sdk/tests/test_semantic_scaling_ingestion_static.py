from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.semantic_scaling_ingestion_engine import SemanticScalingIngestionEngine  # noqa: E402


def _build_source_tree(root: Path) -> None:
    (root / "sound/soc/qcom").mkdir(parents=True, exist_ok=True)
    (root / "sound/soc/codecs").mkdir(parents=True, exist_ok=True)
    (root / "techpack/audio").mkdir(parents=True, exist_ok=True)
    (root / "include/sound").mkdir(parents=True, exist_ok=True)

    (root / "include/sound/qcom-audio.h").write_text(
        """
        #ifndef __QCOM_AUDIO_H
        #define __QCOM_AUDIO_H
        #define QCOM_AUDIO_ROUTE_ID 42
        #endif
        """,
        encoding="utf-8",
    )
    (root / "sound/soc/qcom/msm-machine.c").write_text(
        """
        #include <sound/qcom-audio.h>
        static int msm_startup(void *substream) { return 0; }
        static int msm_hw_params(void *substream, void *params) { devm_clk_get(0, "rx"); return 0; }
        static int msm_prepare(void *substream) { clk_prepare_enable(0); return 0; }
        static int msm_trigger(void *substream, int cmd) {
          if (cmd == SNDRV_PCM_TRIGGER_START) return 0;
          if (cmd == SNDRV_PCM_TRIGGER_STOP) return 0;
          return 0;
        }
        static int msm_set_fmt(void *dai, unsigned int fmt) { return 0; }
        static int msm_set_sysclk(void *dai, int clk_id, unsigned int freq, int dir) { clk_get(0, "rx"); return 0; }
        static void msm_shutdown(void *substream) { }
        static struct snd_soc_dai_ops msm_test_dai_ops = {
          .startup = msm_startup,
          .hw_params = msm_hw_params,
          .prepare = msm_prepare,
          .trigger = msm_trigger,
          .set_fmt = msm_set_fmt,
          .set_sysclk = msm_set_sysclk,
          .shutdown = msm_shutdown,
        };
        static const struct snd_soc_dapm_widget msm_widgets[] = {
          SND_SOC_DAPM_AIF_IN("MultiMedia1 Playback", NULL, 0, 0, 0),
          SND_SOC_DAPM_SPK("RX_AIF", NULL),
        };
        static const struct snd_soc_dapm_route msm_routes[] = {
          { "RX_AIF", NULL, "MultiMedia1 Playback" },
        };
        static const struct snd_soc_dai_link msm_test_fe_links[] = { 0 };
        static const struct snd_soc_dai_link msm_test_be_links[] = { 0 };
        static int qcom_audio_startup(void) { return QCOM_AUDIO_ROUTE_ID; }
        """,
        encoding="utf-8",
    )
    (root / "sound/soc/codecs/wcd938x.c").write_text(
        """
        #include <sound/qcom-audio.h>
        #define WCD938X_CODEC 1
        static struct snd_kcontrol_new wcd_controls[] = {
          SOC_DAPM_SINGLE("RX MIXER", 0, 0, 1, 0),
          SOC_DAPM_ENUM("RX MUX", 0),
        };
        static int wcd938x_codec_probe(void) { return qcom_audio_startup(); }
        """,
        encoding="utf-8",
    )
    (root / "techpack/audio/tx-path.c").write_text(
        """
        #include <sound/qcom-audio.h>
        static int tx_open(void *substream) { return 0; }
        static int tx_hw_params(void *substream, void *params) { devm_clk_get(0, "tx"); return 0; }
        static int tx_prepare(void *substream) { clk_prepare_enable(0); return 0; }
        static int tx_trigger(void *substream, int cmd) {
          if (cmd == SNDRV_PCM_TRIGGER_START) return 0;
          if (cmd == SNDRV_PCM_TRIGGER_STOP) return 0;
          return 0;
        }
        static int tx_close(void *substream) { return 0; }
        static struct snd_pcm_ops tx_pcm_ops = {
          .open = tx_open,
          .hw_params = tx_hw_params,
          .prepare = tx_prepare,
          .trigger = tx_trigger,
          .close = tx_close,
        };
        static int tx_capture_enable(void) { return QCOM_AUDIO_ROUTE_ID; }
        """,
        encoding="utf-8",
    )


def test_semantic_scaling_deterministic_and_incremental(tmp_path: Path) -> None:
    source_root = tmp_path / "linux"
    output_dir = tmp_path / "out"
    cache_file = output_dir / "semantic_cache_state.json"
    _build_source_tree(source_root)

    engine = SemanticScalingIngestionEngine()
    one = asyncio.run(
        engine.run(
            source_root=source_root,
            output_dir=output_dir,
            cache_file=cache_file,
            workers=2,
        )
    )
    two = asyncio.run(
        engine.run(
            source_root=source_root,
            output_dir=output_dir,
            cache_file=cache_file,
            workers=2,
        )
    )

    assert one.summary["classification"] == "PASS"
    assert two.summary["classification"] == "PASS"
    assert one.discovery_registry["files"] == two.discovery_registry["files"]
    assert one.include_dependency_graph["deterministic_fingerprint"] == two.include_dependency_graph["deterministic_fingerprint"]
    assert one.function_call_graph["deterministic_fingerprint"] == two.function_call_graph["deterministic_fingerprint"]
    assert one.topology_model["deterministic_fingerprint"] == two.topology_model["deterministic_fingerprint"]
    assert one.behavioral_state_graph["edge_count"] > 0
    assert one.activation_order_graph["edge_count"] > 0
    assert one.runtime_causality_graph["edge_count"] > 0
    assert one.power_sequence_graph["edge_count"] > 0
    assert one.stream_intelligence_report["classification"] == "PASS"
    assert one.governance_confidence_report["overall_confidence_score"] >= 0.7
    assert two.incremental_ingestion_report["reparsed_file_count"] == 0
    assert two.incremental_ingestion_report["reused_file_count"] == len(two.discovery_registry["files"])

    include_edges = two.inter_driver_dependency_graph["edges"]
    assert any(
        edge["source"].endswith("msm-machine.c")
        and edge["target"].endswith("qcom-audio.h")
        for edge in include_edges
    )

    header = source_root / "include/sound/qcom-audio.h"
    header.write_text(
        """
        #ifndef __QCOM_AUDIO_H
        #define __QCOM_AUDIO_H
        #define QCOM_AUDIO_ROUTE_ID 108
        #endif
        """,
        encoding="utf-8",
    )
    three = asyncio.run(
        engine.run(
            source_root=source_root,
            output_dir=output_dir,
            cache_file=cache_file,
            workers=2,
        )
    )
    changed = set(three.incremental_ingestion_report["changed_files"])
    dependents = set(three.incremental_ingestion_report["header_invalidation_dependents"])
    reparsed = set(three.incremental_ingestion_report["reparsed_files"])
    assert "include/sound/qcom-audio.h" in changed
    assert "sound/soc/qcom/msm-machine.c" in dependents
    assert "sound/soc/codecs/wcd938x.c" in dependents
    assert "techpack/audio/tx-path.c" in dependents
    assert "sound/soc/qcom/msm-machine.c" in reparsed


def test_semantic_scaling_fail_closed_empty_source(tmp_path: Path) -> None:
    source_root = tmp_path / "empty"
    source_root.mkdir(parents=True, exist_ok=True)
    output_dir = tmp_path / "out"

    result = asyncio.run(
        SemanticScalingIngestionEngine().run(
            source_root=source_root,
            output_dir=output_dir,
            workers=1,
        )
    )
    assert result.summary["classification"] == "FAIL_CLOSED"
    assert "no_eligible_source_files_discovered" in result.summary["fail_closed_reasons"]
    report = json.loads((output_dir / "semantic_scaling_summary.json").read_text(encoding="utf-8"))
    assert report["classification"] == "FAIL_CLOSED"


def test_semantic_scaling_fail_closed_unknown_topology_widget(tmp_path: Path) -> None:
    source_root = tmp_path / "linux"
    (source_root / "sound/soc/qcom").mkdir(parents=True, exist_ok=True)
    (source_root / "include/sound").mkdir(parents=True, exist_ok=True)
    (source_root / "include/sound/min.h").write_text("#define X 1\n", encoding="utf-8")
    (source_root / "sound/soc/qcom/unsafe.c").write_text(
        """
        #include <sound/min.h>
        static const struct snd_soc_dapm_widget msm_widgets[] = {
          SND_SOC_DAPM_AIF_IN("SafeWidget", NULL, 0, 0, 0),
        };
        static const struct snd_soc_dapm_route msm_routes[] = {
          { "SafeWidget", NULL, "MissingSourceWidget" },
        };
        """,
        encoding="utf-8",
    )
    out = tmp_path / "out"
    result = asyncio.run(
        SemanticScalingIngestionEngine().run(
            source_root=source_root,
            output_dir=out,
            workers=1,
        )
    )
    assert result.topology_model["classification"] == "FAIL_CLOSED"
    assert "topology_references_unknown_widgets" in result.topology_model["fail_closed_reasons"]
    assert result.summary["classification"] == "FAIL_CLOSED"


def test_semantic_scaling_fail_closed_missing_clock_dependency(tmp_path: Path) -> None:
    source_root = tmp_path / "linux"
    (source_root / "sound/soc/qcom").mkdir(parents=True, exist_ok=True)
    (source_root / "include/sound").mkdir(parents=True, exist_ok=True)
    (source_root / "include/sound/min.h").write_text("#define X 1\n", encoding="utf-8")
    (source_root / "sound/soc/qcom/missing-clock.c").write_text(
        """
        #include <sound/min.h>
        static int no_clk_startup(void *substream) { return 0; }
        static int no_clk_hw_params(void *substream, void *params) { return 0; }
        static int no_clk_trigger(void *substream, int cmd) { return 0; }
        static struct snd_pcm_ops no_clk_ops = {
          .startup = no_clk_startup,
          .hw_params = no_clk_hw_params,
          .trigger = no_clk_trigger,
        };
        static const struct snd_soc_dapm_widget msm_widgets[] = {
          SND_SOC_DAPM_AIF_IN("Capture", NULL, 0, 0, 0),
          SND_SOC_DAPM_SPK("TX_AIF", NULL),
        };
        static const struct snd_soc_dapm_route msm_routes[] = {
          { "TX_AIF", NULL, "Capture" },
        };
        """,
        encoding="utf-8",
    )
    out = tmp_path / "out"
    result = asyncio.run(
        SemanticScalingIngestionEngine().run(
            source_root=source_root,
            output_dir=out,
            workers=1,
        )
    )
    assert result.stream_intelligence_report["classification"] == "FAIL_CLOSED"
    assert "missing_clock_dependency_callbacks" in result.stream_intelligence_report["fail_closed_reasons"]
    assert result.governance_confidence_report["classification"] == "FAIL_CLOSED"
