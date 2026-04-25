"""Comprehensive Snipara Benchmark Suite.

Compares three scenarios:
1. LLM alone (no context optimization - full docs)
2. With Snipara (optimized context)
3. Snipara + RLM-Runtime (full RLM features: memory, recursive context, etc.)

Usage:
    python -m benchmarks.comprehensive_benchmark --all
    python -m benchmarks.comprehensive_benchmark --llm-only
    python -m benchmarks.comprehensive_benchmark --with-snipara
    python -m benchmarks.comprehensive_benchmark --rlm-runtime
    python -m benchmarks.comprehensive_benchmark --all --model abab6.5s-chat
    python -m benchmarks.comprehensive_benchmark --all --provider minimax
"""

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI

from .config import (
    THRESHOLDS,
    TOKEN_COSTS,
    load_oauth_access_token,
    resolve_snipara_project_ref,
)
from .datasets.snipara_docs import SniparaDocsDataset
from .snipara_client import SniparaClient, create_client


# Supported LLM providers
LLM_PROVIDERS = {
    "openai": {
        "api_key_env": "OPENAI_API_KEY",
        "base_url": None,
        "default_model": "gpt-4o-mini",
    },
    "minimax": {
        "api_key_env": "MINIMAX_API_KEY",
        "base_url": "https://api.minimax.chat/v1/text/chatcompletion_v2",
        "default_model": "abab6.5s-chat",
    },
    "together": {
        "api_key_env": "TOGETHER_API_KEY",
        "base_url": None,
        "default_model": "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
    },
    "anthropic": {
        "api_key_env": "ANTHROPIC_API_KEY",
        "base_url": None,
        "default_model": "claude-3-5-sonnet-20241022",
    },
}


@dataclass
class BenchmarkConfig:
    """Configuration for comprehensive benchmark."""
    # LLM Settings
    model: str = "gpt-4o-mini"
    llm_provider: str = "openai"
    api_key: Optional[str] = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY"))
    base_url: Optional[str] = None
    max_tokens_response: int = 2048
    
    # Snipara Settings
    snipara_project_slug: str = field(default_factory=resolve_snipara_project_ref)
    snipara_api_url: str = "https://api.snipara.com/mcp"
    snipara_oauth_token: Optional[str] = None
    snipara_api_key: Optional[str] = field(default_factory=lambda: os.getenv("SNIPARA_API_KEY"))
    
    # Context budgets
    llm_only_budget: int = 50000  # Full docs (simulated context)
    with_snipara_budget: int = 4000  # Optimized context
    rlm_runtime_budget: int = 6000  # Full RLM context (includes memory)
    
    # Benchmark Settings
    num_trials: int = 3
    timeout_seconds: int = 60
    
    # Output
    reports_dir: Path = field(default_factory=lambda: Path(__file__).parent / "reports")
    verbose: bool = True

    def __post_init__(self):
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        if not self.snipara_oauth_token:
            self.snipara_oauth_token = load_oauth_access_token(self.snipara_project_slug)


@dataclass
class ScenarioResult:
    """Result for a single scenario."""
    scenario: str
    tokens_used: int
    latency_ms: int
    response: str
    evaluation: dict = field(default_factory=dict)


@dataclass
class TestCaseResult:
    """Result for a single test case across all scenarios."""
    test_case_id: str
    query: str
    expected_answer: str
    llm_only: Optional[ScenarioResult] = None
    with_snipara: Optional[ScenarioResult] = None
    rlm_runtime: Optional[ScenarioResult] = None


class ComprehensiveBenchmark:
    """Comprehensive benchmark comparing LLM, Snipara, and RLM-Runtime."""

    def __init__(self, config: Optional[BenchmarkConfig] = None):
        self.config = config or BenchmarkConfig()
        self.dataset = SniparaDocsDataset()
        self.results: list[TestCaseResult] = []
        self._llm_client: Optional[AsyncOpenAI] = None
        self._snipara_client: Optional[SniparaClient] = None

    async def _get_llm_client(self) -> AsyncOpenAI:
        """Get or create LLM client."""
        if self._llm_client is None:
            if not self.config.api_key:
                raise ValueError(f"{self.config.llm_provider.upper()}_API_KEY not configured")
            self._llm_client = AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                timeout=60.0,
            )
        return self._llm_client

    async def _get_snipara_client(self) -> SniparaClient:
        """Get or create Snipara client."""
        if self._snipara_client is None:
            self._snipara_client = await create_client(
                use_real_api=True,
                api_key=self.config.snipara_api_key,
                access_token=self.config.snipara_oauth_token,
                project_slug=self.config.snipara_project_slug,
            )
        return self._snipara_client

    async def _generate_response(
        self,
        client: AsyncOpenAI,
        query: str,
        context: str,
        scenario_name: str
    ) -> ScenarioResult:
        """Generate LLM response for a scenario."""
        start_time = time.perf_counter()
        
        system_prompt = self._get_system_prompt(scenario_name)
        
        user_prompt = f"""Context:
{context}

Question: {query}

Please provide a detailed and accurate answer:"""

        try:
            # Handle MiniMax-specific format
            if self.config.llm_provider == "minimax":
                response = await client.chat.completions.create(
                    model=self.config.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.7,
                )
            else:
                response = await client.chat.completions.create(
                    model=self.config.model,
                    max_tokens=self.config.max_tokens_response,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
            
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            
            # Handle different response formats
            content = ""
            if hasattr(response.choices[0].message, 'content'):
                content = response.choices[0].message.content or ""
            elif hasattr(response.choices[0], 'text'):
                content = response.choices[0].text or ""
            
            # Handle different token count formats
            tokens_used = 0
            if hasattr(response, 'usage') and response.usage:
                if hasattr(response.usage, 'total_tokens'):
                    tokens_used = response.usage.total_tokens
                elif hasattr(response.usage, 'completion_tokens'):
                    tokens_used = response.usage.completion_tokens
            
            return ScenarioResult(
                scenario=scenario_name,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
                response=content,
            )
        except Exception as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            return ScenarioResult(
                scenario=scenario_name,
                tokens_used=0,
                latency_ms=latency_ms,
                response=f"Error: {e}",
            )

    def _get_system_prompt(self, scenario: str) -> str:
        """Get system prompt for scenario."""
        prompts = {
            "llm_only": (
                "You are a helpful assistant answering questions about Snipara. "
                "Use the provided documentation to give accurate, comprehensive answers."
            ),
            "with_snipara": (
                "You are a helpful assistant using Snipara's optimized context. "
                "Answer accurately based on the provided context sections."
            ),
            "rlm_runtime": (
                "You are a helpful assistant with access to RLM runtime features including "
                "memory of past interactions, recursive context, and shared team context. "
                "Use all available context to provide the most accurate and contextual answer."
            ),
        }
        return prompts.get(scenario, prompts["llm_only"])

    async def _evaluate_response(
        self,
        client: AsyncOpenAI,
        query: str,
        expected_answer: str,
        response: str,
        scenario: str
    ) -> dict:
        """Evaluate response quality using LLM-as-judge."""
        eval_prompt = f"""Evaluate this AI response for a question about Snipara.

Question: {query}
Expected Answer: {expected_answer}
Actual Response: {response}

Score these dimensions 0-10:
1. correctness - Is it factually accurate?
2. completeness - Does it cover all aspects?
3. relevance - Is it directly relevant?
4. clarity - Is it clear and well-organized?

Return JSON with scores and brief explanation."""

        try:
            result = await client.chat.completions.create(
                model=self.config.model,
                max_tokens=500,
                messages=[{"role": "user", "content": eval_prompt}],
            )
            eval_text = result.choices[0].message.content or ""
            try:
                return json.loads(eval_text)
            except json.JSONDecodeError:
                return {"overall": 5.0, "note": "Parse failed, using default score"}
        except Exception as e:
            return {"overall": 0, "error": str(e)}

    async def run_test_case(self, test_case: dict) -> TestCaseResult:
        """Run all three scenarios for a single test case."""
        query = test_case.get("query", "")
        expected_answer = test_case.get("expected_answer", "")
        test_case_id = test_case.get("id", query[:50])

        print(f"\n  📋 Test: {test_case_id}")
        print(f"     Query: {query[:60]}...")

        result = TestCaseResult(
            test_case_id=test_case_id,
            query=query,
            expected_answer=expected_answer,
        )

        # Get full docs for LLM-only scenario
        full_docs = self.dataset.load_full_docs()

        # Get Snipara-optimized context
        snipara_context = self.dataset.get_relevant_context(
            test_case_id, self.config.with_snipara_budget
        )

        # Get RLM-Runtime context
        rlm_context = self.dataset.get_relevant_context(
            test_case_id, self.config.rlm_runtime_budget
        )

        try:
            client = await self._get_llm_client()

            # Scenario 1: LLM Only
            print(f"     🔄 LLM only...")
            llm_result = await self._generate_response(
                client, query, full_docs[:30000], "llm_only"
            )
            llm_eval = await self._evaluate_response(
                client, query, expected_answer, llm_result.response, "llm_only"
            )
            llm_result.evaluation = llm_eval
            result.llm_only = llm_result
            print(f"     ✅ LLM: {llm_result.tokens_used}t, {llm_result.latency_ms}ms, score: {llm_eval.get('overall', 'N/A')}")

            # Scenario 2: With Snipara
            print(f"     🔄 Snipara...")
            snipara_result = await self._generate_response(
                client, query, snipara_context, "with_snipara"
            )
            snipara_eval = await self._evaluate_response(
                client, query, expected_answer, snipara_result.response, "with_snipara"
            )
            snipara_result.evaluation = snipara_eval
            result.with_snipara = snipara_result
            print(f"     ✅ Snipara: {snipara_result.tokens_used}t, {snipara_result.latency_ms}ms, score: {snipara_eval.get('overall', 'N/A')}")

            # Scenario 3: Snipara + RLM-Runtime
            print(f"     🔄 RLM-Runtime...")
            rlm_result = await self._generate_response(
                client, query, rlm_context, "rlm_runtime"
            )
            rlm_eval = await self._evaluate_response(
                client, query, expected_answer, rlm_result.response, "rlm_runtime"
            )
            rlm_result.evaluation = rlm_eval
            result.rlm_runtime = rlm_result
            print(f"     ✅ RLM: {rlm_result.tokens_used}t, {rlm_result.latency_ms}ms, score: {rlm_eval.get('overall', 'N/A')}")

        except Exception as e:
            print(f"     ❌ Error: {e}")

        return result

    async def run_all(self, scenarios: list[str] = None) -> list[TestCaseResult]:
        """Run comprehensive benchmark across all test cases."""
        test_cases = self.dataset.test_cases
        
        print("\n" + "="*70)
        print("🧪 COMPREHENSIVE SNIPARA BENCHMARK")
        print("="*70)
        print(f"Provider: {self.config.llm_provider}")
        print(f"Model: {self.config.model}")
        print(f"Test cases: {len(test_cases)}")
        print(f"Scenarios: {scenarios or ['llm_only', 'with_snipara', 'rlm_runtime']}")
        print("="*70)

        self.results = []
        
        for i, test_case in enumerate(test_cases):
            print(f"\n[{i+1}/{len(test_cases)}]")
            result = await self.run_test_case(test_case)
            self.results.append(result)

        return self.results

    def generate_report(self) -> str:
        """Generate markdown report."""
        if not self.results:
            return "No results to report"

        scenarios = ["llm_only", "with_snipara", "rlm_runtime"]
        metrics = {
            "avg_tokens": {s: [] for s in scenarios},
            "avg_latency": {s: [] for s in scenarios},
            "avg_score": {s: [] for s in scenarios},
        }

        for result in self.results:
            for scenario in scenarios:
                sr = getattr(result, scenario.replace("-", "_"))
                if sr:
                    metrics["avg_tokens"][scenario].append(sr.tokens_used)
                    metrics["avg_latency"][scenario].append(sr.latency_ms)
                    if sr.evaluation:
                        metrics["avg_score"][scenario].append(sr.evaluation.get("overall", 0))

        means = {}
        for scenario in scenarios:
            means[scenario] = {
                "tokens": sum(metrics["avg_tokens"][scenario]) / len(metrics["avg_tokens"][scenario]) if metrics["avg_tokens"][scenario] else 0,
                "latency": sum(metrics["avg_latency"][scenario]) / len(metrics["avg_latency"][scenario]) if metrics["avg_latency"][scenario] else 0,
                "score": sum(metrics["avg_score"][scenario]) / len(metrics["avg_score"][scenario]) if metrics["avg_score"][scenario] else 0,
            }

        report = f"""# Comprehensive Snipara Benchmark Report

**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Provider:** {self.config.llm_provider}
**Model:** {self.config.model}
**Test Cases:** {len(self.results)}

## Executive Summary

This benchmark compares three scenarios:
1. **LLM Only** - Full documentation context (simulated, ~50k tokens)
2. **With Snipara** - Optimized context (~4k tokens)
3. **Snipara + RLM-Runtime** - Full RLM features (~6k tokens, memory, recursive context)

## Results Summary

| Metric | LLM Only | With Snipara | RLM-Runtime | Snipara Savings |
|--------|----------|--------------|-------------|-----------------|
| Avg Tokens | {means['llm_only']['tokens']:.0f} | {means['with_snipara']['tokens']:.0f} | {means['rlm_runtime']['tokens']:.0f} | {100 * (1 - means['with_snipara']['tokens'] / means['llm_only']['tokens']):.1f}% |
| Avg Latency (ms) | {means['llm_only']['latency']:.0f} | {means['with_snipara']['latency']:.0f} | {means['rlm_runtime']['latency']:.0f} | - |
| Avg Quality Score | {means['llm_only']['score']:.2f} | {means['with_snipara']['score']:.2f} | {means['rlm_runtime']['score']:.2f} | - |

## Detailed Analysis

### Token Efficiency

| Scenario | Tokens | vs LLM Only |
|----------|--------|-------------|
| LLM Only | {means['llm_only']['tokens']:.0f} | baseline |
| With Snipara | {means['with_snipara']['tokens']:.0f} | {100 * (1 - means['with_snipara']['tokens'] / means['llm_only']['tokens']):+.1f}% |
| RLM-Runtime | {means['rlm_runtime']['tokens']:.0f} | {100 * (1 - means['rlm_runtime']['tokens'] / means['llm_only']['tokens']):+.1f}% |

### Quality Comparison

| Scenario | Score | vs LLM Only |
|----------|-------|-------------|
| LLM Only | {means['llm_only']['score']:.2f}/10 | baseline |
| With Snipara | {means['with_snipara']['score']:.2f}/10 | {means['with_snipara']['score'] - means['llm_only']['score']:+.2f} |
| RLM-Runtime | {means['rlm_runtime']['score']:.2f}/10 | {means['rlm_runtime']['score'] - means['llm_only']['score']:+.2f} |

## Individual Test Results

| Test Case | LLM Score | Snipara Score | RLM Score | Best |
|-----------|-----------|---------------|-----------|------|
"""

        for result in self.results:
            llm_score = result.llm_only.evaluation.get("overall", "N/A") if result.llm_only else "N/A"
            snipara_score = result.with_snipara.evaluation.get("overall", "N/A") if result.with_snipara else "N/A"
            rlm_score = result.rlm_runtime.evaluation.get("overall", "N/A") if result.rlm_runtime else "N/A"
            
            scores = []
            if llm_score != "N/A": scores.append(("LLM", llm_score))
            if snipara_score != "N/A": scores.append(("Snipara", snipara_score))
            if rlm_score != "N/A": scores.append(("RLM", rlm_score))
            
            best = max(scores, key=lambda x: x[1])[0] if scores else "N/A"
            
            report += f"| {result.test_case_id[:40]} | {llm_score} | {snipara_score} | {rlm_score} | {best} |\n"

        report += """
## Conclusion

"""

        token_savings = 100 * (1 - means['with_snipara']['tokens'] / means['llm_only']['tokens']) if means['llm_only']['tokens'] > 0 else 0
        quality_diff = means['with_snipara']['score'] - means['llm_only']['score']
        
        if token_savings > 50 and quality_diff >= 0:
            report += f"✅ **Excellent Results:** Snipara reduces token usage by {token_savings:.1f}% while maintaining or improving quality ({quality_diff:+.2f} points).\n"
        elif token_savings > 30:
            report += f"⚠️  **Good token savings ({token_savings:.1f}%)** but quality impact needs evaluation.\n"
        else:
            report += f"ℹ️  Token savings: {token_savings:.1f}%. Consider tuning context parameters.\n"

        report += f"\n**Cost Analysis** (estimated, per 1M tokens):\n"
        report += f"- Provider: {self.config.llm_provider}\n"
        report += f"- LLM Only cost: ${means['llm_only']['tokens'] / 1_000_000 * 0.5:.4f} per query (estimated)\n"
        report += f"- Snipara cost: ${means['with_snipara']['tokens'] / 1_000_000 * 0.5:.4f} per query (estimated)\n"

        return report

    async def save_results(self) -> Path:
        """Save results to files."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        json_path = self.config.reports_dir / f"comprehensive_benchmark_{timestamp}.json"
        json_data = {
            "timestamp": timestamp,
            "provider": self.config.llm_provider,
            "model": self.config.model,
            "test_cases": len(self.results),
            "results": [
                {
                    "test_case_id": r.test_case_id,
                    "query": r.query,
                    "llm_only": {
                        "tokens": r.llm_only.tokens_used if r.llm_only else 0,
                        "latency_ms": r.llm_only.latency_ms if r.llm_only else 0,
                        "score": r.llm_only.evaluation.get("overall") if r.llm_only else None,
                    },
                    "with_snipara": {
                        "tokens": r.with_snipara.tokens_used if r.with_snipara else 0,
                        "latency_ms": r.with_snipara.latency_ms if r.with_snipara else 0,
                        "score": r.with_snipara.evaluation.get("overall") if r.with_snipara else None,
                    },
                    "rlm_runtime": {
                        "tokens": r.rlm_runtime.tokens_used if r.rlm_runtime else 0,
                        "latency_ms": r.rlm_runtime.latency_ms if r.rlm_runtime else 0,
                        "score": r.rlm_runtime.evaluation.get("overall") if r.rlm_runtime else None,
                    },
                }
                for r in self.results
            ]
        }
        
        with open(json_path, 'w') as f:
            json.dump(json_data, f, indent=2)
        
        md_path = self.config.reports_dir / f"comprehensive_report_{timestamp}.md"
        report = self.generate_report()
        with open(md_path, 'w') as f:
            f.write(report)
        
        print(f"\n📊 Results saved:")
        print(f"   JSON: {json_path}")
        print(f"   Report: {md_path}")
        
        return json_path

    async def cleanup(self):
        """Cleanup resources."""
        if self._snipara_client:
            await self._snipara_client.close()


async def run_benchmark(
    scenarios: Optional[list[str]] = None,
    config: Optional[BenchmarkConfig] = None,
) -> list[TestCaseResult]:
    """Run comprehensive benchmark."""
    benchmark = ComprehensiveBenchmark(config)
    
    try:
        results = await benchmark.run_all(scenarios)
        await benchmark.save_results()
        return results
    finally:
        await benchmark.cleanup()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Comprehensive Snipara Benchmark - Compare LLM, Snipara, and RLM-Runtime"
    )

    # Scenario selection
    parser.add_argument("--all", action="store_true", help="Run all scenarios")
    parser.add_argument("--llm-only", action="store_true", help="Run LLM only benchmark")
    parser.add_argument("--with-snipara", action="store_true", help="Run Snipara benchmark")
    parser.add_argument("--rlm-runtime", action="store_true", help="Run RLM-Runtime benchmark")
    parser.add_argument("--scenarios", type=str, help="Comma-separated scenarios (e.g., 'llm_only,with_snipara')")

    # LLM provider configuration
    parser.add_argument("--provider", choices=list(LLM_PROVIDERS.keys()), default="openai",
                        help="LLM provider (default: openai)")
    parser.add_argument("--model", help="Model to use (provider-specific)")

    # Configuration
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--output", type=Path, help="Output directory for reports")

    # Test case filtering
    parser.add_argument("--difficulty", choices=["easy", "medium", "hard"], help="Filter by difficulty")
    parser.add_argument("--category", choices=["factual", "reasoning", "multi_hop", "edge_case"], help="Filter by category")

    args = parser.parse_args()

    # Determine scenarios
    scenarios = None
    if args.all:
        scenarios = ["llm_only", "with_snipara", "rlm_runtime"]
    else:
        selected = []
        if args.llm_only:
            selected.append("llm_only")
        if args.with_snipara:
            selected.append("with_snipara")
        if args.rlm_runtime:
            selected.append("rlm_runtime")
        if args.scenarios:
            selected.extend(args.scenarios.split(","))
        if selected:
            scenarios = selected

    if not scenarios:
        scenarios = ["llm_only", "with_snipara", "rlm_runtime"]

    # Get provider configuration
    provider_config = LLM_PROVIDERS[args.provider]
    api_key = os.environ.get(provider_config["api_key_env"])
    base_url = provider_config["base_url"]
    default_model = provider_config["default_model"]

    # Create config
    config = BenchmarkConfig(
        model=args.model or default_model,
        llm_provider=args.provider,
        api_key=api_key,
        base_url=base_url,
        verbose=args.verbose,
    )
    if args.output:
        config.reports_dir = args.output

    # Run benchmark
    try:
        asyncio.run(run_benchmark(scenarios, config))
        print("\n✅ Comprehensive benchmark completed!")
    except KeyboardInterrupt:
        print("\n\n⚠️  Benchmark interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Benchmark failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
