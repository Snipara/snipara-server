# Snipara Benchmark Suite

Compares LLM performance **with** and **without** Snipara context optimization across multiple dimensions.

## Latest Results (February 2026)

| Benchmark          | Key Metric    | WITH Snipara | WITHOUT Snipara | Improvement     |
| ------------------ | ------------- | ------------ | --------------- | --------------- |
| Token Efficiency   | Compression   | **4.1x**     | 1x              | 75.6% reduction |
| Context Quality    | Precision@5   | **43.8%**    | 6.0%            | +37.8%          |
| Hallucination (v3) | Halluc. Rate  | **1.2%**     | ~3%             | 60% reduction   |
| Answer Quality     | Overall Score | **6.8/10**   | 6.0/10          | +0.8 points     |

**Key Findings:**

- **4x compression** reduces token costs by ~70%
- **1.2% hallucination rate** with graded scoring (only contradictions count)
- **76% success rate** on docs-qa benchmark suite

See [RESULTS.md](./RESULTS.md) for detailed analysis and historical data.

## Quick Start

```bash
cd apps/mcp-server

# Install dependencies
pip install anthropic tiktoken

# Run all benchmarks
python -m benchmarks.runner --all

# Run deterministic code graph benchmark
python -m benchmarks.code_graph_benchmark --project snipara --runs 3

# Run deterministic companion-vs-direct benchmark
python -m benchmarks.companion_benchmark --project snipara --runs 5

# Force API-key auth when local OAuth tokens are stale
python -m benchmarks.code_graph_benchmark --project snipara --prefer-api-key

# Run specific benchmark
python -m benchmarks.runner --token-efficiency
python -m benchmarks.runner --hallucination --verbose

# Use real Snipara API (requires SNIPARA_API_KEY)
python -m benchmarks.runner --all --use-api

# Filter by difficulty or category
python -m benchmarks.runner --all --difficulty hard
python -m benchmarks.runner --all --category multi_hop

# List all test cases
python -m benchmarks.runner --list-cases
```

## Benchmarks

### 1. Token Efficiency (`--token-efficiency`)

Measures token usage and cost savings when using Snipara context optimization.

| Metric                | Description                   |
| --------------------- | ----------------------------- |
| `compression_ratio`   | Full docs / optimized context |
| `token_reduction_pct` | Percentage of tokens saved    |
| `cost_savings_pct`    | Estimated cost reduction      |

**Does not call LLM** - purely measures token counts.

### 2. Context Quality (`--context-quality`)

Measures information retrieval quality using standard IR metrics.

| Metric           | Description                                   |
| ---------------- | --------------------------------------------- |
| `precision_at_k` | % of retrieved sections that are relevant     |
| `recall_at_k`    | % of relevant sections that were retrieved    |
| `mrr`            | Mean Reciprocal Rank of first relevant result |
| `ndcg`           | Normalized Discounted Cumulative Gain         |

**Does not call LLM** - compares retrieved sections against ground truth.

### 3. Hallucination Detection (`--hallucination`)

Measures TRUE hallucination rate using graded scoring against actual context.

**Improved Methodology (v3 - February 2026):**

The hallucination measurement uses graded scoring (0-100) instead of binary classification:

| Score Range | Meaning                                      |
| ----------- | -------------------------------------------- |
| 100         | Exact quote or verbatim from reference       |
| 90-99       | Very close paraphrase, identical meaning     |
| 70-89       | Reasonable inference, well supported         |
| 50-69       | Partially supported, interpretation required |
| 20-49       | Weakly related, stretching the reference     |
| 1-19        | Not supported (but not contradicting)        |
| 0           | **Directly CONTRADICTS** the reference       |

**Critical Fix (v3):** Claims are grounded against the **actual context provided to the LLM**, not against `full_docs`. This prevents false positives when Snipara returns context from docs not included in the reference set.

```python
# CORRECT: Ground against context (what LLM actually saw)
h = await _eval_hallucination(client, jm, text, context)

# WRONG: Ground against full_docs (may miss Snipara-indexed docs)
h = await _eval_hallucination(client, jm, text, full_docs)
```

| Metric                | Description                                    |
| --------------------- | ---------------------------------------------- |
| `hallucination_rate`  | % of claims with score 0 (contradictions only) |
| `avg_grounding_score` | Average grounding score (0-100)                |
| `claims_analyzed`     | Total claims extracted and scored              |

**Hallucination Rate Progression:**

| Version           | Rate     | Fix Applied                                  |
| ----------------- | -------- | -------------------------------------------- |
| v1 (bug)          | 98.1%    | Grounded against incomplete `full_docs`      |
| v2 (context fix)  | 31.0%    | Ground against actual context                |
| v2.1 (prompt fix) | 2.5%     | Distinguish paraphrases from contradictions  |
| v3 (graded)       | **1.2%** | 0-100 scoring, only score=0 is hallucination |

**Calls LLM** - generates responses, extracts claims, scores grounding.

### 4. Answer Quality (`--answer-quality`)

Evaluates overall response quality using LLM-as-judge.

| Metric         | Score Range | Description                  |
| -------------- | ----------- | ---------------------------- |
| `correctness`  | 0-10        | Factual accuracy             |
| `completeness` | 0-10        | Coverage of question aspects |
| `relevance`    | 0-10        | Direct relevance to query    |
| `faithfulness` | 0-10        | Consistency with source      |
| `clarity`      | 0-10        | Organization and readability |

**Calls LLM** - generates responses and evaluates quality.

### 5. Code Graph Benchmark (`code_graph_benchmark.py`)

Measures the hosted MCP surface for structural code lookups on a real project.

| Metric           | Description                                       |
| ---------------- | ------------------------------------------------- |
| `success_rate`   | Expected symbol fragments found in the payload    |
| `latency_ms.p50` | Median latency per structural case                |
| `latency_ms.p95` | Tail latency for repeated tool calls              |
| `response_bytes` | Payload size, useful for spotting oversized tools |

This benchmark is deterministic and does not require an evaluation LLM.
It can also optionally probe `rlm-runtime` when `OPENAI_API_KEY` is set:

```bash
python -m benchmarks.code_graph_benchmark --project snipara --probe-runtime
```

### 6. Companion Benchmark (`companion_benchmark.py`)

Measures the local `snipara-companion` CLI wrapper against direct hosted MCP calls.

| Metric           | Description                                                 |
| ---------------- | ----------------------------------------------------------- |
| `success_rate`   | Expected structural fragments found in the returned payload |
| `latency_ms.p50` | Median latency for direct-vs-companion cases                |
| `latency_ms.p95` | Tail latency, useful for workflow auto follow-ups           |
| `comparisons`    | Direct/CLI overhead deltas per structural case              |

This benchmark is deterministic and does not require an evaluation LLM.
It writes JSON and markdown reports to `benchmarks/reports/`.

```bash
python -m benchmarks.companion_benchmark --project snipara --runs 5
```

## Test Dataset

21 test cases derived from Snipara's own documentation (CLAUDE.md):

| Category    | Count | Description                                      |
| ----------- | ----- | ------------------------------------------------ |
| `factual`   | 10    | Basic fact retrieval (tech stack, pricing, etc.) |
| `reasoning` | 3     | Requires analysis (cost-benefit, tool selection) |
| `multi_hop` | 3     | Combines info from multiple sections             |
| `edge_case` | 5     | Edge cases (nonexistent features, errors)        |

| Difficulty | Count | Description                      |
| ---------- | ----- | -------------------------------- |
| `easy`     | 12    | Single-section answers           |
| `medium`   | 5     | Multi-section or nuanced answers |
| `hard`     | 4     | Complex reasoning required       |

## Configuration

### Environment Variables

```bash
export ANTHROPIC_API_KEY="sk-ant-..."   # Required for hallucination/answer quality
export SNIPARA_API_KEY="rlm_..."        # Required for --use-api mode
```

### Config Options

| Option         | Default                    | Description                                      |
| -------------- | -------------------------- | ------------------------------------------------ |
| `--model`      | `claude-sonnet-4-20250514` | LLM model for evaluation                         |
| `--verbose`    | `false`                    | Show individual test results                     |
| `--output`     | `benchmarks/reports/`      | Output directory                                 |
| `--use-api`    | `false`                    | Use real Snipara API                             |
| `--difficulty` | all                        | Filter: easy, medium, hard                       |
| `--category`   | all                        | Filter: factual, reasoning, multi_hop, edge_case |

## Output

Reports are saved to `benchmarks/reports/`:

- `token_efficiency_YYYYMMDD_HHMMSS.json` - Individual benchmark results
- `benchmark_report_YYYYMMDD_HHMMSS.md` - Combined markdown report

### Sample Output

```
============================================================
SNIPARA BENCHMARK SUITE
Model: claude-sonnet-4-20250514
Context source: Local extraction
Dataset: 21 test cases
============================================================

Token Efficiency: 3.9x compression (moderate)
  - Context reduced by 74.5%
  - Cost savings: 68.1%
  - With Snipara: ~3840 tokens/query
  - Without Snipara: ~15087 tokens/query
```

## Architecture

```
benchmarks/
├── __init__.py
├── config.py              # Configuration and constants
├── runner.py              # CLI runner and orchestration
├── suite_benchmark.py     # Suite benchmark with graded scoring (v3)
├── README.md              # This file
├── RESULTS.md             # Latest benchmark results and analysis
├── BENCHMARK_PLAN.md      # Benchmark planning and design
├── snipara_client.py      # Real Snipara API client
├── metrics/
│   ├── base.py            # Base classes
│   ├── token_efficiency.py
│   ├── context_quality.py
│   ├── hallucination.py
│   └── answer_quality.py
├── datasets/
│   └── snipara_docs.py    # Test cases, data loading, load_full_docs()
└── reports/               # Generated reports (timestamped dirs)
```

### Suite Benchmark (`suite_benchmark.py`)

The main benchmark runner with graded hallucination scoring:

```bash
# Run suite benchmark
python -m benchmarks.suite_benchmark \
  --suite docs-qa \
  --mode snipara_ctx_mem \
  --runs 1

# Available modes:
# - llm_alone: LLM with no context
# - snipara_ctx_mem: Snipara context + memory tools
# - snipara_ctx_mem_runtime: Full Snipara with runtime execution
```

**Key functions in `suite_benchmark.py`:**

| Function                 | Purpose                                |
| ------------------------ | -------------------------------------- |
| `_eval_hallucination()`  | Graded scoring (0-100) against context |
| `_eval_quality()`        | LLM-as-judge quality scoring           |
| `_eval_search_ranking()` | Precision@K and recall metrics         |
| `run_suite()`            | Main orchestrator                      |

## Reference Documentation Loading

The `load_full_docs()` function in `datasets/snipara_docs.py` loads the reference documentation for grounding checks.

**CRITICAL:** This must include ALL docs that Snipara indexes:

```python
def load_full_docs(self) -> str:
    # Root-level docs
    for name in ["CLAUDE.md", "specs.md", "ROADMAP.md"]:
        ...

    # ALL docs/*.md files (same as Snipara indexes)
    for md_file in sorted(docs_folder.glob("*.md")):
        ...
```

**Why this matters:**

- If `load_full_docs()` only includes 4 files but Snipara indexes 50+ docs
- Claims from the "missing" docs get marked as hallucinations (false positives)
- This caused the 98.1% hallucination bug before the v3 fix

**Current files loaded:**

- `CLAUDE.md`, `specs.md`, `ROADMAP.md` (project root)
- All `docs/*.md` files (~50 documentation files)

## Adding Test Cases

Edit `benchmarks/datasets/snipara_docs.py`:

```python
{
    "id": "my_test_case",
    "query": "What is the question?",
    "expected_answer": "The reference answer...",
    "relevant_sections": [
        "section title 1",
        "section title 2",
    ],
    "ground_truth_claims": [
        "Verifiable fact 1",
        "Verifiable fact 2",
    ],
    "difficulty": "easy",  # easy, medium, hard
    "category": "factual",  # factual, reasoning, multi_hop, edge_case
}
```

## Interpreting Results

### Token Efficiency

| Compression Ratio | Rating            |
| ----------------- | ----------------- |
| ≥10x              | Excellent         |
| ≥5x               | Good              |
| ≥2x               | Moderate          |
| <2x               | Needs improvement |

### Hallucination Rate (Graded v3)

Measures claims that **directly contradict** the provided context (score = 0).

| Hallucination Rate | Rating            |
| ------------------ | ----------------- |
| 0-1%               | Excellent         |
| 1-3%               | Good              |
| 3-5%               | Acceptable        |
| ≥5%                | Needs improvement |

| Avg Grounding Score | Rating                    |
| ------------------- | ------------------------- |
| ≥85                 | Excellent (well-grounded) |
| ≥70                 | Good                      |
| ≥50                 | Acceptable                |
| <50                 | Needs improvement         |

**Note:** Only score=0 counts as hallucination. Low scores (1-49) indicate weak support but not factual errors.

### Answer Quality

| Score | Rating            |
| ----- | ----------------- |
| ≥8    | Excellent         |
| ≥6    | Good              |
| ≥4    | Acceptable        |
| <4    | Needs improvement |

## Extending the Suite

### Adding a New Benchmark

1. Create `benchmarks/metrics/my_benchmark.py`:

```python
from .base import BenchmarkMetric, BenchmarkResult

class MyBenchmark(BenchmarkMetric):
    name = "my_benchmark"
    description = "Description of what this measures"

    async def run_single(
        self,
        test_case: dict,
        with_snipara_context: str,
        without_snipara_context: str,
    ) -> BenchmarkResult:
        # Implement benchmark logic
        return BenchmarkResult(
            benchmark_name=self.name,
            test_case=test_case["id"],
            with_snipara={...},
            without_snipara={...},
            improvement={...},
        )
```

2. Add to `benchmarks/metrics/__init__.py`
3. Add to `BenchmarkType` enum in `config.py`
4. Add CLI flag in `runner.py`

### Using Real Snipara API

The `--use-api` flag calls the actual Snipara MCP endpoint:

```python
from benchmarks.snipara_client import SniparaClient

client = SniparaClient(
    api_key="rlm_...",
    project_slug="snipara",
)

result = await client.context_query(
    query="What is the tech stack?",
    max_tokens=4000,
    search_mode="keyword",
)

print(result.to_context_string())
```

## License

MIT - Part of the RLM SaaS project.
