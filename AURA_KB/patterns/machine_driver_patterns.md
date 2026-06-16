# Machine Driver Patterns (Promotion Status)

## Pattern 1: Keep board policy in machine/DT, keep codec generic
- Confidence: MEDIUM_CONFIDENCE
- Problem: board-specific policy in codec creates upstream friction.
- Accepted solution: shift board/channel-map policy to machine and DT layers.
- Evidence drivers: `wsa883x`, `wsa884x`, `wcd938x` (downstream machine coupling observed, upstream codec genericization observed)
- Maintainers involved: INSUFFICIENT_EVIDENCE for direct machine-driver review comments
- Acceptance rate: 3/3 codec families show this trend

## Gap
- Direct upstream machine-driver patch-review evidence remains INSUFFICIENT_EVIDENCE in current corpus.
