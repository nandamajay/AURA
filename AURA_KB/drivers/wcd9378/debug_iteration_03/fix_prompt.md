# Prompt: WCD9378 Fix Iteration 03 — Wrong Register Addresses + Bad DAPM Routes

## Objective

Fix two precise bugs identified from the board log that are preventing sound
card instantiation (`-EINVAL` / `-22`).

**Files to modify:**
- `AURA_KB/drivers/wcd9378/static_prototype_variant_a1_compile_ready/converted/wcd9378.h`
- `AURA_KB/drivers/wcd9378/static_prototype_variant_a1_compile_ready/converted/wcd9378.c`

No other files are modified.

---

## AURA Governance Invariants

| Principle    | Enforcement |
|---|---|
| BOUNDED      | Read only the allowed sources listed below. |
| OBSERVABLE   | Every change maps to a named log error line. |
| EXPLAINABLE  | Every register value cites the downstream reference file and line. |
| REPLAYABLE   | Deterministic code + JSON artifacts only. |
| INTERRUPTIBLE| If any reference lookup fails, record BLOCKED and stop. |
| REVERSIBLE   | KB artifacts only; no kernel source tree modification. |

---

## Allowed Sources

| Source | Purpose |
|---|---|
| `AURA_KB/drivers/wcd9378/static_prototype_variant_a1_compile_ready/converted/wcd9378.h` | Fix target |
| `AURA_KB/drivers/wcd9378/static_prototype_variant_a1_compile_ready/converted/wcd9378.c` | Fix target |
| `track_b_corpora/audio-kernel-ar/asoc/codecs/wcd9378/wcd9378-registers.h` | Authoritative register address source |
| `track_b_corpora/linux-next/sound/soc/codecs/wcd938x.h` | Cross-check reference |

---

## Forbidden Actions

- Do NOT modify any file outside `AURA_KB/`.
- Do NOT modify the kernel source tree.
- Do NOT commit `AURA/Makefile`.
- Do NOT change any logic beyond the two bugs described below.

---

## Bug 1 — Wrong Register Addresses in `wcd9378.h`

### Evidence from board log

```
[17.423429] ASoC error (-16): at soc_component_read_no_lock() on audio-codec for register: [0x000030ef]
[17.435584] HPH_STATE: ANA_HPH=0xf0
[17.441633] ASoC error (-16): at soc_component_read_no_lock() on audio-codec for register: [0x000030c9]
[17.453727] HPH_STATE: CDC_HPH_GAIN_CTL=0xf0
[17.460858] ASoC error (-16): at soc_component_read_no_lock() on audio-codec for register: [0x000030ca]
[17.473000] HPH_STATE: HPH_RDAC_CLK_CTL1=0xf0
[17.479924] ASoC error (-16): at soc_component_read_no_lock() on audio-codec for register: [0x000030e4]
[17.491999] HPH_STATE: CDC_COMP_CTL_0=0xf0
```

`-16` is `-EBUSY` from regmap — the register address is outside the valid
regmap range, so regmap rejects the access. All four reads return `0xf0`
(the regmap error sentinel), not real hardware values.

### Root cause

`wcd9378.h` lines 66–69 define the four HPH control registers as **aliases
to read-only status registers**:

```c
/* CURRENT — WRONG */
#define WCD9378_ANA_HPH          WCD9378_EAR_STATUS_REG_1      /* 0x30ef */
#define WCD9378_CDC_HPH_GAIN_CTL WCD9378_HPH_L_STATUS          /* 0x30c9 */
#define WCD9378_HPH_RDAC_CLK_CTL1 WCD9378_HPH_R_STATUS         /* 0x30ca */
#define WCD9378_CDC_COMP_CTL_0   WCD9378_HPH_SURGE_HPHLR_SURGE_STATUS /* 0x30e4 */
```

These are status/read-only registers in the 0x30xx range. The real control
registers live at completely different addresses.

### Correct addresses

Derived from `track_b_corpora/audio-kernel-ar/asoc/codecs/wcd9378/wcd9378-registers.h`
using the `WCD9378_REG()` macro:
`((raw & 0x0ff00000) >> 8) | (raw & 0xfff)`

| Macro | Downstream raw address | Correct regmap address |
|---|---|---|
| `WCD9378_ANA_HPH` | `WCD9378_A_BASE + 0x09` = `0x40180009` | `0x1009` |
| `WCD9378_HPH_RDAC_CLK_CTL1` | `WCD9378_A_BASE + 0xd9` = `0x401800d9` | `0x10d9` |
| `WCD9378_CDC_COMP_CTL_0` | `WCD9378_TAMBORA_BASE + 0x14` = `0x40180414` | `0x1414` |
| `WCD9378_CDC_HPH_GAIN_CTL` | `WCD9378_TAMBORA_BASE + 0x4e` = `0x4018044e` | `0x144e` |

Where:
- `WCD9378_A_BASE = 0x40180000` (`WCD9378_BASE(0x3fffffff) + 0x180001`)
- `WCD9378_TAMBORA_BASE = 0x40180400` (`WCD9378_BASE + 0x180401`)

### Fix

In `wcd9378.h`, replace lines 66–69:

```c
/* WRONG — remove these aliases */
#define WCD9378_ANA_HPH                         WCD9378_EAR_STATUS_REG_1
#define WCD9378_CDC_HPH_GAIN_CTL                WCD9378_HPH_L_STATUS
#define WCD9378_HPH_RDAC_CLK_CTL1               WCD9378_HPH_R_STATUS
#define WCD9378_CDC_COMP_CTL_0                  WCD9378_HPH_SURGE_HPHLR_SURGE_STATUS
```

Replace with direct addresses:

```c
/* CORRECT — direct regmap addresses derived from downstream wcd9378-registers.h */
#define WCD9378_ANA_HPH                         0x1009
#define WCD9378_HPH_RDAC_CLK_CTL1               0x10d9
#define WCD9378_CDC_COMP_CTL_0                  0x1414
#define WCD9378_CDC_HPH_GAIN_CTL                0x144e
```

**Do not change** the mask/bit definitions on lines 72–78 — those are correct.

---

## Bug 2 — Invalid DAPM Routes for `HPHL` and `HPHR` widgets

### Evidence from board log

```
[17.498744] Control not supported for path HPHL PGA -> [Switch] -> HPHL
[17.507987] ASoC: Failed to add route HPHL PGA -> [Switch] -> HPHL
[17.516789] Control not supported for path HPHR PGA -> [Switch] -> HPHR
[17.526572] ASoC: Failed to add route HPHR PGA -> [Switch] -> HPHR
[17.535482] snd-sc8280xp sound: ASoC: failed to instantiate card -22
```

`-22` is `-EINVAL`. The card fails to instantiate because two DAPM routes
are invalid.

### Root cause

In `wcd9378.c` the routes are:

```c
{ "HPHL", "Switch", "HPHL PGA" },   /* line 645 — WRONG */
{ "HPHR", "Switch", "HPHR PGA" },   /* line 651 — WRONG */
```

`HPHL` and `HPHR` are declared as `SND_SOC_DAPM_OUT_DRV_E` widgets.
`OUT_DRV_E` is a power-gated output driver — it has **no mixer control**.
A route with a non-NULL control name (`"Switch"`) requires the sink widget
to be a `MIXER` or `SWITCH` type that has a named kcontrol. Using `"Switch"`
on an `OUT_DRV_E` is invalid and ASoC rejects it with `-EINVAL`.

The correct route is a direct connection with `NULL` as the control name,
meaning the output is always connected when the widget is powered.

### Fix

In `wcd9378.c`, change lines 645 and 651:

```c
/* WRONG */
{ "HPHL", "Switch", "HPHL PGA" },
{ "HPHR", "Switch", "HPHR PGA" },

/* CORRECT */
{ "HPHL", NULL, "HPHL PGA" },
{ "HPHR", NULL, "HPHR PGA" },
```

---

## Task 1: Apply Both Fixes

Apply Bug 1 fix to `wcd9378.h` lines 66–69.
Apply Bug 2 fix to `wcd9378.c` lines 645 and 651.

---

## Task 2: Verify No Other Register Aliases Are Wrong

After fixing Bug 1, scan `wcd9378.h` for any other macros that alias
HPH/analog registers to status registers (0x30xx range) when they should
be control registers. Record findings in the change log.

Specifically check:
- `WCD9378_ANA_RX_SUPPLIES` — should be `A_BASE + 0x08` = `0x1008`
- `WCD9378_ANA_BIAS` — should be `A_BASE + 0x01` = `0x1001`
- Any other `WCD9378_ANA_*` or `WCD9378_HPH_*` macros used in `wcd9378.c`

If any are wrong, fix them in the same commit.

---

## Task 3: Change Log JSON

Create:
`AURA_KB/drivers/wcd9378/debug_iteration_03/fix_change_log.json`

```json
[
  {
    "bug_id": "BUG-03-01",
    "file": "wcd9378.h",
    "lines_changed": "66-69",
    "error_in_log": "ASoC error (-16) at soc_component_read_no_lock for registers 0x30ef/0x30c9/0x30ca/0x30e4",
    "root_cause": "Register aliases pointed to read-only status registers instead of control registers",
    "fix": "Replaced aliases with correct regmap addresses 0x1009/0x10d9/0x1414/0x144e",
    "reference": "track_b_corpora/audio-kernel-ar/asoc/codecs/wcd9378/wcd9378-registers.h lines 35/154/300/356",
    "verified_against_downstream": true
  },
  {
    "bug_id": "BUG-03-02",
    "file": "wcd9378.c",
    "lines_changed": "645, 651",
    "error_in_log": "Control not supported for path HPHL PGA -> [Switch] -> HPHL; ASoC failed to add route; card -22",
    "root_cause": "SND_SOC_DAPM_OUT_DRV_E widget has no mixer control; route with non-NULL control name is invalid",
    "fix": "Changed route control name from 'Switch' to NULL for HPHL and HPHR sink routes",
    "reference": "ASoC DAPM widget type rules; wcd938x.c HPHL/HPHR route pattern",
    "verified_against_downstream": true
  }
]
```

---

## Task 4: Validation Checklist JSON

Create:
`AURA_KB/drivers/wcd9378/debug_iteration_03/fix_validation_checklist.json`

```json
[
  {
    "id": "DBG3-CHK-001",
    "check": "WCD9378_ANA_HPH = 0x1009 in wcd9378.h",
    "status": "PASS_STATIC",
    "how_to_verify": "grep WCD9378_ANA_HPH wcd9378.h"
  },
  {
    "id": "DBG3-CHK-002",
    "check": "WCD9378_HPH_RDAC_CLK_CTL1 = 0x10d9 in wcd9378.h",
    "status": "PASS_STATIC",
    "how_to_verify": "grep WCD9378_HPH_RDAC_CLK_CTL1 wcd9378.h"
  },
  {
    "id": "DBG3-CHK-003",
    "check": "WCD9378_CDC_COMP_CTL_0 = 0x1414 in wcd9378.h",
    "status": "PASS_STATIC",
    "how_to_verify": "grep WCD9378_CDC_COMP_CTL_0 wcd9378.h"
  },
  {
    "id": "DBG3-CHK-004",
    "check": "WCD9378_CDC_HPH_GAIN_CTL = 0x144e in wcd9378.h",
    "status": "PASS_STATIC",
    "how_to_verify": "grep WCD9378_CDC_HPH_GAIN_CTL wcd9378.h"
  },
  {
    "id": "DBG3-CHK-005",
    "check": "No alias to WCD9378_EAR_STATUS_REG_1/HPH_L_STATUS/HPH_R_STATUS/HPH_SURGE_STATUS remains for control registers",
    "status": "PASS_STATIC",
    "how_to_verify": "grep -E 'EAR_STATUS|HPH_L_STATUS|HPH_R_STATUS|HPH_SURGE' wcd9378.h — should only appear as their own definitions, not as aliases"
  },
  {
    "id": "DBG3-CHK-006",
    "check": "Route { HPHL, NULL, HPHL PGA } in wcd9378.c",
    "status": "PASS_STATIC",
    "how_to_verify": "grep 'HPHL.*NULL.*HPHL PGA' wcd9378.c"
  },
  {
    "id": "DBG3-CHK-007",
    "check": "Route { HPHR, NULL, HPHR PGA } in wcd9378.c",
    "status": "PASS_STATIC",
    "how_to_verify": "grep 'HPHR.*NULL.*HPHR PGA' wcd9378.c"
  },
  {
    "id": "DBG3-CHK-008",
    "check": "No 'ASoC error (-16)' for HPH registers in dmesg after fix",
    "status": "PENDING_BOARD",
    "how_to_verify": "dmesg | grep 'ASoC error' — should be absent for 0x1009/0x10d9/0x1414/0x144e"
  },
  {
    "id": "DBG3-CHK-009",
    "check": "No 'Control not supported for path HPHL/HPHR' in dmesg after fix",
    "status": "PENDING_BOARD",
    "how_to_verify": "dmesg | grep 'Control not supported' — should be absent"
  },
  {
    "id": "DBG3-CHK-010",
    "check": "Sound card instantiates (no 'failed to instantiate card -22')",
    "status": "PENDING_BOARD",
    "how_to_verify": "dmesg | grep 'failed to instantiate' — should be absent; cat /proc/asound/cards should show card"
  },
  {
    "id": "DBG3-CHK-011",
    "check": "HPH_STATE register dump shows real values (not 0xf0) after fix",
    "status": "PENDING_BOARD",
    "how_to_verify": "dmesg | grep HPH_STATE — values should not be 0xf0"
  },
  {
    "id": "DBG3-CHK-012",
    "check": "No kernel source files modified",
    "status": "PASS_STATIC",
    "how_to_verify": "git diff --name-only — only AURA_KB/ files"
  }
]
```

---

## Task 5: PM Summary

Create:
`AURA_KB/drivers/wcd9378/debug_iteration_03/pm_debug_03_summary.md`

Answer:
1. What were the two bugs and their exact log evidence?
2. Why were the register addresses wrong — copy-paste error or wrong alias?
3. Why was the DAPM route wrong — widget type mismatch?
4. What is the expected outcome after both fixes?
5. What is the next failure to expect (TX slave still UNATTACHED)?
6. What remains fail-closed after these fixes?

---

## Task 6: Validate JSON Artifacts

```bash
python3 -m json.tool \
  AURA_KB/drivers/wcd9378/debug_iteration_03/fix_change_log.json > /dev/null \
  && echo "fix_change_log.json PASS"

python3 -m json.tool \
  AURA_KB/drivers/wcd9378/debug_iteration_03/fix_validation_checklist.json > /dev/null \
  && echo "fix_validation_checklist.json PASS"
```

Record in:
`AURA_KB/drivers/wcd9378/debug_iteration_03/validation.json`

---

## Task 7: Commit and Push

```bash
git add AURA_KB/drivers/wcd9378/debug_iteration_03/
git add AURA_KB/drivers/wcd9378/static_prototype_variant_a1_compile_ready/converted/wcd9378.h
git add AURA_KB/drivers/wcd9378/static_prototype_variant_a1_compile_ready/converted/wcd9378.c
git commit -m "fix(wcd9378): correct HPH register addresses and DAPM OUT_DRV route control names"
git push origin aura_upstream_learning
git status --short
```

Confirm `AURA/Makefile` is NOT staged.

---

## Success Criteria

- [ ] `wcd9378.h` lines 66–69: four macros use direct addresses `0x1009`, `0x10d9`, `0x1414`, `0x144e`
- [ ] `wcd9378.c` lines 645, 651: routes use `NULL` not `"Switch"` for `HPHL`/`HPHR` sink
- [ ] `fix_change_log.json` — parse-valid, both bugs recorded
- [ ] `fix_validation_checklist.json` — parse-valid, 12 checks present
- [ ] `pm_debug_03_summary.md` — answers all 6 questions
- [ ] `validation.json` — parse-valid, all JSON PASS
- [ ] No kernel source tree files modified
- [ ] `AURA/Makefile` NOT staged
- [ ] `git push origin aura_upstream_learning` succeeds
