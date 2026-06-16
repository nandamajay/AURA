"""Track-B M10 intelligence contracts (deterministic, evidence-backed, read-only)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from aura_sdk.logging.logger import get_logger
from core.contracts.track_b_artifact_contracts import (
    TrackBArtifactRecord,
    TrackBLearningRecord,
    collect_learning_records,
    collect_track_b_audits,
    collect_track_b_releases,
    readiness_history,
    summarize_conflicts,
    summarize_dependency_coverage,
    summarize_readiness,
    track_b_overview,
)
from core.contracts.transport_artifact_contracts import ContractValidation

logger = get_logger("core.track_b_intelligence")


def _stable_generated_at_from_strings(values: list[str]) -> str:
    parsed: list[datetime] = []
    for value in values:
        if not value:
            continue
        parsed_dt = _parse_iso(value)
        if parsed_dt:
            parsed.append(parsed_dt.astimezone(timezone.utc))
    if not parsed:
        return ""
    return max(parsed).isoformat()


def _stable_generated_at_from_records(records: list[TrackBArtifactRecord]) -> str:
    return _stable_generated_at_from_strings([item.metadata.modified_at for item in records if item.metadata.modified_at])


def _stable_generated_at_from_learning(entries: list[Any]) -> str:
    return _stable_generated_at_from_strings([getattr(item, "generated_at", "") for item in entries])


def _normalize_summary_generated_at(summary: dict[str, Any], generated_at: str) -> dict[str, Any]:
    if isinstance(summary, dict):
        summary = dict(summary)
        summary["generated_at"] = generated_at
    return summary


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _sort_key(value: Any) -> tuple:
    return (_normalize_text(value),)


def _group_by_run(records: list[TrackBArtifactRecord]) -> dict[str, list[TrackBArtifactRecord]]:
    grouped: dict[str, list[TrackBArtifactRecord]] = {}
    for record in records:
        key = f"{record.metadata.source_root}::{record.metadata.run_id}"
        grouped.setdefault(key, []).append(record)
    for key in grouped:
        grouped[key].sort(key=lambda item: (item.metadata.artifact_file, item.metadata.modified_at, item.metadata.artifact_id))
    return grouped


def _latest_timestamp(items: list[TrackBArtifactRecord]) -> str:
    stamps = [item.metadata.modified_at for item in items if item.metadata.modified_at]
    if not stamps:
        return ""
    return sorted(stamps)[-1]


def _extract_audit_metrics(path: str) -> dict[str, Any]:
    payload = _safe_read_json(Path(path))
    if payload is None:
        return {}
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    return {
        "completion_percent": _as_float(metrics.get("m8_completion_percentage")),
        "production_readiness_percent": _as_float(metrics.get("production_readiness_percentage")),
        "blocker_count": _as_int(metrics.get("blocker_count")),
    }


def build_cross_release_trends(records: list[TrackBArtifactRecord]) -> dict[str, Any]:
    audits = collect_track_b_audits()
    releases = collect_track_b_releases()
    readiness_rows = readiness_history(records)
    learning_records = collect_learning_records(records)
    dependency_summary = summarize_dependency_coverage(records)
    conflict_summary = summarize_conflicts(records)

    audit_trend = []
    for audit in audits:
        metrics = _extract_audit_metrics(audit.path)
        audit_trend.append(
            {
                "audit_id": audit.audit_id,
                "generated_at": audit.generated_at,
                "schema_version": audit.schema_version,
                "classification": audit.classification,
                **metrics,
            }
        )
    audit_trend.sort(key=lambda item: (item.get("generated_at") or "", item.get("audit_id") or ""))

    readiness_trend = [
        {
            "artifact_id": row["artifact_id"],
            "component": row["component"],
            "readiness_status": row["readiness_status"],
            "classification": row["classification"],
            "score_percent": row["score_percent"],
            "modified_at": row["modified_at"],
        }
        for row in readiness_rows
    ]

    release_trend = [
        {
            "release_tag": release.release_tag,
            "commit_sha": release.commit_sha,
            "schema_status": release.schema_status,
            "audit_status": release.audit_status,
            "schema_version": release.schema_version,
        }
        for release in releases
    ]
    release_trend.sort(key=lambda item: (item["release_tag"], item["commit_sha"]))

    learning_trend: list[dict[str, Any]] = []
    learning_by_release: dict[str, dict[str, Any]] = {}
    for entry in learning_records:
        for release_tag in entry.release_backlinks:
            bucket = learning_by_release.setdefault(
                release_tag,
                {
                    "release_tag": release_tag,
                    "total_lessons": 0,
                    "entry_type_counts": {},
                    "latest_generated_at": "",
                },
            )
            bucket["total_lessons"] += 1
            entry_counts = bucket["entry_type_counts"]
            entry_counts[entry.entry_type] = entry_counts.get(entry.entry_type, 0) + 1
            if entry.generated_at and entry.generated_at > bucket["latest_generated_at"]:
                bucket["latest_generated_at"] = entry.generated_at

    for bucket in learning_by_release.values():
        entry_counts = [
            {"entry_type": entry_type, "count": count}
            for entry_type, count in bucket["entry_type_counts"].items()
        ]
        entry_counts.sort(key=lambda item: (item["entry_type"], item["count"]))
        learning_trend.append(
            {
                "release_tag": bucket["release_tag"],
                "total_lessons": bucket["total_lessons"],
                "entry_type_counts": entry_counts,
                "latest_generated_at": bucket["latest_generated_at"],
            }
        )
    learning_trend.sort(key=lambda item: (item["release_tag"], item["latest_generated_at"]))

    generated_at = _stable_generated_at_from_strings(
        [
            _stable_generated_at_from_records(records),
            _stable_generated_at_from_strings([audit.generated_at for audit in audits if audit.generated_at]),
            _stable_generated_at_from_learning(learning_records),
        ]
    )

    return {
        "classification": "PASS",
        "generated_at": generated_at,
        "audit_trend": audit_trend,
        "release_trend": release_trend,
        "readiness_trend": readiness_trend,
        "learning_trend": learning_trend,
        "dependency_summary": _normalize_summary_generated_at(dependency_summary, generated_at),
        "conflict_summary": _normalize_summary_generated_at(conflict_summary, generated_at),
    }


def mine_patterns(records: list[TrackBArtifactRecord]) -> dict[str, Any]:
    failure_reasons: dict[str, int] = {}
    readiness_blockers: dict[str, int] = {}
    dependency_issues: dict[str, int] = {}
    conflict_categories: dict[str, int] = {}

    for record in records:
        payload = record.payload or {}
        if record.metadata.artifact_file == "track_b_upstreaming_readiness.json":
            for reason in payload.get("fail_closed_reasons", []) if isinstance(payload.get("fail_closed_reasons"), list) else []:
                key = _normalize_text(reason)
                if key:
                    failure_reasons[key] = failure_reasons.get(key, 0) + 1
            mandatory_checks = payload.get("mandatory_checks") if isinstance(payload.get("mandatory_checks"), dict) else {}
            for check, value in mandatory_checks.items():
                if not bool(value):
                    readiness_blockers[check] = readiness_blockers.get(check, 0) + 1

        if record.metadata.artifact_file == "track_b_dependency_matrix.json":
            for dep in payload.get("dependency_records", []) if isinstance(payload.get("dependency_records"), list) else []:
                if not isinstance(dep, dict):
                    continue
                missing = _as_int(dep.get("missing_dependency_count"))
                if missing <= 0:
                    continue
                key = _normalize_text(dep.get("upstream_path") or dep.get("downstream_path") or dep.get("candidate_id"))
                if key:
                    dependency_issues[key] = dependency_issues.get(key, 0) + 1

        if record.metadata.artifact_file == "track_b_conflict_ledger.json":
            for conflict in payload.get("conflicts", []) if isinstance(payload.get("conflicts"), list) else []:
                if not isinstance(conflict, dict):
                    continue
                category = _normalize_text(conflict.get("conflict_type") or "UNKNOWN").upper()
                conflict_categories[category] = conflict_categories.get(category, 0) + 1

    def _sorted_counts(counts: dict[str, int]) -> list[dict[str, Any]]:
        rows = [{"key": key, "count": counts[key]} for key in sorted(counts.keys())]
        rows.sort(key=lambda row: (-row["count"], row["key"]))
        return rows

    return {
        "classification": "PASS",
        "generated_at": _stable_generated_at_from_records(records),
        "recurring_failures": _sorted_counts(failure_reasons),
        "recurring_dependency_issues": _sorted_counts(dependency_issues),
        "recurring_conflict_categories": _sorted_counts(conflict_categories),
        "repeated_readiness_blockers": _sorted_counts(readiness_blockers),
    }


def _recommend_from_equivalence(eq_payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = eq_payload.get("candidate_mappings")
    if not isinstance(candidates, list) or not candidates:
        return []
    sorted_candidates = sorted(
        [c for c in candidates if isinstance(c, dict)],
        key=lambda item: (-_as_float(item.get("mapping_score")), _normalize_text(item.get("upstream_symbol")), _normalize_text(item.get("upstream_path")), _as_int(item.get("upstream_line_start"))),
    )
    top = sorted_candidates[0]
    evidence = top.get("evidence") if isinstance(top.get("evidence"), list) else []
    if not evidence:
        return []
    return [
        {
            "recommendation_type": "MAPPING_SUGGESTION",
            "summary": "Review highest-ranked upstream candidate mapping.",
            "candidate_id": _normalize_text(top.get("candidate_id")),
            "upstream_symbol": _normalize_text(top.get("upstream_symbol")),
            "upstream_path": _normalize_text(top.get("upstream_path")),
            "mapping_score": _as_float(top.get("mapping_score")),
            "evidence_refs": evidence,
        }
    ]


def _recommend_dependency_actions(dep_payload: dict[str, Any]) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    evidence_refs = dep_payload.get("evidence") if isinstance(dep_payload.get("evidence"), list) else []
    for dep in dep_payload.get("dependency_records", []) if isinstance(dep_payload.get("dependency_records"), list) else []:
        if not isinstance(dep, dict):
            continue
        missing = _as_int(dep.get("missing_dependency_count"))
        if missing <= 0:
            continue
        record_evidence = dep.get("evidence_refs") if isinstance(dep.get("evidence_refs"), list) else []
        resolved_evidence = record_evidence or evidence_refs
        if not resolved_evidence:
            continue
        recommendations.append(
            {
                "recommendation_type": "DEPENDENCY_RESOLUTION",
                "summary": "Resolve missing dependency links for candidate.",
                "candidate_id": _normalize_text(dep.get("candidate_id")),
                "upstream_path": _normalize_text(dep.get("upstream_path")),
                "downstream_path": _normalize_text(dep.get("downstream_path")),
                "missing_dependency_count": missing,
                "mandatory_checks": dep.get("mandatory_checks", {}),
                "evidence_refs": resolved_evidence,
            }
        )
    recommendations.sort(key=lambda item: (-_as_int(item.get("missing_dependency_count")), _normalize_text(item.get("candidate_id"))))
    return recommendations


def _recommend_conflict_actions(conflict_payload: dict[str, Any]) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    evidence_refs = conflict_payload.get("evidence") if isinstance(conflict_payload.get("evidence"), list) else []
    for conflict in conflict_payload.get("conflicts", []) if isinstance(conflict_payload.get("conflicts"), list) else []:
        if not isinstance(conflict, dict):
            continue
        status = _normalize_text(conflict.get("status")).upper()
        if status == "RESOLVED":
            continue
        record_evidence = conflict.get("evidence_refs") if isinstance(conflict.get("evidence_refs"), list) else []
        resolved_evidence = record_evidence or evidence_refs
        if not resolved_evidence:
            continue
        recommendations.append(
            {
                "recommendation_type": "CONFLICT_RESOLUTION",
                "summary": "Resolve outstanding conflict before readiness.",
                "conflict_id": _normalize_text(conflict.get("conflict_id")),
                "conflict_type": _normalize_text(conflict.get("conflict_type")),
                "severity": _normalize_text(conflict.get("severity")),
                "status": status,
                "candidate_ids": conflict.get("candidate_ids", []),
                "evidence_refs": resolved_evidence,
            }
        )
    recommendations.sort(key=lambda item: (_normalize_text(item.get("severity")), _normalize_text(item.get("conflict_id"))))
    return recommendations


def _recommend_readiness_actions(readiness_payload: dict[str, Any]) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    evidence_refs = readiness_payload.get("evidence") if isinstance(readiness_payload.get("evidence"), list) else []
    if not evidence_refs:
        return []
    mandatory = readiness_payload.get("mandatory_checks") if isinstance(readiness_payload.get("mandatory_checks"), dict) else {}
    for check, value in mandatory.items():
        if not bool(value):
            recommendations.append(
                {
                    "recommendation_type": "READINESS_ACTION",
                    "summary": f"Resolve readiness check: {check}",
                    "check_id": check,
                    "evidence_refs": evidence_refs,
                }
            )
    recommendations.sort(key=lambda item: _normalize_text(item.get("check_id")))
    return recommendations


def build_recommendations(records: list[TrackBArtifactRecord]) -> dict[str, Any]:
    grouped = _group_by_run(records)
    output: list[dict[str, Any]] = []

    for run_key in sorted(grouped.keys()):
        run_records = grouped[run_key]
        eq = next((r for r in run_records if r.metadata.artifact_file == "track_b_equivalence_map.json"), None)
        dep = next((r for r in run_records if r.metadata.artifact_file == "track_b_dependency_matrix.json"), None)
        conflict = next((r for r in run_records if r.metadata.artifact_file == "track_b_conflict_ledger.json"), None)
        readiness = next((r for r in run_records if r.metadata.artifact_file == "track_b_upstreaming_readiness.json"), None)

        recs: list[dict[str, Any]] = []
        if eq and eq.payload:
            recs.extend(_recommend_from_equivalence(eq.payload))
        if dep and dep.payload:
            recs.extend(_recommend_dependency_actions(dep.payload))
        if conflict and conflict.payload:
            recs.extend(_recommend_conflict_actions(conflict.payload))
        if readiness and readiness.payload:
            recs.extend(_recommend_readiness_actions(readiness.payload))

        if not recs:
            continue

        supporting_artifacts = [
            {
                "artifact_id": r.metadata.artifact_id,
                "artifact_file": r.metadata.artifact_file,
                "artifact_name": r.metadata.artifact_name,
            }
            for r in (eq, dep, conflict, readiness)
            if r is not None
        ]
        lineage_refs = [entry["artifact_id"] for entry in supporting_artifacts]

        for entry in recs:
            entry["lineage_refs"] = lineage_refs
            entry["supporting_artifacts"] = supporting_artifacts
            entry["run_id"] = run_key
            entry["component"] = readiness.metadata.component if readiness else (eq.metadata.component if eq else "")

        output.extend(recs)

    output.sort(key=lambda item: (_normalize_text(item.get("recommendation_type")), _normalize_text(item.get("component")), _normalize_text(item.get("summary"))))
    return {
        "classification": "PASS",
        "generated_at": _stable_generated_at_from_records(records),
        "recommendations": output,
    }


def build_learning_intelligence(records: list[TrackBArtifactRecord]) -> dict[str, Any]:
    learning_records = collect_learning_records(records)
    readiness_rows = readiness_history(records)
    readiness_score_by_artifact: dict[str, float] = {row["artifact_id"]: float(row.get("score_percent") or 0.0) for row in readiness_rows}
    readiness_status_by_artifact: dict[str, str] = {row["artifact_id"]: str(row.get("readiness_status") or "") for row in readiness_rows}

    record_by_path: dict[str, TrackBArtifactRecord] = {
        item.metadata.artifact_path: item for item in records
    }

    clusters: dict[tuple[str, str], dict[str, Any]] = {}
    cluster_entries: dict[tuple[str, str], list[TrackBLearningRecord]] = {}
    for entry in learning_records:
        key = (entry.entry_type, _normalize_text(entry.title).lower())
        cluster = clusters.setdefault(
            key,
            {
                "entry_type": entry.entry_type,
                "cluster_key": key[1],
                "count": 0,
                "latest_generated_at": "",
                "entries": [],
            },
        )
        cluster_entries.setdefault(key, []).append(entry)
        cluster["count"] += 1
        cluster["entries"].append(
            {
                "entry_id": entry.entry_id,
                "title": entry.title,
                "classification": entry.classification,
                "generated_at": entry.generated_at,
                "path": entry.path,
            }
        )
        if entry.generated_at and entry.generated_at > cluster["latest_generated_at"]:
            cluster["latest_generated_at"] = entry.generated_at

    cluster_rows = list(clusters.values())
    cluster_rows.sort(key=lambda item: (-_as_int(item["count"]), _normalize_text(item["cluster_key"])))
    for cluster in cluster_rows:
        cluster["entries"] = sorted(cluster["entries"], key=lambda item: (item["generated_at"], item["entry_id"]))[:10]

    reference_generated_at = _stable_generated_at_from_learning(learning_records)
    reference_dt = _parse_iso(reference_generated_at) if reference_generated_at else None
    stale = []
    for cluster in cluster_rows:
        latest = _parse_iso(cluster.get("latest_generated_at") or "")
        if latest and reference_dt and (reference_dt - latest) >= timedelta(days=90):
            stale.append(cluster["cluster_key"])
    stale.sort()

    ranked_lessons: list[dict[str, Any]] = []
    for key, entries in cluster_entries.items():
        cluster = clusters[key]
        releases = set()
        readiness_scores: list[float] = []
        readiness_statuses: list[str] = []
        for entry in entries:
            releases.update(entry.release_backlinks)
            record = record_by_path.get(entry.path)
            if record and record.metadata.artifact_file == "track_b_upstreaming_readiness.json":
                artifact_id = record.metadata.artifact_id
                readiness_scores.append(readiness_score_by_artifact.get(artifact_id, 0.0))
                readiness_statuses.append(readiness_status_by_artifact.get(artifact_id, ""))

        frequency = len(entries)
        recurrence = len(releases)
        if readiness_statuses:
            ready_count = len([status for status in readiness_statuses if status.upper() == "READY"])
            remediation_success_rate = ready_count / len(readiness_statuses)
        else:
            remediation_success_rate = 0.0
        if readiness_scores:
            avg_score = sum(readiness_scores) / len(readiness_scores)
            readiness_impact = round(max(0.0, 100.0 - avg_score), 2)
        else:
            readiness_impact = 0.0

        usefulness_score = round(
            (frequency * 10.0)
            + (recurrence * 5.0)
            + (remediation_success_rate * 20.0)
            + (readiness_impact / 100.0 * 15.0),
            2,
        )

        ranked_lessons.append(
            {
                "entry_type": cluster["entry_type"],
                "cluster_key": cluster["cluster_key"],
                "count": frequency,
                "recurrence": recurrence,
                "remediation_success_rate": round(remediation_success_rate, 4),
                "readiness_impact": readiness_impact,
                "usefulness_score": usefulness_score,
                "latest_generated_at": cluster["latest_generated_at"],
            }
        )

    ranked_lessons.sort(key=lambda item: (-item["usefulness_score"], item["cluster_key"]))

    return {
        "classification": "PASS",
        "generated_at": reference_generated_at,
        "clusters": cluster_rows,
        "ranked_lessons": ranked_lessons[:50],
        "usefulness_model": {
            "frequency_weight": 10.0,
            "recurrence_weight": 5.0,
            "remediation_success_weight": 20.0,
            "readiness_impact_weight": 15.0,
        },
        "stale_clusters": stale,
        "total_lessons": len(learning_records),
    }


def build_executive_dashboard(records: list[TrackBArtifactRecord]) -> dict[str, Any]:
    readiness = summarize_readiness(records)
    conflicts = summarize_conflicts(records)
    dependencies = summarize_dependency_coverage(records)

    coverage = dependencies.get("coverage", {}) if isinstance(dependencies, dict) else {}
    resolved_total = 0
    observed_total = 0
    for item in coverage.values():
        if isinstance(item, dict):
            resolved_total += _as_int(item.get("resolved"))
            observed_total += _as_int(item.get("total"))
    dependency_coverage = round((resolved_total / observed_total) * 100.0, 2) if observed_total else 0.0

    return {
        "classification": "PASS",
        "generated_at": _stable_generated_at_from_records(records),
        "project_health": readiness.get("production_readiness_percent", 0.0),
        "release_health": readiness.get("release_status", "UNKNOWN"),
        "audit_health": readiness.get("audit_status", "UNKNOWN"),
        "blocker_count": readiness.get("blocker_count", 0),
        "open_conflict_count": conflicts.get("open_conflicts", 0),
        "dependency_coverage_percent": dependency_coverage,
        "evidence_completeness_percent": readiness.get("evidence_completeness_percent", 0.0),
    }


def build_readiness_forecast(records: list[TrackBArtifactRecord]) -> dict[str, Any]:
    rows = readiness_history(records)
    total = len(rows)
    ready = len([row for row in rows if _normalize_text(row.get("readiness_status")).upper() == "READY"])
    probability = round((ready / total) * 100.0, 2) if total else 0.0

    conflicts = summarize_conflicts(records)
    dependencies = summarize_dependency_coverage(records)
    coverage = dependencies.get("coverage", {}) if isinstance(dependencies, dict) else {}
    unresolved_conflicts = _as_int(conflicts.get("open_conflicts"))

    coverage_score = 0.0
    if coverage:
        totals = [float(item.get("coverage_percent") or 0.0) for item in coverage.values() if isinstance(item, dict)]
        coverage_score = round(sum(totals) / len(totals), 2) if totals else 0.0

    if unresolved_conflicts > 0 or coverage_score < 50.0:
        risk_level = "HIGH"
    elif coverage_score < 80.0:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    remaining_work = unresolved_conflicts + max(0, 100 - int(coverage_score)) // 10

    return {
        "classification": "PASS",
        "generated_at": _stable_generated_at_from_records(records),
        "readiness_probability_percent": probability,
        "risk_level": risk_level,
        "remaining_work_estimate": remaining_work,
        "sample_count": total,
    }


def track_b_intelligence_overview(*, strict: bool = True) -> dict[str, Any]:
    overview = track_b_overview(strict=strict)
    records = overview["records"]
    return {
        "classification": "PASS" if overview["validation"].valid else "FAIL_CLOSED",
        "generated_at": _stable_generated_at_from_records(records),
        "validation": overview["validation"],
        "trends": build_cross_release_trends(records),
        "patterns": mine_patterns(records),
        "recommendations": build_recommendations(records),
        "learning": build_learning_intelligence(records),
        "executive": build_executive_dashboard(records),
        "forecast": build_readiness_forecast(records),
    }
