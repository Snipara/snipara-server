# Snipara Benchmark Results

**Date:** 2026-01-31 05:59:50
**Provider:** openai
**Model:** gpt-4o-mini
**Runs per task:** 3
**Temperature:** 0.0

---

## Executive Summary

| Suite   | Mode                    | CBS   | Quality | Tokens | Cost    | Latency p50 | Success | Halluc. | Prec@5 |
| ------- | ----------------------- | ----- | ------- | ------ | ------- | ----------- | ------- | ------- | ------ |
| docs-qa | llm_alone               | 0.365 | 6.4/10  | 8737   | $0.0014 | 3489 ms     | 57%     | 24.3%   | 10.5%  |
| docs-qa | snipara_ctx_mem         | 0.500 | 5.3/10  | 4910   | $0.0008 | 3120 ms     | 24%     | 14.9%   | 12.4%  |
| docs-qa | snipara_ctx_mem_runtime | 0.425 | 6.2/10  | 6673   | $0.0012 | 6952 ms     | 43%     | 18.0%   | 12.4%  |
| memory  | snipara_ctx_mem         | 0.464 | 6.8/10  | 5300   | $0.0009 | 4092 ms     | 75%     | 32.9%   | 0.0%   |
| memory  | snipara_ctx_mem_runtime | 0.586 | 8.4/10  | 7080   | $0.0012 | 6174 ms     | 100%    | 9.5%    | 0.0%   |
| coding  | llm_alone               | 0.469 | 8.3/10  | 8915   | $0.0015 | 7596 ms     | 67%     | 0.0%    | 0.0%   |
| coding  | snipara_ctx_mem         | 0.880 | 9.0/10  | 5764   | $0.0010 | 6556 ms     | 100%    | 0.0%    | 20.0%  |
| coding  | snipara_ctx_mem_runtime | 0.702 | 8.6/10  | 7799   | $0.0014 | 9716 ms     | 100%    | 0.0%    | 20.0%  |

## Suite: docs-qa

### Mode Comparison

| Metric           | llm_alone | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------- | --------------- | ----------------------- |
| Quality (0-10)   | 6.38      | 5.26            | 6.17                    |
| Avg Tokens       | 8737      | 4910            | 6673                    |
| Avg Cost ($)     | 0.00140   | 0.00081         | 0.00116                 |
| Latency p50 (ms) | 3489      | 3120            | 6952                    |
| Latency p95 (ms) | 6130      | 7536            | 14739                   |
| Success Rate     | 57%       | 24%             | 43%                     |
| Hallucination    | 24.3%     | 14.9%           | 18.0%                   |
| Precision@5      | 10.5%     | 12.4%           | 12.4%                   |
| Recall           | 62.1%     | 22.9%           | 24.1%                   |
| CBS              | 0.365     | 0.500           | 0.425                   |

### Per-Task Breakdown

| Task                             | Diff.  | llm_alone (q) | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| -------------------------------- | ------ | ------------- | ------------------- | --------------------------- |
| tech_stack                       | easy   | +8.1          | -5.5                | -6.0                        |
| core_value_prop                  | easy   | +8.5          | -5.8                | -5.4                        |
| mcp_tools                        | easy   | +7.8          | -5.5                | -5.5                        |
| pricing                          | easy   | -6.8          | -3.3                | -5.1                        |
| architecture                     | easy   | -3.4          | -3.0                | -2.9                        |
| token_budgeting                  | easy   | -6.1          | -6.4                | -5.5                        |
| shared_context                   | easy   | +8.4          | -2.9                | -3.5                        |
| oauth_device_flow                | easy   | +8.5          | +8.1                | +10.0                       |
| database_models                  | easy   | -3.5          | -5.5                | -6.5                        |
| layered_architecture             | easy   | -4.0          | -5.5                | +9.5                        |
| cost_benefit_analysis            | hard   | +8.5          | +7.2                | +8.5                        |
| when_to_use_decompose            | medium | +8.1          | +7.2                | +8.0                        |
| search_mode_selection            | medium | +8.1          | +8.1                | +9.5                        |
| full_request_flow                | hard   | +8.0          | -4.7                | -5.0                        |
| security_authentication_chain    | hard   | +8.1          | +8.1                | +8.1                        |
| shared_context_budget_allocation | hard   | +9.5          | -4.1                | +9.5                        |
| nonexistent_feature              | medium | -1.5          | -1.9                | -0.0                        |
| ambiguous_acronym                | easy   | -3.5          | -3.1                | -3.1                        |
| version_specific                 | easy   | -3.4          | -2.9                | -2.9                        |
| error_handling                   | medium | +7.2          | -6.3                | +7.2                        |
| empty_context                    | medium | -2.9          | -5.3                | +7.8                        |

## Suite: memory

### Mode Comparison

| Metric           | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------------- | ----------------------- |
| Quality (0-10)   | 6.85            | 8.39                    |
| Avg Tokens       | 5300            | 7080                    |
| Avg Cost ($)     | 0.00085         | 0.00116                 |
| Latency p50 (ms) | 4092            | 6174                    |
| Latency p95 (ms) | 5825            | 7085                    |
| Success Rate     | 75%             | 100%                    |
| Hallucination    | 32.9%           | 9.5%                    |
| Precision@5      | 0.0%            | 0.0%                    |
| Recall           | 12.5%           | 12.5%                   |
| CBS              | 0.464           | 0.586                   |

### Per-Task Breakdown

| Task              | Diff.  | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| ----------------- | ------ | ------------------- | --------------------------- |
| mem_store_recall  | easy   | +9.8                | +9.5                        |
| mem_decision_log  | medium | +8.5                | +9.5                        |
| mem_shared_std    | medium | +7.2                | +7.2                        |
| multi_turn_refine | medium | -1.9                | +7.3                        |

## Suite: coding

### Mode Comparison

| Metric           | llm_alone | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------- | --------------- | ----------------------- |
| Quality (0-10)   | 8.33      | 9.00            | 8.57                    |
| Avg Tokens       | 8915      | 5764            | 7799                    |
| Avg Cost ($)     | 0.00150   | 0.00098         | 0.00137                 |
| Latency p50 (ms) | 7596      | 6556            | 9716                    |
| Latency p95 (ms) | 11355     | 7083            | 11769                   |
| Success Rate     | 67%       | 100%            | 100%                    |
| Hallucination    | 0.0%      | 0.0%            | 0.0%                    |
| Precision@5      | 0.0%      | 20.0%           | 20.0%                   |
| Recall           | 66.7%     | 50.0%           | 50.0%                   |
| CBS              | 0.469     | 0.880           | 0.702                   |

### Per-Task Breakdown

| Task             | Diff.  | llm_alone (q) | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| ---------------- | ------ | ------------- | ------------------- | --------------------------- |
| add_api_endpoint | medium | +9.5          | +9.5                | +9.7                        |
| fix_type_error   | easy   | -6.0          | +8.0                | +7.5                        |
| add_unit_test    | easy   | +9.5          | +9.5                | +8.5                        |

---

_Generated by `suite_benchmark.py` at 2026-01-31 05:59:50_
