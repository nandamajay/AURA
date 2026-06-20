# WCD9378 Implication Report from WCD938x LA-vs-LE Learning

Generated: 2026-06-20  
Scope: learning-only; no conversion, no runtime claim

## 1. What WCD938x teaches us for WCD9378
- Keep LE architecture split: aggregate codec + SDW child driver + shared helpers (`wcd-common`, `wcd-mbhc-v2`, `wcd-clsh-v2`).
  - Evidence: `track_b_corpora/linux-next/sound/soc/codecs/wcd938x.c:3337-3535`, `track_b_corpora/linux-next/sound/soc/codecs/wcd938x-sdw.c:1152-1274`, `track_b_corpora/linux-next/sound/soc/codecs/wcd-common.c:78-113`.
- Normalize DT model to LE property set (`reset-gpios`, `qcom,rx-device`, `qcom,tx-device`, `qcom,*-port-mapping`, `qcom,micbias*-microvolt`).
  - Evidence: `track_b_corpora/linux-next/sound/soc/codecs/wcd938x.c:3211-3231,3461-3471`, `track_b_corpora/linux-next/sound/soc/codecs/wcd938x-sdw.c:1167-1175`, `track_b_corpora/linux-next/sound/soc/codecs/wcd-common.c:41-49`.
- Reuse LE regcache lifecycle (cache-only at start, sync on attach/resume).
  - Evidence: `track_b_corpora/linux-next/sound/soc/codecs/wcd938x-sdw.c:1206-1208,1233-1252`, `track_b_corpora/linux-next/sound/soc/codecs/wcd-common.c:102-113`.
- Keep MBHC/Class-H integrations on shared APIs, not LA private stacks.
  - Evidence: `track_b_corpora/linux-next/sound/soc/codecs/wcd938x.c:2547-2583,3042,3119`, `track_b_corpora/linux-next/sound/soc/codecs/wcd-mbhc-v2.c:1433-1632`, `track_b_corpora/linux-next/sound/soc/codecs/wcd-clsh-v2.c:844-899`.

## 2. What WCD938x does not teach us for WCD9378
- It does not prove WCD9378 SDW numeric identity (part-id/compatible/modalias).
  - WCD938x tuple is codec-specific: `track_b_corpora/linux-next/sound/soc/codecs/wcd938x-sdw.c:1227-1231`.
- It does not prove WCD9378 paging requirements or controller-side paging behavior.
  - WCD938x register range/base do not demonstrate WCD9378 high-address behavior: `track_b_corpora/linux-next/sound/soc/codecs/wcd938x.h:7,586`.
- It does not close WCD9378 class-H base/version blocker.
  - Prior blocker remains fail-closed: `AURA_KB/drivers/wcd9378/blocker_burndown_01_datasheet_delta/conversion_gate_preconditions_delta.json`.

## 3. Which WCD9378 blockers are helped by this learning
- Helped (method/structure only):
  - Lifecycle and component split strategy.
  - DT property normalization strategy.
  - MBHC/Class-H shared-library integration strategy.
  - Runtime PM + regcache lifecycle strategy.
- Cross-check evidence:
  - `AURA_KB/drivers/wcd9378/evidence_request_01/evidence_checklist.json` (runtime evidence still missing but blocker map is clearer).
  - `AURA_KB/drivers/wcd937x/variant_c/lessons_learned.json` (category gains came from lifecycle/API alignment).

## 4. Which WCD9378 blockers remain unchanged
- SDW numeric identity + compatible derivation.
- Paging runtime proof and whether controller update is needed.
- Class-H WCD9378 enum/base decision.
- Runtime playback/capture/mute validation.
- Board DTS finalization.
- Evidence:
  - `AURA_KB/drivers/wcd9378/blocker_burndown_01_datasheet_delta/pm_datasheet_delta_summary.md`.
  - `AURA_KB/drivers/wcd9378/blocker_burndown_01_datasheet_delta/conversion_gate_preconditions_delta.json`.

## 5. Monday runtime evidence priorities reshaped by this audit
1. SDW identity logs first (to unblock SDW device ID and binding direction).
2. Paging traces second (to determine if generic LE regmap lifecycle is sufficient for WCD9378 high addresses).
3. Class-H register trace third (to settle enum/base path).
4. Playback/capture/mute logs after identity+paging are pinned.
- Existing request package already aligns: `AURA_KB/drivers/wcd9378/evidence_request_01/hardware_evidence_request.md`.

## 6. What we should avoid adding to WCD9378 based only on WCD938x
- Any LA vendor hooks (`msm-cdc*`, `bolero`, hwdep, qti debugfs).
- Any LA-only DT property model (`qcom,wcd-rst-gpio-node`, `qcom,rx-slave`, `qcom,tx-slave`, `qcom,cdc-micbias*-mv`).
- Any inferred SDW ID or paging claim copied from sibling codec behavior.
- Any runtime workaround claim without board evidence.

## Bottom line
WCD938x LA-vs-LE mining is high-value for conversion architecture and API mapping quality. It does **not** change WCD9378 NO-GO status for runtime-sensitive blockers.
