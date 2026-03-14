# Snipara Benchmark Results

**Date:** 2026-01-30 18:33:31
**Provider:** openai
**Model:** gpt-4o-mini
**Runs per task:** 3
**Temperature:** 0.0

---

## Executive Summary

| Suite   | Mode                    | CBS   | Quality | Tokens | Cost    | Latency p50 | Success | Halluc. | Prec@5 |
| ------- | ----------------------- | ----- | ------- | ------ | ------- | ----------- | ------- | ------- | ------ |
| docs-qa | llm_alone               | 0.406 | 6.4/10  | 8741   | $0.0014 | 5009 ms     | 57%     | 12.1%   | 10.5%  |
| docs-qa | snipara_ctx_mem         | 0.258 | 4.9/10  | 2708   | $0.0005 | 2894 ms     | 38%     | 16.5%   | 0.0%   |
| docs-qa | snipara_ctx_mem_runtime | 0.357 | 5.8/10  | 3712   | $0.0007 | 7387 ms     | 43%     | 15.7%   | 7.9%   |
| memory  | snipara_ctx_mem         | 0.482 | 6.6/10  | 181    | $0.0001 | 2145 ms     | 50%     | 12.5%   | 0.0%   |
| memory  | snipara_ctx_mem_runtime | 0.545 | 6.7/10  | 322    | $0.0002 | 6452 ms     | 50%     | 0.0%    | 0.0%   |
| coding  | llm_alone               | 0.480 | 8.5/10  | 8946   | $0.0015 | 6703 ms     | 67%     | 0.0%    | 0.0%   |
| coding  | snipara_ctx_mem         | 0.644 | 7.9/10  | 413    | $0.0002 | 6112 ms     | 67%     | 0.0%    | 0.0%   |
| coding  | snipara_ctx_mem_runtime | 0.718 | 9.1/10  | 473    | $0.0002 | 9830 ms     | 100%    | 0.0%    | 0.0%   |

## Suite: docs-qa

### Mode Comparison

| Metric           | llm_alone | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------- | --------------- | ----------------------- |
| Quality (0-10)   | 6.43      | 4.89            | 5.76                    |
| Avg Tokens       | 8741      | 2708            | 3712                    |
| Avg Cost ($)     | 0.00140   | 0.00048         | 0.00072                 |
| Latency p50 (ms) | 5009      | 2894            | 7387                    |
| Latency p95 (ms) | 11626     | 7445            | 17572                   |
| Success Rate     | 57%       | 38%             | 43%                     |
| Hallucination    | 12.1%     | 16.5%           | 15.7%                   |
| Precision@5      | 10.5%     | 0.0%            | 7.9%                    |
| Recall           | 62.1%     | 13.7%           | 21.0%                   |
| CBS              | 0.406     | 0.258           | 0.357                   |

### Per-Task Breakdown

| Task                             | Diff.  | llm_alone (q) | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| -------------------------------- | ------ | ------------- | ------------------- | --------------------------- |
| tech_stack                       | easy   | +8.1          | -3.4                | -6.0                        |
| core_value_prop                  | easy   | +9.5          | -2.9                | -3.5                        |
| mcp_tools                        | easy   | +7.2          | +7.0                | +7.2                        |
| pricing                          | easy   | -6.8          | -0.0                | -3.1                        |
| architecture                     | easy   | -4.0          | -5.5                | -5.3                        |
| token_budgeting                  | easy   | -6.3          | -4.2                | -4.0                        |
| shared_context                   | easy   | +8.5          | +8.1                | +8.5                        |
| oauth_device_flow                | easy   | +8.5          | -2.5                | +8.5                        |
| database_models                  | easy   | -3.4          | -5.5                | -5.5                        |
| layered_architecture             | easy   | -4.0          | -3.9                | -4.1                        |
| cost_benefit_analysis            | hard   | +8.5          | +7.3                | +7.0                        |
| when_to_use_decompose            | medium | +8.1          | +7.0                | +8.0                        |
| search_mode_selection            | medium | +8.1          | +8.1                | +8.5                        |
| full_request_flow                | hard   | +8.0          | -5.6                | -5.0                        |
| security_authentication_chain    | hard   | +8.1          | -0.0                | +7.0                        |
| shared_context_budget_allocation | hard   | +9.5          | +8.1                | +9.5                        |
| nonexistent_feature              | medium | -1.9          | -2.9                | -0.0                        |
| ambiguous_acronym                | easy   | -2.9          | -3.5                | -2.9                        |
| version_specific                 | easy   | -3.4          | -3.0                | -2.9                        |
| error_handling                   | medium | +7.2          | +7.1                | +8.1                        |
| empty_context                    | medium | -2.9          | +7.2                | -6.4                        |

## Suite: memory

### Mode Comparison

| Metric           | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------------- | ----------------------- |
| Quality (0-10)   | 6.59            | 6.72                    |
| Avg Tokens       | 181             | 322                     |
| Avg Cost ($)     | 0.00008         | 0.00016                 |
| Latency p50 (ms) | 2145            | 6452                    |
| Latency p95 (ms) | 7032            | 9473                    |
| Success Rate     | 50%             | 50%                     |
| Hallucination    | 12.5%           | 0.0%                    |
| Precision@5      | 0.0%            | 0.0%                    |
| Recall           | 0.0%            | 0.0%                    |
| CBS              | 0.482           | 0.545                   |

### Per-Task Breakdown

| Task              | Diff.  | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| ----------------- | ------ | ------------------- | --------------------------- |
| mem_store_recall  | easy   | +9.8                | +9.5                        |
| mem_decision_log  | medium | +8.1                | +9.5                        |
| mem_shared_std    | medium | -5.0                | -5.0                        |
| multi_turn_refine | medium | -3.5                | -2.9                        |

## Suite: coding

### Mode Comparison

| Metric           | llm_alone | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------- | --------------- | ----------------------- |
| Quality (0-10)   | 8.53      | 7.90            | 9.07                    |
| Avg Tokens       | 8946      | 413             | 473                     |
| Avg Cost ($)     | 0.00152   | 0.00022         | 0.00024                 |
| Latency p50 (ms) | 6703      | 6112            | 9830                    |
| Latency p95 (ms) | 12784     | 10444           | 13415                   |
| Success Rate     | 67%       | 67%             | 100%                    |
| Hallucination    | 0.0%      | 0.0%            | 0.0%                    |
| Precision@5      | 0.0%      | 0.0%            | 0.0%                    |
| Recall           | 66.7%     | 0.0%            | 0.0%                    |
| CBS              | 0.480     | 0.644           | 0.718                   |

### Per-Task Breakdown

| Task             | Diff.  | llm_alone (q) | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| ---------------- | ------ | ------------- | ------------------- | --------------------------- |
| add_api_endpoint | medium | +10.0         | +9.7                | +9.7                        |
| fix_type_error   | easy   | -6.1          | -6.0                | +8.0                        |
| add_unit_test    | easy   | +9.5          | +8.0                | +9.5                        |

---

_Generated by `suite_benchmark.py` at 2026-01-30 18:33:31_
