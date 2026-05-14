"""Tests for the middleware module.

These tests verify the security middleware components work correctly.
"""

import pytest

from src.middleware import IPRateLimitMiddleware, SecurityHeadersMiddleware


class TestSecurityHeadersMiddleware:
    """Tests for SecurityHeadersMiddleware."""

    def test_init(self):
        """Test middleware initialization."""
        mock_app = object()
        middleware = SecurityHeadersMiddleware(mock_app)
        assert middleware.app is mock_app

    def test_is_class(self):
        """Test SecurityHeadersMiddleware is a class."""
        assert isinstance(SecurityHeadersMiddleware, type)

    def test_has_call_method(self):
        """Test middleware has async __call__ method."""
        assert hasattr(SecurityHeadersMiddleware, "__call__")
        import inspect

        assert inspect.iscoroutinefunction(SecurityHeadersMiddleware.__call__)


class TestIPRateLimitMiddleware:
    """Tests for IPRateLimitMiddleware."""

    def test_init(self):
        """Test middleware initialization."""
        mock_app = object()
        middleware = IPRateLimitMiddleware(mock_app)
        assert middleware.app is mock_app

    def test_is_class(self):
        """Test IPRateLimitMiddleware is a class."""
        assert isinstance(IPRateLimitMiddleware, type)

    def test_has_call_method(self):
        """Test middleware has async __call__ method."""
        assert hasattr(IPRateLimitMiddleware, "__call__")
        import inspect

        assert inspect.iscoroutinefunction(IPRateLimitMiddleware.__call__)

    @pytest.mark.asyncio
    async def test_skips_mcp_endpoints(self):
        """Test that /mcp/ endpoints skip IP rate limiting."""
        for path in ["/mcp", "/mcp/test-project"]:
            app_called = False

            async def mock_app(scope, receive, send):
                nonlocal app_called
                app_called = True

            middleware = IPRateLimitMiddleware(mock_app)

            scope = {"type": "http", "path": path}
            await middleware(scope, None, None)
            assert app_called, f"{path} endpoint should skip rate limiting"

    @pytest.mark.asyncio
    async def test_skips_v1_api_endpoints(self):
        """Test that /v1/ API endpoints skip IP rate limiting.

        This is critical because snipara-mcp client uses /v1/{project}/mcp
        endpoints, and these already have per-API-key rate limiting.
        """
        for path in ["/v1", "/v1/test-project/mcp"]:
            app_called = False

            async def mock_app(scope, receive, send):
                nonlocal app_called
                app_called = True

            middleware = IPRateLimitMiddleware(mock_app)

            scope = {"type": "http", "path": path}
            await middleware(scope, None, None)
            assert app_called, f"{path} endpoint should skip rate limiting"

    @pytest.mark.asyncio
    async def test_skips_health_endpoints(self):
        """Test that health endpoints skip IP rate limiting."""
        for path in ["/health", "/ready"]:
            app_called = False

            async def mock_app(scope, receive, send):
                nonlocal app_called
                app_called = True

            middleware = IPRateLimitMiddleware(mock_app)
            scope = {"type": "http", "path": path}
            await middleware(scope, None, None)
            assert app_called, f"{path} endpoint should skip rate limiting"

    @pytest.mark.asyncio
    async def test_skips_public_metadata_endpoints(self):
        """Test browser metadata endpoints skip IP rate limiting."""
        for path in ["/", "/favicon.ico", "/docs", "/redoc", "/openapi.json"]:
            app_called = False

            async def mock_app(scope, receive, send):
                nonlocal app_called
                app_called = True

            middleware = IPRateLimitMiddleware(mock_app)
            scope = {"type": "http", "path": path}
            await middleware(scope, None, None)
            assert app_called, f"{path} endpoint should skip rate limiting"


class TestMiddlewareModule:
    """Tests for the middleware module structure."""

    def test_exports_security_headers(self):
        """Test SecurityHeadersMiddleware is exported."""
        from src.middleware import SecurityHeadersMiddleware

        assert SecurityHeadersMiddleware is not None

    def test_exports_ip_rate_limit(self):
        """Test IPRateLimitMiddleware is exported."""
        from src.middleware import IPRateLimitMiddleware

        assert IPRateLimitMiddleware is not None

    def test_all_exports(self):
        """Test __all__ contains expected exports."""
        from src import middleware

        assert "SecurityHeadersMiddleware" in middleware.__all__
        assert "IPRateLimitMiddleware" in middleware.__all__
