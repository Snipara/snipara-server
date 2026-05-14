"""
API key validation module.

This module handles authentication for the MCP server, supporting both API keys
and OAuth tokens. Functions that accept a project identifier support THREE forms:
- Database ID        (e.g., "cm5xyz123abc...")
- Project slug       (e.g., "snipara", "my-project")
- GitHub repo ref    (e.g., "owner/repo")  ← resolved against Project.githubRepo

This flexibility lets the CLI auto-resolve a project from the local workspace
(git remote, package.json, etc.) without any manual config.

On the team-API-key path only (never on per-project API keys used by integrators),
if the project does not exist yet and the team has `autoCreateProjects=true`, the
project is auto-created under the team's plan quota.
"""

import hashlib
import re
from datetime import UTC, datetime

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
    "rlm_tenant_profile_create",
    "rlm_tenant_profile_get",
}


# FREE=1, PRO=5, TEAM/ENTERPRISE=unlimited (mirrors packages/shared/src/constants.ts)
PLAN_PROJECT_LIMITS: dict[str, int | None] = {
    "FREE": 1,
    "PRO": 5,
    "TEAM": None,        # unlimited
    "ENTERPRISE": None,  # unlimited
}

CONTEXT_PLAN_HIERARCHY = {
    "FREE": 0,
    "PRO": 1,
    "TEAM": 2,
    "ENTERPRISE": 3,
}

REQUIRED_CONTEXT_PLAN = {
    "STARTER": None,
    "PRO": None,
    "TEAM": "TEAM",
    "ENTERPRISE": "ENTERPRISE",
}


def _parse_project_identifier(identifier: str) -> tuple[str, str | None]:
    """
    Parse a project identifier into (slug, github_repo).

    - "owner/repo"  → ("repo", "owner/repo")
    - "owner/repo.git" → ("repo", "owner/repo")
    - "my-project"  → ("my-project", None)
    - db-id         → treated as slug ("cm5xyz...", None)

    Callers can still match by raw id via `where id = identifier`, the slug form
    is a best-effort derivation for auto-create and display.
    """
    m = re.fullmatch(r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(\.git)?", identifier)
    if m:
        return m.group(2), f"{m.group(1)}/{m.group(2)}"
    return identifier, None


def hash_api_key(key: str) -> str:
    """Hash an API key using SHA-256."""
    return hashlib.sha256(key.encode()).hexdigest()


def normalize_api_key_scopes(scopes: list[str] | None) -> list[str]:
    """Normalize stored API key scopes into a stable, validated list."""
    normalized: list[str] = []

    if isinstance(scopes, list):
        for scope in FULL_API_KEY_SCOPES:
            if scope in scopes and scope not in normalized:
                normalized.append(scope)

    return normalized or [API_KEY_CONTEXT_SCOPE]


async def resolve_project_auth_scopes(
    project_id: str,
    user_id: str | None = None,
) -> list[str]:
    """Derive effective scopes for a project-bound authenticated principal."""
    db = await get_db()

    if not hasattr(db, "agentssubscription"):
        return [API_KEY_CONTEXT_SCOPE]

    project = await db.project.find_unique(
        where={"id": project_id},
        include={"team": True},
    )
    if not project:
        return [API_KEY_CONTEXT_SCOPE]

    agents_subscription = None

    if project.teamId:
        agents_subscription = await db.agentssubscription.find_first(
            where={
                "teamId": project.teamId,
                "status": "active",
            },
        )

        if not agents_subscription:
            owner_member = await db.teammember.find_first(
                where={
                    "teamId": project.teamId,
                    "role": "OWNER",
                },
            )
            if owner_member:
                agents_subscription = await db.agentssubscription.find_first(
                    where={
                        "userId": owner_member.userId,
                        "teamId": None,
                        "status": "active",
                    },
                )

    if not agents_subscription and user_id:
        agents_subscription = await db.agentssubscription.find_first(
            where={
                "userId": user_id,
                "teamId": None,
                "status": "active",
            },
        )

    if not agents_subscription:
        return [API_KEY_CONTEXT_SCOPE]

    grace_period_end = getattr(agents_subscription, "gracePeriodEnd", None)
    if isinstance(grace_period_end, datetime):
        if grace_period_end.tzinfo is None:
            grace_period_end = grace_period_end.replace(tzinfo=UTC)
        if datetime.now(UTC) > grace_period_end:
            return [API_KEY_CONTEXT_SCOPE]

    required_context = REQUIRED_CONTEXT_PLAN.get(agents_subscription.plan)
    if not required_context:
        return list(FULL_API_KEY_SCOPES)

    team_id = getattr(agents_subscription, "teamId", None)
    if not team_id:
        return [API_KEY_CONTEXT_SCOPE]

    context_sub = await db.subscription.find_first(
        where={"teamId": team_id},
    )
    if not context_sub:
        return [API_KEY_CONTEXT_SCOPE]

    required_level = CONTEXT_PLAN_HIERARCHY.get(required_context, 0)
    current_level = CONTEXT_PLAN_HIERARCHY.get(context_sub.plan, 0)

    return (
        list(FULL_API_KEY_SCOPES)
        if current_level >= required_level
        else [API_KEY_CONTEXT_SCOPE]
    )


def get_auth_scopes(auth_info: dict | None) -> list[str]:
    """Return effective scopes for the authenticated principal."""
    if not auth_info:
        return list(FULL_API_KEY_SCOPES)

    scopes = auth_info.get("scopes")
    if isinstance(scopes, list):
        return normalize_api_key_scopes(scopes)

    return list(FULL_API_KEY_SCOPES)


def tool_requires_memory_scope(tool_name: str) -> bool:
    """Return True when a tool reads or writes memory-managed state."""
    return tool_name in MEMORY_TOOL_NAMES


def enforce_tool_scope(tool_name: str, auth_info: dict | None) -> None:
    """Raise when the authenticated principal lacks the required tool scope."""
    required_scope = (
        API_KEY_MEMORY_SCOPE if tool_requires_memory_scope(tool_name) else API_KEY_CONTEXT_SCOPE
    )
    scopes = get_auth_scopes(auth_info)

    if required_scope not in scopes:
        raise PermissionError(
            f"Tool {tool_name} requires {required_scope} scope for this API key."
        )


async def user_key_has_project_access(user_id: str, project_id: str) -> bool:
    """Check user-scoped API key access only for the user's personal workspace."""
    db = await get_db()

    project = await db.project.find_first(
        where={
            "id": project_id,
            "team": {
                "isPersonal": True,
                "members": {
                    "some": {
                        "userId": user_id,
                        "role": "OWNER",
                    }
                },
            },
        },
    )

    return project is not None


async def resolve_project_api_key_access(
    user_id: str,
    project: object,
) -> tuple[str, bool]:
    """Resolve effective project access from real workspace/team membership."""
    team = getattr(project, "team", None)

    if team and getattr(team, "isPersonal", False):
        has_access = await user_key_has_project_access(user_id, project.id)
        return ("ADMIN", False) if has_access else ("NONE", True)

    return await check_team_key_project_access(user_id, project.id, project.teamId)


async def validate_api_key(api_key: str, project_id_or_slug: str) -> dict | None:
    """
    Validate an API key and check project access.

    Tries project-specific API keys first, then falls back to team API keys.
    This allows users to use either:
    - A project-specific key (rlm_...) for a single project
    - A team API key that works for all projects in the team

    Args:
        api_key: The API key from the request header
        project_id_or_slug: The project ID or slug being accessed

    Returns:
        API key record if valid, None otherwise
    """
    db = await get_db()

    # Hash the provided key to compare with stored hash
    key_hash = hash_api_key(api_key)
    project = await get_project_with_team(project_id_or_slug)

    api_key_record = await db.apikey.find_first(
        where={"keyHash": key_hash},
        include={
            "project": {
                "include": {
                    "team": {
                        "include": {
                            "subscription": True,
                        }
                    }
                }
            },
            "user": True,
        },
    )

    if api_key_record:
        # Check if key is revoked
        if api_key_record.revokedAt:
            return None

        # Check if key is expired
        if api_key_record.expiresAt and api_key_record.expiresAt < datetime.now(UTC):
            return None

        if not project:
            return None

        resolved_project = project

        if api_key_record.projectId:
            if api_key_record.projectId != project.id:
                return None
            resolved_project = api_key_record.project or project
            access_level, access_denied = await resolve_project_api_key_access(
                api_key_record.userId, resolved_project
            )
        else:
            has_access = await user_key_has_project_access(api_key_record.userId, project.id)
            if not has_access:
                return None
            access_level, access_denied = "ADMIN", False

        # Update last used timestamp
        await db.apikey.update(
            where={"id": api_key_record.id},
            data={"lastUsedAt": datetime.now(UTC)},
        )

        # Check if this project belongs to an integrator client (for PARTNER rate limits)
        integrator_client = await db.integratorclient.find_first(
            where={"projectId": resolved_project.id}
        )
        is_integrator_project = integrator_client is not None

        return {
            "id": api_key_record.id,
            "name": api_key_record.name,
            "user_id": api_key_record.userId,
            "project_id": resolved_project.id,
            "project": resolved_project,
            "scopes": await resolve_project_auth_scopes(
                resolved_project.id,
                api_key_record.userId,
            ),
            "auth_type": "project_key" if api_key_record.projectId else "user_key",
            "access_level": access_level,
            "access_denied": access_denied,
            "is_integrator_project": is_integrator_project,
        }

    # If no project key found, try team API key.
    if project:
        # Existing project: validate team key belongs to the project's team.
        team_key_record = await db.teamapikey.find_first(
            where={
                "keyHash": key_hash,
                "teamId": project.teamId,
            },
            include={
                "team": {
                    "include": {
                        "subscription": True,
                    }
                },
                "user": True,
            },
        )

        if not team_key_record:
            return None
    else:
        # Project does not exist. Try to match the team key by hash alone, and
        # auto-create the project if the team has autoCreateProjects enabled
        # and hasn't exceeded its plan quota.
        team_key_record = await db.teamapikey.find_first(
            where={"keyHash": key_hash},
            include={
                "team": {
                    "include": {
                        "subscription": True,
                    }
                },
                "user": True,
            },
        )

        if not team_key_record:
            return None

        # Re-check team-key validity BEFORE touching team state
        if team_key_record.revokedAt:
            return None
        if team_key_record.expiresAt and team_key_record.expiresAt < datetime.now(UTC):
            return None

        team = team_key_record.team
        if not team or not getattr(team, "autoCreateProjects", True):
            return None

        # Slug collision by githubRepo: if a project with the same githubRepo
        # already exists in this team, reuse it (avoids duplicate projects when
        # the same repo is connected from multiple workspaces).
        slug, github_repo = _parse_project_identifier(project_id_or_slug)
        if github_repo:
            existing_by_repo = await db.project.find_first(
                where={
                    "teamId": team.id,
                    "githubRepo": github_repo,
                    "deletedAt": None,
                },
                include={
                    "team": {
                        "include": {
                            "subscription": True,
                        }
                    }
                },
            )
            if existing_by_repo:
                project = existing_by_repo

        if not project:
            # Enforce plan project-limit (counts only non-soft-deleted projects)
            effective_plan = get_effective_plan(team.subscription)
            limit = PLAN_PROJECT_LIMITS.get(effective_plan.value)
            if limit is not None:
                active_count = await db.project.count(
                    where={"teamId": team.id, "deletedAt": None}
                )
                if active_count >= limit:
                    return {
                        "id": None,
                        "auth_type": "team_key",
                        "access_denied": True,
                        "quota_exceeded": True,
                        "quota_limit": limit,
                        "quota_plan": effective_plan.value,
                    }

            # Slug collision on pure slug (not githubRepo): return None → caller 409
            slug_collision = await db.project.find_first(
                where={"teamId": team.id, "slug": slug, "deletedAt": None}
            )
            if slug_collision:
                return None

            # Auto-create the project
            project = await db.project.create(
                data={
                    "name": slug,
                    "slug": slug,
                    "githubRepo": github_repo,
                    "teamId": team.id,
                },
                include={
                    "team": {
                        "include": {
                            "subscription": True,
                        }
                    }
                },
            )

    # Check if team key is revoked
    if team_key_record.revokedAt:
        return None

    # Check if team key is expired
    if team_key_record.expiresAt and team_key_record.expiresAt < datetime.now(UTC):
        return None

    # Update last used timestamp for team key
    await db.teamapikey.update(
        where={"id": team_key_record.id},
        data={"lastUsedAt": datetime.now(UTC)},
    )

    # Check per-project access control for team keys
    access_level, access_denied = await check_team_key_project_access(
        team_key_record.userId, project.id, project.teamId
    )

    # Check if this project belongs to an integrator client (for PARTNER rate limits)
    integrator_client = await db.integratorclient.find_first(
        where={"projectId": project.id}
    )
    is_integrator_project = integrator_client is not None

    # Return team key info with project and access level attached
    return {
        "id": team_key_record.id,
        "name": team_key_record.name,
        "user_id": team_key_record.userId,
        "project_id": project.id,
        "project": project,
        "auth_type": "team_key",
        "scopes": await resolve_project_auth_scopes(project.id, team_key_record.userId),
        "access_level": access_level,
        "access_denied": access_denied,
        "is_integrator_project": is_integrator_project,
    }


async def check_team_key_project_access(
    user_id: str, project_id: str, team_id: str
) -> tuple[str, bool]:
    """
    Check if a team key user has access to a specific project.

    This implements per-project access control for team API keys. Access control
    is only enforced when ALL of these conditions are met:
    1. Team has permissionConfig.mode = ADVANCED
    2. Team has permissionConfig.projectAccessControlEnabled = true
    3. User is not OWNER or ADMIN role

    If any condition is false, the user gets full access (backward compatible).

    Args:
        user_id: The user ID associated with the team key
        project_id: The project ID being accessed
        team_id: The team ID

    Returns:
        Tuple of (access_level, access_denied):
        - access_level: "NONE", "VIEWER", "EDITOR", or "ADMIN"
        - access_denied: True if access is denied (level is NONE)
    """
    db = await get_db()

    # Get team permission config and member info in one query
    team_member = await db.teammember.find_first(
        where={
            "userId": user_id,
            "teamId": team_id,
        },
        include={
            "team": {
                "include": {
                    "permissionConfig": True,
                }
            },
            "projectAccess": {
                "where": {
                    "projectId": project_id,
                }
            },
        },
    )

    if not team_member:
        # User is not a team member - should not happen with valid team key
        return "NONE", True

    # Get permission config
    config = team_member.team.permissionConfig if team_member.team else None

    # OWNER and ADMIN roles always have full access (regardless of mode)
    if team_member.role in ("OWNER", "ADMIN"):
        return "ADMIN", False

    # If ADVANCED mode with project access control is NOT enabled,
    # team keys work as before (full access) - backward compatible
    if not config or config.mode != "ADVANCED" or not config.projectAccessControlEnabled:
        return "EDITOR", False  # Full access (backward compatible)

    # Check ProjectMember for explicit access
    if team_member.projectAccess and len(team_member.projectAccess) > 0:
        access_level = team_member.projectAccess[0].accessLevel
        access_denied = access_level == "NONE"
        return access_level, access_denied

    # No explicit ProjectMember entry = NONE access
    return "NONE", True


async def validate_team_api_key(api_key: str, team_id: str) -> dict | None:
    """
    Validate a team API key and check team access.

    Args:
        api_key: The API key from the request header
        team_id: The team being accessed

    Returns:
        API key record if valid, None otherwise
    """
    db = await get_db()

    key_hash = hash_api_key(api_key)

    api_key_record = await db.teamapikey.find_first(
        where={
            "keyHash": key_hash,
            "teamId": team_id,
        },
        include={
            "team": {
                "include": {
                    "subscription": True,
                    "projects": True,
                }
            },
            "user": True,
        },
    )

    if not api_key_record:
        return None

    if api_key_record.expiresAt and api_key_record.expiresAt < datetime.now(UTC):
        return None

    if api_key_record.revokedAt:
        return None

    await db.teamapikey.update(
        where={"id": api_key_record.id},
        data={"lastUsedAt": datetime.now(UTC)},
    )

    return {
        "id": api_key_record.id,
        "name": api_key_record.name,
        "user_id": api_key_record.userId,
        "team_id": api_key_record.teamId,
        "team": api_key_record.team,
        "scopes": list(FULL_API_KEY_SCOPES),
    }


async def get_project_with_team(project_id_or_slug: str) -> dict | None:
    """
    Get project details including team and subscription info.

    Args:
        project_id_or_slug: The project ID, slug, or "owner/repo" (matched
            against Project.githubRepo). Excludes soft-deleted projects.

    Returns:
        Project record with team and subscription, or None
    """
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
        include={
            "team": {
                "include": {
                    "subscription": True,
                }
            },
            "documents": True,
        },
    )

    return project


async def get_team_by_slug_or_id(team_slug_or_id: str) -> dict | None:
    """
    Get team by slug or ID, including subscription and projects.

    Args:
        team_slug_or_id: Team slug or ID

    Returns:
        Team record with subscription and projects, or None
    """
    db = await get_db()

    team = await db.team.find_first(
        where={
            "OR": [
                {"id": team_slug_or_id},
                {"slug": team_slug_or_id},
            ]
        },
        include={
            "subscription": True,
            "projects": True,
        },
    )

    return team


async def validate_oauth_token(token: str, project_id_or_slug: str) -> dict | None:
    """
    Validate an OAuth access token and check project access.

    Args:
        token: The OAuth access token (snipara_at_...)
        project_id_or_slug: The project ID or slug being accessed

    Returns:
        Token record if valid, None otherwise
    """
    db = await get_db()

    # Hash the token to compare with stored hash
    token_hash = hash_api_key(token)

    # Find the OAuth token by hash and project (matching id, slug, or githubRepo)
    oauth_token = await db.oauthtoken.find_first(
        where={
            "accessTokenHash": token_hash,
            "project": {
                "deletedAt": None,
                "OR": [
                    {"id": project_id_or_slug},
                    {"slug": project_id_or_slug},
                    {"githubRepo": project_id_or_slug},
                ],
            },
        },
        include={
            "project": {
                "include": {
                    "team": {
                        "include": {
                            "subscription": True,
                        }
                    }
                }
            },
            "user": True,
        },
    )

    if not oauth_token:
        return None

    # Check if revoked
    if oauth_token.revokedAt:
        return None

    # Check if expired
    if oauth_token.accessExpiresAt < datetime.now(UTC):
        return None

    # Update last used timestamp
    await db.oauthtoken.update(
        where={"id": oauth_token.id},
        data={"lastUsedAt": datetime.now(UTC)},
    )

    # Determine access level from OAuth scope
    # mcp:write scope grants EDITOR, mcp:read grants VIEWER
    oauth_access_level = "EDITOR" if "mcp:write" in (oauth_token.scope or "") else "VIEWER"

    # Check if this project belongs to an integrator client (for PARTNER rate limits)
    integrator_client = await db.integratorclient.find_first(
        where={"projectId": oauth_token.projectId}
    )
    is_integrator_project = integrator_client is not None

    return {
        "id": oauth_token.id,
        "user_id": oauth_token.userId,
        "project_id": oauth_token.projectId,
        "project": oauth_token.project,
        "scope": oauth_token.scope,
        "scopes": await resolve_project_auth_scopes(
            oauth_token.projectId,
            oauth_token.userId,
        ),
        "auth_type": "oauth",
        "access_level": oauth_access_level,
        "access_denied": False,
        "is_integrator_project": is_integrator_project,
    }


async def validate_client_api_key(
    api_key: str, project_id_or_slug: str
) -> dict | None:
    """
    Validate a snipara_ic_ client API key (Integrator client keys).

    Client API keys are issued by integrators to their clients. Each client
    can only access their own assigned project - isolation is enforced.

    Args:
        api_key: The API key (must start with snipara_ic_)
        project_id_or_slug: Project ID or slug to validate access

    Returns:
        Auth info dict if valid, None otherwise
    """
    if not api_key.startswith("snipara_ic_"):
        return None

    db = await get_db()
    key_hash = hash_api_key(api_key)

    # Find the client API key with all relations
    client_key = await db.clientapikey.find_first(
        where={"keyHash": key_hash},
        include={
            "client": {
                "include": {
                    "workspace": {
                        "include": {
                            "integrator": True
                        }
                    },
                    "project": {
                        "include": {
                            "team": {
                                "include": {
                                    "subscription": True
                                }
                            }
                        }
                    }
                }
            }
        }
    )

    if not client_key:
        return None

    # Check if key is revoked
    if client_key.revokedAt:
        return None

    # Check if key is expired
    if client_key.expiresAt and client_key.expiresAt < datetime.now(UTC):
        return None

    # Check if client is active
    if not client_key.client.isActive:
        return None

    # Verify project access - client can ONLY access their own project
    client = client_key.client
    if not client.project:
        return None

    project = client.project
    if project.id != project_id_or_slug and project.slug != project_id_or_slug:
        return None

    # Update lastUsedAt
    await db.clientapikey.update(
        where={"id": client_key.id},
        data={"lastUsedAt": datetime.now(UTC)}
    )

    return {
        "id": client_key.id,
        "name": client_key.name,
        "user_id": client.workspace.integrator.userId,
        "project_id": project.id,
        "project": project,
        "auth_type": "integrator_client",
        "scopes": await resolve_project_auth_scopes(
            project.id,
            client.workspace.integrator.userId,
        ),
        "access_level": "EDITOR",  # Clients get EDITOR access
        "access_denied": False,
        "client_id": client.id,
        "client_bundle": client.bundle,
        "workspace_id": client.workspaceId,
    }


async def get_project_settings(project_id_or_slug: str) -> dict | None:
    """
    Get project automation settings from database.

    These settings are configured in the dashboard and used by the MCP server
    to customize query behavior (max tokens, search mode, etc.).

    Args:
        project_id_or_slug: The project ID or slug

    Returns:
        Dict with automation settings or None if project not found
    """
    db = await get_db()

    # Find by ID, slug, or githubRepo (excluding soft-deleted)
    project = await db.project.find_first(
        where={
            "deletedAt": None,
            "OR": [
                {"id": project_id_or_slug},
                {"slug": project_id_or_slug},
                {"githubRepo": project_id_or_slug},
            ],
        },
        include=None,  # No relations needed, just the project fields
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
        # Memory injection settings (Agents feature)
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
        "memory_deduplicate_before_write": getattr(
            project, "memoryDeduplicateBeforeWrite", True
        ),
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


def get_effective_plan(subscription) -> Plan:
    """
    Get the effective plan for a subscription, considering PRO boost.

    If a FREE user has an active PRO boost (within 30 days of registration),
    they get PRO limits. After the boost expires, they revert to FREE.

    Args:
        subscription: The team subscription object (or None)

    Returns:
        The effective Plan enum value
    """
    if not subscription:
        return Plan.FREE

    plan = subscription.plan

    # If paid plan, use that directly
    if plan != "FREE":
        return Plan(plan)

    # If FREE with active boost, return PRO
    pro_boost_ends_at = getattr(subscription, "proBoostEndsAt", None)
    if pro_boost_ends_at and pro_boost_ends_at > datetime.now(UTC):
        return Plan.PRO

    return Plan.FREE
