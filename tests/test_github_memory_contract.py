"""Tests for GitHub-native memory compiler contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models import (
    AgentMemoryScope,
    AgentMemoryType,
    CompiledContextItem,
    ContextCompileRequest,
    ContextCompileResponse,
    ContextSourceType,
    GitHubArtifactType,
    GitHubMemoryCandidate,
    GitHubSourceRef,
    MemoryCandidateRisk,
)


def test_github_source_ref_builds_stable_evidence_key() -> None:
    source = GitHubSourceRef(
        owner="Snipara",
        repo="snipara-server",
        artifact_type=GitHubArtifactType.PULL_REQUEST,
        external_id="42",
        url="https://github.com/Snipara/snipara-server/pull/42",
        title="Add memory compiler",
        state="merged",
    )

    assert source.repository == "Snipara/snipara-server"
    assert source.stable_key == "github:Snipara/snipara-server:pull_request:42"


def test_github_source_ref_rejects_secret_metadata() -> None:
    with pytest.raises(ValidationError, match="secret-like key"):
        GitHubSourceRef(
            owner="Snipara",
            repo="snipara-server",
            artifact_type=GitHubArtifactType.WORKFLOW_RUN,
            external_id="123",
            url="https://api.github.com/repos/Snipara/snipara-server/actions/runs/123",
            metadata={"headers": {"authorization": "Bearer example"}},
        )


def test_github_source_ref_validates_line_ranges() -> None:
    with pytest.raises(ValidationError, match="line_end"):
        GitHubSourceRef(
            owner="Snipara",
            repo="snipara-server",
            artifact_type=GitHubArtifactType.FILE,
            external_id="docs/AGENTS.md",
            url="https://github.com/Snipara/snipara-server/blob/main/AGENTS.md",
            path="AGENTS.md",
            line_start=30,
            line_end=10,
        )


def test_memory_candidate_with_risk_cannot_auto_approve() -> None:
    source = GitHubSourceRef(
        owner="Snipara",
        repo="snipara-server",
        artifact_type=GitHubArtifactType.REVIEW_COMMENT,
        external_id="987",
        url="https://github.com/Snipara/snipara-server/pull/42#discussion_r987",
    )

    candidate = GitHubMemoryCandidate(
        content="Prefer remote MCP for Codex project memory workflow.",
        memory_type=AgentMemoryType.PREFERENCE,
        scope=AgentMemoryScope.PROJECT,
        evidence=[source],
        risk_flags=[MemoryCandidateRisk.LOW_EVIDENCE],
        auto_approve=True,
    )

    assert candidate.auto_approve is False
    assert candidate.evidence_keys == ["github:Snipara/snipara-server:review_comment:987"]


def test_team_memory_candidate_requires_review() -> None:
    source = GitHubSourceRef(
        owner="Snipara",
        repo="snipara-server",
        artifact_type=GitHubArtifactType.ISSUE,
        external_id="12",
        url="https://github.com/Snipara/snipara-server/issues/12",
    )

    candidate = GitHubMemoryCandidate(
        content="Team policy memory candidates need review before persistence.",
        memory_type=AgentMemoryType.DECISION,
        scope=AgentMemoryScope.TEAM,
        evidence=[source],
        auto_approve=True,
    )

    assert candidate.auto_approve is False


def test_context_compile_response_enforces_token_budget() -> None:
    request = ContextCompileRequest(
        task_intent="Fix workflow regression in planner",
        token_budget=1200,
        repository="Snipara/snipara-server",
        branch="dev",
    )
    item = CompiledContextItem(
        source_type=ContextSourceType.PROJECT_RULE,
        content="Always use remote MCP before local search.",
        priority=0,
        token_count=100,
        confidence=1.0,
    )

    response = ContextCompileResponse(
        bundle_id="bundle-dev-workflow",
        request=request,
        items=[item],
        max_tokens=request.token_budget,
        confidence_summary={"project_rule": 1.0},
    )

    assert response.total_tokens == 100
    assert response.items[0].source_type is ContextSourceType.PROJECT_RULE


def test_context_compile_response_rejects_budget_overflow() -> None:
    request = ContextCompileRequest(task_intent="Compile too much context", token_budget=500)

    with pytest.raises(ValidationError, match="exceeds max_tokens"):
        ContextCompileResponse(
            bundle_id="overflow",
            request=request,
            items=[
                CompiledContextItem(
                    source_type=ContextSourceType.GITHUB,
                    source_ref="github:Snipara/snipara-server:file:README.md",
                    token_count=501,
                )
            ],
            max_tokens=request.token_budget,
        )
