# Real Reconstruction Validation - wsa883x

## Target Selection
Selected target: `wsa883x` from candidate set (`wsa883x`, `wsa884x`, `wcd938x`, `lpass_rx_macro`, `lpass_tx_macro`, `lpass_va_macro`).

Selection basis from existing KB evidence:
- Strongest review chain with explicit v1/v2/v3 evolution in lore index.
- Rich accepted-commit history including follow-up fixes.
- Highest prior reconstruction confidence among corpus drivers.

Evidence:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/lore_links/wsa883x.md`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/accepted_commits/wsa883x.md`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/wsa883x/patch_history.md`

## Phase 1 - Downstream-only Understanding Model
Input constraints used:
- Downstream code only
- AURA_KB rules/patterns/maintainer models/playbooks
- No upstream `wsa883x` source consulted for reconstruction decisions

Downstream ownership model extracted:
- Driver model: vendor SoundWire (`swr_driver`) probe/remove path, manual register/unregister.
  - Evidence: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/audio-kernel-ar/asoc/codecs/wsa883x/wsa883x.c:2208`, `:2215`, `:2216`, `:2230`
- Heavy probe responsibilities: supplies, pinctrl/reset, SWR devnum enumeration, IRQ provisioning, dynamic component/DAI naming, debugfs/procfs.
  - Evidence: `.../wsa883x.c:1806-1882`, `:1890-1981`, `:2024-2051`
- DAPM graph includes vendor transport gate (`SWR DAC_Port`) and speaker event hooks.
  - Evidence: `.../wsa883x.c:1256-1269`
- Machine-driver integration via exported `wsa883x_set_channel_map()` and multiple board files.
  - Evidence: `.../wsa883x.c:1271-1296`, `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/audio-kernel-ar/asoc/audio_machine.c:2209`, `:2217`
- PM model is primarily system sleep + vendor supply LPM transitions, not runtime autosuspend-oriented flow.
  - Evidence: `.../wsa883x.c:2141-2190`

## Phase 2 - Upstream Freeze
Upstream answer-key files were frozen and not used during reconstruction drafting:
- `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/sound/soc/codecs/wsa883x.c`
- `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/Documentation/devicetree/bindings/sound/qcom,wsa883x.yaml`

## Phase 3 - Blind Reconstruction (Downstream + KB Only)
Predicted upstream-quality reconstruction:
1. Convert SWR transport ownership to generic SoundWire slave model (`sdw_driver` + `sdw_slave_ops`).
2. Replace custom/manual registration with devm-managed component registration.
3. Keep minimal codec DAPM graph (`IN -> SPKR`) with explicit controls for SoundWire port enable.
4. Introduce runtime PM with autosuspend and regcache runtime suspend/resume.
5. Move static port wiring from machine-driver helper calls to DT/property based mapping (`qcom,port-mapping`).
6. Split patch series: DT binding -> codec core -> controls/DAPM -> robustness follow-up.

KB evidence used for this reconstruction logic:
- Runtime PM rules: `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/runtime_pm_rules.md`
- SoundWire rules: `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/soundwire_rules.md`
- DAPM rules: `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/dapm_rules.md`
- Codec playbook: `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/playbooks/upstream_codec_driver.md`

Detailed reconstructed patch plan is in:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/validation/real_reconstruction_validation/20260614_002943_wsa883x/reconstructed_patch_series.md`

## Phase 4 - Patch Series Generation
Complete predicted series generated in:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/validation/real_reconstruction_validation/20260614_002943_wsa883x/reconstructed_patch_series.md`

## Phase 5 - Reviewer Feedback Prediction
Predicted reviewer feedback generated in:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/validation/real_reconstruction_validation/20260614_002943_wsa883x/reviewer_prediction_accuracy.md`

## Phase 6 - Reveal Real Upstream Implementation (Answer Key)
Ground truth observed after reconstruction lock:
- Uses generic SoundWire driver and slave ops:
  - `sdw_driver`: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/sound/soc/codecs/wsa883x.c:1717-1728`
  - `sdw_slave_ops`: `.../wsa883x.c:1126-1129`
- Uses devm component registration and static DAI descriptors:
  - `.../wsa883x.c:1674-1677`, `:1412-1426`
- Uses runtime PM autosuspend + regcache runtime callbacks:
  - `.../wsa883x.c:1668-1672`, `:1686-1708`
- Parses DT port mapping and supports reset-gpios/backward compatible powerdown-gpios in binding:
  - Driver parse: `.../wsa883x.c:1635-1637`
  - Binding: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/Documentation/devicetree/bindings/sound/qcom,wsa883x.yaml:39-46`, `:60-64`
- Uses minimal DAPM route + explicit controls for switchable ports:
  - `.../wsa883x.c:1301-1325`, `:1306-1321`

## Phase 7 - Reconstruction vs Reality
Detailed delta matrix and quantitative scoring are in:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/validation/real_reconstruction_validation/20260614_002943_wsa883x/reconstruction_vs_upstream_delta.md`

Reviewer prediction scoring is in:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/validation/real_reconstruction_validation/20260614_002943_wsa883x/reviewer_prediction_accuracy.md`

Final readiness decision is in:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/validation/real_reconstruction_validation/20260614_002943_wsa883x/conversion_readiness_report.md`

