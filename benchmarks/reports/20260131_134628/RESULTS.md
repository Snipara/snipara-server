# Snipara Benchmark Results

**Date:** 2026-01-31 13:46:28
**Provider:** openai
**Model:** gpt-4o-mini
**Runs per task:** 3
**Temperature:** 0.0

---

## Executive Summary

| Suite   | Mode                    | CBS   | Quality | Tokens | Cost    | Latency p50 | Success | Halluc. | Prec@5 |
| ------- | ----------------------- | ----- | ------- | ------ | ------- | ----------- | ------- | ------- | ------ |
| docs-qa | llm_alone               | 0.285 | 6.4/10  | 8737   | $0.0014 | 3595 ms     | 62%     | 27.6%   | 10.5%  |
| docs-qa | snipara_ctx_mem         | 0.533 | 5.3/10  | 3075   | $0.0005 | 3943 ms     | 43%     | 16.1%   | 35.2%  |
| docs-qa | snipara_ctx_mem_runtime | 0.484 | 6.0/10  | 3992   | $0.0007 | 7881 ms     | 52%     | 20.0%   | 35.2%  |
| memory  | snipara_ctx_mem         | 0.561 | 8.4/10  | 5322   | $0.0008 | 4191 ms     | 100%    | 25.0%   | 0.0%   |
| memory  | snipara_ctx_mem_runtime | 0.533 | 8.6/10  | 6804   | $0.0011 | 7605 ms     | 100%    | 13.9%   | 0.0%   |
| coding  | llm_alone               | 0.569 | 9.0/10  | 8961   | $0.0015 | 7260 ms     | 100%    | 0.0%    | 0.0%   |
| coding  | snipara_ctx_mem         | 0.867 | 9.0/10  | 3328   | $0.0006 | 5937 ms     | 100%    | 0.0%    | 20.0%  |
| coding  | snipara_ctx_mem_runtime | 0.728 | 8.4/10  | 4289   | $0.0008 | 10350 ms    | 100%    | 0.0%    | 20.0%  |

## Suite: docs-qa

### Mode Comparison

| Metric           | llm_alone | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------- | --------------- | ----------------------- |
| Quality (0-10)   | 6.39      | 5.28            | 5.98                    |
| Avg Tokens       | 8737      | 3075            | 3992                    |
| Avg Cost ($)     | 0.00140   | 0.00053         | 0.00073                 |
| Latency p50 (ms) | 3595      | 3943            | 7881                    |
| Latency p95 (ms) | 8094      | 9397            | 11439                   |
| Success Rate     | 62%       | 43%             | 52%                     |
| Hallucination    | 27.6%     | 16.1%           | 20.0%                   |
| Precision@5      | 10.5%     | 35.2%           | 35.2%                   |
| Recall           | 62.1%     | 40.5%           | 44.8%                   |
| CBS              | 0.285     | 0.533           | 0.484                   |

### Per-Task Breakdown

| Task                             | Diff.  | llm_alone (q) | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| -------------------------------- | ------ | ------------- | ------------------- | --------------------------- |
| tech_stack                       | easy   | +8.1          | +8.1                | +8.1                        |
| core_value_prop                  | easy   | +8.5          | +8.1                | +9.5                        |
| mcp_tools                        | easy   | +7.0          | -3.3                | -3.1                        |
| pricing                          | easy   | -6.8          | -3.5                | -3.4                        |
| architecture                     | easy   | -3.4          | -5.0                | -2.9                        |
| token_budgeting                  | easy   | +7.2          | -4.1                | -3.5                        |
| shared_context                   | easy   | +8.5          | +8.1                | +9.0                        |
| oauth_device_flow                | easy   | +8.0          | +8.0                | +8.5                        |
| database_models                  | easy   | -3.4          | -2.6                | -2.5                        |
| layered_architecture             | easy   | -4.0          | +8.0                | +8.0                        |
| cost_benefit_analysis            | hard   | +8.5          | +7.0                | +8.1                        |
| when_to_use_decompose            | medium | +8.1          | +7.2                | +8.5                        |
| search_mode_selection            | medium | +8.1          | -3.5                | -5.5                        |
| full_request_flow                | hard   | +8.0          | -6.0                | -5.6                        |
| security_authentication_chain    | hard   | +8.1          | +8.1                | +8.1                        |
| shared_context_budget_allocation | hard   | +9.5          | -3.4                | +9.5                        |
| nonexistent_feature              | medium | -1.9          | -0.0                | -0.0                        |
| ambiguous_acronym                | easy   | -3.5          | -3.5                | -3.5                        |
| version_specific                 | easy   | -3.4          | -0.0                | -2.9                        |
| error_handling                   | medium | +7.2          | +7.2                | +8.0                        |
| empty_context                    | medium | -2.9          | -6.1                | +7.3                        |

## Suite: memory

### Mode Comparison

| Metric           | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------------- | ----------------------- |
| Quality (0-10)   | 8.39            | 8.57                    |
| Avg Tokens       | 5322            | 6804                    |
| Avg Cost ($)     | 0.00085         | 0.00111                 |
| Latency p50 (ms) | 4191            | 7605                    |
| Latency p95 (ms) | 6391            | 8087                    |
| Success Rate     | 100%            | 100%                    |
| Hallucination    | 25.0%           | 13.9%                   |
| Precision@5      | 0.0%            | 0.0%                    |
| Recall           | 50.0%           | 50.0%                   |
| CBS              | 0.561           | 0.533                   |

### Per-Task Breakdown

| Task              | Diff.  | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| ----------------- | ------ | ------------------- | --------------------------- |
| mem_store_recall  | easy   | +9.8                | +9.5                        |
| mem_decision_log  | medium | +8.5                | +9.5                        |
| mem_shared_std    | medium | +8.0                | +8.0                        |
| multi_turn_refine | medium | +7.3                | +7.3                        |

## Suite: coding

### Mode Comparison

| Metric           | llm_alone | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------- | --------------- | ----------------------- |
| Quality (0-10)   | 9.00      | 9.03            | 8.42                    |
| Avg Tokens       | 8961      | 3328            | 4289                    |
| Avg Cost ($)     | 0.00152   | 0.00060         | 0.00082                 |
| Latency p50 (ms) | 7260      | 5937            | 10350                   |
| Latency p95 (ms) | 14836     | 6578            | 10721                   |
| Success Rate     | 100%      | 100%            | 100%                    |
| Hallucination    | 0.0%      | 0.0%            | 0.0%                    |
| Precision@5      | 0.0%      | 20.0%           | 20.0%                   |
| Recall           | 66.7%     | 50.0%           | 50.0%                   |
| CBS              | 0.569     | 0.867           | 0.728                   |

### Per-Task Breakdown

| Task             | Diff.  | llm_alone (q) | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| ---------------- | ------ | ------------- | ------------------- | --------------------------- |
| add_api_endpoint | medium | +9.7          | +9.8                | +9.8                        |
| fix_type_error   | easy   | +7.8          | +7.8                | +7.0                        |
| add_unit_test    | easy   | +9.5          | +9.5                | +8.5                        |

---

_Generated by `suite_benchmark.py` at 2026-01-31 13:46:28_
