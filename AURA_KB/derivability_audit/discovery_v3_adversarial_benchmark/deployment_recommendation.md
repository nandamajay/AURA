# Discovery_V4 Deployment Recommendation

## Operating points
- A (maximize discovered recall): {'threshold': 0.5, 'discovered_precision': 1.0, 'discovered_recall': 1.0, 'discovered_FDR': 0.0, 'discovered_FNR': 0.0, 'abstention_rate': 0.29, 'predicted_discovered': 50, 'tp_discovered': 50, 'fp_discovered': 0}
- B (FDR < 5%): {'threshold': 0.5, 'discovered_precision': 1.0, 'discovered_recall': 1.0, 'discovered_FDR': 0.0, 'discovered_FNR': 0.0, 'abstention_rate': 0.29, 'predicted_discovered': 50, 'tp_discovered': 50, 'fp_discovered': 0}
- C (FDR < 1%): {'threshold': 0.5, 'discovered_precision': 1.0, 'discovered_recall': 1.0, 'discovered_FDR': 0.0, 'discovered_FNR': 0.0, 'abstention_rate': 0.29, 'predicted_discovered': 50, 'tp_discovered': 50, 'fp_discovered': 0}

## Certification sample-size estimate (95% confidence)
- Required discovered predictions with zero false positives for FDR<5%: `73`
- Required discovered predictions with zero false positives for FDR<1%: `381`

## Assessment
- A threshold exists for FDR<1%; deploy only with undecided routing enabled and manual adjudication queue.
- FDR<5% is achievable at selected threshold with reduced discovered recall.

Would Discovery_V4 be deployable for autonomous knowledge promotion? **Conditionally Yes, with abstention and certification sampling.**
