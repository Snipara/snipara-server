# Snipara Benchmark Results

**Date:** 2026-01-31 15:23:15
**Provider:** openai
**Model:** gpt-4o-mini
**Runs per task:** 3
**Temperature:** 0.0

---

## Executive Summary

| Suite   | Mode                    | CBS   | Quality | Tokens | Cost    | Latency p50 | Success | Halluc. | Prec@5 |
| ------- | ----------------------- | ----- | ------- | ------ | ------- | ----------- | ------- | ------- | ------ |
| docs-qa | llm_alone               | 0.298 | 6.6/10  | 8740   | $0.0014 | 3955 ms     | 62%     | 23.4%   | 10.5%  |
| docs-qa | snipara_ctx_mem         | 0.465 | 5.4/10  | 2890   | $0.0005 | 2568 ms     | 43%     | 17.1%   | 38.1%  |
| docs-qa | snipara_ctx_mem_runtime | 0.428 | 6.3/10  | 3747   | $0.0007 | 7750 ms     | 52%     | 23.8%   | 38.1%  |
| memory  | snipara_ctx_mem         | 0.487 | 8.3/10  | 5319   | $0.0008 | 4459 ms     | 75%     | 25.0%   | 0.0%   |
| memory  | snipara_ctx_mem_runtime | 0.273 | 6.8/10  | 3994   | $0.0007 | 9950 ms     | 50%     | 25.0%   | 0.0%   |
| coding  | llm_alone               | 0.466 | 7.8/10  | 8950   | $0.0015 | 6380 ms     | 67%     | 0.0%    | 0.0%   |
| coding  | snipara_ctx_mem         | 0.693 | 7.8/10  | 411    | $0.0002 | 4815 ms     | 67%     | 0.0%    | 0.0%   |
| coding  | snipara_ctx_mem_runtime | 0.762 | 8.3/10  | 487    | $0.0003 | 7065 ms     | 100%    | 0.0%    | 0.0%   |

## Suite: docs-qa

### Mode Comparison

| Metric           | llm_alone | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------- | --------------- | ----------------------- |
| Quality (0-10)   | 6.59      | 5.35            | 6.28                    |
| Avg Tokens       | 8740      | 2890            | 3747                    |
| Avg Cost ($)     | 0.00140   | 0.00051         | 0.00070                 |
| Latency p50 (ms) | 3955      | 2568            | 7750                    |
| Latency p95 (ms) | 7161      | 5761            | 12910                   |
| Success Rate     | 62%       | 43%             | 52%                     |
| Hallucination    | 23.4%     | 17.1%           | 23.8%                   |
| Precision@5      | 10.5%     | 38.1%           | 38.1%                   |
| Recall           | 62.1%     | 42.9%           | 47.2%                   |
| CBS              | 0.298     | 0.465           | 0.428                   |

### Per-Task Breakdown

| Task                             | Diff.  | llm_alone (q) | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| -------------------------------- | ------ | ------------- | ------------------- | --------------------------- |
| tech_stack                       | easy   | +8.6          | +8.1                | +8.6                        |
| core_value_prop                  | easy   | +8.5          | +8.0                | +9.5                        |
| mcp_tools                        | easy   | +7.0          | -3.4                | -2.9                        |
| pricing                          | easy   | -6.5          | -6.1                | -6.1                        |
| architecture                     | easy   | -3.4          | -4.1                | -4.1                        |
| token_budgeting                  | easy   | +7.1          | -4.1                | -4.8                        |
| shared_context                   | easy   | +8.5          | +8.1                | +9.0                        |
| oauth_device_flow                | easy   | +8.5          | +8.0                | +8.0                        |
| database_models                  | easy   | -5.5          | -2.6                | -2.9                        |
| layered_architecture             | easy   | -4.0          | +7.2                | +8.0                        |
| cost_benefit_analysis            | hard   | +8.5          | +7.2                | +8.1                        |
| when_to_use_decompose            | medium | +8.1          | +7.2                | +8.5                        |
| search_mode_selection            | medium | +8.1          | -4.0                | -5.5                        |
| full_request_flow                | hard   | +8.0          | -6.0                | -6.0                        |
| security_authentication_chain    | hard   | +8.1          | +8.1                | +8.0                        |
| shared_context_budget_allocation | hard   | +9.5          | -4.1                | +9.5                        |
| nonexistent_feature              | medium | -3.4          | -0.0                | -0.0                        |
| ambiguous_acronym                | easy   | -3.5          | -3.5                | -3.5                        |
| version_specific                 | easy   | -3.4          | -0.0                | -2.9                        |
| error_handling                   | medium | +7.2          | +7.2                | +8.0                        |
| empty_context                    | medium | -2.9          | -5.3                | +8.1                        |

## Suite: memory

### Mode Comparison

| Metric           | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------------- | ----------------------- |
| Quality (0-10)   | 8.30            | 6.79                    |
| Avg Tokens       | 5319            | 3994                    |
| Avg Cost ($)     | 0.00085         | 0.00071                 |
| Latency p50 (ms) | 4459            | 9950                    |
| Latency p95 (ms) | 6907            | 16682                   |
| Success Rate     | 75%             | 50%                     |
| Hallucination    | 25.0%           | 25.0%                   |
| Precision@5      | 0.0%            | 0.0%                    |
| Recall           | 50.0%           | 25.0%                   |
| CBS              | 0.487           | 0.273                   |

### Per-Task Breakdown

| Task              | Diff.  | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| ----------------- | ------ | ------------------- | --------------------------- |
| mem_store_recall  | easy   | +9.8                | +9.8                        |
| mem_decision_log  | medium | +8.5                | +9.5                        |
| mem_shared_std    | medium | +8.1                | -5.0                        |
| multi_turn_refine | medium | -6.8                | -2.9                        |

## Suite: coding

### Mode Comparison

| Metric           | llm_alone | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------- | --------------- | ----------------------- |
| Quality (0-10)   | 7.77      | 7.83            | 8.35                    |
| Avg Tokens       | 8950      | 411             | 487                     |
| Avg Cost ($)     | 0.00152   | 0.00022         | 0.00025                 |
| Latency p50 (ms) | 6380      | 4815            | 7065                    |
| Latency p95 (ms) | 30713     | 10140           | 10759                   |
| Success Rate     | 67%       | 67%             | 100%                    |
| Hallucination    | 0.0%      | 0.0%            | 0.0%                    |
| Precision@5      | 0.0%      | 0.0%            | 0.0%                    |
| Recall           | 66.7%     | 0.0%            | 0.0%                    |
| CBS              | 0.466     | 0.693           | 0.762                   |

### Per-Task Breakdown

| Task             | Diff.  | llm_alone (q) | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| ---------------- | ------ | ------------- | ------------------- | --------------------------- |
| add_api_endpoint | medium | +9.7          | +9.5                | +9.0                        |
| fix_type_error   | easy   | -3.9          | -6.0                | +7.5                        |
| add_unit_test    | easy   | +9.8          | +8.0                | +8.6                        |

---

_Generated by `suite_benchmark.py` at 2026-01-31 15:23:15_
