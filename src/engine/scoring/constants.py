"""Scoring constants for RLM search engine.

This module contains all constants used by the hybrid keyword+semantic search:
- Stop words for keyword filtering
- Hybrid weight profiles
- Query classification patterns
- List/enumeration detection patterns
- Query expansion mappings
"""

# ---------------------------------------------------------------------------
# Stop words — excluded from keyword scoring to prevent false title matches.
# Without this, "what are prices?" ranks "What Happens When Limits Are Exceeded"
# above actual pricing content because "what" and "are" get 5x title weight.
# ---------------------------------------------------------------------------
STOP_WORDS = frozenset(
    {
        # Articles, auxiliaries, modals
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "need",
        # Prepositions
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "out",
        "off",
        "over",
        "under",
        "again",
        "further",
        # Adverbs and conjunctions
        "then",
        "once",
        "here",
        "there",
        "when",
        "where",
        "why",
        "how",
        "all",
        "both",
        "each",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "nor",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "just",
        "because",
        "but",
        "and",
        "or",
        "if",
        # Pronouns and determiners
        "what",
        "which",
        "who",
        "whom",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "my",
        "your",
        "his",
        "her",
        "our",
        "their",
        "about",
        "up",
        "also",
        "any",
        "many",
        "much",
        # Generic nouns that appear in many queries but aren't distinctive
        "value",
        "proposition",
        "core",
        "main",
        "key",
        "primary",
        "work",
        "works",
        "working",
        "feature",
        "features",
        "thing",
        "things",
        "something",
        "everything",
        # Common verbs that don't add search value
        "use",
        "used",
        "using",
        "get",
        "gets",
        "getting",
        "make",
        "makes",
        "making",
        "see",
        "sees",
        "seeing",
        "know",
        "knows",
        "knowing",
        "think",
        "thinks",
        "want",
        "wants",
        "wanting",
        "like",
        "likes",
    }
)


# ---------------------------------------------------------------------------
# Adaptive Hybrid Search: weight profiles & RRF constant
# ---------------------------------------------------------------------------
# When keyword ranking has high confidence (exact title match, specific terms),
# boost keyword weight to prevent semantic noise from diluting precise results.
# When query is conceptual (how/why/explain), boost semantic weight.
HYBRID_KEYWORD_HEAVY = (0.60, 0.40)  # factual / title-match queries
HYBRID_BALANCED = (0.40, 0.60)  # default - favor semantic for better recall
HYBRID_SEMANTIC_HEAVY = (0.25, 0.75)  # conceptual / how-why queries

# Reciprocal Rank Fusion constant (k=60 is the standard from Cormack+ 2009).
# Lower k gives more weight to top-ranked results, improving precision.
# Higher k smooths rankings, improving recall.
RRF_K = 45  # Reduced from 60 for better precision while keeping good recall


# Generic title terms — these get reduced title weight (1.5x instead of 5x)
# because they appear in many unrelated sections and cause false matches.
GENERIC_TITLE_TERMS = frozenset(
    {
        "snipara",
        "rlm",
        "mcp",  # Project-specific but ubiquitous
        "tools",
        "tool",
        "guide",
        "reference",
        "overview",
        "docs",  # Generic doc terms
        "how",
        "what",
        "when",
        "where",
        "why",  # Question words (shouldn't boost titles)
        "using",
        "use",
        "get",
        "set",
        "run",
        "make",  # Common verbs
        "available",
        "not",
        "error",
        "issue",
        "troubleshoot",  # Debugging terms
    }
)


# Query terms that signal structured/factual content (keyword-friendly)
# These trigger keyword-heavy weights (60/40) for better precision
SPECIFIC_QUERY_TERMS = frozenset(
    {
        # Technical/infrastructure
        "pricing",
        "price",
        "cost",
        "tier",
        "plan",
        "stack",
        "version",
        "model",
        "schema",
        "table",
        "endpoint",
        "api",
        "command",
        "config",
        "database",
        "deploy",
        "deployment",
        "auth",
        "authentication",
        # Business/product terms - these need keyword matching
        "value",
        "proposition",
        "feature",
        "benefit",
        "overview",
        "architecture",
        "workflow",
        "integration",
        "limit",
        "rate",
        # Search-specific terms
        "hybrid",
        "semantic",
        "keyword",
        "search",
        "query",
        "token",
        "context",
        "chunk",
        "section",
        "document",
    }
)


# Conceptual query prefixes (semantic-friendly)
# These trigger semantic-heavy weights (25/75) for better conceptual matching
CONCEPTUAL_PREFIXES = (
    # How/Why questions
    "how does",
    "how do",
    "how is",
    "how are",
    "how can",
    "why does",
    "why do",
    "why is",
    "why are",
    # What questions (conceptual, not factual lookups)
    "what is",
    "what are",
    "what does",
    "what do",
    # Explanation requests
    "explain",
    "describe",
    "compare",
    "tell me about",
    "overview of",
    # Specific conceptual patterns
    "what happens when",
    "what is the difference",
    "what are the tradeoffs",
    "value proposition",
    "core value",
    "main purpose",
    "key features",
)


# ---------------------------------------------------------------------------
# List/Enumeration Query Detection
# ---------------------------------------------------------------------------
# Queries asking for lists of items (articles, tasks, features) should boost
# sections with numbered patterns like "### Article #1", "1. First item", etc.
LIST_QUERY_PATTERNS = frozenset(
    {
        "what are the",
        "list the",
        "list all",
        "which",
        "what to write",
        "what to do",
        "next articles",
        "next tasks",
        "next steps",
        "upcoming",
        "planned",
        "todo",
        "to-do",
        "roadmap",
    }
)

# Patterns in section titles/content that indicate enumerated list items
# These get boosted when a list query is detected
NUMBERED_SECTION_PATTERNS = (
    r"^#+\s*(?:article|task|step|item|feature|issue|bug|story)\s*#?\d+",  # ### Article #1
    r"^#+\s*\d+[\.\):]",  # ## 1. or ## 1) or ## 1:
    r"^\d+[\.\)]",  # 1. or 1) at start
    r"#\d+\b",  # #1, #2, etc.
)

# Terms indicating planned/unpublished/future content
# Boost sections containing these when query asks about "next" or "planned" items
PLANNED_CONTENT_MARKERS = frozenset(
    {
        "📝",
        "unpublished",
        "planned",
        "draft",
        "todo",
        "upcoming",
        "next:",
        "status:",
        "wip",
        "in progress",
        "pending",
    }
)


# ---------------------------------------------------------------------------
# Query Expansion: Abstract terms → concrete keywords for better search recall
# ---------------------------------------------------------------------------
# Abstract queries like "architecture" miss specific sections because they don't
# contain the actual component names. Expand abstract terms with concrete keywords.
QUERY_EXPANSIONS: dict[str, list[str]] = {
    # Architecture queries need component names
    "architecture": [
        "snipara-mcp",
        "FastAPI",
        "Railway",
        "Vercel",
        "Neon",
        "component",
        "three-component",
        "PostgreSQL",
        "Redis",
    ],
    "three-component": [
        "snipara-mcp",
        "FastAPI",
        "Vercel",
        "Railway",
        "PostgreSQL",
    ],
    "components": [
        "snipara-mcp",
        "FastAPI",
        "Vercel",
        "web app",
        "MCP server",
    ],
    # Stack queries
    "tech stack": [
        "Next.js",
        "FastAPI",
        "Prisma",
        "PostgreSQL",
        "Railway",
        "Tailwind",
        "DaisyUI",
        "Stripe",
    ],
    "stack": [
        "Next.js",
        "FastAPI",
        "Prisma",
        "PostgreSQL",
        "Railway",
    ],
    # Deployment queries
    "deployment": [
        "Railway",
        "Vercel",
        "Docker",
        "snipara-fastapi",
        "monorepo",
        "main branch",
        "dev branch",
        "auto-deploy",
    ],
    "deploy": [
        "Railway",
        "Vercel",
        "Docker",
        "production",
        "staging",
    ],
    # MCP tools queries need tool names
    "mcp tools": [
        "rlm_context_query",
        "rlm_ask",
        "rlm_search",
        "rlm_decompose",
        "rlm_multi_query",
        "rlm_plan",
        "rlm_remember",
        "rlm_recall",
    ],
    "tools": [
        "rlm_context_query",
        "rlm_ask",
        "rlm_search",
        "rlm_decompose",
    ],
    # Value proposition needs business terms
    "value proposition": [
        "context optimization",
        "token reduction",
        "90%",
        "LLM-agnostic",
        "high margins",
        "no vendor lock-in",
    ],
    # Shared context needs budget allocation terms
    "shared context": [
        "budget allocation",
        "MANDATORY",
        "BEST_PRACTICES",
        "GUIDELINES",
        "REFERENCE",
        "40%",
        "30%",
        "20%",
        "10%",
    ],
    "budget allocation": [
        "MANDATORY",
        "BEST_PRACTICES",
        "GUIDELINES",
        "REFERENCE",
        "40%",
        "30%",
        "20%",
        "10%",
        "shared context",
    ],
    # Pricing/limits need concrete values
    "pricing": [
        "FREE",
        "PRO",
        "TEAM",
        "ENTERPRISE",
        "$19",
        "$49",
        "$499",
        "queries/mo",
        "100",
        "5000",
        "20000",
    ],
    "limits": [
        "rate limit",
        "monthly",
        "429",
        "exceeded",
        "reset_at",
    ],
    # Memory/agent features
    "memory": [
        "rlm_remember",
        "rlm_recall",
        "rlm_memories",
        "rlm_forget",
        "ttl_days",
        "agent",
        "session",
        "decision",
        "learning",
    ],
    "agent": [
        "memory",
        "swarm",
        "rlm_remember",
        "rlm_recall",
        "coordination",
    ],
}


# ---------------------------------------------------------------------------
# Scoring Parameters
# ---------------------------------------------------------------------------
# Title match weight multiplier (distinctive keywords in titles)
TITLE_WEIGHT_DISTINCTIVE = 5.0
# Title match weight for generic terms
TITLE_WEIGHT_GENERIC = 1.5
# Body match weight
BODY_WEIGHT = 1.0
# BM25-style length normalization parameters
BM25_K1 = 1.2
BM25_B = 0.75
# Ideal section length (tokens) for length normalization
IDEAL_SECTION_LENGTH = 150
