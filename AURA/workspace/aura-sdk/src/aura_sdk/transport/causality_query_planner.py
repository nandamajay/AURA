"""Causality query planner for deterministic engineering investigation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


_INTENT_KEYWORDS: dict[str, list[str]] = {
    "runtime_failure": ["runtime failure", "what caused", "failure", "crash", "incident"],
    "patch_regression": ["which patch", "regression", "introduced", "blast radius", "bisect"],
    "migration_blocker": ["migration", "fail-closed", "upstream abstraction", "portability", "blocker"],
    "lifecycle_drift": ["lifecycle", "sequence drift", "drifted", "dpcm"],
    "topology_invalid": ["topology", "invalid path", "route", "fe", "be"],
    "dsp_sync": ["dsp", "mailbox", "synchronization", "sync failed"],
    "runtime_topology_contradiction": ["contradicts topology", "topology expectations", "mismatch"],
    "confidence_reduction": ["confidence reduced", "why confidence", "confidence"],
    "downstream_upstream_change": ["downstream", "upstream", "changed between"],
    "replay_lineage": ["replay", "lineage", "deterministic", "history"],
}


_INTENT_DOMAIN_MAP: dict[str, list[str]] = {
    "runtime_failure": ["runtime", "topology", "patch", "replay"],
    "patch_regression": ["patch", "runtime", "replay"],
    "migration_blocker": ["migration", "topology", "runtime", "replay"],
    "lifecycle_drift": ["runtime", "topology", "replay"],
    "topology_invalid": ["topology", "runtime", "migration", "replay"],
    "dsp_sync": ["runtime", "topology", "replay"],
    "runtime_topology_contradiction": ["runtime", "topology", "semantic", "replay"],
    "confidence_reduction": ["runtime", "migration", "patch", "replay"],
    "downstream_upstream_change": ["migration", "semantic", "structural", "topology", "replay"],
    "replay_lineage": ["replay", "runtime", "migration", "patch"],
}


_DOMAIN_RESOLVER_ORDER = {
    "runtime": "runtime_question_resolver",
    "migration": "migration_question_resolver",
    "topology": "topology_question_resolver",
    "patch": "patch_reasoning_resolver",
    "replay": "replay_evidence_resolver",
    "semantic": "replay_evidence_resolver",
    "structural": "replay_evidence_resolver",
}


@dataclass(frozen=True)
class CausalityQueryPlanResult:
    causality_query_plan: dict[str, Any]
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
            "ok",
            "pass",
            "success",
            "supported",
        }
    return False


def _infer_intents(question: str) -> list[str]:
    lowered = str(question).strip().lower()
    intents: list[str] = []
    for intent, keywords in sorted(_INTENT_KEYWORDS.items()):
        if any(keyword in lowered for keyword in keywords):
            intents.append(intent)
    if not intents:
        intents = ["runtime_failure"]
    return sorted(set(intents))


def plan_causality_query(
    *,
    question: str,
    governance_state: Mapping[str, Any],
    available_domains: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> CausalityQueryPlanResult:
    governance = _as_dict(governance_state)
    domains = _as_dict(available_domains)

    intents = _infer_intents(str(question))

    planned_domains: list[str] = []
    for intent in intents:
        planned_domains.extend(_as_list(_INTENT_DOMAIN_MAP.get(intent, [])))
    if not planned_domains:
        planned_domains = ["runtime", "replay"]
    planned_domains = sorted(set([str(item) for item in planned_domains if str(item).strip()]))

    domain_availability = {
        str(name): bool(_as_dict(payload))
        for name, payload in sorted(domains.items())
    }

    missing_domains = [
        domain
        for domain in planned_domains
        if not bool(domain_availability.get(domain, False))
    ]

    resolver_order = [
        str(_DOMAIN_RESOLVER_ORDER.get(domain, "replay_evidence_resolver"))
        for domain in planned_domains
    ]

    governance_clean = bool(governance.get("fail_closed_posture", True)) and not any(
        _is_true(governance.get(flag, False))
        for flag in (
            "autonomous_patching_allowed",
            "autonomous_topology_rewrite_allowed",
            "autonomous_runtime_mutation_allowed",
            "autonomous_upstream_generation_allowed",
        )
    )

    classification = "PASS"
    if not governance_clean:
        classification = "FAIL_CLOSED"
    elif missing_domains:
        classification = "FAIL_CLOSED"

    payload = {
        "schema_version": "1.0",
        "report_name": "causality_query_plan",
        "question": str(question).strip(),
        "classification": classification,
        "intents": intents,
        "planned_domains": planned_domains,
        "resolver_order": resolver_order,
        "domain_availability": domain_availability,
        "missing_domains": missing_domains,
        "governance_state": dict(governance),
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return CausalityQueryPlanResult(
        causality_query_plan=payload,
        deterministic_fingerprint=fingerprint,
    )
