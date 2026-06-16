# TX Macro Family

## Members
- lpass-tx-macro
- bolero tx-macro

## Family model
- Common architecture: LPASS transmit macro for capture/decimator routing.
- Common DAPM model: capture-centric graph with decimator controls.
- Common Runtime PM model: macro clocks/votes and stream-state gating.
- Common DT model: qcom,lpass-tx-macro bindings with SoC variants.
- Common registration flow: platform probe + component/DAI ops.
- Common patch structure: core support then DAPM/route additions.
