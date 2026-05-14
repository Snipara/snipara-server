# Self-Hosted Deployment

This guide describes the generic on-prem deployment path for Snipara Server.
Provider-specific production runbooks are not part of this repository.

## Requirements

- PostgreSQL 14 or newer with pgvector
- Redis 7 or newer
- Python 3.11 or newer
- Container runtime for Docker Compose or Kubernetes
- TLS termination through your ingress, reverse proxy, or load balancer
- Secret manager for database URLs, Redis URLs, API keys, and license keys

## Local Evaluation

```bash
cp .env.example .env
docker compose up --build
```

Then initialize a first local project and API key:

```bash
export DATABASE_URL="postgresql://snipara:snipara-dev-password@localhost:5433/snipara"
bash scripts/setup.sh
```

## Production Environment

Set these variables through your deployment platform or secret manager:

```text
DATABASE_URL
REDIS_URL
SNIPARA_LICENSE_KEY
SNIPARA_LICENSE_REQUIRED=true
CORS_ALLOWED_ORIGINS
```

Do not commit real `.env` files. Do not copy provider-specific production
configuration into this repository.

## Health Checks

```http
GET /health
GET /ready
GET /license
```

`/license` returns configuration status only. It does not expose the license
key.

## Upgrade Workflow

1. Pull the new release.
2. Review database migrations under `prisma/migrations/`.
3. Back up PostgreSQL.
4. Apply migrations in staging.
5. Run MCP smoke tests and application health checks.
6. Deploy to production.
7. Verify `/health`, `/ready`, and representative MCP tool calls.

## Release Hygiene

Before distributing a release artifact, verify that it does not contain:

- `.env` files
- cloud provider secrets
- private keys or certificates
- local developer paths
- internal evaluation reports
- debug payloads
- customer data
- SaaS monetization or operations runbooks
