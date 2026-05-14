"""Self-remote license configuration helpers."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from ..config import settings


def _fingerprint(value: str) -> str | None:
    """Return a non-sensitive fingerprint for logging and health output."""
    cleaned = value.strip()
    if not cleaned:
        return None
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:12]


def get_license_status() -> dict[str, Any]:
    """Return license configuration status without exposing the license key."""
    key = settings.snipara_license_key.strip()
    configured = bool(key)
    required = settings.snipara_license_required
    return {
        "product": "Snipara Server",
        "mode": "enterprise" if configured else "evaluation",
        "configured": configured,
        "required": required,
        "valid": configured or not required,
        "key_fingerprint": _fingerprint(key),
        "checked_at": datetime.now(UTC).isoformat(),
    }


def validate_license_configuration() -> None:
    """Fail startup when a production deployment requires a missing license."""
    status = get_license_status()
    if not status["valid"]:
        raise RuntimeError(
            "SNIPARA_LICENSE_REQUIRED is true but SNIPARA_LICENSE_KEY is not set. "
            "Set the license key issued under your Snipara enterprise agreement, "
            "or disable SNIPARA_LICENSE_REQUIRED for local evaluation."
        )
