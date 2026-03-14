"""Token Efficiency Benchmark.

Measures token usage and cost savings when using Snipara context optimization
vs. sending full documentation to the LLM.
"""

from dataclasses import dataclass
from typing import Any

from ..config import TOKEN_COSTS, THRESHOLDS
from .base import BenchmarkMetric, BenchmarkResult


@dataclass
class TokenMetrics:
    """Token-related metrics for a single query."""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    context_tokens: int
    cost_usd: float

    @classmethod
    def calculate(
        cls, context: str, response: str, model: str, encoder: Any
    ) -> "TokenMetrics":
        context_tokens = len(encoder.encode(context)) if context else 0
        # Estimate prompt overhead (system prompt, query, formatting)
        prompt_overhead = 500
        input_tokens = context_tokens + prompt_overhead
        output_tokens = len(encoder.encode(response)) if response else 0
        total_tokens = input_tokens + output_tokens

        # Calculate cost
        costs = TOKEN_COSTS.get(model, TOKEN_COSTS["claude-sonnet-4-20250514"])
        cost_usd = (
            (input_tokens * costs["input"] / 1_000_000)
            + (output_tokens * costs["output"] / 1_000_000)
        )

        return cls(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            context_tokens=context_tokens,
            cost_usd=cost_usd,
        )


class TokenEfficiencyBenchmark(BenchmarkMetric):
    """Benchmark measuring token efficiency and cost savings.

    Compares:
    - Total tokens used (input + output)
    - Context tokens (the documentation sent to LLM)
    - Compression ratio (full docs / optimized context)
    - Cost per query in USD
    - Cost savings percentage
    """

    name = "token_efficiency"
    description = "Measures token usage and cost savings with Snipara optimization"

    async def run_single(
        self,
        test_case: dict,
        with_snipara_context: str,
        without_snipara_context: str,
    ) -> BenchmarkResult:
        """Run token efficiency comparison for a single test case.

        Note: This benchmark doesn't call the LLM - it only measures token counts.
        We simulate the response tokens based on typical response lengths.
        """
        query = test_case.get("query", "")

        # Simulated response length (typical LLM response is 200-500 tokens)
        simulated_response = "A" * 1500  # ~300-400 tokens

        # Calculate metrics for both conditions
        metrics_with = TokenMetrics.calculate(
            context=with_snipara_context,
            response=simulated_response,
            model=self.config.model,
            encoder=self._encoder,
        )

        metrics_without = TokenMetrics.calculate(
            context=without_snipara_context,
            response=simulated_response,
            model=self.config.model,
            encoder=self._encoder,
        )

        # Calculate improvements
        compression_ratio = (
            metrics_without.context_tokens / metrics_with.context_tokens
            if metrics_with.context_tokens > 0
            else 0
        )
        token_reduction = metrics_without.context_tokens - metrics_with.context_tokens
        token_reduction_pct = (
            (token_reduction / metrics_without.context_tokens * 100)
            if metrics_without.context_tokens > 0
            else 0
        )
        cost_savings = metrics_without.cost_usd - metrics_with.cost_usd
        cost_savings_pct = (
            (cost_savings / metrics_without.cost_usd * 100)
            if metrics_without.cost_usd > 0
            else 0
        )

        return BenchmarkResult(
            benchmark_name=self.name,
            test_case=test_case.get("id", query[:50]),
            with_snipara={
                "context_tokens": metrics_with.context_tokens,
                "input_tokens": metrics_with.input_tokens,
                "output_tokens": metrics_with.output_tokens,
                "total_tokens": metrics_with.total_tokens,
                "cost_usd": round(metrics_with.cost_usd, 6),
            },
            without_snipara={
                "context_tokens": metrics_without.context_tokens,
                "input_tokens": metrics_without.input_tokens,
                "output_tokens": metrics_without.output_tokens,
                "total_tokens": metrics_without.total_tokens,
                "cost_usd": round(metrics_without.cost_usd, 6),
            },
            improvement={
                "compression_ratio": round(compression_ratio, 2),
                "token_reduction": token_reduction,
                "token_reduction_pct": round(token_reduction_pct, 1),
                "cost_savings_usd": round(cost_savings, 6),
                "cost_savings_pct": round(cost_savings_pct, 1),
            },
        )

    def _generate_summary(
        self, mean_with: dict, mean_without: dict, mean_improvement: dict
    ) -> str:
        """Generate human-readable summary."""
        compression = mean_improvement.get("compression_ratio", 0)
        reduction_pct = mean_improvement.get("token_reduction_pct", 0)
        savings_pct = mean_improvement.get("cost_savings_pct", 0)

        quality = "excellent" if compression >= THRESHOLDS["compression_ratio_excellent"] else (
            "good" if compression >= THRESHOLDS["compression_ratio_good"] else "moderate"
        )

        return (
            f"Token Efficiency: {compression:.1f}x compression ({quality})\n"
            f"  - Context reduced by {reduction_pct:.1f}%\n"
            f"  - Cost savings: {savings_pct:.1f}%\n"
            f"  - With Snipara: ~{mean_with.get('context_tokens', 0):.0f} tokens/query\n"
            f"  - Without Snipara: ~{mean_without.get('context_tokens', 0):.0f} tokens/query"
        )
