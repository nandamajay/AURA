# Provenance Runtime Guarantee Classification

Date: 2026-05-18

## Guaranteed (Implemented + Runtime-Validated)
- Source intake canonical hashing and duplicate rejection.
- Intake table immutability (`UPDATE/DELETE` blocked by trigger).
- Event and lineage append-only mutation constraints (`UPDATE/DELETE` blocked by trigger).
- Role-gated untrusted intake approval path (reviewer blocked, approver allowed).
- Audit-visible trust overrides (`config.changed` entry).
- Deterministic reconstruction hash under unchanged persisted state.

## Strong but Bounded
- Lineage ordering determinism:
  - corrected to insertion-aware ordering (`created_at,rowid`) and validated.
  - bounded by single-node SQLite ordering semantics.
- Trust classification quality:
  - rule-based validation and lineage checks are deterministic.
  - bounded by metadata completeness and URL/anchor quality.

## Best Effort / Not Guaranteed in This Phase
- External repository availability/reachability validation (network trust is not fully attested).
- Cryptographic authenticity of remote source refs (no signed tag/commit verification yet).
- Malicious actor with direct DB write access bypassing API role checks (outside current runtime trust boundary).

## Explicitly Out of Scope in This Phase
- Autonomous learning / self-training / fine-tuning.
- Distributed provenance replication.
- Multi-node ingestion coordination.
