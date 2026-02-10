"""Basic suffix stemmer for keyword matching.

This module provides a lightweight stemmer for improving keyword matching
without external dependencies like NLTK or spaCy.
"""


def stem_keyword(word: str) -> str:
    """Basic suffix stemmer to improve keyword matching.

    Strips common English suffixes to produce an approximate stem used for
    substring matching. A shorter stem naturally matches more morphological
    variants, e.g. ``stem_keyword("prices")`` → ``"pric"`` which is a
    substring of "pricing", "price", "priced", etc.

    Minimum-length guards ensure short words like "doing" (5 chars) are not
    over-stripped into meaningless 2-char stems.

    Args:
        word: The word to stem.

    Returns:
        The stemmed word (lowercased).
    """
    word = word.lower()

    # Longer suffixes first — order matters.
    if len(word) > 7 and word.endswith("tion"):
        return word[:-4]
    if len(word) > 7 and word.endswith("ment"):
        return word[:-4]
    if len(word) > 7 and word.endswith("ness"):
        return word[:-4]
    if len(word) > 7 and word.endswith("ible"):
        return word[:-4]
    if len(word) > 7 and word.endswith("able"):
        return word[:-4]
    if len(word) > 6 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 6 and word.endswith("ies"):
        return word[:-3]
    if len(word) > 5 and word.endswith("ed") and not word.endswith("eed"):
        return word[:-2]
    if len(word) > 5 and word.endswith("er"):
        return word[:-2]
    if len(word) > 5 and word.endswith("ly"):
        return word[:-2]
    if len(word) > 5 and word.endswith("es"):
        return word[:-2]
    if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    if len(word) > 4 and word.endswith("e") and not word.endswith("ee"):
        return word[:-1]
    return word
