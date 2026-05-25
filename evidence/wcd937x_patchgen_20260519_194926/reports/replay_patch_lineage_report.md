# Replay Patch Lineage Report

- workflow_id: `f1a7203028b455b0b1086517d3070801`
- task_id: `06f970ba-bcb8-4c26-a546-b1e33956f8e9`
- workflow_reconstruction_hash: `bcb3bb236652624f7cbee43234aeea65bfa2e02a85689d9da00947b7516af83a`
- source_reconstruction_hash: `842a548747e593b2e1926272ebcad2d8a657de42985b4965c9c0516eac6f610a`
- workflow_trust_valid: `True`

## Source Lineage Chain
- stage=`downstream_intake` hash=`f3be8bb3f2bc81f49ccf00f635bc68c192c9cc34c50fca35a66cb393aa2c339a` parent=`None`
- stage=`patch_transform` hash=`62454b94f05efcbabacc039c5369e6138a51761dc75590b6d9d12c53ca41cdfa` parent=`f3be8bb3f2bc81f49ccf00f635bc68c192c9cc34c50fca35a66cb393aa2c339a`
- stage=`upstream_prep` hash=`cf0c1e23883f2305e22922150e0fa612678116e491553c4ba88b1d81d5da13c0` parent=`62454b94f05efcbabacc039c5369e6138a51761dc75590b6d9d12c53ca41cdfa`
- stage=`validation` hash=`4fdd621bd564aed7891fa895df413ceb16fe31fcf4258dd68e7f66fefeaf8a42` parent=`cf0c1e23883f2305e22922150e0fa612678116e491553c4ba88b1d81d5da13c0`
- stage=`approval` hash=`472f09e1e07aa4134a21874f893eb00df9848b43450b93f1aa55d5f527ccb874` parent=`4fdd621bd564aed7891fa895df413ceb16fe31fcf4258dd68e7f66fefeaf8a42`

## Workflow Evidence Links (15)
- id=1 type=`proposed_patch_diff` ref=`generated_patch_diffs/0000-cover-letter.patch` hash=`c22984519de1023d31b2d54b8b1f6163ab331cabdddaadfcd11ea1d91f4b1af8`
- id=2 type=`proposed_patch_diff` ref=`generated_patch_diffs/0001-ASoC-codecs-wcd937x-annotate-build-wiring-constraint.patch` hash=`21438f029a655746419b5e06570d78f9fb98c72845964b60a235197ea3a1e6a2`
- id=3 type=`proposed_patch_diff` ref=`generated_patch_diffs/0002-ASoC-codecs-wcd937x-add-core-port-migration-guardrai.patch` hash=`1839a30684cefdeff32f70f4779add03483800001af2101af436693b84db34f0`
- id=4 type=`proposed_patch_diff` ref=`generated_patch_diffs/0003-ASoC-codecs-wcd937x-sdw-document-SWR-to-SDW-migratio.patch` hash=`3e106b1bd291011e03b5645c4e75d08c332815e43a413c9d8367d088f5a13aeb`
- id=5 type=`proposed_patch_diff` ref=`generated_patch_diffs/0004-ASoC-codecs-add-MBHC-CLSH-conversion-alignment-notes.patch` hash=`30323d7d99b01018f6856d62571701900e2953bad605f54f789d70b1823051aa`
- id=6 type=`proposed_patch_diff` ref=`generated_patch_diffs/0005-ASoC-codecs-wcd937x-record-downstream-abstraction-ex.patch` hash=`c22670b3c99b3f5b092579457da5b8e46a5f2bfe3e4c735678ffcd1d60d48177`
- id=7 type=`proposed_patch_diff` ref=`generated_patch_diffs/0006-dt-bindings-sound-qcom-wcd937x-clarify-upstream-sche.patch` hash=`97d6e6eb42d8fed426e4526a47e6221325e5804201bb09ecf0f2b8427eea3213`
- id=8 type=`patchgen_report` ref=`reports/WCD937x_controlled_patch_generation_index.md` hash=`fd6b6d3423c65c56501f47d4c2a2afede7349fc893e493ee4cba72ba2e026d51`
- id=9 type=`patchgen_report` ref=`reports/compile_closure_status.md` hash=`89a50502b31b19fbee6237a223a06b743cf97267deefd4161cf48a3a27b075c4`
- id=10 type=`patchgen_report` ref=`reports/governance_decision_report.md` hash=`689ed02e47289a94ee1ccea0c9c3ff53d4599b183985f2a462cb1a79a8527e03`
- id=11 type=`patchgen_report` ref=`reports/lifecycle_execution_report.md` hash=`fe9abf73fd320cee707655569556ed8d4ad141df10ec68274d9eb1989995598e`
- id=12 type=`patchgen_report` ref=`reports/replay_patch_lineage_report.md` hash=`a84eaa09c773d79186cc132156a5f59637d84ccbfcfdc440a0ed129c3147e3b9`
- id=13 type=`patchgen_report` ref=`reports/unresolved_gap_analysis.md` hash=`014b36c32d3f055f9c234adf6cbc27f47bbf887b435359fd61a92607a4b4b7a3`
- id=14 type=`patchgen_report` ref=`reports/upstream_patch_series_plan.md` hash=`665d34bcc31081e5e773774f465c6771633002ad7d079e8a08864afac1e12177`
- id=15 type=`patchgen_report` ref=`reports/validation_execution_report.md` hash=`70062f55c9b1c8cd0ad3054fa4633a40394f44b11461def84b3bf45ca5628356`

## Replay Notes
- Patch proposal artifacts are replay-linked via engineering_evidence_links.
- Governance decision remains pending; lineage is complete up to approval request stage.
