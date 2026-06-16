# Discovery_V3_Adversarial_Benchmark Failure Analysis

## Summary
- Total items: 200
- Class distribution: 50 copied_rule / 50 generalized_rule / 50 discovered_rule / 50 ambiguous_borderline
- Discovered false-positive rate (FDR): 53.70%
- Discovered false-negative rate (FRR): 0.00%
- Calibration score (ECE): 0.3501

## Precision/Recall by class
- copied_rule: precision=100.00%, recall=12.00%, tp=6, fp=0, fn=44
- generalized_rule: precision=32.56%, recall=56.00%, tp=28, fp=58, fn=22
- discovered_rule: precision=46.30%, recall=100.00%, tp=50, fp=58, fn=0

## Attack-specific accuracy
- paraphrase_attack: 45.00%
- semantic_rewrite_attack: 45.00%
- rule_recombination_attack: 60.00%
- causal_illusion_attack: 25.00%
- transfer_contamination_attack: 35.00%
- reviewer_specific_bias_attack: 50.00%
- abstraction_laundering_attack: 70.00%
- novelty_inflation_attack: 25.00%
- hidden_parent_rule_attack: 25.00%
- interaction_effect_attack: 40.00%

## Top 20 classifier weaknesses
1. [attack_accuracy] `causal_illusion_attack` -> severity=0.7500 (Accuracy 25.00%)
2. [attack_accuracy] `novelty_inflation_attack` -> severity=0.7500 (Accuracy 25.00%)
3. [attack_accuracy] `hidden_parent_rule_attack` -> severity=0.7500 (Accuracy 25.00%)
4. [attack_accuracy] `transfer_contamination_attack` -> severity=0.6500 (Accuracy 35.00%)
5. [attack_accuracy] `interaction_effect_attack` -> severity=0.6000 (Accuracy 40.00%)
6. [attack_accuracy] `paraphrase_attack` -> severity=0.5500 (Accuracy 45.00%)
7. [attack_accuracy] `semantic_rewrite_attack` -> severity=0.5500 (Accuracy 45.00%)
8. [attack_accuracy] `reviewer_specific_bias_attack` -> severity=0.5000 (Accuracy 50.00%)
9. [attack_accuracy] `rule_recombination_attack` -> severity=0.4000 (Accuracy 60.00%)
10. [attack_accuracy] `abstraction_laundering_attack` -> severity=0.3000 (Accuracy 70.00%)
11. [gate_pressure] `threshold_instability` -> severity=0.2500 (50 adversarial cases)
12. [confusion_path] `copied_rule->generalized_rule` -> severity=0.2200 (44 cases)
13. [gate_pressure] `novelty_gate` -> severity=0.2000 (40 adversarial cases)
14. [confusion_path] `ambiguous_borderline->discovered_rule` -> severity=0.1800 (36 cases)
15. [confusion_path] `generalized_rule->discovered_rule` -> severity=0.1100 (22 cases)
16. [confusion_path] `ambiguous_borderline->generalized_rule` -> severity=0.0700 (14 cases)
17. [gate_pressure] `paraphrase_attack` -> severity=0.0500 (10 adversarial cases)
18. [gate_pressure] `semantic_rewrite_attack` -> severity=0.0500 (10 adversarial cases)
19. [gate_pressure] `hidden_parent_rule_attack` -> severity=0.0500 (10 adversarial cases)
20. [gate_pressure] `abstraction_laundering_attack` -> severity=0.0500 (10 adversarial cases)

## Deployment question
- Would Discovery_V2 qualify for deployment if discovered_rule FPR target is <1%? **NO**
- Quantitative justification: observed discovered_rule FDR=53.70%, target<1.00%.
