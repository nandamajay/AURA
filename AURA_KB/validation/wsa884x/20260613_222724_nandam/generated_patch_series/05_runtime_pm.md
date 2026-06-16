# PATCH 5/7

- Title: `ASoC: codecs: wsa884x: add runtime PM and resume safety`
- Purpose: Integrate autosuspend and robust resume path handling.
- Dependencies: PATCH 2
- Expected reviewers: Pierre-Louis Bossart, Mark Brown
- Notes: include timeout-safe gating before regcache sync.
