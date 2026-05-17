# AURA P1 — Plugin Trust Model, Infrastructure Hardening & Audit Compliance
## Artifacts: 15, 17, 18 | Anti-Overengineering: Applied
### Built on: Frozen P0 (Plugin Interface, Registry, Validation Schema)

---

## ARTIFACT 15: PLUGIN TRUST MODEL

### 15.1 Threat Model for Plugins

| ID | Threat | Severity | Mitigation |
|----|--------|----------|------------|
| PT-01 | Malicious plugin executes arbitrary code | HIGH | Plugin code review + sandbox |
| PT-02 | Plugin accesses files outside its directory | MEDIUM | chroot + read-only mounts |
| PT-03 | Plugin consumes excessive resources | MEDIUM | Resource limits per plugin |
| PT-04 | Plugin has network access | MEDIUM | Network isolation (llm-gateway only) |
| PT-05 | Plugin crashes orchestrator | LOW | try/except around all plugin calls |
| PT-06 | Plugin returns malformed data | LOW | Pydantic validation on all outputs |

### 15.2 Plugin Trust Levels

| Level | Trust | Verification | Sandbox |
|-------|-------|-------------|---------|
| BUILTIN | Maximum | Code-reviewed, in-repo | Standard agent sandbox |
| VETTED | High | Manual review + tests | Standard agent sandbox |
| COMMUNITY | Medium | Automated validation only | Restricted sandbox |
| UNTRUSTED | Low | Signature check only | Highly restricted sandbox |

**P1: Only BUILTIN level is supported.**
Plugins are in-repo (`./plugins/`). No external plugin loading.

**P2+:** VETTED and COMMUNITY levels with marketplace.

### 15.3 Plugin Validation Pipeline

```python
class PluginValidator:
    """Validates plugin before loading."""
    
    REQUIRED_METHODS = [
        "get_migration_rules",
        "analyze_dependencies", 
        "get_validation_commands",
        "get_maintainer_profiles",
        "get_simulation_models",
        "get_dashboard_widgets",
        "get_dts_conversion_rules",
    ]
    
    def validate(self, plugin: SubsystemPlugin) -> ValidationResult:
        errors = []
        warnings = []
        
        # Check properties
        for prop in ["name", "version", "subsystem_id"]:
            if not getattr(plugin, prop, None):
                errors.append(f"Missing property: {prop}")
        
        # Check methods exist and are callable
        for method_name in self.REQUIRED_METHODS:
            method = getattr(plugin, method_name, None)
            if not method:
                errors.append(f"Missing method: {method_name}")
            elif not callable(method):
                errors.append(f"Not callable: {method_name}")
        
        # Check method return types (lightweight)
        ctx = SubsystemContext(
            subsystem_name="test",
            downstream_path="/dev/null",
            upstream_path="/dev/null", 
            kernel_sources_path="/dev/null",
            config={},
        )
        
        try:
            rules = plugin.get_migration_rules(ctx)
            if not isinstance(rules, list):
                errors.append("get_migration_rules must return list")
        except Exception as e:
            errors.append(f"get_migration_rules failed: {e}")
        
        return ValidationResult(valid=len(errors)==0, errors=errors, warnings=warnings)
```

### 15.4 Plugin Sandbox (Restricted)

```python
PLUGIN_SANDBOX = SandboxConfig(
    # Same as agent sandbox but more restrictive
    memory_limit_mb=2048,     # 2GB (plugins don't compile)
    cpu_quota_percent=100,     # 1 core
    max_fds=50,
    max_processes=5,
    # Plugins can only read their own directory
    read_only_mounts=[
        "/kernel-sources",
        "/plugins/{plugin_name}/",  # Only their own files
    ],
    # No network for plugins (only agents call LLM)
    allowed_hosts=[],
)
```

---

## ARTIFACT 17: INFRASTRUCTURE HARDENING CHECKLIST

### 17.1 Docker Hardening

| # | Check | Status | Command |
|---|-------|--------|---------|
| H-01 | Containers run as non-root user | REQUIRED | `USER aura-agent` in Dockerfile |
| H-02 | No new privileges allowed | REQUIRED | `security_opt: [no-new-privileges:true]` |
| H-03 | Read-only root filesystem | REQUIRED | `read_only: true` + explicit writable volumes |
| H-04 | Dropped capabilities | REQUIRED | `cap_drop: [ALL]` |
| H-05 | No host network | REQUIRED | Use Docker bridge network |
| H-06 | No host PID namespace | REQUIRED | Default (container PID namespace) |
| H-07 | Resource limits set | REQUIRED | `deploy.resources.limits` |
| H-08 | Health checks configured | REQUIRED | `healthcheck` in compose |
| H-09 | No sensitive env in compose | REQUIRED | Use `.env` file, not inline |
| H-10 | Image from trusted base | REQUIRED | `python:3.12-slim` (official) |
| H-11 | No unnecessary packages | REQUIRED | Minimal apt install |
| H-12 | Secrets not in image layers | REQUIRED | Use build args, not ENV |

### 17.2 Network Hardening

| # | Check | Status | Implementation |
|---|-------|--------|---------------|
| H-13 | Internal services not exposed | REQUIRED | `127.0.0.1:port` for internal |
| H-14 | Only HTTPS externally (P2) | P2 | Caddy/nginx reverse proxy + TLS |
| H-15 | CORS restricted | REQUIRED | Only dashboard origin |
| H-16 | No exposed database port | REQUIRED | SQLite file, no network port |
| H-17 | LLM gateway rate limited | REQUIRED | Token bucket per agent |

### 17.3 File System Hardening

| # | Check | Status | Implementation |
|---|-------|--------|---------------|
| H-18 | Data directory permissions 700 | REQUIRED | `chmod 700 ./data` |
| H-19 | Backup files readable only by owner | REQUIRED | `chmod 600 ./data/backups/*` |
| H-20 | Log files readable only by owner | REQUIRED | `chmod 600 ./data/logs/*` |
| H-21 | Agent outputs isolated per task | REQUIRED | `mkdir -p ./data/agents/{task_id}` |
| H-22 | No world-writable directories | REQUIRED | Startup check |
| H-23 | Secrets files not readable by group | REQUIRED | `chmod 600 ./secrets/*` |

### 17.4 Hardening Verification Script

```bash
#!/bin/bash
# scripts/hardening-check.sh

echo "=== AURA Infrastructure Hardening Check ==="
FAIL=0

# H-01: Non-root user
docker compose exec aura-core id | grep -q "uid=1000" && echo "[PASS] H-01: Non-root user" || { echo "[FAIL] H-01"; FAIL=$((FAIL+1)); }

# H-04: Dropped capabilities
docker inspect aura-core --format '{{.HostConfig.CapDrop}}' | grep -q "ALL" && echo "[PASS] H-04: Capabilities dropped" || { echo "[FAIL] H-04"; FAIL=$((FAIL+1)); }

# H-13: Internal services localhost only
docker compose port llm-gateway 8000 | grep -q "127.0.0.1" && echo "[PASS] H-13: Internal service bound to localhost" || { echo "[WARN] H-13"; }

# H-18: Data directory permissions
stat -c "%a" ./data | grep -q "700" && echo "[PASS] H-18: Data directory restricted" || { echo "[FAIL] H-18"; FAIL=$((FAIL+1)); }

# H-19: Backup file permissions
find ./data/backups -type f ! -perm 600 | wc -l | grep -q "^0$" && echo "[PASS] H-19: Backup files restricted" || { echo "[FAIL] H-19"; FAIL=$((FAIL+1)); }

# H-23: Secrets permissions
find ./secrets -type f ! -perm 600 | wc -l | grep -q "^0$" && echo "[PASS] H-23: Secret files restricted" || { echo "[FAIL] H-23"; FAIL=$((FAIL+1)); }

echo ""
echo "Results: $(($FAIL)) failures"
[ $FAIL -eq 0 ] && echo "ALL CHECKS PASSED" || echo "REVIEW FAILURES ABOVE"
```

---

## ARTIFACT 18: AUDIT + COMPLIANCE RETENTION RULES

### 18.1 Audit Ledger Specification

**Properties:**
- Append-only: UPDATE and DELETE physically prevented by triggers
- Chain hash: SHA256(previous_hash + row_data) for tamper evidence
- Comprehensive: Every user action, every system event
- Queryable: Indexed by timestamp, user, target, event_type
- Exportable: JSON/CSV for compliance reporting

**Retention:**

| Data Type | Retention | Storage | Action After Retention |
|-----------|-----------|---------|----------------------|
| Audit ledger | Permanent | SQLite | Never deleted |
| Agent output files | 30 days | Filesystem | Compressed archive |
| Task logs (replay) | 90 days | SQLite | Archive to JSON |
| Debug logs | 7 days | Filesystem | Delete |
| Info logs | 30 days | Filesystem | Compress + archive |
| Error logs | 1 year | Filesystem | Compress + archive |
| Critical logs | Permanent | SQLite | Never deleted |
| Backups | 30 days | Filesystem | Delete old |
| Snapshots | 30 days | Filesystem | Delete old |
| Knowledge exports | 90 days | Filesystem | Archive |

### 18.2 Compliance Export

```bash
#!/bin/bash
# scripts/compliance-export.sh
# Generate compliance report for auditors

OUTPUT_DIR="./data/exports/compliance_$(date +%Y%m%d)"
mkdir -p "$OUTPUT_DIR"

# Export audit ledger
sqlite3 data/aura.db -csv "SELECT * FROM audit_ledger ORDER BY timestamp" > "$OUTPUT_DIR/audit.csv"

# Export user actions
sqlite3 data/aura.db -csv "SELECT * FROM users" > "$OUTPUT_DIR/users.csv"

# Export approval history
sqlite3 data/aura.db -csv "SELECT * FROM approvals ORDER BY created_at" > "$OUTPUT_DIR/approvals.csv"

# Export patches with approval status
sqlite3 data/aura.db -csv "SELECT * FROM patches ORDER BY created_at" > "$OUTPUT_DIR/patches.csv"

# Generate integrity report
echo "AURA Compliance Report" > "$OUTPUT_DIR/report.txt"
echo "Generated: $(date)" >> "$OUTPUT_DIR/report.txt"
echo "" >> "$OUTPUT_DIR/report.txt"
echo "Audit Events: $(wc -l < "$OUTPUT_DIR/audit.csv")" >> "$OUTPUT_DIR/report.txt"
echo "Users: $(wc -l < "$OUTPUT_DIR/users.csv")" >> "$OUTPUT_DIR/report.txt"
echo "Approvals: $(wc -l < "$OUTPUT_DIR/approvals.csv")" >> "$OUTPUT_DIR/report.txt"

# Compress
tar -czf "$OUTPUT_DIR.tar.gz" -C "$OUTPUT_DIR" .
echo "Compliance export: $OUTPUT_DIR.tar.gz"
```

### 18.3 Audit Governance Rules

| # | Rule | Enforcement |
|---|------|-------------|
| A-01 | Audit log is append-only | SQLite trigger: RAISE(ABORT) on UPDATE/DELETE |
| A-02 | Chain hash is computed on every insert | SQLite trigger: auto-compute after INSERT |
| A-03 | Chain hash can be verified | `verify_chain()` re-computes and compares |
| A-04 | Every approval action is logged | ApprovalEngine writes to audit_ledger before returning |
| A-05 | Every RBAC change is logged | Admin actions → audit_ledger |
| A-06 | Every system configuration change is logged | Config changes → audit_ledger |
| A-07 | Failed auth attempts are logged | Auth middleware → audit_ledger |
| A-08 | Audit log includes before/after state | before_state and after_state JSON columns |
| A-09 | Audit log includes session ID | Session tracking for forensics |
| A-10 | Audit log retention is permanent | No deletion mechanism exists |

---

## P1 MASTER INDEX — ALL 18 ARTIFACTS

| # | Artifact | File | Status |
|---|----------|------|--------|
| 1 | Security + Sandboxing Policy | `01_security_sandboxing.md` | ✅ |
| 2 | Failure Recovery Playbook | `01_security_sandboxing.md` | ✅ |
| 3 | Watchdog Governance Rules | `02_watchdog_circuit.md` | ✅ |
| 4 | Circuit Breaker Governance | `02_watchdog_circuit.md` | ✅ |
| 5 | Agent Isolation Policy | `01_security_sandboxing.md` | ✅ |
| 6 | Secret Management Policy | `01_security_sandboxing.md` | ✅ |
| 7 | Runtime Execution Policy | `03_runtime_cost.md` | ✅ |
| 8 | Replay Recovery Policy | `04_replay_backup.md` | ✅ |
| 9 | Backup + Restore Strategy | `04_replay_backup.md` | ✅ |
| 10 | Disaster Recovery Playbook | `04_replay_backup.md` | ✅ |
| 11 | Operational Monitoring Playbook | `05_monitoring_observability.md` | ✅ |
| 12 | Observability Governance Rules | `05_monitoring_observability.md` | ✅ |
| 13 | Runtime Cost Governance | `03_runtime_cost.md` | ✅ |
| 14 | Resource Budget Enforcement | `03_runtime_cost.md` | ✅ |
| 15 | Plugin Trust Model | `06_plugin_audit.md` | ✅ |
| 16 | Command Execution Restrictions | `01_security_sandboxing.md` | ✅ |
| 17 | Infrastructure Hardening Checklist | `06_plugin_audit.md` | ✅ |
| 18 | Audit + Compliance Retention Rules | `06_plugin_audit.md` | ✅ |

**P1 COMPLETE: 18/18 artifacts specified.**
