# Future Expansion Guidance (Engineering Domain Anchored)

Date: 2026-05-18

## 1) Expansion Philosophy
- domain evolution must preserve deterministic kernel simplicity
- replay integrity and governance continuity are non-negotiable
- every expansion must be evidence-gated

## 2) Good Expansion Patterns
1. Add domain plugin capabilities through existing plugin contract and core-governed APIs.
2. Improve patch workflow completeness by adding explicit lifecycle transitions in core services with replay/audit linkage.
3. Strengthen validation orchestration by adding first-class validation lineage while preserving current deterministic semantics.
4. Expand operator UX using existing evidence and governance endpoints.

## 3) Bad Expansion Patterns
1. Embedding business/agency workflow automation directly into `aura-core` correctness kernel.
2. Introducing hidden autonomous approval actions to speed throughput.
3. Adding distributed infrastructure to mask unresolved single-node bounded behaviors.
4. Treating bounded transport behavior as guaranteed delivery in status surfaces.

## 4) Infrastructure Escalation Triggers (Definition Only)
Escalation can only be considered when:
- repeated high-severity evidence proves single-node bounds are exceeded
- replay/governance semantics can be preserved or strengthened
- local deterministic mitigations are exhausted

This document does not authorize escalation and does not propose implementation.
