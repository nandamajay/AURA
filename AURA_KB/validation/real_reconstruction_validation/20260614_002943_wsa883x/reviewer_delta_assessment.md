# Reviewer Delta Assessment - Simulated Response to Major Deltas

## Major deltas assessed
1. SWR->SDW ownership conversion
2. Probe simplification and removal of vendor diagnostics/notifier paths
3. Runtime PM autosuspend + timeout-safe resume behavior
4. DAPM simplification and kcontrol semantics
5. DT schema shape (`port-mapping`, `powerdown-gpios`/`reset-gpios`)
6. Patch decomposition strategy (AURA 6-patch vs historical 4+revision)

| Delta | Mark Brown | Pierre-Louis Bossart | Krzysztof Kozlowski | Vinod Koul | Bjorn Andersson |
|---|---|---|---|---|---|
| SWR->SDW conversion | Likely acceptance if ASoC interfaces remain idiomatic; may ask for cleaner naming | Likely strong acceptance; will inspect callback/state correctness | Neutral unless DT implications change | Likely acceptance; may ask SoundWire layering questions | Neutral/medium, may ask Qualcomm integration clarity |
| Probe simplification | Likely acceptance (focused patch scope) | Likely acceptance if no lifecycle regressions | Neutral | Neutral | Likely acceptance if platform assumptions removed |
| Runtime PM model | Accept if callbacks are minimal and correct | Likely objection if resume timeout/path robustness missing; request explicit safety | Neutral | Neutral | Neutral |
| DAPM + control behavior | High chance of objections on put-callback semantics and control naming if wrong | Medium scrutiny on event ordering side effects | Neutral | Neutral | Neutral |
| DT schema updates | Low direct objection unless schema impacts audio behavior descriptions | Low-medium if property semantics affect runtime behavior | High scrutiny; likely request strict schema constraints and property clarity | Low | Medium for Qualcomm DT conventions |
| 6-patch decomposition | Likely ask to reduce patch churn or reorder for review flow if too fragmented | Medium: may prefer PM fixes close to affected code | Medium: prefers DT patch sequencing discipline | Low-medium | Low-medium |

## Reviewer-specific likely requested changes
- Mark Brown:
  - enforce `put` callback change semantics and control naming style.
  - Evidence: `/AURA_KB/review_database/mark_brown/controls/wsa883x.md:5-12`
- Pierre-Louis Bossart:
  - require runtime resume timeout-safe behavior before regcache sync.
  - may question fragile callback conditions.
  - Evidence: `/AURA_KB/review_database/pierre_bossart/runtime_pm/wsa883x.md:5-6`, `/AURA_KB/review_database/pierre_bossart/soundwire/wsa883x.md:5-6`
- Krzysztof Kozlowski:
  - likely DT schema strictness asks; direct wsa883x comment evidence is partial.
  - Evidence: `/AURA_KB/review_database/krzysztof_kozlowski/dt/wsa883x.md:3-6`
- Vinod Koul, Bjorn Andersson:
  - per-driver direct evidence insufficient; predictions are low-confidence.
  - Evidence: `/AURA_KB/multi_driver_evidence_report.md:6-10`

