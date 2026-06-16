# Hostile Derivability Audit — Derivation Report

## KB Parent Rules
- `PSR1`: Split series by logical ownership: binding/core/feature/fix.
- `PSR2`: Expect superseded revisions before acceptance.
- `PSR3`: Track accepted commits via Patchwork commit_ref.
- `ALSA1`: Use standard snd_soc_component_driver + snd_soc_dai_driver objects.
- `ALSA2`: kcontrol put must return 1 on state change, 0 otherwise.
- `ALSA3`: Keep initial upstream feature scope reviewable.
- `DAPM1`: Provide explicit DAPM widgets and routes.
- `DAPM2`: Keep DAPM graph minimal in initial series; iterate later.
- `DAPM3`: DAPM minimisation is family-sensitive (WSA vs WCD).
- `DT1`: Submit YAML binding with driver support.
- `DT2`: DT schema constraints are mandatory for acceptance.
- `PM1`: Runtime PM integration expected in codec/macro drivers.
- `PM2`: Resume path must be timeout-safe before cache sync.
- `SDW1`: Use generic SDW lifecycle APIs.
- `SDW2`: Model codec core and SDW transport ownership cleanly.
- `MB1`: Mark Brown: focused reviewable patch deltas; kcontrol semantics.
- `MB2`: Mark Brown: rejects unclear or overly mixed patch scope.
- `PB1`: Pierre Bossart: SDW lifecycle correctness and explicit state handling.
- `PB2`: Pierre Bossart: timeout-safe PM recovery; defensive resume.
- `KK1`: Krzysztof: strict DT schema consistency and variant hygiene.
- `KK2`: Krzysztof: DT binding patches paired with driver enablement.
- `VK1`: Vinod Koul: SoundWire transport conventions (sparse evidence).
- `PL1`: Playbook: stage codec as DT->core->controls->DAPM->fixes.
- `PL2`: Playbook: keep board policy out of codec.
- `PL3`: Playbook: SDW startup/shutdown stream lifecycle explicit.
- `PL4`: Reviewer survival: ownership-clean split + iteration discipline.
- `PL5`: Playbook: commit message quality matters for broad-scope patches.
- `PL6`: Playbook: bisect-safe at each patch.
- `PL7`: Playbook: Changes-since-vN mapping required on resend.

---

## Per-Candidate Results

| ID | GT | Predicted | Score | Correct |
|---|---|---|---|---|
| C1 | copied_rule | copied_rule | 0.9495 | YES |
| C2 | copied_rule | copied_rule | 0.982 | YES |
| C3 | copied_rule | copied_rule | 0.966 | YES |
| C4 | copied_rule | copied_rule | 0.9615 | YES |
| C5 | copied_rule | copied_rule | 0.95 | YES |
| C6 | copied_rule | copied_rule | 0.9705 | YES |
| C7 | copied_rule | copied_rule | 0.9585 | YES |
| C8 | copied_rule | copied_rule | 0.9335 | YES |
| C9 | copied_rule | copied_rule | 0.972 | YES |
| C10 | copied_rule | copied_rule | 0.886 | YES |
| G1 | generalized_rule | generalized_rule | 0.598 | YES |
| G2 | generalized_rule | generalized_rule | 0.5685 | YES |
| G3 | generalized_rule | generalized_rule | 0.588 | YES |
| G4 | generalized_rule | generalized_rule | 0.578 | YES |
| G5 | generalized_rule | copied_rule | 0.953 | NO |
| G6 | generalized_rule | generalized_rule | 0.5835 | YES |
| G7 | generalized_rule | generalized_rule | 0.5515 | YES |
| G8 | generalized_rule | generalized_rule | 0.61 | YES |
| G9 | generalized_rule | generalized_rule | 0.5725 | YES |
| G10 | generalized_rule | generalized_rule | 0.567 | YES |
| D1 | discovered_rule | discovered_rule | 0.0 | YES |
| D2 | discovered_rule | discovered_rule | 0.0 | YES |
| D3 | discovered_rule | discovered_rule | 0.0 | YES |
| D4 | discovered_rule | discovered_rule | 0.0 | YES |
| D5 | discovered_rule | discovered_rule | 0.0 | YES |
| D6 | discovered_rule | discovered_rule | 0.0 | YES |
| D7 | discovered_rule | discovered_rule | 0.0 | YES |
| D8 | discovered_rule | discovered_rule | 0.0 | YES |
| D9 | discovered_rule | discovered_rule | 0.0 | YES |
| D10 | discovered_rule | discovered_rule | 0.0 | YES |

---

## Derivation Detail

### C1 — score=0.9495 — copied_rule
> Split DT binding and driver enablement into separate ownership patches.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | YES | 0.97 | PSR1+DT1->split DT+driver |
| Multi-hop | YES | 0.92 | PSR1->DT1->C1 |
| Rule Composition | YES | 0.96 | PSR1∘DT1 |
| Constraint Combination | YES | 0.90 | PSR1∩DT1 scope |
| Semantic Paraphrase | YES | 0.96 | 'ownership patches' paraphrases PSR1 |
| Reviewer-Playbook | YES | 0.95 | PL1+KK2 playbook |
| Workflow Equivalence | YES | 0.96 | Standard DT-first codec workflow |

### C2 — score=0.982 — copied_rule
> ALSA kcontrol put must return 1 only when state changes.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | YES | 0.99 | ALSA2 exact |
| Multi-hop | YES | 0.95 | ALSA2->C2 |
| Rule Composition | YES | 0.99 | ALSA2 identity |
| Constraint Combination | YES | 0.97 | ALSA2 constraint |
| Semantic Paraphrase | YES | 0.99 | near-verbatim paraphrase |
| Reviewer-Playbook | YES | 0.99 | MB1 kcontrol |
| Workflow Equivalence | YES | 0.99 | ALSA control callback standard |

### C3 — score=0.966 — copied_rule
> Use generic sdw_driver lifecycle APIs for Qualcomm SDW codecs.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | YES | 0.98 | SDW1 exact |
| Multi-hop | YES | 0.94 | SDW1->C3 |
| Rule Composition | YES | 0.97 | SDW1 identity |
| Constraint Combination | YES | 0.95 | SDW1 constraint |
| Semantic Paraphrase | YES | 0.97 | 'generic sdw_driver' paraphrases SDW1 |
| Reviewer-Playbook | YES | 0.97 | PL3+SDW1 |
| Workflow Equivalence | YES | 0.97 | SDW lifecycle standard |

### C4 — score=0.9615 — copied_rule
> Include Changes-since-vN mapping when resending revisions.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | YES | 0.97 | PL7 exact |
| Multi-hop | YES | 0.93 | PL7->C4 |
| Rule Composition | YES | 0.97 | PL7 identity |
| Constraint Combination | YES | 0.95 | PL7 constraint |
| Semantic Paraphrase | YES | 0.97 | paraphrase of PL7 |
| Reviewer-Playbook | YES | 0.97 | PL7 direct |
| Workflow Equivalence | YES | 0.96 | revision discipline standard |

### C5 — score=0.95 — copied_rule
> Keep board-specific routing out of codec driver.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | YES | 0.96 | PL2 exact |
| Multi-hop | YES | 0.92 | PL2->C5 |
| Rule Composition | YES | 0.96 | PL2 identity |
| Constraint Combination | YES | 0.94 | PL2 constraint |
| Semantic Paraphrase | YES | 0.95 | paraphrase of PL2 |
| Reviewer-Playbook | YES | 0.96 | PL2 direct |
| Workflow Equivalence | YES | 0.96 | codec isolation standard |

### C6 — score=0.9705 — copied_rule
> Validate runtime-PM timeout before cache sync on resume path.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | YES | 0.98 | PM2 exact |
| Multi-hop | YES | 0.94 | PM2->C6 |
| Rule Composition | YES | 0.98 | PM2 identity |
| Constraint Combination | YES | 0.96 | PM2 constraint |
| Semantic Paraphrase | YES | 0.98 | paraphrase of PM2 |
| Reviewer-Playbook | YES | 0.97 | PB2+PM2 |
| Workflow Equivalence | YES | 0.97 | PM resume standard |

### C7 — score=0.9585 — copied_rule
> Run strict DT schema validation (dtbs_check) before submission.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | YES | 0.97 | DT2 exact |
| Multi-hop | YES | 0.93 | DT2->C7 |
| Rule Composition | YES | 0.97 | DT2 identity |
| Constraint Combination | YES | 0.95 | DT2 constraint |
| Semantic Paraphrase | YES | 0.96 | paraphrase of DT2 with tool name |
| Reviewer-Playbook | YES | 0.96 | DT2 direct |
| Workflow Equivalence | YES | 0.96 | DT validation standard |

### C8 — score=0.9335 — copied_rule
> Do not mix cleanup-only refactor with functional feature patch.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | YES | 0.95 | PSR1+MB2 |
| Multi-hop | YES | 0.91 | PSR1->MB2->C8 |
| Rule Composition | YES | 0.94 | PSR1∘MB2 |
| Constraint Combination | YES | 0.92 | PSR1∩MB2 |
| Semantic Paraphrase | YES | 0.93 | paraphrase of PSR1+MB2 |
| Reviewer-Playbook | YES | 0.94 | MB2+PSR1 playbook |
| Workflow Equivalence | YES | 0.93 | patch focus standard |

### C9 — score=0.972 — copied_rule
> Keep series bisect-safe at each patch.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | YES | 0.98 | PL6 exact |
| Multi-hop | YES | 0.94 | PL6->C9 |
| Rule Composition | YES | 0.98 | PL6 identity |
| Constraint Combination | YES | 0.96 | PL6 constraint |
| Semantic Paraphrase | YES | 0.98 | paraphrase of PL6 |
| Reviewer-Playbook | YES | 0.98 | PL6 direct |
| Workflow Equivalence | YES | 0.98 | bisect standard |

### C10 — score=0.886 — copied_rule
> Fixes for regressions should be isolated and focused.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | YES | 0.91 | PSR1+ALSA3 |
| Multi-hop | YES | 0.86 | PSR1->ALSA3->C10 |
| Rule Composition | YES | 0.90 | PSR1∘ALSA3 |
| Constraint Combination | YES | 0.84 | PSR1∩ALSA3 scope |
| Semantic Paraphrase | YES | 0.88 | paraphrase of PSR1+ALSA3 |
| Reviewer-Playbook | YES | 0.90 | ALSA3+PSR1 playbook |
| Workflow Equivalence | YES | 0.89 | fix isolation standard |

### G1 — score=0.598 — generalized_rule
> In Qualcomm audio codec bring-up, 2-4 ownership patches survive better than monoliths.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | NO | — | No single rule covers 2-4 patch count heuristic |
| Multi-hop | YES | 0.88 | PSR1+ALSA3+PL4->patch-count heuristic |
| Rule Composition | YES | 0.86 | PSR1∘ALSA3∘PL4 |
| Constraint Combination | YES | 0.80 | PSR1∩ALSA3∩PL4 scope |
| Semantic Paraphrase | YES | 0.65 | partial paraphrase; scope broadened |
| Reviewer-Playbook | YES | 0.85 | PL1+PL4+PSR1 playbook |
| Workflow Equivalence | YES | 0.84 | patch-count workflow heuristic |

### G2 — score=0.5685 — generalized_rule
> When reviewer evidence is sparse, lower confidence and avoid maintainer-specific hard assumptions.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | NO | — | No single rule covers confidence-gate policy |
| Multi-hop | YES | 0.82 | PL4+MB1+PB1->confidence policy |
| Rule Composition | YES | 0.80 | PL4∘MB1∘PB1 |
| Constraint Combination | YES | 0.76 | PL4∩MB1∩PB1 |
| Semantic Paraphrase | YES | 0.65 | partial paraphrase |
| Reviewer-Playbook | YES | 0.80 | PL4 playbook |
| Workflow Equivalence | YES | 0.79 | confidence-gate workflow |

### G3 — score=0.588 — generalized_rule
> Separate transport-ownership changes from control/DAPM changes in SDW codecs.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | NO | — | No single rule covers transport+DAPM split |
| Multi-hop | YES | 0.85 | SDW2+DAPM1+PSR1->transport/DAPM separation |
| Rule Composition | YES | 0.84 | SDW2∘DAPM1∘PSR1 |
| Constraint Combination | YES | 0.80 | SDW2∩DAPM1∩PSR1 |
| Semantic Paraphrase | YES | 0.65 | partial paraphrase |
| Reviewer-Playbook | YES | 0.83 | PL3+SDW2+DAPM1 playbook |
| Workflow Equivalence | YES | 0.83 | transport/DAPM split workflow |

### G4 — score=0.578 — generalized_rule
> PM/SoundWire changes should include explicit failure-path handling before resend.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | NO | — | No single rule covers PM+SDW failure-path |
| Multi-hop | YES | 0.83 | PM2+SDW1+PSR2->failure-path before resend |
| Rule Composition | YES | 0.82 | PM2∘SDW1∘PSR2 |
| Constraint Combination | YES | 0.78 | PM2∩SDW1∩PSR2 |
| Semantic Paraphrase | YES | 0.65 | partial paraphrase |
| Reviewer-Playbook | YES | 0.82 | PB1+PB2+PL3 playbook |
| Workflow Equivalence | YES | 0.81 | PM+SDW failure-path workflow |

### G5 — score=0.953 — copied_rule
> DAPM minimisation should be family-sensitive (WSA vs WCD).

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | YES | 0.96 | DAPM3 near-exact |
| Multi-hop | YES | 0.95 | DAPM3->G5 |
| Rule Composition | YES | 0.96 | DAPM3 identity |
| Constraint Combination | YES | 0.94 | DAPM3 constraint |
| Semantic Paraphrase | YES | 0.95 | near-verbatim paraphrase of DAPM3 |
| Reviewer-Playbook | YES | 0.95 | DAPM3 playbook |
| Workflow Equivalence | YES | 0.95 | family-sensitive DAPM workflow |

**MISCLASSIFICATION**
- GT=generalized_rule PRED=copied_rule SCORE=0.953

### G6 — score=0.5835 — generalized_rule
> Commit message quality matters most when patch scope is broad.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | NO | — | No single rule covers commit quality + scope interaction |
| Multi-hop | YES | 0.84 | PL5+MB2->quality matters for broad scope |
| Rule Composition | YES | 0.83 | PL5∘MB2 |
| Constraint Combination | YES | 0.79 | PL5∩MB2 |
| Semantic Paraphrase | YES | 0.65 | partial paraphrase |
| Reviewer-Playbook | YES | 0.83 | PL5+MB2 playbook |
| Workflow Equivalence | YES | 0.82 | commit quality scope workflow |

### G7 — score=0.5515 — generalized_rule
> Risk rises when too many patches touch same core codec file in v1.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | NO | — | No single rule covers file-touch risk heuristic |
| Multi-hop | YES | 0.80 | PSR1+ALSA3+MB2->file-touch risk |
| Rule Composition | YES | 0.79 | PSR1∘ALSA3∘MB2 |
| Constraint Combination | YES | 0.75 | PSR1∩ALSA3∩MB2 |
| Semantic Paraphrase | YES | 0.60 | partial paraphrase |
| Reviewer-Playbook | YES | 0.79 | PSR1+ALSA3+MB2 playbook |
| Workflow Equivalence | YES | 0.78 | file-touch risk workflow |

### G8 — score=0.61 — generalized_rule
> Map each reviewer objection to an explicit vN delta note to improve convergence.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | NO | — | No single rule covers delta-mapping discipline |
| Multi-hop | YES | 0.87 | PSR2+PL7+PL4->delta mapping |
| Rule Composition | YES | 0.86 | PSR2∘PL7∘PL4 |
| Constraint Combination | YES | 0.82 | PSR2∩PL7∩PL4 |
| Semantic Paraphrase | YES | 0.70 | partial paraphrase |
| Reviewer-Playbook | YES | 0.86 | PSR2+PL7+PL4 playbook |
| Workflow Equivalence | YES | 0.85 | delta mapping workflow |

### G9 — score=0.5725 — generalized_rule
> When DT compatible expansion and reset semantics both change, schema-first split reduces churn.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | NO | — | No single rule covers DT+reset schema-first split |
| Multi-hop | YES | 0.82 | DT1+DT2+KK1+PSR1->schema-first |
| Rule Composition | YES | 0.81 | DT1∘DT2∘KK1∘PSR1 |
| Constraint Combination | YES | 0.77 | DT1∩DT2∩KK1∩PSR1 |
| Semantic Paraphrase | YES | 0.65 | partial paraphrase |
| Reviewer-Playbook | YES | 0.81 | KK1+KK2+DT1 playbook |
| Workflow Equivalence | YES | 0.80 | schema-first DT workflow |

### G10 — score=0.567 — generalized_rule
> Introduce shared helper first, then migrate call sites, for SoundWire runtime allocation changes.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | NO | — | No single rule covers helper-first migration |
| Multi-hop | YES | 0.81 | SDW2+PSR1+PL3->helper-first |
| Rule Composition | YES | 0.80 | SDW2∘PSR1∘PL3 |
| Constraint Combination | YES | 0.76 | SDW2∩PSR1∩PL3 |
| Semantic Paraphrase | YES | 0.65 | partial paraphrase |
| Reviewer-Playbook | YES | 0.80 | PL3+SDW2 playbook |
| Workflow Equivalence | YES | 0.79 | helper-first migration workflow |

### D1 — score=0.0 — discovered_rule
> For WSA88xx introductions, acceptance improves only when PM timeout guards are in core patch AND DAPM stays separate; bundling all three increases objection rate.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | NO | — | Direct: Conditional interaction PM∧DAPM-split not derivable from any KB rule or compositio |
| Multi-hop | NO | — | Multi-hop: Conditional interaction PM∧DAPM-split not derivable from any KB rule or composi |
| Rule Composition | NO | — | Rule Composition: Conditional interaction PM∧DAPM-split not derivable from any KB rule or  |
| Constraint Combination | NO | — | Constraint Combination: Conditional interaction PM∧DAPM-split not derivable from any KB ru |
| Semantic Paraphrase | NO | — | Semantic Paraphrase: Conditional interaction PM∧DAPM-split not derivable from any KB rule  |
| Reviewer-Playbook | NO | — | Reviewer-Playbook: Conditional interaction PM∧DAPM-split not derivable from any KB rule or |
| Workflow Equivalence | NO | — | Workflow Equivalence: Conditional interaction PM∧DAPM-split not derivable from any KB rule |

### D2 — score=0.0 — discovered_rule
> Krzysztof DT objections drop when examples include placeholder port-map node even if property optional.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | NO | — | Direct: Reviewer-specific trigger (placeholder port-map node) absent from all KB rules. |
| Multi-hop | NO | — | Multi-hop: Reviewer-specific trigger (placeholder port-map node) absent from all KB rules. |
| Rule Composition | NO | — | Rule Composition: Reviewer-specific trigger (placeholder port-map node) absent from all KB |
| Constraint Combination | NO | — | Constraint Combination: Reviewer-specific trigger (placeholder port-map node) absent from  |
| Semantic Paraphrase | NO | — | Semantic Paraphrase: Reviewer-specific trigger (placeholder port-map node) absent from all |
| Reviewer-Playbook | NO | — | Reviewer-Playbook: Reviewer-specific trigger (placeholder port-map node) absent from all K |
| Workflow Equivalence | NO | — | Workflow Equivalence: Reviewer-specific trigger (placeholder port-map node) absent from al |

### D3 — score=0.0 — discovered_rule
> Mark patch-structure objections sharply decrease when first non-DT patch builds with CONFIG_SOUNDWIRE=n.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | NO | — | Direct: Build-config conditional (CONFIG_SOUNDWIRE=n) not present in any KB rule. |
| Multi-hop | NO | — | Multi-hop: Build-config conditional (CONFIG_SOUNDWIRE=n) not present in any KB rule. |
| Rule Composition | NO | — | Rule Composition: Build-config conditional (CONFIG_SOUNDWIRE=n) not present in any KB rule |
| Constraint Combination | NO | — | Constraint Combination: Build-config conditional (CONFIG_SOUNDWIRE=n) not present in any K |
| Semantic Paraphrase | NO | — | Semantic Paraphrase: Build-config conditional (CONFIG_SOUNDWIRE=n) not present in any KB r |
| Reviewer-Playbook | NO | — | Reviewer-Playbook: Build-config conditional (CONFIG_SOUNDWIRE=n) not present in any KB rul |
| Workflow Equivalence | NO | — | Workflow Equivalence: Build-config conditional (CONFIG_SOUNDWIRE=n) not present in any KB  |

### D4 — score=0.0 — discovered_rule
> Pierre SDW callback objections reduce when status-callback changes are paired with timeout-test evidence in cover letter.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | NO | — | Direct: Cover-letter content interaction with SDW callback objections not in KB. |
| Multi-hop | NO | — | Multi-hop: Cover-letter content interaction with SDW callback objections not in KB. |
| Rule Composition | NO | — | Rule Composition: Cover-letter content interaction with SDW callback objections not in KB. |
| Constraint Combination | NO | — | Constraint Combination: Cover-letter content interaction with SDW callback objections not  |
| Semantic Paraphrase | NO | — | Semantic Paraphrase: Cover-letter content interaction with SDW callback objections not in  |
| Reviewer-Playbook | NO | — | Reviewer-Playbook: Cover-letter content interaction with SDW callback objections not in KB |
| Workflow Equivalence | NO | — | Workflow Equivalence: Cover-letter content interaction with SDW callback objections not in |

### D5 — score=0.0 — discovered_rule
> In WSA884x follow-ups, a tiny targeted-fix patch is accepted faster only if earlier patches are unchanged between revisions.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | NO | — | Direct: Revision-stability immutability interaction not in KB. |
| Multi-hop | NO | — | Multi-hop: Revision-stability immutability interaction not in KB. |
| Rule Composition | NO | — | Rule Composition: Revision-stability immutability interaction not in KB. |
| Constraint Combination | NO | — | Constraint Combination: Revision-stability immutability interaction not in KB. |
| Semantic Paraphrase | NO | — | Semantic Paraphrase: Revision-stability immutability interaction not in KB. |
| Reviewer-Playbook | NO | — | Reviewer-Playbook: Revision-stability immutability interaction not in KB. |
| Workflow Equivalence | NO | — | Workflow Equivalence: Revision-stability immutability interaction not in KB. |

### D6 — score=0.0 — discovered_rule
> For Qualcomm audio SDW fixes, moving helper introduction before any machine-card touches cuts reviewer churn only when helper has unit-testable API boundaries.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | NO | — | Direct: Helper testability conditional not in KB. |
| Multi-hop | NO | — | Multi-hop: Helper testability conditional not in KB. |
| Rule Composition | NO | — | Rule Composition: Helper testability conditional not in KB. |
| Constraint Combination | NO | — | Constraint Combination: Helper testability conditional not in KB. |
| Semantic Paraphrase | NO | — | Semantic Paraphrase: Helper testability conditional not in KB. |
| Reviewer-Playbook | NO | — | Reviewer-Playbook: Helper testability conditional not in KB. |
| Workflow Equivalence | NO | — | Workflow Equivalence: Helper testability conditional not in KB. |

### D7 — score=0.0 — discovered_rule
> DT review latency is minimised when schema examples use the same compatible ordering as machine-driver DTS updates in same series.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | NO | — | Direct: Compatible ordering alignment effect not in KB. |
| Multi-hop | NO | — | Multi-hop: Compatible ordering alignment effect not in KB. |
| Rule Composition | NO | — | Rule Composition: Compatible ordering alignment effect not in KB. |
| Constraint Combination | NO | — | Constraint Combination: Compatible ordering alignment effect not in KB. |
| Semantic Paraphrase | NO | — | Semantic Paraphrase: Compatible ordering alignment effect not in KB. |
| Reviewer-Playbook | NO | — | Reviewer-Playbook: Compatible ordering alignment effect not in KB. |
| Workflow Equivalence | NO | — | Workflow Equivalence: Compatible ordering alignment effect not in KB. |

### D8 — score=0.0 — discovered_rule
> Reviewer survival improves when PM and SDW rationale share one user-impact paragraph, but code remains split.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | NO | — | Direct: Rationale-structure interaction (shared paragraph, split code) not in KB. |
| Multi-hop | NO | — | Multi-hop: Rationale-structure interaction (shared paragraph, split code) not in KB. |
| Rule Composition | NO | — | Rule Composition: Rationale-structure interaction (shared paragraph, split code) not in KB |
| Constraint Combination | NO | — | Constraint Combination: Rationale-structure interaction (shared paragraph, split code) not |
| Semantic Paraphrase | NO | — | Semantic Paraphrase: Rationale-structure interaction (shared paragraph, split code) not in |
| Reviewer-Playbook | NO | — | Reviewer-Playbook: Rationale-structure interaction (shared paragraph, split code) not in K |
| Workflow Equivalence | NO | — | Workflow Equivalence: Rationale-structure interaction (shared paragraph, split code) not i |

### D9 — score=0.0 — discovered_rule
> Vinod acceptance probability improves when SoundWire helper patches include explicit no-behavior-change proof in commit body.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | NO | — | Direct: Vinod-specific no-behavior-change proof trigger not in KB. |
| Multi-hop | NO | — | Multi-hop: Vinod-specific no-behavior-change proof trigger not in KB. |
| Rule Composition | NO | — | Rule Composition: Vinod-specific no-behavior-change proof trigger not in KB. |
| Constraint Combination | NO | — | Constraint Combination: Vinod-specific no-behavior-change proof trigger not in KB. |
| Semantic Paraphrase | NO | — | Semantic Paraphrase: Vinod-specific no-behavior-change proof trigger not in KB. |
| Reviewer-Playbook | NO | — | Reviewer-Playbook: Vinod-specific no-behavior-change proof trigger not in KB. |
| Workflow Equivalence | NO | — | Workflow Equivalence: Vinod-specific no-behavior-change proof trigger not in KB. |

### D10 — score=0.0 — discovered_rule
> Cross-family transfer succeeds only if discovered rule has at least one non-WSA validation thread; otherwise promotion should be local-only.

| Type | Proof | Conf | Path |
|---|---|---|---|
| Direct | NO | — | Direct: Meta-promotion criterion (non-WSA validation thread requirement) not in KB. |
| Multi-hop | NO | — | Multi-hop: Meta-promotion criterion (non-WSA validation thread requirement) not in KB. |
| Rule Composition | NO | — | Rule Composition: Meta-promotion criterion (non-WSA validation thread requirement) not in  |
| Constraint Combination | NO | — | Constraint Combination: Meta-promotion criterion (non-WSA validation thread requirement) n |
| Semantic Paraphrase | NO | — | Semantic Paraphrase: Meta-promotion criterion (non-WSA validation thread requirement) not  |
| Reviewer-Playbook | NO | — | Reviewer-Playbook: Meta-promotion criterion (non-WSA validation thread requirement) not in |
| Workflow Equivalence | NO | — | Workflow Equivalence: Meta-promotion criterion (non-WSA validation thread requirement) not |

---

## Metrics

### copied_rule
- Precision: 90.9%  Recall: 100.0%  F1: 95.2%
### generalized_rule
- Precision: 100.0%  Recall: 90.0%  F1: 94.7%
### discovered_rule
- Precision: 100.0%  Recall: 100.0%  F1: 100.0%

### Overall
- Accuracy: 96.7%
- FDR: 0.0%
- FRR: 0.0%

---

## What additional evidence upgrades a candidate to discovered_rule?

1. Interaction irreducibility proof: conditional trigger not derivable from any KB subset.
2. External causal anchor: real reviewer comment + revision delta showing the interaction.
3. Counterfactual evidence: 2+ series where condition absent and predicted outcome did not occur.
4. Cross-family transfer: rule improves reviewer-survival on at least one non-WSA family.
5. Adversarial replay failure: existing KB without candidate rule fails to reproduce planning decision.
