"""Internal embedding service for Snipara backend workers.

This app is intended for private Docker-network use only. It centralizes BGE
model loading so MCP workers do not each keep their own large model copy.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .config import settings
from .services.embeddings import (
    LIGHT_MODEL_NAME,
    MODEL_NAME,
    EmbeddingsService,
)

logger = logging.getLogger(__name__)


class EmbedRequest(BaseModel):
    """Single-text embedding request."""

    text: str = Field(min_length=1)
    model: str = MODEL_NAME
    timeout_seconds: float = Field(default=30.0, gt=0.0, le=300.0)


class EmbedBatchRequest(BaseModel):
    """Batch embedding request."""

    texts: list[str] = Field(default_factory=list)
    model: str = MODEL_NAME
    batch_size: int = Field(default=32, ge=1, le=256)
    timeout_seconds: float = Field(default=60.0, gt=0.0, le=600.0)


def _validate_model(model: str) -> str:
    if model not in {MODEL_NAME, LIGHT_MODEL_NAME}:
        raise HTTPException(status_code=400, detail=f"Unsupported embedding model: {model}")
    return model


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load embedding models once in the dedicated embedding process."""
    logger.info("Starting Snipara internal embedding service")
    if settings.preload_embeddings:
        EmbeddingsService.preload_all()
    else:
        logger.info("Embedding preload disabled; service will lazy-load models")
    yield


app = FastAPI(
    title="Snipara Internal Embedding Service",
    description="Private embedding inference service for MCP backend workers",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Lightweight liveness probe."""
    return {"status": "healthy"}


@app.get("/ready")
async def ready() -> JSONResponse:
    """Readiness probe for model preload state."""
    primary_loaded = EmbeddingsService.get_instance(MODEL_NAME).is_loaded()
    light_loaded = EmbeddingsService.get_instance(LIGHT_MODEL_NAME).is_loaded()
    ready_status = primary_loaded if settings.preload_embeddings else True
    content = {
        "status": "ready" if ready_status else "not_ready",
        "checks": {
            "embedding_preload_enabled": settings.preload_embeddings,
            "embedding_primary_loaded": primary_loaded,
            "embedding_light_loaded": light_loaded,
        },
    }
    return JSONResponse(content=content, status_code=200 if ready_status else 503)


@app.post("/embed")
async def embed(request: EmbedRequest) -> dict[str, object]:
    """Generate a single embedding."""
    model_name = _validate_model(request.model)
    service = EmbeddingsService.get_instance(model_name)
    embedding = await service.embed_text_async(request.text, timeout=request.timeout_seconds)
    return {
        "model": model_name,
        "dimension": service.dimension,
        "embedding": embedding,
    }


@app.post("/embed-batch")
async def embed_batch(request: EmbedBatchRequest) -> dict[str, object]:
    """Generate embeddings for multiple texts."""
    model_name = _validate_model(request.model)
    if not request.texts:
        return {"model": model_name, "dimension": 0, "embeddings": []}

    service = EmbeddingsService.get_instance(model_name)
    embeddings = await service.embed_texts_async(
        request.texts,
        batch_size=request.batch_size,
        timeout=request.timeout_seconds,
    )
    return {
        "model": model_name,
        "dimension": service.dimension,
        "embeddings": embeddings,
    }
