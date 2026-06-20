# AURA Upstream Reviewer Simulation — Architecture Blueprint

## 1. Purpose

Simulate focused upstream Linux kernel reviewer behavior on AURA-generated patch series.

This is an **advisory simulation plugin**, not an authority.
It does not replace real upstream review.
It does not claim a patch will be accepted.
It produces actionable, evidence-backed review comments that help the author fix issues before sending to the mailing list.

---

## 2. Terminology

- `LA` = downstream / Linux Android
- `LE` = upstream / Linux Embedded
- `RFC` = Request For Comments patch series
- `LKML` = Linux Kernel Mailing List
- `Patchwork` = upstream patch tracking system

---

## 3. What Already Exists In AURA

AURA already has relevant building blocks:

```
reviewer_behavior_model_v1.py   — Patchwork/lore data-driven reviewer profiles
review_coordinator.py           — Patch review packet builder
simulation.py                   — Subsystem simulation (DAPM, PCM, SoundWire, runtime PM)
upstream_philosophy.py          — Upstream principle evaluator
maintainer_intel.py             — Maintainer engagement briefs
conversion_gate.py              — Governance gate with copy/lineage/scoring checks
wcd_rule_pack_checker.py        — Family rule compliance checker
```

The upstream reviewer simulation plugin **orchestrates** these existing modules
into a focused, lens-driven review workflow.

---

## 4. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AURA Upstream Reviewer Simulation                        │
│                         upstream_reviewer_sim.py                            │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
              ┌────────────────▼────────────────┐
              │         Input Package            │
              │  - patch series / run directory  │
              │  - allowed_sources.json          │
              │  - patch_lineage.json            │
              │  - governance_verdict.json       │
              │  - checkpatch_report.json        │
              │  - full_build_result.json        │
              │  - scoring_result_v4.json        │
              │  - rule_compliance_report.json   │
              │  - subsystem focus selector      │
              └────────────────┬────────────────┘
                               │
              ┌────────────────▼────────────────┐
              │         Lens Dispatcher          │
              │  Selects active review lenses    │
              │  based on subsystem + artifacts  │
              └──┬──────┬──────┬──────┬──────┬──┘
                 │      │      │      │      │
    ┌────────────▼─┐ ┌──▼───┐ ┌▼───┐ ┌▼───┐ ┌▼──────────────┐
    │  Patch       │ │  DT  │ │ Up │ │Rule│ │  Subsystem     │
    │  Structure   │ │Bind  │ │str │ │Pack│ │  Simulation    │
    │  Lens        │ │Lens  │ │Phi │ │Lens│ │  Lens          │
    │              │ │      │ │Lens│ │    │ │                │
    └──────┬───────┘ └──┬───┘ └┬───┘ └┬───┘ └──────┬─────────┘
           │            │      │      │             │
           └────────────┴──────┴──────┴─────────────┘
                               │
              ┌────────────────▼────────────────┐
              │       Comment Aggregator         │
              │  Deduplicates, ranks, classifies │
              │  review comments by severity     │
              └────────────────┬────────────────┘
                               │
              ┌────────────────▼────────────────┐
              │         Output Package           │
              │  upstream_review_report.json     │
              │  review_comments.md              │
              │  maintainer_questions.md         │
              │  fix_plan.md                     │
              │  pm_review_verdict.md            │
              └─────────────────────────────────┘
```

---

## 5. Review Lenses

Each lens is a focused review perspective. Lenses are independent and composable.

### Lens 1: Patch Structure Lens
**Module:** `upstream_reviewer_sim.py` (built-in)
**Checks:**
- Patch count and ordering.
- Commit message format: subject line, body, Signed-off-by.
- Cover letter presence and quality.
- Patch series logical ordering: header → SDW → codec → Kconfig/Makefile.
- No unrelated changes mixed in.
- No fixup commits in RFC.
- Patch size: not too large, not trivially small.

### Lens 2: DT Binding Lens
**Module:** `dts_bindings.py` (existing, extend)
**Checks:**
- Compatible string format.
- Required/optional property coverage.
- YAML binding alignment.
- No downstream-only DT properties.
- No board-specific assumptions in driver.
- Schema validation if binding YAML exists.

### Lens 3: Upstream Philosophy Lens
**Module:** `upstream_philosophy.py` (existing, consume)
**Checks:**
- Minimal scope.
- Clear rationale.
- Generic abstractions.
- No runtime hacks.
- No board-specific workarounds.
- Maintainability.
- Test evidence.

### Lens 4: Rule Pack Lens
**Module:** `wcd_rule_pack_checker.py` (existing, consume)
**Checks:**
- Family rule compliance.
- Vendor elimination.
- Runtime-sensitive fail-closed.
- Lineage coverage.
- Target access discipline.

### Lens 5: Subsystem Simulation Lens
**Module:** `simulation.py` (existing, consume)
**Checks:**
- Probe flow simulation.
- DAPM simulation if audio.
- SoundWire simulation if SDW.
- Runtime PM simulation.
- PCM simulation if audio.

### Lens 6: Maintainer Style Lens
**Module:** `reviewer_behavior_model_v1.py` (existing, consume)
**Checks:**
- Known objection patterns from real Patchwork data.
- Subsystem-specific style expectations.
- Reviewer preference signals.
- Historical acceptance/rejection patterns.

### Lens 7: Build/Compile Lens
**Module:** `upstream_reviewer_sim.py` (built-in)
**Checks:**
- Build result present and PASS.
- Checkpatch WARN/ERROR count.
- BTF/pahole caveats documented.
- Module ELF format correct.
- No unresolved symbols.

---

## 6. Comment Classification

Every review comment must be classified:

| Class | Meaning | Gate Effect |
|---|---|---|
| `BLOCKING_REVIEW_ISSUE` | Maintainer will likely reject | Advisory FAIL |
| `SHOULD_FIX_BEFORE_RFC` | Strong recommendation | Advisory WARN |
| `QUESTION_FOR_MAINTAINER` | Needs upstream decision | Advisory INFO |
| `STYLE_NIT` | Minor style issue | Advisory INFO |
| `RUNTIME_EVIDENCE_REQUIRED` | Cannot judge without hardware | FAIL_CLOSED_OK |
| `ALREADY_ADDRESSED` | Issue exists but is documented | Advisory PASS |
| `FALSE_POSITIVE_RISK` | Heuristic may be wrong | Advisory INFO |

---

## 7. Output Schema

### upstream_review_report.json

```json
{
  "artifact": "upstream_review_report",
  "generated_at_utc": "...",
  "sim_version": "prototype-0.1",
  "run_dir": "...",
  "subsystem_focus": "...",
  "lenses_active": [],
  "summary": {
    "overall_verdict": "BLOCKING|WARN|ADVISORY_ONLY|PASS|UNKNOWN",
    "blocking_count": 0,
    "should_fix_count": 0,
    "question_count": 0,
    "nit_count": 0,
    "runtime_blocked_count": 0
  },
  "comments": [
    {
      "comment_id": "...",
      "lens": "...",
      "classification": "...",
      "location": "file:line or patch:N or artifact:field",
      "comment": "...",
      "evidence": [],
      "recommended_fix": "...",
      "false_positive_risk": "LOW|MEDIUM|HIGH"
    }
  ],
  "lenses_run": [],
  "limitations": [],
  "pm_verdict": "..."
}
```

### review_comments.md
Human-readable review comments grouped by lens and severity.

### maintainer_questions.md
Questions that need upstream maintainer decision before the patch can be finalized.

### fix_plan.md
Ordered list of fixes recommended before sending to mailing list.

### pm_review_verdict.md
PM summary: what to fix now, what to defer, what to ask maintainer, what is runtime-blocked.

---

## 8. CLI Design

```bash
PYTHONPATH=AURA/agents/src python -m aura_agents.upstream_reviewer_sim \
  --run-dir AURA_KB/drivers/wcd9378/static_prototype_variant_a1_compile_ready \
  --subsystem soundwire-codec \
  --lenses patch-structure,dt-binding,upstream-philosophy,rule-pack,build \
  --rules AURA_KB/drivers/wcd_codec_family/rule_promotion_01/wcd_codec_family_rules_promoted.json \
  --output AURA_KB/platform_tools/upstream_reviewer_sim_01/wcd9378_a1_review_report
```

Required args:
- `--run-dir`
- `--output`

Optional args:
- `--subsystem`
- `--lenses`
- `--rules`
- `--strict`
- `--no-simulation`
- `--focus patch:N` to focus on a specific patch

---

## 9. Integration With Existing AURA Modules

```
upstream_reviewer_sim.py
    ├── consumes: conversion_gate governance_verdict.json
    ├── consumes: wcd_rule_pack_checker compliance report
    ├── consumes: upstream_philosophy assessment
    ├── consumes: simulation report
    ├── consumes: reviewer_behavior_model profiles
    ├── consumes: maintainer_intel brief
    ├── consumes: dts_bindings validation
    └── produces: upstream_review_report.json + markdown outputs
```

The plugin does NOT modify any of the consumed artifacts.
It reads them and produces a new review report.

---

## 10. Subsystem Focus Profiles

| Focus | Active Lenses | Key Checks |
|---|---|---|
| `soundwire-codec` | all | SDW identity, paging, regmap, DAPM, Class-H, MBHC |
| `audio-amplifier` | patch, dt, philosophy, rule-pack, build | DAPM, controls, SoundWire |
| `pinctrl` | patch, dt, philosophy, build | pin table, groups, functions, wake IRQ |
| `regulator` | patch, dt, philosophy, build | supply model, enable/disable, DT |
| `generic` | patch, philosophy, build | minimal scope, rationale, style |

---

## 11. Governance Guardrails

- Simulation is advisory only until validated on historical patches.
- `BLOCKING_REVIEW_ISSUE` does not block AURA gate unless explicitly configured.
- `RUNTIME_EVIDENCE_REQUIRED` must never become blocking.
- False-positive risk must be declared for every heuristic check.
- PM must review simulation output before acting on it.
- Simulation must not modify any source or artifact.

---

## 12. Rollout Plan

| Phase | Description | Entry Criteria | Exit Criteria |
|---|---|---|---|
| 1 | Prototype standalone | Architecture approved | Reports generated for WCD9378 A.1 |
| 2 | Validate on historical patches | Phase 1 done | Known-accepted patches score PASS |
| 3 | Advisory gate integration | Phase 2 done | Gate embeds report, no verdict change |
| 4 | Warn mode for known subsystems | Phase 3 done | False positive rate < 10% |
| 5 | Blocking for narrow criteria | Phase 4 done | Regression tests pass |

---

## 13. What This Is Not

- Not a replacement for real upstream review.
- Not a guarantee of acceptance.
- Not a runtime validator.
- Not a scoring system.
- Not a conversion tool.

---

## 14. PM Verdict On Readiness

- Architecture: READY TO IMPLEMENT
- Phase 1 prototype: START NOW
- Production gate integration: AFTER PHASE 2 VALIDATION
