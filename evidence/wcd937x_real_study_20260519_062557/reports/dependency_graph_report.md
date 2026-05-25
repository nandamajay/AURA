# Dependency Graph Report

## Focus Driver
- `asoc/codecs/wcd937x/wcd937x.c`

## Graph Summary
- nodes: `123`
- edges: `253`
- edge types: `{'api_usage': 144, 'build_ref': 11, 'direct_external_include': 40, 'direct_include': 16, 'indirect_external_include': 30, 'indirect_include': 12}`

## Dependency Tree Excerpt
- `asoc/codecs/wcd937x/wcd937x.c`
- `  - asoc/codecs/wcd937x/internal.h`
- `    - asoc/codecs/wcd937x/wcd937x-mbhc.h`
- `    - asoc/codecs/wcd937x/wcd937x.h`
- `    - include/asoc/wcd-clsh.h`
- `    - include/asoc/wcd-irq.h`
- `    - include/asoc/wcd-mbhc-v2.h`
- `    - include/soc/soundwire.h`
- `  - asoc/codecs/wcd937x/wcd937x-registers.h`
- `  - asoc/codecs/wcd937x/wcd937x.h`
- `    - include/bindings/audio-codec-port-types.h`
- `  - include/asoc/bolero-slave-internal.h`
- `  - include/asoc/msm-cdc-pinctrl.h`
- `    - linux/of.h`
- `    - linux/types.h`
- `  - include/asoc/msm-cdc-supply.h`
- `    - linux/kernel.h`
- `    - linux/regulator/consumer.h`
- `    - linux/slab.h`
- `  - include/asoc/wcdcal-hwdep.h`
- `    - sound/msmcal-hwdep.h`
- `    - sound/msmcal-hwdep.h`
- `    - sound/msmcal-hwdep.h`
- `  - include/bindings/audio-codec-port-types.h`
- `  - include/soc/soundwire.h`
- `    - include/soc/audio_mod_devicetable.h`
- `    - linux/device.h`
- `    - linux/irqdomain.h`
- `    - linux/mutex.h`
- `    - linux/regmap.h`
- `    - linux/version.h`
- `  - linux/component.h`
- `  - linux/delay.h`
- `  - linux/device.h`
- `  - linux/kernel.h`
- `  - linux/module.h`
- `  - linux/platform_device.h`
- `  - linux/pm_runtime.h`
- `  - linux/qti-regmap-debugfs.h`
- `  - linux/regmap.h`
- `  - linux/slab.h`
- `  - linux/version.h`
- `  - sound/soc-dapm.h`
- `  - sound/soc.h`
- `  - sound/soc.h`
- `  - sound/tlv.h`

## Platform Coupling Observations
- includes and API usage show strong coupling to `msm_cdc_*`, `swr_*`, `wcd_mbhc_*`, `wcd_clsh`, `wcd_irq_*`, `wcdcal_*`, and bolero internals.

## Unresolved Blockers
- indirect dependencies outside scanned scope still possible
- full transitive compile closure unverified due environment compile limitations

## Artifacts
- `artifacts/downstream_dependency_graph.json`
- `artifacts/downstream_snapshot_paths.txt`
- `artifacts/downstream_snapshot_sha256.txt`
