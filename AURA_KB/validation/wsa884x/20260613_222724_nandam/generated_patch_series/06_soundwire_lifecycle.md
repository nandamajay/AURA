# PATCH 6/7

- Title: `ASoC: codecs: wsa884x: add SoundWire stream lifecycle integration`
- Purpose: Wire hw_params/hw_free/set_stream and SDW slave ops.
- Dependencies: PATCH 2
- Expected reviewers: Pierre-Louis Bossart, Vinod Koul
- Notes: use native SDW lifecycle callbacks.
