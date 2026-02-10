"""Reciprocal Rank Fusion for hybrid search.

This module provides the RRF algorithm for combining keyword and semantic
rankings, along with adaptive weight classification and score normalization.
"""

import re

from .constants import (
    CONCEPTUAL_PREFIXES,
    HYBRID_BALANCED,
    HYBRID_KEYWORD_HEAVY,
    HYBRID_SEMANTIC_HEAVY,
    RRF_K,
    SPECIFIC_QUERY_TERMS,
)
from .stemmer import stem_keyword


def classify_query_weights(
    query: str,
    keyword_scores: dict[str, float],
) -> tuple[float, float]:
    """Return (keyword_weight, semantic_weight) adapted to the query.

    Heuristics (no LLM call, ~0 ms overhead):

    1. **Strong keyword signal** – the top keyword score is well above the
       median, meaning there's likely an exact or near-exact title match.
       Combined with specific technical terms → keyword-heavy (60/40).

    2. **Conceptual query** – starts with "how does", "why", "explain" etc.
       and doesn't contain structured-data terms → semantic-heavy (25/75).

    3. **Default** – balanced (40/60).

    Args:
        query: The search query string.
        keyword_scores: Dictionary of section_id → keyword scores.

    Returns:
        Tuple of (keyword_weight, semantic_weight) summing to 1.0.
    """
    query_lower = query.lower()
    query_words = {w for w in re.findall(r"\w+", query_lower) if len(w) > 2}

    # Signal 1: strong keyword confidence
    kw_values = [v for v in keyword_scores.values() if v > 0]
    strong_keyword = False
    if kw_values:
        top_kw = max(kw_values)
        # Top score is at least 3× the median – very confident match
        median_kw = sorted(kw_values)[len(kw_values) // 2] if kw_values else 0
        strong_keyword = top_kw > 15 and (median_kw == 0 or top_kw / median_kw >= 3)

    # Signal 2: specific / structured-data terms in the query
    # Also check stemmed variants so "prices" matches "price" in the set
    stemmed_words = {stem_keyword(w) for w in query_words}
    has_specific = bool(
        (query_words | stemmed_words) & SPECIFIC_QUERY_TERMS
    )

    # Signal 3: conceptual query pattern
    is_conceptual = any(query_lower.startswith(p) for p in CONCEPTUAL_PREFIXES)

    # Priority: specific keyword matches first, then conceptual patterns
    if strong_keyword and has_specific:
        return HYBRID_KEYWORD_HEAVY
    if strong_keyword:
        return HYBRID_BALANCED  # Don't go full keyword-heavy without specific terms
    if is_conceptual:
        return HYBRID_SEMANTIC_HEAVY
    return HYBRID_BALANCED


def rrf_fusion(
    keyword_scores: dict[str, float],
    semantic_scores: dict[str, float],
    keyword_weight: float = 0.40,
    semantic_weight: float = 0.60,
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion of keyword and semantic rankings.

    RRF score for document *d*::

        rrf(d) = w_kw / (k + rank_kw(d)) + w_sem / (k + rank_sem(d))

    Unlike weighted-score averaging, RRF is **rank-based** so it is
    robust to score-magnitude mismatches between keyword and semantic
    signals (the root cause of the hybrid regression on ``tech_stack``
    and ``core_value_prop``).

    Sections absent from a ranking receive a pessimistic rank equal to
    ``len(ranking) + 1``.

    Args:
        keyword_scores: Dictionary of section_id → keyword relevance scores.
        semantic_scores: Dictionary of section_id → semantic similarity scores.
        keyword_weight: Weight for keyword ranking (default 0.40).
        semantic_weight: Weight for semantic ranking (default 0.60).
        k: RRF constant (default 45). Lower = more weight to top results.

    Returns:
        List of (section_id, rrf_score) tuples, sorted descending by score.
    """
    # Build keyword ranking (descending score)
    kw_ranked = sorted(
        ((sid, sc) for sid, sc in keyword_scores.items() if sc > 0),
        key=lambda x: x[1],
        reverse=True,
    )
    kw_rank: dict[str, int] = {sid: rank for rank, (sid, _) in enumerate(kw_ranked, start=1)}
    default_kw_rank = len(kw_ranked) + 1

    # Build semantic ranking (descending similarity)
    sem_ranked = sorted(
        ((sid, sc) for sid, sc in semantic_scores.items() if sc > 0),
        key=lambda x: x[1],
        reverse=True,
    )
    sem_rank: dict[str, int] = {sid: rank for rank, (sid, _) in enumerate(sem_ranked, start=1)}
    default_sem_rank = len(sem_ranked) + 1

    # Union of all section IDs present in either ranking
    all_ids = set(kw_rank) | set(sem_rank)

    rrf_scores: list[tuple[str, float]] = []
    for sid in all_ids:
        rk = kw_rank.get(sid, default_kw_rank)
        rs = sem_rank.get(sid, default_sem_rank)
        score = keyword_weight / (k + rk) + semantic_weight / (k + rs)
        rrf_scores.append((sid, score))

    rrf_scores.sort(key=lambda x: x[1], reverse=True)
    return rrf_scores


def normalize_scores_graded(
    scores: list[tuple[str, float]],
    decay_factor: float = 0.94,
) -> list[tuple[str, float]]:
    """Normalize scores to 0-100 with clear rank separation.

    Creates a graded scoring where:
    - Rank 1 (ground truth) = 100
    - Each subsequent rank decays by decay_factor
    - But also considers actual score gaps

    This produces clearer separation than raw score normalization:
    - Raw: [0.05, 0.048, 0.045, 0.042] → [100, 96, 90, 84] (too similar)
    - Graded: [0.05, 0.048, 0.045, 0.042] → [100, 94, 88, 83] (clear hierarchy)

    Args:
        scores: List of (id, raw_score) tuples, already sorted descending.
        decay_factor: Base decay per rank (default 0.94 = ~6% drop per rank).

    Returns:
        List of (id, graded_score) with clear separation.
    """
    if not scores:
        return []

    # Top score gets 100
    top_score = scores[0][1] if scores[0][1] > 0 else 1.0
    result = [(scores[0][0], 100.0)]

    for i, (sid, raw) in enumerate(scores[1:], start=1):
        # Combine rank-based decay with score-ratio decay
        # rank_factor: exponential decay based on position (0.94^rank)
        # score_factor: how close is this score to the top? (raw/top)
        rank_factor = decay_factor ** i
        score_factor = raw / top_score if top_score > 0 else 0

        # Weighted combination: 40% rank-based, 60% score-based (favor raw scores)
        # Higher score_weight keeps more relevant sections that may have lower ranks
        graded = 100 * (0.4 * rank_factor + 0.6 * score_factor)

        # Floor at 1 (never 0 unless truly irrelevant)
        result.append((sid, max(round(graded, 1), 1.0)))

    return result


def hybrid_search(
    keyword_scores: dict[str, float],
    semantic_scores: dict[str, float],
    query: str,
    normalize: bool = True,
    decay_factor: float = 0.94,
) -> list[tuple[str, float]]:
    """Complete hybrid search pipeline: weight classification → RRF → normalize.

    This is a convenience function that combines all the hybrid search steps.

    Args:
        keyword_scores: Dictionary of section_id → keyword relevance scores.
        semantic_scores: Dictionary of section_id → semantic similarity scores.
        query: The original search query (used for weight classification).
        normalize: Whether to normalize scores to 0-100 scale.
        decay_factor: Decay factor for score normalization.

    Returns:
        List of (section_id, score) tuples, sorted descending.
    """
    # Classify query to get adaptive weights
    kw_weight, sem_weight = classify_query_weights(query, keyword_scores)

    # Apply RRF fusion
    fused = rrf_fusion(
        keyword_scores=keyword_scores,
        semantic_scores=semantic_scores,
        keyword_weight=kw_weight,
        semantic_weight=sem_weight,
    )

    # Optionally normalize to 0-100 scale
    if normalize:
        return normalize_scores_graded(fused, decay_factor)

    return fused
