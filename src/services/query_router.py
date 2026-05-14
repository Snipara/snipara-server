"""Smart Query Router - Automatically selects optimal execution mode.

This module provides intelligent routing for Snipara queries, determining
whether to use direct context (Mode B) or RLM-Runtime (Mode C) based on
query characteristics.

Routing Criteria:
- Simple factual queries → Direct context (fast, token-efficient)
- Multi-step reasoning → RLM-Runtime (better quality)
- Code generation → RLM-Runtime (iterative refinement)
- Complex queries needing decomposition → RLM-Runtime

Usage:
    from services.query_router import QueryRouter, RouteDecision

    router = QueryRouter()
    decision = router.route(query, context_tokens=4000)

    if decision.mode == "direct":
        # Use rlm_context_query directly
        result = await context_query(query, max_tokens=decision.budget)
    else:
        # Use RLM-Runtime
        result = await rlm.completion(query, options=decision.rlm_options)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class QueryMode(Enum):
    """Execution modes for queries."""

    DIRECT = "direct"  # Direct context query (Mode B)
    RLM_RUNTIME = "rlm"  # RLM-Runtime with tools (Mode C)


class QueryComplexity(Enum):
    """Query complexity levels."""

    SIMPLE = "simple"  # Single-topic factual queries
    MODERATE = "moderate"  # Multi-aspect queries
    COMPLEX = "complex"  # Multi-step reasoning, code generation


@dataclass
class RouteDecision:
    """Routing decision with execution parameters."""

    mode: QueryMode
    complexity: QueryComplexity
    confidence: float  # 0-1, how confident we are in this routing
    reason: str  # Human-readable explanation

    # Mode-specific parameters
    token_budget: int = 6000  # Context token budget
    search_mode: str = "hybrid"  # keyword, semantic, hybrid
    rlm_max_depth: int = 3  # Max RLM recursion depth
    rlm_token_budget: int = 30000  # RLM total token budget
    recommended_tool: str | None = None  # Optional concrete MCP tool recommendation
    recommended_tool_arguments: dict[str, Any] = field(default_factory=dict)

    @property
    def is_direct(self) -> bool:
        return self.mode == QueryMode.DIRECT

    @property
    def is_rlm(self) -> bool:
        return self.mode == QueryMode.RLM_RUNTIME


@dataclass
class QueryRouter:
    """Smart query router that selects optimal execution mode.

    The router analyzes query characteristics to determine:
    1. Query complexity (simple/moderate/complex)
    2. Best execution mode (direct context vs RLM-Runtime)
    3. Optimal parameters (token budgets, search mode, etc.)

    Routing heuristics:
    - Code-related queries → RLM (needs iterative refinement)
    - "How to" / "Explain" queries → RLM (needs reasoning)
    - Simple lookups ("What is X?") → Direct (fast, efficient)
    - Multi-part queries → RLM (needs decomposition)
    """

    # Patterns that indicate complex queries needing RLM
    _COMPLEX_PATTERNS: list[re.Pattern] = field(default_factory=list)

    # Patterns that indicate simple queries (prefer direct)
    _SIMPLE_PATTERNS: list[re.Pattern] = field(default_factory=list)

    # Code-related keywords
    _CODE_KEYWORDS: set[str] = field(default_factory=set)
    _HYBRID_CODE_PATTERNS: list[re.Pattern] = field(default_factory=list)
    _SYMBOL_TARGET_RE: re.Pattern | None = None
    _FILE_TARGET_RE: re.Pattern | None = None

    def __post_init__(self):
        # Complex query patterns → RLM-Runtime
        self._COMPLEX_PATTERNS = [
            re.compile(r"\b(how to|how do|how can|explain|describe|walk me through)\b", re.I),
            re.compile(
                r"\b(implement|create|build|write|generate|refactor)\b.*\b(code|function|class|component|api|endpoint)\b",
                re.I,
            ),
            re.compile(r"\b(step by step|steps to|process for)\b", re.I),
            re.compile(r"\b(compare|difference between|versus|vs\.?)\b", re.I),
            re.compile(r"\b(debug|fix|solve|troubleshoot)\b", re.I),
            re.compile(
                r"\b(and|also|additionally|furthermore)\b.*\?", re.I
            ),  # Multi-part questions
            re.compile(r"\?.*\?", re.I),  # Multiple questions
        ]

        # Simple query patterns → Direct context
        self._SIMPLE_PATTERNS = [
            re.compile(r"^what (is|are) (the )?(.*?)\??$", re.I),
            re.compile(r"^where (is|are|can|do)\b", re.I),
            re.compile(r"^which\b", re.I),
            re.compile(r"^(list|show|get) (the )?(.*?)\??$", re.I),
            re.compile(r"\b(pricing|plans?|cost|price)\b", re.I),
            re.compile(r"\b(version|release)\b", re.I),
        ]

        # Code-related keywords
        self._CODE_KEYWORDS = {
            "code",
            "function",
            "class",
            "method",
            "api",
            "endpoint",
            "implement",
            "create",
            "build",
            "write",
            "generate",
            "refactor",
            "typescript",
            "javascript",
            "python",
            "react",
            "nextjs",
            "test",
            "unit test",
            "integration test",
            "lint",
            "typecheck",
        }
        self._HYBRID_CODE_PATTERNS = [
            re.compile(r"\b(explain|describe|walk me through|how|why|behavior|flow|works?)\b", re.I),
            re.compile(r"\b(implementation|request handling|request flow|lifecycle|control flow)\b", re.I),
        ]
        self._SYMBOL_TARGET_RE = re.compile(r"\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*){2,})\b")
        self._FILE_TARGET_RE = re.compile(r"\b((?:[\w.-]+/)+[\w.-]+\.(?:py|pyi|ts|tsx|js|jsx|go))\b")

    def route(
        self,
        query: str,
        context_tokens: int = 0,
        force_mode: QueryMode | None = None,
    ) -> RouteDecision:
        """Determine optimal execution mode for a query.

        Args:
            query: The user's query
            context_tokens: Current context size (if available)
            force_mode: Override routing decision (for testing)

        Returns:
            RouteDecision with mode, parameters, and reasoning
        """
        if force_mode:
            return RouteDecision(
                mode=force_mode,
                complexity=QueryComplexity.MODERATE,
                confidence=1.0,
                reason=f"Forced to {force_mode.value} mode",
            )

        structural_match = self._match_structural_code_query(query)
        if structural_match is not None:
            return self._route_to_structural(structural_match)

        hybrid_graph_match = self._match_contextual_graph_query(query)

        # Analyze query
        complexity = self._assess_complexity(query)
        code_related = self._is_code_related(query)
        multi_part = self._is_multi_part(query)

        # Decision matrix
        if hybrid_graph_match is not None:
            effective_complexity = (
                QueryComplexity.MODERATE if complexity == QueryComplexity.SIMPLE else complexity
            )
            decision = self._route_to_rlm(query, effective_complexity, True, multi_part)
        elif complexity == QueryComplexity.COMPLEX or code_related or multi_part:
            decision = self._route_to_rlm(query, complexity, code_related, multi_part)
        elif complexity == QueryComplexity.SIMPLE:
            decision = self._route_to_direct(query, complexity)
        else:
            # Moderate complexity - use context size as tiebreaker
            if context_tokens > 10000:
                # Large context already available, use direct
                decision = self._route_to_direct(query, complexity)
            else:
                # Let RLM fetch optimal context
                decision = self._route_to_rlm(query, complexity, code_related, multi_part)

        if hybrid_graph_match and decision.recommended_tool is None:
            decision.recommended_tool = hybrid_graph_match["tool"]
            decision.recommended_tool_arguments = hybrid_graph_match["args"]
            decision.reason = f"{decision.reason}; graph hint: {hybrid_graph_match['reason']}"

        return decision

    def _assess_complexity(self, query: str) -> QueryComplexity:
        """Assess query complexity based on patterns."""
        # Check for complex patterns
        complex_matches = sum(1 for p in self._COMPLEX_PATTERNS if p.search(query))
        if complex_matches >= 2:
            return QueryComplexity.COMPLEX

        # Check for simple patterns
        simple_matches = sum(1 for p in self._SIMPLE_PATTERNS if p.search(query))
        if simple_matches >= 1 and complex_matches == 0:
            return QueryComplexity.SIMPLE

        # Word count heuristic
        word_count = len(query.split())
        if word_count <= 8:
            return QueryComplexity.SIMPLE
        elif word_count >= 25:
            return QueryComplexity.COMPLEX

        return QueryComplexity.MODERATE

    def _match_structural_code_query(self, query: str) -> dict[str, Any] | None:
        """Match structural code queries that map directly to graph tools."""
        normalized = query.strip()
        normalized = re.sub(r"\s+", " ", normalized)

        callers_match = re.match(
            r"^(?:who calls|who is calling|callers of|find callers of)\s+(.+?)\??$",
            normalized,
            re.I,
        )
        if callers_match:
            target = self._symbol_target_argument_dict(callers_match.group(1))
            if target:
                return {
                    "tool": "rlm_code_callers",
                    "args": {**target, "depth": 1, "limit": 50},
                    "reason": "structural code query (reverse call lookup)",
                }

        imports_out_match = re.match(
            r"^(?:imports of|show imports of|what does)\s+(.+?)(?:\s+import)?\??$",
            normalized,
            re.I,
        )
        if imports_out_match:
            target = self._import_target_argument_dict(imports_out_match.group(1))
            if target:
                return {
                    "tool": "rlm_code_imports",
                    "args": {**target, "direction": "out", "limit": 50},
                    "reason": "structural code query (outgoing imports)",
                }

        imports_in_match = re.match(
            r"^(?:who imports|importers of|what imports)\s+(.+?)\??$",
            normalized,
            re.I,
        )
        if imports_in_match:
            target = self._import_target_argument_dict(imports_in_match.group(1))
            if target:
                return {
                    "tool": "rlm_code_imports",
                    "args": {**target, "direction": "in", "limit": 50},
                    "reason": "structural code query (incoming imports)",
                }

        neighbors_match = re.match(
            r"^(?:neighbors of|show neighbors of|subgraph for|graph around|neighbors around)\s+(.+?)\??$",
            normalized,
            re.I,
        )
        if neighbors_match:
            target = self._symbol_target_argument_dict(neighbors_match.group(1))
            if target:
                return {
                    "tool": "rlm_code_neighbors",
                    "args": {**target, "depth": 2, "limit": 200},
                    "reason": "structural code query (local code graph)",
                }

        path_match = re.match(
            r"^(?:shortest path from|path from|how is)\s+(.+?)\s+(?:connected to|to)\s+(.+?)\??$",
            normalized,
            re.I,
        )
        if path_match:
            from_target = self._symbol_target_argument_dict(path_match.group(1), prefix="from")
            to_target = self._symbol_target_argument_dict(path_match.group(2), prefix="to")
            if from_target and to_target:
                return {
                    "tool": "rlm_code_shortest_path",
                    "args": {
                        **from_target,
                        **to_target,
                        "max_hops": 6,
                    },
                    "reason": "structural code query (shortest path)",
                }

        return None

    def _route_to_structural(self, match: dict[str, Any]) -> RouteDecision:
        """Create a direct recommendation for a structural code graph tool."""
        tool = match["tool"]
        return RouteDecision(
            mode=QueryMode.DIRECT,
            complexity=QueryComplexity.MODERATE,
            confidence=0.95,
            reason=f"Direct graph lookup recommended: {match['reason']}",
            token_budget=2000,
            search_mode="keyword",
            recommended_tool=tool,
            recommended_tool_arguments=match["args"],
        )

    def _match_contextual_graph_query(self, query: str) -> dict[str, Any] | None:
        """Surface graph hints for mixed developer questions while keeping doc-first mode."""
        if not any(pattern.search(query) for pattern in self._HYBRID_CODE_PATTERNS):
            return None

        if self._FILE_TARGET_RE is not None:
            file_match = self._FILE_TARGET_RE.search(query)
            if file_match:
                target = self._import_target_argument_dict(file_match.group(1))
                if target:
                    return {
                        "tool": "rlm_code_imports",
                        "args": {**target, "direction": "out", "limit": 24},
                        "reason": "mixed developer query (file dependency context)",
                    }

        if self._SYMBOL_TARGET_RE is not None:
            symbol_match = self._SYMBOL_TARGET_RE.search(query)
            if symbol_match:
                target = self._symbol_target_argument_dict(symbol_match.group(1))
                if target:
                    return {
                        "tool": "rlm_code_neighbors",
                        "args": {**target, "depth": 2, "limit": 24},
                        "reason": "mixed developer query (symbol structure context)",
                    }

        return None

    def _is_code_related(self, query: str) -> bool:
        """Check if query is code-related."""
        query_lower = query.lower()
        return any(kw in query_lower for kw in self._CODE_KEYWORDS)

    def _is_multi_part(self, query: str) -> bool:
        """Check if query has multiple parts/questions."""
        # Multiple question marks
        if query.count("?") >= 2:
            return True
        # Conjunctions suggesting multiple requests
        if re.search(r"\b(and|also|additionally)\b.*\b(and|also|additionally)\b", query, re.I):
            return True
        # Numbered or bulleted items
        if re.search(r"(^|\n)\s*[1-9]\.", query):
            return True
        return False

    def _route_to_direct(self, query: str, complexity: QueryComplexity) -> RouteDecision:
        """Create decision for direct context mode."""
        # Select search mode based on query
        if re.search(r"\b(exact|specific|called|named)\b", query, re.I):
            search_mode = "keyword"
        elif re.search(r"\b(like|similar|related|about)\b", query, re.I):
            search_mode = "semantic"
        else:
            search_mode = "hybrid"

        return RouteDecision(
            mode=QueryMode.DIRECT,
            complexity=complexity,
            confidence=0.8 if complexity == QueryComplexity.SIMPLE else 0.6,
            reason=f"Simple {complexity.value} query - direct context is efficient",
            token_budget=6000,
            search_mode=search_mode,
        )

    def _route_to_rlm(
        self,
        query: str,
        complexity: QueryComplexity,
        code_related: bool,
        multi_part: bool,
    ) -> RouteDecision:
        """Create decision for RLM-Runtime mode."""
        reasons = []
        if complexity == QueryComplexity.COMPLEX:
            reasons.append("complex reasoning required")
        if code_related:
            reasons.append("code-related task")
        if multi_part:
            reasons.append("multi-part question")

        # Adjust parameters based on complexity
        if complexity == QueryComplexity.COMPLEX:
            rlm_budget = 50000
            max_depth = 5
        else:
            rlm_budget = 30000
            max_depth = 3

        return RouteDecision(
            mode=QueryMode.RLM_RUNTIME,
            complexity=complexity,
            confidence=0.85 if code_related else 0.7,
            reason=f"RLM recommended: {', '.join(reasons)}",
            token_budget=8000,  # Pre-fetch more context for RLM
            search_mode="hybrid",
            rlm_max_depth=max_depth,
            rlm_token_budget=rlm_budget,
        )

    @staticmethod
    def _clean_target(raw_target: str) -> str:
        """Normalize a user-provided symbol or path target."""
        cleaned = raw_target.strip().strip("`'\"")
        cleaned = cleaned.rstrip("?.!,;:")
        return cleaned.strip()

    def _import_target_argument_dict(self, raw_target: str) -> dict[str, str] | None:
        """Map a free-form import target to the right tool argument."""
        target = self._clean_target(raw_target)
        if not target:
            return None
        if "::" in target or target.startswith("python::"):
            return {"symbol_key": target}
        if "/" in target or target.endswith((".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".go")):
            return {"file_path": target}
        return {"qualified_name": target}

    def _symbol_target_argument_dict(
        self,
        raw_target: str,
        *,
        prefix: str | None = None,
    ) -> dict[str, str] | None:
        """Map a free-form symbol target to tool arguments.

        Structural graph traversals operate on repo-qualified symbols or stable
        symbol keys, not file paths. Returning None for file-local paths keeps
        the router from suggesting invalid tool calls.
        """
        target = self._clean_target(raw_target)
        if not target:
            return None

        if "::" in target or target.startswith("python::"):
            if prefix is None:
                return {"symbol_key": target}
            return {f"{prefix}_symbol_key": target}

        if "/" in target or target.endswith((".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".go")):
            return None

        if prefix is None:
            return {"qualified_name": target}
        return {prefix: target}


# Singleton instance for convenience
_router: QueryRouter | None = None


def get_router() -> QueryRouter:
    """Get or create the singleton router instance."""
    global _router
    if _router is None:
        _router = QueryRouter()
    return _router


def route_query(query: str, context_tokens: int = 0) -> RouteDecision:
    """Convenience function to route a query.

    Args:
        query: The user's query
        context_tokens: Current context size (optional)

    Returns:
        RouteDecision with optimal mode and parameters
    """
    return get_router().route(query, context_tokens)


# Query complexity scoring for external use
def assess_query_complexity(query: str) -> dict:
    """Assess query complexity and return detailed analysis.

    Useful for debugging routing decisions or logging.

    Returns:
        {
            "complexity": "simple" | "moderate" | "complex",
            "code_related": bool,
            "multi_part": bool,
            "word_count": int,
            "recommended_mode": "direct" | "rlm",
        }
    """
    router = get_router()
    decision = router.route(query)

    return {
        "complexity": decision.complexity.value,
        "code_related": router._is_code_related(query),
        "multi_part": router._is_multi_part(query),
        "word_count": len(query.split()),
        "recommended_mode": decision.mode.value,
        "confidence": decision.confidence,
        "reason": decision.reason,
        "recommended_tool": decision.recommended_tool,
        "recommended_tool_arguments": decision.recommended_tool_arguments,
    }
