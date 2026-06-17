"""Tests for deterministic conversion scoring."""

from __future__ import annotations

import json
from pathlib import Path

from aura_agents.conversion_scoring import render_score_json, score_conversion


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _sample_source() -> str:
    return """
#include <linux/module.h>
#include "sound/soc.h"

#define CDC_VA_REG0 0x00
#define WSA_COMP_REG1 0x04

static int demo_component_probe(struct snd_soc_component *c)
{
    dev_dbg(NULL, "x");
    return 0;
}

static int demo_probe(struct platform_device *pdev)
{
    of_property_read_u32(NULL, "gain-step", NULL);
    device_property_read_u32(NULL, "mode-select", NULL);
    devm_regmap_init_mmio(NULL, NULL, NULL);
    devm_snd_soc_register_component(NULL, NULL, NULL, 0);
    pm_runtime_enable(NULL);
    return devm_kzalloc(NULL, 1, 0) ? 0 : 0;
}

static int demo_remove(struct platform_device *pdev)
{
    return 0;
}

static int demo_runtime_suspend(struct device *dev)
{
    return 0;
}

static int demo_runtime_resume(struct device *dev)
{
    return 0;
}

static const struct snd_soc_dapm_widget demo_widgets[] = {
    SND_SOC_DAPM_INPUT("IN"),
    SND_SOC_DAPM_OUTPUT("OUT"),
    SND_SOC_DAPM_MIXER("MX", 0, 0, NULL, 0),
};

static const struct snd_soc_dapm_route demo_routes[] = {
    {"OUT", NULL, "MX"},
    {"MX", NULL, "IN"},
};

static const struct snd_kcontrol_new demo_controls[] = {
    SOC_SINGLE("Volume", CDC_VA_REG0, 0, 0xff, 0),
    SOC_ENUM("Mode", NULL),
};

static const struct of_device_id demo_of_match[] = {
    { .compatible = "qcom,demo" },
    {}
};
MODULE_DEVICE_TABLE(of, demo_of_match);

static const struct dev_pm_ops demo_pm_ops = {
    SET_RUNTIME_PM_OPS(demo_runtime_suspend, demo_runtime_resume, NULL)
};

module_platform_driver(demo_driver);
"""


def test_identical_files_all_100(tmp_path: Path):
    upstream = _write(tmp_path / "upstream.c", _sample_source())
    converted = _write(tmp_path / "converted.c", _sample_source())

    report = score_conversion(converted, upstream)

    for category in report["categories"].values():
        assert category["score"] == 100.0
    assert report["overall"]["score"] == 100.0


def test_empty_converted_has_zero_overlap_scores(tmp_path: Path):
    upstream = _write(tmp_path / "upstream.c", _sample_source())
    converted = _write(tmp_path / "converted.c", "")

    report = score_conversion(converted, upstream)
    categories = report["categories"]

    assert categories["FUNCTION_MATCH"]["score"] == 0.0
    assert categories["API_COVERAGE"]["score"] == 0.0
    assert categories["REGISTER_COVERAGE"]["score"] == 0.0
    assert categories["DAPM_WIDGETS"]["score"] == 0.0
    assert categories["DAPM_ROUTES"]["score"] == 0.0
    assert categories["DAPM_CONTROLS"]["score"] == 0.0
    assert categories["LIFECYCLE_PATTERN"]["score"] == 0.0
    assert categories["DT_PROPERTY_COVERAGE"]["score"] == 0.0
    assert categories["INCLUDE_ALIGNMENT"]["score"] == 0.0


def test_vendor_elimination_zero_when_banned_symbol_present(tmp_path: Path):
    upstream = _write(tmp_path / "upstream.c", _sample_source())
    converted = _write(tmp_path / "converted.c", _sample_source() + "\nmsm_cdc_pinctrl = 1;\n")

    report = score_conversion(converted, upstream)

    assert report["categories"]["VENDOR_ELIMINATION"]["score"] == 0.0
    assert report["categories"]["VENDOR_ELIMINATION"]["total_occurrences"] > 0


def test_known_function_overlap_exact_arithmetic(tmp_path: Path):
    upstream_text = """
static int f1(void) { return 0; }
static int f2(void) { return 0; }
static int f3(void) { return 0; }
static int f4(void) { return 0; }
static int f5(void) { return 0; }
"""
    converted_text = """
static int f1(void) { return 0; }
static int f2(void) { return 0; }
static int f3(void) { return 0; }
"""
    upstream = _write(tmp_path / "upstream.c", upstream_text)
    converted = _write(tmp_path / "converted.c", converted_text)

    report = score_conversion(converted, upstream)

    assert report["categories"]["FUNCTION_MATCH"]["upstream_count"] == 5
    assert report["categories"]["FUNCTION_MATCH"]["matched_count"] == 3
    assert report["categories"]["FUNCTION_MATCH"]["score"] == 60.0

    category_scores = [report["categories"][name]["score"] for name in report["categories"]]
    expected_overall = round(sum(float(v) for v in category_scores) / len(category_scores), 2)
    assert report["overall"]["score"] == expected_overall


def test_determinism_bit_identical_json(tmp_path: Path):
    upstream = _write(tmp_path / "upstream.c", _sample_source())
    converted = _write(tmp_path / "converted.c", _sample_source())

    first = score_conversion(converted, upstream)
    second = score_conversion(converted, upstream)

    assert render_score_json(first) == render_score_json(second)
    assert json.loads(render_score_json(first)) == json.loads(render_score_json(second))
