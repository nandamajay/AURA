# PM Architecture Summary

## 1. Is AURA Ready As Plug-And-Play Today?

No. AURA is `PARTIAL_NOT_PLUG_AND_PLAY_YET`.

AURA is strong enough for governed experiments and compile-ready RFC workflows, but not yet a fully productized plug-and-play platform for arbitrary downstream-to-upstream conversions.

## 2. What Is Ready?

- Existing-upstream-target scoring through v3/v4 scorers.
- Multi-file scoring.
- Canonical conversion gate.
- Anti-copy and derivation verifier.
- Allowed-source artifact requirement.
- Patch lineage checking.
- WCD937x/WCD9378 KB methodology.
- Static prototype and RFC-only workflows.

## 3. What Is Not Ready?

- First-class new-driver/no-target scoring mode.
- Compile/checkpatch as canonical gates.
- Runtime evidence ingestion.
- Prompt registry.
- Conversion mode selector.
- Cross-terminal PM behavior without conversation memory.
- Folder governance across multiple AURA directories.

## 4. What Must Be Fixed Before Scaling?

P0 fixes:

1. Unified run manifest schema.
2. Driver input package schema.
3. Compile/checkpatch gates.
4. New-driver/no-target gate mode.
5. Prompt registry.
6. Installable `aura-pm` skill.
7. Folder source-of-truth policy.

## 5. Should We Create/Install An Actual `aura-pm` Skill Globally?

Yes, but not blindly in this run. This audit creates a draft under `AURA_KB/platform_architecture/aura_pm_skill_draft/SKILL.md`. Review it first, then install globally once accepted.

## 6. Should AURA PM Run Separately From Execution Agents?

Yes for production-like work. Recommended split:

- Terminal 1: AURA PM / architect / adversarial reviewer.
- Terminal 2: execution agent for conversion, compile, and artifact generation.

The PM terminal should own verdicts, not code generation velocity.

## 7. Recommended Next 3-Step Roadmap

1. Finish WCD9378 A.1 compile-ready validation and capture honest compile/checkpatch results.
2. Review and install the `aura-pm` skill for cross-terminal consistency.
3. Implement P0 platform gates: run manifest, no-target gate mode, compile gate, checkpatch gate, and prompt registry.

## 8. Before Continuing WCD9378 After Compile A.1

- Do not add LPASS PM runtime changes without runtime evidence.
- Do not add reset-in-`hw_params()` workaround.
- Do not claim playback/capture support.
- Ingest Monday hardware evidence into the existing evidence checklist.
- Resolve SDW identity, paging runtime proof, Class-H behavior, board DTS, and runtime validation blockers before moving beyond RFC-only.
