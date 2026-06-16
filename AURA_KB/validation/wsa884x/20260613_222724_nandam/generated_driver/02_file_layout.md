# File Layout Proposal (Blind v1)

1. `sound/soc/codecs/wsa884x.c`
- codec core, reg defaults, controls, DAPM, DAI ops, SDW probe/runtime PM.

2. `Documentation/devicetree/bindings/sound/qcom,wsa8840.yaml`
- binding schema for compatible and optional port mapping/reset properties.

3. `sound/soc/codecs/Kconfig`
- `config SND_SOC_WSA884X` with SoundWire dependency.

4. `sound/soc/codecs/Makefile`
- add `snd-soc-wsa884x-y := wsa884x.o` and object export.
