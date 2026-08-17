# Self-Hosted Deployment

This guide describes the generic deployment path for Snipara Server. Provider-
specific production runbooks are intentionally kept outside this repository.

## Requirements

- PostgreSQL 14 or newer with pgvector
- Redis 7 or newer (recommended; the server has an in-memory fallback)
- Python 3.11 or newer
- Docker Compose or another container runtime
- TLS termination through an operator-controlled ingress or reverse proxy
- Secret management for DATABASE_URL, Redis URL and the local API key

## Local deployment

```bash
cp .env.example .env
# Set a long random SNIPARA_LOCAL_API_KEY in .env.
docker compose up --build
```

In another terminal:

```bash
set -a
source .env
set +a
bash scripts/setup.sh
```

The setup creates one local workspace at the slug local. It never creates a
Cloud account or sends project data to Snipara.

## Production configuration

Set these through the deployment platform:

```text
DATABASE_URL
REDIS_URL
SNIPARA_LOCAL_API_KEY
CORS_ALLOWED_ORIGINS
```

Optional:

```text
PRELOAD_EMBEDDINGS
EMBEDDING_SERVICE_URL
SENTRY_DSN
USAGE_TRACKING_ENABLED
```

Do not commit real environment files or credentials.

## Health checks

```text
GET /health
GET /ready
GET /capabilities
```

The MCP smoke endpoint is POST /mcp/local with X-API-Key authentication.

## Upgrade workflow

1. Pin a released Snipara Server tag or image digest.
2. Back up PostgreSQL and verify restore procedures.
3. Review public schema changes and test them on a copy.
4. Deploy to staging and run health plus MCP smoke tests.
5. Promote the same immutable artifact.
6. Keep the previous image digest available for rollback.

The local setup script may use Prisma db push only against a fresh local database.
Production Cloud migrations use the private migration process.

## Release hygiene

Before distributing an artifact, verify that it contains no environment files,
credentials, customer documents, private Cloud code, internal runbooks,
developer paths or debug payloads.
