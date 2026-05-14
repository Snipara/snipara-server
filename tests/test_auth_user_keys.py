"""Regression tests for personal and team MCP API key access."""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from types import ModuleType
from unittest.mock import AsyncMock

import pytest


@pytest.fixture(scope="module")
def auth_module():
    """Import the auth module from the local package context."""
    project_root = Path(__file__).resolve().parents[1]
    previous_cwd = Path.cwd()
    os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
    os.chdir(project_root)
    try:
        sys.modules.pop("src.auth", None)
        sys.modules.pop("src.models", None)

        prisma_module = ModuleType("prisma")
        prisma_module.Prisma = type("Prisma", (), {})
        sys.modules["prisma"] = prisma_module

        models_module = ModuleType("src.models")

        class Plan(str, Enum):
            FREE = "FREE"
            PRO = "PRO"
            TEAM = "TEAM"
            ENTERPRISE = "ENTERPRISE"

        models_module.Plan = Plan
        sys.modules["src.models"] = models_module

        module = importlib.import_module("src.auth")
        yield importlib.reload(module)
    finally:
        os.chdir(previous_cwd)


def _build_db(
    *,
    api_key_record=None,
    personal_access_project=None,
    team_key_record=None,
    integrator_client=None,
):
    """Create the minimal mocked DB shape needed by validate_api_key."""
    return SimpleNamespace(
        apikey=SimpleNamespace(
            find_first=AsyncMock(return_value=api_key_record),
            update=AsyncMock(),
        ),
        project=SimpleNamespace(find_first=AsyncMock(return_value=personal_access_project)),
        teamapikey=SimpleNamespace(
            find_first=AsyncMock(return_value=team_key_record),
            update=AsyncMock(),
        ),
        integratorclient=SimpleNamespace(find_first=AsyncMock(return_value=integrator_client)),
    )


def test_validate_api_key_rejects_personal_key_for_team_project(monkeypatch, auth_module):
    """Personal keys must not inherit access to team-scoped projects."""
    project = SimpleNamespace(id="proj_team", teamId="team_123")
    api_key_record = SimpleNamespace(
        id="key_123",
        name="Personal key",
        userId="user_123",
        projectId=None,
        project=None,
        revokedAt=None,
        expiresAt=None,
        accessLevel=None,
        scopes=["memory", "context"],
    )
    db = _build_db(api_key_record=api_key_record, personal_access_project=None)

    monkeypatch.setattr(auth_module, "get_db", AsyncMock(return_value=db))
    monkeypatch.setattr(auth_module, "get_project_with_team", AsyncMock(return_value=project))

    result = asyncio.run(auth_module.validate_api_key("secret", "proj_team"))

    assert result is None
    db.apikey.update.assert_not_awaited()

    lookup = db.project.find_first.await_args.kwargs
    assert lookup["where"] == {
        "id": "proj_team",
        "team": {
            "isPersonal": True,
            "members": {
                "some": {
                    "userId": "user_123",
                    "role": "OWNER",
                }
            },
        },
    }
    assert "select" not in lookup


def test_validate_api_key_accepts_personal_key_for_personal_project(monkeypatch, auth_module):
    """Personal keys should continue to work across the user's personal projects."""
    project = SimpleNamespace(
        id="proj_personal",
        teamId="team_personal",
        team=SimpleNamespace(isPersonal=True),
    )
    api_key_record = SimpleNamespace(
        id="key_123",
        name="Personal key",
        userId="user_123",
        projectId=None,
        project=None,
        revokedAt=None,
        expiresAt=None,
        accessLevel=None,
        scopes=["memory", "context", "memory"],
    )
    db = _build_db(
        api_key_record=api_key_record,
        personal_access_project=SimpleNamespace(id="proj_personal"),
    )

    monkeypatch.setattr(auth_module, "get_db", AsyncMock(return_value=db))
    monkeypatch.setattr(auth_module, "get_project_with_team", AsyncMock(return_value=project))
    derived_scopes = AsyncMock(return_value=["context"])
    monkeypatch.setattr(auth_module, "resolve_project_auth_scopes", derived_scopes)

    result = asyncio.run(auth_module.validate_api_key("secret", "proj_personal"))

    assert result is not None
    assert result["auth_type"] == "user_key"
    assert result["project_id"] == "proj_personal"
    assert result["project"] is project
    assert result["access_level"] == "ADMIN"
    assert result["access_denied"] is False
    assert result["scopes"] == ["context"]
    derived_scopes.assert_awaited_once_with("proj_personal", "user_123")
    db.apikey.update.assert_awaited_once()


def test_validate_api_key_derives_project_key_access_from_team_membership(
    monkeypatch, auth_module
):
    """Project keys should inherit effective rights from real team membership."""
    project = SimpleNamespace(
        id="proj_team",
        teamId="team_123",
        team=SimpleNamespace(isPersonal=False),
    )
    api_key_record = SimpleNamespace(
        id="key_123",
        name="Project key",
        userId="user_123",
        projectId="proj_team",
        project=project,
        revokedAt=None,
        expiresAt=None,
        accessLevel="VIEWER",
        scopes=["context"],
    )
    db = _build_db(api_key_record=api_key_record)

    monkeypatch.setattr(auth_module, "get_db", AsyncMock(return_value=db))
    monkeypatch.setattr(auth_module, "get_project_with_team", AsyncMock(return_value=project))
    membership_access = AsyncMock(return_value=("ADMIN", False))
    monkeypatch.setattr(auth_module, "check_team_key_project_access", membership_access)
    derived_scopes = AsyncMock(return_value=["context", "memory"])
    monkeypatch.setattr(auth_module, "resolve_project_auth_scopes", derived_scopes)

    result = asyncio.run(auth_module.validate_api_key("secret", "proj_team"))

    assert result is not None
    assert result["auth_type"] == "project_key"
    assert result["project_id"] == "proj_team"
    assert result["project"] is project
    assert result["access_level"] == "ADMIN"
    assert result["access_denied"] is False
    assert result["scopes"] == ["context", "memory"]
    membership_access.assert_awaited_once_with("user_123", "proj_team", "team_123")
    derived_scopes.assert_awaited_once_with("proj_team", "user_123")
    db.apikey.update.assert_awaited_once()


def test_validate_api_key_propagates_project_key_access_denial(
    monkeypatch, auth_module
):
    """Project keys should stop working when team membership denies the project."""
    project = SimpleNamespace(
        id="proj_team",
        teamId="team_123",
        team=SimpleNamespace(isPersonal=False),
    )
    api_key_record = SimpleNamespace(
        id="key_123",
        name="Project key",
        userId="user_123",
        projectId="proj_team",
        project=project,
        revokedAt=None,
        expiresAt=None,
        accessLevel="ADMIN",
        scopes=["context"],
    )
    db = _build_db(api_key_record=api_key_record)

    monkeypatch.setattr(auth_module, "get_db", AsyncMock(return_value=db))
    monkeypatch.setattr(auth_module, "get_project_with_team", AsyncMock(return_value=project))
    membership_access = AsyncMock(return_value=("NONE", True))
    monkeypatch.setattr(auth_module, "check_team_key_project_access", membership_access)
    derived_scopes = AsyncMock(return_value=["context"])
    monkeypatch.setattr(auth_module, "resolve_project_auth_scopes", derived_scopes)

    result = asyncio.run(auth_module.validate_api_key("secret", "proj_team"))

    assert result is not None
    assert result["auth_type"] == "project_key"
    assert result["access_level"] == "NONE"
    assert result["access_denied"] is True
    assert result["scopes"] == ["context"]
    membership_access.assert_awaited_once_with("user_123", "proj_team", "team_123")
    derived_scopes.assert_awaited_once_with("proj_team", "user_123")
    db.apikey.update.assert_awaited_once()


def test_validate_api_key_accepts_team_key_for_team_project(monkeypatch, auth_module):
    """Team keys remain the mechanism for accessing team-scoped projects."""
    project = SimpleNamespace(id="proj_team", teamId="team_123")
    team_key_record = SimpleNamespace(
        id="team_key_123",
        name="Team key",
        userId="user_123",
        teamId="team_123",
        revokedAt=None,
        expiresAt=None,
    )
    db = _build_db(team_key_record=team_key_record)

    monkeypatch.setattr(auth_module, "get_db", AsyncMock(return_value=db))
    monkeypatch.setattr(auth_module, "get_project_with_team", AsyncMock(return_value=project))
    monkeypatch.setattr(
        auth_module,
        "check_team_key_project_access",
        AsyncMock(return_value=("EDITOR", False)),
    )
    derived_scopes = AsyncMock(return_value=["context"])
    monkeypatch.setattr(auth_module, "resolve_project_auth_scopes", derived_scopes)

    result = asyncio.run(auth_module.validate_api_key("secret", "proj_team"))

    assert result is not None
    assert result["auth_type"] == "team_key"
    assert result["project_id"] == "proj_team"
    assert result["project"] is project
    assert result["access_level"] == "EDITOR"
    assert result["access_denied"] is False
    assert result["scopes"] == ["context"]
    derived_scopes.assert_awaited_once_with("proj_team", "user_123")
    db.teamapikey.update.assert_awaited_once()
