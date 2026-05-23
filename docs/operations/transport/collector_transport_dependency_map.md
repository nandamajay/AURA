# Collector Transport Dependency Map

## Status
- phase: T5 + W3
- result: PASSED_WITH_ADVISORY
- date: 2026-05-20

## Scan Scope
- root: `AURA`
- excluded: `AURA/workspace/aura-sdk/src/aura_sdk/transport`
- patterns: `adb`, `ssh`, `ttyUSB`, `serial`, `pyserial`, `COM[0-9]`, `tinymix`, `tinyplay`, `tinycap`

## Findings
- No collector-named modules detected by filename search.
- No hardcoded transport execution patterns detected outside transport adapters.
- One non-executing `ssh` scheme reference exists in provenance URL parsing.

## Interpretation
- Current codebase remains transport-abstraction friendly.
- Collectors can use dispatcher-only contract.

## Advisory Limits
- Pattern-based static scan only.
- Runtime-side collector behavior not validated in live execution.
