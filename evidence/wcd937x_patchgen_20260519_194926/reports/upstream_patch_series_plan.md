# Upstream Patch Series Plan (Controlled Proposal)

Generated: `2026-05-19T14:35:35.174224+00:00`

## Workflow Binding
- intake_id: `422644851b76d1651150bf26e9d363ca`
- source_snapshot_id: `e04874f825598459c536cd1a4b87b31b`
- engineering_snapshot_id: `3af35b086646f957681633c6d6c404d8`
- workflow_id: `f1a7203028b455b0b1086517d3070801`
- task_id: `06f970ba-bcb8-4c26-a546-b1e33956f8e9`
- provenance: `ssh://review-android.quicinc.com:29418/platform/vendor/qcom/opensource/audio-kernel-ar` @ `audio-kernel-cmn.lnx.0.0` (`466891703077f54117390782cce636830ad8ae1c`)

## Patch Groups
### Group 1: build/symbol wiring
- proposed git diff: `generated_patch_diffs/0001-ASoC-codecs-wcd937x-annotate-build-wiring-constraint.patch`
- commit message: `ASoC: codecs: wcd937x: annotate build wiring constraints for migration`
- upstream rationale: Keep WCD937x core/SDW split explicit and surface migration constraints at Kconfig/Makefile boundary.
- affected dependencies: Kconfig symbol graph, Makefile object wiring, SND_SOC_WCD937X(_SDW)
- unresolved blockers: No sign-off/commit body yet; needs maintainer-quality message and operator review.
- validation expectations: checkpatch clean after sign-off/message fixes; compile depends on prepared kernel config.
- replay evidence linkage: workflow `f1a7203028b455b0b1086517d3070801` evidence table + lineage stage entries
- classification: **advisory-only**

### Group 2: codec core port
- proposed git diff: `generated_patch_diffs/0002-ASoC-codecs-wcd937x-add-core-port-migration-guardrai.patch`
- commit message: `ASoC: codecs: wcd937x: add core-port migration guardrails`
- upstream rationale: Annotate codec core boundary to prevent downstream-only hooks from being reintroduced during porting.
- affected dependencies: wcd937x core, wcd-common, mbhc/clsh integration path, regmap/pm-runtime touchpoints
- unresolved blockers: No functional downstream feature parity implemented in this patch; comments only.
- validation expectations: No functional regression expected; final port requires real code deltas + compile closure.
- replay evidence linkage: workflow `f1a7203028b455b0b1086517d3070801` evidence table + lineage stage entries
- classification: **advisory-only**

### Group 3: SoundWire transport migration
- proposed git diff: `generated_patch_diffs/0003-ASoC-codecs-wcd937x-sdw-document-SWR-to-SDW-migratio.patch`
- commit message: `ASoC: codecs: wcd937x-sdw: document SWR to SDW migration boundary`
- upstream rationale: Capture SWR→SDW ownership boundary explicitly before functional transport-porting changes.
- affected dependencies: wcd937x-sdw channel maps, sdw_stream_add_slave path, SDW transport assumptions
- unresolved blockers: Real transport semantic conversion still unresolved; no SWR compatibility shim included.
- validation expectations: Compile subject to prepared kernel tree; follow-up patch needed for behavior alignment.
- replay evidence linkage: workflow `f1a7203028b455b0b1086517d3070801` evidence table + lineage stage entries
- classification: **advisory-only**

### Group 4: MBHC/CLSH alignment
- proposed git diff: `generated_patch_diffs/0004-ASoC-codecs-add-MBHC-CLSH-conversion-alignment-notes.patch`
- commit message: `ASoC: codecs: add MBHC/CLSH conversion alignment notes for WCD937x`
- upstream rationale: Flag MBHC and Class-H as dedicated validation gates for WCD937x migration sequencing.
- affected dependencies: wcd-mbhc-v2, wcd-clsh-v2, headset detect flow, class-H power path
- unresolved blockers: No callback behavior rewrite yet; downstream calibration interactions unresolved.
- validation expectations: Needs targeted runtime audio validation once functional patches exist.
- replay evidence linkage: workflow `f1a7203028b455b0b1086517d3070801` evidence table + lineage stage entries
- classification: **advisory-only**

### Group 5: downstream abstraction removal
- proposed git diff: `generated_patch_diffs/0005-ASoC-codecs-wcd937x-record-downstream-abstraction-ex.patch`
- commit message: `ASoC: codecs: wcd937x: record downstream abstraction exclusion boundaries`
- upstream rationale: Pin explicit exclusion of qti-regmap-debugfs/msm_cdc/wcdcal wrappers in upstream codec scope.
- affected dependencies: qti-regmap-debugfs, msm_cdc_* wrappers, wcdcal hwdep calibration path
- unresolved blockers: No upstream-equivalent implementation for excluded downstream abstractions in current patchset.
- validation expectations: Cannot claim upstream compatibility until replacement strategy is implemented and validated.
- replay evidence linkage: workflow `f1a7203028b455b0b1086517d3070801` evidence table + lineage stage entries
- classification: **blocked**

### Group 6: DT binding alignment
- proposed git diff: `generated_patch_diffs/0006-dt-bindings-sound-qcom-wcd937x-clarify-upstream-sche.patch`
- commit message: `dt-bindings: sound: qcom,wcd937x: clarify upstream schema boundary`
- upstream rationale: Keep DT schema as upstream contract and reject downstream helper abstractions in binding surface.
- affected dependencies: qcom,wcd937x.yaml schema semantics, DT validation pipeline
- unresolved blockers: dt-doc-validate tool missing in current environment; schema checks not fully executable.
- validation expectations: dt_binding_check must pass with dtschema installed before submission.
- replay evidence linkage: workflow `f1a7203028b455b0b1086517d3070801` evidence table + lineage stage entries
- classification: **advisory-only**

## Classification Summary
- compile-ready: none (0)
- advisory-only: groups 1,2,3,4,6
- blocked: group 5
- unresolved dependency state: present (downstream-only abstraction parity incomplete + environment/tooling gaps)

## Authoritative Inputs Used
- `/local/mnt/workspace/AURA_V1/evidence/wcd937x_real_study_20260519_062557/reports/dependency_graph_report.md`
- `/local/mnt/workspace/AURA_V1/evidence/wcd937x_real_study_20260519_062557/reports/downstream_upstream_api_mapping_report.md`
- `/local/mnt/workspace/AURA_V1/evidence/wcd937x_real_study_20260519_062557/reports/semantic_transformation_plan.md`
- `/local/mnt/workspace/AURA_V1/evidence/wcd937x_real_study_20260519_062557/reports/patch_grouping_proposal.md`
- `/local/mnt/workspace/AURA_V1/evidence/wcd937x_real_study_20260519_062557/reports/replay_lineage_report.md`
