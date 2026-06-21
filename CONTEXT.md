# AURA Session Context — Handoff Document

> Read this at the start of every new CLI session to reconstruct state in 60 seconds.
> Last updated: 2026-06-21

---

## Repo / Branch

- CWD: `/local/mnt/workspace/AURA_V1_upstream`
- Branch: `aura_upstream_learning`
- Terminology: `LA` = downstream/Linux Android, `LE` = upstream/Linux Embedded

---

## Active Tracks

### Track 1: WCD9378 Driver Conversion — PAUSED

- State: `COMPILE_READY_RFC` — not runtime-ready
- A.1 patches compile on arm64 linux-next (build at `/local/mnt/workspace/aura_builds/wcd9378_a1_linux/`)
- Waiting for Monday hardware evidence from ELIZA board
- Key artifacts: `AURA_KB/drivers/wcd9378/static_prototype_variant_a1_compile_ready/`
- Runtime blockers still open: SDW identity, paging, Class-H, playback/capture, detach/re-enumeration
- **Do NOT modify WCD9378 code until hardware evidence arrives**
- Evidence request package: `AURA_KB/drivers/wcd9378/evidence_request_01/`

### Track 2: AURA Production Platform Hardening — Phase 3 COMPLETE

- Production system: `/local/mnt/workspace/AURA/`
- Progress: `PRODUCTION_PROGRESS.json`
- **Phase 0**: COMPLETED (11/11) — architecture audit, contract registry
- **Phase 1**: COMPLETED (28/28) — state machine, contracts, execution stages, fail-closed
- **Phase 2**: COMPLETED (20/20) — provider abstraction, retry/circuit-breaker, budget, cache
- **Phase 3**: COMPLETED (19/19) — approval workflow, charter enforcement, hash-chained audit, safety boundaries
- **Current phase**: phase_4 (Replay & Determinism) — NOT_STARTED
- Tests: 103 passing in `/local/mnt/workspace/AURA/`
- Production commits are local-only (no remote configured on AURA repo)
- Phase 3 audit: `PHASE_3_AUDIT_REPORT.json`

### Track 3: Upstream Reviewer Simulation — Phase 1 COMPLETE

- Progress: `AURA_KB/platform_tools/upstream_reviewer_sim_01/plan/progress_tracker.json`
- **Phase 0**: COMPLETED (R4) — lore.kernel.org profiles for 4 P0 reviewers at HIGH confidence
  - Mark Brown: HIGH (65 threads), Kozlowski: HIGH (53), Bossart: HIGH (242), Koul: HIGH (210)
  - Bjorn Andersson: LOW_CONFIDENCE, Linus Walleij: LOW_CONFIDENCE
  - Liam Girdwood: INACTIVE (0 messages 2021–2025), Konrad Dybcio: INACTIVE
  - Profiles: `AURA_KB/reviewer_profiles/processed/*_profile_v4.json`
- **Phase 1**: COMPLETED_WITH_WARNINGS — simulation engine built, pilots run
  - Engine: `AURA/agents/src/aura_agents/upstream_reviewer_sim.py`
  - WCD9378 A.1 pilot: `AURA_KB/platform_tools/upstream_reviewer_sim_01/pilots/wcd9378_a1_review/`
    - Verdict: NEEDS_WORK, 0 blocking, 6 warnings, upstream-philosophy lens FAIL_CLOSED
  - WSA884x Variant B pilot: `AURA_KB/platform_tools/upstream_reviewer_sim_01/pilots/wsa884x_variant_b_review/`
  - PM eval: `AURA_KB/platform_tools/upstream_reviewer_sim_01/pilots/pm_phase1_evaluation.json`
- **Phase 2**: BLOCKED_ON_PHASE_1_SIGNOFF — needs PM sign-off to proceed
- **Next action**: PM sign-off on Phase 1 → then Phase 2 (subsystem simulation integration)

---

## Key Artifacts Quick Reference

| Artifact | Path |
|---|---|
| Production progress | `PRODUCTION_PROGRESS.json` |
| Production dashboard | `PRODUCTION_DASHBOARD.md` |
| Phase 3 audit | `PHASE_3_AUDIT_REPORT.json` |
| Reviewer sim tracker | `AURA_KB/platform_tools/upstream_reviewer_sim_01/plan/progress_tracker.json` |
| Reviewer profiles | `AURA_KB/reviewer_profiles/processed/` |
| WCD family rules | `AURA_KB/drivers/wcd_codec_family/rule_promotion_01/wcd_codec_family_rules_promoted.json` |
| WCD9378 evidence request | `AURA_KB/drivers/wcd9378/evidence_request_01/` |
| AURA PM skill | `AURA_KB/platform_architecture/aura_pm_skill_draft/SKILL.md` |
| Platform architecture | `AURA_KB/platform_architecture/` |

---

## Immediate Next Actions (priority order)

1. **Reviewer Sim Phase 2** — PM sign-off on Phase 1 → start subsystem simulation integration
2. **Production Phase 4** — Replay & Determinism hardening (snapshot isolation, integrity, recovery)
3. **WCD9378** — Wait for Monday hardware evidence; do not modify code before then

---

## Governance Reminders

- Never modify kernel source outside `AURA_KB/` artifacts
- Never modify WCD9378 generated source before hardware evidence
- Never self-report scores without canonical gate artifacts
- All JSON artifacts must be parse-valid before commit
- Always commit and push after completing a task
- Production AURA repo has no remote — commits are local only

