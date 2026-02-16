"""Database connection module using Prisma with automatic reconnection."""

import asyncio
import logging

from prisma import Prisma

logger = logging.getLogger(__name__)

# Global Prisma client instance
_client: Prisma | None = None
_lock = asyncio.Lock()

# Reconnection settings
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 1.0


async def _create_client() -> Prisma:
    """Create and connect a new Prisma client with retry logic."""
    for attempt in range(MAX_RETRIES):
        try:
            client = Prisma()
            await client.connect()
            # Ensure public schema is in search_path for pgvector types
            # Multi-tenant databases (Vaultbrix) set search_path to tenant schema only,
            # but pgvector is installed in public schema
            try:
                result = await client.query_raw("SHOW search_path;")
                current_path = result[0]["search_path"] if result else ""
                if "public" not in current_path.lower():
                    # Append public to existing search_path
                    new_path = f"{current_path}, public" if current_path else "public"
                    await client.execute_raw(f"SET search_path TO {new_path};")
                    logger.info(f"Database search_path updated: {new_path}")
            except Exception as e:
                logger.warning(f"Could not update search_path: {e}")
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
    global _client

    async with _lock:
        # Check if we have an existing client and if it's still connected
        if _client is not None:
            if await _is_connected(_client):
                return _client
            else:
                # Connection is stale, disconnect and recreate
                logger.warning("Database connection stale, reconnecting...")
                try:
                    await _client.disconnect()
                except Exception:
                    pass  # Ignore disconnect errors on stale connection
                _client = None

        # Create new connection
        _client = await _create_client()
        return _client


async def close_db() -> None:
    """Close the database connection."""
    global _client
    async with _lock:
        if _client is not None:
            try:
                await _client.disconnect()
                logger.info("Database connection closed")
            except Exception as e:
                logger.warning(f"Error closing database connection: {e}")
            finally:
                _client = None
