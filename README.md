# Snipara Server

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-101828?style=flat-square&logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-MCP%20backend-101828?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-ready-101828?style=flat-square&logo=docker)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-FSL--1.1--Apache--2.0-101828?style=flat-square)](LICENSE)

The source-available MCP backend behind Snipara.

Snipara turns large documentation, code, team standards, and project memory into compact, relevant context for AI tools. Instead of sending a whole repository or a pile of docs to an LLM, Snipara retrieves the right pieces, fits them into a token budget, and keeps decisions, shared context, and workflow state reusable across sessions.

```text
Docs, code, memory, standards
        |
        v
Snipara Server
  - context retrieval
  - memory and decisions
  - shared team context
  - code and document indexing
  - MCP tools
        |
        v
Any MCP-compatible AI client
```

Snipara is model-agnostic. It optimizes context delivery; you keep using your own LLM, IDE, agent, or orchestration layer.

## What This Repo Is

`snipara-server` is the FastAPI MCP server. It exposes Snipara's HTTP APIs and MCP tools, runs retrieval and indexing, stores project memory, and connects to PostgreSQL and Redis.

It is not the local MCP client package. If you only want to connect an AI client to hosted Snipara, install [`snipara-mcp`](https://pypi.org/project/snipara-mcp/) or use the hosted HTTP MCP endpoint.

| Component | Purpose |
| --- | --- |
| `snipara-server` | Self-hostable FastAPI backend and MCP HTTP server |
| `snipara-mcp` | Thin local MCP client/stdio bridge for AI clients |
| `snipara.com` | Hosted product, dashboard, billing, docs, and managed API |

## Why Teams Use Snipara

- **Less context waste**: retrieve focused context instead of dumping entire repos or docs.
- **Better continuity**: persist decisions, learnings, conventions, and handoffs.
- **Team-aware retrieval**: combine project-specific context with approved shared standards.
- **Agent-ready workflows**: expose memory, tasks, swarms, htasks, and orchestration through MCP tools.
- **Self-hostable backend**: run the MCP server close to your data when compliance or data residency matters.

## Features

### Context Retrieval

- Semantic, keyword, and hybrid search
- Token-budgeted responses
- Source references and chunk retrieval
- Auto-decomposition for complex queries
- Index health checks and reindex recommendations

### Durable Memory

- Remember and recall project learnings
- Decision logs with supersession
- Evidence-aware memory lifecycle
- Session memory, compaction, and daily briefs

### Shared Team Context

- Team standards and templates
- Shared collections linked to projects
- Multi-project and team-scoped queries
- Context allocation by priority and token budget

### Agent Workflows

- Tasks, hierarchical tasks, checkpoints, and audit trails
- Swarms, claims, broadcasts, and agent profiles
- Journal entries and run summaries
- Tool recommendations for better agent routing

### Operations

- Health and readiness endpoints
- Background indexing jobs
- Redis-backed rate limiting
- Security headers and CORS controls
- Sentry integration
- Docker Compose stack with PostgreSQL + pgvector and Redis

## Quick Start

### 1. Clone

```bash
git clone https://github.com/Snipara/snipara-server.git
cd snipara-server
```

### 2. Start the stack

```bash
docker compose up --build
```

This starts:

- Snipara Server on `http://localhost:8000`
- PostgreSQL with pgvector on `localhost:5433`
- Redis on `localhost:6380`

### 3. Create your first project and API key

In a second terminal:

```bash
export DATABASE_URL="postgresql://snipara:snipara@localhost:5433/snipara"
bash scripts/setup.sh
```

The setup script prints a project slug and an API key. Keep the API key private.

### 4. Check the server

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

### 5. Connect an MCP client

Use the project slug and API key printed by `scripts/setup.sh`.

```json
{
  "mcpServers": {
    "snipara": {
      "type": "http",
      "url": "http://localhost:8000/mcp/my-project",
      "headers": {
        "X-API-Key": "rlm_your_key_here"
      }
    }
  }
}
```

Then ask your AI client to list tools or call `rlm_help`.

## Hosted MCP

For hosted Snipara, use:

```text
https://api.snipara.com/mcp/{project_slug}
```

With:

```http
X-API-Key: rlm_...
```

Team-scoped MCP is available at:

```text
https://api.snipara.com/mcp/team/{team_id}
```

## Common MCP Tools

| Tool | Use it for |
| --- | --- |
| `rlm_help` | Discover the right Snipara tool for a task |
| `rlm_context_query` | Retrieve optimized context from docs/code/memory |
| `rlm_ask` | Quick question over indexed project context |
| `rlm_search` | Keyword or pattern search |
| `rlm_read` | Read exact lines from indexed content |
| `rlm_get_chunk` | Retrieve a referenced chunk by ID |
| `rlm_remember` | Store durable project memory |
| `rlm_recall` | Retrieve relevant memory for the current task |
| `rlm_decision_create` | Record a decision with rationale |
| `rlm_shared_context` | Pull approved team or project standards |
| `rlm_multi_project_query` | Search across team projects |
| `rlm_index_health` | Check whether a project needs reindexing |
| `rlm_index_recommendations` | Get actionable indexing recommendations |
| `rlm_upload_document` | Add a document to the project index |
| `rlm_sync_documents` | Batch-sync documents |
| `rlm_task_create` | Create agent work items |
| `rlm_htask_create_feature` | Create hierarchical feature work |
| `rlm_swarm_create` | Coordinate multi-agent work |

The full tool list is available through the MCP `tools/list` method.

## HTTP Endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Lightweight liveness check |
| `GET /ready` | Database and embedding readiness |
| `POST /mcp/{project_slug}` | Streamable HTTP MCP endpoint |
| `POST /mcp/team/{team_id}` | Team-scoped MCP endpoint |
| `POST /v1/{project_id}/mcp` | Legacy project MCP API |
| `GET /v1/{project_id}/context` | Current project context |
| `GET /v1/{project_id}/limits` | Plan and usage limits |
| `GET /v1/{project_id}/stats` | Usage statistics |
| `POST /v1/{project_id}/reindex` | Start an incremental or full reindex |
| `GET /v1/{project_id}/reindex/{job_id}` | Read reindex job status |
| `GET /v1/{project_id}/memories/recall` | Recall project memory |
| `POST /v1/{project_id}/memories` | Store project memory |

Interactive OpenAPI docs are available locally at:

```text
http://localhost:8000/docs
```

## Configuration

Create `.env` from `.env.example` or export variables directly.

| Variable | Required | Description |
| --- | --- | --- |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `REDIS_URL` | No | Redis connection string for rate limiting and cache |
| `HOST` | No | Bind host, default `0.0.0.0` |
| `PORT` | No | Bind port, default `8000` |
| `DEBUG` | No | Development mode flag |
| `CORS_ALLOWED_ORIGINS` | Production | Comma-separated allowed origins |
| `SNIPARA_LICENSE_KEY` | No | Optional self-hosted license key |
| `INTERNAL_API_SECRET` | No | Secret for internal server-to-server operations |
| `SENTRY_DSN` | No | Optional Sentry DSN |
| `ENVIRONMENT` | No | Environment label for logs/Sentry |

Production note: do not leave `CORS_ALLOWED_ORIGINS=*` in a public deployment.

## Local Development

### Install

```bash
uv sync --extra dev
```

### Run the API

```bash
export DATABASE_URL="postgresql://snipara:snipara@localhost:5433/snipara"
export REDIS_URL="redis://localhost:6380"
uv run uvicorn src.server:app --reload --host 0.0.0.0 --port 8000
```

### Run checks

```bash
uv run ruff check .
uv run mypy src
uv run pytest
```

### Regenerate API docs

```bash
uv run python docs/generate-api-docs.py
```

## Indexing and Reindexing

Snipara indexes documents into chunks and embeddings so the MCP tools can retrieve focused context.

Trigger an incremental reindex:

```bash
curl -X POST "http://localhost:8000/v1/my-project/reindex" \
  -H "X-API-Key: rlm_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{"mode":"incremental"}'
```

Trigger a full reindex:

```bash
curl -X POST "http://localhost:8000/v1/my-project/reindex" \
  -H "X-API-Key: rlm_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{"mode":"full"}'
```

Use `rlm_index_health` and `rlm_index_recommendations` from MCP when you want the agent to detect indexing issues itself.

## Architecture

```text
MCP client or AI agent
        |
        | HTTP MCP / JSON-RPC
        v
FastAPI app
        |
        +-- MCP transport and tool registry
        +-- RLM context engine
        +-- memory, decisions, tasks, swarms
        +-- background indexing jobs
        |
        +--> PostgreSQL + pgvector
        +--> Redis
```

Important directories:

| Path | Purpose |
| --- | --- |
| `src/server.py` | FastAPI application and HTTP endpoints |
| `src/mcp_transport.py` | Streamable HTTP MCP transport |
| `src/mcp/tool_defs.py` | MCP tool definitions and tiers |
| `src/rlm_engine.py` | Context retrieval and orchestration engine |
| `src/services/` | Indexing, memory, swarms, tasks, analytics |
| `src/models/` | Pydantic request/response models |
| `prisma/schema.prisma` | Python Prisma schema copy |
| `scripts/` | Setup, indexing, and operational scripts |
| `snipara-mcp/` | Local MCP client package source |
| `snipara-sdk/` | Python SDK source |

## Production Deployment

The recommended public deployment path is Docker behind a TLS reverse proxy.

Minimum production stack:

- PostgreSQL 14+ with pgvector
- Redis 7+
- Snipara Server container
- TLS termination through Traefik, nginx, Cloudflare, or a managed load balancer
- Explicit CORS origins
- Private API keys and internal secrets managed outside Git

Example:

```bash
docker compose up -d --build
curl http://localhost:8000/health
```

For managed Snipara production, the operational deployment is handled from the main Snipara deployment scripts. This repository is the backend build/source mirror; keep it synchronized with the monorepo backend before deployment.

## Security Model

Snipara Server is designed to keep retrieval useful without making the backend permissive by default.

- API keys are required for project MCP access.
- Team-scoped MCP requires team key validation.
- Redis-backed rate limits protect API keys and public demo keys.
- IP rate limiting adds a second layer against scans.
- Security headers middleware is enabled.
- CORS should be explicit in production.
- Sentry events redact sensitive request headers.
- Secrets belong in environment variables or a secret manager, never in Git.

Before making a public deployment, review:

- `.env.example`
- `CORS_ALLOWED_ORIGINS`
- database network access
- Redis network access
- API key rotation policy
- logs and error tracking redaction

## Self-Hosted Licensing

Snipara Server is source-available under the Functional Source License.

You may run Snipara Server for your own production use under the Additional Use Grant in `LICENSE`. The license does not allow offering Snipara Server as a competing hosted or managed context optimization service.

See [LICENSE](LICENSE) for the exact terms.

## Hosted vs Self-Hosted

| Need | Use hosted Snipara | Self-host Snipara Server |
| --- | --- | --- |
| Fastest setup | Yes | No |
| No infrastructure work | Yes | No |
| Data stays in your network | No | Yes |
| Custom network/security controls | Limited | Yes |
| Air-gapped or private cloud | No | Yes |
| Automatic updates | Yes | You manage updates |

## Related Packages

### `snipara-mcp`

Local MCP client/stdio bridge. It lets tools such as Claude Desktop, Cursor, Windsurf, and Codex talk to Snipara over MCP.

```bash
uvx snipara-mcp
```

### `snipara-sdk`

Python SDK and CLI helpers for project setup, document sync, and client integration.

```bash
cd snipara-sdk
uv sync
```

## Contributing

Issues and pull requests are welcome.

Before opening a PR:

1. Keep secrets out of commits.
2. Run lint and tests.
3. Update docs when behavior changes.
4. Keep the Prisma schema aligned with the source-of-truth application schema.
5. Prefer small, reviewable changes.

```bash
uv run ruff check .
uv run pytest
```

## Support

- Website: [snipara.com](https://snipara.com)
- Docs: [snipara.com/docs](https://snipara.com/docs)
- Issues: [github.com/Snipara/snipara-server/issues](https://github.com/Snipara/snipara-server/issues)
- Security reports: security@snipara.com
- General support: support@snipara.com

## License

Snipara Server is licensed under the Functional Source License, Version 1.1, Apache 2.0 Future License.

The Change License is Apache 2.0. See [LICENSE](LICENSE) for the exact grant, restrictions, and change date.
