"""Agent memory and swarm models for RLM MCP Server (Phase 8.2 & 9.1)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .enums import AgentMemoryScope, AgentMemoryType

# ============ AGENT MEMORY MODELS (Phase 8.2) ============


class RememberResult(BaseModel):
    """Result of rlm_remember tool."""

    memory_id: str = Field(..., description="Unique identifier for the stored memory")
    content: str = Field(..., description="The stored content")
    type: AgentMemoryType = Field(..., description="Memory type")
    scope: AgentMemoryScope = Field(..., description="Memory scope")
    category: str | None = Field(default=None, description="Category if provided")
    expires_at: datetime | None = Field(default=None, description="When memory expires")
    created: bool = Field(default=True, description="True if new, False if updated")
    message: str = Field(..., description="Human-readable status message")


class RecalledMemory(BaseModel):
    """A memory recalled with relevance scoring."""

    memory_id: str = Field(..., description="Memory ID")
    content: str = Field(..., description="Memory content")
    type: AgentMemoryType = Field(..., description="Memory type")
    scope: AgentMemoryScope = Field(..., description="Memory scope")
    category: str | None = Field(default=None, description="Category")
    relevance: float = Field(..., ge=0.0, le=1.0, description="Relevance score")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence after decay")
    created_at: datetime = Field(..., description="When memory was created")
    last_accessed_at: datetime | None = Field(default=None, description="Last access time")
    access_count: int = Field(default=0, ge=0, description="Times accessed")


class RecallResult(BaseModel):
    """Result of rlm_recall tool."""

    memories: list[RecalledMemory] = Field(
        default_factory=list, description="Recalled memories ranked by relevance"
    )
    total_searched: int = Field(default=0, ge=0, description="Total memories searched")
    query: str = Field(..., description="Original query")
    timing_ms: int = Field(default=0, ge=0, description="Recall latency in milliseconds")


class MemoryInfo(BaseModel):
    """Information about a stored memory."""

    memory_id: str = Field(..., description="Memory ID")
    content: str = Field(..., description="Memory content")
    type: AgentMemoryType = Field(..., description="Memory type")
    scope: AgentMemoryScope = Field(..., description="Memory scope")
    category: str | None = Field(default=None, description="Category")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Current confidence")
    source: str | None = Field(default=None, description="Memory source")
    created_at: datetime = Field(..., description="Creation time")
    expires_at: datetime | None = Field(default=None, description="Expiration time")
    access_count: int = Field(default=0, ge=0, description="Access count")


class MemoriesResult(BaseModel):
    """Result of rlm_memories tool."""

    memories: list[MemoryInfo] = Field(default_factory=list, description="List of memories")
    total_count: int = Field(default=0, ge=0, description="Total matching memories")
    has_more: bool = Field(default=False, description="More results available")


class ForgetResult(BaseModel):
    """Result of rlm_forget tool."""

    deleted_count: int = Field(default=0, ge=0, description="Number of memories deleted")
    message: str = Field(..., description="Human-readable status message")


# ============ MULTI-AGENT SWARM MODELS (Phase 9.1) ============


class SwarmCreateResult(BaseModel):
    """Result of rlm_swarm_create tool."""

    swarm_id: str = Field(..., description="Unique swarm identifier")
    name: str = Field(..., description="Swarm name")
    max_agents: int = Field(..., description="Maximum agents")
    task_timeout: int = Field(..., description="Task timeout seconds")
    claim_timeout: int = Field(..., description="Claim timeout seconds")
    created_at: datetime = Field(..., description="Creation time")
    message: str = Field(..., description="Human-readable status message")


class SwarmJoinResult(BaseModel):
    """Result of rlm_swarm_join tool."""

    swarm_id: str = Field(..., description="Swarm ID")
    agent_id: str = Field(..., description="Agent ID")
    swarm_name: str = Field(..., description="Swarm name")
    current_agents: int = Field(..., ge=0, description="Current number of agents")
    max_agents: int = Field(..., description="Maximum agents allowed")
    message: str = Field(..., description="Human-readable status message")


class ClaimResult(BaseModel):
    """Result of rlm_claim tool."""

    claim_id: str = Field(..., description="Unique claim identifier")
    swarm_id: str = Field(..., description="Swarm ID")
    agent_id: str = Field(..., description="Agent ID")
    resource_type: str = Field(..., description="Resource type")
    resource_id: str = Field(..., description="Resource identifier")
    acquired: bool = Field(..., description="Whether claim was acquired")
    expires_at: datetime = Field(..., description="When claim expires")
    held_by: str | None = Field(
        default=None, description="If not acquired, agent ID holding the resource"
    )
    message: str = Field(..., description="Human-readable status message")


class ReleaseResult(BaseModel):
    """Result of rlm_release tool."""

    released: bool = Field(..., description="Whether resource was released")
    resource_type: str = Field(..., description="Resource type")
    resource_id: str = Field(..., description="Resource identifier")
    message: str = Field(..., description="Human-readable status message")


class StateGetResult(BaseModel):
    """Result of rlm_state_get tool."""

    swarm_id: str = Field(..., description="Swarm ID")
    key: str = Field(..., description="State key")
    value: Any | None = Field(default=None, description="State value (JSON)")
    version: int = Field(default=0, ge=0, description="State version for concurrency")
    exists: bool = Field(..., description="Whether key exists")
    updated_by: str | None = Field(default=None, description="Agent that last updated")
    updated_at: datetime | None = Field(default=None, description="Last update time")


class StateSetResult(BaseModel):
    """Result of rlm_state_set tool."""

    swarm_id: str = Field(..., description="Swarm ID")
    key: str = Field(..., description="State key")
    version: int = Field(..., ge=1, description="New state version")
    success: bool = Field(..., description="Whether update succeeded")
    conflict: bool = Field(
        default=False, description="True if version mismatch (optimistic lock failed)"
    )
    message: str = Field(..., description="Human-readable status message")


class BroadcastResult(BaseModel):
    """Result of rlm_broadcast tool."""

    event_id: str = Field(..., description="Unique event identifier")
    swarm_id: str = Field(..., description="Swarm ID")
    event_type: str = Field(..., description="Event type")
    delivered: bool = Field(..., description="Whether event was published")
    message: str = Field(..., description="Human-readable status message")


class TaskCreateResult(BaseModel):
    """Result of rlm_task_create tool."""

    task_id: str = Field(..., description="Unique task identifier")
    swarm_id: str = Field(..., description="Swarm ID")
    title: str = Field(..., description="Task title")
    priority: int = Field(..., description="Task priority")
    status: str = Field(default="pending", description="Task status")
    depends_on: list[str] = Field(default_factory=list, description="Dependencies")
    message: str = Field(..., description="Human-readable status message")


class TaskClaimResult(BaseModel):
    """Result of rlm_task_claim tool."""

    task_id: str | None = Field(
        default=None, description="Claimed task ID (null if none available)"
    )
    swarm_id: str = Field(..., description="Swarm ID")
    agent_id: str = Field(..., description="Agent ID")
    title: str | None = Field(default=None, description="Task title")
    description: str | None = Field(default=None, description="Task description")
    priority: int = Field(default=0, description="Task priority")
    claimed: bool = Field(..., description="Whether a task was claimed")
    message: str = Field(..., description="Human-readable status message")


class TaskCompleteResult(BaseModel):
    """Result of rlm_task_complete tool."""

    task_id: str = Field(..., description="Task ID")
    swarm_id: str = Field(..., description="Swarm ID")
    status: str = Field(..., description="Final task status ('completed' or 'failed')")
    completed: bool = Field(..., description="Whether task was completed successfully")
    unblocked_tasks: list[str] = Field(
        default_factory=list, description="Task IDs now unblocked by this completion"
    )
    message: str = Field(..., description="Human-readable status message")
