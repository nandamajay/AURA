# WCD937x Dependency Graph Report

## Snapshot Anchors
- downstream_commit: `a89e32cf75ed4ef166c39caa1b39d8ec3818a633`
- upstream_tag: `v6.18` (`7d0a66e4bb9081d75c82ec4957c50034cb0ea449`)
- requested_path: `asoc/codecs/wcd9378/wcd937x.c` (not present)
- resolved_path: `asoc/codecs/wcd937x/wcd937x.c`

## Graph Summary
- node_count: 101
- edge_count: 190
- downstream_nodes: 26
- upstream_nodes: 13
- external_nodes: 62
- edge_type[build_ref]: 6
- edge_type[include]: 155
- edge_type[symbol_dep]: 19
- edge_type[upstream_map]: 10

## High-Risk Dependency Clusters
- Qualcomm local power/pinctrl abstractions: `msm_cdc_*` APIs and headers.
- SoundWire transport coupling: `swr_*` APIs and slave driver split (`wcd937x_slave.c`).
- Non-upstream debug/calibration hooks: `qti-regmap-debugfs`, `wcdcal-hwdep`.
- MBHC/CLSH helper coupling across shared downstream codec helpers.

## Upstream Mapping Edges (selected)
- `asoc/codecs/wcd937x/wcd937x.c` -> `sound/soc/codecs/wcd937x.c` (core codec logic refactor)
- `asoc/codecs/wcd937x/wcd937x_slave.c` -> `sound/soc/codecs/wcd937x-sdw.c` (SoundWire transport split)
- `asoc/codecs/wcd937x/wcd937x-mbhc.c` -> `sound/soc/codecs/wcd-mbhc-v2.c` (MBHC upstream framework alignment)
- `asoc/codecs/wcd937x/internal.h` -> `sound/soc/codecs/wcd937x.h` (private state struct migration)
- `asoc/codecs/wcd-clsh.c` -> `sound/soc/codecs/wcd-clsh-v2.c` (Class-H helper alignment)
- `include/asoc/wcd-mbhc-v2.h` -> `sound/soc/codecs/wcd-mbhc-v2.h` (MBHC API surface mapping)
- `asoc/codecs/Kbuild` -> `sound/soc/codecs/Kconfig` (build symbol integration)
- `asoc/codecs/Makefile` -> `sound/soc/codecs/Makefile` (obj list integration)
- `asoc/codecs/wcd937x/wcd937x.c` -> `Documentation/devicetree/bindings/sound/qcom,wcd937x.yaml` (DT property compatibility)
- `asoc/codecs/wcd937x/wcd937x_slave.c` -> `Documentation/devicetree/bindings/sound/qcom,wcd937x-sdw.yaml` (SDW DT compatibility)

## Artifact
- Full graph JSON: `artifacts/dependency_graph.json`
