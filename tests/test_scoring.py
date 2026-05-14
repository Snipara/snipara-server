"""Tests for the engine.scoring module.

These tests verify the extracted scoring module works correctly.
No database or external dependencies required.
"""


from src.engine.scoring import (
    adjust_score_for_query_intent,
    STOP_WORDS,
    calculate_keyword_score,
    compute_keyword_weights,
    classify_query_weights,
    expand_keywords,
    extract_keywords,
    filter_ubiquitous_keywords,
    hybrid_search,
    is_list_query,
    normalize_scores_graded,
    rrf_fusion,
    stem_keyword,
)
from src.engine.scoring.constants import (
    CONCEPTUAL_PREFIXES,
    GENERIC_TITLE_TERMS,
    HYBRID_BALANCED,
    HYBRID_KEYWORD_HEAVY,
    HYBRID_SEMANTIC_HEAVY,
    QUERY_EXPANSIONS,
    RRF_K,
    SPECIFIC_QUERY_TERMS,
)


class TestStemmer:
    """Tests for the stem_keyword function."""

    def test_stem_prices(self):
        """Test stemming 'prices' to 'pric'."""
        assert stem_keyword("prices") == "pric"

    def test_stem_pricing(self):
        """Test stemming 'pricing' to 'pric'."""
        assert stem_keyword("pricing") == "pric"

    def test_stem_authentication(self):
        """Test stemming 'authentication' removes -tion suffix."""
        assert stem_keyword("authentication") == "authentica"

    def test_stem_short_word(self):
        """Test that short words are not over-stemmed."""
        assert stem_keyword("go") == "go"
        assert stem_keyword("do") == "do"

    def test_stem_preserves_base(self):
        """Test that words without suffixes are preserved."""
        assert stem_keyword("api") == "api"
        # "code" is only 4 chars, below the 5-char threshold for 'e' removal
        assert stem_keyword("code") == "code"
        # Longer words with 'e' suffix do get stemmed
        assert stem_keyword("configure") == "configur"


class TestKeywordExtraction:
    """Tests for keyword extraction functions."""

    def test_extract_keywords_basic(self):
        """Test basic keyword extraction."""
        keywords = extract_keywords("What is Snipara?")
        assert "snipara" in keywords
        assert "what" not in keywords  # stop word

    def test_extract_keywords_stop_words_removed(self):
        """Test that stop words are removed."""
        keywords = extract_keywords("How does the API work?")
        assert "how" not in keywords
        assert "does" not in keywords
        assert "the" not in keywords
        assert "api" in keywords

    def test_expand_keywords(self):
        """Test keyword expansion with abstract terms."""
        keywords = ["architecture"]
        expanded = expand_keywords(keywords)
        assert "architecture" in expanded
        assert any(term in expanded for term in ["service", "system", "database"])
        assert not any(term in expanded for term in ["fastapi", "infomaniak", "vps"])

    def test_filter_ubiquitous_keywords(self):
        """Test separating ubiquitous from distinctive keywords."""
        keywords = ["snipara", "api", "authentication"]
        ubiquitous = {"snipara"}

        distinctive, ubiq = filter_ubiquitous_keywords(keywords, ubiquitous)
        assert "snipara" in ubiq
        assert "api" in distinctive
        assert "authentication" in distinctive


class TestListQueryDetection:
    """Tests for list/enumeration query detection."""

    def test_list_query_detected(self):
        """Test detection of list queries."""
        assert is_list_query("What are the next articles to write?")
        assert is_list_query("List all the features")
        assert is_list_query("What to do next?")

    def test_non_list_query(self):
        """Test that non-list queries are not detected."""
        assert not is_list_query("How does authentication work?")
        assert not is_list_query("Explain the architecture")


class TestQueryWeightClassification:
    """Tests for adaptive query weight classification."""

    def test_balanced_default(self):
        """Test that generic queries get balanced weights."""
        kw, sem = classify_query_weights("some query", {"s1": 5.0, "s2": 3.0})
        assert kw == HYBRID_BALANCED[0]
        assert sem == HYBRID_BALANCED[1]

    def test_conceptual_query_weights(self):
        """Test that conceptual queries get semantic-heavy weights."""
        kw, sem = classify_query_weights("how does authentication work?", {})
        assert kw == HYBRID_SEMANTIC_HEAVY[0]
        assert sem == HYBRID_SEMANTIC_HEAVY[1]

    def test_selection_query_weights(self):
        """Recommendation/selection prompts should favor semantic ranking."""
        kw, sem = classify_query_weights(
            "which model should I use for a security audit?",
            {"s1": 60.0, "s2": 10.0},
        )
        assert kw == HYBRID_SEMANTIC_HEAVY[0]
        assert sem == HYBRID_SEMANTIC_HEAVY[1]

    def test_keyword_heavy_with_specific_terms(self):
        """Test keyword-heavy weights for specific terms with strong signal."""
        # Strong keyword signal with specific terms
        kw_scores = {"s1": 50.0, "s2": 5.0, "s3": 1.0}  # Top score >> median
        kw, sem = classify_query_weights("pricing tier plan", kw_scores)
        assert kw == HYBRID_KEYWORD_HEAVY[0]


class TestRRFFusion:
    """Tests for Reciprocal Rank Fusion algorithm."""

    def test_rrf_basic(self):
        """Test basic RRF fusion."""
        kw_scores = {"s1": 10.0, "s2": 5.0, "s3": 1.0}
        sem_scores = {"s1": 0.9, "s2": 0.5, "s3": 0.8}

        results = rrf_fusion(kw_scores, sem_scores, 0.5, 0.5)

        # Results should be sorted descending
        assert len(results) == 3
        assert results[0][0] == "s1"  # s1 is top in both rankings

    def test_rrf_empty_inputs(self):
        """Test RRF with empty inputs."""
        assert rrf_fusion({}, {}, 0.5, 0.5) == []

    def test_rrf_disjoint_rankings(self):
        """Test RRF with disjoint rankings."""
        kw_scores = {"s1": 10.0}
        sem_scores = {"s2": 0.9}

        results = rrf_fusion(kw_scores, sem_scores, 0.5, 0.5)
        assert len(results) == 2  # Union of both


class TestScoreNormalization:
    """Tests for graded score normalization."""

    def test_normalize_basic(self):
        """Test basic score normalization."""
        scores = [("s1", 0.05), ("s2", 0.04), ("s3", 0.03)]
        normalized = normalize_scores_graded(scores)

        assert normalized[0][1] == 100.0  # Top gets 100
        assert normalized[1][1] < 100.0  # Others decay
        assert normalized[2][1] < normalized[1][1]

    def test_normalize_empty(self):
        """Test normalization of empty list."""
        assert normalize_scores_graded([]) == []


class TestHybridSearch:
    """Tests for the complete hybrid search pipeline."""

    def test_hybrid_search_basic(self):
        """Test complete hybrid search pipeline."""
        kw_scores = {"s1": 10.0, "s2": 5.0}
        sem_scores = {"s1": 0.8, "s2": 0.9}

        results = hybrid_search(kw_scores, sem_scores, "test query")
        assert len(results) == 2
        # First result should have score 100 (normalized)
        assert results[0][1] == 100.0


class TestKeywordScoring:
    """Tests for keyword scoring heuristics."""

    def test_generic_title_term_does_not_get_multi_hit_boost(self):
        """Generic terms like 'model' should not dominate via title coverage boost."""

        class Section:
            def __init__(self, title: str):
                self.id = title
                self.title = title
                self.content = "Reserve for security audits and deep reviews."
                self.start_line = 1
                self.end_line = 2
                self.level = 2

        generic = Section("Security model")
        relevant = Section("Security audit guidance")

        generic_score = calculate_keyword_score(generic, ["model", "security", "audit"])
        relevant_score = calculate_keyword_score(relevant, ["model", "security", "audit"])

        assert relevant_score > generic_score

    def test_compute_keyword_weights_prioritizes_rare_terms(self):
        class Section:
            def __init__(self, title: str, content: str):
                self.id = title
                self.title = title
                self.content = content
                self.start_line = 1
                self.end_line = 2
                self.level = 2

        sections = [
            Section("Security Model", "Security model details."),
            Section("OPUS (Most Capable)", "Reserve Opus for security audits."),
            Section("The Daemon Model", "Daemon model overview."),
        ]

        weights = compute_keyword_weights(sections, ["model", "security", "audit"])

        assert weights["audit"] > weights["model"]

    def test_selection_intent_boosts_actionable_guidance(self):
        class Section:
            def __init__(self, title: str, content: str):
                self.id = title
                self.title = title
                self.content = content
                self.start_line = 1
                self.end_line = 2
                self.level = 2

        actionable = Section("OPUS (Most Capable)", "Reserve Opus for security audits.")
        explanatory = Section("Security Model", "The security model covers bearer tokens.")

        boosted = adjust_score_for_query_intent(
            actionable,
            "which model should I use for a security audit",
            10.0,
            keywords=["model", "security", "audit"],
        )
        penalized = adjust_score_for_query_intent(
            explanatory,
            "which model should I use for a security audit",
            10.0,
            keywords=["model", "security", "audit"],
        )

        assert boosted > penalized

    def test_keyword_scoring_lifts_audit_recommendation_section(self):
        class Section:
            def __init__(self, title: str, content: str):
                self.id = title
                self.title = title
                self.content = content
                self.start_line = 1
                self.end_line = 2
                self.level = 2

        sections = [
            Section("Security Model", "The security model covers bearer tokens."),
            Section("The Daemon Model", "The daemon model explains a long-lived process."),
            Section("OPUS (Most Capable)", "Reserve Opus for security audits and deep reviews."),
        ]

        query = "which model should I use for a security audit"
        keywords = expand_keywords(extract_keywords(query))
        weights = compute_keyword_weights(sections, keywords)
        ranked = sorted(
            (
                (
                    section.title,
                    calculate_keyword_score(
                        section,
                        keywords,
                        keyword_weights=weights,
                        query=query,
                    ),
                )
                for section in sections
            ),
            key=lambda item: item[1],
            reverse=True,
        )

        assert ranked[0][0] == "OPUS (Most Capable)"

    def test_handle_query_focuses_problem_section(self):
        class Section:
            def __init__(self, title: str, content: str):
                self.id = title
                self.title = title
                self.content = content
                self.start_line = 1
                self.end_line = 2
                self.level = 2

        sections = [
            Section(
                "Gstack Browser Architecture",
                "The browser daemon manages lifecycle and orchestration.",
            ),
            Section(
                "Port Selection",
                "The daemon falls back to the next available port when a collision is detected.",
            ),
        ]

        query = "how does the gstack browser daemon handle port collisions"
        keywords = expand_keywords(extract_keywords(query))
        weights = compute_keyword_weights(sections, keywords)
        ranked = sorted(
            (
                (
                    section.title,
                    calculate_keyword_score(
                        section,
                        keywords,
                        keyword_weights=weights,
                        query=query,
                    ),
                )
                for section in sections
            ),
            key=lambda item: item[1],
            reverse=True,
        )

        assert ranked[0][0] == "Port Selection"


class TestConstants:
    """Tests for scoring constants."""

    def test_stop_words_not_empty(self):
        """Test that stop words set is populated."""
        assert len(STOP_WORDS) > 50

    def test_generic_title_terms(self):
        """Test generic title terms include expected values."""
        assert "snipara" in GENERIC_TITLE_TERMS
        assert "mcp" in GENERIC_TITLE_TERMS

    def test_specific_query_terms(self):
        """Test specific query terms include expected values."""
        assert "pricing" in SPECIFIC_QUERY_TERMS
        assert "api" in SPECIFIC_QUERY_TERMS

    def test_conceptual_prefixes(self):
        """Test conceptual prefixes."""
        assert "how does" in CONCEPTUAL_PREFIXES
        assert "what is" in CONCEPTUAL_PREFIXES

    def test_query_expansions(self):
        """Test query expansions dictionary."""
        assert "architecture" in QUERY_EXPANSIONS
        assert len(QUERY_EXPANSIONS["architecture"]) > 0

    def test_rrf_k_value(self):
        """Test RRF constant is reasonable."""
        assert RRF_K > 0
        assert RRF_K < 100  # Standard values are 45-60
