"""Context Quality Benchmark.

Measures the quality of retrieved context using Information Retrieval metrics:
- Precision@K: How many retrieved sections are relevant?
- Recall@K: How many relevant sections were retrieved?
- MRR (Mean Reciprocal Rank): Position of first relevant result
- NDCG (Normalized Discounted Cumulative Gain): Ranking quality
"""

import math
import re
from typing import Optional

from ..config import THRESHOLDS
from .base import BenchmarkMetric, BenchmarkResult


class ContextQualityBenchmark(BenchmarkMetric):
    """Benchmark measuring context retrieval quality.

    Compares how well Snipara retrieves relevant sections vs. naive approaches
    (random selection, first-N sections, keyword-only).
    """

    name = "context_quality"
    description = "Measures precision, recall, MRR, and NDCG of retrieved context"

    # Ubiquitous keywords that appear in 40%+ of sections - exclude from matching
    # These inflate false positives when used for word overlap matching
    STOPWORDS = {
        # Project-specific terms (appear everywhere)
        "snipara", "rlm", "mcp", "context", "api", "server",
        # Generic documentation terms
        "docs", "documentation", "reference", "guide", "overview",
        # Common tech terms
        "tools", "tool", "query", "search", "project", "user", "team",
        # Articles and prepositions (already filtered by len > 2, but explicit)
        "the", "and", "for", "with", "from", "that", "this", "your",
    }

    async def run_single(
        self,
        test_case: dict,
        with_snipara_context: str,
        without_snipara_context: str,
    ) -> BenchmarkResult:
        """Run context quality evaluation for a single test case.

        Args:
            test_case: Must contain:
                - query: The search query
                - relevant_sections: List of section titles/identifiers that are relevant
                - k: Number of top results to evaluate (default: 5)
        """
        query = test_case.get("query", "")
        relevant_sections = set(test_case.get("relevant_sections", []))
        k = test_case.get("k", 5)

        # Extract section titles from contexts
        with_sections = self._extract_sections(with_snipara_context)
        without_sections = self._extract_sections(without_snipara_context)

        # Calculate metrics for Snipara
        with_metrics = self._calculate_ir_metrics(
            retrieved=with_sections[:k],
            relevant=relevant_sections,
            all_retrieved=with_sections,
        )

        # Calculate metrics for baseline (without Snipara - naive approach)
        without_metrics = self._calculate_ir_metrics(
            retrieved=without_sections[:k],
            relevant=relevant_sections,
            all_retrieved=without_sections,
        )

        # Calculate improvements
        precision_improvement = with_metrics["precision"] - without_metrics["precision"]
        recall_improvement = with_metrics["recall"] - without_metrics["recall"]
        ndcg_improvement = with_metrics["ndcg"] - without_metrics["ndcg"]
        mrr_improvement = with_metrics["mrr"] - without_metrics["mrr"]

        return BenchmarkResult(
            benchmark_name=self.name,
            test_case=test_case.get("id", query[:50]),
            with_snipara={
                "precision_at_k": round(with_metrics["precision"], 3),
                "recall_at_k": round(with_metrics["recall"], 3),
                "mrr": round(with_metrics["mrr"], 3),
                "ndcg": round(with_metrics["ndcg"], 3),
                "f1": round(with_metrics["f1"], 3),
                "num_retrieved": len(with_sections),
                "num_relevant_found": with_metrics["relevant_found"],
            },
            without_snipara={
                "precision_at_k": round(without_metrics["precision"], 3),
                "recall_at_k": round(without_metrics["recall"], 3),
                "mrr": round(without_metrics["mrr"], 3),
                "ndcg": round(without_metrics["ndcg"], 3),
                "f1": round(without_metrics["f1"], 3),
                "num_retrieved": len(without_sections),
                "num_relevant_found": without_metrics["relevant_found"],
            },
            improvement={
                "precision_improvement": round(precision_improvement, 3),
                "recall_improvement": round(recall_improvement, 3),
                "mrr_improvement": round(mrr_improvement, 3),
                "ndcg_improvement": round(ndcg_improvement, 3),
            },
        )

    def _extract_sections(self, context: str) -> list[str]:
        """Extract section titles/headers from context.

        Looks for markdown headers or section markers in the context.
        """
        if not context:
            return []

        # Match markdown headers (# Header, ## Header, etc.)
        header_pattern = r"^#{1,6}\s+(.+)$"
        headers = re.findall(header_pattern, context, re.MULTILINE)

        # Also match numbered sections (1. Section, 2. Section)
        numbered_pattern = r"^\d+\.\s+\*\*(.+?)\*\*"
        numbered = re.findall(numbered_pattern, context, re.MULTILINE)

        # Combine and deduplicate while preserving order
        sections = []
        seen = set()
        for h in headers + numbered:
            h_clean = h.strip().lower()
            if h_clean not in seen:
                sections.append(h_clean)
                seen.add(h_clean)

        return sections

    def _is_section_match(self, retrieved_title: str, expected_title: str) -> bool:
        """Check if a retrieved section title matches an expected title.

        Uses flexible matching:
        1. Exact match (after normalization)
        2. Substring match (expected is in retrieved or vice versa)
        3. Word overlap >= 75% (excluding stopwords), with min 2 distinctive words

        The stopword exclusion prevents false positives from ubiquitous terms
        like "MCP", "tools", "Snipara" that appear in 40%+ of sections.
        """
        retrieved_norm = retrieved_title.lower().strip()
        expected_norm = expected_title.lower().strip()

        # Exact match
        if retrieved_norm == expected_norm:
            return True

        # Substring match
        if expected_norm in retrieved_norm or retrieved_norm in expected_norm:
            return True

        # Word overlap matching (excluding stopwords)
        retrieved_words = set(
            w for w in retrieved_norm.split()
            if len(w) > 2 and w not in self.STOPWORDS
        )
        expected_words = set(
            w for w in expected_norm.split()
            if len(w) > 2 and w not in self.STOPWORDS
        )

        # Require at least 2 distinctive (non-stopword) words to match
        # This prevents "MCP Tools Reference" matching "39 MCP Tools" via just "mcp"+"tools"
        if expected_words and retrieved_words:
            overlap = retrieved_words & expected_words
            overlap_count = len(overlap)

            # Need at least 2 distinctive words to match, OR all words if fewer
            min_required = min(2, len(expected_words))
            if overlap_count < min_required:
                return False

            # Check if at least 75% of expected distinctive words are in retrieved
            if overlap_count >= len(expected_words) * 0.75:
                return True
            # Also check reverse - if retrieved is more specific
            if overlap_count >= len(retrieved_words) * 0.75:
                return True

        return False

    def _calculate_ir_metrics(
        self,
        retrieved: list[str],
        relevant: set[str],
        all_retrieved: list[str],
    ) -> dict:
        """Calculate Information Retrieval metrics.

        Args:
            retrieved: Top-K retrieved section titles
            relevant: Set of relevant section titles (ground truth)
            all_retrieved: All retrieved sections (for recall calculation)
        """
        if not retrieved or not relevant:
            return {
                "precision": 0.0,
                "recall": 0.0,
                "mrr": 0.0,
                "ndcg": 0.0,
                "f1": 0.0,
                "relevant_found": 0,
            }

        # Check which retrieved sections are relevant (using flexible matching)
        # Track which expected sections have been matched to avoid double-counting
        matched_expected = set()
        is_relevant = []
        for ret in retrieved:
            # Find if this retrieved section matches any unmatched expected section
            matched = False
            for rel in relevant:
                if rel not in matched_expected and self._is_section_match(ret, rel):
                    matched = True
                    matched_expected.add(rel)
                    break
            is_relevant.append(1 if matched else 0)
        relevant_found = sum(is_relevant)

        # Precision@K: relevant in top-K / K
        precision = relevant_found / len(retrieved) if retrieved else 0

        # Recall@K: How many of the expected relevant sections were retrieved?
        # Use all_retrieved for a more fair recall calculation with flexible matching
        relevant_covered = set()
        for rel in relevant:
            for ret in all_retrieved:
                if self._is_section_match(ret, rel):
                    relevant_covered.add(rel)
                    break
        recall = len(relevant_covered) / len(relevant) if relevant else 0

        # MRR: 1 / position of first relevant result
        mrr = 0.0
        for i, rel in enumerate(is_relevant):
            if rel:
                mrr = 1.0 / (i + 1)
                break

        # NDCG: Normalized Discounted Cumulative Gain
        dcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(is_relevant))
        # Ideal DCG (all relevant items at top)
        ideal_relevance = [1] * min(len(relevant), len(retrieved))
        ideal_relevance.extend([0] * (len(retrieved) - len(ideal_relevance)))
        idcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(ideal_relevance))
        ndcg = dcg / idcg if idcg > 0 else 0

        # F1: Harmonic mean of precision and recall
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0
        )

        return {
            "precision": precision,
            "recall": recall,
            "mrr": mrr,
            "ndcg": ndcg,
            "f1": f1,
            "relevant_found": relevant_found,
        }

    def _generate_summary(
        self, mean_with: dict, mean_without: dict, mean_improvement: dict
    ) -> str:
        """Generate human-readable summary."""
        precision = mean_with.get("precision_at_k", 0)
        recall = mean_with.get("recall_at_k", 0)
        ndcg = mean_with.get("ndcg", 0)

        precision_good = precision >= THRESHOLDS["precision_good"]
        recall_good = recall >= THRESHOLDS["recall_good"]

        quality = "excellent" if precision_good and recall_good else (
            "good" if precision_good or recall_good else "needs improvement"
        )

        return (
            f"Context Quality: {quality}\n"
            f"  With Snipara:\n"
            f"    - Precision@K: {precision:.1%}\n"
            f"    - Recall@K: {recall:.1%}\n"
            f"    - NDCG: {ndcg:.3f}\n"
            f"  Improvement over baseline:\n"
            f"    - Precision: +{mean_improvement.get('precision_improvement', 0):.1%}\n"
            f"    - Recall: +{mean_improvement.get('recall_improvement', 0):.1%}"
        )
