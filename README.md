# Snipara Server

Self-hosted Snipara Server is the enterprise runtime for project-owned AI
memory and source-backed context retrieval.

Snipara gives MCP-compatible agents and internal applications a shared project
memory layer that survives sessions, users, tools, and model changes. Your
organization keeps the data, the database, and the deployment boundary.

## Repository Boundary

This repository is the on-prem server distribution. It includes:

- FastAPI application entrypoint
- streamable HTTP MCP transport
- REST compatibility routes
- project and team context APIs
- reviewed project memory tools
- shared context and decision tools
- document indexing, chunk retrieval, and code graph retrieval
- Docker Compose setup for local evaluation

This repository intentionally excludes:

- SaaS web application code
- SaaS monetization and operations workflows
- internal evaluation harnesses and generated performance reports
- private production deployment runbooks
- local developer paths and private infrastructure references
- committed secrets or real environment files

## License

Snipara Server is commercial, source-available software for enterprise
self-hosted deployments. Production use requires a valid Snipara enterprise
license agreement and license key.

The source is provided under the Functional Source License, Version 1.1, with
an Apache-2.0 future license. See [LICENSE](LICENSE) and
[docs/LICENSING.md](docs/LICENSING.md).

## Quickstart

```bash
cp .env.example .env
docker compose up --build
```

In another shell:

```bash
export DATABASE_URL="postgresql://snipara:snipara-dev-password@localhost:5433/snipara"
bash scripts/setup.sh
```

Health checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/license
```

## MCP Configuration

Use the API key created by `scripts/setup.sh`:

```json
{
  "mcpServers": {
    "snipara": {
      "type": "http",
      "url": "http://localhost:8000/mcp/my-project",
      "headers": {
        "X-API-Key": "rlm_example_replace_me"
      }
    }
  }
}
```

## Production Configuration

Production deployments should set environment variables through a secret
manager, not committed files.

Required:

- `DATABASE_URL`
- `REDIS_URL`
- `SNIPARA_LICENSE_KEY`
- `SNIPARA_LICENSE_REQUIRED=true`
- `CORS_ALLOWED_ORIGINS`

Optional:

- `SENTRY_DSN`
- `PRELOAD_EMBEDDINGS`
- `EMBEDDING_SERVICE_URL`
- `ENABLE_CODE_INGESTION`
- `ENABLE_INTEGRATOR_ADMIN_API`

The base on-prem package leaves SaaS/admin commercial surfaces disabled by
default. Enable only the surfaces covered by the enterprise agreement and
deployment design.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Licensing](docs/LICENSING.md)
- [Self-hosted Enterprise](SELF_HOSTED_ENTERPRISE.md)
- [Contributing](CONTRIBUTING.md)

## Security

Do not commit:

- `.env` files
- license keys
- database URLs with credentials
- API keys
- private certificates or SSH keys
- customer data
- evaluation reports or debug payloads

Run secret scanning before distributing a fork or release artifact.
