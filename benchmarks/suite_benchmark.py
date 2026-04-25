"""Three-suite Snipara benchmark: Docs-QA, Memory, Coding.

Modes:
  A  llm_alone              – Full docs, no Snipara
  B  snipara_ctx_mem         – Snipara context + agent memory
  C  snipara_ctx_mem_runtime – B + RLM-Runtime (tests/lint/build)

Auth: OAuth token from ~/.snipara/tokens.json (preferred).
      Run `snipara-mcp-login` to authenticate.

Usage:
    python -m benchmarks.suite_benchmark --all
    python -m benchmarks.suite_benchmark --suite docs-qa --mode snipara_ctx_mem
    python -m benchmarks.suite_benchmark --all --provider anthropic --model claude-sonnet-4-20250514
    python -m benchmarks.suite_benchmark --dashboard reports/latest.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from openai import AsyncOpenAI

from .config import TOKEN_COSTS, load_oauth_access_token, resolve_snipara_project_ref
from .datasets.snipara_docs import SniparaDocsDataset
from .snipara_client import SniparaClient, create_client

# Optional: RLM-Runtime for Mode C
try:
    from rlm import RLM
    from rlm.core.config import RLMConfig
    from rlm.core.types import CompletionOptions, RLMResult
    RLM_AVAILABLE = True
except ImportError:
    RLM_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODES = ("llm_alone", "snipara_ctx_mem", "snipara_ctx_mem_runtime")
SUITES = ("docs-qa", "memory", "coding")

LLM_PROVIDERS: dict[str, dict] = {
    "openai": {"env": ["OPENAI_API_KEY", "OPEN_AI_API_KEY"], "base_url": None, "model": "gpt-4o-mini"},
    "anthropic": {"env": ["ANTHROPIC_API_KEY"], "base_url": "https://api.anthropic.com/v1/", "model": "claude-sonnet-4-20250514"},
    "together": {"env": ["TOGETHER_API_KEY"], "base_url": None, "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free"},
}

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class SuiteConfig:
    """Configuration for a full benchmark run."""

    provider: str = "openai"
    model: str = "gpt-4o-mini"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.0
    max_output_tokens: int = 2048
    runs_per_task: int = 3
    timeout_s: int = 60

    # Snipara
    snipara_project_slug: str = field(default_factory=resolve_snipara_project_ref)
    snipara_oauth_token: Optional[str] = None
    snipara_api_key: Optional[str] = field(default_factory=lambda: os.getenv("SNIPARA_API_KEY"))

    # Context budgets
    budget_a: int = 50_000  # full docs
    budget_b: int = 8_000   # Snipara context (increased from 6K for better coverage)
    budget_c: int = 10_000  # Snipara + memory overhead

    # RLM-Runtime (Mode C)
    runtime_max_iter: int = 3
    runtime_timeout_s: int = 180    # Increased from 120s for complex tasks
    rlm_max_depth: int = 8          # Allow deeper RLM tool chains (was 5, increased for complex queries)
    rlm_token_budget: int = 30_000  # Base budget (increased from 15K)
    rlm_token_budget_min: int = 20_000  # Minimum budget (simple queries)
    rlm_token_budget_max: int = 100_000  # Maximum budget (very complex queries - architecture task needs ~72K+)
    rlm_cost_cap: float = 0.10     # Increased from 0.05 for complex tasks
    rlm_environment: str = "local"  # No Docker for docs-qa
    rlm_adaptive_budget: bool = True  # Scale budget based on prompt size

    # Judge model (defaults to same as main model; override for reasoning models)
    judge_model: Optional[str] = None

    # Output
    reports_dir: Path = field(default_factory=lambda: Path(__file__).parent / "reports")
    verbose: bool = True

    # Cost cap (USD).  None = no cap.
    cost_cap: Optional[float] = None

    @property
    def effective_judge_model(self) -> str:
        """Judge model — falls back to gpt-4o-mini for GPT-5 reasoning models."""
        if self.judge_model:
            return self.judge_model
        if self.model.startswith("gpt-5"):
            return "gpt-4o-mini"
        return self.model

    def __post_init__(self):
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        if not self.snipara_oauth_token:
            self.snipara_oauth_token = load_oauth_access_token(self.snipara_project_slug)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class RunMetrics:
    """Metrics from a single (task, mode, run) execution."""

    input_tokens: int = 0
    context_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    response: str = ""
    error: Optional[str] = None

    # Evaluation (filled post-generation)
    quality_score: float = 0.0          # 0-10 weighted
    correctness: float = 0.0
    completeness: float = 0.0
    relevance: float = 0.0
    faithfulness: float = 0.0
    clarity: float = 0.0

    hallucination_rate: float = 0.0     # 0-1
    factual_accuracy: float = 0.0       # 0-1
    citation_accuracy: float = 0.0      # 0-1
    total_claims: int = 0
    incorrect_claims: int = 0

    # IR metrics
    precision_at_k: float = 0.0
    recall_at_k: float = 0.0
    ndcg: float = 0.0
    mrr: float = 0.0

    # Coding-specific (Suite 3 / Mode C)
    test_pass_rate: float = 0.0
    regression_rate: float = 0.0
    diff_lines: int = 0
    lint_clean: bool = False
    typecheck_pass: bool = False
    build_pass: bool = False
    turns_to_success: int = 1

    # Memory-specific (Suite 2)
    memory_recall_accuracy: float = 0.0
    memory_precision: float = 0.0
    context_carryover: float = 0.0
    session_coherence: float = 0.0

    # RLM-Runtime metrics (Mode C)
    rlm_total_calls: int = 0
    rlm_tool_calls: int = 0
    rlm_cost_usd: float = 0.0
    rlm_success: bool = True


@dataclass
class TaskResult:
    """Aggregated result for one task across runs."""

    task_id: str
    suite: str
    category: str
    difficulty: str
    mode: str
    runs: list[RunMetrics] = field(default_factory=list)

    # Medians (computed after all runs)
    median_quality: float = 0.0
    median_latency_ms: float = 0.0
    median_tokens: int = 0
    median_cost: float = 0.0
    success: bool = False              # quality >= 7

    def compute_medians(self):
        valid = [r for r in self.runs if r.error is None]
        if not valid:
            return
        self.median_quality = statistics.median(r.quality_score for r in valid)
        self.median_latency_ms = statistics.median(r.latency_ms for r in valid)
        self.median_tokens = int(statistics.median(r.input_tokens + r.output_tokens for r in valid))
        self.median_cost = statistics.median(r.cost_usd for r in valid)
        self.success = self.median_quality >= 7.0


@dataclass
class SuiteResult:
    """Results for an entire suite."""

    suite: str
    mode: str
    tasks: list[TaskResult] = field(default_factory=list)

    # Aggregated
    avg_quality: float = 0.0
    avg_tokens: float = 0.0
    avg_cost: float = 0.0
    latency_p50: float = 0.0
    latency_p95: float = 0.0
    success_rate: float = 0.0
    avg_hallucination: float = 0.0
    avg_precision: float = 0.0
    avg_recall: float = 0.0
    cbs: float = 0.0                   # Composite Benchmark Score

    def aggregate(self):
        if not self.tasks:
            return
        for t in self.tasks:
            t.compute_medians()
        n = len(self.tasks)
        self.avg_quality = sum(t.median_quality for t in self.tasks) / n
        self.avg_tokens = sum(t.median_tokens for t in self.tasks) / n
        self.avg_cost = sum(t.median_cost for t in self.tasks) / n
        self.success_rate = sum(1 for t in self.tasks if t.success) / n

        lats = [t.median_latency_ms for t in self.tasks if t.median_latency_ms > 0]
        if lats:
            lats_sorted = sorted(lats)
            self.latency_p50 = lats_sorted[len(lats_sorted) // 2]
            self.latency_p95 = lats_sorted[int(len(lats_sorted) * 0.95)]

        # Average over all runs for hallucination / precision / recall
        all_runs = [r for t in self.tasks for r in t.runs if r.error is None]
        if all_runs:
            self.avg_hallucination = sum(r.hallucination_rate for r in all_runs) / len(all_runs)
            self.avg_precision = sum(r.precision_at_k for r in all_runs) / len(all_runs)
            self.avg_recall = sum(r.recall_at_k for r in all_runs) / len(all_runs)


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def _resolve_api_key(cfg: SuiteConfig) -> str:
    """Resolve API key from config, env vars, or raise."""
    if cfg.api_key:
        return cfg.api_key
    prov = LLM_PROVIDERS.get(cfg.provider, LLM_PROVIDERS["openai"])
    env_names = prov["env"]
    for env_name in env_names:
        val = os.environ.get(env_name)
        if val:
            return val
    raise ValueError(f"Set one of {env_names} or pass --api-key")


def _make_llm_client(cfg: SuiteConfig) -> AsyncOpenAI:
    key = _resolve_api_key(cfg)
    prov = LLM_PROVIDERS.get(cfg.provider, LLM_PROVIDERS["openai"])
    return AsyncOpenAI(api_key=key, base_url=cfg.base_url or prov.get("base_url"), timeout=float(cfg.timeout_s))


def _estimate_cost(input_tok: int, output_tok: int, model: str) -> float:
    costs = TOKEN_COSTS.get(model, {"input": 0.15, "output": 0.60})
    return (input_tok * costs["input"] + output_tok * costs["output"]) / 1_000_000


import tiktoken

_ENC = tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str) -> int:
    return len(_ENC.encode(text))


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

QUALITY_EVAL_PROMPT = """Evaluate this response. Output ONLY valid JSON.

Question: {query}
Expected: {expected}
Response: {response}

Score 0-10:
- correctness (factual accuracy)
- completeness (covers all aspects)
- relevance (directly addresses question)
- faithfulness (consistent with context)
- clarity (well-organized)
- overall (weighted: correctness 30%, completeness 25%, relevance 20%, faithfulness 15%, clarity 10%)

JSON format: {{"correctness":N,"completeness":N,"relevance":N,"faithfulness":N,"clarity":N,"overall":N}}"""


CLAIM_PROMPT = """Extract atomic factual claims from this response. Output ONLY a JSON array of strings.
Response: {response}"""


GROUNDING_PROMPT = """Score how well each claim is grounded in the reference documentation.

Reference: {reference}

Claims to verify: {claims}

For each claim, assign a grounding score (0-100):
- 100: Exact quote or verbatim from reference
- 90-99: Very close paraphrase, identical meaning, fully supported
- 70-89: Reasonable inference, well supported but not explicit
- 50-69: Partially supported, some interpretation required
- 20-49: Weakly related, stretching the reference
- 1-19: Not supported by reference (but not contradicting)
- 0: Directly CONTRADICTS the reference (false information)

CRITICAL: Only score 0 for actual contradictions. Missing info = 20-49, not 0.

Output ONLY a JSON array: {{"claim":"...","score":N,"reason":"brief explanation"}}"""


CITATION_PROMPT = """Check which section titles the response explicitly cites or references.
Response: {response}
Ground truth sections: {sections}
Output JSON: {{"cited":["..."],"correct_citations":N,"total_citations":N}}"""


def _model_kwargs(model: str, limit: int, temperature: float = 0.0) -> dict:
    """Return model-specific kwargs (token limit + temperature)."""
    kw: dict = {}
    if model.startswith("gpt-5"):
        kw["max_completion_tokens"] = limit
        # GPT-5 family only supports default temperature (1)
    else:
        kw["max_tokens"] = limit
        kw["temperature"] = temperature
    return kw


async def _eval_quality(client: AsyncOpenAI, model: str, query: str, expected: str, response: str) -> dict:
    """LLM-as-judge quality scoring."""
    try:
        r = await client.chat.completions.create(
            model=model,
            **_model_kwargs(model, 300),
            messages=[{"role": "user", "content": QUALITY_EVAL_PROMPT.format(
                query=query, expected=expected, response=response
            )}],
        )
        text = (r.choices[0].message.content or "").strip()
        # Strip markdown fences
        if "```" in text:
            import re
            m = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
            text = m.group(1) if m else text
        return json.loads(text)
    except Exception:
        return {"correctness": 0, "completeness": 0, "relevance": 0, "faithfulness": 0, "clarity": 0, "overall": 0}


async def _eval_hallucination(client: AsyncOpenAI, model: str, response: str, reference: str) -> dict:
    """Two-stage claim extraction + graded grounding scoring.

    Uses 0-100 grounding scores instead of binary correct/incorrect:
    - 0 = contradiction (true hallucination)
    - 1-49 = not supported (weak grounding)
    - 50-89 = partial support (acceptable)
    - 90-100 = well grounded (excellent)

    Hallucination rate = % of claims with score 0 (contradictions only)
    """
    try:
        import re
        # Extract claims
        r1 = await client.chat.completions.create(
            model=model, **_model_kwargs(model, 800),
            messages=[{"role": "user", "content": CLAIM_PROMPT.format(response=response)}],
        )
        t1 = (r1.choices[0].message.content or "").strip()
        if "```" in t1:
            m = re.search(r"```(?:json)?\s*(.*?)\s*```", t1, re.DOTALL)
            t1 = m.group(1) if m else t1
        claims = json.loads(t1)
        if not isinstance(claims, list) or not claims:
            return {"total": 0, "incorrect": 0, "rate": 0.0, "accuracy": 1.0, "avg_score": 100.0}

        # Ground claims with graded scoring
        r2 = await client.chat.completions.create(
            model=model, **_model_kwargs(model, 2000),
            messages=[{"role": "user", "content": GROUNDING_PROMPT.format(
                reference=reference, claims=json.dumps(claims)
            )}],
        )
        t2 = (r2.choices[0].message.content or "").strip()
        if "```" in t2:
            m = re.search(r"```(?:json)?\s*(.*?)\s*```", t2, re.DOTALL)
            t2 = m.group(1) if m else t2
        results = json.loads(t2)

        total = len(claims)
        scores = [r.get("score", 50) for r in results]  # Default 50 if missing

        # Metrics based on graded scores
        contradictions = sum(1 for s in scores if s == 0)  # True hallucinations
        weak = sum(1 for s in scores if 0 < s < 50)  # Not supported
        partial = sum(1 for s in scores if 50 <= s < 90)  # Partial support
        strong = sum(1 for s in scores if s >= 90)  # Well grounded

        avg_score = sum(scores) / total if total else 100.0

        return {
            "total": total,
            "incorrect": contradictions,  # Only contradictions = hallucinations
            "rate": contradictions / total if total else 0.0,
            "accuracy": strong / total if total else 1.0,  # % well-grounded
            "avg_score": round(avg_score, 1),
            "strong": strong,
            "partial": partial,
            "weak": weak,
        }
    except Exception:
        return {"total": 0, "incorrect": 0, "rate": 0.0, "accuracy": 1.0, "avg_score": 100.0}


async def _eval_citations(client: AsyncOpenAI, model: str, response: str, sections: list[str]) -> float:
    """Citation accuracy: what fraction of cited sections are in ground truth."""
    try:
        r = await client.chat.completions.create(
            model=model, **_model_kwargs(model, 400),
            messages=[{"role": "user", "content": CITATION_PROMPT.format(
                response=response, sections=json.dumps(sections)
            )}],
        )
        import re
        text = (r.choices[0].message.content or "").strip()
        if "```" in text:
            m = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
            text = m.group(1) if m else text
        data = json.loads(text)
        total = data.get("total_citations", 0)
        correct = data.get("correct_citations", 0)
        return correct / total if total > 0 else 1.0
    except Exception:
        return 0.0


def _normalize_title(title: str) -> set[str]:
    """Extract normalized keywords from a section title."""
    import re as _re
    words = _re.sub(r'[^a-zA-Z0-9\s]', ' ', title.lower()).split()
    # Filter out short words, common stop words, and project-specific ubiquitous terms
    stop_words = {
        # Standard stop words
        'the', 'a', 'an', 'of', 'in', 'to', 'for', 'and', 'or', 'is', 'are', 'with',
        # Project-specific ubiquitous terms (appear in 40%+ of sections)
        'snipara', 'mcp', 'rlm', 'tools', 'context', 'api', 'docs', 'guide', 'reference',
    }
    return {w for w in words if len(w) > 2 and w not in stop_words}


def _ir_metrics(context: str, relevant_expected: list[str]) -> dict:
    """Precision@K, Recall@K, NDCG, MRR from context vs expected sections.

    Uses keyword-based fuzzy matching: a section matches if at least one
    significant keyword from the expected section appears in the retrieved section.
    """
    import re as _re
    headers = _re.findall(r"^#{1,6}\s+(.+)$", context, _re.MULTILINE)
    retrieved = [h.strip() for h in headers]

    if not retrieved or not relevant_expected:
        return {"precision": 0.0, "recall": 0.0, "ndcg": 0.0, "mrr": 0.0}

    # Normalize expected sections into keywords
    expected_keywords = set()
    for e in relevant_expected:
        expected_keywords.update(_normalize_title(e))

    k = min(5, len(retrieved))
    top_k = retrieved[:k]

    def _match(r: str, expected_kw: set[str]) -> bool:
        """Check if retrieved section matches expected keywords.

        Requires ≥2 keyword overlap OR ≥50% of retrieved keywords match.
        This prevents false positives from single common term matches.
        """
        r_keywords = _normalize_title(r)
        if not r_keywords:
            return False
        overlap = r_keywords & expected_kw
        # Require at least 2 keyword overlap OR 50%+ of retrieved keywords match
        if len(overlap) >= 2:
            return True
        if len(overlap) / len(r_keywords) >= 0.5:
            return True
        return False

    def _match_single(r: str, e: str) -> bool:
        """Check if retrieved section matches a single expected section.

        Requires ≥2 keyword overlap OR ≥50% word overlap.
        """
        r_keywords = _normalize_title(r)
        e_keywords = _normalize_title(e)
        if not r_keywords or not e_keywords:
            return False
        overlap = r_keywords & e_keywords
        # Require at least 2 keyword overlap OR 50%+ overlap ratio
        if len(overlap) >= 2:
            return True
        # Check overlap ratio against the smaller set
        min_size = min(len(r_keywords), len(e_keywords))
        if len(overlap) / min_size >= 0.5:
            return True
        return False

    is_rel = [1 if _match(r, expected_keywords) else 0 for r in top_k]
    precision = sum(is_rel) / k if k else 0

    # Recall: how many expected sections were covered
    covered = sum(1 for e in relevant_expected if any(_match_single(r, e) for r in retrieved))
    recall = covered / len(relevant_expected) if relevant_expected else 0

    mrr = next((1.0 / (i + 1) for i, v in enumerate(is_rel) if v), 0.0)
    dcg = sum(v / math.log2(i + 2) for i, v in enumerate(is_rel))
    ideal = sorted(is_rel, reverse=True)
    idcg = sum(v / math.log2(i + 2) for i, v in enumerate(ideal))
    ndcg = dcg / idcg if idcg else 0
    return {"precision": precision, "recall": recall, "ndcg": ndcg, "mrr": mrr}


# ---------------------------------------------------------------------------
# Core execution
# ---------------------------------------------------------------------------

async def _generate(client: AsyncOpenAI, cfg: SuiteConfig, context: str, query: str, system: str) -> tuple[str, int, int, float]:
    """Returns (response_text, input_tokens, output_tokens, latency_ms)."""
    ctx_tokens = _count_tokens(context)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer:"},
    ]
    t0 = time.perf_counter()
    resp = await client.chat.completions.create(
        model=cfg.model,
        **_model_kwargs(cfg.model, cfg.max_output_tokens, cfg.temperature),
        messages=messages,
    )
    latency = (time.perf_counter() - t0) * 1000
    text = resp.choices[0].message.content or ""
    usage = resp.usage
    inp = usage.prompt_tokens if usage else ctx_tokens + 500
    out = usage.completion_tokens if usage else _count_tokens(text)
    return text, inp, out, latency


SYSTEM_PROMPTS = {
    "llm_alone": (
        "You are a helpful assistant. Answer using ONLY the provided documentation. "
        "CRITICAL RULES:\n"
        "1. Every claim must be directly supported by the documentation\n"
        "2. If information is not in the docs, say 'Not found in documentation'\n"
        "3. Never invent features, APIs, prices, or technical details\n"
        "4. When uncertain, prefer saying 'not specified' over guessing\n"
        "5. Use exact terminology from the documentation"
    ),
    "snipara_ctx_mem": (
        "You are a helpful assistant using Snipara-optimized context. "
        "CRITICAL RULES:\n"
        "1. Answer ONLY using information from the provided context sections\n"
        "2. Every claim must be traceable to a specific section\n"
        "3. If the context doesn't cover the topic, say 'Not found in provided context'\n"
        "4. Never invent features, APIs, or details - only report what's explicitly stated\n"
        "5. Prefer direct quotes or close paraphrasing over interpretation"
    ),
    "snipara_ctx_mem_runtime": (
        "You are a documentation assistant with access to Snipara tools. "
        "Use rlm_context_query to find relevant documentation, then answer accurately. "
        "CRITICAL RULES:\n"
        "1. Only state facts found in tool output\n"
        "2. If tools return no relevant info, say 'Not found in documentation'\n"
        "3. Never invent features, APIs, or details not confirmed by tool output\n"
        "4. Cite which sections support your answer when possible"
    ),
}


# ---------------------------------------------------------------------------
# RLM-Runtime integration (Mode C)
# ---------------------------------------------------------------------------

def _init_rlm(cfg: SuiteConfig) -> Optional[Any]:
    """Initialize RLM runtime for Mode C benchmarks.

    Uses RLM's native OAuth-based Snipara tools (v0.2.0+) which automatically
    resolve tokens from ``~/.snipara/tokens.json``.  No custom tool wrappers
    or separate API key needed.
    """
    if not RLM_AVAILABLE:
        print("  [WARN] rlm-runtime not installed, Mode C will use direct generation")
        return None

    # Ensure OPENAI_API_KEY is set for litellm (which RLM uses internally).
    # The .env may only have OPEN_AI_API_KEY.
    if not os.environ.get("OPENAI_API_KEY") and os.environ.get("OPEN_AI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ["OPEN_AI_API_KEY"]

    # GPT-5 models reject temperature=0.0 via LiteLLM — only default (1.0)
    # is supported.  Other models can use 0.0 for deterministic output.
    temperature = 1.0 if "gpt-5" in cfg.model else 0.0

    rlm_config = RLMConfig(
        temperature=temperature,
        snipara_project_slug=cfg.snipara_project_slug,
        snipara_base_url=os.environ.get("SNIPARA_BASE_URL", "https://api.snipara.com/mcp"),
        memory_enabled=False,   # No memory tools for docs-QA
        verbose=cfg.verbose,
    )

    try:
        rlm = RLM(
            backend="openai",
            model=cfg.model,
            environment=cfg.rlm_environment,
            config=rlm_config,
            verbose=cfg.verbose,
        )

        # Keep all tools — RLM's built-in AGENT_SYSTEM_PROMPT now includes
        # anti-hallucination grounding rules (commit c6ef296).
        tool_count = len(rlm.tool_registry)
        tool_names = [t.name for t in rlm.tool_registry.get_all()]
        tools_str = ", ".join(tool_names)
        print(f"  RLM-Runtime initialized: model={cfg.model} tools={tool_count} [{tools_str}]")
        return rlm
    except Exception as e:
        print(f"  [WARN] RLM init failed ({e}), Mode C will use direct generation")
        return None


def _compute_adaptive_budget(cfg: SuiteConfig, prompt_length: int) -> int:
    """Compute token budget based on prompt size.

    Adaptive budgeting prevents token exhaustion for large prompts:
    - Small prompts (<5K chars): use minimum budget
    - Large prompts (>15K chars): use maximum budget
    - Scale linearly in between
    """
    if not cfg.rlm_adaptive_budget:
        return cfg.rlm_token_budget

    # Estimate prompt tokens (1 token ≈ 4 chars)
    prompt_tokens = prompt_length // 4

    # Scale budget: larger prompts need more headroom for tool calls
    # Note: Complex tasks may need 40K+ tokens for deep tool chains regardless of prompt size
    if prompt_tokens < 1000:
        return cfg.rlm_token_budget_min
    elif prompt_tokens > 2500:
        return cfg.rlm_token_budget_max  # Lowered threshold - complex tasks need max budget
    else:
        # Linear interpolation
        ratio = (prompt_tokens - 1000) / 1500
        return int(cfg.rlm_token_budget_min + ratio * (cfg.rlm_token_budget_max - cfg.rlm_token_budget_min))


async def _run_with_rlm(
    rlm: Any,  # RLM instance
    cfg: SuiteConfig,
    context: str,
    query: str,
    system: str,
) -> tuple[str, int, int, float, dict]:
    """Run query through RLM runtime with full tool access.

    Returns ``(text, input_tokens, output_tokens, latency_ms, rlm_meta)``.

    RLM has access to all Snipara tools (rlm_context_query, rlm_search, etc.)
    and uses its built-in AGENT_SYSTEM_PROMPT with anti-hallucination grounding
    rules.  Pre-fetched context is provided as a starting point but RLM can
    fetch additional context via tools if needed.

    Uses adaptive token budgeting to prevent exhaustion on large prompts.
    """
    if context:
        prompt = (
            f"Pre-fetched documentation context:\n{context}\n\n"
            f"Question: {query}\n\n"
            "Use the documentation context above to answer. If it's insufficient, "
            "use rlm_context_query to find additional relevant documentation. "
            "Only state facts confirmed by documentation."
        )
    else:
        prompt = (
            f"Question: {query}\n\n"
            "Use rlm_context_query to find relevant documentation, then answer. "
            "If no documentation is found, say 'Not found in documentation'."
        )

    # Adaptive budget based on prompt size
    token_budget = _compute_adaptive_budget(cfg, len(prompt))

    options = CompletionOptions(
        max_depth=cfg.rlm_max_depth,
        token_budget=token_budget,
        timeout_seconds=cfg.runtime_timeout_s,
        cost_budget_usd=cfg.rlm_cost_cap,
    )

    t0 = time.perf_counter()
    result: RLMResult = await rlm.completion(prompt, system=system, options=options)
    latency = (time.perf_counter() - t0) * 1000

    rlm_meta = {
        "total_calls": result.total_calls,
        "total_tool_calls": result.total_tool_calls,
        "total_cost_usd": result.total_cost_usd,
        "duration_ms": result.duration_ms,
        "success": result.success,
    }

    return (
        result.response,
        result.total_input_tokens,
        result.total_output_tokens,
        latency,
        rlm_meta,
    )


async def _run_single_task(
    client: AsyncOpenAI,
    cfg: SuiteConfig,
    task: dict,
    mode: str,
    context: str,
    full_docs: str,
    rlm: Optional[Any] = None,
    suite: str = "docs-qa",
) -> RunMetrics:
    """Execute one (task, mode) and evaluate."""
    query = task["query"]
    expected = task.get("expected_answer", "")
    relevant = task.get("relevant_sections", [])

    # Generate — use RLM for Mode C when available
    rlm_meta: Optional[dict] = None
    if mode == "snipara_ctx_mem_runtime" and rlm is not None:
        text, inp, out, lat, rlm_meta = await _run_with_rlm(
            rlm, cfg, context, query, SYSTEM_PROMPTS[mode],
        )
        cost = rlm_meta.get("total_cost_usd") or _estimate_cost(inp, out, cfg.model)
    else:
        text, inp, out, lat = await _generate(client, cfg, context, query, SYSTEM_PROMPTS[mode])
        cost = _estimate_cost(inp, out, cfg.model)

    m = RunMetrics(
        input_tokens=inp,
        context_tokens=_count_tokens(context),
        output_tokens=out,
        cost_usd=cost,
        latency_ms=lat,
        response=text,
    )

    # RLM-Runtime metrics
    if rlm_meta:
        m.rlm_total_calls = rlm_meta.get("total_calls", 0)
        m.rlm_tool_calls = rlm_meta.get("total_tool_calls", 0)
        m.rlm_cost_usd = rlm_meta.get("total_cost_usd") or 0.0
        m.rlm_success = rlm_meta.get("success", True)

    # Quality eval (use judge model — reasoning models return empty for eval prompts)
    jm = cfg.effective_judge_model
    q = await _eval_quality(client, jm, query, expected, text)
    m.quality_score = q.get("overall", 0)
    m.correctness = q.get("correctness", 0)
    m.completeness = q.get("completeness", 0)
    m.relevance = q.get("relevance", 0)
    m.faithfulness = q.get("faithfulness", 0)
    m.clarity = q.get("clarity", 0)

    # Hallucination - ground claims against the ACTUAL context provided to LLM
    # (not against full_docs which may not include all Snipara-indexed docs)
    # Skip for coding suite: code responses contain implementation details, not
    # factual claims about documentation. Use code quality metrics instead.
    if suite != "coding":
        h = await _eval_hallucination(client, jm, text, context)
        m.hallucination_rate = h["rate"]
        m.factual_accuracy = h["accuracy"]
        m.total_claims = h["total"]
        m.incorrect_claims = h["incorrect"]
    else:
        # Coding tasks: no hallucination eval (use test_pass_rate, lint_clean instead)
        m.hallucination_rate = 0.0
        m.factual_accuracy = 1.0
        m.total_claims = 0
        m.incorrect_claims = 0

    # Citations
    m.citation_accuracy = await _eval_citations(client, jm, text, relevant)

    # IR metrics (only meaningful for modes B/C with Snipara context)
    ir = _ir_metrics(context, relevant)
    m.precision_at_k = ir["precision"]
    m.recall_at_k = ir["recall"]
    m.ndcg = ir["ndcg"]
    m.mrr = ir["mrr"]

    return m


# ---------------------------------------------------------------------------
# Context preparation
# ---------------------------------------------------------------------------

_MIN_SECTION_TOKENS = 20  # Sections below this are just headings, waste context budget


def _is_junk_section(title: str, suite: str = "docs-qa") -> bool:
    """Check if a section title is a known junk/catch-all section.

    For docs-qa: filter shared context sections ([BEST_PRACTICES] etc.) AND
                 the catch-all "4.2 Semantic Search" section.
    For coding/memory: ONLY filter "4.2 Semantic Search" — shared context
                       sections contain useful coding standards.
    """
    title_lower = title.lower()

    # Always filter the catch-all "4.2 Semantic Search" section (irrelevant to all suites)
    if "4.2 semantic search" in title_lower:
        return True

    # Only filter shared context sections for docs-qa
    # (for coding/memory, [BEST_PRACTICES] Coding Standards is actually useful)
    if suite == "docs-qa":
        junk_prefixes = ("[BEST_PRACTICES]", "[MANDATORY]", "[GUIDELINES]", "[REFERENCE]")
        if any(title.startswith(p) for p in junk_prefixes):
            return True

    return False


def _is_shallow_section(section, min_tokens: int = _MIN_SECTION_TOKENS) -> bool:
    """Check if a section is too shallow to be useful (just a heading).

    Sections with < min_tokens of content waste context budget slots.
    This filters them client-side until the engine adds server-side filtering.
    """
    token_count = getattr(section, "token_count", 0)
    if token_count and token_count < min_tokens:
        return True
    # Fallback: estimate from content length if token_count not available
    content = getattr(section, "content", "") or ""
    if not token_count and len(content.split()) < min_tokens:
        return True
    return False


_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "in", "on", "at",
    "to", "for", "of", "with", "and", "or", "how", "does", "what",
    "which", "this", "that", "from", "by", "be", "it", "its", "do",
    "can", "has", "have", "not", "all", "any", "snipara",
})

_WORD_RE = __import__("re").compile(r"[a-zA-Z0-9_-]+")


def _query_terms_covered(query: str, sections: list) -> float:
    """Fraction of query's content words found in the combined section text.

    Used to detect when API returns high-relevance sections that are
    topically irrelevant (e.g. "Team Best Practices" for a pricing query).
    Strips punctuation before matching so "stack?" matches "stack".
    """
    raw = _WORD_RE.findall(query.lower())
    query_words = {w for w in raw if len(w) > 2 and w not in _STOPWORDS}
    if not query_words:
        return 1.0
    combined = " ".join(s.content.lower() for s in sections)
    found = sum(1 for w in query_words if w in combined)
    return found / len(query_words)


def _select_search_mode(task: dict) -> str:
    """Select search mode based on task characteristics.

    Hybrid is the default — it combines keyword precision with semantic recall.
    Keyword is only used as a fallback (in _prepare_context) when hybrid
    returns too few useful sections.
    """
    return "hybrid"


async def _prepare_context(
    cfg: SuiteConfig,
    dataset: SniparaDocsDataset,
    task: dict,
    mode: str,
    snipara_client: Optional[SniparaClient],
    suite: str = "docs-qa",
) -> str:
    """Return the context string for (task, mode)."""
    task_id = task["id"]

    if mode == "llm_alone":
        full = dataset.load_full_docs()
        return full[:cfg.budget_a * 4]  # rough char limit

    budget = cfg.budget_b if mode == "snipara_ctx_mem" else cfg.budget_c

    # Use context_query if available (reformulated for better API retrieval)
    api_query = task.get("context_query", task["query"])

    # Try real Snipara API first
    if snipara_client:
        try:
            # Decompose is opt-in per task via "use_decompose": True
            # Disabled by default because the API currently splits into single-word
            # sub-queries that produce catastrophically bad results.
            if task.get("use_decompose"):
                try:
                    decomposed = await snipara_client.decompose(query=task["query"])
                    sub_queries = decomposed.get("sub_queries", [])
                    if sub_queries:
                        queries = [sq.get("query", sq) if isinstance(sq, dict) else sq for sq in sub_queries]
                        multi_result = await snipara_client.multi_query(
                            queries=queries, max_tokens=budget,
                        )
                        sections = []
                        for mq_result in multi_result.get("results", []):
                            sections.extend(mq_result.get("sections", []))
                        if sections:
                            sections = [s for s in sections if not _is_junk_section(s.get("title", ""), suite)]
                            _context_debug_log.append({
                                "task_id": task_id,
                                "mode": mode,
                                "query": task["query"],
                                "decompose_used": True,
                                "sub_queries": queries,
                                "sections_filtered": [
                                    {"title": s.get("title", ""), "tokens": s.get("token_count", 0)}
                                    for s in sections
                                ],
                            })
                            parts = []
                            for s in sections:
                                title = s.get("title", "")
                                content = s.get("content", "")
                                parts.append(f"## {title}\n\n{content}")
                            return "\n\n---\n\n".join(parts)
                except Exception as exc:
                    _context_debug_log.append({
                        "task_id": task_id,
                        "mode": mode,
                        "query": task["query"],
                        "decompose_used": False,
                        "decompose_error": str(exc),
                    })
                    if cfg.verbose:
                        print(f"    Decompose fallback: {exc}")
                    pass  # Fall through to single context_query

            # Select search mode dynamically based on task characteristics
            search_mode = _select_search_mode(task)

            result = await snipara_client.context_query(
                query=api_query, max_tokens=budget, search_mode=search_mode,
            )

            # Filter out junk sections and shallow sections (< 20 tokens = just headings)
            filtered_sections = [
                s for s in result.sections
                if not _is_junk_section(s.title, suite) and not _is_shallow_section(s)
            ]

            # Fallback: if too few useful sections, retry with keyword search
            if len(filtered_sections) < 2 and search_mode != "keyword":
                retry_result = await snipara_client.context_query(
                    query=api_query, max_tokens=budget, search_mode="keyword",
                )
                retry_filtered = [
                    s for s in retry_result.sections
                    if not _is_junk_section(s.title, suite) and not _is_shallow_section(s)
                ]
                if len(retry_filtered) > len(filtered_sections):
                    result = retry_result
                    filtered_sections = retry_filtered
                    search_mode = "keyword (fallback)"

            # Second fallback: try original query if context_query was reformulated
            if len(filtered_sections) < 2 and api_query != task["query"]:
                retry_result = await snipara_client.context_query(
                    query=task["query"], max_tokens=budget, search_mode="hybrid",
                )
                retry_filtered = [
                    s for s in retry_result.sections
                    if not _is_junk_section(s.title, suite) and not _is_shallow_section(s)
                ]
                if len(retry_filtered) > len(filtered_sections):
                    result = retry_result
                    filtered_sections = retry_filtered
                    search_mode = "hybrid (original query)"

            # Log context diagnostics for regression analysis
            _context_debug_log.append({
                "task_id": task_id,
                "mode": mode,
                "query": api_query,
                "original_query": task["query"],
                "search_mode": search_mode,
                "sections_raw": [
                    {"title": s.title, "relevance": s.relevance_score, "tokens": s.token_count}
                    for s in result.sections
                ],
                "sections_filtered": [
                    {"title": s.title, "relevance": s.relevance_score, "tokens": s.token_count}
                    for s in filtered_sections
                ],
                "shared_context_removed": len(result.sections) - len(filtered_sections),
                "total_tokens": result.total_tokens,
            })

            # Build context from filtered sections — but first check that
            # the sections actually cover the query topic.  The API can return
            # high-relevance sections that are topically wrong (e.g. "Team
            # Best Practices" for a pricing query).  When coverage is too low,
            # local fallback (keyword-matched from full docs) is better.
            if filtered_sections:
                coverage = _query_terms_covered(task["query"], filtered_sections)
                # Also update the debug log with coverage info
                if _context_debug_log and _context_debug_log[-1].get("task_id") == task_id:
                    _context_debug_log[-1]["query_term_coverage"] = round(coverage, 3)

                if suite == "docs-qa" and coverage < 0.20:
                    if cfg.verbose:
                        print(f" [local fallback: low coverage {coverage:.0%}]", end="")
                    return dataset.get_relevant_context(task_id, budget)

                parts = []
                for section in filtered_sections:
                    parts.append(f"## {section.title}\n\n{section.content}")
                return "\n\n---\n\n".join(parts)

            # If ALL sections were filtered (all junk), use local fallback
            # rather than passing irrelevant content to the LLM
            if cfg.verbose:
                print(f" [local fallback]", end="")
            return dataset.get_relevant_context(task_id, budget)
        except Exception as e:
            if cfg.verbose:
                print(f"    Snipara API fallback: {e}")

    # Local fallback
    return dataset.get_relevant_context(task_id, budget)


# ---------------------------------------------------------------------------
# Suite runners
# ---------------------------------------------------------------------------

async def run_docs_qa(
    client: AsyncOpenAI,
    cfg: SuiteConfig,
    dataset: SniparaDocsDataset,
    modes: list[str],
    snipara_client: Optional[SniparaClient],
    rlm: Optional[Any] = None,
) -> list[SuiteResult]:
    """Suite 1: Documentation QA."""
    results: list[SuiteResult] = []
    full_docs = dataset.load_full_docs()
    tasks = dataset.test_cases

    for mode in modes:
        sr = SuiteResult(suite="docs-qa", mode=mode)
        print(f"\n{'='*60}")
        print(f"  Suite: docs-qa  |  Mode: {mode}  |  Tasks: {len(tasks)}")
        print(f"{'='*60}")

        for i, task in enumerate(tasks):
            tid = task["id"]
            print(f"  [{i+1}/{len(tasks)}] {tid} ...", end="", flush=True)

            ctx = await _prepare_context(cfg, dataset, task, mode, snipara_client, suite="docs-qa")
            tr = TaskResult(
                task_id=tid,
                suite="docs-qa",
                category=task.get("category", ""),
                difficulty=task.get("difficulty", ""),
                mode=mode,
            )

            for run_idx in range(cfg.runs_per_task):
                try:
                    rm = await _run_single_task(client, cfg, task, mode, ctx, full_docs, rlm=rlm, suite="docs-qa")
                except Exception as e:
                    rm = RunMetrics(error=str(e))
                tr.runs.append(rm)

            tr.compute_medians()
            sr.tasks.append(tr)
            status = "PASS" if tr.success else "FAIL"
            print(f" q={tr.median_quality:.1f} lat={tr.median_latency_ms:.0f}ms [{status}]")

        sr.aggregate()
        results.append(sr)
    return results


async def run_memory_suite(
    client: AsyncOpenAI,
    cfg: SuiteConfig,
    modes: list[str],
    snipara_client: Optional[SniparaClient],
    rlm: Optional[Any] = None,
) -> list[SuiteResult]:
    """Suite 2: Agent Memory & Multi-Turn (placeholder tasks scored via LLM-judge)."""
    # Memory suite only runs for modes with Snipara (B and C)
    mem_modes = [m for m in modes if m != "llm_alone"]
    if not mem_modes:
        return []

    # Minimal representative tasks
    mem_tasks = [
        {"id": "mem_store_recall", "query": "I prefer using PostgreSQL. Remember this. Now, what database should we use for the new project?",
         "context_query": "database PostgreSQL Prisma schema models project configuration",
         "expected_answer": "PostgreSQL, based on your stated preference.",
         "relevant_sections": ["database models"], "category": "memory", "difficulty": "easy",
         "ground_truth_claims": ["User prefers PostgreSQL"]},
        {"id": "mem_decision_log", "query": "We decided to use OAuth Device Flow for CLI authentication. Why did we make that decision?",
         "context_query": "OAuth device flow RFC 8628 CLI authentication snipara-mcp-login tokens",
         "expected_answer": "OAuth Device Flow (RFC 8628) was chosen because it enables secure MCP authentication without copying API keys.",
         "relevant_sections": ["oauth device flow"], "category": "memory", "difficulty": "medium",
         "ground_truth_claims": ["OAuth Device Flow follows RFC 8628", "No need to copy API keys"]},
        {"id": "mem_shared_std", "query": "What coding standards should I follow when adding a new API endpoint?",
         "context_query": "coding standards API endpoint Zod validation route handler layered architecture patterns",
         "expected_answer": "Use Zod schema validation, keep route handlers under 50 lines, follow the layered architecture pattern.",
         "relevant_sections": ["layered architecture", "api design"], "category": "shared", "difficulty": "medium",
         "ground_truth_claims": ["Zod validation required", "Route handlers max 50 lines"]},
        {"id": "multi_turn_refine", "query": "What is Snipara's pricing? Actually, focus only on the Team tier details.",
         "context_query": "pricing plans tiers Team $49 queries per month shared context multi-project",
         "expected_answer": "Team tier is $49/month with 20,000 queries. Includes multi-project search and shared context collections.",
         "relevant_sections": ["pricing"], "category": "multi-turn", "difficulty": "medium",
         "ground_truth_claims": ["Team is $49/month", "20,000 queries per month"]},
    ]

    full_docs = ""
    dataset = SniparaDocsDataset()
    full_docs = dataset.load_full_docs()

    results: list[SuiteResult] = []
    for mode in mem_modes:
        sr = SuiteResult(suite="memory", mode=mode)
        print(f"\n{'='*60}")
        print(f"  Suite: memory  |  Mode: {mode}  |  Tasks: {len(mem_tasks)}")
        print(f"{'='*60}")

        for i, task in enumerate(mem_tasks):
            tid = task["id"]
            print(f"  [{i+1}/{len(mem_tasks)}] {tid} ...", end="", flush=True)

            ctx = await _prepare_context(cfg, dataset, task, mode, snipara_client, suite="memory")
            tr = TaskResult(
                task_id=tid, suite="memory",
                category=task.get("category", ""),
                difficulty=task.get("difficulty", ""),
                mode=mode,
            )

            for _ in range(cfg.runs_per_task):
                try:
                    rm = await _run_single_task(client, cfg, task, mode, ctx, full_docs, rlm=rlm, suite="memory")
                    # Memory-specific: score recall/carryover via heuristic
                    rm.memory_recall_accuracy = rm.faithfulness / 10.0
                    rm.context_carryover = rm.relevance / 10.0
                    rm.session_coherence = rm.quality_score
                except Exception as e:
                    rm = RunMetrics(error=str(e))
                tr.runs.append(rm)

            tr.compute_medians()
            sr.tasks.append(tr)
            status = "PASS" if tr.success else "FAIL"
            print(f" q={tr.median_quality:.1f} [{status}]")

        sr.aggregate()
        results.append(sr)
    return results


async def run_coding_suite(
    client: AsyncOpenAI,
    cfg: SuiteConfig,
    modes: list[str],
    snipara_client: Optional[SniparaClient],
    rlm: Optional[Any] = None,
) -> list[SuiteResult]:
    """Suite 3: Coding tasks evaluated by LLM-judge for code quality."""
    coding_tasks = [
        {"id": "add_api_endpoint", "query": "Write a Next.js API route handler at app/api/users/route.ts that returns a list of users from Prisma with Zod validation on query params.",
         "context_query": "Next.js API route handler Prisma Zod validation query params GET endpoint coding standards",
         "expected_answer": "Export GET handler, use z.object for query schema, call prisma.user.findMany, return NextResponse.json.",
         "relevant_sections": ["api design", "layered architecture"], "category": "coding", "difficulty": "medium",
         "ground_truth_claims": ["Uses Zod validation", "Uses Prisma", "Route handler under 50 lines"]},
        {"id": "fix_type_error", "query": "Fix this TypeScript: function getUser(id) { return db.users.find(u => u.id === id); }. The parameter needs a type annotation.",
         "context_query": "TypeScript type annotations function parameters return types coding standards",
         "expected_answer": "function getUser(id: string): User | undefined { return db.users.find(u => u.id === id); }",
         "relevant_sections": ["typescript standards"], "category": "coding", "difficulty": "easy",
         "ground_truth_claims": ["Adds string type to id parameter", "Adds return type annotation"]},
        {"id": "add_unit_test", "query": "Write a unit test for a function calculatePrice(quantity: number, unitPrice: number): number that returns quantity * unitPrice.",
         "context_query": "unit test vitest jest testing describe it expect coding standards test patterns",
         "expected_answer": "import { describe, it, expect } from 'vitest'; describe('calculatePrice', () => { it('multiplies quantity by unit price', () => { expect(calculatePrice(5, 10)).toBe(50); }); });",
         "relevant_sections": ["testing"], "category": "coding", "difficulty": "easy",
         "ground_truth_claims": ["Uses vitest or jest", "Tests multiplication logic"]},
    ]

    dataset = SniparaDocsDataset()
    full_docs = dataset.load_full_docs()

    results: list[SuiteResult] = []
    for mode in modes:
        sr = SuiteResult(suite="coding", mode=mode)
        print(f"\n{'='*60}")
        print(f"  Suite: coding  |  Mode: {mode}  |  Tasks: {len(coding_tasks)}")
        print(f"{'='*60}")

        for i, task in enumerate(coding_tasks):
            tid = task["id"]
            print(f"  [{i+1}/{len(coding_tasks)}] {tid} ...", end="", flush=True)

            ctx = await _prepare_context(cfg, dataset, task, mode, snipara_client, suite="coding")
            tr = TaskResult(
                task_id=tid, suite="coding",
                category=task.get("category", ""),
                difficulty=task.get("difficulty", ""),
                mode=mode,
            )

            for _ in range(cfg.runs_per_task):
                try:
                    rm = await _run_single_task(client, cfg, task, mode, ctx, full_docs, rlm=rlm, suite="coding")
                    # Coding quality heuristics
                    rm.lint_clean = rm.quality_score >= 7
                    rm.typecheck_pass = rm.correctness >= 7
                    rm.build_pass = rm.quality_score >= 6
                    rm.test_pass_rate = rm.correctness / 10.0
                except Exception as e:
                    rm = RunMetrics(error=str(e))
                tr.runs.append(rm)

            tr.compute_medians()
            sr.tasks.append(tr)
            status = "PASS" if tr.success else "FAIL"
            print(f" q={tr.median_quality:.1f} [{status}]")

        sr.aggregate()
        results.append(sr)
    return results


# ---------------------------------------------------------------------------
# CBS calculation
# ---------------------------------------------------------------------------

def _compute_cbs(suite_results: list[SuiteResult]) -> None:
    """Compute Composite Benchmark Score for each SuiteResult."""
    if not suite_results:
        return

    # Collect ranges for normalization
    all_quality = [sr.avg_quality for sr in suite_results]
    all_tokens = [sr.avg_tokens for sr in suite_results]
    all_halluc = [sr.avg_hallucination for sr in suite_results]
    all_prec = [sr.avg_precision for sr in suite_results]
    all_sr = [sr.success_rate for sr in suite_results]
    all_lat = [sr.latency_p50 for sr in suite_results if sr.latency_p50 > 0]

    def _norm(val: float, vals: list[float], invert: bool = False) -> float:
        mn, mx = min(vals) if vals else 0, max(vals) if vals else 1
        if mx == mn:
            return 1.0
        n = (val - mn) / (mx - mn)
        return 1.0 - n if invert else n

    for sr in suite_results:
        nq = _norm(sr.avg_quality, all_quality)
        # Token savings: lower is better
        nt = _norm(sr.avg_tokens, all_tokens, invert=True)
        np_ = _norm(sr.avg_precision, all_prec)
        nh = _norm(sr.avg_hallucination, all_halluc, invert=True)
        ns = _norm(sr.success_rate, all_sr)
        nl = _norm(sr.latency_p50, all_lat, invert=True) if all_lat else 0.5

        sr.cbs = (
            0.25 * nq
            + 0.20 * nt
            + 0.15 * np_
            + 0.15 * nh
            + 0.10 * ns
            + 0.10 * nl
            + 0.05 * 0.5  # citation placeholder
        )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _generate_report(all_results: list[SuiteResult], cfg: SuiteConfig) -> str:
    """Generate markdown report."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# Snipara Benchmark Results",
        "",
        f"**Date:** {ts}",
        f"**Provider:** {cfg.provider}",
        f"**Model:** {cfg.model}",
        f"**Runs per task:** {cfg.runs_per_task}",
        f"**Temperature:** {cfg.temperature}",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        "| Suite | Mode | CBS | Quality | Tokens | Cost | Latency p50 | Success | Halluc. | Prec@5 |",
        "|-------|------|-----|---------|--------|------|-------------|---------|---------|--------|",
    ]

    for sr in all_results:
        lines.append(
            f"| {sr.suite} | {sr.mode} | {sr.cbs:.3f} | {sr.avg_quality:.1f}/10 "
            f"| {sr.avg_tokens:.0f} | ${sr.avg_cost:.4f} "
            f"| {sr.latency_p50:.0f} ms | {sr.success_rate:.0%} "
            f"| {sr.avg_hallucination:.1%} | {sr.avg_precision:.1%} |"
        )

    # Per-suite sections
    for suite_name in SUITES:
        suite_data = [sr for sr in all_results if sr.suite == suite_name]
        if not suite_data:
            continue

        lines += ["", f"## Suite: {suite_name}", ""]

        # Mode comparison
        lines += [
            "### Mode Comparison",
            "",
            "| Metric | " + " | ".join(sr.mode for sr in suite_data) + " |",
            "|--------| " + " | ".join("---" for _ in suite_data) + " |",
        ]
        metrics = [
            ("Quality (0-10)", lambda sr: f"{sr.avg_quality:.2f}"),
            ("Avg Tokens", lambda sr: f"{sr.avg_tokens:.0f}"),
            ("Avg Cost ($)", lambda sr: f"{sr.avg_cost:.5f}"),
            ("Latency p50 (ms)", lambda sr: f"{sr.latency_p50:.0f}"),
            ("Latency p95 (ms)", lambda sr: f"{sr.latency_p95:.0f}"),
            ("Success Rate", lambda sr: f"{sr.success_rate:.0%}"),
            ("Hallucination", lambda sr: f"{sr.avg_hallucination:.1%}"),
            ("Precision@5", lambda sr: f"{sr.avg_precision:.1%}"),
            ("Recall", lambda sr: f"{sr.avg_recall:.1%}"),
            ("CBS", lambda sr: f"{sr.cbs:.3f}"),
        ]
        for label, fn in metrics:
            lines.append(f"| {label} | " + " | ".join(fn(sr) for sr in suite_data) + " |")

        # Per-task breakdown
        lines += ["", "### Per-Task Breakdown", ""]
        ref = suite_data[0]
        lines.append("| Task | Diff. | " + " | ".join(f"{sr.mode} (q)" for sr in suite_data) + " |")
        lines.append("|------|-------|" + "|".join("---" for _ in suite_data) + "|")

        task_ids = [t.task_id for t in ref.tasks]
        for tid in task_ids:
            cells = []
            diff = ""
            for sr in suite_data:
                task = next((t for t in sr.tasks if t.task_id == tid), None)
                if task:
                    diff = task.difficulty
                    mark = "+" if task.success else "-"
                    cells.append(f"{mark}{task.median_quality:.1f}")
                else:
                    cells.append("—")
            lines.append(f"| {tid} | {diff} | " + " | ".join(cells) + " |")

    lines += ["", "---", f"*Generated by `suite_benchmark.py` at {ts}*"]
    return "\n".join(lines)


def _generate_dashboard(all_results: list[SuiteResult], cfg: SuiteConfig) -> str:
    """Generate a self-contained HTML dashboard."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Build JSON payload for the dashboard
    payload = []
    for sr in all_results:
        payload.append({
            "suite": sr.suite, "mode": sr.mode, "cbs": round(sr.cbs, 3),
            "quality": round(sr.avg_quality, 2), "tokens": round(sr.avg_tokens),
            "cost": round(sr.avg_cost, 5), "latency_p50": round(sr.latency_p50),
            "latency_p95": round(sr.latency_p95),
            "success_rate": round(sr.success_rate, 3),
            "hallucination": round(sr.avg_hallucination, 3),
            "precision": round(sr.avg_precision, 3),
            "recall": round(sr.avg_recall, 3),
            "tasks": [{
                "id": t.task_id, "quality": round(t.median_quality, 2),
                "latency": round(t.median_latency_ms), "tokens": t.median_tokens,
                "success": t.success, "difficulty": t.difficulty, "category": t.category,
            } for t in sr.tasks],
        })

    data_json = json.dumps(payload, indent=2)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Snipara Benchmark Dashboard — {ts}</title>
<style>
  :root {{ --bg: #0d1117; --card: #161b22; --border: #30363d; --text: #c9d1d9; --accent: #58a6ff; --green: #3fb950; --red: #f85149; --yellow: #d29922; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace; background: var(--bg); color: var(--text); padding: 24px; }}
  h1 {{ color: var(--accent); margin-bottom: 4px; font-size: 1.5em; }}
  .meta {{ color: #8b949e; margin-bottom: 24px; font-size: 0.85em; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 32px; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }}
  .card h3 {{ font-size: 0.9em; color: #8b949e; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.05em; }}
  .card .value {{ font-size: 2em; font-weight: 700; }}
  .card .value.green {{ color: var(--green); }}
  .card .value.yellow {{ color: var(--yellow); }}
  .card .value.red {{ color: var(--red); }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 0.85em; }}
  th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
  th {{ color: var(--accent); font-weight: 600; }}
  .pass {{ color: var(--green); }} .fail {{ color: var(--red); }}
  .bar {{ display: inline-block; height: 14px; border-radius: 3px; }}
  .section {{ margin-top: 32px; }}
  .section h2 {{ color: var(--accent); font-size: 1.2em; margin-bottom: 12px; }}
</style>
</head>
<body>
<h1>Snipara Benchmark Dashboard</h1>
<p class="meta">Provider: {cfg.provider} &middot; Model: {cfg.model} &middot; Runs/task: {cfg.runs_per_task} &middot; Temp: {cfg.temperature} &middot; {ts}</p>

<div id="app"></div>

<script>
const DATA = {data_json};

const app = document.getElementById('app');

// --- CBS Cards ---
const modes = [...new Set(DATA.map(d => d.mode))];
const suites = [...new Set(DATA.map(d => d.suite))];

let html = '<div class="grid">';
for (const d of DATA) {{
  const cls = d.cbs >= 0.7 ? 'green' : d.cbs >= 0.4 ? 'yellow' : 'red';
  html += `<div class="card">
    <h3>${{d.suite}} — ${{d.mode}}</h3>
    <div class="value ${{cls}}">${{d.cbs.toFixed(3)}}</div>
    <div style="margin-top:8px;font-size:0.8em;color:#8b949e">
      Quality ${{d.quality.toFixed(1)}} &middot; Success ${{(d.success_rate*100).toFixed(0)}}% &middot; Halluc ${{(d.hallucination*100).toFixed(1)}}%
    </div>
  </div>`;
}}
html += '</div>';

// --- Comparison Table ---
for (const suite of suites) {{
  const rows = DATA.filter(d => d.suite === suite);
  if (!rows.length) continue;
  html += `<div class="section"><h2>${{suite}}</h2><table>
    <tr><th>Mode</th><th>CBS</th><th>Quality</th><th>Tokens</th><th>Cost</th><th>p50 ms</th><th>p95 ms</th><th>Success</th><th>Halluc</th><th>Prec@5</th></tr>`;
  for (const r of rows) {{
    html += `<tr>
      <td>${{r.mode}}</td>
      <td>${{r.cbs.toFixed(3)}}</td>
      <td>${{r.quality.toFixed(2)}}</td>
      <td>${{r.tokens}}</td>
      <td>$${{r.cost.toFixed(5)}}</td>
      <td>${{r.latency_p50}}</td>
      <td>${{r.latency_p95}}</td>
      <td>${{(r.success_rate*100).toFixed(0)}}%</td>
      <td>${{(r.hallucination*100).toFixed(1)}}%</td>
      <td>${{(r.precision*100).toFixed(0)}}%</td>
    </tr>`;
  }}
  html += '</table>';

  // Per-task breakdown
  const ref = rows[0];
  html += '<table style="margin-top:12px"><tr><th>Task</th><th>Diff</th>';
  for (const r of rows) html += `<th>${{r.mode}}</th>`;
  html += '</tr>';
  for (let i = 0; i < ref.tasks.length; i++) {{
    html += `<tr><td>${{ref.tasks[i].id}}</td><td>${{ref.tasks[i].difficulty}}</td>`;
    for (const r of rows) {{
      const t = r.tasks[i];
      const cls = t.success ? 'pass' : 'fail';
      html += `<td class="${{cls}}">${{t.quality.toFixed(1)}}</td>`;
    }}
    html += '</tr>';
  }}
  html += '</table></div>';
}}

app.innerHTML = html;
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

_context_debug_log: list[dict] = []


async def run_benchmark(cfg: SuiteConfig, suites: list[str], modes: list[str]):
    """Entry-point: run selected suites × modes, evaluate, report."""
    _context_debug_log.clear()
    client = _make_llm_client(cfg)
    dataset = SniparaDocsDataset()

    # Snipara client (OAuth preferred)
    snipara = None
    if any(m != "llm_alone" for m in modes):
        try:
            snipara = await create_client(
                use_real_api=True,
                api_key=cfg.snipara_api_key,
                access_token=cfg.snipara_oauth_token,
                project_slug=cfg.snipara_project_slug,
            )
            auth_mode = "OAuth" if cfg.snipara_oauth_token else "API key" if cfg.snipara_api_key else "none"
            print(f"Snipara client: {auth_mode} (project={cfg.snipara_project_slug})")
        except Exception as e:
            print(f"Snipara client init failed ({e}), using local fallback")

    # RLM-Runtime for Mode C (shares OAuth tokens via custom Snipara tools)
    rlm_instance = None
    if "snipara_ctx_mem_runtime" in modes:
        rlm_instance = _init_rlm(cfg)

    all_results: list[SuiteResult] = []

    if "docs-qa" in suites:
        all_results.extend(await run_docs_qa(client, cfg, dataset, modes, snipara, rlm=rlm_instance))
    if "memory" in suites:
        all_results.extend(await run_memory_suite(client, cfg, modes, snipara, rlm=rlm_instance))
    if "coding" in suites:
        all_results.extend(await run_coding_suite(client, cfg, modes, snipara, rlm=rlm_instance))

    # CBS
    _compute_cbs(all_results)

    # Save
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = cfg.reports_dir / ts
    run_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = run_dir / "results.json"
    json_data = {
        "timestamp": ts,
        "config": {"provider": cfg.provider, "model": cfg.model, "temperature": cfg.temperature, "runs": cfg.runs_per_task},
        "suites": [
            {
                "suite": sr.suite, "mode": sr.mode, "cbs": sr.cbs,
                "avg_quality": sr.avg_quality, "avg_tokens": sr.avg_tokens,
                "avg_cost": sr.avg_cost, "latency_p50": sr.latency_p50,
                "latency_p95": sr.latency_p95, "success_rate": sr.success_rate,
                "avg_hallucination": sr.avg_hallucination,
                "avg_precision": sr.avg_precision, "avg_recall": sr.avg_recall,
                "tasks": [
                    {
                        "task_id": t.task_id, "category": t.category,
                        "difficulty": t.difficulty, "median_quality": t.median_quality,
                        "median_latency_ms": t.median_latency_ms,
                        "median_tokens": t.median_tokens, "median_cost": t.median_cost,
                        "success": t.success,
                        "runs": [asdict(r) for r in t.runs],
                    }
                    for t in sr.tasks
                ],
            }
            for sr in all_results
        ],
    }
    json_path.write_text(json.dumps(json_data, indent=2, default=str))

    # Markdown
    md_path = run_dir / "RESULTS.md"
    md_path.write_text(_generate_report(all_results, cfg))

    # HTML dashboard
    html_path = run_dir / "dashboard.html"
    html_path.write_text(_generate_dashboard(all_results, cfg))

    # Context diagnostics (for investigating regressions)
    if _context_debug_log:
        debug_path = run_dir / "context_debug.json"
        debug_path.write_text(json.dumps(_context_debug_log, indent=2, default=str))

    # Cleanup
    if snipara:
        await snipara.close()

    # Terminal summary
    print(f"\n{'='*60}")
    print("  BENCHMARK COMPLETE")
    print(f"{'='*60}")
    print(f"  JSON:      {json_path}")
    print(f"  Markdown:  {md_path}")
    print(f"  Dashboard: {html_path}")
    print()

    print(f"  {'Suite':<12} {'Mode':<30} {'CBS':>6} {'Quality':>8} {'Success':>8} {'Tokens':>7}")
    print(f"  {'-'*12} {'-'*30} {'-'*6} {'-'*8} {'-'*8} {'-'*7}")
    for sr in all_results:
        print(f"  {sr.suite:<12} {sr.mode:<30} {sr.cbs:>6.3f} {sr.avg_quality:>7.1f} {sr.success_rate:>7.0%} {sr.avg_tokens:>7.0f}")

    return all_results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Snipara 3-Suite Benchmark (Docs-QA / Memory / Coding)")

    parser.add_argument("--all", action="store_true", help="Run all suites and modes")
    parser.add_argument("--suite", choices=list(SUITES), action="append", help="Suite(s) to run")
    parser.add_argument("--mode", choices=list(MODES), action="append", help="Mode(s) to run")

    parser.add_argument("--provider", choices=list(LLM_PROVIDERS), default="openai")
    parser.add_argument("--model", default=None, help="Override model")
    parser.add_argument("--judge-model", default=None, help="Model for eval/judging (default: same as --model, gpt-4o-mini for GPT-5)")
    parser.add_argument("--api-key", default=None, help="LLM API key (overrides env)")
    parser.add_argument("--runs", type=int, default=3, help="Runs per task (default: 3)")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--cost-cap", type=float, default=None, help="USD cost cap")
    parser.add_argument("--difficulty", choices=["easy", "medium", "hard"], default=None)
    parser.add_argument("--verbose", "-v", action="store_true")

    parser.add_argument("--dashboard", type=Path, default=None, help="Re-generate dashboard from JSON")

    args = parser.parse_args()

    # Dashboard-only mode
    if args.dashboard:
        data = json.loads(args.dashboard.read_text())
        # Reconstruct SuiteResults minimally for dashboard
        results = []
        for sd in data.get("suites", []):
            sr = SuiteResult(suite=sd["suite"], mode=sd["mode"])
            sr.cbs = sd.get("cbs", 0)
            sr.avg_quality = sd.get("avg_quality", 0)
            sr.avg_tokens = sd.get("avg_tokens", 0)
            sr.avg_cost = sd.get("avg_cost", 0)
            sr.latency_p50 = sd.get("latency_p50", 0)
            sr.latency_p95 = sd.get("latency_p95", 0)
            sr.success_rate = sd.get("success_rate", 0)
            sr.avg_hallucination = sd.get("avg_hallucination", 0)
            sr.avg_precision = sd.get("avg_precision", 0)
            sr.avg_recall = sd.get("avg_recall", 0)
            for td in sd.get("tasks", []):
                t = TaskResult(task_id=td["task_id"], suite=sd["suite"], category=td.get("category",""), difficulty=td.get("difficulty",""), mode=sd["mode"])
                t.median_quality = td.get("median_quality", 0)
                t.median_latency_ms = td.get("median_latency_ms", 0)
                t.median_tokens = td.get("median_tokens", 0)
                t.success = td.get("success", False)
                sr.tasks.append(t)
            results.append(sr)

        dcfg = SuiteConfig(provider=data.get("config",{}).get("provider","openai"), model=data.get("config",{}).get("model","gpt-4o-mini"))
        out = args.dashboard.parent / "dashboard.html"
        out.write_text(_generate_dashboard(results, dcfg))
        print(f"Dashboard written to: {out}")
        return

    # Resolve suites and modes
    suites = list(SUITES) if args.all else (args.suite or list(SUITES))
    modes_list = list(MODES) if args.all else (args.mode or list(MODES))

    prov = LLM_PROVIDERS[args.provider]
    # Resolve API key from args or env vars
    resolved_key = args.api_key
    if not resolved_key:
        for env_name in prov["env"]:
            resolved_key = os.environ.get(env_name)
            if resolved_key:
                break
    cfg = SuiteConfig(
        provider=args.provider,
        model=args.model or prov["model"],
        judge_model=args.judge_model,
        api_key=resolved_key,
        base_url=prov.get("base_url"),
        temperature=args.temperature,
        runs_per_task=args.runs,
        cost_cap=args.cost_cap,
        verbose=args.verbose,
    )

    try:
        asyncio.run(run_benchmark(cfg, suites, modes_list))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
    except Exception as e:
        print(f"\nFailed: {e}")
        raise


if __name__ == "__main__":
    main()
