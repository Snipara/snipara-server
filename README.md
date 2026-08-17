# Snipara Server

Open source, self-hosted MCP server for project context, semantic search and
persistent agent memory.

The server is designed to run on infrastructure you control. Documents,
embeddings, memories, logs and usage records stay in your PostgreSQL database.
No Snipara Cloud account, commercial license key or hosted service is required.

## What is included

- FastAPI REST and streamable HTTP MCP transport
- project-local documents, chunks, summaries and embeddings
- persistent memory, decisions and session context
- optional code graph and multi-agent coordination tools
- PostgreSQL + pgvector and Redis local Compose services
- local API-key authentication and local-only usage tracking
- tests, Docker build and a reproducible local setup

## What is deliberately excluded

The public server is not the Snipara Cloud application. It does not include
the web UI, login/OAuth/device flow, SaaS multi-tenancy, billing, plans,
resellers, partners, integrator administration, customer analytics or private
deployment secrets.

Those surfaces remain in the private Cloud repository and consume tagged,
immutable Snipara Server releases.

## Quickstart with Docker

```bash
cp .env.example .env
# Replace the placeholder SNIPARA_LOCAL_API_KEY with a long random value.
docker compose up --build
```

In another terminal, initialize the local schema and workspace:

```bash
set -a
source .env
set +a
bash scripts/setup.sh
```

Check the server:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

The local MCP endpoint is:

```text
http://localhost:8000/mcp/local
```

Example MCP configuration:

```json
{
  "mcpServers": {
    "snipara": {
      "type": "http",
      "url": "http://localhost:8000/mcp/local",
      "headers": {
        "X-API-Key": "<SNIPARA_LOCAL_API_KEY>"
      }
    }
  }
}
```

## Configuration

Required:

- DATABASE_URL
- SNIPARA_LOCAL_API_KEY

Recommended local services:

- REDIS_URL for distributed rate limits, cache and event streaming
- CORS_ALLOWED_ORIGINS when a browser client is used

Optional:

- PRELOAD_EMBEDDINGS=false to load models lazily
- EMBEDDING_SERVICE_URL for an operator-managed embedding service
- SENTRY_DSN only when the operator explicitly opts in to external error
  reporting
- USAGE_TRACKING_ENABLED=false to disable the local PostgreSQL query ledger

Never put real keys, customer data or provider credentials in Git.

## Development

```bash
python -m pip install -e ".[dev]"
prisma generate --schema prisma/schema.prisma
DATABASE_URL="postgresql://..." prisma validate --schema prisma/schema.prisma
ruff check src tests
pytest -q
```

prisma db push is supported by scripts/init-db.sh for a fresh local database
only. Production Cloud schema changes use the private migration path.

## License

Snipara Server is licensed under Apache-2.0. See [LICENSE](LICENSE) and
[docs/LICENSING.md](docs/LICENSING.md).

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [OSS boundary and compatibility schema](docs/OSS_BOUNDARY.md)
- [Releasing](docs/RELEASING.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Licensing](docs/LICENSING.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
