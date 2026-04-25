"""Base classes for benchmark metrics."""

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import tiktoken


@dataclass
class BenchmarkResult:
    """Result from a single benchmark run."""

    benchmark_name: str
    test_case: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # With Snipara
    with_snipara: dict = field(default_factory=dict)

    # Without Snipara (baseline)
    without_snipara: dict = field(default_factory=dict)

    # Comparison metrics
    improvement: dict = field(default_factory=dict)

    # Metadata
    latency_ms: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class AggregatedResults:
    """Aggregated results across multiple test cases."""

    benchmark_name: str
    num_cases: int
    results: list[BenchmarkResult]

    # Aggregated metrics (mean values)
    mean_with_snipara: dict = field(default_factory=dict)
    mean_without_snipara: dict = field(default_factory=dict)
    mean_improvement: dict = field(default_factory=dict)

    # Summary
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "benchmark_name": self.benchmark_name,
            "num_cases": self.num_cases,
            "mean_with_snipara": self.mean_with_snipara,
            "mean_without_snipara": self.mean_without_snipara,
            "mean_improvement": self.mean_improvement,
            "summary": self.summary,
            "results": [r.to_dict() for r in self.results],
        }


class BenchmarkMetric(ABC):
    """Base class for benchmark metrics."""

    name: str = "base"
    description: str = "Base benchmark metric"

    def __init__(self, config: Any):
        self.config = config
        self._encoder = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken."""
        return len(self._encoder.encode(text))

    @abstractmethod
    async def run_single(
        self,
        test_case: dict,
        with_snipara_context: str,
        without_snipara_context: str,
    ) -> BenchmarkResult:
        """Run benchmark on a single test case.

        Args:
            test_case: Dict with 'query', 'expected_answer', 'relevant_sections', etc.
            with_snipara_context: Optimized context from Snipara
            without_snipara_context: Full/unoptimized context

        Returns:
            BenchmarkResult with metrics for both conditions
        """
        pass

    async def run_all(self, test_cases: list[dict], contexts: dict) -> AggregatedResults:
        """Run benchmark on all test cases and aggregate results.

        Args:
            test_cases: List of test case dicts
            contexts: Dict mapping case_id -> {'with_snipara': str, 'without_snipara': str}

        Returns:
            AggregatedResults with all individual results and aggregated metrics
        """
        results = []
        for case in test_cases:
            case_id = case.get("id", case.get("query", "unknown"))
            ctx = contexts.get(case_id, {})

            start = time.time()
            try:
                result = await self.run_single(
                    test_case=case,
                    with_snipara_context=ctx.get("with_snipara", ""),
                    without_snipara_context=ctx.get("without_snipara", ""),
                )
                result.latency_ms = (time.time() - start) * 1000
            except Exception as e:
                result = BenchmarkResult(
                    benchmark_name=self.name,
                    test_case=case_id,
                    error=str(e),
                    latency_ms=(time.time() - start) * 1000,
                )
            results.append(result)

        return self._aggregate_results(results)

    def _aggregate_results(self, results: list[BenchmarkResult]) -> AggregatedResults:
        """Aggregate individual results into summary statistics."""
        valid_results = [r for r in results if r.error is None]
        if not valid_results:
            return AggregatedResults(
                benchmark_name=self.name,
                num_cases=len(results),
                results=results,
                summary="All test cases failed.",
            )

        # Calculate means for each metric
        mean_with = self._calculate_means([r.with_snipara for r in valid_results])
        mean_without = self._calculate_means([r.without_snipara for r in valid_results])
        mean_improvement = self._calculate_means([r.improvement for r in valid_results])

        return AggregatedResults(
            benchmark_name=self.name,
            num_cases=len(results),
            results=results,
            mean_with_snipara=mean_with,
            mean_without_snipara=mean_without,
            mean_improvement=mean_improvement,
            summary=self._generate_summary(mean_with, mean_without, mean_improvement),
        )

    def _calculate_means(self, dicts: list[dict]) -> dict:
        """Calculate mean values across list of metric dicts."""
        if not dicts:
            return {}

        # Collect all numeric values by key
        all_keys = set()
        for d in dicts:
            all_keys.update(k for k, v in d.items() if isinstance(v, (int, float)))

        means = {}
        for key in all_keys:
            values = [d.get(key) for d in dicts if isinstance(d.get(key), (int, float))]
            if values:
                means[key] = sum(values) / len(values)

        return means

    def _generate_summary(
        self, mean_with: dict, mean_without: dict, mean_improvement: dict
    ) -> str:
        """Generate human-readable summary. Override in subclasses for custom summaries."""
        return f"{self.name}: See detailed metrics for results."

    def save_results(self, results: AggregatedResults, output_dir: Path) -> Path:
        """Save results to JSON file."""
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"{self.name}_{timestamp}.json"

        with open(output_path, "w") as f:
            json.dump(results.to_dict(), f, indent=2)

        return output_path
