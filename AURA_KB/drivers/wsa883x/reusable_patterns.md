# WSA883x Reusable Patterns

## Pattern A: Standard SDW Stream Lifecycle
- Problem: vendor-specific bus hookups complicate upstream review.
- Accepted pattern: use `sdw_stream_add_slave/remove_slave` and SDW ops tables.
- Evidence: upstream `wsa883x.c:1356-1367`, `1126-1129`.
- Reusability: High.

## Pattern B: Minimal DAPM Graph First
- Problem: complex custom routing creates review friction.
- Accepted pattern: keep codec DAPM minimal and explicit.
- Evidence: upstream `wsa883x.c:1301-1325`.
- Reusability: High.

## Pattern C: Runtime PM Integrated in Baseline Driver
- Problem: PM gaps identified during review.
- Accepted pattern: autosuspend + runtime suspend/resume hooks from early revisions.
- Evidence: upstream `wsa883x.c:1668-1708`.
- Reusability: High.
