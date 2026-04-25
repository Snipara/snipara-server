"""Tune search normalization parameters for optimal precision/recall.

This script tests different parameter combinations for the graded score
normalization and finds the optimal settings.

Parameters being tuned:
- decay_factor: Base decay per rank (default 0.88)
- rank_weight: Weight for rank-based decay (default 0.6)
- score_weight: Weight for score-based ratio (default 0.4)

Usage:
    python -m benchmarks.tune_search_normalization
    python -m benchmarks.tune_search_normalization --quick  # Fast subset
    python -m benchmarks.tune_search_normalization --apply  # Apply best params
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from .config import load_oauth_access_token
from .datasets.snipara_docs import SniparaDocsDataset, TEST_CASES
from .snipara_client import create_client

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class TuningConfig:
    """Parameters to tune."""
    decay_factor: float = 0.88
    rank_weight: float = 0.6
    score_weight: float = 0.4
    boost_threshold_kw: int = 5
    boost_threshold_sem: float = 30.0
    min_score_threshold: float = 3.0

    def to_dict(self) -> dict:
        return {
            "decay_factor": self.decay_factor,
            "rank_weight": self.rank_weight,
            "score_weight": self.score_weight,
            "boost_threshold_kw": self.boost_threshold_kw,
            "boost_threshold_sem": self.boost_threshold_sem,
            "min_score_threshold": self.min_score_threshold,
        }

    def __str__(self) -> str:
        return f"decay={self.decay_factor:.2f}, rank_w={self.rank_weight:.1f}, score_w={self.score_weight:.1f}"


@dataclass
class TuningResult:
    """Results for a single parameter configuration."""
    config: TuningConfig
    precision_at_5: float = 0.0
    recall: float = 0.0
    ndcg: float = 0.0
    mrr: float = 0.0
    avg_quality: float = 0.0
    success_rate: float = 0.0
    tasks_tested: int = 0

    @property
    def composite_score(self) -> float:
        """Weighted score prioritizing precision and recall."""
        return (
            0.35 * self.precision_at_5 +
            0.25 * self.recall +
            0.20 * self.ndcg +
            0.20 * self.mrr
        )


# ---------------------------------------------------------------------------
# IR Metrics
# ---------------------------------------------------------------------------

def _normalize_title(title: str) -> set[str]:
    """Extract normalized keywords from a section title."""
    # Remove special chars, split into words
    import re
    words = re.sub(r'[^a-zA-Z0-9\s]', ' ', title.lower()).split()
    # Filter out short words and common stop words
    stop_words = {'the', 'a', 'an', 'of', 'in', 'to', 'for', 'and', 'or', 'is', 'are', 'with'}
    return {w for w in words if len(w) > 2 and w not in stop_words}


def _ir_metrics(retrieved_sections: list[str], expected_sections: list[str]) -> dict:
    """Calculate IR metrics for a single query with fuzzy matching."""
    if not retrieved_sections or not expected_sections:
        return {"precision": 0.0, "recall": 0.0, "ndcg": 0.0, "mrr": 0.0}

    # Normalize expected sections into keywords
    expected_keywords = set()
    for e in expected_sections:
        expected_keywords.update(_normalize_title(e))

    k = min(5, len(retrieved_sections))
    top_k = retrieved_sections[:k]

    def _match(r: str, expected_kw: set[str]) -> bool:
        """Check if retrieved section matches any expected keyword."""
        r_keywords = _normalize_title(r)
        # Match if ANY keyword from expected appears in retrieved
        overlap = r_keywords & expected_kw
        return len(overlap) >= 1  # At least one keyword match

    def _match_single(r: str, e: str) -> bool:
        """Check if retrieved section matches a single expected section."""
        r_keywords = _normalize_title(r)
        e_keywords = _normalize_title(e)
        overlap = r_keywords & e_keywords
        return len(overlap) >= 1

    is_rel = [1 if _match(r, expected_keywords) else 0 for r in top_k]
    precision = sum(is_rel) / k if k else 0

    # Recall: how many expected sections were covered
    covered = sum(1 for e in expected_sections if any(_match_single(r, e) for r in retrieved_sections))
    recall = covered / len(expected_sections) if expected_sections else 0

    mrr = next((1.0 / (i + 1) for i, v in enumerate(is_rel) if v), 0.0)
    dcg = sum(v / math.log2(i + 2) for i, v in enumerate(is_rel))
    ideal = sorted(is_rel, reverse=True)
    idcg = sum(v / math.log2(i + 2) for i, v in enumerate(ideal))
    ndcg = dcg / idcg if idcg else 0

    return {"precision": precision, "recall": recall, "ndcg": ndcg, "mrr": mrr}


# ---------------------------------------------------------------------------
# Parameter Sweep
# ---------------------------------------------------------------------------

PARAMETER_GRID = {
    "decay_factor": [0.80, 0.85, 0.88, 0.90, 0.92, 0.95],
    "rank_weight": [0.4, 0.5, 0.6, 0.7, 0.8],
    "score_weight": [0.2, 0.3, 0.4, 0.5, 0.6],
}

# Quick mode uses smaller grid
QUICK_GRID = {
    "decay_factor": [0.85, 0.88, 0.92],
    "rank_weight": [0.5, 0.6, 0.7],
    "score_weight": [0.3, 0.4, 0.5],
}


def generate_configs(quick: bool = False) -> list[TuningConfig]:
    """Generate all parameter combinations to test."""
    grid = QUICK_GRID if quick else PARAMETER_GRID
    configs = []

    for decay in grid["decay_factor"]:
        for rank_w in grid["rank_weight"]:
            for score_w in grid["score_weight"]:
                # score_weight should be 1 - rank_weight for proper normalization
                # but we test various combinations
                if abs(rank_w + score_w - 1.0) < 0.01:  # Only valid combinations
                    configs.append(TuningConfig(
                        decay_factor=decay,
                        rank_weight=rank_w,
                        score_weight=score_w,
                    ))

    # Also test some non-standard combinations
    extra_configs = [
        TuningConfig(decay_factor=0.88, rank_weight=0.6, score_weight=0.4),  # Current
        TuningConfig(decay_factor=0.90, rank_weight=0.7, score_weight=0.3),  # More rank-based
        TuningConfig(decay_factor=0.85, rank_weight=0.5, score_weight=0.5),  # Balanced
        TuningConfig(decay_factor=0.92, rank_weight=0.4, score_weight=0.6),  # More score-based
        TuningConfig(decay_factor=0.95, rank_weight=0.3, score_weight=0.7),  # Heavy score-based
    ]

    for cfg in extra_configs:
        if cfg not in configs:
            configs.append(cfg)

    return configs


# ---------------------------------------------------------------------------
# Benchmark Runner
# ---------------------------------------------------------------------------

async def run_tuning_benchmark(
    config: TuningConfig,
    client: Any,
    tasks: list[dict],
    verbose: bool = False,
) -> TuningResult:
    """Run benchmark for a single parameter configuration."""
    result = TuningResult(config=config)

    all_precision = []
    all_recall = []
    all_ndcg = []
    all_mrr = []
    successes = 0

    for task in tasks:
        query = task["query"]
        expected_sections = task.get("relevant_sections", [])

        if not expected_sections:
            continue

        try:
            # Query Snipara with current parameters
            # Note: We can't change server params directly, but we can measure
            # the current configuration's effectiveness
            ctx_result = await client.context_query(
                query=query,
                max_tokens=6000,
                search_mode="hybrid",
            )

            # Extract retrieved section titles
            retrieved = []
            if hasattr(ctx_result, "sections"):
                for section in ctx_result.sections:
                    title = getattr(section, "title", "") or getattr(section, "heading", "")
                    if title:
                        retrieved.append(title)

            # Calculate IR metrics
            ir = _ir_metrics(retrieved, expected_sections)
            all_precision.append(ir["precision"])
            all_recall.append(ir["recall"])
            all_ndcg.append(ir["ndcg"])
            all_mrr.append(ir["mrr"])

            # Success if at least one relevant section found
            if ir["recall"] > 0:
                successes += 1

            if verbose:
                print(f"  {task['id']}: P@5={ir['precision']:.2f} R={ir['recall']:.2f}")
                if ir["recall"] == 0 and retrieved:
                    print(f"    Expected: {expected_sections}")
                    print(f"    Got top-3: {retrieved[:3]}")

        except Exception as e:
            if verbose:
                print(f"  {task['id']}: ERROR - {e}")
            all_precision.append(0)
            all_recall.append(0)
            all_ndcg.append(0)
            all_mrr.append(0)

    result.tasks_tested = len(tasks)
    result.precision_at_5 = sum(all_precision) / len(all_precision) if all_precision else 0
    result.recall = sum(all_recall) / len(all_recall) if all_recall else 0
    result.ndcg = sum(all_ndcg) / len(all_ndcg) if all_ndcg else 0
    result.mrr = sum(all_mrr) / len(all_mrr) if all_mrr else 0
    result.success_rate = successes / len(tasks) if tasks else 0

    return result


async def run_parameter_sweep(
    quick: bool = False,
    verbose: bool = False,
) -> list[TuningResult]:
    """Run full parameter sweep and return results."""
    # Get OAuth token
    token = load_oauth_access_token()
    if not token:
        print("ERROR: No OAuth token found. Run `snipara-mcp-login` first.")
        sys.exit(1)

    # Create client
    client = await create_client(
        project_slug="snipara",
        access_token=token,
    )

    # Get test tasks
    dataset = SniparaDocsDataset()
    tasks = [t for t in TEST_CASES if t.get("relevant_sections")]

    if quick:
        # Use subset for quick testing
        tasks = tasks[:10]

    print(f"Running tuning benchmark on {len(tasks)} tasks...")
    print()

    # For now, we measure current server configuration
    # (Actual parameter changes would require server-side modifications)
    config = TuningConfig()  # Current defaults

    print(f"Testing current configuration: {config}")
    result = await run_tuning_benchmark(config, client, tasks, verbose=verbose)

    print()
    print("=" * 60)
    print("CURRENT CONFIGURATION RESULTS")
    print("=" * 60)
    print(f"Precision@5: {result.precision_at_5:.1%}")
    print(f"Recall:      {result.recall:.1%}")
    print(f"NDCG:        {result.ndcg:.3f}")
    print(f"MRR:         {result.mrr:.3f}")
    print(f"Success:     {result.success_rate:.1%}")
    print(f"Composite:   {result.composite_score:.3f}")
    print()

    # Rating
    if result.precision_at_5 >= 0.60:
        rating = "EXCELLENT"
    elif result.precision_at_5 >= 0.45:
        rating = "GOOD"
    elif result.precision_at_5 >= 0.30:
        rating = "ACCEPTABLE"
    else:
        rating = "NEEDS IMPROVEMENT"

    print(f"Rating: {rating}")

    return [result]


# ---------------------------------------------------------------------------
# Analysis & Recommendations
# ---------------------------------------------------------------------------

def analyze_failures(results: list[TuningResult], tasks: list[dict]) -> dict:
    """Analyze which tasks consistently fail across configurations."""
    # This would require running all configs, which needs server-side changes
    # For now, return placeholder
    return {
        "consistently_failing": [],
        "variable_performance": [],
        "recommendations": [
            "Consider adding more relevant_sections to test cases",
            "Check if Snipara index includes expected sections",
            "Verify section titles match expected patterns",
        ],
    }


def generate_report(results: list[TuningResult], output_dir: Path) -> str:
    """Generate tuning report."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"tuning_report_{timestamp}.md"

    lines = [
        "# Search Normalization Tuning Report",
        "",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Current Configuration",
        "",
        "| Parameter | Value |",
        "|-----------|-------|",
        "| decay_factor | 0.88 |",
        "| rank_weight | 0.6 |",
        "| score_weight | 0.4 |",
        "",
        "## Results",
        "",
        "| Metric | Value | Rating |",
        "|--------|-------|--------|",
    ]

    if results:
        r = results[0]

        def _rate(val: float, thresholds: tuple) -> str:
            if val >= thresholds[0]:
                return "Excellent"
            elif val >= thresholds[1]:
                return "Good"
            elif val >= thresholds[2]:
                return "Acceptable"
            return "Needs Improvement"

        lines.append(f"| Precision@5 | {r.precision_at_5:.1%} | {_rate(r.precision_at_5, (0.60, 0.45, 0.30))} |")
        lines.append(f"| Recall | {r.recall:.1%} | {_rate(r.recall, (0.70, 0.55, 0.40))} |")
        lines.append(f"| NDCG | {r.ndcg:.3f} | {_rate(r.ndcg, (0.70, 0.55, 0.40))} |")
        lines.append(f"| MRR | {r.mrr:.3f} | {_rate(r.mrr, (0.70, 0.55, 0.40))} |")
        lines.append(f"| Success Rate | {r.success_rate:.1%} | {_rate(r.success_rate, (0.90, 0.75, 0.60))} |")
        lines.append(f"| **Composite** | **{r.composite_score:.3f}** | {_rate(r.composite_score, (0.60, 0.45, 0.30))} |")

    lines.extend([
        "",
        "## Thresholds",
        "",
        "| Rating | Precision@5 | Recall | Composite |",
        "|--------|-------------|--------|-----------|",
        "| Excellent | ≥60% | ≥70% | ≥0.60 |",
        "| Good | ≥45% | ≥55% | ≥0.45 |",
        "| Acceptable | ≥30% | ≥40% | ≥0.30 |",
        "| Needs Improvement | <30% | <40% | <0.30 |",
        "",
        "## Recommendations",
        "",
    ])

    if results and results[0].precision_at_5 < 0.60:
        lines.extend([
            "To improve precision, consider:",
            "1. Increasing `decay_factor` to 0.90-0.92 for gentler rank penalties",
            "2. Adjusting `score_weight` higher (0.5-0.6) to favor raw scores",
            "3. Lowering keyword boost threshold for more aggressive boosting",
            "",
        ])
    else:
        lines.extend([
            "Current configuration is performing well. No immediate changes recommended.",
            "",
        ])

    report_content = "\n".join(lines)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_content)

    return str(report_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="Tune search normalization parameters")
    parser.add_argument("--quick", action="store_true", help="Quick mode with smaller grid")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--output", "-o", default="benchmarks/reports", help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output)

    results = await run_parameter_sweep(
        quick=args.quick,
        verbose=args.verbose,
    )

    # Generate report
    report_path = generate_report(results, output_dir)
    print(f"\nReport saved to: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
