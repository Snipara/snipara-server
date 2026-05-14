"""Tests for the Graphify-compatible code graph export."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from src.api import graphify as graphify_api
from src.server import app
from src.services.code_graph.graphify_export import build_graphify_payload


def _sample_node_rows():
    return [
        {
            "symbolKey": "python::src.rlm_engine::method::src.rlm_engine.RLMEngine._handle_context_query",
            "kind": "METHOD",
            "language": "python",
            "modulePath": "src.rlm_engine",
            "qualifiedName": "src.rlm_engine.RLMEngine._handle_context_query",
            "localName": "_handle_context_query",
            "startLine": 1872,
            "endLine": 2642,
            "signature": "(self, params: dict[str, Any]) -> ToolResult",
            "file_path": "src/rlm_engine.py",
        },
        {
            "symbolKey": "python::src.db::function::src.db.get_db",
            "kind": "FUNCTION",
            "language": "python",
            "modulePath": "src.db",
            "qualifiedName": "src.db.get_db",
            "localName": "get_db",
            "startLine": 10,
            "endLine": 20,
            "signature": "() -> Prisma",
            "file_path": "src/db.py",
        },
    ]


def _sample_edge_rows():
    return [
        {
            "kind": "CALLS",
            "source": "AST",
            "confidence": 1.0,
            "fromSymbolKey": "python::src.rlm_engine::method::src.rlm_engine.RLMEngine._handle_context_query",
            "fromQualifiedName": "src.rlm_engine.RLMEngine._handle_context_query",
            "toSymbolKey": "python::src.db::function::src.db.get_db",
            "toQualifiedName": "src.db.get_db",
        },
        {
            "kind": "REFERENCES",
            "source": "HEURISTIC",
            "confidence": 0.4,
            "fromSymbolKey": "python::src.rlm_engine::method::src.rlm_engine.RLMEngine._handle_context_query",
            "fromQualifiedName": "src.rlm_engine.RLMEngine._handle_context_query",
            "toSymbolKey": "python::src.db::function::src.db.get_db",
            "toQualifiedName": "src.db.get_db",
        },
    ]


def test_build_graphify_payload_uses_node_link_shape():
    payload = build_graphify_payload(
        project_id="proj_snipara_001",
        project_slug="snipara",
        project_name="Snipara",
        node_rows=_sample_node_rows(),
        edge_rows=_sample_edge_rows(),
        indexed_document_count=2,
        last_indexed_at=datetime(2026, 4, 23, 13, 0, tzinfo=UTC),
        directed=False,
    )

    assert payload["directed"] is False
    assert payload["multigraph"] is False
    assert payload["graph"]["schema"] == "graphify-node-link-v1-subset"
    assert payload["graph"]["indexed_document_count"] == 2
    assert payload["graph"]["languages"] == ["python"]
    assert payload["nodes"][0]["id"].startswith("python::src.rlm_engine")
    assert payload["nodes"][0]["norm_label"] == "src.rlm_engine.rlmengine._handle_context_query"
    assert payload["nodes"][0]["source_location"] == "L1872-L2642"
    assert payload["links"][0]["relation"] == "calls"
    assert payload["links"][0]["confidence"] == "EXTRACTED"
    assert payload["links"][1]["confidence"] == "AMBIGUOUS"


def test_build_graphify_payload_accepts_string_timestamp():
    payload = build_graphify_payload(
        project_id="proj_snipara_001",
        project_slug="snipara",
        project_name="Snipara",
        node_rows=_sample_node_rows(),
        edge_rows=_sample_edge_rows(),
        indexed_document_count=2,
        last_indexed_at="2026-04-23 13:00:00+00:00",
        directed=False,
    )

    assert payload["graph"]["last_indexed_at"] == "2026-04-23 13:00:00+00:00"


def test_graphify_export_endpoint_returns_payload(monkeypatch):
    async def fake_validate_and_rate_limit(project_id, api_key, client_ip=None):
        return (
            {"id": "key_123"},
            SimpleNamespace(id="proj_snipara_001", slug="snipara", name="Snipara"),
            None,
            {},
        )

    db = SimpleNamespace(
        query_raw=AsyncMock(
            side_effect=[
                _sample_node_rows(),
                _sample_edge_rows(),
                [
                    {
                        "indexed_document_count": 2,
                        "last_indexed_at": datetime(2026, 4, 23, 13, 0, tzinfo=UTC),
                    }
                ],
            ]
        )
    )

    monkeypatch.setattr(graphify_api, "validate_and_rate_limit", fake_validate_and_rate_limit)
    monkeypatch.setattr(graphify_api, "get_db", AsyncMock(return_value=db))

    client = TestClient(app)
    response = client.get(
        "/v1/snipara/graphify/graph.json",
        headers={"X-API-Key": "rlm_test"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["graph"]["project_slug"] == "snipara"
    assert data["graph"]["node_count"] == 2
    assert data["links"][0]["confidence"] == "EXTRACTED"


def test_graphify_export_endpoint_requires_indexed_graph(monkeypatch):
    async def fake_validate_and_rate_limit(project_id, api_key, client_ip=None):
        return (
            {"id": "key_123"},
            SimpleNamespace(id="proj_snipara_001", slug="snipara", name="Snipara"),
            None,
            {},
        )

    db = SimpleNamespace(
        query_raw=AsyncMock(
            side_effect=[
                [],
                [],
                [{"indexed_document_count": 0, "last_indexed_at": None}],
            ]
        )
    )

    monkeypatch.setattr(graphify_api, "validate_and_rate_limit", fake_validate_and_rate_limit)
    monkeypatch.setattr(graphify_api, "get_db", AsyncMock(return_value=db))

    client = TestClient(app)
    response = client.get(
        "/v1/snipara/graphify/graph.json",
        headers={"Authorization": "Bearer snipara_at_test"},
    )

    assert response.status_code == 409
    data = response.json()
    assert data["success"] is False
    assert "No indexed code graph is available" in data["error"]
