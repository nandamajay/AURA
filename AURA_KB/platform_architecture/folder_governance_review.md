# Folder Governance Review

## Source Of Truth

The current source of truth for upstream-learning work is:

- Repo: `/local/mnt/workspace/AURA_V1_upstream`
- Branch: `aura_upstream_learning`
- Tooling root: `AURA/agents/src/aura_agents/`
- KB root: `AURA_KB/`
- Kernel corpus: `track_b_corpora/linux-next/`

Future agents should use `/local/mnt/workspace/AURA_V1_upstream` as `cwd` for this workstream unless a new source-of-truth decision artifact explicitly says otherwise.

## Governance Risk From Multiple Folders

The workspace contains multiple AURA-named folders: `AURA`, `AURA_V1`, `AURA_V1_ops`, and `AURA_V1_upstream`. This creates real governance risk:

- Agents may run tools from one folder and write artifacts to another.
- Git branches and dirty worktrees can diverge.
- Governance improvements may be implemented in one repo and not used by another.
- `/tmp` replay work is valid for isolation but can hide provenance unless commands and copied inputs are recorded.

Observed risk level: `RISK`, not `FAIL`. Current WCD937x/WCD9378 KB work is coherent inside `AURA_V1_upstream`, but sibling folders should not be treated as interchangeable.

## Consolidation Recommendation

- Keep `AURA_V1_upstream` as active source of truth for upstream driver conversion learning.
- Treat sibling `AURA`, `AURA_V1`, and `AURA_V1_ops` as separate workstreams or archives until a signed consolidation plan exists.
- Move production conversion gates under `AURA/agents/src/aura_agents/` in the active repo.
- Keep KB/training artifacts under `AURA_KB/` in the active repo.
- Store reusable prompts under a future `AURA_KB/prompts/` registry.
- Store architecture decisions under a future `AURA_KB/adr/` or `AURA_KB/platform_architecture/adr/` path.

## /tmp Execution Policy

Temporary worktrees under `/tmp` are acceptable for patch replay, compile, and isolation, but must not become source of truth.

Required controls:

- Every `/tmp` validation must record source repo SHA, command, output path, and copied artifact path.
- Final artifacts must be copied back under `AURA_KB/`.
- Gate verdicts must live under the tracked repo, not only `/tmp`.
- PM summaries must distinguish temporary validation from committed evidence.
- Agents must never silently use `/tmp` generated code as if it were canonical.

## What Should Be Read-Only Archive

- Historical variants without canonical gates should remain reference data, not acceptance data.
- Invalid copied/derivative variants should be retained as negative examples but clearly marked invalid.
- Sibling folders should be read-only for this workstream unless a task explicitly scopes cross-repo synchronization.
