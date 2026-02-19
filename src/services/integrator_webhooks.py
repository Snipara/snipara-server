"""Integrator webhook delivery service.

This module handles webhook event creation and delivery to integrator workspaces.
Events are queued in the database and delivered asynchronously.
"""

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime, timedelta

import httpx

from ..db import get_db

logger = logging.getLogger(__name__)

# Webhook event types
EVENT_CLIENT_CREATED = "client.created"
EVENT_CLIENT_UPDATED = "client.updated"
EVENT_CLIENT_DELETED = "client.deleted"
EVENT_API_KEY_CREATED = "api_key.created"
EVENT_API_KEY_REVOKED = "api_key.revoked"
EVENT_USAGE_LIMIT_WARNING = "usage.limit_warning"
EVENT_USAGE_LIMIT_EXCEEDED = "usage.limit_exceeded"


async def create_webhook_event(
    workspace_id: str,
    event_type: str,
    payload: dict,
) -> str | None:
    """
    Create a webhook event for delivery.

    Args:
        workspace_id: The integrator workspace ID
        event_type: Event type (e.g., "client.created")
        payload: Event payload data

    Returns:
        Event ID if created, None if workspace has no webhook URL
    """
    db = await get_db()

    # Get workspace to check webhook URL
    workspace = await db.integratorworkspace.find_first(
        where={"id": workspace_id}
    )

    if not workspace or not workspace.webhookUrl:
        logger.debug(f"No webhook URL for workspace {workspace_id}, skipping event")
        return None

    # Create the event
    event = await db.integratorwebhookevent.create(
        data={
            "workspaceId": workspace_id,
            "eventType": event_type,
            "payload": json.dumps(payload),
            "status": "PENDING",
            "attempts": 0,
        }
    )

    logger.info(f"Created webhook event {event.id} ({event_type}) for workspace {workspace_id}")

    # Trigger async delivery (fire and forget)
    asyncio.create_task(deliver_webhook_event(event.id))

    return event.id


def sign_webhook_payload(payload: str, secret: str) -> str:
    """
    Sign a webhook payload using HMAC-SHA256.

    Args:
        payload: JSON payload string
        secret: Webhook secret

    Returns:
        Signature in format "sha256=..."
    """
    signature = hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"


async def deliver_webhook_event(event_id: str, max_retries: int = 3) -> bool:
    """
    Deliver a webhook event to the integrator's endpoint.

    Args:
        event_id: The event ID to deliver
        max_retries: Maximum retry attempts

    Returns:
        True if delivered successfully, False otherwise
    """
    db = await get_db()

    event = await db.integratorwebhookevent.find_first(
        where={"id": event_id},
        include={"workspace": True},
    )

    if not event:
        logger.error(f"Webhook event {event_id} not found")
        return False

    workspace = event.workspace
    if not workspace or not workspace.webhookUrl:
        logger.warning(f"No webhook URL for event {event_id}")
        await db.integratorwebhookevent.update(
            where={"id": event_id},
            data={"status": "FAILED", "lastError": "No webhook URL configured"},
        )
        return False

    # Parse payload
    try:
        payload_data = json.loads(event.payload)
    except json.JSONDecodeError:
        payload_data = event.payload

    # Build webhook payload
    webhook_payload = {
        "event_id": event.id,
        "event_type": event.eventType,
        "workspace_id": workspace.id,
        "created_at": event.createdAt.isoformat(),
        "data": payload_data,
    }
    payload_json = json.dumps(webhook_payload)

    # Build headers
    headers = {
        "Content-Type": "application/json",
        "X-Snipara-Event": event.eventType,
        "X-Snipara-Delivery": event.id,
    }

    # Sign if secret is configured
    if workspace.webhookSecret:
        signature = sign_webhook_payload(payload_json, workspace.webhookSecret)
        headers["X-Snipara-Signature"] = signature

    # Attempt delivery
    attempt = event.attempts + 1

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                workspace.webhookUrl,
                content=payload_json,
                headers=headers,
            )

            if response.status_code >= 200 and response.status_code < 300:
                # Success
                await db.integratorwebhookevent.update(
                    where={"id": event_id},
                    data={
                        "status": "DELIVERED",
                        "attempts": attempt,
                        "deliveredAt": datetime.now(UTC),
                    },
                )
                logger.info(f"Webhook event {event_id} delivered successfully")
                return True
            else:
                # HTTP error
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                logger.warning(f"Webhook delivery failed for {event_id}: {error_msg}")

                if attempt >= max_retries:
                    await db.integratorwebhookevent.update(
                        where={"id": event_id},
                        data={
                            "status": "FAILED",
                            "attempts": attempt,
                            "lastError": error_msg,
                        },
                    )
                    return False
                else:
                    await db.integratorwebhookevent.update(
                        where={"id": event_id},
                        data={
                            "attempts": attempt,
                            "lastError": error_msg,
                        },
                    )
                    # Schedule retry with exponential backoff
                    delay = 2 ** attempt  # 2, 4, 8 seconds
                    await asyncio.sleep(delay)
                    return await deliver_webhook_event(event_id, max_retries)

    except httpx.TimeoutException:
        error_msg = "Request timeout"
        logger.warning(f"Webhook delivery timeout for {event_id}")
    except httpx.RequestError as e:
        error_msg = f"Request error: {str(e)}"
        logger.warning(f"Webhook delivery error for {event_id}: {e}")
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"Webhook delivery failed for {event_id}: {e}", exc_info=True)

    # Handle failure
    if attempt >= max_retries:
        await db.integratorwebhookevent.update(
            where={"id": event_id},
            data={
                "status": "FAILED",
                "attempts": attempt,
                "lastError": error_msg,
            },
        )
        return False
    else:
        await db.integratorwebhookevent.update(
            where={"id": event_id},
            data={
                "attempts": attempt,
                "lastError": error_msg,
            },
        )
        # Schedule retry with exponential backoff
        delay = 2 ** attempt
        await asyncio.sleep(delay)
        return await deliver_webhook_event(event_id, max_retries)


async def retry_failed_webhooks(max_age_hours: int = 24) -> int:
    """
    Retry failed webhook events that are less than max_age_hours old.

    This should be called periodically by a background job.

    Args:
        max_age_hours: Only retry events created within this many hours

    Returns:
        Number of events retried
    """
    db = await get_db()

    cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)

    failed_events = await db.integratorwebhookevent.find_many(
        where={
            "status": "PENDING",
            "createdAt": {"gte": cutoff},
            "attempts": {"lt": 3},
        },
        take=100,
    )

    retried = 0
    for event in failed_events:
        asyncio.create_task(deliver_webhook_event(event.id))
        retried += 1

    if retried > 0:
        logger.info(f"Scheduled {retried} failed webhooks for retry")

    return retried


# ============ CONVENIENCE FUNCTIONS ============


async def emit_client_created(workspace_id: str, client_data: dict) -> str | None:
    """Emit a client.created webhook event."""
    return await create_webhook_event(
        workspace_id,
        EVENT_CLIENT_CREATED,
        client_data,
    )


async def emit_client_updated(workspace_id: str, client_data: dict, changes: dict) -> str | None:
    """Emit a client.updated webhook event."""
    return await create_webhook_event(
        workspace_id,
        EVENT_CLIENT_UPDATED,
        {"client": client_data, "changes": changes},
    )


async def emit_client_deleted(workspace_id: str, client_id: str, client_email: str) -> str | None:
    """Emit a client.deleted webhook event."""
    return await create_webhook_event(
        workspace_id,
        EVENT_CLIENT_DELETED,
        {"client_id": client_id, "email": client_email},
    )


async def emit_api_key_created(
    workspace_id: str, client_id: str, key_name: str, key_prefix: str
) -> str | None:
    """Emit an api_key.created webhook event."""
    return await create_webhook_event(
        workspace_id,
        EVENT_API_KEY_CREATED,
        {"client_id": client_id, "key_name": key_name, "key_prefix": key_prefix},
    )


async def emit_api_key_revoked(
    workspace_id: str, client_id: str, key_id: str, key_name: str
) -> str | None:
    """Emit an api_key.revoked webhook event."""
    return await create_webhook_event(
        workspace_id,
        EVENT_API_KEY_REVOKED,
        {"client_id": client_id, "key_id": key_id, "key_name": key_name},
    )


async def emit_usage_limit_warning(
    workspace_id: str, client_id: str, current: int, limit: int, bundle: str
) -> str | None:
    """Emit a usage.limit_warning webhook event (80% threshold)."""
    return await create_webhook_event(
        workspace_id,
        EVENT_USAGE_LIMIT_WARNING,
        {
            "client_id": client_id,
            "current_usage": current,
            "limit": limit,
            "bundle": bundle,
            "percentage": round(current / limit * 100, 1) if limit > 0 else 0,
        },
    )


async def emit_usage_limit_exceeded(
    workspace_id: str, client_id: str, current: int, limit: int, bundle: str
) -> str | None:
    """Emit a usage.limit_exceeded webhook event."""
    return await create_webhook_event(
        workspace_id,
        EVENT_USAGE_LIMIT_EXCEEDED,
        {
            "client_id": client_id,
            "current_usage": current,
            "limit": limit,
            "bundle": bundle,
        },
    )
