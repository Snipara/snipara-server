# Snipara Benchmark Results

**Date:** 2026-01-31 17:50:03
**Provider:** openai
**Model:** gpt-4o-mini
**Runs per task:** 3
**Temperature:** 0.0

---

## Executive Summary

| Suite   | Mode                    | CBS   | Quality | Tokens | Cost    | Latency p50 | Success | Halluc. | Prec@5 |
| ------- | ----------------------- | ----- | ------- | ------ | ------- | ----------- | ------- | ------- | ------ |
| docs-qa | snipara_ctx_mem         | 0.547 | 6.1/10  | 2616   | $0.0005 | 3864 ms     | 48%     | 13.1%   | 27.1%  |
| docs-qa | snipara_ctx_mem_runtime | 0.514 | 6.3/10  | 2933   | $0.0006 | 5435 ms     | 52%     | 15.2%   | 27.1%  |
| memory  | snipara_ctx_mem         | 0.448 | 8.2/10  | 4040   | $0.0007 | 4602 ms     | 75%     | 25.0%   | 0.0%   |
| memory  | snipara_ctx_mem_runtime | 0.607 | 8.5/10  | 4529   | $0.0008 | 6298 ms     | 100%    | 0.0%    | 0.0%   |
| coding  | snipara_ctx_mem         | 0.694 | 9.0/10  | 5026   | $0.0009 | 7711 ms     | 100%    | 2.0%    | 20.0%  |
| coding  | snipara_ctx_mem_runtime | 0.586 | 8.4/10  | 5553   | $0.0010 | 9795 ms     | 100%    | 0.0%    | 20.0%  |

## Suite: docs-qa

### Mode Comparison

| Metric           | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------------- | ----------------------- |
| Quality (0-10)   | 6.06            | 6.28                    |
| Avg Tokens       | 2616            | 2933                    |
| Avg Cost ($)     | 0.00047         | 0.00057                 |
| Latency p50 (ms) | 3864            | 5435                    |
| Latency p95 (ms) | 8386            | 11296                   |
| Success Rate     | 48%             | 52%                     |
| Hallucination    | 13.1%           | 15.2%                   |
| Precision@5      | 27.1%           | 27.1%                   |
| Recall           | 30.1%           | 30.1%                   |
| CBS              | 0.547           | 0.514                   |

### Per-Task Breakdown

| Task                             | Diff.  | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| -------------------------------- | ------ | ------------------- | --------------------------- |
| tech_stack                       | easy   | +7.5                | +7.5                        |
| core_value_prop                  | easy   | +9.5                | +9.5                        |
| mcp_tools                        | easy   | +7.8                | -6.0                        |
| pricing                          | easy   | -6.1                | -6.1                        |
| architecture                     | easy   | -6.8                | -4.0                        |
| token_budgeting                  | easy   | -4.1                | -5.5                        |
| shared_context                   | easy   | +8.5                | +9.0                        |
| oauth_device_flow                | easy   | -5.5                | +7.0                        |
| database_models                  | easy   | -2.9                | -2.5                        |
| layered_architecture             | easy   | +8.1                | +8.0                        |
| cost_benefit_analysis            | hard   | +7.0                | +8.0                        |
| when_to_use_decompose            | medium | +8.1                | +8.5                        |
| search_mode_selection            | medium | -5.6                | +8.1                        |
| full_request_flow                | hard   | -4.1                | -6.0                        |
| security_authentication_chain    | hard   | +8.1                | +8.1                        |
| shared_context_budget_allocation | hard   | +9.5                | +9.5                        |
| nonexistent_feature              | medium | -1.5                | -0.0                        |
| ambiguous_acronym                | easy   | -2.9                | -4.0                        |
| version_specific                 | easy   | -1.5                | -1.5                        |
| error_handling                   | medium | +8.0                | +7.2                        |
| empty_context                    | medium | -4.1                | -5.8                        |

## Suite: memory

### Mode Comparison

| Metric           | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------------- | ----------------------- |
| Quality (0-10)   | 8.19            | 8.46                    |
| Avg Tokens       | 4040            | 4529                    |
| Avg Cost ($)     | 0.00067         | 0.00078                 |
| Latency p50 (ms) | 4602            | 6298                    |
| Latency p95 (ms) | 5087            | 7538                    |
| Success Rate     | 75%             | 100%                    |
| Hallucination    | 25.0%           | 0.0%                    |
| Precision@5      | 0.0%            | 0.0%                    |
| Recall           | 25.0%           | 25.0%                   |
| CBS              | 0.448           | 0.607                   |

### Per-Task Breakdown

| Task              | Diff.  | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| ----------------- | ------ | ------------------- | --------------------------- |
| mem_store_recall  | easy   | +9.7                | +9.5                        |
| mem_decision_log  | medium | +8.5                | +8.5                        |
| mem_shared_std    | medium | +8.0                | +8.6                        |
| multi_turn_refine | medium | -6.5                | +7.3                        |

## Suite: coding

### Mode Comparison

| Metric           | snipara_ctx_mem | snipara_ctx_mem_runtime |
| ---------------- | --------------- | ----------------------- |
| Quality (0-10)   | 9.02            | 8.43                    |
| Avg Tokens       | 5026            | 5553                    |
| Avg Cost ($)     | 0.00088         | 0.00101                 |
| Latency p50 (ms) | 7711            | 9795                    |
| Latency p95 (ms) | 10575           | 12158                   |
| Success Rate     | 100%            | 100%                    |
| Hallucination    | 2.0%            | 0.0%                    |
| Precision@5      | 20.0%           | 20.0%                   |
| Recall           | 50.0%           | 50.0%                   |
| CBS              | 0.694           | 0.586                   |

### Per-Task Breakdown

| Task             | Diff.  | snipara_ctx_mem (q) | snipara_ctx_mem_runtime (q) |
| ---------------- | ------ | ------------------- | --------------------------- |
| add_api_endpoint | medium | +9.7                | +10.0                       |
| fix_type_error   | easy   | +7.8                | +7.5                        |
| add_unit_test    | easy   | +9.5                | +7.8                        |

---

_Generated by `suite_benchmark.py` at 2026-01-31 17:50:03_
