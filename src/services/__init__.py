"""Services module for RLM MCP Server."""

from src.services.cache import QueryCache, TieredCache, get_cache, get_tiered_cache
from src.services.cache_stats import (
    generate_query_hash,
    get_l2_cached_result,
    invalidate_l2_cache,
    record_cache_hit,
    record_cache_miss,
    set_l2_cached_result,
)
from src.services.chunk_quality import (
    ChunkQuality,
    compute_chunk_quality,
    is_high_quality,
    quality_penalty,
)
from src.services.chunker import Chunk, DocumentChunker, get_chunker
from src.services.embeddings import EmbeddingsService, get_embeddings_service

# Hierarchical Tasks (Phase 17)
from src.services.htask_coordinator import (
    block_task,
    close_task,
    complete_task,
    create_feature_with_workstreams,
    create_htask,
    delete_htask,
    get_htask,
    get_htask_tree,
    recommend_batch,
    unblock_task,
    update_htask,
    verify_closure,
)
from src.services.htask_events import (
    cleanup_old_events,
    get_checkpoint_delta,
    get_events_since,
    get_htask_metrics,
    get_task_audit_trail,
    log_htask_event,
)
from src.services.htask_policy import (
    allows_hard_delete,
    allows_structural_update,
    can_close_with_exceptions,
    get_compat_mode,
    get_max_depth,
    get_policy,
    get_policy_raw,
    is_blocking_default,
    requires_evidence_on_complete,
    update_policy,
)
from src.services.index_health import (
    IndexHealth,
    QualityDistribution,
    StaleDocument,
    TierDistribution,
    compute_index_health,
    get_index_recommendations,
)
from src.services.indexer import DocumentIndexer, get_indexer
from src.services.search_analytics import (
    DailyStats,
    LatencyPercentiles,
    SearchAnalytics,
    ToolUsage,
    compute_search_analytics,
    get_query_trends,
    get_top_queries,
)
from src.services.tier_manager import (
    TIER_CONFIG,
    batch_update_chunk_access,
    compute_tier,
    should_promote,
    update_chunk_access,
)

__all__ = [
    "EmbeddingsService",
    "get_embeddings_service",
    "DocumentIndexer",
    "get_indexer",
    "DocumentChunker",
    "Chunk",
    "get_chunker",
    "QueryCache",
    "TieredCache",
    "get_cache",
    "get_tiered_cache",
    # Cache stats (Phase 8.1)
    "generate_query_hash",
    "record_cache_hit",
    "record_cache_miss",
    "get_l2_cached_result",
    "set_l2_cached_result",
    "invalidate_l2_cache",
    # Tier management
    "TIER_CONFIG",
    "compute_tier",
    "should_promote",
    "update_chunk_access",
    "batch_update_chunk_access",
    # Chunk quality
    "ChunkQuality",
    "compute_chunk_quality",
    "is_high_quality",
    "quality_penalty",
    # Index health (Sprint 3)
    "IndexHealth",
    "TierDistribution",
    "QualityDistribution",
    "StaleDocument",
    "compute_index_health",
    "get_index_recommendations",
    # Search analytics (Sprint 3)
    "SearchAnalytics",
    "LatencyPercentiles",
    "ToolUsage",
    "DailyStats",
    "compute_search_analytics",
    "get_query_trends",
    "get_top_queries",
    # Hierarchical Tasks (Phase 17)
    "create_htask",
    "create_feature_with_workstreams",
    "get_htask",
    "get_htask_tree",
    "update_htask",
    "block_task",
    "unblock_task",
    "complete_task",
    "verify_closure",
    "close_task",
    "delete_htask",
    "recommend_batch",
    "log_htask_event",
    "get_events_since",
    "get_task_audit_trail",
    "get_checkpoint_delta",
    "get_htask_metrics",
    "cleanup_old_events",
    "get_policy",
    "get_policy_raw",
    "update_policy",
    "can_close_with_exceptions",
    "is_blocking_default",
    "get_max_depth",
    "requires_evidence_on_complete",
    "allows_structural_update",
    "allows_hard_delete",
    "get_compat_mode",
]
