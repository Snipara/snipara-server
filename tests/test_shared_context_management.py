"""Tests for MCP shared-context management handlers."""

from types import SimpleNamespace

import pytest

from src.models import Plan
import src.services.shared_context as shared_context_service
from src.services.shared_context import link_shared_collection_to_project

try:
    from src.rlm_engine import RLMEngine

    PRISMA_AVAILABLE = True
except RuntimeError:
    PRISMA_AVAILABLE = False


@pytest.mark.skipif(not PRISMA_AVAILABLE, reason="Prisma client not generated")
class TestSharedContextManagementHandlers:
    """Verify shared-context admin handlers route the right inputs."""

    @pytest.mark.asyncio
    async def test_create_collection_uses_current_project_team(self, monkeypatch):
        engine = RLMEngine("proj_snipara_001", plan=Plan.TEAM, user_id="user_123")
        captured: dict = {}

        async def fake_get_db():
            async def find_unique(*, where):
                assert where == {"id": "proj_snipara_001"}
                return SimpleNamespace(teamId="team_456")

            return SimpleNamespace(project=SimpleNamespace(find_unique=find_unique))

        async def fake_create_shared_collection(**kwargs):
            captured.update(kwargs)
            return {"collection_id": "col_1", "name": kwargs["name"]}

        monkeypatch.setattr("src.rlm_engine.get_db", fake_get_db)
        monkeypatch.setattr("src.rlm_engine.create_shared_collection", fake_create_shared_collection)

        result = await engine._handle_create_collection(
            {"name": "Vutler Best Practices", "description": "Vutler-only standards"}
        )

        assert captured == {
            "user_id": "user_123",
            "team_id": "team_456",
            "name": "Vutler Best Practices",
            "slug": None,
            "description": "Vutler-only standards",
            "is_public": False,
        }
        assert result.data["collection_id"] == "col_1"

    @pytest.mark.asyncio
    async def test_get_collection_documents_forwards_include_content(self, monkeypatch):
        engine = RLMEngine("proj_snipara_001", plan=Plan.TEAM, user_id="user_123")
        captured: dict = {}

        async def fake_get_collection_documents(**kwargs):
            captured.update(kwargs)
            return {
                "collection": {"id": kwargs["collection_id"], "name": "Best Practices"},
                "documents": [],
            }

        monkeypatch.setattr(
            "src.rlm_engine.get_collection_documents", fake_get_collection_documents
        )

        result = await engine._handle_get_collection_documents(
            {"collection_id": "col_1", "include_content": False}
        )

        assert captured == {
            "collection_id": "col_1",
            "user_id": "user_123",
            "include_content": False,
        }
        assert result.data["collection"]["id"] == "col_1"

    @pytest.mark.asyncio
    async def test_link_and_unlink_collection_forward_target_project(self, monkeypatch):
        engine = RLMEngine("proj_snipara_001", plan=Plan.TEAM, user_id="user_123")
        link_calls: list[tuple[str, dict]] = []

        async def fake_link_shared_collection_to_project(**kwargs):
            link_calls.append(("link", kwargs))
            return {"action": "linked", "project_slug": "test-workspace-api-vutler"}

        async def fake_unlink_shared_collection_from_project(**kwargs):
            link_calls.append(("unlink", kwargs))
            return {"action": "unlinked", "project_slug": "test-workspace-api-vutler"}

        monkeypatch.setattr(
            "src.rlm_engine.link_shared_collection_to_project",
            fake_link_shared_collection_to_project,
        )
        monkeypatch.setattr(
            "src.rlm_engine.unlink_shared_collection_from_project",
            fake_unlink_shared_collection_from_project,
        )

        link_result = await engine._handle_link_collection(
            {
                "collection_id": "col_vutler",
                "project_id_or_slug": "test-workspace-api-vutler",
                "enabled_categories": ["BEST_PRACTICES"],
            }
        )
        unlink_result = await engine._handle_unlink_collection(
            {
                "collection_id": "col_mixed",
                "project_id_or_slug": "test-workspace-api-vutler",
            }
        )

        assert link_calls == [
            (
                "link",
                {
                    "collection_id": "col_vutler",
                    "project_id_or_slug": "test-workspace-api-vutler",
                    "user_id": "user_123",
                    "priority": None,
                    "token_budget_percent": None,
                    "enabled_categories": ["BEST_PRACTICES"],
                },
            ),
            (
                "unlink",
                {
                    "collection_id": "col_mixed",
                    "project_id_or_slug": "test-workspace-api-vutler",
                    "user_id": "user_123",
                },
            ),
        ]
        assert link_result.data["action"] == "linked"
        assert unlink_result.data["action"] == "unlinked"


@pytest.mark.asyncio
async def test_link_shared_collection_uses_find_first_priority_lookup(monkeypatch):
    captured: dict = {}

    async def fake_resolve_project(project_id_or_slug, user_id):
        assert project_id_or_slug == "snipara"
        assert user_id == "user_123"
        return SimpleNamespace(id="proj_1", slug="snipara")

    async def fake_resolve_collection(collection_id, user_id):
        assert collection_id == "col_1"
        assert user_id == "user_123"
        return SimpleNamespace(id="col_1", name="Snipara Best Practices")

    async def find_unique(*, where):
        assert where == {"projectId_collectionId": {"projectId": "proj_1", "collectionId": "col_1"}}
        return None

    async def find_first(*, where, order):
        assert where == {"projectId": "proj_1"}
        assert order == {"priority": "desc"}
        return SimpleNamespace(priority=4)

    async def update(*, where, data):
        captured["update"] = {"where": where, "data": data}
        return None

    async def create(*, data):
        captured["create"] = data
        return SimpleNamespace(id="link_1", priority=data["priority"])

    async def fake_get_db():
        return SimpleNamespace(
            projectsharedcontext=SimpleNamespace(
                find_unique=find_unique,
                find_first=find_first,
                create=create,
            ),
            sharedcontextcollection=SimpleNamespace(update=update),
        )

    monkeypatch.setattr(shared_context_service, "get_db", fake_get_db)
    monkeypatch.setattr(shared_context_service, "_resolve_accessible_project", fake_resolve_project)
    monkeypatch.setattr(shared_context_service, "_resolve_accessible_collection", fake_resolve_collection)

    result = await link_shared_collection_to_project(
        collection_id="col_1",
        project_id_or_slug="snipara",
        user_id="user_123",
    )

    assert captured["create"]["priority"] == 5
    assert result["action"] == "linked"
