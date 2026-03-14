# Snipara Benchmark Results

**Date:** 2026-01-31 09:14:50
**Provider:** openai
**Model:** gpt-4o-mini
**Runs per task:** 3
**Temperature:** 0.0

---

## Executive Summary

| Suite   | Mode                    | CBS   | Quality | Tokens | Cost    | Latency p50 | Success | Halluc. | Prec@5 |
| ------- | ----------------------- | ----- | ------- | ------ | ------- | ----------- | ------- | ------- | ------ |
| docs-qa | llm_alone               | 0.314 | 6.3/10  | 8734   | $0.0014 | 4193 ms     | 52%     | 13.1%   | 10.5%  |
| docs-qa | snipara_ctx_mem         | 0.470 | 5.3/10  | 3091   | $0.0005 | 2866 ms     | 43%     | 13.7%   | 35.2%  |
| docs-qa | snipara_ctx_mem_runtime | 0.427 | 6.2/10  | 4006   | $0.0007 | 6263 ms     | 52%     | 22.2%   | 35.2%  |
| memory  | snipara_ctx_mem         | 0.592 | 6.9/10  | 1154   | $0.0002 | 3155 ms     | 50%     | 0.0%    | 0.0%   |
| memory  | snipara_ctx_mem_runtime | 0.561 | 7.2/10  | 1636   | $0.0003 | 5937 ms     | 75%     | 6.4%    | 0.0%   |
| coding  | llm_alone               | 0.472 | 8.5/10  | 8973   | $0.0015 | 8895 ms     | 67%     | 0.0%    | 0.0%   |
| coding  | snipara_ctx_mem         | 0.665 | 8.1/10  | 404    | $0.0002 | 7168 ms     | 67%     | 0.0%    | 0.0%   |
| coding  | snipara_ctx_mem_runtime | 0.713 | 8.4/10  | 475    | $0.0002 | 9216 ms     | 100%    | 0.0%    | 0.0%   |

## Suite: docs-qa

### Mode Comparison

| Metric           | llm_alone | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------- | --------------- | ----------------------- |
| Quality (0-10)   | 6.32      | 5.25            | 6.20                    |
| Avg Tokens       | 8734      | 3091            | 4006                    |
| Avg Cost ($)     | 0.00140   | 0.00053         | 0.00074                 |
| Latency p50 (ms) | 4193      | 2866            | 6263                    |
| Latency p95 (ms) | 8767      | 7182            | 11710                   |
| Success Rate     | 52%       | 43%             | 52%                     |
| Hallucination    | 13.1%     | 13.7%           | 22.2%                   |
| Precision@5      | 10.5%     | 35.2%           | 35.2%                   |
| Recall           | 62.1%     | 40.5%           | 44.8%                   |
| CBS              | 0.314     | 0.470           | 0.427                   |

### Per-Task Breakdown

| Task                             | Diff.  | llm_alone (q) | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| -------------------------------- | ------ | ------------- | ------------------- | --------------------------- |
| tech_stack                       | easy   | +8.1          | +8.1                | +8.6                        |
| core_value_prop                  | easy   | +8.5          | +8.0                | +9.5                        |
| mcp_tools                        | easy   | +7.0          | -3.4                | -2.9                        |
| pricing                          | easy   | -6.8          | -2.9                | -3.4                        |
| architecture                     | easy   | -4.1          | -4.5                | -5.1                        |
| token_budgeting                  | easy   | -6.1          | -3.1                | -3.5                        |
| shared_context                   | easy   | +8.5          | +8.0                | +9.0                        |
| oauth_device_flow                | easy   | +8.5          | +8.0                | +8.5                        |
| database_models                  | easy   | -3.5          | -2.9                | -2.5                        |
| layered_architecture             | easy   | -4.0          | +8.0                | +8.0                        |
| cost_benefit_analysis            | hard   | +8.5          | +7.2                | +8.5                        |
| when_to_use_decompose            | medium | +8.1          | +7.2                | +8.5                        |
| search_mode_selection            | medium | +8.1          | -4.0                | -5.5                        |
| full_request_flow                | hard   | -6.8          | -6.0                | -6.8                        |
| security_authentication_chain    | hard   | +8.1          | +8.1                | +8.1                        |
| shared_context_budget_allocation | hard   | +9.5          | -4.1                | +9.5                        |
| nonexistent_feature              | medium | -1.9          | -0.0                | -0.0                        |
| ambiguous_acronym                | easy   | -2.9          | -3.5                | -3.5                        |
| version_specific                 | easy   | -3.4          | -0.0                | -3.0                        |
| error_handling                   | medium | +7.2          | +7.2                | +8.1                        |
| empty_context                    | medium | -2.9          | -6.1                | +7.8                        |

## Suite: memory

### Mode Comparison

| Metric           | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------------- | ----------------------- |
| Quality (0-10)   | 6.91            | 7.22                    |
| Avg Tokens       | 1154            | 1636                    |
| Avg Cost ($)     | 0.00021         | 0.00035                 |
| Latency p50 (ms) | 3155            | 5937                    |
| Latency p95 (ms) | 3449            | 9311                    |
| Success Rate     | 50%             | 75%                     |
| Hallucination    | 0.0%            | 6.4%                    |
| Precision@5      | 0.0%            | 0.0%                    |
| Recall           | 12.5%           | 12.5%                   |
| CBS              | 0.592           | 0.561                   |

### Per-Task Breakdown

| Task              | Diff.  | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| ----------------- | ------ | ------------------- | --------------------------- |
| mem_store_recall  | easy   | +9.8                | +9.5                        |
| mem_decision_log  | medium | +8.5                | +9.5                        |
| mem_shared_std    | medium | -6.5                | +7.0                        |
| multi_turn_refine | medium | -2.9                | -2.9                        |

## Suite: coding

### Mode Comparison

| Metric           | llm_alone | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------- | --------------- | ----------------------- |
| Quality (0-10)   | 8.53      | 8.08            | 8.40                    |
| Avg Tokens       | 8973      | 404             | 475                     |
| Avg Cost ($)     | 0.00153   | 0.00021         | 0.00025                 |
| Latency p50 (ms) | 8895      | 7168            | 9216                    |
| Latency p95 (ms) | 14606     | 14029           | 13899                   |
| Success Rate     | 67%       | 67%             | 100%                    |
| Hallucination    | 0.0%      | 0.0%            | 0.0%                    |
| Precision@5      | 0.0%      | 0.0%            | 0.0%                    |
| Recall           | 66.7%     | 0.0%            | 0.0%                    |
| CBS              | 0.472     | 0.665           | 0.713                   |

### Per-Task Breakdown

| Task             | Diff.  | llm_alone (q) | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| ---------------- | ------ | ------------- | ------------------- | --------------------------- |
| add_api_endpoint | medium | +10.0         | +9.7                | +9.7                        |
| fix_type_error   | easy   | -6.1          | -6.0                | +7.5                        |
| add_unit_test    | easy   | +9.5          | +8.6                | +8.0                        |

---

_Generated by `suite_benchmark.py` at 2026-01-31 09:14:50_
