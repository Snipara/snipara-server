"""Graphify-compatible export endpoints for persisted Snipara code graphs."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from ..db import get_db
from ..services.code_graph import GraphifyExportService
from .deps import get_api_key, validate_and_rate_limit

router = APIRouter(tags=["Graphify Adapter"])


@router.get("/v1/{project_id}/graphify/graph.json")
async def export_graphify_graph(
    project_id: str,
    api_key: Annotated[str, Depends(get_api_key)],
    directed: bool = Query(
        default=False,
        description="Export as a directed graph. Default remains undirected for Graphify serve parity.",
    ),
):
    """Export the persisted code graph as Graphify-compatible node-link JSON."""
    _, project, _, _ = await validate_and_rate_limit(project_id, api_key)
    db = await get_db()
    payload = await GraphifyExportService(db).export_project_graph(
        project_id=project.id,
        project_slug=getattr(project, "slug", project_id),
        project_name=getattr(project, "name", project_id),
        directed=directed,
    )
    if not payload["nodes"]:
        raise HTTPException(
            status_code=409,
            detail=(
                "No indexed code graph is available for this project. "
                f"Run POST /v1/{project_id}/reindex?kind=code first."
            ),
        )
    return payload
