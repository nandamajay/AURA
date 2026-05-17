# Human Authority & Safe Autonomy Charter

## Document Control

| Property | Value |
|----------|-------|
| Version | 1.0.0 |
| Status | Enforceable (code-implemented) |
| Date | 2026-05-15 |
| Classification | Platform Invariant — Constitutional |

---

## Table of Contents

1. [Core Principle](#1-core-principle)
2. [Six Autonomy Principles](#2-six-autonomy-principles)
3. [Mandatory Human Controls](#3-mandatory-human-controls)
4. [Self-Modification Prohibitions](#4-self-modification-prohibitions)
5. [High-Risk Actions Requiring Approval](#5-high-risk-actions-requiring-approval)
6. [Autonomous Execution Safety](#6-autonomous-execution-safety)
7. [Explainability Requirements](#7-explainability-requirements)
8. [Fail-Safe Principle](#8-fail-safe-principle)
9. [Enforcement Architecture](#9-enforcement-architecture)
10. [API Reference](#10-api-reference)
11. [Implementation](#11-implementation)

---

## 1. Core Principle

> **Autonomy must remain: bounded, observable, explainable, replayable, interruptible, reversible.**

> **Human governance is the final authority.**

The platform exists to **augment engineering capability**, not replace engineering authority. AURA must behave as **an accountable engineering operating system** — not an uncontrollable autonomous entity.

---

## 2. Six Autonomy Principles

| Principle | Definition | Enforcement |
|-----------|-----------|-------------|
| **BOUNDED** | Autonomy has defined limits — cannot exceed human-set boundaries | GovernanceGuard checks every action against RBAC + charter rules |
| **OBSERVABLE** | All actions are visible in real time | Audit ledger + event bus + WebSocket streaming |
| **EXPLAINABLE** | All actions have preserved reasoning traces | ExplainabilityTracker captures 6 lineage types |
| **REPLAYABLE** | All actions can be deterministically replayed | TaskRecorder + ReplayEngine with seeded RNG |
| **INTERRUPTIBLE** | All actions can be stopped by human operators | `POST /charter/intervene` — immediate pause/cancel |
| **REVERSIBLE** | All actions can be undone | `POST /charter/rollback` + state preservation |

---

## 3. Mandatory Human Controls

Eight manual control capabilities are always available, regardless of system state:

| Control | Endpoint | Description |
|---------|----------|-------------|
| **Manual Intervention** | `POST /api/v1/charter/intervene` | Pause or modify an ongoing autonomous action |
| **Manual Override** | `POST /api/v1/charter/override` | Force an action through automated blocks (with justification) |
| **Manual Rollback** | `POST /api/v1/charter/rollback` | Revert system to a previous state |
| **Manual Approval** | `POST /api/v1/charter/approvals/request` | Request explicit approval for high-risk actions |
| **Manual Replay Inspection** | `GET /api/v1/tasks/{task_id}/replay` | Inspect any task's deterministic replay |
| **Manual Task Cancellation** | `PATCH /api/v1/tasks/{task_id}/cancel` | Cancel any running or queued task |
| **Manual Audit Inspection** | `GET /api/v1/governance/audit` | Query the full append-only audit ledger |
| **Manual Policy Enforcement** | `POST /api/v1/charter/enforce` | Manually trigger policy enforcement checks |

**These endpoints cannot be disabled by the platform itself.** They are protected by the highest RBAC level and are exempt from autonomous blocking.

---

## 4. Self-Modification Prohibitions

The platform must **NEVER** silently:

| # | Prohibition | Pattern Detected | Severity |
|---|-------------|-----------------|----------|
| 1 | Rewrite governance rules | Actions containing "governance", "rule", "policy", "permission", "role" | CRITICAL |
| 2 | Rewrite replay semantics | Actions containing "replay", "snapshot", "task_log", "seed" | CRITICAL |
| 3 | Bypass architecture compliance | Actions containing "architecture", "constitution", "contract", "subsystem" | CRITICAL |
| 4 | Bypass audit systems | Actions containing "audit", "ledger", "chain_hash", "tamper" | CRITICAL |
| 5 | Alter validation logic | Actions containing "validation", "test", "verify", "check" | CRITICAL |
| 6 | Change security policies | Actions containing "security", "auth", "jwt", "secret", "sandbox" | CRITICAL |

**Enforcement**: `SelfModificationDetector` + `GovernanceGuard` check every action against these 6 patterns. Matching actions are **blocked unless** `explicitly_approved=True` is in the context. All detections create `CharterViolation` records with CRITICAL severity.

---

## 5. High-Risk Actions Requiring Approval

Ten categories require **explicit human approval** before execution:

| # | Action | Required Role | Description |
|---|--------|--------------|-------------|
| 1 | Governance modification | **admin** | Change governance rules, roles, policies |
| 2 | Security policy change | **admin** | Modify security settings, JWT secrets, auth |
| 3 | Architecture contract mutation | **architect** | Change subsystem contracts or interfaces |
| 4 | Plugin trust elevation | **architect** | Increase plugin trust level or capabilities |
| 5 | Destructive migration | **architect** | Run migrations that delete or alter data |
| 6 | Deletion operation | **approver** | Delete patches, tasks, rules, audit entries |
| 7 | Replay ledger reset | **admin** | Reset or truncate replay/task logs |
| 8 | Audit ledger maintenance | **admin** | Modify or maintain the audit ledger |
| 9 | Infrastructure escalation | **architect** | Change Docker/K8s infrastructure |
| 10 | External system execution | **approver** | Execute commands on external systems |

**Approval flow**:
1. Action detected as high-risk
2. `HumanApprovalGate` creates pending request
3. Request expires in 60 minutes if not resolved
4. Human with sufficient role explicitly approves or rejects
5. Only then does the action proceed
6. All approvals are auditable

---

## 6. Autonomous Execution Safety

All autonomous execution is constrained by:

| Bound | Implementation | Default |
|-------|---------------|---------|
| **Rate limited** | Per-agent-type request throttling | 10 req/min |
| **Resource bounded** | Per-agent: 2 CPU, 4GB RAM, 100 FDs | configurable |
| **Timeout bounded** | Agent timeout: 300s (5 min) | configurable |
| **Sandbox constrained** | seccomp-bpf (P1), command whitelist | P2: restricted |
| **Observable real-time** | WebSocket events + SSE streaming | always on |

---

## 7. Explainability Requirements

Every major autonomous action must preserve **6 lineage types**:

| Lineage Type | Captured By | Content |
|-------------|-------------|---------|
| **Reasoning trace** | ExplainabilityTracker | Why the action was taken, step-by-step reasoning |
| **Execution trace** | ExplainabilityTracker | What code paths were executed, with status |
| **Event lineage** | EventBus + ExplainabilityTracker | All events published/consumed |
| **Dependency lineage** | ExplainabilityTracker | What services/components were depended on |
| **Replay lineage** | TaskRecorder + ExplainabilityTracker | Seed, model version, snapshots for replay |
| **Rollback lineage** | ExplainabilityTracker | Rollback points and procedures |

**Completeness score**: 0.0 to 1.0. Traces with score < 1.0 generate warnings.

---

## 8. Fail-Safe Principle

> When uncertainty exceeds confidence: **degrade gracefully, request human review, avoid destructive action, preserve state, preserve evidence.**

**Confidence threshold**: 0.7 (configurable by admin)

| Scenario | Confidence | Destructive? | Outcome |
|----------|-----------|--------------|---------|
| Normal operation | >= 0.7 | No | Proceed |
| Degraded mode | < 0.7 | No | Proceed with human review request |
| Destructive blocked | < 0.7 | Yes | **BLOCKED**. State preserved. Human review required. |

All fail-safe activations are logged in `failsafe_incidents` table.

---

## 9. Enforcement Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    HUMAN OPERATOR                         │
│  (override, intervene, approve, rollback, inspect)       │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTP API
┌──────────────────────▼───────────────────────────────────┐
│              CHARTER ROUTER (/api/v1/charter)             │
│  • intervene  • override  • rollback  • approvals         │
│  • explainability  • failsafe  • integrity  • violations  │
└──────────────────────┬───────────────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         │             │             │
┌────────▼────┐ ┌──────▼──────┐ ┌───▼───────────┐
│Governance   │ │Human        │ │Self-          │
│Guard        │ │Approval     │ │Modification   │
│             │ │Gate         │ │Detector       │
│• RBAC check │ │• Pending    │ │• Hash monitor │
│• High-risk  │ │  requests   │ │• Pattern match│
│  classify   │ │• Role check │ │• Integrity    │
│• Confidence │ │• Audit trail│ │  registry     │
│  threshold  │ │• Timeout    │ │               │
└────────┬────┘ └──────┬──────┘ └───┬───────────┘
         │             │            │
         └─────────────┼────────────┘
                       │
              ┌────────▼──────┐
              │Explainability │
              │Tracker        │
              │• 6 lineage    │
              │  types        │
              │• Completeness │
              │  score        │
              └────────┬──────┘
                       │
              ┌────────▼──────┐
              │FailSafe       │
              │Controller     │
              │• Confidence   │
              │  evaluation   │
              │• Destructive  │
              │  block        │
              │• State        │
              │  preservation │
              └───────────────┘
```

---

## 10. API Reference

### Charter Information

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/charter/principles` | Six autonomy principles |
| GET | `/api/v1/charter/human-controls` | Eight mandatory controls |
| GET | `/api/v1/charter/high-risk-actions` | Ten actions requiring approval |
| GET | `/api/v1/charter/self-modification-rules` | Six prohibitions |
| GET | `/api/v1/charter/summary` | Complete charter status |

### Human Control

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/charter/intervene` | Manual intervention |
| POST | `/api/v1/charter/override` | Manual override (with justification) |
| POST | `/api/v1/charter/rollback` | Manual rollback |
| POST | `/api/v1/charter/check-action` | Dry-run action permission check |

### Approvals

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/charter/approvals/request` | Request approval |
| POST | `/api/v1/charter/approvals/{id}/approve` | Approve (human) |
| POST | `/api/v1/charter/approvals/{id}/reject` | Reject |
| GET | `/api/v1/charter/approvals/pending` | List pending |

### Explainability

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/charter/explainability/traces/{id}` | Get trace |
| GET | `/api/v1/charter/explainability/report` | Completeness report |

### Fail-Safe

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/charter/failsafe/report` | Incident report |
| POST | `/api/v1/charter/failsafe/evaluate` | Evaluate action |

### Integrity & Violations

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/charter/integrity/report` | Modification detections |
| POST | `/api/v1/charter/integrity/check` | Check file integrity |
| GET | `/api/v1/charter/violations` | Charter violations |

---

## 11. Implementation

### Files Created

| Component | File | Lines |
|-----------|------|-------|
| **Charter Model** | `workspace/aura-sdk/src/aura_sdk/governance/charter.py` | ~200 |
| **GovernanceGuard** | `workspace/aura-sdk/src/aura_sdk/governance/guard.py` | ~200 |
| **HumanApprovalGate** | `workspace/aura-sdk/src/aura_sdk/governance/approval_gate.py` | ~180 |
| **SelfModificationDetector** | `workspace/aura-sdk/src/aura_sdk/governance/modification_detector.py` | ~150 |
| **ExplainabilityTracker** | `workspace/aura-sdk/src/aura_sdk/governance/explainability.py` | ~200 |
| **FailSafeController** | `workspace/aura-sdk/src/aura_sdk/governance/failsafe.py` | ~150 |
| **Charter Router** | `services/core/src/core/routers/charter.py` | ~300 |
| **Charter Schema** | `knowledge/schema/015_charter_governance.sql` | ~150 |
| **This Document** | `AURA_Human_Authority_Charter.md` | ~350 |

### Pre-Seeded Data

| Table | Records | Content |
|-------|---------|---------|
| `charter_config` | 1 | Charter version 1.0.0, threshold 0.7 |
| `engineering_decisions` | 3 | Human authority, confidence fail-safe, 6 prohibitions |
| `known_risks` | 4 | Autonomous bypass, over-confidence, integrity violation, config tampering |
| 6 enforcement tables | 0 (populated at runtime) | violations, approvals, traces, incidents, detections, integrity |

### Runtime Enforcement Flow

```
Action Requested
      │
      ▼
┌─────────────┐
│GovernanceGuard│
│  check_action │
└──────┬──────┘
       │
   ┌───┴────┬──────────┬──────────────┐
   │        │          │              │
RBAC?   High-risk?  Self-mod?   Confidence?
   │        │          │              │
   ▼        ▼          ▼              ▼
DENIED  APPROVAL    VIOLATION   FAIL-SAFE
        GATE                         │
       (human)                   ┌──┴──┐
                                  │     │
                              Destructive? Other?
                                  │     │
                                  ▼     ▼
                               BLOCK  DEGRADE
                               +      + human
                               state  review
                               save
```

---

## Constitution Compliance

This Charter is an **extension of Article IV (Governance)** and **Article VI (Human Maintainability)** of the AURA Immutable Architecture Constitution:

- **Article I**: Charter applies to all 8 subsystems
- **Article II**: All charter APIs use Pydantic models with JSON contracts
- **Article III**: Deterministic enforcement — same action → same outcome
- **Article IV**: RBAC + 3-dim approval + audit — all enforced by GovernanceGuard
- **Article V**: No over-engineering — pattern matching, not formal verification
- **Article VI**: Human maintainability — all reasoning preserved, all actions explainable
- **Article VII**: Charter enforcement is P0 (foundation), not deferred

---

*Human governance is final. The platform exists to augment engineering capability, not replace engineering authority.*

*End of Charter*
