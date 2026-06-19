# WCD9378 External Bring-Up Claim Audit — PM Triage Summary

Generated: 2026-06-19T18:08:05Z (audit-only, no source modifications)

## 1) Which external claims are confirmed?
- Confirmed downstream DT/ID usage:
  - `qcom,wcd9378-codec` in `wcd9378.c:4591-4593`.
  - `qcom,wcd9378-slave` / `wcd9378-slave` in `wcd9378-slave.c:313-321`.
- Confirmed downstream SWR/SDCA behavior:
  - Paging enabled on both slaves in `wcd9378.c:4509,4518`.
  - SDCA IRQ programming in `wcd9378.c:4531-4541`.
  - SDCA-capable regmap callbacks in `wcd9378-regmap.c:879-970`.
- Confirmed downstream MBHC/Class-H presence:
  - MBHC init in `wcd9378.c:4160-4165`.
  - Class-H init in `wcd9378.c:4187`.
  - Class-H DAPM supply in `wcd9378.c:3672-3674`.

## 2) Which claims are contradicted or unsupported?
- Contradicted:
  - "Upstream WCD937x bindings can be used unchanged" is contradicted by:
    - upstream compat set (`qcom,wcd9370-codec`/`qcom,wcd9375-codec`) in `qcom,wcd937x.yaml:21-27`,
    - downstream `qcom,wcd9378-codec` in `wcd9378.c:4591-4593`,
    - downstream legacy properties in `wcd9378.c:4424-4444,4717-4727`.
- Unsupported/UNVERIFIED:
  - "Upstream SoundWire core must be changed" (no direct blocker proven in `linux-next/drivers/soundwire/qcom.c` and `bus.c` review).
  - Runtime success claims (playback/capture/mute-closed) have no reproducible test logs in allowed sources.

## 3) Which are board-only?
- `qcom,wcd-rst-gpio-node` (`wcd9378.c:4424-4431`) vs upstream `reset-gpios` (`qcom,wcd93xx-common.yaml:13-16,85-88`).
- `qcom,rx-slave`/`qcom,tx-slave` (`wcd9378.c:4443-4444`) vs upstream `qcom,rx-device`/`qcom,tx-device` (`qcom,wcd93xx-common.yaml:29-35`).
- `qcom,rx_swr_ch_map`/`qcom,tx_swr_ch_map` (`wcd9378.c:4717-4720`) vs upstream `qcom,*-port-mapping` (`qcom,wcd937x-sdw.yaml:24-60`).
- `qcom,cdc-micbias*-mv` (`wcd9378.c:4346-4378`) vs upstream `qcom,micbias*-microvolt` (`qcom,wcd93xx-common.yaml:37-55`).

## 4) Which are dangerous upstream hacks?
- Debug register poke/dump infrastructure:
  - slave debugfs (`wcd9378-slave.c:343-369`),
  - SDCA debugfs API (`sdca-registers-api.c:221-257`).
- Bring-up style log trace: `"wcd irq init done"` in `wcd9378.c:4547-4548`.

## 5) Which WCD9378 areas are ready for conversion?
- High-confidence areas:
  - Vendor-framework removal (includes/APIs).
  - Regulator API migration to upstream bulk regulators.
  - Reset API migration to gpiod/reset-gpios.
  - SWR API replacement with Linux SDW API model (`wcd937x-sdw.c` pattern).

## 6) Which areas must remain fail-closed?
- Compatible/binding strategy for `qcom,wcd9378-codec` (schema coverage unresolved).
- Whether `qcom,swr-tx-port-params` is truly required or removable.
- SDW ID equivalence and paging semantics under upstream SDW stack.
- Class-H base/version selection (`wcd-clsh-v2` mapping choice).
- Runtime claims (playback/capture/mute closure) without deterministic test evidence.

## 7) Are we ready to start WCD9378 conversion?
- **No (not yet).**
- Blocking items remain in `FAIL_CLOSED`/`MISSING` state in the readiness checklist (binding/ID/paging/runtime evidence/datasheet sufficiency).

## 8) If yes, what should be the first patch series scope?
- Not applicable while blocked.
- If blockers are cleared, safest first scope is non-functional API cleanup only:
  - vendor include removal,
  - regulator/reset API migration,
  - DT property normalization scaffolding,
  - no behavior-changing runtime/audio path edits in first series.

## 9) If no, what evidence is missing?
- Concrete binding decision for WCD9378 compatible and property schema.
- Hardware-backed SDW identity + paging behavior proof under upstream SDW.
- Deterministic runtime validation logs (playback/capture/mute regressions).
- Definitive Class-H and MBHC mapping choice for upstream shared modules.
- Better-than-marketing datasheet signal for WCD9378-specific software integration (current PDF is 1-page WCD9370/9375 specs only).
