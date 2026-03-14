# Snipara Benchmark Plan

## Three Modes Under Test

| Mode  | Label                     | Description                                                               |
| ----- | ------------------------- | ------------------------------------------------------------------------- |
| **A** | `llm_alone`               | LLM receives full docs (up to 50 K tokens), no Snipara                    |
| **B** | `snipara_ctx_mem`         | LLM receives Snipara-optimized context (4 K) + agent memory recall        |
| **C** | `snipara_ctx_mem_runtime` | Same as B, plus RLM-Runtime executes tests/lint/build before final output |

---

## Suite 1 — Documentation QA (21 existing tasks)

Measures context-optimization quality on factual, reasoning, multi-hop, and edge-case questions.

### Tasks (from `datasets/snipara_docs.py`)

| #   | ID                                 | Category  | Difficulty |
| --- | ---------------------------------- | --------- | ---------- |
| 1   | `tech_stack`                       | factual   | easy       |
| 2   | `core_value_prop`                  | factual   | easy       |
| 3   | `mcp_tools`                        | factual   | easy       |
| 4   | `pricing`                          | factual   | easy       |
| 5   | `architecture`                     | factual   | easy       |
| 6   | `token_budgeting`                  | factual   | easy       |
| 7   | `shared_context`                   | factual   | easy       |
| 8   | `oauth_device_flow`                | factual   | easy       |
| 9   | `database_models`                  | factual   | easy       |
| 10  | `layered_architecture`             | factual   | easy       |
| 11  | `cost_benefit_analysis`            | reasoning | hard       |
| 12  | `when_to_use_decompose`            | reasoning | medium     |
| 13  | `search_mode_selection`            | reasoning | medium     |
| 14  | `full_request_flow`                | multi_hop | hard       |
| 15  | `security_authentication_chain`    | multi_hop | hard       |
| 16  | `shared_context_budget_allocation` | multi_hop | hard       |
| 17  | `nonexistent_feature`              | edge_case | medium     |
| 18  | `ambiguous_acronym`                | edge_case | easy       |
| 19  | `version_specific`                 | edge_case | easy       |
| 20  | `error_handling`                   | edge_case | medium     |
| 21  | `empty_context`                    | edge_case | medium     |

### Metrics

| Metric                    | Formula / Method                                                                               | Unit   |
| ------------------------- | ---------------------------------------------------------------------------------------------- | ------ |
| **Token usage (input)**   | `tiktoken.encode(system + context + query)`                                                    | tokens |
| **Token usage (context)** | `tiktoken.encode(context)`                                                                     | tokens |
| **Token usage (output)**  | `response.usage.completion_tokens`                                                             | tokens |
| **Cost**                  | `(input * $/M_in + output * $/M_out)` per model                                                | USD    |
| **Latency p50**           | Median of 3 runs per task                                                                      | ms     |
| **Latency p95**           | 95th percentile across all tasks                                                               | ms     |
| **Context precision**     | `\|relevant ∩ top_K\| / K`                                                                     | 0–1    |
| **Context recall**        | `\|relevant_retrieved\| / \|relevant_expected\|`                                               | 0–1    |
| **NDCG**                  | Normalized Discounted Cumulative Gain                                                          | 0–1    |
| **MRR**                   | 1 / rank of first relevant result                                                              | 0–1    |
| **Citation accuracy**     | `cited ∩ ground_truth / cited` (LLM-judge)                                                     | 0–1    |
| **Hallucination rate**    | `incorrect_claims / total_claims` (two-stage)                                                  | 0–1    |
| **Factual accuracy**      | `correct_claims / verifiable_claims`                                                           | 0–1    |
| **Answer quality**        | Weighted: correctness 30 %, completeness 25 %, relevance 20 %, faithfulness 15 %, clarity 10 % | 0–10   |
| **Success rate**          | `tasks_scoring_≥7 / total`                                                                     | 0–1    |
| **Turns to success**      | Always 1 for single-turn QA                                                                    | count  |

### Pass/Fail Criteria

| Metric             | Mode A Baseline | Mode B Target    | Mode C Target  |
| ------------------ | --------------- | ---------------- | -------------- |
| Context tokens     | ~50 K           | < 5 K (90 % cut) | < 7 K          |
| Hallucination rate | < 10 %          | < 5 %            | < 5 %          |
| Answer quality     | ≥ 6.0           | ≥ 7.0            | ≥ 7.5          |
| Precision@5        | < 20 %          | ≥ 60 %           | ≥ 60 %         |
| Cost per query     | baseline        | ≥ 80 % savings   | ≥ 70 % savings |

---

## Suite 2 — Agent Memory & Multi-Turn (12 tasks)

Measures memory recall, session continuity, and context accumulation.

### Tasks

| #   | ID                      | Type       | Description                            |
| --- | ----------------------- | ---------- | -------------------------------------- |
| 1   | `mem_store_recall`      | memory     | Store a fact, recall it 3 turns later  |
| 2   | `mem_decision_log`      | memory     | Log decision, verify retrieval         |
| 3   | `mem_preference`        | memory     | Store preference, verify influence     |
| 4   | `mem_context_carry`     | session    | Inject context, verify persistence     |
| 5   | `mem_shared_std`        | shared     | Load team standards, verify compliance |
| 6   | `mem_multi_project`     | team       | Cross-project pattern search           |
| 7   | `multi_turn_refine`     | multi-turn | 3-turn answer refinement               |
| 8   | `multi_turn_contradict` | multi-turn | Correct earlier wrong answer           |
| 9   | `multi_turn_aggregate`  | multi-turn | Combine info from 3 queries            |
| 10  | `decompose_execute`     | planning   | Decompose + execute sub-queries        |
| 11  | `plan_generate`         | planning   | Generate feature execution plan        |
| 12  | `template_render`       | templates  | Load and render prompt template        |

### Metrics

| Metric                     | Formula / Method                            | Unit   |
| -------------------------- | ------------------------------------------- | ------ |
| **Token usage**            | Summed across turns                         | tokens |
| **Cost**                   | Cumulative across turns                     | USD    |
| **Latency p50 / p95**      | Per-turn and end-to-end                     | ms     |
| **Memory recall accuracy** | `recalled ∩ stored / stored`                | 0–1    |
| **Memory precision**       | `relevant_recalled / total_recalled`        | 0–1    |
| **Context carryover**      | `injected_terms_in_turn_N / injected_terms` | 0–1    |
| **Session coherence**      | LLM-judge: turn N builds on N−1 (0–10)      | 0–10   |
| **Hallucination rate**     | Two-stage                                   | 0–1    |
| **Answer quality**         | Weighted score                              | 0–10   |
| **Success rate**           | Tasks scoring ≥ 7                           | 0–1    |
| **Turns to success**       | Turns until score ≥ 8                       | count  |

### Pass/Fail Criteria

| Metric                 | Mode A (N/A) | Mode B Target | Mode C Target |
| ---------------------- | ------------ | ------------- | ------------- |
| Memory recall accuracy | —            | ≥ 85 %        | ≥ 85 %        |
| Context carryover      | —            | ≥ 90 %        | ≥ 90 %        |
| Session coherence      | —            | ≥ 7.0         | ≥ 7.5         |
| Turns to success       | —            | ≤ 2           | ≤ 2           |

> Mode A has no memory/session capability and is excluded from this suite.

---

## Suite 3 — Coding Tasks (10 tasks)

Measures code generation with and without runtime validation.

### Tasks

| #   | ID                    | Language   | Difficulty | Description                       |
| --- | --------------------- | ---------- | ---------- | --------------------------------- |
| 1   | `add_api_endpoint`    | TypeScript | medium     | REST endpoint with Zod validation |
| 2   | `fix_type_error`      | TypeScript | easy       | Fix type error in function        |
| 3   | `add_prisma_query`    | TypeScript | medium     | Prisma query with proper types    |
| 4   | `refactor_component`  | React/TSX  | medium     | Refactor per team standards       |
| 5   | `add_unit_test`       | TypeScript | easy       | Write unit test for function      |
| 6   | `fix_sql_injection`   | TypeScript | hard       | Fix SQL injection vuln            |
| 7   | `add_auth_middleware` | TypeScript | hard       | Add auth middleware               |
| 8   | `python_mcp_tool`     | Python     | medium     | New MCP tool in FastAPI           |
| 9   | `fix_race_condition`  | Python     | hard       | Fix async race condition          |
| 10  | `add_migration`       | SQL/Prisma | medium     | DB migration for new table        |

### Metrics

| Metric                         | Formula / Method                                      | Unit   |
| ------------------------------ | ----------------------------------------------------- | ------ |
| **Token usage**                | input + context + output                              | tokens |
| **Cost**                       | Per model pricing                                     | USD    |
| **Latency p50 / p95**          | Includes runtime exec for Mode C                      | ms     |
| **Context precision / recall** | IR metrics                                            | 0–1    |
| **Hallucination rate**         | Claims vs docs                                        | 0–1    |
| **Answer quality**             | LLM-judge (0–10)                                      | 0–10   |
| **Test pass rate**             | `passing / total` after diff                          | 0–1    |
| **Regression rate**            | `new_failures / prev_passing`                         | 0–1    |
| **Diff size**                  | Lines added + removed                                 | lines  |
| **Lint clean**                 | 0 ESLint/mypy warnings                                | bool   |
| **Type-check pass**            | `tsc --noEmit` exits 0                                | bool   |
| **Build pass**                 | `pnpm build` exits 0                                  | bool   |
| **Code quality**               | LLM-judge: correctness, readability, standards (0–10) | 0–10   |
| **Success rate**               | Tests pass AND quality ≥ 7                            | 0–1    |
| **Turns to success**           | Iterations until tests pass (Mode C self-corrects)    | count  |

### Pass/Fail Criteria

| Metric           | Mode A       | Mode B | Mode C |
| ---------------- | ------------ | ------ | ------ |
| Test pass rate   | ≥ 40 %       | ≥ 60 % | ≥ 85 % |
| Regression rate  | < 20 %       | < 10 % | < 5 %  |
| Lint clean       | ≥ 50 %       | ≥ 70 % | ≥ 90 % |
| Build pass       | ≥ 50 %       | ≥ 70 % | ≥ 90 % |
| Code quality     | ≥ 5.0        | ≥ 6.5  | ≥ 7.5  |
| Turns to success | 1 (no retry) | 1      | ≤ 3    |

---

## Scoring Rubric

### Quality Score (0–10) — LLM-as-Judge

| Score | Label      | Criteria                                         |
| ----- | ---------- | ------------------------------------------------ |
| 9–10  | Excellent  | Correct, complete, well-cited, no hallucinations |
| 7–8   | Good       | Mostly correct, minor omissions, good citations  |
| 5–6   | Acceptable | Partially correct, noticeable gaps               |
| 3–4   | Poor       | Significant errors or missing info               |
| 0–2   | Fail       | Wrong, hallucinated, or irrelevant               |

### Composite Benchmark Score (CBS)

```
CBS = 0.25 × norm_quality
    + 0.20 × norm_token_savings
    + 0.15 × norm_precision
    + 0.15 × (1 − norm_hallucination)
    + 0.10 × norm_success_rate
    + 0.10 × norm_latency_score
    + 0.05 × norm_citation_accuracy
```

### CBS-C (Coding Suite Bonus for Mode C)

```
CBS_C = CBS
      + 0.10 × test_pass_rate
      + 0.05 × (1 − regression_rate)
      + 0.05 × lint_build_pass_rate
```

---

## Dataset Composition

| Category         | Count  | %         | Rationale                 |
| ---------------- | ------ | --------- | ------------------------- |
| Factual (easy)   | 10     | 23 %      | Baseline capability       |
| Factual (medium) | 5      | 12 %      | Moderate retrieval        |
| Reasoning        | 7      | 16 %      | Multi-concept synthesis   |
| Multi-hop        | 3      | 7 %       | Cross-section composition |
| Edge cases       | 5      | 12 %      | Robustness                |
| Memory/session   | 7      | 16 %      | Agent continuity          |
| Coding           | 6      | 14 %      | Code generation           |
| **Total**        | **43** | **100 %** |                           |

### Per-Task Ground Truth

Each task includes:

- `query` — natural language question or instruction
- `expected_answer` — reference answer or reference implementation
- `relevant_sections` — doc section titles that should be retrieved
- `ground_truth_claims` — atomic verifiable facts
- `difficulty` — easy / medium / hard
- `category` — factual / reasoning / multi_hop / edge_case / memory / coding
- `success_criteria` — task-specific pass condition
- Coding tasks additionally: `test_file`, `target_files`, `setup_commands`

---

## Experiment Protocol

### Fixed Parameters

| Parameter              | Value               | Rationale                           |
| ---------------------- | ------------------- | ----------------------------------- |
| Temperature            | 0.0                 | Deterministic for reproducibility   |
| Runs per task          | 3                   | Statistical stability (median used) |
| Max output tokens      | 2048                | Standardized output                 |
| Context budget B       | 4000 tokens         | Snipara default                     |
| Context budget C       | 6000 tokens         | Includes memory                     |
| Full docs budget A     | 50000 tokens        | "No optimization"                   |
| Evaluation model       | Same as generation  | No cross-model bias                 |
| RLM-Runtime iterations | 3 max               | Mode C self-correction cap          |
| RLM-Runtime timeout    | 120 s per iteration | Prevent runaway                     |

### Cost Caps

| Model           | Max Cost / Full Run | Estimated Calls             |
| --------------- | ------------------- | --------------------------- |
| gpt-4o-mini     | $2.00               | 43 × 3 modes × 3 runs = 387 |
| claude-sonnet-4 | $15.00              | 387                         |
| claude-opus-4.5 | $50.00              | 387                         |

### Execution Steps

```
1. SETUP
   ├─ Verify OAuth token   → ~/.snipara/tokens.json
   ├─ Verify LLM API key   → provider env var
   ├─ Verify Snipara API   → GET /health
   ├─ Load dataset (43 tasks)
   └─ Create reports/<timestamp>/

2. EXECUTE  (per task × mode × 3 runs)
   ├─ Record start_ts
   ├─ Prepare context
   │   ├─ A: load_full_docs() → truncate 50 K
   │   ├─ B: context_query() + rlm_recall()
   │   └─ C: same as B + RLM-Runtime env
   ├─ Generate response (temp=0.0)
   ├─ Record: tokens, latency, raw response
   ├─ Mode C only: run tests/lint/build → record pass/fail
   └─ Record end_ts

3. EVALUATE  (per task result)
   ├─ Extract claims → two-stage hallucination check
   ├─ LLM-as-judge quality (5 dims)
   ├─ Citation accuracy check
   ├─ IR metrics (precision, recall, NDCG, MRR)
   └─ Token efficiency (compression, cost)

4. AGGREGATE
   ├─ Medians across 3 runs
   ├─ p50 / p95 latencies
   ├─ Success rates
   ├─ CBS and CBS-C scores
   └─ Comparison tables

5. REPORT
   ├─ JSON results
   ├─ Markdown report
   ├─ HTML dashboard
   └─ Terminal summary
```

### Statistical Notes

- **3 runs minimum** per (task, mode) — median eliminates outliers
- **Temperature 0.0** — eliminates stochastic variance; 3 runs captures API jitter
- **Wilcoxon signed-rank test** for A-vs-B and B-vs-C paired comparisons
- **Cohen's d** effect size reported alongside p-values

---

## CLI Reference

```bash
# Full suite, all modes
python -m benchmarks.suite_benchmark --all

# Single suite
python -m benchmarks.suite_benchmark --suite docs-qa
python -m benchmarks.suite_benchmark --suite memory
python -m benchmarks.suite_benchmark --suite coding

# Single mode
python -m benchmarks.suite_benchmark --mode llm_alone
python -m benchmarks.suite_benchmark --mode snipara_ctx_mem
python -m benchmarks.suite_benchmark --mode snipara_ctx_mem_runtime

# Provider / model
python -m benchmarks.suite_benchmark --all --provider anthropic --model claude-sonnet-4-20250514

# Difficulty filter
python -m benchmarks.suite_benchmark --all --difficulty hard

# Cost cap
python -m benchmarks.suite_benchmark --all --cost-cap 5.00

# Dashboard from existing results
python -m benchmarks.suite_benchmark --dashboard reports/latest.json
```
