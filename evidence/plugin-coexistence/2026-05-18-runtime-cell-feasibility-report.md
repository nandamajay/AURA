# Runtime Cell Feasibility Report

Run ID: `plugin-coexist-20260518T102218Z-yuhxd7`

## Assessed Feasibility
`{
  "replay_partition_feasibility": {
    "status": "partial",
    "reason": "task_logs preserve per-task input domain markers, but replay namespace is not enforced by runtime partition key",
    "evidence": {
      "namespace_mismatch_count": 0,
      "task_log_coverage": 56
    }
  },
  "governance_partition_feasibility": {
    "status": "partial",
    "reason": "approval IDs and patch IDs can be domain-scoped by convention, but governance schema has no explicit domain boundary column",
    "evidence": {
      "status_by_domain": {
        "driver": {
          "passed": 3,
          "failed": 3,
          "pending": 3,
          "in_progress": 3
        },
        "media": {
          "passed": 3,
          "failed": 3,
          "pending": 3,
          "in_progress": 3
        },
        "automation": {
          "passed": 3,
          "failed": 3,
          "pending": 3,
          "in_progress": 3
        },
        "research": {
          "passed": 3,
          "failed": 3,
          "pending": 3,
          "in_progress": 3
        }
      },
      "audit_entries_count": 52
    }
  },
  "queue_partition_feasibility": {
    "status": "weak",
    "reason": "single shared 3-tier scheduler with no per-domain quotas or isolation gates",
    "evidence": {
      "queue_samples": 12,
      "per_domain_summary": {
        "driver": {
          "created": 14,
          "final_status_counts": {
            "completed": 14
          },
          "replay_status_counts": {
            "200": 14
          },
          "replay_integrity_ok": 14,
          "start_lag_seconds": {
            "count": 14,
            "p50": 0.349,
            "p95": 0.64,
            "max": 0.673
          }
        },
        "media": {
          "created": 14,
          "final_status_counts": {
            "completed": 14
          },
          "replay_status_counts": {
            "200": 14
          },
          "replay_integrity_ok": 14,
          "start_lag_seconds": {
            "count": 14,
            "p50": 1.163,
            "p95": 1.621,
            "max": 1.644
          }
        },
        "automation": {
          "created": 14,
          "final_status_counts": {
            "completed": 14
          },
          "replay_status_counts": {
            "200": 14
          },
          "replay_integrity_ok": 14,
          "start_lag_seconds": {
            "count": 14,
            "p50": 16.77,
            "p95": 17.539,
            "max": 17.604
          }
        },
        "research": {
          "created": 14,
          "final_status_counts": {
            "completed": 14
          },
          "replay_status_counts": {
            "200": 14
          },
          "replay_integrity_ok": 14,
          "start_lag_seconds": {
            "count": 14,
            "p50": 0.858,
            "p95": 1.21,
            "max": 2.323
          }
        }
      }
    }
  },
  "event_bus_partition_feasibility": {
    "status": "weak",
    "reason": "shared system channel fanout causes cross-domain event visibility under coexistence pressure",
    "evidence": {
      "max_foreign_ratio": 0.751,
      "collector_samples": [
        {
          "watch_domain": "driver",
          "total": 1012,
          "own": 253,
          "foreign": 759,
          "foreign_ratio": 0.75,
          "retry_seen": {
            "driver": [
              4,
              5,
              6
            ],
            "media": [
              4,
              5,
              6
            ],
            "automation": [
              4,
              5,
              6
            ],
            "research": [
              4,
              5,
              6
            ]
          }
        },
        {
          "watch_domain": "media",
          "total": 380,
          "own": 95,
          "foreign": 285,
          "foreign_ratio": 0.75,
          "retry_seen": {}
        },
        {
          "watch_domain": "automation",
          "total": 1012,
          "own": 253,
          "foreign": 759,
          "foreign_ratio": 0.75,
          "retry_seen": {
            "driver": [
              4,
              5,
              6
            ],
            "media": [
              4,
              5,
              6
            ],
            "automation": [
              4,
              5,
              6
            ],
            "research": [
              4,
              5,
              6
            ]
          }
        },
        {
          "watch_domain": "research",
          "total": 382,
          "own": 95,
          "foreign": 287,
          "foreign_ratio": 0.751,
          "retry_seen": {}
        }
      ]
    }
  },
  "per_plugin_audit_scope": {
    "status": "partial",
    "reason": "audit is global append-only; per-plugin views are reconstructable via target_id conventions"
  },
  "per_plugin_replay_lineage": {
    "status": "partial",
    "reason": "lineage exists per task_id but not enforced as plugin runtime-cell namespace"
  },
  "per_plugin_observability": {
    "status": "partial",
    "reason": "domain markers in payload/input enable derived metrics, but counters are not partition-native"
  },
  "trust_sandbox_boundaries": {
    "status": "weak",
    "reason": "plugin registry supports load-time containment only; no hard trust sandbox per plugin"
  }
}`

## Key Direction
- Replay/governance partitioning is feasible by convention today, but weak without explicit partition keys.
- Queue/event bus are the dominant blockers for strong runtime-cell guarantees.
- Per-plugin observability can be derived, but is not first-class isolated telemetry.
