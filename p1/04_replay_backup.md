# AURA P1 — Replay Recovery, Backup/Restore & Disaster Recovery
## Artifacts: 8, 9, 10 | Anti-Overengineering: Applied
### Built on: Frozen P0 (Deterministic Context, Task Recorder, Replay Engine)

---

## ARTIFACT 8: REPLAY RECOVERY POLICY

### 8.1 Recording Guarantees

| Guarantee | Implementation | Verification |
|-----------|---------------|------------|
| G-01 | Every LLM prompt is recorded | `record_prompt()` called before every `call_llm()` | Query task_logs table |
| G-02 | Every LLM response is recorded | `record_response()` called with raw response | Query task_logs table |
| G-03 | Execution seed is recorded | DeterministicContext.seed stored at task start | Hash match on replay |
| G-04 | Model version is pinned | `model_version` stored, not dynamic | Cross-check with model release date |
| G-05 | Output hash is verifiable | SHA256(output_json) stored, compared on replay | ReplayResult.hash_match |
| G-06 | Partial recordings survive crashes | Each record_* does immediate INSERT | Check DB on recovery |
| G-07 | Recording doesn't block execution | Async writes, separate DB connection | Latency < 1ms per write |

### 8.2 Replay Fidelity Levels

```
PERFECT:    output_hash == expected_hash
            → Identical output, complete confidence

PARTIAL:    output_hash != expected_hash 
            AND responses_consumed == total_responses
            → Same LLM responses used, but agent logic diverged
            → Likely cause: code change in agent

INCOMPLETE: responses_consumed < total_responses
            → Replay stopped early (exception or timeout)
            → Likely cause: agent code change or resource issue

MISMATCH:   responses_consumed > total_responses
            → Replay needed more responses than recorded
            → Likely cause: agent now makes more LLM calls
```

### 8.3 Replay Recovery Policy

| Scenario | Action | Human Required |
|----------|--------|---------------|
| PERFECT replay | Use for regression testing | No |
| PARTIAL replay | Flag for review, check agent code diff | Maybe |
| INCOMPLETE replay | Flag as bug, create incident | Yes |
| MISMATCH replay | Update test expectations | Maybe |
| Recorded responses missing | Cannot replay, flag as data loss | Yes |
| DB corruption during replay | Use snapshot restore (see Art. 9) | Yes |

### 8.4 Snapshot Policy

| Parameter | Value | Justification |
|-----------|-------|---------------|
| Auto-snapshot frequency | Before each migration batch | Recovery point before risky operation |
| Snapshot retention | 30 days | Sufficient for most incidents |
| Max snapshots | 50 | Prevent disk exhaustion |
| Snapshot location | `./data/snapshots/{timestamp}_{label}/` | Host volume, Docker-agnostic |
| Snapshot contents | SQLite DB + WAL + agent outputs | Full recoverable state |
| Manual snapshot | POST /admin/snapshot?label=pre-release | Admin-initiated |

---

## ARTIFACT 9: BACKUP + RESTORE STRATEGY

### 9.1 Backup Levels

```
Level 1: Continuous (WAL)
  - SQLite WAL file provides continuous crash recovery
  - No admin action required
  - Survives: process crash, power loss
  - Does NOT survive: disk corruption, accidental deletion

Level 2: Hourly (WAL checkpoint)
  - `PRAGMA wal_checkpoint(RESTART)` → consolidates WAL into DB
  - Automated: cron job or orchestrator timer
  - Retention: 24 hours (24 copies)

Level 3: Daily (file copy)
  - `cp data/aura.db data/backups/aura_YYYYMMDD.db`
  - gzip compression
  - Retention: 30 days
  - Storage: ~5MB per backup (compressed)

Level 4: Weekly (full export)
  - JSON export of all tables
  - Stored in data/exports/
  - Retention: 90 days
  - Purpose: Data portability, compliance

Level 5: Manual (snapshot)
  - Full snapshot: DB + WAL + agent outputs
  - Admin-triggered
  - Purpose: Major changes, pre-upgrade
```

### 9.2 Automated Backup Script

```bash
#!/bin/bash
# scripts/backup.sh — Daily automated backup

BACKUP_DIR="./data/backups"
DB_PATH="./data/aura.db"
WAL_PATH="./data/aura.db-wal"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/aura_$TIMESTAMP.db"

# Ensure WAL is checkpointed
docker compose exec -T aura-core \
    sqlite3 /data/aura.db "PRAGMA wal_checkpoint(RESTART);"

# Copy database
cp "$DB_PATH" "$BACKUP_FILE"

# Include WAL if it exists
if [ -f "$WAL_PATH" ]; then
    cp "$WAL_PATH" "$BACKUP_FILE-wal"
fi

# Compress
gzip -f "$BACKUP_FILE"
[ -f "$BACKUP_FILE-wal" ] && gzip -f "$BACKUP_FILE-wal"

# Retention: keep last 30 daily backups
find "$BACKUP_DIR" -name "aura_*.db.gz" -mtime +30 -delete
find "$BACKUP_DIR" -name "aura_*.db-wal.gz" -mtime +30 -delete

echo "Backup: $BACKUP_FILE.gz ($(stat -f%z "$BACKUP_FILE.gz" 2>/dev/null || stat -c%s "$BACKUP_FILE.gz") bytes)"
```

### 9.3 Restore Procedure

```bash
#!/bin/bash
# scripts/restore.sh — Restore from backup

BACKUP_DIR="./data/backups"
DB_PATH="./data/aura.db"

# List available backups
echo "Available backups:"
ls -lt "$BACKUP_DIR"/*.db.gz | head -20

# Get backup to restore
if [ -z "$1" ]; then
    echo "Usage: $0 <backup_filename>"
    exit 1
fi
BACKUP_FILE="$BACKUP_DIR/$1"

# Stop services
docker compose stop aura-core

# Restore
gunzip -c "$BACKUP_FILE" > "$DB_PATH"

# If WAL backup exists, restore it too
WAL_BACKUP="${BACKUP_FILE%.db.gz}.db-wal.gz"
if [ -f "$WAL_BACKUP" ]; then
    gunzip -c "$WAL_BACKUP" > "./data/aura.db-wal"
fi

# Start services
docker compose start aura-core

# Verify
echo "Verifying database..."
docker compose exec aura-core sqlite3 /data/aura.db "PRAGMA integrity_check;"

echo "Restore complete."
```

---

## ARTIFACT 10: DISASTER RECOVERY PLAYBOOK

### 10.1 Failure Scenarios & Recovery

| Scenario | RTO | RPO | Recovery | Steps |
|----------|-----|-----|----------|-------|
| Agent crash | 30s | N/A | Auto-retry | RetryExecutor handles |
| Agent timeout | 2 min | N/A | Auto-retry | Watchdog + retry |
| LLM outage | 5 min | N/A | Auto-fallback | Queue + alert admin |
| DB corruption | 10 min | 24h | Restore backup | scripts/restore.sh |
| Host disk full | 15 min | N/A | Manual cleanup | Free disk, restart |
| Host OOM | 5 min | N/A | Auto-restart | Docker restart policy |
| Container failure | 1 min | N/A | Auto-restart | Docker healthcheck |
| Full host failure | 30 min | 24h | Restore from backup | New host + restore |
| Cascading failure | 30 min | N/A | Degraded mode | Manual intervention |

### 10.2 Recovery Playbook Template

```
INCIDENT RESPONSE TEMPLATE

1. DETECT
   - Source: alert / monitoring / user report
   - Timestamp: 
   - Severity: P0 (platform down) / P1 (degraded) / P2 (warning)

2. ASSESS
   - Check: make health
   - Check: docker compose ps
   - Check: tail -50 data/logs/core.jsonl
   - Identify: affected subsystem(s)

3. CONTAIN
   - If cascading: enter degraded mode
   - If resource exhaustion: stop background agents
   - If security incident: revoke sessions, rotate secrets

4. RESOLVE
   - Follow specific procedure (F-01 through F-04)
   - Verify fix: make health returns 200

5. RECOVER
   - Exit degraded mode if applicable
   - Resume normal operations
   - Verify all agents responding

6. REVIEW
   - Generate incident report from audit log
   - Update runbooks if needed
   - Post-mortem within 48 hours
```

---

## SELF-VALIDATION

| Artifact | Complexity | AOG Pass | Notes |
|----------|-----------|----------|-------|
| Replay Recovery | Low | Yes | 4 fidelity levels, clear actions |
| Backup/Restore | Low | Yes | 5 levels, standard SQLite patterns |
| Disaster Recovery | Medium | Yes | 9 scenarios with RTO/RPO, no K8s needed |
