# Kcontrols (Blind v1)

## Proposed controls
- `PA Volume` (TLV)
- `WSA Mode` (enum: speaker/receiver)
- SDW path toggles per functional port:
  - DAC, COMP, BOOST, PBR, VISENSE, CPS switches

## Semantics
- `put` callbacks return `1` on change, `0` otherwise.
- Control names remain user-facing and style-consistent.
