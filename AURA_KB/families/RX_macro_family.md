# RX Macro Family

## Members
- lpass-rx-macro
- bolero rx-macro

## Family model
- Common architecture: LPASS macro platform driver, register-backed path controls.
- Common DAPM model: mixer/mux + decimator/interpolator path graphs.
- Common Runtime PM model: macro-level PM with codec clock/resource interactions.
- Common DT model: qcom,lpass-rx-macro compatibles by SoC.
- Common registration flow: platform probe -> component/DAI register.
- Common patch structure: support patch + DAPM/routes patch.
