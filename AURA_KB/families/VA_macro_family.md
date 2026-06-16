# VA Macro Family

## Members
- lpass-va-macro
- bolero va-macro

## Family model
- Common architecture: voice-assistant capture macro path.
- Common DAPM model: decimator and voice-input chains.
- Common Runtime PM model: macro runtime clocks and wake handling.
- Common DT model: qcom,lpass-va-macro schema and clock constraints.
- Common registration flow: platform probe + component/DAI + PM callbacks.
- Common patch structure: core support + DAPM/routes + fixup patches.
