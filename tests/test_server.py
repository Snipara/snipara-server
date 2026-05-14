"""Tests for the MCP server endpoints."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.server import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_check(self, client):
        """Test /health endpoint returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "timestamp" in data

    def test_root_endpoint(self, client):
        """Test / endpoint returns API info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "RLM MCP Server"
        assert "version" in data
        assert data["docs"] == "/docs"

    def test_ready_requires_primary_embedding_when_preload_enabled(self, client, monkeypatch):
        """When eager preload is enabled, /ready should require the primary model."""
        from src import server
        from src.services.embeddings import EmbeddingsService, LIGHT_MODEL_NAME, MODEL_NAME

        db = AsyncMock()
        db.query_raw = AsyncMock(return_value=[{"ok": 1}])
        monkeypatch.setattr(server, "get_db", AsyncMock(return_value=db))
        monkeypatch.setattr(server.settings, "preload_embeddings", True)

        class FakeEmbeddingInstance:
            def __init__(self, loaded: bool):
                self._loaded = loaded

            def is_loaded(self) -> bool:
                return self._loaded

        def fake_get_instance(cls, model_name=MODEL_NAME):
            if model_name == LIGHT_MODEL_NAME:
                return FakeEmbeddingInstance(False)
            return FakeEmbeddingInstance(False)

        monkeypatch.setattr(EmbeddingsService, "get_instance", classmethod(fake_get_instance))

        response = client.get("/ready")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["embedding_preload_enabled"] is True
        assert data["checks"]["embedding_primary_loaded"] is False
        assert data["checks"]["embeddings_ready"] is False

    def test_ready_allows_lazy_embeddings_when_preload_disabled(self, client, monkeypatch):
        """When eager preload is disabled, /ready should pass once the DB is reachable."""
        from src import server
        from src.services.embeddings import EmbeddingsService, LIGHT_MODEL_NAME, MODEL_NAME

        db = AsyncMock()
        db.query_raw = AsyncMock(return_value=[{"ok": 1}])
        monkeypatch.setattr(server, "get_db", AsyncMock(return_value=db))
        monkeypatch.setattr(server.settings, "preload_embeddings", False)

        class FakeEmbeddingInstance:
            def __init__(self, loaded: bool):
                self._loaded = loaded

            def is_loaded(self) -> bool:
                return self._loaded

        def fake_get_instance(cls, model_name=MODEL_NAME):
            if model_name == LIGHT_MODEL_NAME:
                return FakeEmbeddingInstance(False)
            return FakeEmbeddingInstance(False)

        monkeypatch.setattr(EmbeddingsService, "get_instance", classmethod(fake_get_instance))

        response = client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["checks"]["embedding_preload_enabled"] is False
        assert data["checks"]["embedding_primary_loaded"] is False
        assert data["checks"]["embeddings_ready"] is True


class TestMCPEndpoints:
    """Tests for MCP tool endpoints."""

    def test_mcp_requires_api_key(self, client):
        """Test that MCP endpoint requires API key."""
        response = client.post(
            "/v1/test-project/mcp",
            json={"tool": "rlm_stats", "params": {}},
        )
        # Should fail with 422 (missing header) or 401 (invalid key)
        assert response.status_code in [401, 422]

    def test_mcp_invalid_api_key(self, client, mock_validate_api_key_invalid):
        """Test MCP endpoint with invalid API key."""
        response = client.post(
            "/v1/test-project/mcp",
            json={"tool": "rlm_stats", "params": {}},
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code == 401
        data = response.json()
        assert data["success"] is False
        assert "Invalid API key" in data["error"]

    def test_context_requires_api_key(self, client):
        """Test that context endpoint requires API key."""
        response = client.get("/v1/test-project/context")
        assert response.status_code in [401, 422]

    def test_limits_requires_api_key(self, client):
        """Test that limits endpoint requires API key."""
        response = client.get("/v1/test-project/limits")
        assert response.status_code in [401, 422]

    def test_mcp_accepts_bearer_authorization(self, client, monkeypatch):
        """Legacy /v1 MCP should accept Authorization: Bearer tokens."""
        from src import server

        seen: dict[str, str | None] = {"api_key": None}

        async def fake_validate_and_rate_limit(project_id, api_key, client_ip=None):
            seen["api_key"] = api_key
            return (
                {
                    "id": "oauth-token-id",
                    "user_id": "user-123",
                    "access_level": "EDITOR",
                    "auth_type": "oauth",
                },
                SimpleNamespace(id="resolved-project"),
                server.Plan.FREE,
                {},
            )

        async def fake_check_usage_limits(project_id, plan):
            return SimpleNamespace(exceeded=False, current=0, max=100)

        async def fake_track_usage(**kwargs):
            return None

        class FakeResult:
            data = {"ok": True}
            input_tokens = 1
            output_tokens = 2

        class FakeEngine:
            def __init__(self, *args, **kwargs):
                pass

            async def execute(self, tool, params):
                return FakeResult()

        monkeypatch.setattr(server, "validate_and_rate_limit", fake_validate_and_rate_limit)
        monkeypatch.setattr(server, "check_usage_limits", fake_check_usage_limits)
        monkeypatch.setattr(server, "track_usage", fake_track_usage)
        monkeypatch.setattr(server, "enforce_tool_scope", lambda *args, **kwargs: None)
        monkeypatch.setattr(server, "RLMEngine", FakeEngine)

        response = client.post(
            "/v1/test-project/mcp",
            json={"tool": "rlm_stats", "params": {}},
            headers={"Authorization": "Bearer snipara_at_test"},
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert seen["api_key"] == "snipara_at_test"

    def test_context_accepts_bearer_authorization(self, client, monkeypatch):
        """Legacy GET /v1 endpoints should also accept Authorization: Bearer tokens."""
        from src import server

        seen: dict[str, str | None] = {"api_key": None}

        async def fake_validate_and_rate_limit(project_id, api_key, client_ip=None):
            seen["api_key"] = api_key
            return (
                {
                    "id": "oauth-token-id",
                    "user_id": "user-123",
                    "access_level": "EDITOR",
                    "auth_type": "oauth",
                },
                SimpleNamespace(id="resolved-project"),
                server.Plan.FREE,
                {},
            )

        class FakeEngine:
            session_context = "remembered context"

            def __init__(self, *args, **kwargs):
                pass

            async def load_session_context(self):
                return None

        monkeypatch.setattr(server, "validate_and_rate_limit", fake_validate_and_rate_limit)
        monkeypatch.setattr(server, "RLMEngine", FakeEngine)

        response = client.get(
            "/v1/test-project/context",
            headers={"Authorization": "Bearer snipara_at_test"},
        )

        assert response.status_code == 200
        assert response.json()["has_context"] is True
        assert seen["api_key"] == "snipara_at_test"


class TestRequestValidation:
    """Tests for request validation."""

    def test_invalid_tool_name(self, client):
        """Test that invalid tool names are rejected."""
        response = client.post(
            "/v1/test-project/mcp",
            json={"tool": "invalid_tool", "params": {}},
            headers={"X-API-Key": "test-key"},
        )
        # Should fail validation (422) or auth (401)
        assert response.status_code in [401, 422]

    def test_missing_tool(self, client):
        """Test that missing tool field is rejected."""
        response = client.post(
            "/v1/test-project/mcp",
            json={"params": {}},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 422


class TestResponseFormat:
    """Tests for response format consistency."""

    def test_error_response_format(self, client, mock_validate_api_key_invalid):
        """Test that error responses have consistent format."""
        response = client.post(
            "/v1/test-project/mcp",
            json={"tool": "rlm_stats", "params": {}},
            headers={"X-API-Key": "invalid-key"},
        )
        data = response.json()

        # Check required fields in error response
        assert "success" in data
        assert data["success"] is False
        assert "error" in data
        assert "usage" in data
        assert "latency_ms" in data["usage"]
