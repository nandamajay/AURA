# Reconstructed Patch Series (Blind) - wsa883x

Constraint used during creation: downstream + AURA_KB only.

## Predicted Series
| Patch | Title | Purpose | Dependencies | Expected reviewers |
|---|---|---|---|---|
| 1/6 | ASoC: dt-bindings: sound: add qcom,wsa883x SoundWire codec schema | Add base YAML with compatible, regulator, gpio/reset semantics | none | Krzysztof Kozlowski, Rob Herring, Conor Dooley |
| 2/6 | ASoC: codecs: add wsa883x SoundWire codec core | Add core driver skeleton, regmap, component registration, DAI | 1/6 | Mark Brown, Pierre-Louis Bossart |
| 3/6 | ASoC: codecs: wsa883x: add controls and DAPM graph | Add kcontrols, DAPM widgets/routes, event hooks | 2/6 | Mark Brown |
| 4/6 | ASoC: codecs: wsa883x: switch to runtime PM autosuspend | Add runtime suspend/resume + regcache sync strategy | 2/6 | Pierre-Louis Bossart, Mark Brown |
| 5/6 | ASoC: codecs: wsa883x: add SoundWire stream lifecycle hooks | Add set_stream/hw_params/hw_free mapping to SDW stream APIs | 2/6 | Pierre-Louis Bossart, Vinod Koul |
| 6/6 | ASoC: dt-bindings: sound: wsa883x: document port mapping/reset updates | Add `qcom,port-mapping` and shared-reset compatible schema updates | 1/6 | Krzysztof Kozlowski |

## Rationale
- Patch split follows KB codec playbook ordering (DT first, then core, then DAPM/controls, then robustness/evolution).
  - Evidence: `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/playbooks/upstream_codec_driver.md`
- Runtime PM and SDW lifecycle were placed as explicit patches due to recurring reviewer focus.
  - Evidence: `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/runtime_pm_rules.md`, `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/soundwire_rules.md`

## Comparison to Actual Historical Shape
Actual accepted history was closer to:
- DT binding initial patch
- codec core patch
- controls/DAPM patch (iterated v1 -> v2 -> v3)
- follow-up runtime timeout fix
- later DT/port-mapping + shared reset evolution

Evidence:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/lore_links/wsa883x.md`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/accepted_commits/wsa883x.md`

Patch-shape assessment:
- Predicted series is bisect-safe and reviewable.
- It is slightly more front-loaded than the historical accepted shape.

