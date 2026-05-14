"""Fixture-first GitHub importer for the memory compiler MVP."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from src.models.enums import (
    AgentMemoryScope,
    AgentMemoryType,
    EvidenceType,
    MemorySource,
    MemoryStatus,
)
from src.models.github_memory import (
    CompiledContextItem,
    ContextCompileRequest,
    ContextCompileResponse,
    ContextSourceType,
    GitHubArtifactType,
    GitHubMemoryCandidate,
    GitHubMemoryPolicyResult,
    GitHubMemoryPromotionPlan,
    GitHubMemoryReviewAction,
    GitHubMemoryReviewItem,
    GitHubSourceRef,
    MemoryCandidateRisk,
)
from src.models.memory_v2 import MemoryCreatePayload, MemoryEvidencePayload

DECISION_LINE_PATTERN = re.compile(
    r"^\s*(?:decision|decided|rationale)\s*:\s*(?P<value>.+)$",
    re.IGNORECASE | re.MULTILINE,
)
PREFERENCE_PATTERN = re.compile(
    r"\b(always|prefer|must|should|never|do not|don't)\b",
    re.IGNORECASE,
)
SECRET_TEXT_PATTERN = re.compile(
    r"\b(api[_-]?key|authorization|bearer\s+[a-z0-9._-]+|password|private[_-]?key|secret|token)\b",
    re.IGNORECASE,
)
POLICY_VERSION = "github-memory-policy/v1"


def build_github_source_refs(snapshot: dict[str, Any]) -> list[GitHubSourceRef]:
    """Build stable GitHub source refs from an already-authorized snapshot."""
    owner, repo = _repo_owner_name(snapshot)
    repository_url = _repository_url(snapshot, owner, repo)
    branch = _repository_branch(snapshot)

    refs = [
        GitHubSourceRef(
            owner=owner,
            repo=repo,
            artifact_type=GitHubArtifactType.REPOSITORY,
            external_id=f"{owner}/{repo}",
            url=repository_url,
            title=snapshot.get("repository", {}).get("name") or repo,
            branch=branch,
            metadata={"default_branch": branch},
        )
    ]

    for rule in snapshot.get("repository_rules") or []:
        rule_id = _required_str(rule, "id")
        refs.append(
            GitHubSourceRef(
                owner=owner,
                repo=repo,
                artifact_type=GitHubArtifactType.REPOSITORY_RULE,
                external_id=rule_id,
                url=rule.get("html_url") or repository_url,
                title=rule.get("name") or rule_id,
                branch=rule.get("branch") or branch,
                state=rule.get("enforcement"),
                updated_at=rule.get("updated_at"),
                metadata=_compact_metadata(rule, ["target", "source_type", "rules_count"]),
            )
        )

    for tree_item in snapshot.get("tree") or []:
        path = _required_str(tree_item, "path")
        refs.append(
            GitHubSourceRef(
                owner=owner,
                repo=repo,
                artifact_type=GitHubArtifactType.TREE,
                external_id=path,
                url=tree_item.get("html_url")
                or f"https://github.com/{owner}/{repo}/tree/{branch}/{path}",
                title=path,
                branch=tree_item.get("branch") or branch,
                sha=tree_item.get("sha"),
                path=path,
                metadata=_compact_metadata(tree_item, ["type", "size"]),
            )
        )

    for file_item in snapshot.get("files") or []:
        path = _required_str(file_item, "path")
        refs.append(
            GitHubSourceRef(
                owner=owner,
                repo=repo,
                artifact_type=GitHubArtifactType.FILE,
                external_id=path,
                url=file_item.get("html_url")
                or f"https://github.com/{owner}/{repo}/blob/{branch}/{path}",
                title=path,
                branch=file_item.get("branch") or branch,
                sha=file_item.get("sha"),
                path=path,
                metadata=_compact_metadata(file_item, ["size", "kind", "language"]),
            )
        )

    for issue in snapshot.get("issues") or []:
        number = _required_str(issue, "number")
        refs.append(
            GitHubSourceRef(
                owner=owner,
                repo=repo,
                artifact_type=GitHubArtifactType.ISSUE,
                external_id=number,
                url=issue.get("html_url") or f"https://github.com/{owner}/{repo}/issues/{number}",
                title=issue.get("title"),
                state=issue.get("state"),
                updated_at=issue.get("updated_at"),
            )
        )

    for pull_request in snapshot.get("pull_requests") or []:
        number = _required_str(pull_request, "number")
        refs.append(
            GitHubSourceRef(
                owner=owner,
                repo=repo,
                artifact_type=GitHubArtifactType.PULL_REQUEST,
                external_id=number,
                url=pull_request.get("html_url")
                or f"https://github.com/{owner}/{repo}/pull/{number}",
                title=pull_request.get("title"),
                state=_pull_request_state(pull_request),
                branch=pull_request.get("head_branch"),
                sha=pull_request.get("merge_commit_sha") or pull_request.get("head_sha"),
                updated_at=pull_request.get("updated_at"),
            )
        )

    for comment in snapshot.get("review_comments") or []:
        comment_id = _required_str(comment, "id")
        path = comment.get("path")
        line = _optional_int(comment.get("line") or comment.get("original_line"))
        refs.append(
            GitHubSourceRef(
                owner=owner,
                repo=repo,
                artifact_type=GitHubArtifactType.REVIEW_COMMENT,
                external_id=comment_id,
                url=comment.get("html_url")
                or f"https://github.com/{owner}/{repo}/pull/{comment.get('pull_request_number', '')}",
                title=comment.get("subject") or path,
                branch=comment.get("branch") or branch,
                sha=comment.get("commit_id"),
                path=path,
                line_start=line,
                line_end=line,
                updated_at=comment.get("updated_at"),
            )
        )

    for commit in snapshot.get("commits") or []:
        sha = _required_str(commit, "sha")
        refs.append(
            GitHubSourceRef(
                owner=owner,
                repo=repo,
                artifact_type=GitHubArtifactType.COMMIT,
                external_id=sha,
                url=commit.get("html_url") or f"https://github.com/{owner}/{repo}/commit/{sha}",
                title=_first_line(commit.get("message")),
                sha=sha,
                branch=commit.get("branch") or branch,
                updated_at=commit.get("committed_at"),
            )
        )

    for run in snapshot.get("workflow_runs") or []:
        run_id = _required_str(run, "id")
        refs.append(
            GitHubSourceRef(
                owner=owner,
                repo=repo,
                artifact_type=GitHubArtifactType.WORKFLOW_RUN,
                external_id=run_id,
                url=run.get("html_url")
                or f"https://github.com/{owner}/{repo}/actions/runs/{run_id}",
                title=run.get("name"),
                branch=run.get("branch") or branch,
                sha=run.get("head_sha"),
                state=run.get("conclusion") or run.get("status"),
                updated_at=run.get("updated_at"),
                metadata=_compact_metadata(run, ["status", "conclusion", "event"]),
            )
        )

    for job in snapshot.get("workflow_jobs") or []:
        job_id = _required_str(job, "id")
        run_id = job.get("run_id")
        refs.append(
            GitHubSourceRef(
                owner=owner,
                repo=repo,
                artifact_type=GitHubArtifactType.WORKFLOW_JOB,
                external_id=job_id,
                url=job.get("html_url")
                or f"https://github.com/{owner}/{repo}/actions/runs/{run_id}/job/{job_id}",
                title=job.get("name"),
                branch=job.get("branch") or branch,
                sha=job.get("head_sha"),
                state=job.get("conclusion") or job.get("status"),
                updated_at=job.get("completed_at") or job.get("updated_at"),
                metadata=_compact_metadata(job, ["run_id", "status", "conclusion"]),
            )
        )

    for check in snapshot.get("check_runs") or []:
        check_id = _required_str(check, "id")
        refs.append(
            GitHubSourceRef(
                owner=owner,
                repo=repo,
                artifact_type=GitHubArtifactType.CHECK_RUN,
                external_id=check_id,
                url=check.get("html_url") or f"https://github.com/{owner}/{repo}/runs/{check_id}",
                title=check.get("name"),
                branch=check.get("branch") or branch,
                sha=check.get("head_sha"),
                state=check.get("conclusion") or check.get("status"),
                updated_at=check.get("completed_at") or check.get("updated_at"),
                metadata=_compact_metadata(check, ["status", "conclusion", "app_slug"]),
            )
        )

    for release in snapshot.get("releases") or []:
        release_id = _required_str(release, "id")
        tag_name = release.get("tag_name")
        refs.append(
            GitHubSourceRef(
                owner=owner,
                repo=repo,
                artifact_type=GitHubArtifactType.RELEASE,
                external_id=release_id,
                url=release.get("html_url")
                or f"https://github.com/{owner}/{repo}/releases/tag/{tag_name or release_id}",
                title=release.get("name") or tag_name,
                branch=release.get("target_commitish") or branch,
                sha=release.get("target_commitish"),
                state="draft" if release.get("draft") else "published",
                updated_at=release.get("published_at") or release.get("updated_at"),
                metadata=_compact_metadata(release, ["tag_name", "prerelease", "draft"]),
            )
        )

    return _dedupe_source_refs(refs)


def extract_github_memory_candidates(snapshot: dict[str, Any]) -> list[GitHubMemoryCandidate]:
    """Extract reviewable memory candidates from a GitHub snapshot."""
    refs = build_github_source_refs(snapshot)
    by_key = {ref.stable_key: ref for ref in refs}
    owner, repo = _repo_owner_name(snapshot)
    candidates: list[GitHubMemoryCandidate] = []

    for pull_request in snapshot.get("pull_requests") or []:
        if not pull_request.get("merged"):
            continue
        body = str(pull_request.get("body") or "")
        decision = _extract_decision(body)
        if not decision:
            continue
        number = _required_str(pull_request, "number")
        source = by_key[f"github:{owner}/{repo}:pull_request:{number}"]
        if _contains_secret_like_text(decision):
            candidates.append(_secret_like_candidate(source, f"GitHub PR #{number}"))
            continue
        candidates.append(
            GitHubMemoryCandidate(
                content=f"Decision from GitHub PR #{number}: {decision}",
                memory_type=AgentMemoryType.DECISION,
                scope=AgentMemoryScope.PROJECT,
                category="github-pr-decision",
                evidence=[source],
                confidence=0.82,
                suggested_ttl_days=30,
                auto_approve=False,
            )
        )

    for rule in snapshot.get("repository_rules") or []:
        rule_id = _required_str(rule, "id")
        source = by_key[f"github:{owner}/{repo}:repository_rule:{rule_id}"]
        title = rule.get("name") or rule_id
        enforcement = rule.get("enforcement") or "configured"
        candidates.append(
            GitHubMemoryCandidate(
                content=f"GitHub repository rule is {enforcement}: {title}.",
                memory_type=AgentMemoryType.DECISION,
                scope=AgentMemoryScope.PROJECT,
                category="github-repository-rule",
                evidence=[source],
                confidence=0.8,
                suggested_ttl_days=30,
                auto_approve=False,
            )
        )

    for comment in snapshot.get("review_comments") or []:
        body = str(comment.get("body") or "")
        if not PREFERENCE_PATTERN.search(body):
            continue
        comment_id = _required_str(comment, "id")
        source = _source_ref_by_type_external_id(
            refs,
            GitHubArtifactType.REVIEW_COMMENT,
            comment_id,
        )
        if _contains_secret_like_text(body):
            candidates.append(_secret_like_candidate(source, f"GitHub review comment {comment_id}"))
            continue
        candidates.append(
            GitHubMemoryCandidate(
                content=f"Review feedback pattern from GitHub: {_first_sentence(body)}",
                memory_type=AgentMemoryType.LEARNING,
                scope=AgentMemoryScope.PROJECT,
                category="github-review-feedback",
                evidence=[source],
                confidence=0.68,
                suggested_ttl_days=21,
                risk_flags=[MemoryCandidateRisk.LOW_EVIDENCE],
                auto_approve=True,
            )
        )

    for run in snapshot.get("workflow_runs") or []:
        if str(run.get("conclusion") or "").lower() != "failure":
            continue
        summary = str(run.get("failure_summary") or "").strip()
        if not summary:
            continue
        run_id = _required_str(run, "id")
        source = by_key[f"github:{owner}/{repo}:workflow_run:{run_id}"]
        if _contains_secret_like_text(summary):
            candidates.append(_secret_like_candidate(source, f"GitHub Actions run {run_id}"))
            continue
        candidates.append(
            GitHubMemoryCandidate(
                content=f"CI failure pattern from GitHub Actions: {_first_sentence(summary)}",
                memory_type=AgentMemoryType.LEARNING,
                scope=AgentMemoryScope.PROJECT,
                category="github-ci-failure",
                evidence=[source],
                confidence=0.62,
                suggested_ttl_days=14,
                risk_flags=[MemoryCandidateRisk.LOW_EVIDENCE],
                auto_approve=True,
            )
        )

    return _dedupe_candidates(candidates)


def evaluate_github_memory_candidate(
    candidate: GitHubMemoryCandidate,
    *,
    allow_auto_approve: bool = False,
) -> GitHubMemoryPolicyResult:
    """Evaluate a GitHub memory candidate against the review-first policy."""

    reasons: list[str] = []

    if not candidate.evidence:
        reasons.append("missing_evidence")
        return GitHubMemoryPolicyResult(
            action=GitHubMemoryReviewAction.REJECT,
            reasons=reasons,
            policy_version=POLICY_VERSION,
        )

    risk_flags = set(candidate.risk_flags)
    if MemoryCandidateRisk.SECRET_LIKE in risk_flags:
        reasons.append("secret_like")
        return GitHubMemoryPolicyResult(
            action=GitHubMemoryReviewAction.REJECT,
            reasons=reasons,
            policy_version=POLICY_VERSION,
        )

    if risk_flags:
        reasons.extend(sorted(flag.value for flag in risk_flags))

    if candidate.scope in {AgentMemoryScope.TEAM, AgentMemoryScope.USER, AgentMemoryScope.AGENT}:
        reasons.append(f"{candidate.scope.value}_scope_requires_review")

    if not allow_auto_approve:
        reasons.append("review_first_default")

    if reasons:
        return GitHubMemoryPolicyResult(
            action=GitHubMemoryReviewAction.QUEUE,
            reasons=reasons,
            policy_version=POLICY_VERSION,
        )

    if candidate.auto_approve:
        return GitHubMemoryPolicyResult(
            action=GitHubMemoryReviewAction.AUTO_APPROVE,
            reasons=["explicit_low_risk_project_candidate"],
            policy_version=POLICY_VERSION,
        )

    return GitHubMemoryPolicyResult(
        action=GitHubMemoryReviewAction.QUEUE,
        reasons=["candidate_requested_review"],
        policy_version=POLICY_VERSION,
    )


def build_github_memory_review_items(
    snapshot: dict[str, Any],
    *,
    allow_auto_approve: bool = False,
) -> list[GitHubMemoryReviewItem]:
    """Build deterministic review items from extracted GitHub candidates."""

    items: list[GitHubMemoryReviewItem] = []
    for candidate in extract_github_memory_candidates(snapshot):
        policy = evaluate_github_memory_candidate(
            candidate,
            allow_auto_approve=allow_auto_approve,
        )
        items.append(
            GitHubMemoryReviewItem(
                review_id=_review_id(candidate),
                candidate=candidate,
                policy=policy,
            )
        )
    return items


def build_github_memory_promotion_plan(
    review_item: GitHubMemoryReviewItem,
    *,
    project_id: str | None = None,
    team_id: str | None = None,
    user_id: str | None = None,
    agent_id: str | None = None,
    reviewed_by: str | None = None,
) -> GitHubMemoryPromotionPlan:
    """Map an approved GitHub review item into Memory V2 create/evidence payloads."""

    if review_item.policy.action is GitHubMemoryReviewAction.REJECT:
        raise ValueError("rejected GitHub memory candidates cannot be promoted")

    if review_item.policy.action is GitHubMemoryReviewAction.QUEUE and not reviewed_by:
        raise ValueError("queued GitHub memory candidates require reviewed_by before promotion")

    candidate = review_item.candidate
    owner_payload = _memory_owner_payload_for_scope(
        candidate.scope,
        project_id=project_id,
        team_id=team_id,
        user_id=user_id,
        agent_id=agent_id,
    )
    now = datetime.now(UTC)
    stale_at = (
        now + timedelta(days=candidate.suggested_ttl_days) if candidate.suggested_ttl_days else None
    )

    memory = MemoryCreatePayload(
        **owner_payload,
        type=candidate.memory_type,
        scope=candidate.scope,
        status=MemoryStatus.ACTIVE,
        title=_candidate_title(candidate),
        content=candidate.content,
        category=candidate.category,
        confidence=candidate.confidence,
        freshness_score=1.0,
        evidence_score=_candidate_evidence_score(candidate),
        valid_from=now,
        stale_at=stale_at,
        source=MemorySource.WEBHOOK,
        created_by="github-memory-compiler",
        reviewed_by=reviewed_by,
    )
    evidence = [
        MemoryEvidencePayload(
            evidence_type=_evidence_type_for_github_artifact(source.artifact_type),
            external_ref=source.url,
            snippet=source.stable_key,
            line_start=source.line_start,
            line_end=source.line_end,
            weight=candidate.confidence,
        )
        for source in candidate.evidence
    ]

    return GitHubMemoryPromotionPlan(
        review_id=review_item.review_id,
        memory=memory,
        evidence=evidence,
        policy=review_item.policy,
    )


def compile_github_memory_context(
    request: ContextCompileRequest,
    review_items: list[GitHubMemoryReviewItem],
    *,
    extra_items: list[CompiledContextItem] | None = None,
) -> ContextCompileResponse:
    """Pack reviewed GitHub candidates and supplied context items within budget."""

    now = datetime.now(UTC)
    candidate_items: list[CompiledContextItem] = []
    omitted_items: list[CompiledContextItem] = []
    warnings: list[str] = []

    if ContextSourceType.GITHUB not in request.allowed_source_types:
        omitted_items.extend(
            _omitted_github_candidate_item(
                item,
                omitted_reason="source_type_not_allowed",
            )
            for item in review_items
        )
    else:
        for review_item in review_items:
            if review_item.policy.action is GitHubMemoryReviewAction.REJECT:
                omitted_items.append(
                    _omitted_github_candidate_item(
                        review_item,
                        omitted_reason="policy_rejected",
                    )
                )
                continue

            if request.repository and not _candidate_matches_repository(
                review_item.candidate,
                request.repository,
            ):
                omitted_items.append(
                    _omitted_github_candidate_item(
                        review_item,
                        omitted_reason="repository_mismatch",
                    )
                )
                continue

            stale, item_warnings = _candidate_staleness(review_item.candidate, request, now)
            warnings.extend(item_warnings)
            candidate_items.append(
                _compiled_item_from_review_item(review_item, request, stale=stale)
            )

    supplied_items = [
        _normalize_compiled_item(item)
        for item in (extra_items or [])
        if item.source_type in request.allowed_source_types
    ]
    omitted_items.extend(
        item.model_copy(update={"omitted_reason": "source_type_not_allowed"})
        for item in (extra_items or [])
        if item.source_type not in request.allowed_source_types
    )

    packed_items, budget_omitted = _pack_context_items(
        [*supplied_items, *candidate_items],
        token_budget=request.token_budget,
    )
    omitted_items.extend(budget_omitted)

    return ContextCompileResponse(
        bundle_id=_context_bundle_id(request, packed_items, omitted_items),
        request=request,
        items=packed_items,
        omitted_refs=omitted_items,
        max_tokens=request.token_budget,
        confidence_summary=_confidence_summary(packed_items),
        staleness_warnings=sorted(set(warnings)),
    )


def _repo_owner_name(snapshot: dict[str, Any]) -> tuple[str, str]:
    repository = snapshot.get("repository") or {}
    full_name = str(repository.get("full_name") or snapshot.get("full_name") or "").strip()
    if full_name.count("/") != 1:
        raise ValueError("GitHub snapshot requires repository.full_name in owner/repo format")
    owner, repo = full_name.split("/", 1)
    if not owner or not repo:
        raise ValueError("GitHub snapshot requires non-empty owner and repo")
    return owner, repo


def _repository_url(snapshot: dict[str, Any], owner: str, repo: str) -> str:
    repository = snapshot.get("repository") or {}
    return str(repository.get("html_url") or f"https://github.com/{owner}/{repo}")


def _repository_branch(snapshot: dict[str, Any]) -> str:
    repository = snapshot.get("repository") or {}
    return str(repository.get("default_branch") or snapshot.get("branch") or "main")


def _pull_request_state(pull_request: dict[str, Any]) -> str | None:
    if pull_request.get("merged"):
        return "merged"
    return pull_request.get("state")


def _extract_decision(text: str) -> str | None:
    match = DECISION_LINE_PATTERN.search(text)
    if not match:
        return None
    return _first_sentence(match.group("value"))


def _contains_secret_like_text(text: str) -> bool:
    return bool(SECRET_TEXT_PATTERN.search(text))


def _secret_like_candidate(source: GitHubSourceRef, label: str) -> GitHubMemoryCandidate:
    return GitHubMemoryCandidate(
        content=(
            f"{label} contains decision-like or preference-like text with secret-like material. "
            "Review the GitHub source before creating any durable memory."
        ),
        memory_type=AgentMemoryType.TODO,
        scope=AgentMemoryScope.PROJECT,
        category="github-secret-review",
        evidence=[source],
        confidence=0.2,
        suggested_ttl_days=7,
        risk_flags=[MemoryCandidateRisk.SECRET_LIKE],
        auto_approve=False,
    )


def _compact_metadata(source: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: source[key] for key in keys if key in source and source[key] is not None}


def _dedupe_source_refs(refs: list[GitHubSourceRef]) -> list[GitHubSourceRef]:
    seen: set[str] = set()
    deduped: list[GitHubSourceRef] = []
    for source_ref in refs:
        if source_ref.stable_key in seen:
            continue
        seen.add(source_ref.stable_key)
        deduped.append(source_ref)
    return deduped


def _dedupe_candidates(candidates: list[GitHubMemoryCandidate]) -> list[GitHubMemoryCandidate]:
    seen: set[tuple[str, tuple[str, ...]]] = set()
    deduped: list[GitHubMemoryCandidate] = []
    for candidate in candidates:
        key = (candidate.content.lower(), tuple(candidate.evidence_keys))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _review_id(candidate: GitHubMemoryCandidate) -> str:
    digest = sha256(
        "\n".join([candidate.content, *candidate.evidence_keys]).encode("utf-8")
    ).hexdigest()[:16]
    return f"github-review-{digest}"


def _compiled_item_from_review_item(
    review_item: GitHubMemoryReviewItem,
    request: ContextCompileRequest,
    *,
    stale: bool,
) -> CompiledContextItem:
    candidate = review_item.candidate
    first_source = candidate.evidence[0] if candidate.evidence else None
    source_ref = first_source.stable_key if first_source and request.include_references else None
    evidence = candidate.evidence if request.include_references else []

    return CompiledContextItem(
        source_type=ContextSourceType.GITHUB,
        content=candidate.content,
        source_ref=source_ref,
        evidence=evidence,
        priority=_candidate_context_priority(review_item, request, stale=stale),
        token_count=_estimate_tokens(candidate.content),
        confidence=candidate.confidence,
        stale=stale,
    )


def _omitted_github_candidate_item(
    review_item: GitHubMemoryReviewItem,
    *,
    omitted_reason: str,
) -> CompiledContextItem:
    candidate = review_item.candidate
    first_source = candidate.evidence[0] if candidate.evidence else None
    return CompiledContextItem(
        source_type=ContextSourceType.GITHUB,
        source_ref=first_source.stable_key if first_source else review_item.review_id,
        evidence=candidate.evidence,
        priority=_candidate_context_priority(review_item, None, stale=True),
        token_count=0,
        confidence=candidate.confidence,
        stale=True,
        omitted_reason=omitted_reason,
    )


def _normalize_compiled_item(item: CompiledContextItem) -> CompiledContextItem:
    if item.token_count > 0:
        return item
    payload = item.content or item.chunk_id or item.source_ref or ""
    return item.model_copy(update={"token_count": _estimate_tokens(payload)})


def _pack_context_items(
    items: list[CompiledContextItem],
    *,
    token_budget: int,
) -> tuple[list[CompiledContextItem], list[CompiledContextItem]]:
    packed: list[CompiledContextItem] = []
    omitted: list[CompiledContextItem] = []
    total_tokens = 0

    for item in sorted(items, key=lambda item: (item.priority, -item.confidence, item.token_count)):
        if total_tokens + item.token_count > token_budget:
            omitted.append(item.model_copy(update={"omitted_reason": "token_budget_exceeded"}))
            continue
        packed.append(item)
        total_tokens += item.token_count

    return packed, omitted


def _candidate_matches_repository(candidate: GitHubMemoryCandidate, repository: str) -> bool:
    normalized = repository.lower()
    return any(source.repository.lower() == normalized for source in candidate.evidence)


def _candidate_staleness(
    candidate: GitHubMemoryCandidate,
    request: ContextCompileRequest,
    now: datetime,
) -> tuple[bool, list[str]]:
    stale = False
    warnings: list[str] = []

    if request.branch:
        evidence_branches = [source.branch for source in candidate.evidence if source.branch]
        if evidence_branches and request.branch not in evidence_branches:
            stale = True
            warnings.append(f"branch_mismatch:{candidate.evidence_keys[0]}")

    if request.freshness_days:
        threshold = now - timedelta(days=request.freshness_days)
        for source in candidate.evidence:
            updated_at = _aware_utc(source.updated_at)
            if updated_at and updated_at < threshold:
                stale = True
                warnings.append(f"stale_evidence:{source.stable_key}")

    return stale, warnings


def _candidate_context_priority(
    review_item: GitHubMemoryReviewItem,
    request: ContextCompileRequest | None,
    *,
    stale: bool,
) -> int:
    candidate = review_item.candidate
    priority = 40
    if review_item.policy.action is GitHubMemoryReviewAction.AUTO_APPROVE:
        priority = 20
    if candidate.risk_flags:
        priority += 10
    if stale:
        priority += 20
    if (
        request
        and request.branch
        and any(source.branch == request.branch for source in candidate.evidence)
    ):
        priority -= 5
    return priority


def _confidence_summary(items: list[CompiledContextItem]) -> dict[str, float]:
    grouped: dict[str, list[float]] = {}
    for item in items:
        grouped.setdefault(item.source_type.value, []).append(item.confidence)
    return {
        source_type: round(sum(confidences) / len(confidences), 3)
        for source_type, confidences in grouped.items()
    }


def _context_bundle_id(
    request: ContextCompileRequest,
    items: list[CompiledContextItem],
    omitted_items: list[CompiledContextItem],
) -> str:
    digest_input = "\n".join(
        [
            request.task_intent,
            str(request.token_budget),
            str(request.repository or ""),
            str(request.branch or ""),
            *[
                f"item:{item.source_type.value}:{item.source_ref}:{item.content}:{item.token_count}"
                for item in items
            ],
            *[
                f"omit:{item.source_type.value}:{item.source_ref}:{item.omitted_reason}"
                for item in omitted_items
            ],
        ]
    )
    digest = sha256(digest_input.encode("utf-8")).hexdigest()[:16]
    return f"github-context-{digest}"


def _estimate_tokens(text: str) -> int:
    normalized = re.sub(r"\s+", " ", text.strip())
    if not normalized:
        return 0
    return max(1, (len(normalized) + 3) // 4)


def _aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _memory_owner_payload_for_scope(
    scope: AgentMemoryScope,
    *,
    project_id: str | None,
    team_id: str | None,
    user_id: str | None,
    agent_id: str | None,
) -> dict[str, str | None]:
    owner_payload = {
        "project_id": project_id,
        "team_id": team_id,
        "user_id": user_id,
        "agent_id": agent_id,
    }
    required_by_scope = {
        AgentMemoryScope.PROJECT: ("project_id", project_id),
        AgentMemoryScope.TEAM: ("team_id", team_id),
        AgentMemoryScope.USER: ("user_id", user_id),
        AgentMemoryScope.AGENT: ("agent_id", agent_id),
    }
    required_name, required_value = required_by_scope[scope]
    if not required_value:
        raise ValueError(f"{scope.value}-scoped GitHub memories require {required_name}")
    return owner_payload


def _candidate_title(candidate: GitHubMemoryCandidate) -> str:
    label_by_type = {
        AgentMemoryType.DECISION: "GitHub decision",
        AgentMemoryType.LEARNING: "GitHub learning",
        AgentMemoryType.PREFERENCE: "GitHub preference",
        AgentMemoryType.TODO: "GitHub review task",
        AgentMemoryType.FACT: "GitHub fact",
        AgentMemoryType.CONTEXT: "GitHub context",
    }
    label = label_by_type[candidate.memory_type]
    if candidate.category:
        return f"{label}: {candidate.category}"
    return label


def _candidate_evidence_score(candidate: GitHubMemoryCandidate) -> float:
    return min(1.0, 0.45 + (len(candidate.evidence) * 0.2) + (candidate.confidence * 0.2))


def _evidence_type_for_github_artifact(artifact_type: GitHubArtifactType) -> EvidenceType:
    if artifact_type is GitHubArtifactType.PULL_REQUEST:
        return EvidenceType.PR
    if artifact_type is GitHubArtifactType.ISSUE:
        return EvidenceType.ISSUE
    if artifact_type is GitHubArtifactType.COMMIT:
        return EvidenceType.COMMIT
    if artifact_type in {
        GitHubArtifactType.WORKFLOW_RUN,
        GitHubArtifactType.WORKFLOW_JOB,
        GitHubArtifactType.CHECK_RUN,
    }:
        return EvidenceType.WEBHOOK
    return EvidenceType.EXTERNAL_URL


def _source_ref_by_type_external_id(
    refs: list[GitHubSourceRef],
    artifact_type: GitHubArtifactType,
    external_id: str,
) -> GitHubSourceRef:
    for source_ref in refs:
        if source_ref.artifact_type is artifact_type and source_ref.external_id == external_id:
            return source_ref
    raise KeyError(f"missing GitHub source ref for {artifact_type.value}:{external_id}")


def _required_str(source: dict[str, Any], key: str) -> str:
    value = source.get(key)
    if value is None:
        raise ValueError(f"GitHub snapshot item missing required field: {key}")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"GitHub snapshot item has empty required field: {key}")
    return normalized


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _first_line(value: Any) -> str | None:
    if value is None:
        return None
    line = str(value).strip().splitlines()[0].strip()
    return line or None


def _first_sentence(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.strip())
    if not normalized:
        return ""
    sentence = re.split(r"(?<=[.!?])\s+", normalized, maxsplit=1)[0]
    return sentence[:240]
