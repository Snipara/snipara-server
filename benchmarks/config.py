"""Benchmark configuration and constants.

AUTHENTICATION:
    OAuth tokens are the PREFERRED authentication method for Snipara.
    OAuth tokens are auto-loaded from ~/.snipara/tokens.json.

    To authenticate:
        1. Run: snipara-mcp-login
        2. Follow the device flow prompts
        3. Tokens are saved automatically

    API keys (SNIPARA_API_KEY) are deprecated for benchmarks.
    Use OAuth for secure, refreshable authentication.
"""

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


def load_oauth_access_token(project_slug: str = "snipara") -> Optional[str]:
    """Load OAuth access token from ~/.snipara/tokens.json.

    Returns:
        Access token string or None if not found/expired
    """
    tokens_file = Path.home() / ".snipara" / "tokens.json"
    if not tokens_file.exists():
        return None

    try:
        tokens = json.loads(tokens_file.read_text())
        for _, token_data in tokens.items():
            if token_data.get("project_slug") == project_slug:
                # Warn if expired (SniparaClient will auto-refresh)
                expires_at = token_data.get("expires_at")
                if expires_at:
                    try:
                        exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                        if exp_dt.tzinfo is None:
                            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                        if exp_dt < datetime.now(timezone.utc):
                            print(
                                f"[config] OAuth token expired at {expires_at}. "
                                "SniparaClient will attempt auto-refresh.",
                                file=sys.stderr,
                            )
                    except (ValueError, TypeError):
                        pass
                return token_data.get("access_token")
        # Fallback to first token
        if tokens:
            return list(tokens.values())[0].get("access_token")
    except (json.JSONDecodeError, KeyError):
        pass
    return None


class BenchmarkType(Enum):
    """Types of benchmarks available."""
    TOKEN_EFFICIENCY = "token_efficiency"
    CONTEXT_QUALITY = "context_quality"
    HALLUCINATION = "hallucination"
    ANSWER_QUALITY = "answer_quality"


@dataclass
class BenchmarkConfig:
    """Configuration for running benchmarks.

    Authentication priority:
        1. OAuth token from ~/.snipara/tokens.json (preferred)
        2. SNIPARA_API_KEY env var (deprecated)

    Run 'snipara-mcp-login' to set up OAuth authentication.
    """

    # LLM Settings - GPT-4o-mini is default (cheaper for benchmarks)
    model: str = "gpt-4o-mini"
    llm_provider: str = "openai"  # Provider: openai, minimax, together, anthropic
    api_key: Optional[str] = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    base_url: Optional[str] = None
    max_tokens_response: int = 2048

    # Snipara Settings - OAuth preferred, API key deprecated
    snipara_project_slug: str = field(default_factory=lambda: os.getenv("SNIPARA_PROJECT_SLUG", "snipara"))
    snipara_api_url: str = "http://localhost:8000/mcp"  # Use local dev server
    # OAuth token auto-loaded, API key only as fallback
    snipara_oauth_token: Optional[str] = field(default_factory=lambda: load_oauth_access_token())
    snipara_api_key: Optional[str] = None  # Deprecated - use OAuth

    # Token Budgets for comparison
    with_snipara_budget: int = 8000      # Optimized context (increased for better recall)
    without_snipara_budget: int = 50000  # Full docs (simulated)

    # Benchmark Settings
    num_trials: int = 3                   # Repeat each test N times
    timeout_seconds: int = 60             # Max time per LLM call

    # Output
    reports_dir: Path = field(default_factory=lambda: Path(__file__).parent / "reports")
    verbose: bool = True

    def __post_init__(self):
        self.reports_dir.mkdir(parents=True, exist_ok=True)


# Evaluation thresholds
THRESHOLDS = {
    "compression_ratio_good": 5.0,       # 5:1 compression is good
    "compression_ratio_excellent": 10.0,  # 10:1 is excellent
    "precision_good": 0.7,               # 70% precision is good
    "recall_good": 0.6,                  # 60% recall is good
    "hallucination_acceptable": 0.1,     # <10% hallucination rate
    "answer_accuracy_good": 0.8,         # 80% correct answers
}


# Token costs (per 1M tokens, approximate)
TOKEN_COSTS = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},  # Default - very cheap
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
    "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
}
