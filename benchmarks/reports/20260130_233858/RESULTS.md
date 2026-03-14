# Snipara Benchmark Results

**Date:** 2026-01-30 23:38:58
**Provider:** openai
**Model:** gpt-4o-mini
**Runs per task:** 3
**Temperature:** 0.0

---

## Executive Summary

| Suite   | Mode                    | CBS   | Quality | Tokens | Cost    | Latency p50 | Success | Halluc. | Prec@5 |
| ------- | ----------------------- | ----- | ------- | ------ | ------- | ----------- | ------- | ------- | ------ |
| docs-qa | llm_alone               | 0.450 | 6.4/10  | 8732   | $0.0014 | 3790 ms     | 57%     | 18.0%   | 10.5%  |
| docs-qa | snipara_ctx_mem         | 0.454 | 5.1/10  | 2916   | $0.0005 | 3271 ms     | 29%     | 16.8%   | 5.7%   |
| docs-qa | snipara_ctx_mem_runtime | 0.426 | 5.6/10  | 4313   | $0.0008 | 6855 ms     | 48%     | 16.8%   | 7.6%   |
| memory  | snipara_ctx_mem         | 0.472 | 6.7/10  | 2787   | $0.0005 | 2044 ms     | 50%     | 33.8%   | 0.0%   |
| memory  | snipara_ctx_mem_runtime | 0.506 | 7.0/10  | 4202   | $0.0008 | 6913 ms     | 75%     | 6.7%    | 0.0%   |
| coding  | llm_alone               | 0.436 | 7.9/10  | 8907   | $0.0015 | 7072 ms     | 67%     | 0.0%    | 0.0%   |
| coding  | snipara_ctx_mem         | 0.617 | 7.2/10  | 2935   | $0.0006 | 5060 ms     | 67%     | 0.0%    | 0.0%   |
| coding  | snipara_ctx_mem_runtime | 0.701 | 8.5/10  | 4250   | $0.0008 | 5899 ms     | 100%    | 0.0%    | 0.0%   |

## Suite: docs-qa

### Mode Comparison

| Metric           | llm_alone | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------- | --------------- | ----------------------- |
| Quality (0-10)   | 6.38      | 5.09            | 5.57                    |
| Avg Tokens       | 8732      | 2916            | 4313                    |
| Avg Cost ($)     | 0.00139   | 0.00052         | 0.00081                 |
| Latency p50 (ms) | 3790      | 3271            | 6855                    |
| Latency p95 (ms) | 7489      | 9305            | 19282                   |
| Success Rate     | 57%       | 29%             | 48%                     |
| Hallucination    | 18.0%     | 16.8%           | 16.8%                   |
| Precision@5      | 10.5%     | 5.7%            | 7.6%                    |
| Recall           | 62.1%     | 13.0%           | 20.1%                   |
| CBS              | 0.450     | 0.454           | 0.426                   |

### Per-Task Breakdown

| Task                             | Diff.  | llm_alone (q) | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| -------------------------------- | ------ | ------------- | ------------------- | --------------------------- |
| tech_stack                       | easy   | +8.6          | -5.3                | +7.5                        |
| core_value_prop                  | easy   | +8.5          | -3.5                | -4.3                        |
| mcp_tools                        | easy   | +7.0          | -6.3                | +7.0                        |
| pricing                          | easy   | -6.8          | -4.1                | -3.1                        |
| architecture                     | easy   | -4.0          | -5.0                | -5.8                        |
| token_budgeting                  | easy   | -5.5          | -5.5                | -3.6                        |
| shared_context                   | easy   | +8.5          | +8.1                | +8.5                        |
| oauth_device_flow                | easy   | +8.5          | -0.0                | +8.5                        |
| database_models                  | easy   | -3.4          | -4.3                | -5.5                        |
| layered_architecture             | easy   | -4.0          | -4.0                | -4.0                        |
| cost_benefit_analysis            | hard   | +8.5          | +8.0                | +7.3                        |
| when_to_use_decompose            | medium | +8.1          | +8.1                | +8.0                        |
| search_mode_selection            | medium | +8.1          | +8.1                | +8.5                        |
| full_request_flow                | hard   | +8.0          | -5.0                | -5.6                        |
| security_authentication_chain    | hard   | +8.1          | -0.0                | -0.0                        |
| shared_context_budget_allocation | hard   | +8.5          | +9.1                | +9.5                        |
| nonexistent_feature              | medium | -3.4          | -2.9                | -0.0                        |
| ambiguous_acronym                | easy   | -2.9          | -3.1                | -2.9                        |
| version_specific                 | easy   | -3.4          | -2.9                | -1.6                        |
| error_handling                   | medium | +7.2          | +7.2                | +8.0                        |
| empty_context                    | medium | -2.9          | -6.3                | +7.8                        |

## Suite: memory

### Mode Comparison

| Metric           | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------------- | ----------------------- |
| Quality (0-10)   | 6.69            | 6.97                    |
| Avg Tokens       | 2787            | 4202                    |
| Avg Cost ($)     | 0.00046         | 0.00075                 |
| Latency p50 (ms) | 2044            | 6913                    |
| Latency p95 (ms) | 3240            | 7928                    |
| Success Rate     | 50%             | 75%                     |
| Hallucination    | 33.8%           | 6.7%                    |
| Precision@5      | 0.0%            | 0.0%                    |
| Recall           | 0.0%            | 12.5%                   |
| CBS              | 0.472           | 0.506                   |

### Per-Task Breakdown

| Task              | Diff.  | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| ----------------- | ------ | ------------------- | --------------------------- |
| mem_store_recall  | easy   | +9.8                | +9.5                        |
| mem_decision_log  | medium | +8.1                | +8.5                        |
| mem_shared_std    | medium | -5.5                | +7.0                        |
| multi_turn_refine | medium | -3.4                | -2.9                        |

## Suite: coding

### Mode Comparison

| Metric           | llm_alone | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------- | --------------- | ----------------------- |
| Quality (0-10)   | 7.92      | 7.18            | 8.50                    |
| Avg Tokens       | 8907      | 2935            | 4250                    |
| Avg Cost ($)     | 0.00149   | 0.00057         | 0.00082                 |
| Latency p50 (ms) | 7072      | 5060            | 5899                    |
| Latency p95 (ms) | 21986     | 12655           | 10165                   |
| Success Rate     | 67%       | 67%             | 100%                    |
| Hallucination    | 0.0%      | 0.0%            | 0.0%                    |
| Precision@5      | 0.0%      | 0.0%            | 0.0%                    |
| Recall           | 66.7%     | 0.0%            | 0.0%                    |
| CBS              | 0.436     | 0.617           | 0.701                   |

### Per-Task Breakdown

| Task             | Diff.  | llm_alone (q) | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| ---------------- | ------ | ------------- | ------------------- | --------------------------- |
| add_api_endpoint | medium | +9.5          | +9.7                | +10.0                       |
| fix_type_error   | easy   | -4.5          | +8.0                | +8.0                        |
| add_unit_test    | easy   | +9.8          | -3.9                | +7.5                        |

---

_Generated by `suite_benchmark.py` at 2026-01-30 23:38:58_
