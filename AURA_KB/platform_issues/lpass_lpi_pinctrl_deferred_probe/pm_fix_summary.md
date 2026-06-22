# PM Fix Summary — LPASS LPI Pinctrl Deferred Probe

## 1. What is the root cause?

The root cause is a missing `lpass_tlmm: pinctrl@7760000` node in
`eliza.dtsi`. The `pinctrl-lpass-lpi` driver calls `of_pm_clk_add_clks()` at
probe time, which reads the DTS `clocks` and `clock-names` properties. Without
the LPASS LPI pinctrl node and its `core`/`audio` clocks, `7760000.pinctrl`
fails probe and the audio deferred-probe chain stalls.

## 2. What does this patch fix?

- Adds the `gpr` hierarchy under the existing `remoteproc_adsp` `glink-edge`.
- Adds `q6apm`, `q6apmbedai`, and `q6apmdai` service nodes needed by the audio
  graph.
- Adds `q6prm` and `q6prmcc`, providing the `qcom,q6prm-lpass-clocks` clock
  controller needed by `lpass_tlmm`.
- Adds `lpass_tlmm: pinctrl@7760000` with `clocks`, `clock-names`,
  `gpio-controller`, `gpio-ranges`, and six audio pinctrl states:
  `tx_swr_active`, `rx_swr_active`, `dmic01_default`, `dmic23_default`,
  `wsa_swr_active`, and `wsa2_swr_active`.

## 3. What does this patch NOT fix?

- It does not add SoundWire master nodes `swr1`, `swr2`, or `swr3`; those are
  part of later WCD9378 bring-up additions.
- It does not fix `gcc-eliza sync_state pending due to crypto`.
- It does not fix the WCD9378 TX slave UNATTACHED issue.
- It does not claim or guarantee audio playback/capture works end-to-end.

## 4. What must be confirmed on board before upstreaming?

- `7760000.pinctrl` probes cleanly with no deferred probe message.
- `7660000.codec` VA macro probes after the pinctrl fix.
- The sound card instantiates without `VA Capture: error getting cpu dai name`.
- The `q6apmdai` SMMU stream IDs `0x1001/0x80` and `0x1041/0x20`, copied from
  SM8750, are correct for Eliza.

## 5. Is this fix safe to apply to the bring-up DTS now?

Yes. This is a pure DTS addition that adds missing nodes expected by existing
drivers. It does not modify existing Eliza nodes. Risk is low, with the main
open item being board confirmation of Eliza-specific SMMU stream IDs.

## 6. What is the upstream submission path for this fix?

- Target tree: `qcom/dt`.
- Maintainers: Bjorn Andersson and Konrad Dybcio.
- File: `arch/arm64/boot/dts/qcom/eliza.dtsi`.
- Series placement: standalone prerequisite patch or part of the Eliza audio
  bring-up series before WCD9378/SoundWire patches.
- Requirement: board-level boot test confirmation before RFC submission.

## 7. What is the recommended next human action?

Apply `eliza_lpass_lpi_fix.patch` to the bring-up DTS tree, rebuild the DTB,
flash it to Eliza EVK, and capture dmesg. Confirm `7760000.pinctrl` probes
cleanly. If successful, proceed with the WCD9378 TX UNATTACHED fix.
