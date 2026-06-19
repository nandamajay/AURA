# AURA Application Model

## Current Nature Of AURA

AURA is not yet a fully plug-and-play product. Today it is best described as a hybrid of:

- A framework for governed driver conversion experiments.
- A PM/governance layer around LLM execution.
- A deterministic verifier/gate system for scoring, lineage, and copy-risk checks.
- A knowledge base of conversion attempts, evidence, blockers, and lessons.
- A future productized application once run manifests, input packages, gates, and PM skills are standardized.

## Plug-And-Play Assessment

AURA is partially plug-and-play for downstream-to-upstream conversion when the driver has an upstream target or close references and the operator follows the established governance prompts. It is not yet plug-and-play for arbitrary new drivers because input packaging, mode selection, compile gates, runtime evidence ingestion, and folder governance are still partly manual.

## Biggest Advantages

- Converts LLM output from untrusted code into gated artifacts.
- Forces evidence, lineage, replay, and fail-closed decisions.
- Catches copy/derivation issues that raw score-only workflows miss.
- Supports both existing-upstream-target scoring and no-target RFC workflows.
- Builds durable KB from failed and successful iterations.
- Encourages upstream-first architecture instead of downstream code dumping.

## Biggest Disadvantages

- Generation remains prompt-driven and can vary across terminals.
- PM behavior is strong but not yet installed as a reusable skill.
- New-driver scoring has no true equivalent target and therefore relies on gates, compile, and evidence rather than score.
- Compile/checkpatch/runtime validation are not yet first-class gate inputs.
- Multiple AURA folders create source-of-truth risk.
- Runtime-sensitive decisions still need human hardware evidence.

## Difference From Normal LLM Conversion

Normal LLM conversion often produces code, self-reports a score, and moves on. AURA adds:

- Bounded source access.
- Explicit allowlists.
- Patch lineage.
- Deterministic scoring and verifier output.
- Anti-copy/derivation checks.
- Fail-closed blocker handling.
- PM verdicts and evidence packages.
- Iterative learning from blind, skeleton-informed, and hybrid variants.

## What Prevents Production Use

- No universal driver input package schema.
- No deterministic conversion mode selector.
- No canonical compile/checkpatch gate integration.
- No runtime evidence parser.
- No global PM skill installed for cross-terminal consistency.
- No formal prompt registry.
- Folder governance ambiguity.

## What To Build Before Scaling

1. Unified run manifest and driver input package schemas.
2. New-driver/no-target gate mode.
3. Compile and checkpatch gate integration.
4. AURA PM skill installation.
5. Prompt registry.
6. Runtime/hardware evidence ingestion.
7. Folder source-of-truth consolidation.
