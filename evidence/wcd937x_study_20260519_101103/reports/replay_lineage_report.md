# Replay Lineage Report

## Replay Anchors
- intake_id: `6f817915bdc0cb628815128b1b03cc68`
- workflow_id: `d285331f26c70c20ac81f9ed3b273279`
- task_id: `cfec91e4-ec3a-4788-84c2-51f85d4639f6`
- source reconstruction hash: `193efbb0b2d9858bc1093cbb561e8fb57ce83961d848db4937351c2862017d72`
- workflow reconstruction hash: `402680bab41f15d7298db8fdbb1f1c999caeda77deb020b2590284d20892078c`
- workflow trust_valid: `True`

## Lineage Chain (source_lineage_entries)
- `downstream_intake`: `0e511dcbf873057abd1e420727f5d13cbb04ec0b1d939905bfb0de50b8459793` <- `ROOT`
- `patch_transform`: `3c4e28d4d7dac293b9fe33c26498e2c7dd4a0988739f50d27fa80f07caa1ab7d` <- `0e511dcbf873057abd1e420727f5d13cbb04ec0b1d939905bfb0de50b8459793`
- `upstream_prep`: `3b587e61de10aef6b6bd60dea802cba5a55711215fd4e9736d58d4bf1f7a6cd8` <- `3c4e28d4d7dac293b9fe33c26498e2c7dd4a0988739f50d27fa80f07caa1ab7d`
- `validation`: `234e878ff5ee4c8ad2a4dde4e7b22317bb27ae06b51b3349779b09f760714306` <- `3b587e61de10aef6b6bd60dea802cba5a55711215fd4e9736d58d4bf1f7a6cd8`
- `approval`: `7adfc31ce69a9d5f4f4a6b4b7989c661e2a069dbab7d9698a4eda6df371b81ed` <- `234e878ff5ee4c8ad2a4dde4e7b22317bb27ae06b51b3349779b09f760714306`
- `replay_evidence`: `f6d1ac2497e3217443e4fff0dcc6d2a3f686521ee7d4787ccf1b275488910f42` <- `7adfc31ce69a9d5f4f4a6b4b7989c661e2a069dbab7d9698a4eda6df371b81ed`
- `replay_evidence`: `4c4e0dd82fab6139bda8ed0d1952d79755e03c175fe390a9cc078200225668f8` <- `f6d1ac2497e3217443e4fff0dcc6d2a3f686521ee7d4787ccf1b275488910f42`
- `patch_transform`: `fa5f7e1c29a3a6ae4cba7c95df44cf7109490b5f3e30f5acd57f540cc4a081be` <- `4c4e0dd82fab6139bda8ed0d1952d79755e03c175fe390a9cc078200225668f8`
- `validation`: `a3d64145f5c60f62ce17cd67bc9d76347a9ca74a11c141a20217d613b78693f4` <- `fa5f7e1c29a3a6ae4cba7c95df44cf7109490b5f3e30f5acd57f540cc4a081be`
- `replay_evidence`: `e89eea7f786916615d9f706b2e4ac618815dd9597d9bf940f47eafa5a9c66c86` <- `a3d64145f5c60f62ce17cd67bc9d76347a9ca74a11c141a20217d613b78693f4`

## Evidence Links Persisted
- workflow evidence links: `10` reports linked via `/engineering/workflows/{id}/evidence`.

## Replay Reconstruction Result
- engineering reconstruction: success (`trust_valid=true`, no failures)
- provenance reconstruction: success
- task replay integrity: verified during governance decision (`replay_integrity_ok=true`)

## Evidence Files
- `raw/runtime_lifecycle_trace.json`
- `raw/runtime_evidence_link_trace.json`
- `raw/source_lineage_rows.json`
- `raw/engineering_evidence_links_rows.json`
- `raw/workflow_events_rows.json`
