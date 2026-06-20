# WCD Family Conversion Checklist

## 1. Input package requirements
- [ ] LA donor source paths are explicit and complete.
- [ ] LE reference paths are explicit and complete.
- [ ] Runtime evidence package status is declared (available vs missing).
- [ ] Prior blocker and PM artifacts are attached.

## 2. LA vs LE terminology
- [ ] Use `LA` for downstream/Linux Android and `LE` for upstream/Linux Embedded consistently.
- [ ] Avoid mixing vendor naming with LE naming in conclusions.

## 3. Source allowlist and hidden-target rules
- [ ] Allowed sources are declared before work starts.
- [ ] Hidden LE target files remain inaccessible until scoring stage (for transfer experiments).
- [ ] Any allowlist deviation is recorded as FAIL_CLOSED.

## 4. Conversion mode selection
- [ ] Select mode explicitly (`BLIND_TRANSFORMATION`, `SKELETON_INFORMED`, `PRODUCTION_NEW_DRIVER`, `HYBRID`).
- [ ] Justify mode with blocker/evidence state.
- [ ] Runtime-sensitive unresolved areas force fail-closed mode constraints.

## 5. Upstream architecture reuse rules
- [ ] Prefer LE split architecture (main codec + SDW transport + shared libraries).
- [ ] Use LE lifecycle patterns for probe/bind/remove and component registration.
- [ ] Keep Kconfig/Makefile integration aligned with LE family pattern.

## 6. SoundWire checks
- [ ] Preserve LE RX/TX structure and transport split.
- [ ] Do not infer SDW numeric identity from sibling codecs.
- [ ] Require runtime logs for identity tuple and paging/controller proof.

## 7. Regmap/regcache checks
- [ ] Apply LE regcache lifecycle pattern (cache-only early; sync on attach/resume).
- [ ] Do not claim paging correctness from static regmap code alone.
- [ ] Track cache/restore assumptions as runtime-sensitive.

## 8. MBHC/Class-H checks
- [ ] Reuse shared LE MBHC/Class-H frameworks where applicable.
- [ ] Keep codec-specific Class-H base/version choices fail-closed without hardware traces.
- [ ] Do not claim audio path correctness from static Class-H mapping.

## 9. DAPM/control/route checks
- [ ] Map widgets/routes/controls with explicit LA source -> LE structure rationale.
- [ ] Avoid name-only cloning.
- [ ] Attach anti-copy verifier output for DAPM-heavy conversions.

## 10. DTS/schema/schematic checks
- [ ] Normalize LA DT properties to LE schema names.
- [ ] Document dropped or transformed properties.
- [ ] Keep board schematic/runtime proof separate from schema normalization completion.

## 11. Runtime evidence gating
- [ ] Maintain runtime blocker register with explicit evidence IDs.
- [ ] Block runtime claims until required hardware logs/traces are present.
- [ ] Require PM non-claims section when blockers remain.

## 12. Anti-copy/anti-derivation checks
- [ ] Run verifier derivation checks for LE references, LE targets, and LA donors.
- [ ] Treat downstream derivation warnings as governance risk, not informational noise.
- [ ] Escalate similarity warnings to PM review before promotion.

## 13. Vendor-elimination checks
- [ ] Remove vendor-only includes/APIs/wrappers unless LE equivalent exists.
- [ ] Provide replacement mapping table for each removed symbol.
- [ ] Gate fails if vendor-elimination materially regresses.

## 14. Compile/checkpatch/gate requirements
- [ ] Compile result is recorded honestly (`PASS`, `FAIL`, or environment-not-run).
- [ ] Checkpatch output is captured and classified.
- [ ] Canonical gate verdict artifact is present and used as source of truth.
- [ ] Lineage coverage is recorded and above threshold.

## 15. PM verdict vocabulary
- [ ] Use explicit PM verdict tokens and avoid ambiguous prose-only conclusions.
- [ ] Include: what improved, what regressed, what remains fail-closed, and what must not be claimed.
- [ ] Distinguish static quality gains from runtime readiness.
