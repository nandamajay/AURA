# Transport Governance Validation

## Status
- phase: T5 + W3
- result: PASSED_WITH_ADVISORY
- date: 2026-05-20
- scope: static repository scan for hardcoded transport usage outside transport adapters

## Evidence
- command: `grep -RIn "\\badb\\b" AURA --include='*.py' --exclude-dir='transport'`
- result: no matches
- command: `grep -RIn "\\bssh\\b" AURA --include='*.py' --exclude-dir='transport'`
- result: one match in URL parsing logic only
- command: `grep -RIn "ttyUSB|serial" AURA --include='*.py' --exclude-dir='transport'`
- result: no matches
- command: `grep -RIn "pyserial|import serial|COM[0-9]" AURA --include='*.py' --exclude-dir='transport'`
- result: no matches

## Findings
- No hardcoded adb, ssh command execution, or serial COM access detected outside transport adapters.
- No direct collector-side COM access patterns were detected by static scan.
- One reference to `ssh` scheme exists in provenance URL parsing and is non-executing.

## Required Checks
- collectors remain transport-agnostic: PASSED_WITH_ADVISORY
- no hardcoded adb paths in collectors: PASSED
- no direct COM access from AURA runtime: PASSED
- failures preserve UNKNOWN: CODE_PATH_PRESENT, RUNTIME_NOT_EXECUTED
- evidence logging deterministic: CODE_PATH_PRESENT, RUNTIME_NOT_EXECUTED

## Advisory Limits
- Pattern-based scanning only.
- No live distributed endpoint execution in this pass.
