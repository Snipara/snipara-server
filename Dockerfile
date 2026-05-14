# syntax=docker/dockerfile:1

# ============ BUILD STAGE ============
FROM python:3.12-slim AS builder

WORKDIR /app
ARG TORCH_VERSION=2.11.0

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Install Python dependencies
COPY requirements-prod.txt .
COPY wheelhouse ./wheelhouse
RUN pip install --no-cache-dir --upgrade pip && \
    if find wheelhouse -maxdepth 1 -name 'torch-*.whl' | grep -q .; then \
        pip install --no-cache-dir --no-index --find-links=wheelhouse "torch==${TORCH_VERSION}"; \
    else \
        pip install --no-cache-dir "torch==${TORCH_VERSION}"; \
    fi && \
    rm -rf wheelhouse && \
    pip install --no-cache-dir -r requirements-prod.txt

# Create appuser home directory structure for Prisma and model caches
RUN mkdir -p \
    /home/appuser/.cache/prisma \
    /home/appuser/.cache/huggingface \
    /home/appuser/.cache/torch/sentence_transformers
ENV HOME="/home/appuser"
ENV HF_HOME="/home/appuser/.cache/huggingface"
ENV TRANSFORMERS_CACHE="/home/appuser/.cache/huggingface"
ENV SENTENCE_TRANSFORMERS_HOME="/home/appuser/.cache/torch/sentence_transformers"

# Generate Prisma client (with HOME set so binaries go to /home/appuser/.cache)
COPY prisma ./prisma
RUN prisma generate


# ============ RUNTIME STAGE ============
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install runtime dependencies required by Prisma's bundled Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    libatomic1 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash appuser

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy Prisma binaries and cache directory skeleton from builder.
# Embedding weights are intentionally not baked into the image; production uses
# dedicated cache volumes plus an explicit warmup step.
COPY --from=builder --chown=appuser:appgroup /home/appuser/.cache /home/appuser/.cache

# Set HOME and cache variables (must match build stage)
ENV HOME="/home/appuser"
ENV HF_HOME="/home/appuser/.cache/huggingface"
ENV TRANSFORMERS_CACHE="/home/appuser/.cache/huggingface"
ENV SENTENCE_TRANSFORMERS_HOME="/home/appuser/.cache/torch/sentence_transformers"

# Copy application code
COPY --chown=appuser:appgroup src ./src

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check - use /ready for full readiness verification
# start-period=120s accounts for embedding model preload + DB connection
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8000/ready', timeout=10); exit(0 if r.status_code == 200 else 1)" || exit 1

# Run the MCP server with configurable Gunicorn workers. Production defaults to
# fewer MCP workers because embeddings can run in a separate internal service.
CMD ["sh", "-c", "exec gunicorn src.server:app -w ${WEB_CONCURRENCY:-2} -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 --timeout ${GUNICORN_TIMEOUT:-120} --graceful-timeout ${GUNICORN_GRACEFUL_TIMEOUT:-30}"]
