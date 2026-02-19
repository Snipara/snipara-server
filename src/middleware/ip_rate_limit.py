"""IP-based rate limiting middleware.

Provides secondary rate limiting layer by client IP address.
"""

import json

from ..config import settings
from ..usage import check_ip_rate_limit


class IPRateLimitMiddleware:
    """
    Secondary rate limiting layer by client IP address.

    Applies to all HTTP requests before reaching endpoint handlers.
    Uses X-Forwarded-For header (behind reverse proxy) or direct client address.
    Skips health check endpoint to avoid blocking monitoring.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Skip health/readiness check endpoints
        path = scope.get("path", "")
        if path in ("/health", "/ready"):
            await self.app(scope, receive, send)
            return

        # Skip MCP and API endpoints - they have per-API-key rate limiting
        # This prevents multi-agent systems on same IP from blocking each other
        # /mcp/ = streamable HTTP transport, /v1/ = REST API (used by snipara-mcp client)
        if path.startswith("/mcp/") or path.startswith("/v1/"):
            await self.app(scope, receive, send)
            return

        # Extract client IP from X-Forwarded-For (behind proxy) or direct connection
        client_ip = None
        headers = dict(scope.get("headers", []))
        forwarded_for = headers.get(b"x-forwarded-for")
        if forwarded_for:
            # First IP in X-Forwarded-For is the original client
            client_ip = forwarded_for.decode().split(",")[0].strip()
        elif scope.get("client"):
            client_ip = scope["client"][0]

        if client_ip:
            rate_ok = await check_ip_rate_limit(client_ip)
            if not rate_ok:
                response_body = json.dumps(
                    {
                        "detail": f"IP rate limit exceeded: {settings.ip_rate_limit_requests} requests per minute"
                    }
                ).encode()
                await send(
                    {
                        "type": "http.response.start",
                        "status": 429,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(response_body)).encode()),
                        ],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": response_body,
                    }
                )
                return

        await self.app(scope, receive, send)
