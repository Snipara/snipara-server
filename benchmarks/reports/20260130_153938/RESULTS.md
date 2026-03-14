# Snipara Benchmark Results

**Date:** 2026-01-30 15:39:38
**Provider:** openai
**Model:** gpt-4o-mini
**Runs per task:** 3
**Temperature:** 0.0

---

## Executive Summary

| Suite   | Mode                    | CBS   | Quality | Tokens | Cost    | Latency p50 | Success | Halluc. | Prec@5 |
| ------- | ----------------------- | ----- | ------- | ------ | ------- | ----------- | ------- | ------- | ------ |
| docs-qa | llm_alone               | 0.374 | 6.4/10  | 8734   | $0.0014 | 4085 ms     | 57%     | 13.2%   | 8.6%   |
| docs-qa | snipara_ctx_mem         | 0.261 | 4.2/10  | 2704   | $0.0005 | 2623 ms     | 24%     | 19.8%   | 0.0%   |
| docs-qa | snipara_ctx_mem_runtime | 0.428 | 5.3/10  | 2805   | $0.0006 | 7926 ms     | 29%     | 13.9%   | 20.0%  |
| memory  | snipara_ctx_mem         | 0.627 | 6.5/10  | 175    | $0.0001 | 2248 ms     | 50%     | 0.0%    | 0.0%   |
| memory  | snipara_ctx_mem_runtime | 0.584 | 6.7/10  | 321    | $0.0002 | 5486 ms     | 50%     | 0.0%    | 0.0%   |
| coding  | llm_alone               | 0.489 | 8.5/10  | 8945   | $0.0015 | 6103 ms     | 67%     | 0.0%    | 0.0%   |
| coding  | snipara_ctx_mem         | 0.673 | 8.1/10  | 409    | $0.0002 | 5611 ms     | 67%     | 0.0%    | 0.0%   |
| coding  | snipara_ctx_mem_runtime | 0.718 | 9.0/10  | 489    | $0.0003 | 8298 ms     | 100%    | 0.0%    | 0.0%   |

## Suite: docs-qa

### Mode Comparison

| Metric           | llm_alone | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------- | --------------- | ----------------------- |
| Quality (0-10)   | 6.42      | 4.18            | 5.26                    |
| Avg Tokens       | 8734      | 2704            | 2805                    |
| Avg Cost ($)     | 0.00139   | 0.00047         | 0.00056                 |
| Latency p50 (ms) | 4085      | 2623            | 7926                    |
| Latency p95 (ms) | 10085     | 5394            | 21736                   |
| Success Rate     | 57%       | 24%             | 29%                     |
| Hallucination    | 13.2%     | 19.8%           | 13.9%                   |
| Precision@5      | 8.6%      | 0.0%            | 20.0%                   |
| Recall           | 63.4%     | 3.2%            | 15.9%                   |
| CBS              | 0.374     | 0.261           | 0.428                   |

### Per-Task Breakdown

| Task                             | Diff.  | llm_alone (q) | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| -------------------------------- | ------ | ------------- | ------------------- | --------------------------- |
| tech_stack                       | easy   | +8.6          | -5.5                | +7.2                        |
| core_value_prop                  | easy   | +9.5          | -3.8                | -5.3                        |
| mcp_tools                        | easy   | +7.2          | -3.5                | -2.8                        |
| pricing                          | easy   | -6.8          | -0.0                | -3.1                        |
| architecture                     | easy   | -3.0          | -3.0                | -2.9                        |
| token_budgeting                  | easy   | -6.3          | -3.1                | -4.5                        |
| shared_context                   | easy   | +8.5          | -3.6                | -5.6                        |
| oauth_device_flow                | easy   | +8.5          | -2.9                | +8.5                        |
| database_models                  | easy   | -3.5          | -3.5                | -6.0                        |
| layered_architecture             | easy   | -4.0          | -3.5                | -5.0                        |
| cost_benefit_analysis            | hard   | +8.5          | +7.5                | +7.0                        |
| when_to_use_decompose            | medium | +8.1          | +7.2                | +8.5                        |
| search_mode_selection            | medium | +8.1          | +8.5                | -5.5                        |
| full_request_flow                | hard   | +8.0          | -5.6                | -5.6                        |
| security_authentication_chain    | hard   | +8.1          | -0.0                | +8.0                        |
| shared_context_budget_allocation | hard   | +8.5          | -4.0                | +9.7                        |
| nonexistent_feature              | medium | -3.1          | -1.9                | -0.0                        |
| ambiguous_acronym                | easy   | -2.9          | -3.1                | -3.5                        |
| version_specific                 | easy   | -3.4          | -3.1                | -2.9                        |
| error_handling                   | medium | +7.2          | +7.2                | -2.5                        |
| empty_context                    | medium | -2.9          | +7.2                | -6.3                        |

## Suite: memory

### Mode Comparison

| Metric           | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------------- | ----------------------- |
| Quality (0-10)   | 6.45            | 6.72                    |
| Avg Tokens       | 175             | 321                     |
| Avg Cost ($)     | 0.00008         | 0.00016                 |
| Latency p50 (ms) | 2248            | 5486                    |
| Latency p95 (ms) | 4917            | 6861                    |
| Success Rate     | 50%             | 50%                     |
| Hallucination    | 0.0%            | 0.0%                    |
| Precision@5      | 0.0%            | 0.0%                    |
| Recall           | 0.0%            | 0.0%                    |
| CBS              | 0.627           | 0.584                   |

### Per-Task Breakdown

| Task              | Diff.  | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| ----------------- | ------ | ------------------- | --------------------------- |
| mem_store_recall  | easy   | +9.8                | +9.5                        |
| mem_decision_log  | medium | +8.1                | +9.5                        |
| mem_shared_std    | medium | -5.0                | -5.0                        |
| multi_turn_refine | medium | -3.0                | -2.9                        |

## Suite: coding

### Mode Comparison

| Metric           | llm_alone | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------- | --------------- | ----------------------- |
| Quality (0-10)   | 8.45      | 8.08            | 9.00                    |
| Avg Tokens       | 8945      | 409             | 489                     |
| Avg Cost ($)     | 0.00151   | 0.00021         | 0.00025                 |
| Latency p50 (ms) | 6103      | 5611            | 8298                    |
| Latency p95 (ms) | 13302     | 9840            | 11856                   |
| Success Rate     | 67%       | 67%             | 100%                    |
| Hallucination    | 0.0%      | 0.0%            | 0.0%                    |
| Precision@5      | 0.0%      | 0.0%            | 0.0%                    |
| Recall           | 66.7%     | 0.0%            | 0.0%                    |
| CBS              | 0.489     | 0.673           | 0.718                   |

### Per-Task Breakdown

| Task             | Diff.  | llm_alone (q) | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| ---------------- | ------ | ------------- | ------------------- | --------------------------- |
| add_api_endpoint | medium | +9.5          | +9.7                | +10.0                       |
| fix_type_error   | easy   | -6.1          | -6.0                | +7.5                        |
| add_unit_test    | easy   | +9.8          | +8.6                | +9.5                        |

---

_Generated by `suite_benchmark.py` at 2026-01-30 15:39:38_
