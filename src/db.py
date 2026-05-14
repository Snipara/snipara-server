"""Database connection module using Prisma with automatic reconnection."""

import asyncio
import logging
import os
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from prisma import Prisma

logger = logging.getLogger(__name__)

# Global Prisma client instance
_client: Prisma | None = None
_lock = asyncio.Lock()
_last_healthcheck_monotonic: float | None = None

# Reconnection settings
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 1.0
HEALTHCHECK_INTERVAL_SECONDS = 300.0


def _normalize_database_url(url: str | None) -> str | None:
    """Strip Prisma's schema query param so public stays in the search_path."""
    if not url:
        return url

    parts = urlsplit(url)
    query_items = parse_qsl(parts.query, keep_blank_values=True)
    filtered_items = [(key, value) for key, value in query_items if key.lower() != "schema"]

    if len(filtered_items) == len(query_items):
        return url

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(filtered_items),
            parts.fragment,
        )
    )


def _prepare_database_url() -> None:
    """Ensure DATABASE_URL does not force a single schema."""
    current_url = os.getenv("DATABASE_URL")
    normalized_url = _normalize_database_url(current_url)

    if normalized_url and normalized_url != current_url:
        os.environ["DATABASE_URL"] = normalized_url
        logger.warning(
            "Removed schema query parameter from DATABASE_URL to preserve "
            "tenant_snipara, public search_path for pgvector"
        )


async def _create_client() -> Prisma:
    """Create and connect a new Prisma client with retry logic."""
    for attempt in range(MAX_RETRIES):
        try:
            _prepare_database_url()
            client = Prisma()
            await client.connect()
            # CRITICAL: Force search_path for pgvector support
            # Multi-tenant databases (PostgreSQL) need both tenant schema (for tables) and public (for pgvector)
            try:
                await client.execute_raw("SET search_path TO tenant_snipara, public;")
                logger.info("Database search_path set to: tenant_snipara, public")
            except Exception as e:
                logger.error(f"FAILED to set search_path (pgvector will not work): {e}")
            logger.info("Database connection established")
            return client
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY_SECONDS * (2**attempt)  # Exponential backoff
                logger.warning(
                    f"Database connection attempt {attempt + 1} failed: {e}. "
                    f"Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
            else:
                logger.error(f"Failed to connect to database after {MAX_RETRIES} attempts: {e}")
                raise


async def _is_connected(client: Prisma) -> bool:
    """Check if the database connection is still alive."""
    try:
        # Execute a simple query to verify connection
        await client.query_raw("SELECT 1")
        return True
    except Exception:
        return False


async def get_db() -> Prisma:
    """
    Get or create the Prisma client instance with automatic reconnection.

    Handles idle connection closures from Neon/PostgreSQL by verifying
    connection health and reconnecting if necessary.
    """
    global _client, _last_healthcheck_monotonic

    async with _lock:
        # Check if we have an existing client and if it's still connected
        if _client is not None:
            if _client.is_connected():
                now = time.monotonic()
                if (
                    _last_healthcheck_monotonic is not None
                    and now - _last_healthcheck_monotonic < HEALTHCHECK_INTERVAL_SECONDS
                ):
                    return _client

                if await _is_connected(_client):
                    _last_healthcheck_monotonic = now
                    return _client
            else:
                logger.warning("Database client disconnected, reconnecting...")

            # Connection is stale, disconnect and recreate
            logger.warning("Database connection stale, reconnecting...")
            try:
                await _client.disconnect()
            except Exception:
                pass  # Ignore disconnect errors on stale connection
            _client = None
            _last_healthcheck_monotonic = None

        # Create new connection
        _client = await _create_client()
        _last_healthcheck_monotonic = time.monotonic()
        return _client


async def close_db() -> None:
    """Close the database connection."""
    global _client, _last_healthcheck_monotonic
    async with _lock:
        if _client is not None:
            try:
                await _client.disconnect()
                logger.info("Database connection closed")
            except Exception as e:
                logger.warning(f"Error closing database connection: {e}")
            finally:
                _client = None
                _last_healthcheck_monotonic = None
