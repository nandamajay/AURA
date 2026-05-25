# Compile Retry Status

- compile_retries_used: `1`
- compile_retries_limit: `3`
- regeneration_retries_used: `0`
- regeneration_retries_limit: `2`
- semantic_remap_retries_used: `0`
- semantic_remap_retries_limit: `1`

## Stop Conditions
- retries continue only for timeout/resource-guard failures
- semantic or dependency failures fail closed without infinite loop
