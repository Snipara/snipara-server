"""Benchmark runner CLI.

Usage:
    python -m benchmarks.runner --all
    python -m benchmarks.runner --token-efficiency
    python -m benchmarks.runner --hallucination
    python -m benchmarks.runner --context-quality
    python -m benchmarks.runner --answer-quality
    python -m benchmarks.runner --all --verbose --output report.json

    # Use real Snipara API
    python -m benchmarks.runner --all --use-api

    # Filter by difficulty or category
    python -m benchmarks.runner --all --difficulty hard
    python -m benchmarks.runner --all --category multi_hop

    # Use MiniMax provider
    python -m benchmarks.runner --all --provider minimax --model abab6.5s-chat
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import BenchmarkConfig, BenchmarkType
from .datasets.snipara_docs import SniparaDocsDataset
from .datasets.moltbot_issues import MoltbotIssuesDataset
from .snipara_client import SniparaClient, create_client
from .metrics import (
    TokenEfficiencyBenchmark,
    ContextQualityBenchmark,
    HallucinationBenchmark,
    AnswerQualityBenchmark,
    AggregatedResults,
)


# Supported LLM providers (mirrored from comprehensive_benchmark.py)
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


class CombinedDataset:
    """Combines multiple datasets for comprehensive benchmarking."""

    def __init__(self, datasets: list):
        self.datasets = datasets
        self._full_docs: Optional[str] = None

    @property
    def test_cases(self) -> list[dict]:
        """Get all test cases from all datasets."""
        cases = []
        for ds in self.datasets:
            cases.extend(ds.test_cases)
        return cases

    def get_summary(self) -> dict:
        """Get combined summary statistics."""
        difficulties = {}
        categories = {}
        for ds in self.datasets:
            summary = ds.get_summary()
            for diff, count in summary.get("by_difficulty", {}).items():
                difficulties[diff] = difficulties.get(diff, 0) + count
            for cat, count in summary.get("by_category", {}).items():
                categories[cat] = categories.get(cat, 0) + count
        return {
            "total_cases": len(self.test_cases),
            "by_difficulty": difficulties,
            "by_category": categories,
            "datasets": [type(ds).__name__ for ds in self.datasets],
        }

    def load_full_docs(self) -> str:
        """Load full docs from all datasets."""
        if self._full_docs is not None:
            return self._full_docs
        parts = []
        for ds in self.datasets:
            parts.append(ds.load_full_docs())
        self._full_docs = "\n\n=== DATASET BOUNDARY ===\n\n".join(parts)
        return self._full_docs

    def prepare_contexts(self, max_tokens_with: int = 4000) -> dict:
        """Prepare contexts from all datasets."""
        contexts = {}
        for ds in self.datasets:
            contexts.update(ds.prepare_contexts(max_tokens_with))
        return contexts


class BenchmarkRunner:
    """Orchestrates benchmark execution and reporting."""

    def __init__(
        self,
        config: Optional[BenchmarkConfig] = None,
        use_api: bool = False,
        difficulty: Optional[str] = None,
        category: Optional[str] = None,
        dataset_name: str = "snipara",
    ):
        self.config = config or BenchmarkConfig()
        self.dataset_name = dataset_name
        self.dataset = self._create_dataset(dataset_name)
        self.results: dict[str, AggregatedResults] = {}
        self.use_api = use_api
        self.difficulty = difficulty
        self.category = category
        self._api_client: Optional[SniparaClient] = None

    def _create_dataset(self, name: str):
        """Create dataset instance based on name."""
        if name == "snipara":
            return SniparaDocsDataset()
        elif name == "moltbot":
            return MoltbotIssuesDataset()
        elif name == "all":
            return CombinedDataset([SniparaDocsDataset(), MoltbotIssuesDataset()])
        else:
            raise ValueError(f"Unknown dataset: {name}")

    def _get_test_cases(self) -> list[dict]:
        """Get filtered test cases based on difficulty and category."""
        cases = self.dataset.test_cases

        if self.difficulty:
            cases = [c for c in cases if c.get("difficulty") == self.difficulty]

        if self.category:
            cases = [c for c in cases if c.get("category") == self.category]

        return cases

    async def _get_api_client(self) -> SniparaClient:
        """Get or create Snipara API client.

        Uses OAuth token by default (auto-loaded from ~/.snipara/tokens.json).
        API keys are deprecated.
        """
        if self._api_client is None:
            self._api_client = await create_client(
                use_real_api=True,
                api_key=self.config.snipara_api_key,
                access_token=self.config.snipara_oauth_token,
                project_slug=self.config.snipara_project_slug,
            )
        return self._api_client

    async def _prepare_contexts_with_api(self, test_cases: list[dict]) -> dict:
        """Prepare contexts using real Snipara API."""
        client = await self._get_api_client()
        full_docs = self.dataset.load_full_docs()
        contexts = {}

        for case in test_cases:
            case_id = case["id"]
            query = case["query"]

            try:
                # Call real Snipara API with hybrid search for better NL query handling
                result = await client.context_query(
                    query=query,
                    max_tokens=self.config.with_snipara_budget,
                    search_mode="hybrid",
                )
                if not result.sections:
                    print(
                        f"  ⚠️  API returned 0 sections for {case_id} "
                        f"(project={self.config.snipara_project_slug})"
                    )
                with_snipara = result.to_context_string()
            except Exception as e:
                print(f"  ⚠️  API call failed for {case_id}: {e}")
                # Fallback to local extraction
                with_snipara = self.dataset.get_relevant_context(
                    case_id, self.config.with_snipara_budget
                )

            contexts[case_id] = {
                "with_snipara": with_snipara,
                "without_snipara": full_docs,
            }

        return contexts

    async def run_benchmark(self, benchmark_type: BenchmarkType) -> AggregatedResults:
        """Run a single benchmark type."""
        test_cases = self._get_test_cases()

        print(f"\n{'='*60}")
        print(f"Running: {benchmark_type.value}")
        if self.difficulty:
            print(f"Difficulty filter: {self.difficulty}")
        if self.category:
            print(f"Category filter: {self.category}")
        print(f"{'='*60}\n")

        # Get benchmark instance
        benchmark = self._get_benchmark(benchmark_type)

        # For hallucination benchmark, set full docs for two-stage verification
        if benchmark_type == BenchmarkType.HALLUCINATION:
            full_docs = self.dataset.load_full_docs()
            benchmark.set_full_docs(full_docs)
            print(f"Full docs loaded for factual verification ({len(full_docs):,} chars)")

            # If using API and docs are large, provide Snipara client for execute_python
            if self.use_api and len(full_docs) > benchmark.LARGE_DOCS_THRESHOLD:
                api_client = await self._get_api_client()
                benchmark.set_snipara_client(api_client)
                print(f"  ℹ️  Using execute_python for programmatic verification (docs > {benchmark.LARGE_DOCS_THRESHOLD:,} chars)")

        # Prepare contexts
        if self.use_api:
            print("Preparing contexts via Snipara API...")
            contexts = await self._prepare_contexts_with_api(test_cases)
        else:
            print("Preparing contexts (local extraction)...")
            contexts = self.dataset.prepare_contexts(
                max_tokens_with=self.config.with_snipara_budget
            )
            # Filter contexts to match test cases
            contexts = {k: v for k, v in contexts.items() if k in [c["id"] for c in test_cases]}

        # Run benchmark
        print(f"Running {len(test_cases)} test cases...")
        results = await benchmark.run_all(
            test_cases=test_cases,
            contexts=contexts,
        )

        # Store and display results
        self.results[benchmark_type.value] = results
        self._print_results(results)

        # Save individual results
        output_path = benchmark.save_results(results, self.config.reports_dir)
        print(f"\nResults saved to: {output_path}")

        return results

    def _get_benchmark(self, benchmark_type: BenchmarkType):
        """Get benchmark instance for type."""
        benchmarks = {
            BenchmarkType.TOKEN_EFFICIENCY: TokenEfficiencyBenchmark,
            BenchmarkType.CONTEXT_QUALITY: ContextQualityBenchmark,
            BenchmarkType.HALLUCINATION: HallucinationBenchmark,
            BenchmarkType.ANSWER_QUALITY: AnswerQualityBenchmark,
        }
        return benchmarks[benchmark_type](self.config)

    def _print_results(self, results: AggregatedResults):
        """Print results to console."""
        print(f"\n{results.summary}\n")

        if self.config.verbose:
            print("Individual results:")
            for r in results.results:
                status = "✓" if r.error is None else "✗"
                print(f"  {status} {r.test_case}: {r.latency_ms:.0f}ms")
                if r.error:
                    print(f"      Error: {r.error}")

    async def run_all(self) -> dict[str, AggregatedResults]:
        """Run all benchmarks."""
        test_cases = self._get_test_cases()
        summary = self.dataset.get_summary()

        # Check if LLM-based benchmarks can run
        llm_benchmarks = {BenchmarkType.HALLUCINATION, BenchmarkType.ANSWER_QUALITY}
        
        # Get API key based on provider
        provider_config = LLM_PROVIDERS.get(self.config.llm_provider, LLM_PROVIDERS["openai"])
        api_key_env = provider_config["api_key_env"]
        has_api_key = bool(self.config.api_key or os.environ.get(api_key_env))

        print("\n" + "="*60)
        print("SNIPARA BENCHMARK SUITE")
        print(f"Dataset: {self.dataset_name} ({len(test_cases)} test cases)")
        print(f"Provider: {self.config.llm_provider}")
        print(f"Model: {self.config.model}")
        print(f"Context source: {'Snipara API' if self.use_api else 'Local extraction'}")
        if self.difficulty or self.category:
            print(f"Filters: difficulty={self.difficulty or 'all'}, category={self.category or 'all'}")
        print(f"Full dataset: {summary}")
        if not has_api_key:
            print(f"⚠️  {api_key_env} not set - skipping LLM-based benchmarks")
        print("="*60)

        for benchmark_type in BenchmarkType:
            # Skip LLM-based benchmarks if no API key
            if benchmark_type in llm_benchmarks and not has_api_key:
                print(f"\n⏭️  Skipping {benchmark_type.value} (requires {api_key_env})")
                continue

            try:
                await self.run_benchmark(benchmark_type)
            except Exception as e:
                print(f"\n❌ {benchmark_type.value} failed: {e}")

        # Generate combined report
        self._generate_combined_report()

        return self.results

    def _generate_combined_report(self):
        """Generate combined markdown report."""
        report_path = self.config.reports_dir / f"benchmark_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

        with open(report_path, "w") as f:
            f.write("# Snipara Benchmark Report\n\n")
            f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Model:** {self.config.model}\n")
            f.write(f"**Test Cases:** {len(self.dataset.test_cases)}\n\n")

            f.write("## Executive Summary\n\n")
            for name, results in self.results.items():
                f.write(f"### {name.replace('_', ' ').title()}\n\n")
                f.write("```\n")
                f.write(results.summary)
                f.write("\n```\n\n")

            f.write("## Detailed Results\n\n")
            for name, results in self.results.items():
                f.write(f"### {name.replace('_', ' ').title()}\n\n")
                f.write("| Metric | With Snipara | Without Snipara | Improvement |\n")
                f.write("|--------|--------------|-----------------|-------------|\n")

                for key in results.mean_with_snipara:
                    with_val = results.mean_with_snipara.get(key, "N/A")
                    without_val = results.mean_without_snipara.get(key, "N/A")
                    improvement = results.mean_improvement.get(f"{key}_improvement", "N/A")

                    # Format values
                    if isinstance(with_val, float):
                        with_val = f"{with_val:.3f}"
                    if isinstance(without_val, float):
                        without_val = f"{without_val:.3f}"
                    if isinstance(improvement, float):
                        improvement = f"{improvement:+.3f}"

                    f.write(f"| {key} | {with_val} | {without_val} | {improvement} |\n")

                f.write("\n")

            f.write("## Conclusion\n\n")
            f.write("This benchmark demonstrates the value of Snipara's context optimization:\n\n")

            # Token efficiency summary
            if "token_efficiency" in self.results:
                te = self.results["token_efficiency"]
                compression = te.mean_improvement.get("compression_ratio", 0)
                f.write(f"- **Token Efficiency:** {compression:.1f}x compression ratio\n")

            # Hallucination summary
            if "hallucination" in self.results:
                h = self.results["hallucination"]
                reduction = h.mean_improvement.get("hallucination_reduction_pct", 0)
                f.write(f"- **Hallucination Reduction:** {reduction:.1f}%\n")

            # Answer quality summary
            if "answer_quality" in self.results:
                aq = self.results["answer_quality"]
                improvement = aq.mean_improvement.get("overall_improvement", 0)
                f.write(f"- **Answer Quality Improvement:** {improvement:+.1f} points\n")

        print(f"\n📊 Combined report saved to: {report_path}")


async def run_benchmarks(
    benchmark_types: Optional[list[BenchmarkType]] = None,
    config: Optional[BenchmarkConfig] = None,
    use_api: bool = False,
    difficulty: Optional[str] = None,
    category: Optional[str] = None,
    dataset_name: str = "snipara",
) -> dict[str, AggregatedResults]:
    """Main entry point for running benchmarks.

    Args:
        benchmark_types: List of benchmark types to run. If None, runs all.
        config: Benchmark configuration. If None, uses defaults.
        use_api: Whether to use real Snipara API for context retrieval.
        difficulty: Filter test cases by difficulty (easy, medium, hard).
        category: Filter test cases by category (factual, reasoning, multi_hop, edge_case).
        dataset_name: Dataset to use: 'snipara', 'moltbot', or 'all'.

    Returns:
        Dict mapping benchmark name to aggregated results.
    """
    runner = BenchmarkRunner(
        config=config,
        use_api=use_api,
        difficulty=difficulty,
        category=category,
        dataset_name=dataset_name,
    )

    if benchmark_types is None:
        return await runner.run_all()

    for bt in benchmark_types:
        await runner.run_benchmark(bt)

    # Cleanup API client if used
    if runner._api_client:
        await runner._api_client.close()

    return runner.results


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Snipara Benchmark Suite - Compare LLM performance with/without context optimization"
    )

    # Benchmark selection
    parser.add_argument("--all", action="store_true", help="Run all benchmarks")
    parser.add_argument("--token-efficiency", action="store_true", help="Run token efficiency benchmark")
    parser.add_argument("--context-quality", action="store_true", help="Run context quality benchmark")
    parser.add_argument("--hallucination", action="store_true", help="Run hallucination detection benchmark")
    parser.add_argument("--answer-quality", action="store_true", help="Run answer quality benchmark")

    # Configuration
    parser.add_argument("--provider", choices=list(LLM_PROVIDERS.keys()), default="openai",
                        help="LLM provider (default: openai)")
    parser.add_argument("--model", default="gpt-4o-mini", help="Model to use (default: gpt-4o-mini)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--output", "-o", type=Path, help="Output directory for reports")

    # API and filtering options
    parser.add_argument("--use-api", action="store_true", help="Use real Snipara API for context retrieval")
    parser.add_argument("--difficulty", choices=["easy", "medium", "hard"], help="Filter by difficulty")
    parser.add_argument("--category", choices=["factual", "reasoning", "multi_hop", "edge_case", "bug_fix", "validation", "streaming", "media"], help="Filter by category")

    # Dataset selection
    parser.add_argument("--dataset", choices=["snipara", "moltbot", "all"], default="snipara",
                        help="Dataset to use: snipara (default), moltbot, or all (combined)")

    # Dataset info
    parser.add_argument("--list-cases", action="store_true", help="List all test cases and exit")

    args = parser.parse_args()

    # List test cases if requested
    if args.list_cases:
        if args.dataset == "snipara":
            dataset = SniparaDocsDataset()
        elif args.dataset == "moltbot":
            dataset = MoltbotIssuesDataset()
        else:
            dataset = CombinedDataset([SniparaDocsDataset(), MoltbotIssuesDataset()])
        summary = dataset.get_summary()
        print(f"\n📊 Dataset Summary ({args.dataset}):")
        print(f"  Total test cases: {summary['total_cases']}")
        print(f"  By difficulty: {summary['by_difficulty']}")
        print(f"  By category: {summary['by_category']}")
        if 'datasets' in summary:
            print(f"  Combined from: {summary['datasets']}")
        print("\n📋 Test Cases:")
        for case in dataset.test_cases:
            diff = case.get('difficulty', 'unknown')
            cat = case.get('category', 'unknown')
            print(f"  [{diff:6}] [{cat:10}] {case['id']}: {case['query'][:60]}...")
        sys.exit(0)

    # Determine which benchmarks to run
    benchmark_types = []
    if args.all:
        benchmark_types = list(BenchmarkType)
    else:
        if args.token_efficiency:
            benchmark_types.append(BenchmarkType.TOKEN_EFFICIENCY)
        if args.context_quality:
            benchmark_types.append(BenchmarkType.CONTEXT_QUALITY)
        if args.hallucination:
            benchmark_types.append(BenchmarkType.HALLUCINATION)
        if args.answer_quality:
            benchmark_types.append(BenchmarkType.ANSWER_QUALITY)

    if not benchmark_types:
        parser.print_help()
        print("\n⚠️  Please specify at least one benchmark to run (--all or specific flags)")
        sys.exit(1)

    # Create config with provider settings
    provider_config = LLM_PROVIDERS.get(args.provider, LLM_PROVIDERS["openai"])
    api_key_env = provider_config["api_key_env"]
    api_key = os.environ.get(api_key_env)
    
    config = BenchmarkConfig(
        model=args.model,
        llm_provider=args.provider,
        api_key=api_key,
        base_url=provider_config.get("base_url"),
        verbose=args.verbose,
    )
    if args.output:
        config.reports_dir = args.output

    # Run benchmarks
    try:
        asyncio.run(run_benchmarks(
            benchmark_types=benchmark_types,
            config=config,
            use_api=args.use_api,
            difficulty=args.difficulty,
            category=args.category,
            dataset_name=args.dataset,
        ))
        print("\n✅ Benchmark suite completed successfully!")
    except KeyboardInterrupt:
        print("\n\n⚠️  Benchmark interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Benchmark failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
