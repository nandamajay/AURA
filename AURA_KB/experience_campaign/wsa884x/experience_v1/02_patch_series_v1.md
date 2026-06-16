# Phase 2 - Patch Series Generation (v1)

## Series intent
First send as if real upstream submission; includes deliberate over-splitting risk to exercise review-survival behavior.

## Patch 1
- Title: `ASoC: dt-bindings: qcom,wsa8840: add WSA884x binding`
- Purpose: introduce YAML schema and compatibles.
- Files touched:
  - `Documentation/devicetree/bindings/sound/qcom,wsa8840.yaml`
- Dependencies: none.
- Review risk: MEDIUM.
- Maintainer risk: Krzysztof (schema strictness), Mark (series hygiene).
- Expected comments: property constraints, compatible modeling, example cleanup.

## Patch 2
- Title: `ASoC: codecs: wsa884x: add core codec skeleton`
- Purpose: add regmap, probe/remove skeleton, base component registration.
- Files touched:
  - `sound/soc/codecs/wsa884x.c`
  - `sound/soc/codecs/Kconfig`
  - `sound/soc/codecs/Makefile`
- Dependencies: Patch 1.
- Review risk: MEDIUM.
- Maintainer risk: Mark.
- Expected comments: callback scope and split quality.

## Patch 3
- Title: `ASoC: codecs: wsa884x: add DAPM widgets/routes`
- Purpose: add playback path topology.
- Files touched:
  - `sound/soc/codecs/wsa884x.c`
- Dependencies: Patch 2.
- Review risk: MEDIUM.
- Maintainer risk: Mark.
- Expected comments: keep graph minimal and semantics clean.

## Patch 4
- Title: `ASoC: codecs: wsa884x: add controls and enums`
- Purpose: add user controls including mode controls.
- Files touched:
  - `sound/soc/codecs/wsa884x.c`
- Dependencies: Patch 2.
- Review risk: HIGH.
- Maintainer risk: Mark.
- Expected comments: kcontrol `put` semantics and naming style.

## Patch 5
- Title: `ASoC: codecs: wsa884x: add runtime PM support`
- Purpose: add autosuspend and runtime resume/suspend handling.
- Files touched:
  - `sound/soc/codecs/wsa884x.c`
- Dependencies: Patch 2.
- Review risk: HIGH.
- Maintainer risk: Pierre, Mark.
- Expected comments: timeout-safety ordering on resume path.

## Patch 6
- Title: `ASoC: codecs: wsa884x: add SoundWire stream lifecycle`
- Purpose: add SDW startup/shutdown stream handling and status callbacks.
- Files touched:
  - `sound/soc/codecs/wsa884x.c`
- Dependencies: Patches 2 and 5.
- Review risk: HIGH.
- Maintainer risk: Pierre, Krzysztof, Vinod.
- Expected comments: SDW callback conditions, state guards, ownership boundaries.

## Patch 7
- Title: `ASoC: codecs: wsa884x: documentation and cleanup`
- Purpose: docs and message cleanup.
- Files touched:
  - `sound/soc/codecs/wsa884x.c` (comments/changelog style)
- Dependencies: all previous.
- Review risk: MEDIUM.
- Maintainer risk: Mark.
- Expected comments: fold into logical patches instead of standalone cleanup.

## v1 risk summary
- Highest-risk zones: patch over-splitting, PM ordering, SDW lifecycle details, control semantics.
- Evidence:
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_campaign/20260614_092103_reviewer_evidence_acquisition/review_survival_rules_v2.md`
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/patch_submission_rules.md`
