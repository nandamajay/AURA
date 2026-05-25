# SoundWire Topology Diff

## Structural Mapping Evidence
- Downstream `swr_` hits: `80`
- Upstream `sdw_` hits: `81`
- Downstream top files: `[('asoc/codecs/wcd937x/wcd937x.c', 59), ('asoc/codecs/wcd937x/wcd937x_slave.c', 10), ('asoc/codecs/wcd937x/wcd937x.h', 7), ('asoc/codecs/wcd937x/internal.h', 4)]`
- Upstream top files: `[('sound/soc/codecs/wcd937x-sdw.c', 31), ('sound/soc/codecs/wcd937x.c', 30), ('sound/soc/codecs/wcd-common.c', 11), ('sound/soc/codecs/wcd-common.h', 8)]`

## Observed Structural Differences
- Downstream evidence references SWR device-centric symbols and wrappers.
- Upstream evidence references SDW slave ops/component registration and SDW stream APIs.
- Mapping state from prior study: `inferred` (not confirmed behavioral parity).

## Runtime Equivalence Decision
- Transport topology runtime equivalence: `UNKNOWN`
- Reasons:
  - No captured runtime bus event trace in this pass.
  - No device-level SoundWire interrupt/stream attach behavioral replay proof.
  - Structural API transition alone is insufficient for parity claims.

## Classification
- advisory_only
- runtime_unverified
- escalation_required
