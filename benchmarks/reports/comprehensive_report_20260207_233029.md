# Comprehensive Snipara Benchmark Report

**Date:** 2026-02-07 23:30:29
**Provider:** openai
**Model:** gpt-4o
**Test Cases:** 21

## Executive Summary

This benchmark compares three scenarios:
1. **LLM Only** - Full documentation context (simulated, ~50k tokens)
2. **With Snipara** - Optimized context (~4k tokens)
3. **Snipara + RLM-Runtime** - Full RLM features (~6k tokens, memory, recursive context)

## Results Summary

| Metric | LLM Only | With Snipara | RLM-Runtime | Snipara Savings |
|--------|----------|--------------|-------------|-----------------|
| Avg Tokens | 7491 | 1459 | 1618 | 80.5% |
| Avg Latency (ms) | 5860 | 3976 | 5654 | - |
| Avg Quality Score | 5.00 | 5.00 | 5.00 | - |

## Detailed Analysis

### Token Efficiency

| Scenario | Tokens | vs LLM Only |
|----------|--------|-------------|
| LLM Only | 7491 | baseline |
| With Snipara | 1459 | +80.5% |
| RLM-Runtime | 1618 | +78.4% |

### Quality Comparison

| Scenario | Score | vs LLM Only |
|----------|-------|-------------|
| LLM Only | 5.00/10 | baseline |
| With Snipara | 5.00/10 | +0.00 |
| RLM-Runtime | 5.00/10 | +0.00 |

## Individual Test Results

| Test Case | LLM Score | Snipara Score | RLM Score | Best |
|-----------|-----------|---------------|-----------|------|
| tech_stack | 5.0 | 5.0 | 5.0 | LLM |
| core_value_prop | 5.0 | 5.0 | 5.0 | LLM |
| mcp_tools | 5.0 | 5.0 | 5.0 | LLM |
| pricing | 5.0 | 5.0 | 5.0 | LLM |
| architecture | 5.0 | 5.0 | 5.0 | LLM |
| token_budgeting | 5.0 | 5.0 | 5.0 | LLM |
| shared_context | 5.0 | 5.0 | 5.0 | LLM |
| oauth_device_flow | 5.0 | 5.0 | 5.0 | LLM |
| database_models | 5.0 | 5.0 | 5.0 | LLM |
| layered_architecture | 5.0 | 5.0 | 5.0 | LLM |
| cost_benefit_analysis | 5.0 | 5.0 | 5.0 | LLM |
| when_to_use_decompose | 5.0 | 5.0 | 5.0 | LLM |
| search_mode_selection | 5.0 | 5.0 | 5.0 | LLM |
| full_request_flow | 5.0 | 5.0 | 5.0 | LLM |
| security_authentication_chain | 5.0 | 5.0 | 5.0 | LLM |
| shared_context_budget_allocation | 5.0 | 5.0 | 5.0 | LLM |
| nonexistent_feature | 5.0 | 5.0 | 5.0 | LLM |
| ambiguous_acronym | 5.0 | 5.0 | 5.0 | LLM |
| version_specific | 5.0 | 5.0 | 5.0 | LLM |
| error_handling | 5.0 | 5.0 | 5.0 | LLM |
| empty_context | 5.0 | 5.0 | 5.0 | LLM |

## Conclusion

✅ **Excellent Results:** Snipara reduces token usage by 80.5% while maintaining or improving quality (+0.00 points).

**Cost Analysis** (estimated, per 1M tokens):
- Provider: openai
- LLM Only cost: $0.0037 per query (estimated)
- Snipara cost: $0.0007 per query (estimated)
