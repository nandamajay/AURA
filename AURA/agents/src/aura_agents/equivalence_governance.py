"""Governed equivalence assertions for Track-B mapping."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from aura_agents.stage_engine import canonical_json_sha256


APPROVAL_STATES = {"pending", "approved", "rejected"}
MANDATORY_SIGNALS_BY_COMPONENT_TYPE = {
    "function": ("path_family", "compatible_family", "registration_role"),
}
DEFAULT_APPROVAL_TIMESTAMP = "input_timestamp_not_provided"


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float_or_zero(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        number = float(value)
    except Exception:
        return 0.0
    return max(0.0, min(1.0, number))


def _int_or_zero(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except Exception:
        return 0
    return max(0, number)


def _assertion_identity_payload(proposal: "EquivalenceAssertionProposal") -> dict[str, Any]:
    return {
        "assertion_type": proposal.assertion_type,
        "match_type": proposal.match_type,
        "downstream_component": proposal.downstream_component,
        "upstream_component": proposal.upstream_component,
        "evidence": proposal.evidence,
    }


def _evidence_signal_scores(evidence: list[dict[str, Any]]) -> dict[str, float]:
    grouped: dict[str, list[float]] = {}
    for entry in evidence:
        signal_id = _text(_safe_dict(entry).get("signal_id"))
        if not signal_id:
            continue
        grouped.setdefault(signal_id, []).append(_float_or_zero(_safe_dict(entry).get("score")))
    return {signal_id: sum(scores) / len(scores) for signal_id, scores in sorted(grouped.items()) if scores}


def _compute_confidence(
    *,
    downstream_component: dict[str, Any],
    evidence: list[dict[str, Any]],
    signal_weights: dict[str, float],
) -> tuple[dict[str, Any], list[str]]:
    component_type = _text(downstream_component.get("component_type")).lower()
    mandatory = MANDATORY_SIGNALS_BY_COMPONENT_TYPE.get(component_type, ())
    signal_scores = _evidence_signal_scores(evidence)
    fail_closed_reasons: list[str] = []

    for signal_id in mandatory:
        if signal_id not in signal_scores:
            fail_closed_reasons.append(f"mandatory_signal_missing:{signal_id}")

    if fail_closed_reasons:
        return {
            "value": 0.0,
            "method": "weighted_mean_with_mandatory_signal_cap",
            "signals": signal_scores,
            "mandatory_signals": list(mandatory),
        }, fail_closed_reasons

    weighted_sum = 0.0
    total_weight = 0.0
    for signal_id, score in sorted(signal_scores.items()):
        weight = signal_weights.get(signal_id, 1.0)
        if isinstance(weight, bool):
            weight = 1.0
        try:
            weight = float(weight)
        except Exception:
            weight = 1.0
        if weight <= 0.0:
            continue
        weighted_sum += score * weight
        total_weight += weight

    value = weighted_sum / total_weight if total_weight else 0.0
    if mandatory:
        value = min(value, min(signal_scores[signal_id] for signal_id in mandatory))
    return {
        "value": round(value, 4),
        "method": "weighted_mean_with_mandatory_signal_cap",
        "signals": signal_scores,
        "mandatory_signals": list(mandatory),
    }, []


@dataclass
class EquivalenceAssertionProposal:
    assertion_type: str
    match_type: str
    downstream_component: dict[str, Any]
    upstream_component: dict[str, Any]
    evidence: list[dict[str, Any]]
    governance: dict[str, Any] = field(default_factory=lambda: {"approval_state": "pending"})
    fail_closed_reasons: list[str] = field(default_factory=list)
    signal_weights: dict[str, float] = field(default_factory=dict)
    confidence: dict[str, Any] = field(init=False)
    assertion_id: str = field(init=False)

    def __post_init__(self) -> None:
        self.assertion_type = _text(self.assertion_type)
        self.match_type = _text(self.match_type)
        self.downstream_component = _safe_dict(self.downstream_component)
        self.upstream_component = _safe_dict(self.upstream_component)
        self.evidence = [_safe_dict(entry) for entry in _safe_list(self.evidence)]
        self.governance = {"approval_state": "pending", **_safe_dict(self.governance)}
        self.signal_weights = {
            _text(key): _float_or_zero(value) for key, value in _safe_dict(self.signal_weights).items() if _text(key)
        }
        self.confidence, computed_reasons = _compute_confidence(
            downstream_component=self.downstream_component,
            evidence=self.evidence,
            signal_weights=self.signal_weights,
        )
        reasons = [_text(reason) for reason in _safe_list(self.fail_closed_reasons) if _text(reason)]
        self.fail_closed_reasons = sorted(set(reasons + computed_reasons))
        self.assertion_id = canonical_json_sha256(_assertion_identity_payload(self))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EquivalenceAssertionProposal":
        item = _safe_dict(payload)
        return cls(
            assertion_type=item.get("assertion_type"),
            match_type=item.get("match_type"),
            downstream_component=_safe_dict(item.get("downstream_component")),
            upstream_component=_safe_dict(item.get("upstream_component")),
            evidence=[_safe_dict(entry) for entry in _safe_list(item.get("evidence"))],
            governance=_safe_dict(item.get("governance")),
            fail_closed_reasons=[_text(reason) for reason in _safe_list(item.get("fail_closed_reasons"))],
            signal_weights=_safe_dict(item.get("signal_weights")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "assertion_id": self.assertion_id,
            "assertion_type": self.assertion_type,
            "match_type": self.match_type,
            "downstream_component": self.downstream_component,
            "upstream_component": self.upstream_component,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "governance": self.governance,
            "fail_closed_reasons": self.fail_closed_reasons,
        }


def _coerce_proposal(proposal: EquivalenceAssertionProposal | dict[str, Any]) -> EquivalenceAssertionProposal:
    if isinstance(proposal, EquivalenceAssertionProposal):
        return proposal
    return EquivalenceAssertionProposal.from_dict(_safe_dict(proposal))


def validate_assertion_proposal(proposal: EquivalenceAssertionProposal | dict[str, Any]) -> tuple[bool, list[str]]:
    item = _coerce_proposal(proposal)
    reasons: list[str] = []
    if not item.assertion_type:
        reasons.append("missing_assertion_type")
    if not item.match_type:
        reasons.append("missing_match_type")
    if not item.downstream_component:
        reasons.append("missing_downstream_component")
    if not item.upstream_component:
        reasons.append("missing_upstream_component")
    if not item.evidence:
        reasons.append("no_evidence")

    for component_name, component in (
        ("downstream_component", item.downstream_component),
        ("upstream_component", item.upstream_component),
    ):
        if not _text(component.get("component_type")):
            reasons.append(f"{component_name}.missing_component_type")
        if not _text(component.get("symbol")) and not _text(component.get("component_name")):
            reasons.append(f"{component_name}.missing_symbol")
        if not _text(component.get("source_path")):
            reasons.append(f"{component_name}.missing_source_path")

    for index, entry in enumerate(item.evidence):
        if not _text(entry.get("source_artifact_sha256")):
            reasons.append(f"evidence[{index}].missing_source_artifact_sha256")
        if not _text(entry.get("extractor_id")):
            reasons.append(f"evidence[{index}].missing_extractor_id")
        if not _text(entry.get("signal_id")):
            reasons.append(f"evidence[{index}].missing_signal_id")

    approval_state = _text(item.governance.get("approval_state"))
    if approval_state not in APPROVAL_STATES:
        reasons.append("governance.invalid_approval_state")

    reasons.extend(item.fail_closed_reasons)
    return not reasons, sorted(set(reasons))


class EquivalenceGovernanceGate:
    def approve(
        self,
        proposal: EquivalenceAssertionProposal | dict[str, Any],
        approver_id: str,
        rationale: str,
        timestamp: str | None = None,
    ) -> EquivalenceAssertionProposal:
        item = _coerce_proposal(proposal)
        valid, reasons = validate_assertion_proposal(item)
        if not valid:
            item.fail_closed_reasons = sorted(set(item.fail_closed_reasons + reasons))
            return item
        approval_timestamp = _text(timestamp) or _text(item.governance.get("approval_timestamp")) or DEFAULT_APPROVAL_TIMESTAMP
        governance = dict(item.governance)
        governance.update(
            {
                "approval_state": "approved",
                "approver_id": _text(approver_id),
                "rationale": _text(rationale),
                "approval_timestamp": approval_timestamp,
            }
        )
        governance["audit_ledger_sha256"] = canonical_json_sha256(
            {
                "assertion_id": item.assertion_id,
                "approver_id": governance["approver_id"],
                "rationale": governance["rationale"],
                "timestamp": approval_timestamp,
            }
        )
        return EquivalenceAssertionProposal(
            assertion_type=item.assertion_type,
            match_type=item.match_type,
            downstream_component=item.downstream_component,
            upstream_component=item.upstream_component,
            evidence=item.evidence,
            governance=governance,
            fail_closed_reasons=item.fail_closed_reasons,
            signal_weights=item.signal_weights,
        )

    def reject(
        self,
        proposal: EquivalenceAssertionProposal | dict[str, Any],
        approver_id: str,
        reason: str,
        timestamp: str | None = None,
    ) -> EquivalenceAssertionProposal:
        item = _coerce_proposal(proposal)
        rejection_timestamp = _text(timestamp) or _text(item.governance.get("rejection_timestamp")) or DEFAULT_APPROVAL_TIMESTAMP
        governance = dict(item.governance)
        governance.update(
            {
                "approval_state": "rejected",
                "approver_id": _text(approver_id),
                "rejection_reason": _text(reason),
                "rejection_timestamp": rejection_timestamp,
            }
        )
        governance["audit_ledger_sha256"] = canonical_json_sha256(
            {
                "assertion_id": item.assertion_id,
                "approver_id": governance["approver_id"],
                "reason": governance["rejection_reason"],
                "timestamp": rejection_timestamp,
            }
        )
        return EquivalenceAssertionProposal(
            assertion_type=item.assertion_type,
            match_type=item.match_type,
            downstream_component=item.downstream_component,
            upstream_component=item.upstream_component,
            evidence=item.evidence,
            governance=governance,
            fail_closed_reasons=item.fail_closed_reasons,
            signal_weights=item.signal_weights,
        )


def assertion_to_candidate_mapping(approved_assertion: EquivalenceAssertionProposal | dict[str, Any]) -> dict[str, Any] | None:
    assertion = _coerce_proposal(approved_assertion)
    valid, reasons = validate_assertion_proposal(assertion)
    if not valid or assertion.governance.get("approval_state") != "approved":
        return None

    governance = assertion.governance
    provenance_entries: list[dict[str, Any]] = []
    evidence_refs = [
        {
            "signal_id": _text(entry.get("signal_id")),
            "extractor_id": _text(entry.get("extractor_id")),
            "source_artifact_sha256": _text(entry.get("source_artifact_sha256")),
            "source_path": _text(entry.get("source_path")),
        }
        for entry in assertion.evidence
    ]
    for index, entry in enumerate(assertion.evidence):
        path = _text(entry.get("path")) or _text(entry.get("source_path"))
        line_start = _int_or_zero(entry.get("line_start"))
        line_end = _int_or_zero(entry.get("line_end"))
        if line_end < line_start:
            line_end = line_start
        provenance = {
            "evidence_type": _text(entry.get("evidence_type")) or f"governed_equivalence:{_text(entry.get('signal_id'))}",
            "corpus_role": _text(entry.get("corpus_role")).lower(),
            "corpus_id": _text(entry.get("corpus_id")),
            "remote": _text(entry.get("remote")),
            "branch": _text(entry.get("branch")),
            "commit_sha": _text(entry.get("commit_sha")).lower(),
            "path": path,
            "line_start": line_start,
            "line_end": line_end,
            "snippet_sha256": _text(entry.get("snippet_sha256")),
            "source_artifact_name": _text(entry.get("source_artifact_name")) or "GOVERNED_EQUIVALENCE_ASSERTION",
            "source_artifact_sha256": _text(entry.get("source_artifact_sha256")).lower(),
            "extraction_rule_id": _text(entry.get("extraction_rule_id")) or _text(entry.get("extractor_id")),
        }
        if not provenance["snippet_sha256"]:
            provenance["snippet_sha256"] = canonical_json_sha256(
                {
                    "assertion_id": assertion.assertion_id,
                    "evidence_index": index,
                    "entry": entry,
                }
            )
        provenance["evidence_id"] = _text(entry.get("evidence_id")) or canonical_json_sha256(provenance)
        provenance_entries.append(provenance)
    candidate_identity = {
        "assertion_id": assertion.assertion_id,
        "match_type": assertion.match_type,
        "downstream_component": assertion.downstream_component,
        "upstream_component": assertion.upstream_component,
        "confidence": assertion.confidence.get("value", 0.0),
        "audit_ledger_sha256": governance.get("audit_ledger_sha256"),
    }
    return {
        "candidate_id": canonical_json_sha256(candidate_identity),
        "mapping_state": "CANDIDATE",
        "match_type": assertion.match_type,
        "assertion_type": assertion.assertion_type,
        "assertion_id": assertion.assertion_id,
        "score": float(assertion.confidence.get("value") or 0.0),
        "confidence": float(assertion.confidence.get("value") or 0.0),
        "score_components": {
            "formula": assertion.confidence.get("method"),
            "evidence_signals": assertion.confidence.get("signals", {}),
            "mandatory_signals": assertion.confidence.get("mandatory_signals", []),
        },
        "downstream_component": assertion.downstream_component,
        "upstream_component": assertion.upstream_component,
        "evidence": provenance_entries,
        "evidence_refs": evidence_refs,
        "governance": {
            "approval_state": governance.get("approval_state"),
            "approver_id": governance.get("approver_id"),
            "approval_timestamp": governance.get("approval_timestamp"),
            "audit_ledger_sha256": governance.get("audit_ledger_sha256"),
        },
    }

DEPENDENCY_RESOLUTION_TYPES = {
    "REMOVAL_REQUIRED",
    "UPSTREAM_REPLACEMENT_EXISTS",
    "UPSTREAM_EQUIVALENT_EXISTS",
    "UNUSED_IN_UPSTREAM_PATH",
    "UPSTREAMING_REQUIRED",
}
DEPENDENCY_COMPLEXITIES = {"trivial", "moderate", "significant"}


def _dependency_assertion_identity_payload(proposal: "DependencyResolutionAssertion") -> dict[str, Any]:
    return {
        "assertion_type": proposal.assertion_type,
        "driver": proposal.driver,
        "dependency_header": proposal.dependency_header,
        "resolution_type": proposal.resolution_type,
        "upstream_equivalent": proposal.upstream_equivalent,
        "conversion_strategy": proposal.conversion_strategy,
        "complexity": proposal.complexity,
        "evidence": proposal.evidence,
    }


@dataclass
class DependencyResolutionAssertion:
    assertion_type: str
    driver: str
    dependency_header: str
    resolution_type: str
    upstream_equivalent: str | None
    conversion_strategy: str
    complexity: str
    evidence: list[dict[str, Any]]
    governance: dict[str, Any] = field(default_factory=lambda: {"approval_state": "pending"})
    fail_closed_reasons: list[str] = field(default_factory=list)
    assertion_id: str = field(init=False)

    def __post_init__(self) -> None:
        self.assertion_type = _text(self.assertion_type) or "governed_human_assertion"
        self.driver = _text(self.driver)
        self.dependency_header = _text(self.dependency_header)
        self.resolution_type = _text(self.resolution_type).upper()
        upstream_equivalent = _text(self.upstream_equivalent)
        self.upstream_equivalent = upstream_equivalent or None
        self.conversion_strategy = _text(self.conversion_strategy)
        self.complexity = _text(self.complexity).lower()
        self.evidence = [_safe_dict(entry) for entry in _safe_list(self.evidence)]
        self.governance = {"approval_state": "pending", **_safe_dict(self.governance)}
        self.fail_closed_reasons = sorted(
            {_text(reason) for reason in _safe_list(self.fail_closed_reasons) if _text(reason)}
        )
        self.assertion_id = canonical_json_sha256(_dependency_assertion_identity_payload(self))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DependencyResolutionAssertion":
        item = _safe_dict(payload)
        return cls(
            assertion_type=item.get("assertion_type") or "governed_human_assertion",
            driver=item.get("driver"),
            dependency_header=item.get("dependency_header"),
            resolution_type=item.get("resolution_type"),
            upstream_equivalent=item.get("upstream_equivalent"),
            conversion_strategy=item.get("conversion_strategy"),
            complexity=item.get("complexity"),
            evidence=[_safe_dict(entry) for entry in _safe_list(item.get("evidence"))],
            governance=_safe_dict(item.get("governance")),
            fail_closed_reasons=[_text(reason) for reason in _safe_list(item.get("fail_closed_reasons"))],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "assertion_id": self.assertion_id,
            "assertion_type": self.assertion_type,
            "driver": self.driver,
            "dependency_header": self.dependency_header,
            "resolution_type": self.resolution_type,
            "upstream_equivalent": self.upstream_equivalent,
            "conversion_strategy": self.conversion_strategy,
            "complexity": self.complexity,
            "evidence": self.evidence,
            "governance": self.governance,
            "fail_closed_reasons": self.fail_closed_reasons,
        }


def _coerce_dependency_assertion(
    proposal: DependencyResolutionAssertion | dict[str, Any],
) -> DependencyResolutionAssertion:
    if isinstance(proposal, DependencyResolutionAssertion):
        return proposal
    return DependencyResolutionAssertion.from_dict(_safe_dict(proposal))


def validate_dependency_resolution_assertion(
    proposal: DependencyResolutionAssertion | dict[str, Any],
) -> tuple[bool, list[str]]:
    item = _coerce_dependency_assertion(proposal)
    reasons: list[str] = []
    if item.assertion_type != "governed_human_assertion":
        reasons.append("invalid_assertion_type")
    if not item.driver:
        reasons.append("missing_driver")
    if not item.dependency_header:
        reasons.append("missing_dependency_header")
    if item.resolution_type not in DEPENDENCY_RESOLUTION_TYPES:
        reasons.append("invalid_resolution_type")
    if item.resolution_type == "UPSTREAM_REPLACEMENT_EXISTS" and not item.upstream_equivalent:
        reasons.append("missing_upstream_equivalent")
    if not item.conversion_strategy:
        reasons.append("missing_conversion_strategy")
    if item.complexity not in DEPENDENCY_COMPLEXITIES:
        reasons.append("invalid_complexity")
    if not item.evidence:
        reasons.append("no_evidence")

    for index, entry in enumerate(item.evidence):
        if not _text(entry.get("source_artifact_sha256")):
            reasons.append(f"evidence[{index}].missing_source_artifact_sha256")
        if not _text(entry.get("extractor_id")):
            reasons.append(f"evidence[{index}].missing_extractor_id")
        if not (_text(entry.get("source_path")) or _text(entry.get("path"))):
            reasons.append(f"evidence[{index}].missing_source_path")

    approval_state = _text(item.governance.get("approval_state"))
    if approval_state not in APPROVAL_STATES:
        reasons.append("governance.invalid_approval_state")

    reasons.extend(item.fail_closed_reasons)
    return not reasons, sorted(set(reasons))


class DependencyResolutionGovernanceGate:
    def approve(
        self,
        proposal: DependencyResolutionAssertion | dict[str, Any],
        approver_id: str,
        rationale: str,
        timestamp: str | None = None,
    ) -> DependencyResolutionAssertion:
        item = _coerce_dependency_assertion(proposal)
        valid, reasons = validate_dependency_resolution_assertion(item)
        if not valid:
            item.fail_closed_reasons = sorted(set(item.fail_closed_reasons + reasons))
            return item
        approval_timestamp = _text(timestamp) or _text(item.governance.get("approval_timestamp")) or DEFAULT_APPROVAL_TIMESTAMP
        governance = dict(item.governance)
        governance.update(
            {
                "approval_state": "approved",
                "approver_id": _text(approver_id),
                "rationale": _text(rationale),
                "approval_timestamp": approval_timestamp,
            }
        )
        governance["audit_ledger_sha256"] = canonical_json_sha256(
            {
                "assertion_id": item.assertion_id,
                "approver_id": governance["approver_id"],
                "rationale": governance["rationale"],
                "timestamp": approval_timestamp,
            }
        )
        return DependencyResolutionAssertion(
            assertion_type=item.assertion_type,
            driver=item.driver,
            dependency_header=item.dependency_header,
            resolution_type=item.resolution_type,
            upstream_equivalent=item.upstream_equivalent,
            conversion_strategy=item.conversion_strategy,
            complexity=item.complexity,
            evidence=item.evidence,
            governance=governance,
            fail_closed_reasons=item.fail_closed_reasons,
        )

    def reject(
        self,
        proposal: DependencyResolutionAssertion | dict[str, Any],
        approver_id: str,
        reason: str,
        timestamp: str | None = None,
    ) -> DependencyResolutionAssertion:
        item = _coerce_dependency_assertion(proposal)
        rejection_timestamp = _text(timestamp) or _text(item.governance.get("rejection_timestamp")) or DEFAULT_APPROVAL_TIMESTAMP
        governance = dict(item.governance)
        governance.update(
            {
                "approval_state": "rejected",
                "approver_id": _text(approver_id),
                "rejection_reason": _text(reason),
                "rejection_timestamp": rejection_timestamp,
            }
        )
        governance["audit_ledger_sha256"] = canonical_json_sha256(
            {
                "assertion_id": item.assertion_id,
                "approver_id": governance["approver_id"],
                "reason": governance["rejection_reason"],
                "timestamp": rejection_timestamp,
            }
        )
        return DependencyResolutionAssertion(
            assertion_type=item.assertion_type,
            driver=item.driver,
            dependency_header=item.dependency_header,
            resolution_type=item.resolution_type,
            upstream_equivalent=item.upstream_equivalent,
            conversion_strategy=item.conversion_strategy,
            complexity=item.complexity,
            evidence=item.evidence,
            governance=governance,
            fail_closed_reasons=item.fail_closed_reasons,
        )


def dependency_assertion_to_resolution(
    approved_assertion: DependencyResolutionAssertion | dict[str, Any],
) -> dict[str, Any] | None:
    assertion = _coerce_dependency_assertion(approved_assertion)
    valid, _ = validate_dependency_resolution_assertion(assertion)
    if not valid or assertion.governance.get("approval_state") != "approved":
        return None

    return {
        "assertion_id": assertion.assertion_id,
        "assertion_type": assertion.assertion_type,
        "driver": assertion.driver,
        "dependency_header": assertion.dependency_header,
        "resolution_type": assertion.resolution_type,
        "upstream_equivalent": assertion.upstream_equivalent,
        "conversion_strategy": assertion.conversion_strategy,
        "complexity": assertion.complexity,
        "evidence_refs": [
            {
                "extractor_id": _text(entry.get("extractor_id")),
                "source_artifact_sha256": _text(entry.get("source_artifact_sha256")),
                "source_path": _text(entry.get("source_path")) or _text(entry.get("path")),
                "signal_id": _text(entry.get("signal_id")),
            }
            for entry in assertion.evidence
        ],
        "governance": {
            "approval_state": assertion.governance.get("approval_state"),
            "approver_id": assertion.governance.get("approver_id"),
            "approval_timestamp": assertion.governance.get("approval_timestamp"),
            "audit_ledger_sha256": assertion.governance.get("audit_ledger_sha256"),
        },
    }


def _artifact_evidence_entry(
    *,
    artifact_sha: str,
    dependency_header: str,
    signal_id: str,
    source: dict[str, Any],
    fallback_path: str,
    score: float,
) -> dict[str, Any]:
    source_path = (
        _text(source.get("file"))
        or _text(source.get("upstream_file"))
        or _text(source.get("path"))
        or fallback_path
        or dependency_header
    )
    line_start = _int_or_zero(source.get("line")) or _int_or_zero(source.get("line_start"))
    line_end = _int_or_zero(source.get("line_end")) or line_start
    source_record = {
        "dependency_header": dependency_header,
        "signal_id": signal_id,
        "source": source,
    }
    return {
        "signal_id": signal_id,
        "score": score,
        "extractor_id": "dependency_resolution_map.loader.v1",
        "source_artifact_sha256": artifact_sha,
        "source_artifact_name": "DEPENDENCY_RESOLUTION_MAP",
        "source_path": source_path,
        "path": source_path,
        "line_start": line_start,
        "line_end": line_end,
        "snippet_sha256": canonical_json_sha256(source_record),
    }


def load_dependency_resolutions_from_artifact(path: Path) -> list[DependencyResolutionAssertion]:
    artifact_path = Path(path)
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact_sha = canonical_json_sha256(payload)
    driver = _text(payload.get("driver"))
    proposals: list[DependencyResolutionAssertion] = []
    for raw_dependency in _safe_list(payload.get("dependencies")):
        dependency = _safe_dict(raw_dependency)
        dependency_header = _text(dependency.get("downstream_header"))
        if not dependency_header:
            continue
        confidence = _float_or_zero(dependency.get("evidence_confidence")) or 1.0
        fallback_path = _text(dependency.get("actual_header_path")) or dependency_header
        evidence: list[dict[str, Any]] = []
        for entry in _safe_list(dependency.get("usage_evidence")):
            evidence.append(
                _artifact_evidence_entry(
                    artifact_sha=artifact_sha,
                    dependency_header=dependency_header,
                    signal_id="usage_evidence",
                    source=_safe_dict(entry),
                    fallback_path=fallback_path,
                    score=confidence,
                )
            )
        for entry in _safe_list(dependency.get("upstream_equivalent_evidence")):
            evidence.append(
                _artifact_evidence_entry(
                    artifact_sha=artifact_sha,
                    dependency_header=dependency_header,
                    signal_id="upstream_equivalent_evidence",
                    source=_safe_dict(entry),
                    fallback_path=fallback_path,
                    score=confidence,
                )
            )
        proposals.append(
            DependencyResolutionAssertion(
                assertion_type="governed_human_assertion",
                driver=driver,
                dependency_header=dependency_header,
                resolution_type=dependency.get("resolution_type"),
                upstream_equivalent=dependency.get("upstream_equivalent"),
                conversion_strategy=dependency.get("conversion_strategy"),
                complexity=dependency.get("complexity"),
                evidence=evidence,
            )
        )
    return proposals

