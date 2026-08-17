"""Local authentication and project configuration helpers.

The public server uses a static operator key for self-hosted deployments. A
small database API-key compatibility path is retained for existing private
installations during migration; OAuth, team-key and integrator authentication
are Cloud-only and are not part of this module.
"""

import hashlib
import hmac
from datetime import UTC, datetime

from .config import settings
from .db import get_db
from .models import Plan
from .models.responses import normalize_memory_novelty_threshold

API_KEY_CONTEXT_SCOPE = "context"
API_KEY_MEMORY_SCOPE = "memory"
FULL_API_KEY_SCOPES = [API_KEY_CONTEXT_SCOPE, API_KEY_MEMORY_SCOPE]

MEMORY_TOOL_NAMES = {
    "rlm_remember",
    "rlm_remember_if_novel",
    "rlm_end_of_task_commit",
    "rlm_remember_bulk",
    "rlm_recall",
    "rlm_journal_append",
    "rlm_journal_get",
    "rlm_journal_summarize",
    "rlm_session_memories",
    "rlm_memory_compact",
    "rlm_memory_health",
    "rlm_memory_duplicate_candidates",
    "rlm_memory_clean_candidates",
    "rlm_memory_daily_brief",
    "rlm_memory_invalidate",
    "rlm_memory_attach_source",
    "rlm_memory_supersede",
    "rlm_memory_verify",
}

# Kept for the engine's local project guard. There is no commercial plan
# enforcement in the OSS runtime.
PLAN_PROJECT_LIMITS: dict[str, int | None] = {
    "FREE": 1,
    "PRO": 5,
    "TEAM": None,
    "ENTERPRISE": None,
}


def hash_api_key(key: str) -> str:
    """Hash a database API key using SHA-256."""
    return hashlib.sha256(key.encode()).hexdigest()


def normalize_api_key_scopes(scopes: list[str] | None) -> list[str]:
    """Normalize stored API-key scopes into a stable, validated list."""
    normalized: list[str] = []
    if isinstance(scopes, list):
        for scope in FULL_API_KEY_SCOPES:
            if scope in scopes and scope not in normalized:
                normalized.append(scope)
    return normalized or [API_KEY_CONTEXT_SCOPE]


def get_auth_scopes(auth_info: dict | None) -> list[str]:
    """Return effective scopes for the authenticated principal."""
    if not auth_info:
        return list(FULL_API_KEY_SCOPES)
    scopes = auth_info.get("scopes")
    if isinstance(scopes, list):
        return normalize_api_key_scopes(scopes)
    return list(FULL_API_KEY_SCOPES)


def tool_requires_memory_scope(tool_name: str) -> bool:
    """Return True for tools that read or write persistent memory."""
    return tool_name in MEMORY_TOOL_NAMES


def enforce_tool_scope(tool_name: str, auth_info: dict | None) -> None:
    """Reject a tool call when the credential lacks its local scope."""
    required_scope = (
        API_KEY_MEMORY_SCOPE if tool_requires_memory_scope(tool_name) else API_KEY_CONTEXT_SCOPE
    )
    if required_scope not in get_auth_scopes(auth_info):
        raise PermissionError(f"Tool {tool_name} requires {required_scope} scope for this API key.")


async def get_project_with_team(project_id_or_slug: str) -> object | None:
    """Resolve a project by ID, slug or GitHub-style repository reference."""
    db = await get_db()
    return await db.project.find_first(
        where={
            "deletedAt": None,
            "OR": [
                {"id": project_id_or_slug},
                {"slug": project_id_or_slug},
                {"githubRepo": project_id_or_slug},
            ],
        },
        include={
            "team": {
                "include": {
                    "subscription": True,
                }
            },
            "documents": True,
        },
    )


async def validate_local_api_key(api_key: str, project_id_or_slug: str) -> dict | None:
    """Validate the operator-provided key used by a self-hosted instance."""
    configured_key = settings.snipara_local_api_key.strip()
    if not configured_key or not hmac.compare_digest(api_key, configured_key):
        return None

    project = await get_project_with_team(project_id_or_slug)
    if not project:
        return None

    return {
        "id": "local-operator",
        "name": "Local operator key",
        "user_id": None,
        "project_id": project.id,
        "project": project,
        "team_id": getattr(project, "teamId", None),
        "auth_type": "local",
        "access_level": "ADMIN",
        "scopes": list(FULL_API_KEY_SCOPES),
        "access_denied": False,
    }


async def validate_api_key(api_key: str, project_id_or_slug: str) -> dict | None:
    """Validate a project-bound database API key for migration compatibility."""
    db = await get_db()
    project = await get_project_with_team(project_id_or_slug)
    if not project:
        return None

    record = await db.apikey.find_first(
        where={"keyHash": hash_api_key(api_key)},
        include={
            "project": {
                "include": {
                    "team": {
                        "include": {
                            "subscription": True,
                        }
                    }
                }
            }
        },
    )
    if not record or record.revokedAt:
        return None
    if record.expiresAt and record.expiresAt < datetime.now(UTC):
        return None
    if not record.projectId or record.projectId != project.id:
        return None

    await db.apikey.update(
        where={"id": record.id},
        data={"lastUsedAt": datetime.now(UTC)},
    )
    return {
        "id": record.id,
        "name": record.name,
        "user_id": None,
        "project_id": project.id,
        "project": project,
        "team_id": getattr(project, "teamId", None),
        "auth_type": "project_key",
        "access_level": getattr(record, "accessLevel", "EDITOR"),
        "scopes": normalize_api_key_scopes(getattr(record, "scopes", None)),
        "access_denied": False,
    }


async def get_project_settings(project_id_or_slug: str) -> dict | None:
    """Load local project behavior settings."""
    db = await get_db()
    project = await db.project.find_first(
        where={
            "deletedAt": None,
            "OR": [
                {"id": project_id_or_slug},
                {"slug": project_id_or_slug},
                {"githubRepo": project_id_or_slug},
            ],
        },
    )
    if not project:
        return None

    return {
        "automation_client": project.automationClient,
        "auto_inject_context": project.autoInjectContext,
        "track_accessed_files": project.trackAccessedFiles,
        "preserve_on_compaction": project.preserveOnCompaction,
        "restore_on_session_start": project.restoreOnSessionStart,
        "enrich_prompts": project.enrichPrompts,
        "max_tokens_per_query": project.maxTokensPerQuery,
        "search_mode": project.searchMode,
        "include_summaries": project.includeSummaries,
        "memory_injection_enabled": getattr(project, "memoryInjectionEnabled", False),
        "memory_inject_types": getattr(project, "memoryInjectTypes", None),
        "memory_exclude_session_checkpoints": getattr(
            project, "memoryExcludeSessionCheckpoints", False
        ),
        "memory_min_confidence": getattr(project, "memoryMinConfidence", 0.2),
        "memory_recall_query": getattr(project, "memoryRecallQuery", None),
        "memory_save_on_commit": getattr(project, "memorySaveOnCommit", False),
        "memory_auto_recall_on_session_start": getattr(
            project, "memoryAutoRecallOnSessionStart", True
        ),
        "memory_auto_recall_on_resume": getattr(project, "memoryAutoRecallOnResume", True),
        "memory_deduplicate_before_write": getattr(project, "memoryDeduplicateBeforeWrite", True),
        "memory_end_of_task_commit_enabled": getattr(
            project, "memoryEndOfTaskCommitEnabled", True
        ),
        "memory_workspace_profile_enabled": getattr(
            project, "memoryWorkspaceProfileEnabled", True
        ),
        "memory_novelty_threshold": normalize_memory_novelty_threshold(
            getattr(project, "memoryNoveltyThreshold", None)
        ),
        "memory_resume_window_minutes": getattr(project, "memoryResumeWindowMinutes", 180),
        "memory_review_mode": getattr(project, "memoryReviewMode", "AUTO"),
        "memory_capture_tool_results": getattr(project, "memoryCaptureToolResults", True),
        "memory_capture_failures": getattr(project, "memoryCaptureFailures", False),
    }


def get_effective_plan(subscription: object | None) -> Plan:
    """Return the local free plan unless a compatibility subscription exists."""
    if not subscription:
        return Plan.FREE
    plan = getattr(subscription, "plan", "FREE")
    if plan not in Plan.__members__:
        return Plan.FREE
    return Plan(plan)
