# WSA Family

## Members
- wsa881x
- wsa883x
- wsa884x
- wsa8855

## Family model
- Common architecture: codec driver + bus transport integration (SWR downstream, SDW upstream).
- Common DAPM model: minimal speaker-endpoint graphs and switchable signal paths.
- Common Runtime PM: autosuspend + resume/suspend hooks.
- Common DT model: qcom binding YAML with strict required properties upstream.
- Common registration flow: component + DAI registration inside bus probe.
- Common patch structure: DT binding + codec core, then follow-up refinements.
