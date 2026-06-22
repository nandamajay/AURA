# Prompt: Generate LPASS LPI Pinctrl Deferred Probe DTS Fix Patch for Eliza EVK

## Objective

Generate a concrete, apply-ready unified-diff DTS patch that fixes the
deferred probe chain blocking the entire audio subsystem on Eliza EVK.

The patch targets:
  `track_b_corpora/linux-next/arch/arm64/boot/dts/qcom/eliza.dtsi`

All output artifacts go under `AURA_KB/platform_issues/lpass_lpi_pinctrl_deferred_probe/`.
No kernel source tree files are modified.

---

## AURA Governance Invariants

| Principle    | Enforcement |
|---|---|
| BOUNDED      | Read only the allowed sources listed below. |
| OBSERVABLE   | Every DTS property added maps to a root-cause item in `root_cause_analysis.json`. |
| EXPLAINABLE  | Each node/property cites the reference file and line number. |
| REPLAYABLE   | Deterministic unified-diff patch + JSON artifacts only. |
| INTERRUPTIBLE| If any reference lookup fails, record BLOCKED and stop. |
| REVERSIBLE   | KB artifacts only; no kernel source tree modification. |

---

## Allowed Sources

| Source | Purpose |
|---|---|
| `AURA_KB/platform_issues/lpass_lpi_pinctrl_deferred_probe/root_cause_analysis.json` | Root cause — read first |
| `track_b_corpora/linux-next/arch/arm64/boot/dts/qcom/eliza.dtsi` | Patch target — read-only reference |
| `track_b_corpora/linux-next/arch/arm64/boot/dts/qcom/sm8750.dtsi` | Node patterns reference |
| `track_b_corpora/linux-next/drivers/pinctrl/qcom/pinctrl-lpass-lpi.c` | Clock binding verification |

---

## Forbidden Actions

- Do NOT modify any file outside `AURA_KB/`.
- Do NOT modify the kernel source tree.
- Do NOT generate C source patches.
- Do NOT claim runtime audio works after this fix.
- Do NOT address `gcc-eliza sync_state pending due to crypto` (unrelated).
- Do NOT commit `AURA/Makefile` (pre-existing dirty file — never stage it).

---

## Root Cause Summary (from `root_cause_analysis.json`)

```
7760000.pinctrl  FAILS  → "qcom-milos-lpass-lpi-pinctrl: Failed to get clk 'core'"
  Cause: eliza.dtsi has no lpass_tlmm node → driver calls of_pm_clk_add_clks()
         → reads 'clocks' DTS property → absent → returns -ENODEV → deferred probe

  Cascade:
    7760000.pinctrl FAILS
      → 7660000.codec (VA macro) blocked
        → 6b00000.codec (WSA), 6ae0000.codec (TX), 6ac0000.codec (RX) blocked
          → 6ad0000.soundwire (RX SWR), 7630000.soundwire (TX SWR),
            6b10000.soundwire (WSA SWR) blocked
              → sound card: "VA Capture: error getting cpu dai name"

  Dependency: lpass_tlmm needs &q6prmcc as clock provider.
              q6prmcc lives inside remoteproc_adsp → glink-edge → gpr → q6prm.
              eliza.dtsi glink-edge is a stub with no gpr/q6apm/q6prm children.
```

---

## Task 1: Read Reference Nodes and Record Inventory

Read the following from `sm8750.dtsi` and record exact line numbers:

1. `remoteproc_adsp` glink-edge → gpr → q6apm + q6prm hierarchy
   (sm8750.dtsi lines ~2251–2360)
2. `lpass_tlmm: pinctrl@7760000` full node with all pinctrl states
   (sm8750.dtsi lines ~2588–2710)

Read from `eliza.dtsi`:
3. `remoteproc_adsp: remoteproc@3000000` glink-edge stub
   (eliza.dtsi lines ~2008–2019)
4. `lpass_lpicx_noc: interconnect@7420000` — insertion point for lpass_tlmm
   (eliza.dtsi lines ~2027–2033)

Read from `pinctrl-lpass-lpi.c`:
5. `of_pm_clk_add_clks()` call and clock-names binding
   (lines ~530–545)

Create:
`AURA_KB/platform_issues/lpass_lpi_pinctrl_deferred_probe/reference_node_inventory.json`

Schema:
```json
[
  {
    "node_label": "string",
    "source_file": "string",
    "source_line_start": 0,
    "source_line_end": 0,
    "address": "0x...",
    "compatible": "string",
    "present_in_eliza_dtsi": false,
    "action_required": "ADD | EXTEND | VERIFY | NONE",
    "notes": "string"
  }
]
```

---

## Task 2: Generate the Unified-Diff Patch

Create:
`AURA_KB/platform_issues/lpass_lpi_pinctrl_deferred_probe/eliza_lpass_lpi_fix.patch`

The patch must be a valid unified-diff against
`track_b_corpora/linux-next/arch/arm64/boot/dts/qcom/eliza.dtsi`.

Use this header format:
```
--- a/arch/arm64/boot/dts/qcom/eliza.dtsi
+++ b/arch/arm64/boot/dts/qcom/eliza.dtsi
```

### Hunk 1 — Extend glink-edge with GPR / Q6APM / Q6PRM hierarchy

Context: the existing `glink-edge` stub inside `remoteproc_adsp: remoteproc@3000000`
(eliza.dtsi ~line 2008).

Replace the closing `};` of the stub glink-edge with the full hierarchy:

```dts
		glink-edge {
			interrupts-extended = <&ipcc IPCC_CLIENT_LPASS
						     IPCC_MPROC_SIGNAL_GLINK_QMP
						     IRQ_TYPE_EDGE_RISING>;
			mboxes = <&ipcc IPCC_CLIENT_LPASS
					IPCC_MPROC_SIGNAL_GLINK_QMP>;

			label = "lpass";
			qcom,remote-pid = <2>;

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

Reference: `sm8750.dtsi` lines 2251–2360.

### Hunk 2 — Add lpass_tlmm pinctrl node

Insert after the closing `};` of `lpass_lpicx_noc: interconnect@7420000`
(eliza.dtsi ~line 2033), before `sdhc_2: mmc@8804000`:

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

Reference: `sm8750.dtsi` lines 2588–2710.

**Note on compatible:** `qcom,sm8750-lpass-lpi-pinctrl` is used as primary
because Eliza shares address `0x7760000` and 23-pin count with SM8750.
Record as `PENDING_DRIVER_DECISION` in checklist if a dedicated
`qcom,eliza-lpass-lpi-pinctrl` is required.

**Note on pinctrl states:** `tx_swr_active` pins (gpio0/1/2/14) and
`rx_swr_active` pins (gpio3/4/5) are confirmed from the Eliza EVK bring-up
notes (TX SWR pinctrl and RX SWR pinctrl sections).

### Hunk 3 — Add pinctrl-0 to SoundWire master nodes

The SoundWire master nodes (`swr1` at `0x6ad0000`, `swr2` at `0x7630000`,
`swr3` at `0x6b10000`) are **not yet present in upstream eliza.dtsi** — they
are part of the bring-up additions.

For this hunk, generate a **separate note file** rather than a patch hunk,
because the SWR nodes do not exist in the upstream eliza.dtsi to patch against.

Create:
`AURA_KB/platform_issues/lpass_lpi_pinctrl_deferred_probe/swr_pinctrl_note.md`

Document:
- When `swr1` (RX, `0x6ad0000`) is added to eliza.dtsi, it must include:
  ```dts
  pinctrl-names = "default";
  pinctrl-0 = <&rx_swr_active>;
  ```
- When `swr2` (TX, `0x7630000`) is added to eliza.dtsi, it must include:
  ```dts
  pinctrl-names = "default";
  pinctrl-0 = <&tx_swr_active>;
  ```
- When `swr3` (WSA, `0x6b10000`) is added to eliza.dtsi, it must include:
  ```dts
  pinctrl-names = "default";
  pinctrl-0 = <&wsa_swr_active>;
  ```
- Reference: `sm8750.dtsi` lines 2434, 2387, 2498.

---

## Task 3: Validation Checklist JSON

Create:
`AURA_KB/platform_issues/lpass_lpi_pinctrl_deferred_probe/fix_validation_checklist.json`

```json
[
  {
    "id": "LPI-FIX-CHK-001",
    "check": "lpass_tlmm node address 0x7760000 matches boot log '7760000.pinctrl'",
    "rationale": "Address in DTS must match what the kernel reports in deferred probe log",
    "status": "PASS",
    "evidence": "Boot log: '7760000.pinctrl: Failed to get clk core'; sm8750.dtsi:2588 reg=0x07760000"
  },
  {
    "id": "LPI-FIX-CHK-002",
    "check": "clock-names = 'core', 'audio' matches pinctrl-lpass-lpi.c binding",
    "rationale": "Driver calls of_pm_clk_add_clks() which reads clock-names; 'core' is the first required name",
    "status": "PASS",
    "evidence": "pinctrl-lpass-lpi.c ~line 538; sm8750.dtsi:2594 clock-names = 'core', 'audio'"
  },
  {
    "id": "LPI-FIX-CHK-003",
    "check": "q6prmcc is defined (inside gpr/q6prm) before lpass_tlmm in DTS parse order",
    "rationale": "lpass_tlmm clocks = <&q6prmcc ...> requires q6prmcc phandle to be resolved",
    "status": "PASS",
    "evidence": "Hunk 1 adds q6prmcc inside remoteproc_adsp at ~line 2019; Hunk 2 adds lpass_tlmm at ~line 2034 — q6prmcc appears first"
  },
  {
    "id": "LPI-FIX-CHK-004",
    "check": "gpio-ranges = <&lpass_tlmm 0 0 23> — 23 pins matches SM8750 and milos",
    "rationale": "Pin count must match the SoC's LPASS LPI GPIO bank size",
    "status": "PASS",
    "evidence": "sm8750.dtsi:2599 gpio-ranges = <&lpass_tlmm 0 0 23>; milos.dtsi same"
  },
  {
    "id": "LPI-FIX-CHK-005",
    "check": "tx_swr_active pins (gpio0/1/2/14) match Eliza EVK bring-up pinctrl notes",
    "rationale": "TX SWR CLK=gpio0, DATA0=gpio1, DATA1=gpio2, DATA2=gpio14 per bring-up notes",
    "status": "PASS",
    "evidence": "Eliza EVK bring-up notes: TX SWR pinctrl section; sm8750.dtsi:2601 identical"
  },
  {
    "id": "LPI-FIX-CHK-006",
    "check": "rx_swr_active pins (gpio3/4/5) match Eliza EVK bring-up pinctrl notes",
    "rationale": "RX SWR CLK=gpio3, DATA0=gpio4, DATA1=gpio5 per bring-up notes",
    "status": "PASS",
    "evidence": "Eliza EVK bring-up notes: RX SWR pinctrl section; sm8750.dtsi:2619 identical"
  },
  {
    "id": "LPI-FIX-CHK-007",
    "check": "compatible 'qcom,sm8750-lpass-lpi-pinctrl' is in driver of_match_table",
    "rationale": "Driver must match the compatible string or probe will fail with -ENODEV",
    "status": "PASS",
    "evidence": "pinctrl-lpass-lpi.c of_match_table contains qcom,sm8750-lpass-lpi-pinctrl"
  },
  {
    "id": "LPI-FIX-CHK-008",
    "check": "iommus for q6apmdai confirmed against Eliza SMMU mapping",
    "rationale": "SMMU stream IDs are SoC-specific; values copied from sm8750 need board confirmation",
    "status": "PENDING_BOARD",
    "evidence": "Used sm8750.dtsi values (0x1001/0x80, 0x1041/0x20) as starting point"
  },
  {
    "id": "LPI-FIX-CHK-009",
    "check": "swr1/swr2/swr3 pinctrl-0 references documented in swr_pinctrl_note.md",
    "rationale": "SWR nodes not yet in upstream eliza.dtsi; pinctrl-0 must be added when nodes are upstreamed",
    "status": "PASS",
    "evidence": "swr_pinctrl_note.md created with per-node instructions"
  },
  {
    "id": "LPI-FIX-CHK-010",
    "check": "After fix: 7760000.pinctrl probe succeeds (no 'Failed to get clk core')",
    "rationale": "Primary fix target — pinctrl node must probe cleanly",
    "status": "PENDING_BOARD",
    "evidence": "Requires board re-test on Monday"
  },
  {
    "id": "LPI-FIX-CHK-011",
    "check": "After fix: 7660000.codec (VA macro) probe succeeds",
    "rationale": "VA macro is the first downstream dependent of lpass_tlmm",
    "status": "PENDING_BOARD",
    "evidence": "Requires board re-test on Monday"
  },
  {
    "id": "LPI-FIX-CHK-012",
    "check": "After fix: sound card instantiates without 'VA Capture: error getting cpu dai name'",
    "rationale": "Sound card failure is the end symptom of the full deferred probe chain",
    "status": "PENDING_BOARD",
    "evidence": "Requires board re-test on Monday"
  },
  {
    "id": "LPI-FIX-CHK-013",
    "check": "gcc-eliza sync_state pending due to crypto is NOT addressed by this fix",
    "rationale": "Crypto sync_state is an unrelated GCC clock controller issue",
    "status": "PASS",
    "evidence": "Patch contains no changes to GCC or crypto nodes"
  }
]
```

---

## Task 4: PM Summary

Create:
`AURA_KB/platform_issues/lpass_lpi_pinctrl_deferred_probe/pm_fix_summary.md`

Answer all seven questions:

1. **What is the root cause?**
   Missing `lpass_tlmm: pinctrl@7760000` node in `eliza.dtsi`. The
   `pinctrl-lpass-lpi` driver calls `of_pm_clk_add_clks()` at probe time,
   which reads the `clocks` DTS property. When the node is absent the entire
   audio deferred probe chain stalls.

2. **What does this patch fix?**
   - Adds `q6prmcc` clock-controller (inside `gpr → q6prm`) to the
     `remoteproc_adsp` glink-edge, unblocking the `&q6prmcc` phandle reference.
   - Adds `lpass_tlmm: pinctrl@7760000` with correct `clocks`, `clock-names`,
     `gpio-controller`, `gpio-ranges`, and all six pinctrl states needed by
     the audio subsystem (`tx_swr_active`, `rx_swr_active`, `dmic01_default`,
     `dmic23_default`, `wsa_swr_active`, `wsa2_swr_active`).

3. **What does this patch NOT fix?**
   - Does not add the SoundWire master nodes (`swr1`/`swr2`/`swr3`) — those
     are part of the WCD9378 bring-up additions, not this fix.
   - Does not fix `gcc-eliza sync_state pending due to crypto`.
   - Does not fix the WCD9378 TX slave UNATTACHED issue (separate fix).
   - Does not guarantee audio playback/capture works end-to-end.

4. **What must be confirmed on board before upstreaming?**
   - `7760000.pinctrl` probes cleanly (no deferred probe in dmesg).
   - `7660000.codec` (VA macro) probes after pinctrl fix.
   - Sound card instantiates without "VA Capture: error".
   - SMMU stream IDs for `q6apmdai` (`0x1001/0x80`, `0x1041/0x20`) are
     correct for Eliza (currently copied from SM8750).

5. **Is this fix safe to apply to the bring-up DTS now?**
   YES — this is a pure DTS addition. It adds missing nodes that the driver
   already expects. No existing nodes are modified. Risk: LOW.

6. **What is the upstream submission path for this fix?**
   - Target tree: `qcom/dt` (Bjorn Andersson / Konrad Dybcio)
   - File: `arch/arm64/boot/dts/qcom/eliza.dtsi`
   - Patch series: can be submitted as part of the Eliza audio bring-up series
     or as a standalone prerequisite patch before the WCD9378/SWR patches.
   - Requires: board-level boot test confirmation before RFC submission.

7. **What is the recommended next human action?**
   Apply `eliza_lpass_lpi_fix.patch` to the bring-up DTS tree, rebuild DTB,
   flash to Eliza EVK, and capture dmesg. Confirm `7760000.pinctrl` probes
   cleanly. If successful, proceed with WCD9378 TX UNATTACHED fix on Monday.

---

## Task 5: Validate All JSON Artifacts

Run:
```bash
python3 -m json.tool \
  AURA_KB/platform_issues/lpass_lpi_pinctrl_deferred_probe/reference_node_inventory.json \
  > /dev/null && echo "reference_node_inventory.json PASS"

python3 -m json.tool \
  AURA_KB/platform_issues/lpass_lpi_pinctrl_deferred_probe/fix_validation_checklist.json \
  > /dev/null && echo "fix_validation_checklist.json PASS"
```

Record results in:
`AURA_KB/platform_issues/lpass_lpi_pinctrl_deferred_probe/patch_generation_validation.json`

```json
{
  "reference_node_inventory_json": "PASS | FAIL",
  "fix_validation_checklist_json": "PASS | FAIL",
  "patch_file_exists": true,
  "swr_pinctrl_note_exists": true,
  "pm_fix_summary_exists": true,
  "kernel_source_modified": false,
  "aura_makefile_staged": false,
  "all_checks_pass": true
}
```

---

## Task 6: Commit and Push

```bash
git add AURA_KB/platform_issues/lpass_lpi_pinctrl_deferred_probe/
git commit -m "feat(kb): generate LPASS LPI pinctrl deferred probe DTS fix patch for Eliza EVK"
git push origin aura_upstream_learning
git status --short
```

Confirm `AURA/Makefile` is NOT in the staged files.

---

## Success Criteria

- [ ] `reference_node_inventory.json` — parse-valid, covers all 5 reference lookups
- [ ] `eliza_lpass_lpi_fix.patch` — valid unified-diff, Hunk 1 (gpr/q6prm) + Hunk 2 (lpass_tlmm)
- [ ] `swr_pinctrl_note.md` — documents pinctrl-0 for swr1/swr2/swr3
- [ ] `fix_validation_checklist.json` — parse-valid, all 13 checks present
- [ ] `pm_fix_summary.md` — answers all 7 questions
- [ ] `patch_generation_validation.json` — parse-valid, `all_checks_pass: true`
- [ ] No kernel source files modified
- [ ] `AURA/Makefile` NOT staged or committed
- [ ] All JSON artifacts pass `python3 -m json.tool`
- [ ] `git push origin aura_upstream_learning` succeeds
