"""Semantic scoring for RLM search engine.

This module provides semantic similarity scoring using embeddings.
Two paths are supported:
1. Pre-computed embeddings via pgvector (fast, preferred)
2. On-the-fly embeddings (fallback when chunks not available)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ..services.embeddings import EmbeddingsService

logger = logging.getLogger(__name__)


class SectionProtocol(Protocol):
    """Protocol for Section-like objects."""

    id: str
    title: str
    content: str
    start_line: int
    end_line: int
    level: int


class SemanticScorer:
    """Calculates semantic similarity scores for document sections.

    Supports two modes:
    1. Pre-computed chunks from pgvector (fast, ~50ms)
    2. On-the-fly embedding (slower fallback, ~3-5s for 30 sections)
    """

    def __init__(
        self,
        project_id: str,
        embeddings_service: "EmbeddingsService | None" = None,
    ):
        """Initialize the semantic scorer.

        Args:
            project_id: The project ID for chunk lookups.
            embeddings_service: Optional embeddings service for on-the-fly scoring.
        """
        self.project_id = project_id
        self.embeddings_service = embeddings_service

    async def calculate_scores_from_chunks(
        self,
        query: str,
        db: "any",  # PrismaClient
        limit: int = 50,
        min_similarity: float = 0.3,
        sections: list[SectionProtocol] | None = None,
    ) -> dict[str, float]:
        """Calculate semantic scores using pre-computed chunk embeddings via pgvector.

        This is the fast path for semantic search - uses embeddings that were
        pre-computed during document indexing rather than generating them on-the-fly.

        Args:
            query: The search query string.
            db: Database client for chunk lookups.
            limit: Maximum number of chunks to retrieve.
            min_similarity: Minimum cosine similarity threshold (0-1).
            sections: Optional sections to map chunks back to.

        Returns:
            Dictionary mapping section IDs to their semantic similarity scores (0-1).
        """
        # Import here to avoid circular imports
        from ..services.indexer import DocumentIndexer

        indexer = DocumentIndexer(db)

        try:
            result = await indexer.search_similar(
                project_id=self.project_id,
                query=query,
                limit=limit,
                min_similarity=min_similarity,
            )

            # If no sections provided, return chunk scores directly
            if sections is None:
                return {
                    chunk.get("id", ""): chunk.get("similarity", 0.0)
                    for chunk in result.get("results", [])
                }

            # Map chunk results back to section IDs by line overlap
            scores: dict[str, float] = {}
            for chunk in result.get("results", []):
                chunk_start = chunk.get("start_line", 0)
                chunk_end = chunk.get("end_line", 0)
                chunk_similarity = chunk.get("similarity", 0.0)

                for section in sections:
                    # Check if chunk overlaps with section (by line range)
                    if chunk_start <= section.end_line and chunk_end >= section.start_line:
                        # Use max score if section appears in multiple chunks
                        current_score = scores.get(section.id, 0.0)
                        scores[section.id] = max(current_score, chunk_similarity)

            logger.info(
                f"Chunk-based semantic search: {len(result.get('results', []))} chunks, "
                f"{len(scores)} sections scored"
            )
            return scores

        except Exception as e:
            logger.warning(f"Chunk-based semantic search failed: {e}")
            return {}

    async def calculate_scores_on_the_fly(
        self,
        query: str,
        sections: list[SectionProtocol],
        candidate_ids: set[str] | None = None,
        max_sections: int = 30,
    ) -> dict[str, float]:
        """Calculate semantic similarity scores for sections (on-the-fly fallback path).

        Uses the *light* embedding model (bge-small-en-v1.5, 384 dims) which is ~10x
        faster than bge-large on CPU. This path is only used when pre-computed pgvector
        chunks are not available. Both query and section embeddings are computed fresh
        so dimension mismatch with pgvector (1024 dims) is not an issue.

        Args:
            query: The search query string.
            sections: List of sections to score.
            candidate_ids: If provided, only embed these section IDs (e.g. top keyword hits).
            max_sections: Hard cap on sections to embed (default 30). bge-small-en-v1.5
                takes ~0.3s per text on Railway CPU; 30 sections ≈ 3-5s.

        Returns:
            Dictionary mapping section IDs to similarity scores (0-1).
        """
        if not sections:
            return {}

        if self.embeddings_service is None:
            logger.warning("No embeddings service available for on-the-fly scoring")
            return {}

        try:
            # Filter to candidate sections if provided, otherwise use all
            if candidate_ids is not None:
                filtered_sections = [s for s in sections if s.id in candidate_ids]
            else:
                filtered_sections = list(sections)

            # Hard cap to prevent batch embedding timeout on large projects
            if len(filtered_sections) > max_sections:
                logger.info(
                    f"Capping on-the-fly embedding from {len(filtered_sections)} to {max_sections} sections"
                )
                filtered_sections = filtered_sections[:max_sections]

            if not filtered_sections:
                return {}

            # Generate query embedding (async to avoid blocking event loop)
            query_embedding = await self.embeddings_service.embed_text_async(query)

            # Generate section embeddings (title + truncated content)
            # Using 120 chars to reduce tokenization cost on CPU.
            # Title carries the primary semantic signal; content adds context.
            section_texts = [
                f"{s.title}\n{s.content[:120]}"
                for s in filtered_sections
            ]
            section_embeddings = await self.embeddings_service.embed_texts_async(section_texts)

            # Calculate similarities
            similarities = self.embeddings_service.cosine_similarity(
                query_embedding, section_embeddings
            )

            # Map to section IDs
            return {
                section.id: similarity
                for section, similarity in zip(filtered_sections, similarities)
            }
        except Exception as e:
            logger.warning(f"Semantic search failed, falling back to empty scores: {e}")
            return {}


async def calculate_semantic_scores(
    query: str,
    sections: list[SectionProtocol],
    embeddings_service: "EmbeddingsService",
    candidate_ids: set[str] | None = None,
    max_sections: int = 30,
) -> dict[str, float]:
    """Convenience function for on-the-fly semantic scoring.

    Args:
        query: The search query string.
        sections: List of sections to score.
        embeddings_service: The embeddings service to use.
        candidate_ids: If provided, only embed these section IDs.
        max_sections: Hard cap on sections to embed.

    Returns:
        Dictionary mapping section IDs to similarity scores (0-1).
    """
    scorer = SemanticScorer(
        project_id="",  # Not needed for on-the-fly
        embeddings_service=embeddings_service,
    )
    return await scorer.calculate_scores_on_the_fly(
        query=query,
        sections=sections,
        candidate_ids=candidate_ids,
        max_sections=max_sections,
    )
