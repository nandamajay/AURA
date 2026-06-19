"""Tests for multi-file conversion scoring (v4)."""

from __future__ import annotations

import json
from pathlib import Path

from aura_agents.multifile_scoring import (
    render_multifile_score_json,
    score_multifile,
    _stem_normalize,
    _auto_pair_files,
)


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


SIMPLE_SOURCE = """
#include <linux/module.h>

#define CDC_RX_REG0 0x00

static int demo_probe(struct platform_device *pdev)
{
    devm_regmap_init_mmio(NULL, NULL, NULL);
    devm_snd_soc_register_component(NULL, NULL, NULL, 0);
    return 0;
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
};

static const struct snd_soc_dapm_route demo_routes[] = {
    {"OUT", NULL, "IN"},
};

static const struct snd_kcontrol_new demo_controls[] = {
    SOC_SINGLE("Vol", CDC_RX_REG0, 0, 0xff, 0),
};

static const struct of_device_id demo_of_match[] = {
    { .compatible = "qcom,demo" },
    {}
};

static const struct dev_pm_ops demo_pm_ops = {
    SET_RUNTIME_PM_OPS(demo_runtime_suspend, demo_runtime_resume, NULL)
};

module_platform_driver(demo_driver);
"""


def test_stem_normalize():
    assert _stem_normalize("wcd937x_slave.c") == "wcd937x-slave"
    assert _stem_normalize("wcd937x-sdw.c") == "wcd937x-sdw"
    assert _stem_normalize("LPASS-CDC-RX-Macro.c") == "lpass-cdc-rx-macro"


def test_identical_single_file_dirs(tmp_path: Path):
    """Two dirs with identical single file should score 100."""
    up_dir = tmp_path / "upstream"
    cv_dir = tmp_path / "converted"
    up_dir.mkdir()
    cv_dir.mkdir()

    _write(up_dir / "driver.c", SIMPLE_SOURCE)
    _write(cv_dir / "driver.c", SIMPLE_SOURCE)

    report = score_multifile(up_dir, cv_dir)

    assert report["file_pairing"]["paired_source_files"] == 1
    assert report["file_pairing"]["unpaired_upstream_source_files"] == 0
    assert report["aggregate"]["overall"] == 100.0


def test_unpaired_upstream_file_scores_zero(tmp_path: Path):
    """Upstream file with no converted match should contribute 0."""
    up_dir = tmp_path / "upstream"
    cv_dir = tmp_path / "converted"
    up_dir.mkdir()
    cv_dir.mkdir()

    _write(up_dir / "main.c", SIMPLE_SOURCE)
    _write(up_dir / "extra.c", SIMPLE_SOURCE)
    _write(cv_dir / "main.c", SIMPLE_SOURCE)
    # extra.c has no pair

    report = score_multifile(up_dir, cv_dir)

    assert report["file_pairing"]["paired_source_files"] == 1
    assert report["file_pairing"]["unpaired_upstream_source_files"] == 1
    # Aggregate should be ~50% (one file 100%, one file 0%, equal weight)
    assert 45.0 <= report["aggregate"]["overall"] <= 55.0


def test_weighted_by_line_count(tmp_path: Path):
    """Larger upstream file should have more weight in aggregate."""
    up_dir = tmp_path / "upstream"
    cv_dir = tmp_path / "converted"
    up_dir.mkdir()
    cv_dir.mkdir()

    # Small file (10 lines) - will score 100
    small_source = "static int f1(void) { return 0; }\n" * 10
    _write(up_dir / "small.c", small_source)
    _write(cv_dir / "small.c", small_source)

    # Large file (100 lines) - unpaired, scores 0
    large_source = "static int f1(void) { return 0; }\n" * 100
    _write(up_dir / "large.c", large_source)

    report = score_multifile(up_dir, cv_dir)

    # Weight: small=10, large=100. Aggregate = (100*10 + 0*100) / 110 ≈ 9.09
    assert report["aggregate"]["overall"] < 15.0


def test_file_map_explicit_pairing(tmp_path: Path):
    """Explicit file map should pair renamed files."""
    up_dir = tmp_path / "upstream"
    cv_dir = tmp_path / "converted"
    up_dir.mkdir()
    cv_dir.mkdir()

    _write(up_dir / "wcd937x-sdw.c", SIMPLE_SOURCE)
    _write(cv_dir / "wcd937x_slave.c", SIMPLE_SOURCE)

    # Without map: won't pair (sdw != slave)
    report_no_map = score_multifile(up_dir, cv_dir)
    assert report_no_map["file_pairing"]["paired_source_files"] == 0

    # With map: should pair
    map_file = _write(
        tmp_path / "map.json",
        json.dumps({"wcd937x-sdw.c": "wcd937x_slave.c"})
    )
    report_with_map = score_multifile(up_dir, cv_dir, file_map_path=map_file)
    assert report_with_map["file_pairing"]["paired_source_files"] == 1
    assert report_with_map["aggregate"]["overall"] == 100.0


def test_multi_file_three_sources(tmp_path: Path):
    """Three source files, all paired identically."""
    up_dir = tmp_path / "upstream"
    cv_dir = tmp_path / "converted"
    up_dir.mkdir()
    cv_dir.mkdir()

    for name in ["main.c", "sdw.c", "utils.c"]:
        _write(up_dir / name, SIMPLE_SOURCE)
        _write(cv_dir / name, SIMPLE_SOURCE)

    report = score_multifile(up_dir, cv_dir)

    assert report["file_pairing"]["paired_source_files"] == 3
    assert report["aggregate"]["overall"] == 100.0


def test_headers_not_scored_as_source(tmp_path: Path):
    """Header files should not appear as scored source files."""
    up_dir = tmp_path / "upstream"
    cv_dir = tmp_path / "converted"
    up_dir.mkdir()
    cv_dir.mkdir()

    _write(up_dir / "driver.c", SIMPLE_SOURCE)
    _write(up_dir / "driver.h", "#define FOO 1\n")
    _write(cv_dir / "driver.c", SIMPLE_SOURCE)
    _write(cv_dir / "driver.h", "#define FOO 1\n")

    report = score_multifile(up_dir, cv_dir)

    # Only .c should be scored
    assert report["file_pairing"]["paired_source_files"] == 1
    # Headers should be in paired_header_files
    assert report["file_pairing"]["paired_header_files"] == 1


def test_determinism(tmp_path: Path):
    """Two identical runs must produce identical output."""
    up_dir = tmp_path / "upstream"
    cv_dir = tmp_path / "converted"
    up_dir.mkdir()
    cv_dir.mkdir()

    _write(up_dir / "driver.c", SIMPLE_SOURCE)
    _write(cv_dir / "driver.c", SIMPLE_SOURCE)

    report1 = score_multifile(up_dir, cv_dir)
    report2 = score_multifile(up_dir, cv_dir)

    json1 = render_multifile_score_json(report1)
    json2 = render_multifile_score_json(report2)
    assert json1 == json2


def test_empty_converted_dir(tmp_path: Path):
    """All upstream files unpaired should score 0 overall."""
    up_dir = tmp_path / "upstream"
    cv_dir = tmp_path / "converted"
    up_dir.mkdir()
    cv_dir.mkdir()

    _write(up_dir / "driver.c", SIMPLE_SOURCE)

    report = score_multifile(up_dir, cv_dir)

    assert report["file_pairing"]["paired_source_files"] == 0
    assert report["file_pairing"]["unpaired_upstream_source_files"] == 1
    assert report["aggregate"]["overall"] == 0.0


def test_per_file_reports_contain_all_categories(tmp_path: Path):
    """Each per-file report should have all 10 scoring categories."""
    up_dir = tmp_path / "upstream"
    cv_dir = tmp_path / "converted"
    up_dir.mkdir()
    cv_dir.mkdir()

    _write(up_dir / "driver.c", SIMPLE_SOURCE)
    _write(cv_dir / "driver.c", SIMPLE_SOURCE)

    report = score_multifile(up_dir, cv_dir)

    for file_report in report["per_file_scores"]:
        assert len(file_report["categories"]) == 10


def test_auto_pair_ignores_case_normalization(tmp_path: Path):
    """Auto-pairing should match despite underscore/hyphen differences."""
    up_dir = tmp_path / "upstream"
    cv_dir = tmp_path / "converted"
    up_dir.mkdir()
    cv_dir.mkdir()

    _write(up_dir / "wcd-codec.c", SIMPLE_SOURCE)
    _write(cv_dir / "wcd_codec.c", SIMPLE_SOURCE)

    paired, unpaired_up, unpaired_cv = _auto_pair_files(
        up_dir, cv_dir,
        upstream_extensions=(".c",),
        converted_extensions=(".c",),
    )
    assert len(paired) == 1
    assert len(unpaired_up) == 0
    assert len(unpaired_cv) == 0
