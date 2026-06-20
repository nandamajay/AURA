# AURA Upstream Reviewer Simulation — Execution Blueprint

## Phase 1: Prototype Execution Plan

### Step 1: Implement upstream_reviewer_sim.py

New module under:
`AURA/agents/src/aura_agents/upstream_reviewer_sim.py`

Responsibilities:
- CLI entry point.
- Lens dispatcher.
- Patch Structure Lens (built-in).
- Build/Compile Lens (built-in).
- Orchestrate existing lenses.
- Comment aggregator.
- Output writer.

### Step 2: Integrate Existing Lenses

Order of integration:

1. `upstream_philosophy.py` — already works standalone, consume output.
2. `wcd_rule_pack_checker.py` — already works standalone, consume output.
3. `simulation.py` — consume for audio subsystems.
4. `dts_bindings.py` — review and consume for DT lens.
5. `reviewer_behavior_model_v1.py` — consume offline profiles only, no live Patchwork fetch.
6. `maintainer_intel.py` — consume offline only, no live DB.

### Step 3: First Pilot Run

Target: WCD9378 A.1 compile-ready patches.

```bash
PYTHONPATH=AURA/agents/src python -m aura_agents.upstream_reviewer_sim \
  --run-dir AURA_KB/drivers/wcd9378/static_prototype_variant_a1_compile_ready \
  --subsystem soundwire-codec \
  --lenses patch-structure,dt-binding,upstream-philosophy,rule-pack,build \
  --rules AURA_KB/drivers/wcd_codec_family/rule_promotion_01/wcd_codec_family_rules_promoted.json \
  --output AURA_KB/platform_tools/upstream_reviewer_sim_01/pilots/wcd9378_a1_review
```

Expected outputs:
- `wcd9378_a1_review/upstream_review_report.json`
- `wcd9378_a1_review/review_comments.md`
- `wcd9378_a1_review/maintainer_questions.md`
- `wcd9378_a1_review/fix_plan.md`
- `wcd9378_a1_review/pm_review_verdict.md`

### Step 4: Second Pilot Run

Target: WSA884x Variant B patches.

```bash
PYTHONPATH=AURA/agents/src python -m aura_agents.upstream_reviewer_sim \
  --run-dir AURA_KB/drivers/wsa884x_three_variant_experiment/variant_b_relative_skeleton \
  --subsystem audio-amplifier \
  --lenses patch-structure,dt-binding,upstream-philosophy,rule-pack,build \
  --rules AURA_KB/drivers/wcd_codec_family/rule_promotion_01/wcd_codec_family_rules_promoted.json \
  --output AURA_KB/platform_tools/upstream_reviewer_sim_01/pilots/wsa884x_variant_b_review
```

### Step 5: PM Evaluation

After both pilots:
- Did the simulation find real issues?
- Did it surface known WCD9378 runtime blockers correctly?
- Did it produce false positives?
- Which lenses were most useful?
- Which lenses need tuning?

---

## Data Flow Diagram

```
Input Package
    │
    ├── patches/*.patch ──────────────────► Patch Structure Lens
    │                                            │
    ├── patch_lineage.json ──────────────► Rule Pack Lens
    │                                            │
    ├── governance_verdict.json ──────────► Rule Pack Lens
    │                                            │
    ├── checkpatch_report.json ───────────► Build/Compile Lens
    │                                            │
    ├── full_build_result.json ───────────► Build/Compile Lens
    │                                            │
    ├── scoring_result_v4.json ───────────► Comment Aggregator
    │                                            │
    ├── allowed_sources.json ────────────► Rule Pack Lens
    │                                            │
    ├── runtime_fail_closed_items.json ──► Comment Aggregator
    │                                            │
    └── converted/*.c *.h ───────────────► DT Binding Lens
                                           Upstream Philosophy Lens
                                           Subsystem Simulation Lens
                                                │
                                         Comment Aggregator
                                                │
                                         Output Package
                                                │
                              ┌─────────────────┼─────────────────┐
                              │                 │                 │
                   upstream_review_report.json  │         fix_plan.md
                              │         review_comments.md        │
                              │                 │    maintainer_questions.md
                              └─────────────────┴─────────────────┘
                                                │
                                       pm_review_verdict.md
```

---

## Comment Severity Ordering

When generating `fix_plan.md`, order by:

1. `BLOCKING_REVIEW_ISSUE` — fix before any RFC submission.
2. `SHOULD_FIX_BEFORE_RFC` — strong recommendation.
3. `RUNTIME_EVIDENCE_REQUIRED` — document and wait for hardware.
4. `QUESTION_FOR_MAINTAINER` — prepare answer or ask explicitly.
5. `STYLE_NIT` — fix if time permits.
6. `FALSE_POSITIVE_RISK` — review manually, do not act blindly.

---

## Governance Rules For Simulation

1. Simulation output is advisory only in Phase 1.
2. Every comment must cite evidence: file, line, artifact, or pattern.
3. Every heuristic check must declare `false_positive_risk`.
4. `RUNTIME_EVIDENCE_REQUIRED` must never become a gate blocker.
5. Simulation must not modify any source, patch, or AURA artifact.
6. PM must review output before acting.
7. Simulation must not claim "maintainer will accept."
8. Simulation must not invent objections without evidence.

---

## Success Metrics For Phase 1

- Generates valid JSON report.
- Surfaces at least one known WCD9378 runtime blocker.
- Does not claim runtime readiness.
- Does not modify any source.
- Produces actionable fix_plan.md.
- PM can use output to improve patches before RFC.

---

## Next Steps After Phase 1

1. Validate on 3 historical accepted patches from Patchwork.
2. Validate on 3 historical rejected patches from Patchwork.
3. Measure false positive rate.
4. Tune heuristics.
5. Propose advisory gate integration.
