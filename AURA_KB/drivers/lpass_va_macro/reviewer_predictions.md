# lpass_va_macro Reviewer Predictions

Classification: **PASS**
Evidence mode: **online_patchwork**
Patchwork API: `https://patchwork.kernel.org/api/1.2`

## Evidence Acquisition
- Candidate series: 176
- Selected series: 60
- Fetched series: 60
- Target reviewer interactions: `{"Krzysztof Kozlowski": 29, "Mark Brown": 10, "Pierre-Louis Bossart": 54}`
- Scope queries: `["ASoC: qcom: lpass", "ASoC: codecs: lpass-va-macro", "soundwire: qcom"]`

## Overall Prediction
- Recommended patch count: **7**
- Split request probability: **0.262**
- Predicted review rounds to acceptance: **3**
- Predicted acceptance probability: **0.930**
- Primary risk drivers: soundwire ownership boundary, runtime PM sequencing evidence, feature/refactor mixing, DT binding scope creep

## Per-Reviewer Preferences
### Mark Brown
- Series score: 0.162
- Profile interactions: 10
- Objection frequency: 0.200
- Relevant preferences: patch_split_preference=0.100, ownership_boundary_sensitivity=0.100, dt_schema_strictness=0.500, commit_message_expectation=0.000, pm_sequencing_preference=0.100, soundwire_lifecycle_preference=0.600
- Top objection categories: soundwire, dt_schema, controls, patch_split, refactor

### Pierre-Louis Bossart
- Series score: 0.441
- Profile interactions: 54
- Objection frequency: 0.574
- Relevant preferences: patch_split_preference=0.019, ownership_boundary_sensitivity=0.000, dt_schema_strictness=0.111, commit_message_expectation=0.148, pm_sequencing_preference=0.500, soundwire_lifecycle_preference=0.926
- Top objection categories: soundwire, controls, runtime_pm, commit_message, dt_schema

### Krzysztof Kozlowski
- Series score: 0.112
- Profile interactions: 8
- Objection frequency: 0.500
- Relevant preferences: patch_split_preference=0.000, ownership_boundary_sensitivity=0.000, dt_schema_strictness=0.750, commit_message_expectation=0.000, pm_sequencing_preference=0.000, soundwire_lifecycle_preference=1.000
- Top objection categories: soundwire, dt_schema, controls, dapm

## Predicted Patch Series
### Patch-01: ASoC: codecs: lpass-va-macro: isolate register-name migration from behavior changes
- Purpose: Convert downstream LPASS_CDC_VA_* register references to upstream CDC_VA_* naming without changing runtime behavior.
- Files touched: `sound/soc/codecs/lpass-va-macro.c`
- Dependencies addressed: lpass-cdc-registers.h
- Maintainers: Mark Brown
- Review difficulty: **HIGH**
- Top objection probabilities: soundwire=0.819, controls=0.691, commit_message=0.407, runtime_pm=0.324, refactor=0.322
- Expected comments:
  - Keep this as mechanical/no-functional-change only.
  - Do not mix register renames with LPI, PM, or SoundWire behavior.

### Patch-02: ASoC: codecs: lpass-va-macro: remove dependency on downstream lpass-cdc macro framework
- Purpose: Map downstream lpass-cdc registration/runtime callback model onto existing upstream component/platform lifecycle.
- Files touched: `sound/soc/codecs/lpass-va-macro.c`
- Dependencies addressed: lpass-cdc.h
- Maintainers: Mark Brown
- Review difficulty: **HIGH**
- Top objection probabilities: soundwire=0.819, controls=0.691, commit_message=0.477, runtime_pm=0.324, ownership_boundary=0.322
- Expected comments:
  - Explain why the downstream framework should not be upstreamed.
  - Keep lifecycle conversion separate from runtime PM behavior.

### Patch-03: ASoC: codecs: lpass-macro-common: add only shared helper infrastructure with first VA user
- Purpose: Introduce shared helper only when consumed by VA macro, avoiding unused exported APIs.
- Files touched: `sound/soc/codecs/lpass-macro-common.c, sound/soc/codecs/lpass-macro-common.h, sound/soc/codecs/lpass-va-macro.c`
- Dependencies addressed: lpass-cdc-clk-rsc.h
- Maintainers: Mark Brown
- Review difficulty: **HIGH**
- Top objection probabilities: soundwire=0.819, controls=0.691, runtime_pm=0.424, commit_message=0.357, dt_schema=0.304
- Expected comments:
  - Do not export helpers before an in-tree user exists.
  - Justify common-code placement versus static VA-local helper.

### Patch-04: ASoC: codecs: lpass-va-macro: migrate VA runtime PM and clock sequencing
- Purpose: Replace vendor clock-resource votes with upstream clock/runtime PM sequencing while preserving VA behavior.
- Files touched: `sound/soc/codecs/lpass-va-macro.c`
- Dependencies addressed: lpass-cdc-clk-rsc.h, dsp/digital-cdc-rsc-mgr.h
- Maintainers: Mark Brown
- Review difficulty: **HIGH**
- Top objection probabilities: soundwire=0.819, controls=0.691, runtime_pm=0.604, commit_message=0.477, dt_schema=0.304
- Expected comments:
  - Provide trace or power evidence for PM sequencing.
  - Preserve error unwinding and autosuspend behavior.

### Patch-05: soundwire: qcom: keep VA SoundWire behavior in controller/topology layer
- Purpose: Avoid importing swr-wcd private notifications into VA macro; route any required behavior through upstream SoundWire ownership boundaries.
- Files touched: `drivers/soundwire/qcom.c, sound/soc/codecs/lpass-va-macro.c`
- Dependencies addressed: soc/swr-common.h, soc/swr-wcd.h
- Maintainers: Pierre-Louis Bossart, Mark Brown
- Review difficulty: **HIGH**
- Top objection probabilities: soundwire=0.990, controls=0.691, ownership_boundary=0.362, commit_message=0.357, runtime_pm=0.324
- Expected comments:
  - Do not create private codec-to-controller notification APIs.
  - Split controller changes from codec changes unless dependency ordering requires otherwise.

### Patch-06: ASoC: codecs: lpass-va-macro: drop downstream pinctrl/version compatibility paths
- Purpose: Remove downstream-only pinctrl and linux/version.h compatibility assumptions from the upstream path.
- Files touched: `sound/soc/codecs/lpass-va-macro.c`
- Dependencies addressed: asoc/msm-cdc-pinctrl.h, linux/version.h
- Maintainers: Mark Brown
- Review difficulty: **HIGH**
- Top objection probabilities: soundwire=0.819, controls=0.691, commit_message=0.437, runtime_pm=0.324, dt_schema=0.304
- Expected comments:
  - Do not add version conditionals to upstream code.
  - Explain why downstream pinctrl behavior is not part of upstream VA macro.

### Patch-07: dt-bindings: sound: qcom,lpass-va-macro: document only required binding deltas if any remain
- Purpose: Keep DT binding changes separate and only include them if the conversion genuinely requires new properties or compatibles.
- Files touched: `Documentation/devicetree/bindings/sound/qcom,lpass-va-macro.yaml`
- Dependencies addressed: none
- Maintainers: Krzysztof Kozlowski, Mark Brown
- Review difficulty: **HIGH**
- Top objection probabilities: soundwire=0.819, controls=0.691, dt_schema=0.644, commit_message=0.477, runtime_pm=0.324
- Expected comments:
  - Do not add downstream-only properties without schema justification and users.
  - Run dt_binding_check and keep DTS changes separate from driver changes.

## Actionable Recommendations
- Keep register renames and include cleanup mechanically separate from behavioral changes.
- Do not add userspace controls or new public ABI for LPI/runtime state.
- Do not upstream lpass-cdc, swr-wcd, or msm-cdc-pinctrl vendor frameworks; map behavior to existing upstream ownership layers.
- Merge any new shared helper with its first in-tree VA consumer; avoid unused exported helpers.
- Keep SoundWire controller changes separate from ASoC codec changes unless a single patch is required for bisect safety.
- Add DT binding changes only if a driver patch introduces a real new property or compatible; otherwise omit DT from v1.
- For runtime PM/clock sequencing, include trace evidence in the cover letter and preserve existing error unwinding.
- Use commit messages that explain why downstream vendor dependencies are removed rather than copied upstream.

## Patchwork Evidence Examples
- Series 1108044: `soundwire: qcom: add support for EE-aware register layout` (Krzysztof Kozlowski)
  - URL: https://patchwork.kernel.org/project/alsa-devel/list/?series=1108044
  - Categories: dapm, dt_schema, soundwire
- Series 997726: `soundwire: qcom: add support for v3.1.0 controller` (Krzysztof Kozlowski)
  - URL: https://patchwork.kernel.org/project/alsa-devel/list/?series=997726
  - Categories: controls, dt_schema, soundwire
- Series 841839: `[v2] soundwire: qcom: allow multi-link on newer devices` (Krzysztof Kozlowski)
  - URL: https://patchwork.kernel.org/project/alsa-devel/list/?series=841839
  - Categories: controls, soundwire
- Series 841094: `[RESEND] soundwire: qcom: allow multi-link on newer devices` (Krzysztof Kozlowski)
  - URL: https://patchwork.kernel.org/project/alsa-devel/list/?series=841094
  - Categories: controls, soundwire
- Series 804906: `soundwire: qcom: allow multi-link on newer devices` (Krzysztof Kozlowski, Pierre-Louis Bossart)
  - URL: https://patchwork.kernel.org/project/alsa-devel/list/?series=804906
  - Categories: controls, soundwire
- Series 803662: `soundwire: qcom: set controller id to hw master id` (Krzysztof Kozlowski)
  - URL: https://patchwork.kernel.org/project/alsa-devel/list/?series=803662
  - Categories: controls, soundwire
- Series 796495: `[1/3] soundwire: qcom: drop unneeded DAI .set_stream callback` (Krzysztof Kozlowski, Pierre-Louis Bossart)
  - URL: https://patchwork.kernel.org/project/alsa-devel/list/?series=796495
  - Categories: controls, dt_schema, soundwire
- Series 753045: `soundwire: qcom: fix storing port config out-of-bounds` (Krzysztof Kozlowski, Pierre-Louis Bossart)
  - URL: https://patchwork.kernel.org/project/alsa-devel/list/?series=753045
  - Categories: commit_message, refactor, soundwire
- Series 748561: `[1/2] soundwire: qcom: fix unbalanced pm_runtime_put()` (Pierre-Louis Bossart)
  - URL: https://patchwork.kernel.org/project/alsa-devel/list/?series=748561
  - Categories: commit_message, controls, runtime_pm, soundwire
- Series 748560: `soundwire: qcom: add proper error paths in qcom_swrm_startup()` (Pierre-Louis Bossart)
  - URL: https://patchwork.kernel.org/project/alsa-devel/list/?series=748560
  - Categories: runtime_pm, soundwire
