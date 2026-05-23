# RB3 Controlled Runtime Procedural Validation

## Scope
RB3Gen2 only. No multi-board expansion.

## Runtime workflow phases
1. pre-runtime snapshot (`/proc/asound`, tinymix/amixer, dapm/debugfs, dmesg)
2. approved asset deployment (`AURA_ADB_PUSH ...`)
3. approved mixer sequencing (`AURA_TINYMIX_SET` / `AURA_AMIXER_CSET`)
4. approved PCM playback (`AURA_PLAYBACK_APLAY`)
5. post-runtime snapshot and correlation
6. approved cleanup (`AURA_ADB_RM`)

## Governance
- Linux approves and sequences operations.
- Windows executes only approved canonical wrappers.
- write operations require:
  - `--allow-write-ops`
  - `--execution-mode governed_write_approved`
  - Windows worker `-EnableAssetPush`
- fail-closed rejection on malformed wrappers or invalid targets.

## Execution entrypoints
- Linux dry-run:
  - `python3 AURA/scripts/rb3-runtime-procedural-playback.py`
- Linux live controlled run:
  - `python3 AURA/scripts/rb3-runtime-procedural-playback.py --live-run --timeout-seconds 30`
- Windows worker (write wrappers enabled):
  - `pwsh -ExecutionPolicy Bypass -File <repo>\\AURA\\scripts\\windows-bridge-worker.ps1 -BridgeRoot <bridge> -UseAdbShell -EnableAssetPush -AdbPath \"C:\\adb_tool\\platform-tools\\adb.exe\" -AdbSerial <serial> -LiveTrace`

## Evidence-driven outcomes
- runtime state machine classification is evidence-based
- unsupported/missing telemetry remains advisory
- no parity/equivalence/merge-readiness claims
