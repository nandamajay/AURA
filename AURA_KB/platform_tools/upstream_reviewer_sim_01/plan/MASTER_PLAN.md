# AURA Upstream Reviewer Simulation — Master Plan

## Document Purpose

This is the living master plan for the AURA Upstream Reviewer Simulation plugin.
It is updated every time a phase step is completed, started, or changed.
Progress cards are stored in `progress_cards/` and linked here.
Do not delete history — append only.

---

## Terminology

- `LA` = downstream / Linux Android
- `LE` = upstream / Linux Embedded
- `lore` = lore.kernel.org
- `Patchwork` = patchwork.kernel.org
- `RFC` = Request For Comments patch

---

## Overall Goal

Simulate focused upstream Linux kernel reviewer behavior on AURA-generated patch series.
Produce actionable, evidence-backed review comments grounded in real reviewer history.
Advisory only — not a replacement for real upstream review.

---

## Phase Overview

| Phase | Name | Status | Target Completion |
|---|---|---|---|
| 0 | Reviewer Pattern Learning | COMPLETED | Before Phase 1 |
| 1 | Simulation Engine Prototype | COMPLETED_WITH_WARNINGS | After Phase 0 |
| 2 | Subsystem Simulation Integration | COMPLETED_WITH_WARNINGS | After Phase 1 |
| 3 | Profile Validation | READY_TO_START | After Phase 2 |
| 4 | Advisory Gate Integration | NOT_STARTED | After Phase 3 |
| 5 | Warn Mode And Narrow Blocking | NOT_STARTED | After Phase 4 |

---

## Phase 0: Reviewer Pattern Learning

### Purpose
Build the real intelligence foundation.
Without this, simulation is just a linter.
With this, simulation is grounded in real reviewer behavior from lore/Patchwork history.

### Status: COMPLETED (via R4)

### Steps

| Step | Description | Status | Notes |
|---|---|---|---|
| 0.1 | Define subsystems and maintainers | COMPLETED | reviewer list and subsystem map finalized |
| 0.2 | Define fetch parameters | COMPLETED | fetch_parameters.json created |
| 0.3 | Fetch raw comment history | COMPLETED | raw artifacts generated for P0/P1/P2 |
| 0.4 | Filter and clean raw data | COMPLETED | min-word/bot/ack/CI/duplicate filters applied |
| 0.5 | Extract objection/acceptance patterns | COMPLETED | per-reviewer pattern sets extracted |
| 0.6 | Build per-reviewer behavioral profiles | COMPLETED | processed profiles generated where data available |
| 0.7 | Build per-subsystem rule sets | COMPLETED | rule files created for target subsystems |
| 0.8 | Validate profiles against known outcomes | COMPLETED | validation report + accuracy metrics generated |
| 0.9 | Store offline profiles in AURA_KB | COMPLETED | raw/processed/metadata separation enforced |
| 0.10 | PM review and sign-off | COMPLETED | see `pm_phase0_summary_r4.md` and `phase0_validation_r4.json` |

### Target Subsystems

| Subsystem | Scope Queries | Priority |
|---|---|---|
| ASoC/Qualcomm | `ASoC: qcom`, `ASoC: codecs` | P0 |
| SoundWire | `ASoC: SoundWire`, `soundwire: qcom` | P0 |
| DT Bindings Audio | `dt-bindings: sound: qcom`, `dt-bindings: sound` | P0 |
| Pinctrl Qualcomm | `pinctrl: qcom` | P1 |
| Qualcomm Platform | `arm64: dts: qcom`, `clk: qcom` | P2 |

### Target Reviewers

| Reviewer | Subsystem | Priority | Min Threads | Max Series |
|---|---|---|---|---|
| Mark Brown | ASoC/* | P0 | 50 | 500 |
| Pierre-Louis Bossart | ASoC/SoundWire | P0 | 50 | 300 |
| Krzysztof Kozlowski | dt-bindings/* | P0 | 50 | 400 |
| Vinod Koul | ASoC/qcom/SoundWire | P0 | 50 | 200 |
| Liam Girdwood | ASoC/* | P1 | 20 | 150 |
| Bjorn Andersson | qcom/* | P1 | 20 | 200 |
| Linus Walleij | pinctrl/* | P1 | 20 | 200 |
| Rob Herring | dt-bindings/* | P1 | 20 | 200 |
| Konrad Dybcio | qcom/* | P2 | 20 | 150 |

### Fetch Parameters

| Parameter | Value | Reason |
|---|---|---|
| Primary time window | 2023–2025 | Recent behavior most relevant |
| Secondary time window | 2021–2025 | For low-activity reviewers |
| Hard cutoff | Nothing before 2021 | Older rules may be outdated |
| Patch states | accepted, rejected, changes-requested | Only resolved outcomes |
| Minimum comment length | 20 words | Exclude trivial acks |
| Minimum threads per profile | 50 for primary, 20 for secondary | Statistical significance |
| Exclude | Bot comments, CI results, pure acks | Noise reduction |
| Profile rebuild frequency | Every 6 months | Keep current |
| Raw vs processed | Store separately | Re-process without re-fetch |

### Profile Confidence Levels

| Threads | Confidence |
|---|---|
| >= 50 | HIGH |
| 20–49 | MEDIUM / LOW_CONFIDENCE |
| < 20 | INSUFFICIENT_DATA |

### Storage Layout

```
AURA_KB/reviewer_profiles/
  raw/
    {reviewer_slug}_raw_{year_start}_{year_end}.json
  processed/
    {reviewer_slug}_profile_v{N}.json
  validation/
    profile_validation_results.json
    accuracy_report.md
  metadata/
    fetch_parameters.json
    fetch_log.json
    profile_versions.json
```

### Success Criteria

- [x] All P0 reviewers have HIGH confidence profiles.
- [x] P1 threshold met with approved inactivity exemption for Liam Girdwood.
- [x] Profiles validated against at least 3 known accepted patches.
- [x] Profiles validated against at least 3 known rejected patches.
- [x] Objection pattern precision >= 60%.
- [x] False positive rate on accepted patches <= 2 per run.
- [x] All profiles versioned and dated.
- [x] Raw data stored separately from processed profiles.

### Known Limitations

- Cannot fetch private email threads.
- Cannot fetch IRC/Slack discussions.
- Cannot get verbal agreements from conferences.
- Patchwork API may have gaps in older data.
- Reviewer behavior may change after profile is built.
- Profile must be rebuilt every 6 months.

---

## Phase 1: Simulation Engine Prototype

### Purpose
Build the orchestrator using Phase 0 profiles.
Run first pilots on WCD9378 A.1 and WSA884x Variant B.

### Status: COMPLETED_WITH_WARNINGS

### Steps

| Step | Description | Status | Notes |
|---|---|---|---|
| 1.1 | Implement upstream_reviewer_sim.py orchestrator | COMPLETED | `aura_agents.upstream_reviewer_sim` added |
| 1.2 | Implement Patch Structure Lens | COMPLETED | deterministic static checks implemented |
| 1.3 | Implement Build/Compile Lens | COMPLETED | compile artifact + Kconfig/Makefile checks implemented |
| 1.4 | Integrate upstream_philosophy.py | COMPLETED | implemented with `FAIL_CLOSED` fallback on runtime import incompatibility |
| 1.5 | Integrate wcd_rule_pack_checker.py | COMPLETED | checker integrated and mapped into lens findings |
| 1.6 | Implement Comment Aggregator | COMPLETED | dedupe, severity sort, reviewer confidence tagging implemented |
| 1.7 | Implement Output Writer | COMPLETED | JSON + 3 markdown artifacts produced per pilot |
| 1.8 | Pilot run on WCD9378 A.1 | COMPLETED | output in `pilots/wcd9378_a1_review/` |
| 1.9 | Pilot run on WSA884x Variant B | COMPLETED | output in `pilots/wsa884x_variant_b_review/` |
| 1.10 | PM evaluation | COMPLETED | `pilots/pm_phase1_evaluation.json` |

### Success Criteria

- [x] Generates valid JSON report.
- [x] Surfaces known WCD9378 runtime blockers.
- [x] Does not claim runtime readiness.
- [x] Does not modify any source.
- [x] Produces actionable fix_plan.md.
- [x] PM can use output to improve patches before RFC.

---

## Phase 2: Subsystem Simulation Integration

### Purpose
Add deeper subsystem-specific checks using existing AURA simulation modules.

### Status: COMPLETED_WITH_WARNINGS

### Steps

| Step | Description | Status | Notes |
|---|---|---|---|
| 2.1 | Fix StrEnum Python 3.10 compatibility | COMPLETED | `step_2_1_strenum_fix.json` recorded |
| 2.2 | Add ASoC/Qualcomm subsystem lens grounded in v4 profiles | COMPLETED | `asoc-subsystem` lens integrated into dispatcher |
| 2.3 | Enhance DT binding lens with YAML/schema checks | COMPLETED | profile-linked DT checks + suggested filename output |
| 2.4 | Add subsystem focus profile weighting | COMPLETED | reviewer verdicts tagged as primary/secondary |
| 2.5 | Pilot on WCD939x Variant 1 | COMPLETED | output in `pilots/wcd939x_variant1_review/` |
| 2.6 | PM evaluation and secondary pilot (WSA884x Variant C) | COMPLETED | `pm_phase2_evaluation.json` + `pilots/wsa884x_variant_c_review/` |

### Success Criteria

- [x] Subsystem simulation adds >= 3 new useful comments vs Phase 1 baseline.
- [x] DT binding lens catches at least one real DT issue per pilot.
- [x] Subsystem reviewer weighting is active in reviewer verdict output.

---

## Phase 3: Profile Validation

### Purpose
Prove simulation has real reviewer signal, not just heuristics.

### Status: READY_TO_START

### Steps

| Step | Description | Status | Notes |
|---|---|---|---|
| 3.1 | Select 3 known-accepted patches from Patchwork | NOT_STARTED | |
| 3.2 | Select 3 known-rejected patches from Patchwork | NOT_STARTED | |
| 3.3 | Run simulation on all 6 | NOT_STARTED | |
| 3.4 | Compare vs real reviewer comments | NOT_STARTED | |
| 3.5 | Measure precision/recall | NOT_STARTED | |
| 3.6 | Tune profiles and heuristics | NOT_STARTED | |
| 3.7 | PM sign-off | NOT_STARTED | |

### Success Criteria

- [ ] Simulation catches >= 70% of real reviewer objections on rejected patches.
- [ ] Simulation produces < 2 false BLOCKING_REVIEW_ISSUE on accepted patches.
- [ ] PM trusts output as useful signal.

---

## Phase 4: Advisory Gate Integration

### Purpose
Embed simulation output into canonical gate in advisory mode.

### Status: NOT_STARTED (blocked on Phase 3)

### Steps

| Step | Description | Status | Notes |
|---|---|---|---|
| 4.1 | Design gate integration schema extension | NOT_STARTED | |
| 4.2 | Implement --reviewer-sim gate flag | NOT_STARTED | |
| 4.3 | Embed reviewer_sim_summary in governance_verdict.json | NOT_STARTED | |
| 4.4 | Verify gate verdict unchanged in advisory mode | NOT_STARTED | |
| 4.5 | Regression tests | NOT_STARTED | |
| 4.6 | PM sign-off | NOT_STARTED | |

### Success Criteria

- [ ] Gate runs cleanly with and without --reviewer-sim.
- [ ] Simulation findings appear in gate verdict artifact.
- [ ] No false gate failures introduced.
- [ ] Regression tests pass.

---

## Phase 5: Warn Mode And Narrow Blocking

### Purpose
Promote narrow, high-confidence simulation findings to gate warnings or blockers.

### Status: NOT_STARTED (blocked on Phase 4)

### Steps

| Step | Description | Status | Notes |
|---|---|---|---|
| 5.1 | Define narrow blocking criteria | NOT_STARTED | |
| 5.2 | Implement warn mode for high-confidence checks | NOT_STARTED | |
| 5.3 | Regression tests for all promoted checks | NOT_STARTED | |
| 5.4 | False positive rate measurement | NOT_STARTED | |
| 5.5 | PM sign-off | NOT_STARTED | |

### Success Criteria

- [ ] False positive rate < 10% for promoted checks.
- [ ] Regression tests pass.
- [ ] No good patches are blocked.
- [ ] RUNTIME_EVIDENCE_REQUIRED never becomes blocking.

---

## Governance Guardrails (All Phases)

- Simulation never modifies source or artifacts.
- RUNTIME_EVIDENCE_REQUIRED never becomes blocking.
- Every heuristic declares false positive risk.
- PM reviews simulation output before acting.
- Simulation never claims "maintainer will accept."
- Phase N+1 cannot start until Phase N success criteria are met.
- All profiles versioned and dated.
- Raw data stored separately from processed profiles.

---

## Progress History

| Date | Phase | Step | Action | Result |
|---|---|---|---|---|
| 2026-06-21 | - | - | Master plan created | DONE |
| 2026-06-21 | 0 | 0.R4 | lore-based profile rebuild completed | PHASE_0_COMPLETE |
| 2026-06-21 | 1 | 1.1-1.10 | simulation prototype implemented + two pilot runs completed | PHASE_1_COMPLETE_WITH_WARNINGS |
| 2026-06-22 | 2 | 2.1-2.6 | subsystem simulation integration, dual pilots, PM evaluation | PHASE_2_COMPLETED_WITH_WARNINGS |

---

## Open Questions

| ID | Question | Raised | Status |
|---|---|---|---|
| Q1 | Should Phase 1 include simulation.py or keep artifact-only? | 2026-06-21 | RESOLVED (artifact-first with fail-closed integration hooks) |
| Q2 | First pilot: WCD9378 A.1 only or also WSA884x Variant B? | 2026-06-21 | OPEN |
| Q3 | Should fix_plan.md include code suggestions or issue identification only? | 2026-06-21 | OPEN |
| Q4 | Patchwork API rate limits — do we need caching strategy? | 2026-06-21 | OPEN |
| Q5 | Should reviewer profiles be public in AURA_KB or private? | 2026-06-21 | OPEN |


### Phase 0 Update (2026-06-21)
- Verdict: `PHASE_0_FAILED_RETRY_REQUIRED`
- P0 HIGH confidence reviewers: 1/4
- P1 LOW/HIGH confidence reviewers: 2/4
- Artifacts: `AURA_KB/reviewer_profiles/`

### Phase 0 R4 Update (2026-06-21)
- Verdict: `PHASE_0_COMPLETE`
- P0 HIGH confidence reviewers: 4/4
- P1 LOW/HIGH threshold: met with confirmed inactivity exemption for Liam Girdwood
- Artifacts: `AURA_KB/reviewer_profiles/` (R1/R2/R3 preserved, R4 appended)

### Phase 1 Update (2026-06-21)
- Verdict: `PHASE_1_COMPLETE_WITH_WARNINGS`
- Implemented: `AURA/agents/src/aura_agents/upstream_reviewer_sim.py`
- Pilot outputs: `AURA_KB/platform_tools/upstream_reviewer_sim_01/pilots/`
- Noted warning: `upstream-philosophy` lens entered `FAIL_CLOSED` due runtime dependency mismatch in this environment

### Phase 2 Update (2026-06-22)
- Verdict: `PHASE_2_COMPLETED_WITH_WARNINGS`
- Implemented: StrEnum compatibility shim, ASoC subsystem lens, DT binding enhancements, subsystem reviewer weighting
- Pilot outputs: `wcd939x_variant1_review` and `wsa884x_variant_c_review`
- Artifacts: `AURA_KB/platform_tools/upstream_reviewer_sim_01/phase2/`
