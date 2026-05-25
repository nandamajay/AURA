# Compile Closure Status

- closure_state: **NOT_CLOSED**
- reason: kernel source tree in patch-proposal worktree is not prepared for build/analysis targets.

## Evidence
- sparse exit `2` with missing autoconf/include config
- clang exit `2` with same missing generated config
- compile_scope exit `2` with same missing generated config
- dt_binding_check exit `2` due missing dt-doc-validate

## Truthful Classification
- compile-ready patch group count: 0
- advisory-only patch group count: 5
- blocked patch group count: 1
- upstream merge readiness: **not established**
