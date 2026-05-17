# SAFE_TO_PUSH Report

Generated: 2026-05-18 (Asia/Colombo)
Repository root: `<workspace-root>`
Git state at audit time: `No commits yet on master`

## Executive Status

Status: **CONDITIONAL / NOT READY TO PUSH UNTIL MANUAL REVIEW ACKNOWLEDGED**

Reason:
- Real credential file exists locally: `AURA/.env` (ignored, not pushable).
- Runtime DB/export artifacts with user/account data exist locally (ignored after policy hardening).
- Two files contain local path references and need explicit review before first public push.

## Detected Sensitive or Unsafe Local Artifacts

- `AURA/.env`
  - Contains live environment credentials/secrets.
  - Currently ignored by `.gitignore`.
- `AURA/data/aura.db`
  - Live SQLite runtime DB snapshot.
  - Currently ignored.
- `AURA/data/exports/**`
  - Contains exported runtime/audit/user CSV content (includes internal email and hashed auth data).
  - Currently ignored.
- `AURA/data/backups/**`
  - Runtime backup archives.
  - Currently ignored.
- `AURA/dashboard/node_modules/**`, `AURA/dashboard/dist/**`, Python cache directories
  - Build/runtime artifacts, ignored.

## Candidate Files Requiring Manual Review (Before First Push)

- `AURA/PHASE_COMPLETION_REPORT.md`
  - Contained a local absolute path reference; sanitized to `<workspace>/AURA`.
- `AURA/.env.example`
  - Contains local host-path example for QGenie CLI mount; template-only but should be intentionally accepted.
- `CLI_AGENT_HANDOFF_PROMPT.pdf`
  - Binary doc; proprietary/content review required before publishing.
- `AURA_Platform_Design_Document.docx`
  - Binary design doc; proprietary/content review required before publishing.

## Files/Classes Excluded by Ignore Policy

- Secrets and env files: `.env`, `.env.*` (except `.env.example`/sample/template).
- Key material: `*.pem`, `*.key`, `id_rsa*`, `id_ed25519*`.
- Python artifacts: `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, virtualenvs, coverage outputs.
- Node/Vite artifacts: `node_modules`, `.vite`, `.next`, coverage outputs.
- Docker local overrides: `docker-compose.override.yml`, `docker-compose.local.yml`, `docker-compose.*.local.yml`.
- DB/WAL/shm: `*.db`, `*.sqlite*`, `*-wal`, `*-shm`.
- Runtime data: `AURA/data/backups/**`, `AURA/data/exports/**`, `AURA/data/logs/**`, `AURA/data/tmp/**`, `AURA/data/agents/**`, `AURA/data/outputs/**`.
- Evidence exception preserved for commit eligibility:
  - `AURA/data/outputs/runtime_discovery/*.json`

## Secret Scan Result (Push-Candidate Scope)

- No live API keys/tokens/private keys detected in commit-candidate text files.
- Placeholder examples detected in docs/templates (`sk-your-key`, env variable examples), expected and non-sensitive.

## Required Gate Before Push

Before first push, explicitly confirm inclusion/exclusion decision for:
- `AURA/PHASE_COMPLETION_REPORT.md`
- `AURA/.env.example` local-path comment line
- `CLI_AGENT_HANDOFF_PROMPT.pdf`
- `AURA_Platform_Design_Document.docx`
