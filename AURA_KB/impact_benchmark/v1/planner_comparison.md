# Planner Comparison

## Pairwise Mean Deltas
- A vs B: {'acceptance_probability_delta': 0.0674, 'objection_reduction': 0.3803, 'review_round_reduction': 0.27, 'latency_reduction': 1.5657, 'planner_confidence_gain': 0.0365}
- B vs C: {'acceptance_probability_delta': 0.0295, 'objection_reduction': 0.2013, 'review_round_reduction': 0.04, 'latency_reduction': 0.5508, 'planner_confidence_gain': 0.0266}
- A vs C: {'acceptance_probability_delta': 0.0969, 'objection_reduction': 0.5816, 'review_round_reduction': 0.31, 'latency_reduction': 2.1165, 'planner_confidence_gain': 0.0631}

## Interpretation
- Positive acceptance delta and reductions in objections/rounds/latency indicate better planning quality.
- B vs C isolates discovered_rule contribution over generalized knowledge.
