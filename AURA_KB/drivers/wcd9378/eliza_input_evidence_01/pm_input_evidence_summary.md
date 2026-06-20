# WCD9378 ELIZA Input Evidence Summary

## Terminology Lock

- `LA` means downstream / Linux Android.
- `LE` means upstream / Linux Embedded.

Use this terminology consistently in future AURA prompts and artifacts.

## Gerrit Access Result

The three LA audio device-tree Gerrit changes were not readable without authentication. Direct page fetch and Gerrit REST detail fetch both redirected to login and returned HTTP `401`.

Changes checked:

- `6540959` under `platform/vendor/qcom/opensource/audio-devicetree`
- `6743027` under `platform/vendor/qcom/opensource/audio-devicetree`
- `6748944` under `platform/vendor/qcom/opensource/audio-devicetree`

PM conclusion: these are valuable inputs, but AURA cannot use their contents until you provide patch exports, screenshots are not preferred, or an authenticated checkout/fetch.

## Local ELIZA/WCD9378 Inputs Found

- `/local/mnt/workspace/Datasheets/80-71506-1_REV_AA_Qualcomm_Aqstic_WCD9378_Data_Sheet.pdf`
- `/local/mnt/workspace/Datasheets/ELIZA_schematic_wcd9378.pdf`
- `/local/mnt/workspace/Datasheets/qualcomm_aqstic_wcd937x_specs.pdf`

The WCD9378 datasheet and ELIZA schematic are text-extractable and useful for static evidence.

## Useful Static Evidence Extracted

### ELIZA Schematic

- Board/schematic title identifies EVK audio DC with `WCD9378` and `2XWSA884X`.
- WCD9378 component appears as `U6`, part `CD90-58923-1`.
- Reset signal is `WCD9378_RST_N`, connected to `RESET_N` / pin `33`.
- RX SoundWire signals are present:
  - `WCD9378_SWR_RX_CLK` -> `CDC_SWR_RX_CLK` / pin `19`
  - `WCD9378_SWR_RX_DATA0` -> `CDC_SWR_RX_D0` / pin `28`
  - `WCD9378_SWR_RX_DATA1` -> `CDC_SWR_RX_D1` / pin `10`
- TX SoundWire signals are present:
  - `WCD9378_SWR_TX_CLK` -> `CDC_SWR_TX_CLK` / pin `20`
  - `WCD9378_SWR_TX_DATA0` -> `CDC_SWR_TX_D0` / pin `15`
  - `WCD9378_SWR_TX_DATA1` -> `CDC_SWR_TX_D1` / pin `16`
- Analog inputs include `AMIC1..AMIC4` positive/negative input nets.
- Analog outputs include `HPH_L`, `HPH_R`, `HPH_REF`, `AUX_OUT_P/M`, and `EAR_OUT_P/M`.
- Mic-bias signals show `MIC_BIAS1/2/3` and corresponding WCD9378 mic-bias nets.
- Supply evidence includes `VDD_MIC_BIAS`, `VDD_A`, `VDD_IO`, and `VDD_CP` related WCD9378 rails.

### WCD9378 Datasheet

- WCD9378 uses SoundWire for on-chip digital audio channels.
- Datasheet states Tx and Rx SoundWire peripherals each have two data lanes.
- Reset pin is `RESET_N` pin `33`.
- RX SoundWire pins: `SWR_RX_CLK` pin `19`, `SWR_RX_DATA0` pin `28`, `SWR_RX_DATA1` pin `10`.
- TX SoundWire pins: `SWR_TX_CLK` pin `20`, `SWR_TX_DATA0` pin `15`, `SWR_TX_DATA1` pin `16`.
- Power pins include `VDD_CX`, `VDD_PX`, `VDD_MIC_BIAS`, `VDD_A`, `VDD_CP`, `PA_VPOS`, and `PA_VNEG`.
- Mic-bias supports three bias sources, programmable from `1.05V` to `2.85V`, with `1.8V` typical listed.
- Device identification table includes WCD9378 chip ID bytes `0x00 0x00 0x10 0x01` for sample rows.

## PM Interpretation

This improves our static confidence for ELIZA board wiring and WCD9378 pin/supply/audio topology. It does not replace runtime evidence.

The biggest useful addition is board-specific confirmation that ELIZA exposes two-lane RX and TX SoundWire between the SoC/LPI side and WCD9378, matching the WCD9378 datasheet. This can guide DTS review and engineer evidence requests.

## Still Blocked

- Exact LA DTS changes from the three Gerrit links are still blocked by authentication.
- Runtime SDW identity is still blocked until board logs are available.
- Paged register access behavior is still blocked until register traces or runtime logs are available.
- Class-H/HPH behavior is still blocked until runtime register traces are available.

## Next Action Requested From User

Please export the three Gerrit changes as patches using an authenticated environment, for example:

```bash
ssh -p 29418 review-android.quicinc.com gerrit query --format=JSON change:6540959 --current-patch-set
ssh -p 29418 review-android.quicinc.com gerrit query --format=JSON change:6743027 --current-patch-set
ssh -p 29418 review-android.quicinc.com gerrit query --format=JSON change:6748944 --current-patch-set
```

Or provide `git fetch` commands/patch files from Gerrit. Once available, AURA should audit those LA DTS changes against the ELIZA schematic and the LE binding expectations before changing any LE DTS or driver code.
