"""Tests for the fixture-first GitHub memory importer."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from src.models import (
    AgentMemoryScope,
    AgentMemoryType,
    CompiledContextItem,
    ContextCompileRequest,
    ContextSourceType,
    EvidenceType,
    GitHubArtifactType,
    GitHubMemoryReviewAction,
    MemoryCandidateRisk,
    MemorySource,
    MemoryStatus,
)
from src.services.github_memory_importer import (
    build_github_memory_promotion_plan,
    build_github_memory_review_items,
    build_github_source_refs,
    compile_github_memory_context,
    extract_github_memory_candidates,
)

FIXTURE = Path(__file__).parent / "fixtures" / "github_memory" / "repo_snapshot.json"


def _load_snapshot() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _snapshot_with_secret_pull_request() -> dict:
    snapshot = deepcopy(_load_snapshot())
    snapshot["pull_requests"].append(
        {
            "number": 44,
            "title": "Secret-bearing decision",
            "state": "closed",
            "merged": True,
            "head_branch": "dev",
            "merge_commit_sha": "abc444",
            "html_url": "https://github.com/Snipara/snipara-server/pull/44",
            "updated_at": "2026-05-06T22:00:00Z",
            "body": "Decision: Store bearer sk_live_secret in the test config.",
        }
    )
    return snapshot


def test_build_source_refs_covers_supported_github_artifacts() -> None:
    refs = build_github_source_refs(_load_snapshot())
    artifact_types = {ref.artifact_type for ref in refs}

    assert GitHubArtifactType.REPOSITORY in artifact_types
    assert GitHubArtifactType.REPOSITORY_RULE in artifact_types
    assert GitHubArtifactType.TREE in artifact_types
    assert GitHubArtifactType.FILE in artifact_types
    assert GitHubArtifactType.ISSUE in artifact_types
    assert GitHubArtifactType.PULL_REQUEST in artifact_types
    assert GitHubArtifactType.REVIEW_COMMENT in artifact_types
    assert GitHubArtifactType.COMMIT in artifact_types
    assert GitHubArtifactType.WORKFLOW_RUN in artifact_types
    assert GitHubArtifactType.WORKFLOW_JOB in artifact_types
    assert GitHubArtifactType.CHECK_RUN in artifact_types
    assert GitHubArtifactType.RELEASE in artifact_types


def test_build_source_refs_are_idempotent_and_do_not_copy_secret_metadata() -> None:
    snapshot = _load_snapshot()
    first_keys = [ref.stable_key for ref in build_github_source_refs(snapshot)]
    second_keys = [ref.stable_key for ref in build_github_source_refs(snapshot)]

    assert first_keys == second_keys
    assert len(first_keys) == len(set(first_keys))
    assert all("token" not in ref.metadata for ref in build_github_source_refs(snapshot))


def test_extract_candidates_from_merged_pr_review_feedback_and_failed_ci() -> None:
    candidates = extract_github_memory_candidates(_load_snapshot())

    assert [candidate.memory_type for candidate in candidates] == [
        AgentMemoryType.DECISION,
        AgentMemoryType.DECISION,
        AgentMemoryType.LEARNING,
        AgentMemoryType.LEARNING,
    ]
    assert candidates[0].auto_approve is False
    assert candidates[0].category == "github-pr-decision"
    assert "GitHub PR #42" in candidates[0].content
    assert candidates[1].category == "github-repository-rule"
    assert candidates[2].auto_approve is False
    assert MemoryCandidateRisk.LOW_EVIDENCE in candidates[2].risk_flags
    assert candidates[3].category == "github-ci-failure"


def test_extract_candidates_uses_stable_evidence_keys() -> None:
    candidates = extract_github_memory_candidates(_load_snapshot())

    assert candidates[0].evidence_keys == ["github:Snipara/snipara-server:pull_request:42"]
    assert candidates[1].evidence_keys == [
        "github:Snipara/snipara-server:repository_rule:ruleset-1"
    ]
    assert candidates[2].evidence_keys == [
        "github:Snipara/snipara-server:review_comment:987:apps/mcp-server/src/models/github_memory.py:21-21"
    ]
    assert candidates[3].evidence_keys == ["github:Snipara/snipara-server:workflow_run:555"]


def test_review_items_are_review_first_by_default() -> None:
    items = build_github_memory_review_items(_load_snapshot())

    assert [item.policy.action for item in items] == [
        GitHubMemoryReviewAction.QUEUE,
        GitHubMemoryReviewAction.QUEUE,
        GitHubMemoryReviewAction.QUEUE,
        GitHubMemoryReviewAction.QUEUE,
    ]
    assert "review_first_default" in items[0].policy.reasons
    assert "low_evidence" in items[2].policy.reasons
    assert [item.review_id for item in items] == [
        item.review_id for item in build_github_memory_review_items(_load_snapshot())
    ]


def test_secret_like_github_text_is_rejected_without_copying_secret() -> None:
    items = build_github_memory_review_items(_snapshot_with_secret_pull_request())
    secret_item = next(item for item in items if item.candidate.category == "github-secret-review")

    assert secret_item.policy.action is GitHubMemoryReviewAction.REJECT
    assert "secret_like" in secret_item.policy.reasons
    assert MemoryCandidateRisk.SECRET_LIKE in secret_item.candidate.risk_flags
    assert "sk_live_secret" not in secret_item.candidate.content
    assert secret_item.evidence_keys == ["github:Snipara/snipara-server:pull_request:44"]


def test_promotion_plan_requires_reviewer_for_queued_candidates() -> None:
    pr_item = next(
        item
        for item in build_github_memory_review_items(_load_snapshot())
        if item.candidate.category == "github-pr-decision"
    )

    with pytest.raises(ValueError, match="require reviewed_by"):
        build_github_memory_promotion_plan(pr_item, project_id="proj_1")


def test_promotion_plan_builds_memory_v2_payload_with_github_evidence() -> None:
    pr_item = next(
        item
        for item in build_github_memory_review_items(_load_snapshot())
        if item.candidate.category == "github-pr-decision"
    )

    plan = build_github_memory_promotion_plan(
        pr_item,
        project_id="proj_1",
        reviewed_by="user_1",
    )

    assert plan.review_id == pr_item.review_id
    assert plan.policy.action is GitHubMemoryReviewAction.QUEUE
    assert plan.memory.project_id == "proj_1"
    assert plan.memory.scope is AgentMemoryScope.PROJECT
    assert plan.memory.source is MemorySource.WEBHOOK
    assert plan.memory.status is MemoryStatus.ACTIVE
    assert plan.memory.created_by == "github-memory-compiler"
    assert plan.memory.reviewed_by == "user_1"
    assert plan.memory.stale_at is not None
    assert plan.memory.content == pr_item.candidate.content
    assert plan.memory.evidence_score > 0
    assert [evidence.evidence_type for evidence in plan.evidence] == [EvidenceType.PR]
    assert plan.evidence[0].external_ref == "https://github.com/Snipara/snipara-server/pull/42"
    assert plan.evidence[0].snippet == "github:Snipara/snipara-server:pull_request:42"


def test_promotion_plan_requires_owner_id_for_target_scope() -> None:
    pr_item = next(
        item
        for item in build_github_memory_review_items(_load_snapshot())
        if item.candidate.category == "github-pr-decision"
    )
    team_item = pr_item.model_copy(
        update={"candidate": pr_item.candidate.model_copy(update={"scope": AgentMemoryScope.TEAM})}
    )

    with pytest.raises(ValueError, match="team_id"):
        build_github_memory_promotion_plan(team_item, reviewed_by="user_1")


def test_rejected_secret_candidate_cannot_promote() -> None:
    secret_item = next(
        item
        for item in build_github_memory_review_items(_snapshot_with_secret_pull_request())
        if item.candidate.category == "github-secret-review"
    )

    with pytest.raises(ValueError, match="cannot be promoted"):
        build_github_memory_promotion_plan(
            secret_item,
            project_id="proj_1",
            reviewed_by="user_1",
        )


def test_context_compiler_packs_reviewable_github_items_under_budget() -> None:
    request = ContextCompileRequest(
        task_intent="Prepare an agent to review GitHub memory candidates",
        token_budget=700,
        repository="Snipara/snipara-server",
        branch="dev",
    )

    response = compile_github_memory_context(
        request,
        build_github_memory_review_items(_load_snapshot()),
    )
    second_response = compile_github_memory_context(
        request,
        build_github_memory_review_items(_load_snapshot()),
    )

    assert response.bundle_id == second_response.bundle_id
    assert response.max_tokens == request.token_budget
    assert response.total_tokens <= request.token_budget
    assert response.items
    assert all(item.source_type is ContextSourceType.GITHUB for item in response.items)
    assert any("Decision from GitHub PR #42" in (item.content or "") for item in response.items)
    assert response.confidence_summary["github"] > 0


def test_context_compiler_omits_rejected_candidates_without_copying_secret() -> None:
    request = ContextCompileRequest(
        task_intent="Prepare GitHub memory review queue",
        token_budget=700,
        repository="Snipara/snipara-server",
    )

    response = compile_github_memory_context(
        request,
        build_github_memory_review_items(_snapshot_with_secret_pull_request()),
    )

    assert any(item.omitted_reason == "policy_rejected" for item in response.omitted_refs)
    serialized = response.model_dump_json()
    assert "sk_live_secret" not in serialized


def test_context_compiler_respects_budget_and_keeps_omitted_refs() -> None:
    request = ContextCompileRequest(
        task_intent="Pack project rules before GitHub candidates",
        token_budget=500,
        repository="Snipara/snipara-server",
    )
    project_rule = CompiledContextItem(
        source_type=ContextSourceType.PROJECT_RULE,
        content="Always use remote MCP before local search.",
        priority=0,
        token_count=490,
        confidence=1.0,
    )

    response = compile_github_memory_context(
        request,
        build_github_memory_review_items(_load_snapshot()),
        extra_items=[project_rule],
    )

    assert response.items[0].source_type is ContextSourceType.PROJECT_RULE
    assert response.total_tokens <= request.token_budget
    assert any(item.omitted_reason == "token_budget_exceeded" for item in response.omitted_refs)


def test_context_compiler_marks_branch_mismatch_warnings() -> None:
    request = ContextCompileRequest(
        task_intent="Review release branch context",
        token_budget=700,
        repository="Snipara/snipara-server",
        branch="release",
    )

    response = compile_github_memory_context(
        request,
        build_github_memory_review_items(_load_snapshot()),
    )

    assert response.staleness_warnings
    assert any(item.stale for item in response.items)
