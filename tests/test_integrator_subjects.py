import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")

from src.services.integrator_subjects import (
    build_integrator_subject_user_id,
    memory_call_uses_user_scope,
    resolve_integrator_memory_user_id,
)


def test_integrator_subject_user_id_is_namespaced_and_hashed():
    first = build_integrator_subject_user_id("client_a", "user-123")
    second = build_integrator_subject_user_id("client_b", "user-123")

    assert first.startswith("integrator:client_a:user:")
    assert "user-123" not in first
    assert first != second


def test_scope_user_memory_call_requires_integrator_external_user():
    assert memory_call_uses_user_scope("rlm_remember", {"scope": "user"}) is True
    assert memory_call_uses_user_scope("rlm_remember", {"scope": "project"}) is False
    assert (
        memory_call_uses_user_scope(
            "rlm_remember_bulk",
            {"memories": [{"text": "x", "scope": "project"}, {"text": "y", "scope": "user"}]},
        )
        is True
    )


def test_integrator_memory_user_id_uses_external_subject_only_for_memory_tools():
    auth_info = {"auth_type": "integrator_client", "client_id": "client_a"}

    assert (
        resolve_integrator_memory_user_id(
            auth_info=auth_info,
            default_user_id="owner_user",
            tool_name="rlm_context_query",
            arguments={"external_user_id": "end_user"},
        )
        == "owner_user"
    )
    assert (
        resolve_integrator_memory_user_id(
            auth_info=auth_info,
            default_user_id="owner_user",
            tool_name="rlm_recall",
            arguments={},
        )
        is None
    )
    assert resolve_integrator_memory_user_id(
        auth_info=auth_info,
        default_user_id="owner_user",
        tool_name="rlm_recall",
        arguments={"external_user_id": "end_user"},
    ).startswith("integrator:client_a:user:")


def test_integrator_subject_rejects_invalid_external_user_id():
    with pytest.raises(ValueError):
        build_integrator_subject_user_id("client_a", "")

    with pytest.raises(ValueError):
        resolve_integrator_memory_user_id(
            auth_info={"auth_type": "integrator_client", "client_id": "client_a"},
            default_user_id="owner_user",
            tool_name="rlm_recall",
            arguments={"external_user_id": 123},
        )
