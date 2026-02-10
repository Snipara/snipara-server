"""Pydantic models for RLM MCP Server request/response schemas.

This module re-exports all models for backward compatibility.
Import from submodules directly for cleaner imports:

    from src.models.enums import ToolName, Plan
    from src.models.context import ContextQueryResult
"""

# ============ ENUMS ============
# ============ AGENT MODELS ============
from .agent import (
    BroadcastResult,
    ClaimResult,
    ForgetResult,
    MemoriesResult,
    MemoryInfo,
    RecalledMemory,
    RecallResult,
    ReleaseResult,
    RememberResult,
    StateGetResult,
    StateSetResult,
    SwarmCreateResult,
    SwarmJoinResult,
    TaskClaimResult,
    TaskCompleteResult,
    TaskCreateResult,
)

# ============ CONTEXT QUERY MODELS ============
from .context import (
    ContextQueryResult,
    ContextSection,
    ContextSectionRef,
    DecomposeResult,
    GetChunkResult,
    MultiQueryResult,
    MultiQueryResultItem,
    PlanResult,
    PlanStep,
    SubQuery,
)

# ============ DOCUMENT MODELS ============
from .documents import (
    IndexJobCreateResponse,
    IndexJobStatusResponse,
    RequestAccessResult,
    SettingsResult,
    SyncDocumentsResult,
    UploadDocumentResult,
)
from .enums import (
    AgentMemoryScope,
    AgentMemoryType,
    DecomposeStrategy,
    DocumentCategoryEnum,
    IndexJobStatus,
    Plan,
    PlanStrategy,
    SearchMode,
    SummaryType,
    ToolName,
)

# ============ REQUEST MODELS ============
from .requests import (
    AskParams,
    BroadcastParams,
    ClaimParams,
    ContextQueryParams,
    DecomposeParams,
    DeleteSummaryParams,
    ForgetParams,
    GetSummariesParams,
    GetTemplateParams,
    InjectParams,
    ListTemplatesParams,
    MCPRequest,
    MemoriesParams,
    MultiProjectQueryParams,
    MultiQueryItem,
    MultiQueryParams,
    PlanParams,
    ReadParams,
    RecallParams,
    ReleaseParams,
    RememberParams,
    RequestAccessParams,
    SearchParams,
    SharedContextParams,
    StateGetParams,
    StateSetParams,
    StoreSummaryParams,
    SwarmCreateParams,
    SwarmJoinParams,
    SyncDocumentItem,
    SyncDocumentsParams,
    TaskClaimParams,
    TaskCompleteParams,
    TaskCreateParams,
)

# ============ RESPONSE MODELS ============
from .responses import (
    DocumentInfo,
    HealthResponse,
    LimitsInfo,
    MCPResponse,
    ProjectContext,
    ProjectSettings,
    ReadyResponse,
    SectionInfo,
    StatsResponse,
    ToolResult,
    UsageInfo,
)

# ============ SHARED CONTEXT MODELS ============
from .shared import (
    GetTemplateResult,
    ListTemplatesResult,
    PromptTemplateInfo,
    SharedContextResult,
    SharedDocumentInfo,
)

# ============ SUMMARY MODELS ============
from .summary import (
    DeleteSummaryResult,
    GetSummariesResult,
    StoreSummaryResult,
    SummaryInfo,
)

__all__ = [
    # Enums
    "AgentMemoryScope",
    "AgentMemoryType",
    "DecomposeStrategy",
    "DocumentCategoryEnum",
    "IndexJobStatus",
    "Plan",
    "PlanStrategy",
    "SearchMode",
    "SummaryType",
    "ToolName",
    # Request models
    "AskParams",
    "BroadcastParams",
    "ClaimParams",
    "ContextQueryParams",
    "DecomposeParams",
    "DeleteSummaryParams",
    "ForgetParams",
    "GetSummariesParams",
    "GetTemplateParams",
    "InjectParams",
    "ListTemplatesParams",
    "MCPRequest",
    "MemoriesParams",
    "MultiProjectQueryParams",
    "MultiQueryItem",
    "MultiQueryParams",
    "PlanParams",
    "ReadParams",
    "RecallParams",
    "ReleaseParams",
    "RememberParams",
    "RequestAccessParams",
    "SearchParams",
    "SharedContextParams",
    "StateGetParams",
    "StateSetParams",
    "StoreSummaryParams",
    "SwarmCreateParams",
    "SwarmJoinParams",
    "SyncDocumentItem",
    "SyncDocumentsParams",
    "TaskClaimParams",
    "TaskCompleteParams",
    "TaskCreateParams",
    # Response models
    "DocumentInfo",
    "HealthResponse",
    "LimitsInfo",
    "MCPResponse",
    "ProjectContext",
    "ProjectSettings",
    "ReadyResponse",
    "SectionInfo",
    "StatsResponse",
    "ToolResult",
    "UsageInfo",
    # Context query models
    "ContextQueryResult",
    "ContextSection",
    "ContextSectionRef",
    "DecomposeResult",
    "GetChunkResult",
    "MultiQueryResult",
    "MultiQueryResultItem",
    "PlanResult",
    "PlanStep",
    "SubQuery",
    # Summary models
    "DeleteSummaryResult",
    "GetSummariesResult",
    "StoreSummaryResult",
    "SummaryInfo",
    # Shared context models
    "GetTemplateResult",
    "ListTemplatesResult",
    "PromptTemplateInfo",
    "SharedContextResult",
    "SharedDocumentInfo",
    # Agent models
    "BroadcastResult",
    "ClaimResult",
    "ForgetResult",
    "MemoriesResult",
    "MemoryInfo",
    "RecalledMemory",
    "RecallResult",
    "ReleaseResult",
    "RememberResult",
    "StateGetResult",
    "StateSetResult",
    "SwarmCreateResult",
    "SwarmJoinResult",
    "TaskClaimResult",
    "TaskCompleteResult",
    "TaskCreateResult",
    # Document models
    "IndexJobCreateResponse",
    "IndexJobStatusResponse",
    "RequestAccessResult",
    "SettingsResult",
    "SyncDocumentsResult",
    "UploadDocumentResult",
]
