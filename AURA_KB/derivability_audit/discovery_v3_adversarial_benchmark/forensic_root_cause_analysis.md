# Discovery_V2 Forensic Root-Cause Analysis

- Baseline discovered FDR: 53.70% (58/108)
- Extracted discovered false positives: 58

## Ranked clusters by FDR contribution
1. `threshold_instability_borderline` count=36 share=62.07% est_FDR_reduction=23.15pp
2. `hidden_parent_rule` count=10 share=17.24% est_FDR_reduction=4.72pp
3. `causal_illusion` count=10 share=17.24% est_FDR_reduction=4.72pp
4. `novelty_inflation` count=10 share=17.24% est_FDR_reduction=4.72pp
5. `transfer_contamination` count=8 share=13.79% est_FDR_reduction=3.70pp
6. `interaction_effect_false_positive` count=7 share=12.07% est_FDR_reduction=3.21pp
7. `reviewer_specific_bias` count=3 share=5.17% est_FDR_reduction=1.32pp
8. `derivable_rule_mistaken_as_discovery` count=2 share=3.45% est_FDR_reduction=0.87pp
9. `rule_recombination` count=0 share=0.00% est_FDR_reduction=0.00pp
10. `abstraction_laundering` count=0 share=0.00% est_FDR_reduction=0.00pp
11. `benchmark_leakage` count=0 share=0.00% est_FDR_reduction=0.00pp

## Discovery_V3 replay metrics
- discovered precision: 100.00%
- discovered recall: 100.00%
- discovered FDR: 0.00%
- discovered FNR: 0.00%
- overall accuracy: 53.00%
- discovered FDR 95% Wilson CI: [0.00%, 7.14%]
- FDR<5% feasible at 95% CI? NO
- FDR<1% feasible at 95% CI? NO
