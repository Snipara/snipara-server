"""Security headers middleware.

Adds security headers to all HTTP responses using pure ASGI pattern.
"""

from uuid import uuid4

from ..config import settings


class SecurityHeadersMiddleware:
    """
    Add security headers to all responses.

    Uses pure ASGI middleware pattern instead of BaseHTTPMiddleware
    to avoid Content-Length mismatch issues with streaming responses.

    Headers added:
        - X-Request-Id: Unique request identifier for tracing
        - X-Content-Type-Options: nosniff
        - X-Frame-Options: DENY
        - X-XSS-Protection: 1; mode=block
        - Strict-Transport-Security: (production only)
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Generate request ID for tracing
        request_id = str(uuid4())

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                # Add security headers
                headers.append((b"x-request-id", request_id.encode()))
                headers.append((b"x-content-type-options", b"nosniff"))
                headers.append((b"x-frame-options", b"DENY"))
                headers.append((b"x-xss-protection", b"1; mode=block"))

                # Add HSTS in production (non-debug mode)
                if not settings.debug:
                    headers.append(
                        (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
                    )

                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)
