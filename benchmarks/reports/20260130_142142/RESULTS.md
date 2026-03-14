# Snipara Benchmark Results

**Date:** 2026-01-30 14:21:42
**Provider:** anthropic
**Model:** claude-sonnet-4-20250514
**Runs per task:** 3
**Temperature:** 0.0

---

## Executive Summary

| Suite   | Mode                    | CBS   | Quality | Tokens | Cost    | Latency p50 | Success | Halluc. | Prec@5 |
| ------- | ----------------------- | ----- | ------- | ------ | ------- | ----------- | ------- | ------- | ------ |
| docs-qa | llm_alone               | 0.925 | 0.0/10  | 0      | $0.0000 | 0 ms        | 0%      | 0.0%    | 0.0%   |
| docs-qa | snipara_ctx_mem         | 0.925 | 0.0/10  | 0      | $0.0000 | 0 ms        | 0%      | 0.0%    | 0.0%   |
| docs-qa | snipara_ctx_mem_runtime | 0.925 | 0.0/10  | 0      | $0.0000 | 0 ms        | 0%      | 0.0%    | 0.0%   |
| memory  | snipara_ctx_mem         | 0.925 | 0.0/10  | 0      | $0.0000 | 0 ms        | 0%      | 0.0%    | 0.0%   |
| memory  | snipara_ctx_mem_runtime | 0.925 | 0.0/10  | 0      | $0.0000 | 0 ms        | 0%      | 0.0%    | 0.0%   |
| coding  | llm_alone               | 0.925 | 0.0/10  | 0      | $0.0000 | 0 ms        | 0%      | 0.0%    | 0.0%   |
| coding  | snipara_ctx_mem         | 0.925 | 0.0/10  | 0      | $0.0000 | 0 ms        | 0%      | 0.0%    | 0.0%   |
| coding  | snipara_ctx_mem_runtime | 0.925 | 0.0/10  | 0      | $0.0000 | 0 ms        | 0%      | 0.0%    | 0.0%   |

## Suite: docs-qa

### Mode Comparison

| Metric           | llm_alone | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------- | --------------- | ----------------------- |
| Quality (0-10)   | 0.00      | 0.00            | 0.00                    |
| Avg Tokens       | 0         | 0               | 0                       |
| Avg Cost ($)     | 0.00000   | 0.00000         | 0.00000                 |
| Latency p50 (ms) | 0         | 0               | 0                       |
| Latency p95 (ms) | 0         | 0               | 0                       |
| Success Rate     | 0%        | 0%              | 0%                      |
| Hallucination    | 0.0%      | 0.0%            | 0.0%                    |
| Precision@5      | 0.0%      | 0.0%            | 0.0%                    |
| Recall           | 0.0%      | 0.0%            | 0.0%                    |
| CBS              | 0.925     | 0.925           | 0.925                   |

### Per-Task Breakdown

| Task                             | Diff.  | llm_alone (q) | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| -------------------------------- | ------ | ------------- | ------------------- | --------------------------- |
| tech_stack                       | easy   | -0.0          | -0.0                | -0.0                        |
| core_value_prop                  | easy   | -0.0          | -0.0                | -0.0                        |
| mcp_tools                        | easy   | -0.0          | -0.0                | -0.0                        |
| pricing                          | easy   | -0.0          | -0.0                | -0.0                        |
| architecture                     | easy   | -0.0          | -0.0                | -0.0                        |
| token_budgeting                  | easy   | -0.0          | -0.0                | -0.0                        |
| shared_context                   | easy   | -0.0          | -0.0                | -0.0                        |
| oauth_device_flow                | easy   | -0.0          | -0.0                | -0.0                        |
| database_models                  | easy   | -0.0          | -0.0                | -0.0                        |
| layered_architecture             | easy   | -0.0          | -0.0                | -0.0                        |
| cost_benefit_analysis            | hard   | -0.0          | -0.0                | -0.0                        |
| when_to_use_decompose            | medium | -0.0          | -0.0                | -0.0                        |
| search_mode_selection            | medium | -0.0          | -0.0                | -0.0                        |
| full_request_flow                | hard   | -0.0          | -0.0                | -0.0                        |
| security_authentication_chain    | hard   | -0.0          | -0.0                | -0.0                        |
| shared_context_budget_allocation | hard   | -0.0          | -0.0                | -0.0                        |
| nonexistent_feature              | medium | -0.0          | -0.0                | -0.0                        |
| ambiguous_acronym                | easy   | -0.0          | -0.0                | -0.0                        |
| version_specific                 | easy   | -0.0          | -0.0                | -0.0                        |
| error_handling                   | medium | -0.0          | -0.0                | -0.0                        |
| empty_context                    | medium | -0.0          | -0.0                | -0.0                        |

## Suite: memory

### Mode Comparison

| Metric           | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------------- | ----------------------- |
| Quality (0-10)   | 0.00            | 0.00                    |
| Avg Tokens       | 0               | 0                       |
| Avg Cost ($)     | 0.00000         | 0.00000                 |
| Latency p50 (ms) | 0               | 0                       |
| Latency p95 (ms) | 0               | 0                       |
| Success Rate     | 0%              | 0%                      |
| Hallucination    | 0.0%            | 0.0%                    |
| Precision@5      | 0.0%            | 0.0%                    |
| Recall           | 0.0%            | 0.0%                    |
| CBS              | 0.925           | 0.925                   |

### Per-Task Breakdown

| Task              | Diff.  | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| ----------------- | ------ | ------------------- | --------------------------- |
| mem_store_recall  | easy   | -0.0                | -0.0                        |
| mem_decision_log  | medium | -0.0                | -0.0                        |
| mem_shared_std    | medium | -0.0                | -0.0                        |
| multi_turn_refine | medium | -0.0                | -0.0                        |

## Suite: coding

### Mode Comparison

| Metric           | llm_alone | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------- | --------------- | ----------------------- |
| Quality (0-10)   | 0.00      | 0.00            | 0.00                    |
| Avg Tokens       | 0         | 0               | 0                       |
| Avg Cost ($)     | 0.00000   | 0.00000         | 0.00000                 |
| Latency p50 (ms) | 0         | 0               | 0                       |
| Latency p95 (ms) | 0         | 0               | 0                       |
| Success Rate     | 0%        | 0%              | 0%                      |
| Hallucination    | 0.0%      | 0.0%            | 0.0%                    |
| Precision@5      | 0.0%      | 0.0%            | 0.0%                    |
| Recall           | 0.0%      | 0.0%            | 0.0%                    |
| CBS              | 0.925     | 0.925           | 0.925                   |

### Per-Task Breakdown

| Task             | Diff.  | llm_alone (q) | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| ---------------- | ------ | ------------- | ------------------- | --------------------------- |
| add_api_endpoint | medium | -0.0          | -0.0                | -0.0                        |
| fix_type_error   | easy   | -0.0          | -0.0                | -0.0                        |
| add_unit_test    | easy   | -0.0          | -0.0                | -0.0                        |

---

_Generated by `suite_benchmark.py` at 2026-01-30 14:21:42_
