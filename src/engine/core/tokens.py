"""Token counting utilities.

This module provides token counting using tiktoken for GPT-4/Claude compatibility.
"""

import tiktoken

# Initialize tiktoken encoder (using cl100k_base for GPT-4/Claude compatibility)
_encoding: tiktoken.Encoding | None = None


def get_encoder() -> tiktoken.Encoding:
    """Get or create the tiktoken encoder (lazy initialization).

    Returns:
        The tiktoken encoding instance for cl100k_base
    """
    global _encoding
    if _encoding is None:
        _encoding = tiktoken.get_encoding("cl100k_base")
    return _encoding


def count_tokens(text: str) -> int:
    """Count tokens in text using tiktoken.

    Args:
        text: Text to count tokens for

    Returns:
        Number of tokens in the text
    """
    return len(get_encoder().encode(text))
