# Prompt: Fix LPASS LPI Pinctrl Deferred Probe on Eliza EVK

## Objective

Fix the deferred probe chain that prevents the entire audio subsystem from
probing on Eliza EVK.  The root cause is a missing `lpass_tlmm` pinctrl node
(and its `q6prmcc` clock-controller dependency) in `eliza.dtsi`.

This is a **DTS-only fix**.  No C source files are modified.
All generated patch artifacts go under `AURA_KB/` only.

---

## AURA Governance Invariants

| Principle    | Enforcement |
|---|---|
| BOUNDED      | Read only the allowed sources listed below. |
| OBSERVABLE   | Every DTS property added must map to a logged root-cause item. |
| EXPLAINABLE  | Each node/property must cite the reference file and line. |
| REPLAYABLE   | Deterministic JSON + DTS patch artifacts only. |
| INTERRUPTIBLE| If any reference is missing, stop and record BLOCKED. |
| REVERSIBLE   | Audit/patch artifacts only; no kernel source tree modification. |

---

## Allowed Sources

### Root-cause artifact (read first)
- `AURA_KB/platform_issues/lpass_lpi_pinctrl_deferred_probe/root_cause_analysis.json`

### Eliza target DTS (read-only reference)
- `track_b_corpora/linux-next/arch/arm64/boot/dts/qcom/eliza.dtsi`
- `track_b_corpora/linux-next/arch/arm64/boot/dts/qcom/eliza-cqs-evk.dtsi`
  (if present)

### Reference upstream DTS (read-only, for node patterns)
- `track_b_corpora/linux-next/arch/arm64/boot/dts/qcom/sm8750.dtsi`
  — `lpass_tlmm: pinctrl@7760000` at line ~2588
  — `remoteproc_adsp` glink-edge → gpr → q6apm/q6prm hierarchy at line ~2214
- `track_b_corpora/linux-next/arch/arm64/boot/dts/qcom/milos.dtsi`
  — `lpass_tlmm: pinctrl@3440000` at line ~1484

### Reference upstream driver (read-only, for clock binding)
- `track_b_corpora/linux-next/drivers/pinctrl/qcom/pinctrl-lpass-lpi.c`
  — `of_pm_clk_add_clks()` call at line ~538
  — `clock-names` binding: `"core"` and `"audio"`

---

## Forbidden Actions

- Do NOT modify any file outside `AURA_KB/`.
- Do NOT modify kernel source tree.
- Do NOT generate C patches.
- Do NOT claim runtime audio works.
- Do NOT address the unrelated `gcc-eliza sync_state pending due to crypto` message.

---

## Background: Root Cause Summary

The deferred probe chain (from `root_cause_analysis.json`):

```
7760000.pinctrl  FAILS  (qcom-milos-lpass-lpi-pinctrl: Failed to get clk 'core')
  → 7660000.codec (VA macro) blocked
    → 6b00000.codec (WSA), 6ae0000.codec (TX), 6ac0000.codec (RX) blocked
      → 6ad0000.soundwire (RX SWR), 7630000.soundwire (TX SWR),
        6b10000.soundwire (WSA SWR) blocked
          → sound card fails: "VA Capture: error getting cpu dai name"
```

**Direct cause:** `eliza.dtsi` has no `lpass_tlmm: pinctrl@7760000` node.
The driver `pinctrl-lpass-lpi.c:538` calls `of_pm_clk_add_clks(dev)` which
reads the `clocks` property from DTS.  When the property is absent the call
returns `-ENODEV`, which is treated as a deferred probe trigger.

**Dependency cause:** `lpass_tlmm` needs `&q6prmcc` as its clock provider.
`q6prmcc` lives inside the `gpr → q6prm: service@2` hierarchy under
`remoteproc_adsp → glink-edge`.  In `eliza.dtsi` the `glink-edge` node is a
stub with no `gpr` / `q6apm` / `q6prm` children.

---

## Task 1: Read and Confirm Reference Nodes

Before generating any patch, read and record:

1. From `sm8750.dtsi` lines ~2214–2360:
   - Full `remoteproc_adsp → glink-edge → gpr → q6apm` hierarchy
   - Full `q6prm: service@2 → q6prmcc` node

2. From `sm8750.dtsi` lines ~2588–2710:
   - Full `lpass_tlmm: pinctrl@7760000` node including all pinctrl states:
     `tx_swr_active`, `rx_swr_active`, `dmic01_default`, `dmic23_default`,
     `wsa_swr_active`, `wsa2_swr_active`

3. From `eliza.dtsi` lines ~1971–2020:
   - Existing `remoteproc_adsp: remoteproc@3000000` node and its `glink-edge`
     stub (confirm it has no `gpr` children)

Record findings in:
`AURA_KB/platform_issues/lpass_lpi_pinctrl_deferred_probe/reference_node_inventory.json`

Schema per entry:
```json
{
  "node_label": "...",
  "source_file": "...",
  "source_line": 0,
  "address": "0x...",
  "compatible": "...",
  "present_in_eliza": true,
  "action_required": "ADD | EXTEND | NONE"
}
```

---

## Task 2: Generate DTS Patch Artifact

Create:
`AURA_KB/platform_issues/lpass_lpi_pinctrl_deferred_probe/eliza_lpass_lpi_fix.patch`

The patch must be a standard unified-diff (`diff -u`) style patch against
`track_b_corpora/linux-next/arch/arm64/boot/dts/qcom/eliza.dtsi`.

### Change A — Extend `remoteproc_adsp` glink-edge with GPR/APM/PRM hierarchy

Inside the existing `glink-edge` node of `remoteproc_adsp: remoteproc@3000000`,
add the following (modelled exactly on `sm8750.dtsi` lines 2295–2360,
substituting Eliza-specific iommu/smmu values where they differ):

```dts
			glink-edge {
				/* ... existing properties unchanged ... */

				gpr {
					compatible = "qcom,gpr";
					qcom,glink-channels = "adsp_apps";
					qcom,domain = <GPR_DOMAIN_ID_ADSP>;
					qcom,intents = <512 20>;
					#address-cells = <1>;
					#size-cells = <0>;

					q6apm: service@1 {
						compatible = "qcom,q6apm";
						reg = <GPR_APM_MODULE_IID>;
						#sound-dai-cells = <0>;
						qcom,protection-domain = "avs/audio",
									 "msm/adsp/audio_pd";

						q6apmbedai: bedais {
							compatible = "qcom,q6apm-lpass-dais";
							#sound-dai-cells = <1>;
						};

						q6apmdai: dais {
							compatible = "qcom,q6apm-dais";
							iommus = <&apps_smmu 0x1001 0x80>,
								 <&apps_smmu 0x1041 0x20>;
						};
					};

					q6prm: service@2 {
						compatible = "qcom,q6prm";
						reg = <GPR_PRM_MODULE_IID>;
						qcom,protection-domain = "avs/audio",
									 "msm/adsp/audio_pd";

						q6prmcc: clock-controller {
							compatible = "qcom,q6prm-lpass-clocks";
							#clock-cells = <2>;
						};
					};
				};
			};
```

**Note on iommus:** Use the same values as `sm8750.dtsi` (`0x1001/0x80`,
`0x1041/0x20`) as a starting point.  Record in the validation checklist that
these must be confirmed against Eliza SMMU mapping before board submission.

### Change B — Add `lpass_tlmm` pinctrl node

Add the following as a new top-level `soc` child node in `eliza.dtsi`,
immediately after the `lpass_lpicx_noc` interconnect node (around line 2035):

```dts
		lpass_tlmm: pinctrl@7760000 {
			compatible = "qcom,sm8750-lpass-lpi-pinctrl",
				     "qcom,sm8650-lpass-lpi-pinctrl";
			reg = <0x0 0x07760000 0x0 0x20000>;

			clocks = <&q6prmcc LPASS_HW_MACRO_VOTE LPASS_CLK_ATTRIBUTE_COUPLE_NO>,
				 <&q6prmcc LPASS_HW_DCODEC_VOTE LPASS_CLK_ATTRIBUTE_COUPLE_NO>;
			clock-names = "core", "audio";

			gpio-controller;
			#gpio-cells = <2>;
			gpio-ranges = <&lpass_tlmm 0 0 23>;

			tx_swr_active: tx-swr-active-state {
				clk-pins {
					pins = "gpio0";
					function = "swr_tx_clk";
					drive-strength = <2>;
					slew-rate = <1>;
					bias-disable;
				};

				data-pins {
					pins = "gpio1", "gpio2", "gpio14";
					function = "swr_tx_data";
					drive-strength = <2>;
					slew-rate = <1>;
					bias-bus-hold;
				};
			};

			rx_swr_active: rx-swr-active-state {
				clk-pins {
					pins = "gpio3";
					function = "swr_rx_clk";
					drive-strength = <2>;
					slew-rate = <1>;
					bias-disable;
				};

				data-pins {
					pins = "gpio4", "gpio5";
					function = "swr_rx_data";
					drive-strength = <2>;
					slew-rate = <1>;
					bias-bus-hold;
				};
			};

			dmic01_default: dmic01-default-state {
				clk-pins {
					pins = "gpio6";
					function = "dmic1_clk";
					drive-strength = <8>;
					output-high;
				};

				data-pins {
					pins = "gpio7";
					function = "dmic1_data";
					drive-strength = <8>;
					input-enable;
				};
			};

			dmic23_default: dmic23-default-state {
				clk-pins {
					pins = "gpio8";
					function = "dmic2_clk";
					drive-strength = <8>;
					output-high;
				};

				data-pins {
					pins = "gpio9";
					function = "dmic2_data";
					drive-strength = <8>;
					input-enable;
				};
			};

			wsa_swr_active: wsa-swr-active-state {
				clk-pins {
					pins = "gpio10";
					function = "wsa_swr_clk";
					drive-strength = <2>;
					slew-rate = <1>;
					bias-disable;
				};

				data-pins {
					pins = "gpio11";
					function = "wsa_swr_data";
					drive-strength = <2>;
					slew-rate = <1>;
					bias-bus-hold;
				};
			};

			wsa2_swr_active: wsa2-swr-active-state {
				clk-pins {
					pins = "gpio15";
					function = "wsa2_swr_clk";
					drive-strength = <2>;
					slew-rate = <1>;
					bias-disable;
				};

				data-pins {
					pins = "gpio16";
					function = "wsa2_swr_data";
					drive-strength = <2>;
					slew-rate = <1>;
					bias-bus-hold;
				};
			};
		};
```

**Note on compatible string:** `qcom,sm8750-lpass-lpi-pinctrl` is used as the
primary compatible because Eliza shares the same address (`0x7760000`) and
pin count (23) as SM8750.  If Eliza requires a dedicated compatible string
(`qcom,eliza-lpass-lpi-pinctrl`), that must be added to the driver's
`of_match_table` — record this as a PENDING_DRIVER_DECISION in the checklist.

### Change C — Wire pinctrl-0 references in existing audio nodes

In `eliza.dtsi` (or `eliza-evk.dtsi` if the audio nodes live there), add
`pinctrl-0` and `pinctrl-names` references to the SoundWire master nodes that
were previously blocked:

For `swr1` (RX SWR master at `0x6ad0000`):
```dts
			pinctrl-names = "default";
			pinctrl-0 = <&rx_swr_active>;
```

For `swr2` (TX SWR master at `0x7630000`):
```dts
			pinctrl-names = "default";
			pinctrl-0 = <&tx_swr_active>;
```

For `swr3` (WSA SWR master at `0x6b10000`, if present):
```dts
			pinctrl-names = "default";
			pinctrl-0 = <&wsa_swr_active>;
```

---

## Task 3: Validation Checklist JSON

Create:
`AURA_KB/platform_issues/lpass_lpi_pinctrl_deferred_probe/fix_validation_checklist.json`

Each item:
```json
{
  "id": "LPI-FIX-CHK-001",
  "check": "...",
  "rationale": "...",
  "status": "PASS | FAIL | PENDING_BOARD | PENDING_DRIVER_DECISION",
  "evidence": "..."
}
```

Required checks:

| ID | Check |
|---|---|
| LPI-FIX-CHK-001 | `lpass_tlmm` node address `0x7760000` matches boot log `7760000.pinctrl` |
| LPI-FIX-CHK-002 | `clock-names = "core", "audio"` matches `pinctrl-lpass-lpi.c` binding |
| LPI-FIX-CHK-003 | `q6prmcc` is defined before `lpass_tlmm` in DTS parse order |
| LPI-FIX-CHK-004 | `gpio-ranges = <&lpass_tlmm 0 0 23>` — 23 pins matches SM8750/milos |
| LPI-FIX-CHK-005 | `tx_swr_active` pins (gpio0/1/2/14) match eliza-evk.dtsi pinctrl from bring-up notes |
| LPI-FIX-CHK-006 | `rx_swr_active` pins (gpio3/4/5) match eliza-evk.dtsi pinctrl from bring-up notes |
| LPI-FIX-CHK-007 | `compatible = "qcom,sm8750-lpass-lpi-pinctrl"` is in driver `of_match_table` |
| LPI-FIX-CHK-008 | iommus for `q6apmdai` confirmed against Eliza SMMU mapping (PENDING_BOARD) |
| LPI-FIX-CHK-009 | `swr1`/`swr2`/`swr3` pinctrl-0 references resolve to correct state nodes |
| LPI-FIX-CHK-010 | After fix: `7760000.pinctrl` probe succeeds (PENDING_BOARD) |
| LPI-FIX-CHK-011 | After fix: `7660000.codec` (VA macro) probe succeeds (PENDING_BOARD) |
| LPI-FIX-CHK-012 | After fix: sound card instantiates without "VA Capture: error" (PENDING_BOARD) |
| LPI-FIX-CHK-013 | `gcc-eliza sync_state pending due to crypto` is NOT addressed by this fix |

---

## Task 4: PM Summary

Create:
`AURA_KB/platform_issues/lpass_lpi_pinctrl_deferred_probe/pm_fix_summary.md`

Answer:
1. What is the root cause?
2. What does this patch fix?
3. What does this patch NOT fix?
4. What must be confirmed on board before upstreaming?
5. Is this fix safe to apply to the bring-up DTS now?
6. What is the upstream submission path for this fix?
7. What is the recommended next human action?

---

## Task 5: Commit and Push

```bash
git add AURA_KB/platform_issues/lpass_lpi_pinctrl_deferred_probe/
git commit -m "feat(kb): generate LPASS LPI pinctrl deferred probe DTS fix for Eliza EVK"
git push origin aura_upstream_learning
git status --short
```

---

## Success Criteria

- [ ] `reference_node_inventory.json` — parse-valid, all 3 nodes inventoried
- [ ] `eliza_lpass_lpi_fix.patch` — unified-diff format, covers Changes A/B/C
- [ ] `fix_validation_checklist.json` — parse-valid, all 13 checks present
- [ ] `pm_fix_summary.md` — answers all 7 questions
- [ ] No kernel source files modified
- [ ] `AURA/Makefile` NOT staged or committed
- [ ] All JSON artifacts pass `python3 -m json.tool`
- [ ] git push to `origin/aura_upstream_learning` succeeds
