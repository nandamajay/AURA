# PATCH 4/7

- Title: `ASoC: codecs: wsa884x: add controls and mode switches`
- Purpose: Add PA/mode/port controls with strict kcontrol semantics.
- Dependencies: PATCH 2
- Expected reviewers: Mark Brown
- Notes: explicit `put` return-on-change behavior.
