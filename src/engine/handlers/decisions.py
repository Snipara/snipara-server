# apps/mcp-server/src/engine/handlers/decisions.py
"""Handlers for decision log MCP tools."""

from typing import Any

from src.models.decision import (
    Decision,
    DecisionCreateParams,
    DecisionImpact,
    DecisionQueryParams,
    DecisionQueryResult,
    DecisionStatus,
)


async def handle_decision_create(
    db: Any,
    project_id: str,
    params: DecisionCreateParams,
) -> Decision:
    """Create a new decision record."""
    # Generate next decision ID
    count = await db.projectdecision.count(where={"projectId": project_id})
    decision_id = f"DEC-{count + 1:03d}"

    record = await db.projectdecision.create(
        data={
            "decisionId": decision_id,
            "projectId": project_id,
            "title": params.title,
            "owner": params.owner,
            "scope": params.scope,
            "impact": params.impact.value,
            "context": params.context,
            "decision": params.decision,
            "rationale": params.rationale,
            "alternatives": params.alternatives,
            "revertPlan": params.revert_plan,
            "tags": params.tags,
        }
    )

    return Decision(
        id=record.decisionId,
        title=record.title,
        owner=record.owner,
        date=record.createdAt,
        scope=record.scope,
        impact=DecisionImpact(record.impact),
        status=DecisionStatus(record.status),
        context=record.context,
        decision=record.decision,
        rationale=record.rationale,
        alternatives=record.alternatives or [],
        revert_plan=record.revertPlan,
        tags=record.tags or [],
    )


async def handle_decision_query(
    db: Any,
    project_id: str,
    params: DecisionQueryParams,
) -> DecisionQueryResult:
    """Query decisions with filters."""
    # Build where clause
    where: dict[str, Any] = {"projectId": project_id}

    # Text query search in title, context, decision, rationale
    if params.query:
        where["OR"] = [
            {"title": {"contains": params.query, "mode": "insensitive"}},
            {"context": {"contains": params.query, "mode": "insensitive"}},
            {"decision": {"contains": params.query, "mode": "insensitive"}},
            {"rationale": {"contains": params.query, "mode": "insensitive"}},
        ]

    if params.scope:
        where["scope"] = params.scope

    if params.status:
        where["status"] = params.status  # Already a string
    elif not params.include_superseded:
        # By default exclude superseded decisions
        where["status"] = {"not": DecisionStatus.SUPERSEDED.value}

    if params.impact:
        where["impact"] = params.impact  # Already a string

    if params.owner:
        where["owner"] = params.owner

    if params.since:
        where["createdAt"] = {"gte": params.since}

    if params.tags:
        where["tags"] = {"hasSome": params.tags}

    # Query with count
    records = await db.projectdecision.find_many(
        where=where,
        order_by={"createdAt": "desc"},
        take=params.limit + 1,  # +1 to check has_more
    )

    has_more = len(records) > params.limit
    records = records[: params.limit]

    total = await db.projectdecision.count(where=where)

    decisions = [
        Decision(
            id=r.decisionId,
            title=r.title,
            owner=r.owner,
            date=r.createdAt,
            scope=r.scope,
            impact=DecisionImpact(r.impact),
            status=DecisionStatus(r.status),
            context=r.context,
            decision=r.decision,
            rationale=r.rationale,
            alternatives=r.alternatives or [],
            revert_plan=r.revertPlan,
            supersedes=r.supersedes,
            superseded_by=r.supersededBy,
            tags=r.tags or [],
        )
        for r in records
    ]

    return DecisionQueryResult(
        decisions=decisions,
        total=total,
        has_more=has_more,
    )


async def handle_decision_supersede(
    db: Any,
    project_id: str,
    old_decision_id: str,
    new_decision_params: DecisionCreateParams,
) -> Decision:
    """Create a new decision that supersedes an existing one."""
    # Find old decision
    old = await db.projectdecision.find_first(
        where={"projectId": project_id, "decisionId": old_decision_id}
    )

    if not old:
        raise ValueError(f"Decision {old_decision_id} not found")

    # Create new decision
    new_decision = await handle_decision_create(db, project_id, new_decision_params)

    # Update old decision to be superseded
    await db.projectdecision.update(
        where={"id": old.id},
        data={
            "status": DecisionStatus.SUPERSEDED.value,
            "supersededBy": new_decision.id,
        },
    )

    # Update new decision to reference old
    await db.projectdecision.update(
        where={"projectId": project_id, "decisionId": new_decision.id},
        data={"supersedes": old_decision_id},
    )

    new_decision.supersedes = old_decision_id
    return new_decision
