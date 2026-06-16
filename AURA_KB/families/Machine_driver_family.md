# Machine Driver Family

## Members
- downstream board machine files
- upstream qcom/*.c machine cards

## Family model
- Common architecture: machine/card layer wiring FE/BE and codec links.
- Common DAPM model: board-level widgets/routes and audio-routing controls.
- Common Runtime PM model: card-level votes/clocks integrated with LPASS and codecs.
- Common DT model: sound card node + codec endpoint bindings.
- Common registration flow: platform card registration and dai_link setup.
- Common patch structure: board support in SoC-specific machine files.
