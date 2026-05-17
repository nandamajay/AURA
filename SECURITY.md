# Security Policy

## Reporting a Vulnerability

Report suspected vulnerabilities privately to repository maintainers.
Do not publish exploit details before coordinated remediation.

## Scope

Security-sensitive areas include:
- authentication and token handling,
- governance approval controls,
- audit integrity and replay integrity paths,
- secret/config handling in service runtimes.

## Secret Handling Rules

- Never commit `.env` files or live credentials.
- Never commit runtime DB snapshots with sensitive data.
- Use template files (`.env.example`) for documentation only.

## Disclosure Workflow

1. Report privately with reproduction details.
2. Maintainer acknowledges and triages severity.
3. Fix is developed on stabilization branch with evidence.
4. Patch is released and disclosure is coordinated.
