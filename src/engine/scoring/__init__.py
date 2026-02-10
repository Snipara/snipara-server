"""Scoring engine for RLM hybrid search.

This package provides the scoring algorithms for keyword and semantic search:
- Keyword scoring with BM25-style length normalization
- Semantic scoring via embeddings (on-the-fly and pre-computed)
- Reciprocal Rank Fusion (RRF) for hybrid search
- Adaptive weight classification based on query type

Usage:
    from src.engine.scoring import (
        calculate_keyword_score,
        extract_keywords,
        classify_query_weights,
        rrf_fusion,
        hybrid_search,
    )
"""

from .constants import (
    CONCEPTUAL_PREFIXES,
    GENERIC_TITLE_TERMS,
    HYBRID_BALANCED,
    HYBRID_KEYWORD_HEAVY,
    HYBRID_SEMANTIC_HEAVY,
    LIST_QUERY_PATTERNS,
    NUMBERED_SECTION_PATTERNS,
    PLANNED_CONTENT_MARKERS,
    QUERY_EXPANSIONS,
    RRF_K,
    SPECIFIC_QUERY_TERMS,
    STOP_WORDS,
)
from .keyword_scorer import (
    calculate_keyword_score,
    expand_keywords,
    extract_keywords,
    filter_ubiquitous_keywords,
    is_list_query,
)
from .rrf_fusion import (
    classify_query_weights,
    hybrid_search,
    normalize_scores_graded,
    rrf_fusion,
)
from .semantic_scorer import (
    SemanticScorer,
    calculate_semantic_scores,
)
from .stemmer import stem_keyword

__all__ = [
    # Constants
    "CONCEPTUAL_PREFIXES",
    "GENERIC_TITLE_TERMS",
    "HYBRID_BALANCED",
    "HYBRID_KEYWORD_HEAVY",
    "HYBRID_SEMANTIC_HEAVY",
    "LIST_QUERY_PATTERNS",
    "NUMBERED_SECTION_PATTERNS",
    "PLANNED_CONTENT_MARKERS",
    "QUERY_EXPANSIONS",
    "RRF_K",
    "SPECIFIC_QUERY_TERMS",
    "STOP_WORDS",
    # Stemmer
    "stem_keyword",
    # Keyword scorer
    "calculate_keyword_score",
    "expand_keywords",
    "extract_keywords",
    "filter_ubiquitous_keywords",
    "is_list_query",
    # Semantic scorer
    "SemanticScorer",
    "calculate_semantic_scores",
    # RRF fusion
    "classify_query_weights",
    "hybrid_search",
    "normalize_scores_graded",
    "rrf_fusion",
]
