# Snipara MCP Server

Context Optimization as a Service for LLM applications. Reduce 500K tokens to 5K with semantic search and intelligent ranking.

## Quick Start (Hosted API)

**No self-hosting required.** The API is hosted at `api.snipara.com` and ready to use.

### 1. Get an API Key

Sign up at [snipara.com/dashboard](https://snipara.com/dashboard) (free tier: 100 queries/month)

### 2. Configure Your MCP Client

**Claude Code / VS Code:**

```json
{
  "mcpServers": {
    "snipara": {
      "type": "http",
      "url": "https://api.snipara.com/mcp/{project_id}",
      "headers": {
        "X-API-Key": "rlm_your_api_key"
      }
    }
  }
}
```

**Or use the CLI:**

```bash
pip install snipara-mcp
snipara login
snipara init
```

### 3. Query Your Documentation

```python
# Using the MCP tools
rlm_context_query("How does authentication work?")
rlm_ask("What are the API endpoints?")
rlm_remember("User prefers dark mode", type="preference")
```

---

## API Reference

### Base URL

```
https://api.snipara.com
```

### Authentication

All endpoints require the `X-API-Key` header with one of:

| Key Type    | Prefix        | Usage                          |
| ----------- | ------------- | ------------------------------ |
| API Key     | `rlm_`        | Standard access for projects   |
| OAuth Token | `snipara_at_` | OAuth flow for desktop apps    |
| Client Key  | `snipara_ic_` | Integrator-provisioned clients |

### MCP Endpoints (JSON-RPC)

#### Streamable HTTP Transport

```
POST /mcp/{project_id}
```

The primary MCP endpoint supporting the [Streamable HTTP transport](https://modelcontextprotocol.io/docs/concepts/transports#streamable-http) specification.

**Example (Claude Code config):**

```json
{
  "mcpServers": {
    "snipara": {
      "type": "http",
      "url": "https://api.snipara.com/mcp/your-project-id"
    }
  }
}
```

#### Team Multi-Project Queries

```
POST /mcp/team/{team_id}
```

Query across all projects in a team. Requires a team API key.

### REST API Endpoints

#### Execute MCP Tool

```http
POST /v1/{project_id}/mcp
Content-Type: application/json
X-API-Key: rlm_xxx

{
  "tool": "rlm_context_query",
  "params": {
    "query": "How does authentication work?",
    "max_tokens": 4000
  }
}
```

**Response:**

```json
{
  "success": true,
  "result": { "sections": [...], "total_tokens": 3200 },
  "usage": {
    "input_tokens": 15,
    "output_tokens": 3200,
    "latency_ms": 245
  }
}
```

#### Get Usage Limits

```http
GET /v1/{project_id}/limits
X-API-Key: rlm_xxx
```

#### Get Usage Statistics

```http
GET /v1/{project_id}/stats?days=30
X-API-Key: rlm_xxx
```

#### Trigger Re-indexing

```http
POST /v1/{project_id}/reindex?mode=incremental
X-API-Key: rlm_xxx
```

#### Memory Recall (for hooks)

```http
GET /v1/{project_id}/memories/recall?query=authentication&limit=10
X-API-Key: rlm_xxx
```

#### Store Memory (for hooks)

```http
POST /v1/{project_id}/memories
X-API-Key: rlm_xxx

{
  "content": "User prefers TypeScript",
  "type": "preference",
  "category": "tech-stack"
}
```

### SSE Endpoints (Real-time)

#### Tool Execution via SSE

```http
GET /v1/{project_id}/mcp/sse?tool=rlm_context_query&params={"query":"auth"}
X-API-Key: rlm_xxx
```

#### Swarm Real-time Events

```http
GET /v1/{project_id}/swarm/{swarm_id}/sse
X-API-Key: rlm_xxx
```

Streams events: `task_created`, `task_completed`, `agent_joined`, `state_changed`, etc.

### Health Endpoints

```http
GET /health    # Liveness check
GET /ready     # Readiness check (DB + embeddings)
GET /          # API info
```

---

## Integrator Admin API

For platforms integrating Snipara for their users.

### Create Client

```http
POST /v1/integrator/clients
X-API-Key: rlm_xxx

{
  "name": "Client Company",
  "email": "client@example.com",
  "bundle": "STANDARD"
}
```

**Response includes:**

- `client_id`: Unique client identifier
- `project_id`: Auto-created project for the client
- `api_key`: Client API key (`snipara_ic_...`)

### Client Bundles

| Bundle    | Queries/Month | Memories | Swarms | Documents |
| --------- | ------------- | -------- | ------ | --------- |
| LITE      | 200           | 100      | 1      | 50        |
| STANDARD  | 2,000         | 500      | 5      | 200       |
| UNLIMITED | ∞             | ∞        | ∞      | ∞         |

### Pre-provision Swarm

```http
POST /v1/integrator/clients/{client_id}/swarms
X-API-Key: rlm_xxx

{
  "name": "client-swarm",
  "description": "Pre-provisioned swarm for client",
  "max_agents": 10
}
```

### List Client Swarms

```http
GET /v1/integrator/clients/{client_id}/swarms
X-API-Key: rlm_xxx
```

### Webhooks

Configure webhooks to receive events:

- `client.created`, `client.updated`, `client.deleted`
- `api_key.created`, `api_key.revoked`
- `swarm.task.created`, `swarm.task.completed`

---

## Available MCP Tools

### Query Tools

| Tool                | Description                       |
| ------------------- | --------------------------------- |
| `rlm_context_query` | Semantic search with token budget |
| `rlm_ask`           | Quick query (~2500 tokens)        |
| `rlm_search`        | Regex pattern search              |
| `rlm_read`          | Read specific line ranges         |
| `rlm_sections`      | List document sections            |

### Memory Tools

| Tool                | Description             |
| ------------------- | ----------------------- |
| `rlm_remember`      | Store a memory          |
| `rlm_remember_bulk` | Store multiple memories |
| `rlm_recall`        | Semantic memory recall  |
| `rlm_memories`      | List memories           |
| `rlm_forget`        | Delete memories         |

### Swarm Tools

| Tool                | Description      |
| ------------------- | ---------------- |
| `rlm_swarm_create`  | Create a swarm   |
| `rlm_swarm_join`    | Join a swarm     |
| `rlm_task_create`   | Create a task    |
| `rlm_task_claim`    | Claim a task     |
| `rlm_task_complete` | Complete a task  |
| `rlm_agent_status`  | Get agent status |

### Document Management

| Tool                  | Description            |
| --------------------- | ---------------------- |
| `rlm_upload_document` | Upload a document      |
| `rlm_sync_documents`  | Bulk sync documents    |
| `rlm_load_document`   | Load raw document      |
| `rlm_load_project`    | Load project structure |

---

## Self-Hosting (Development)

### Prerequisites

- Python 3.10+
- PostgreSQL 15+ (with pgvector extension)
- Redis (for rate limiting)

### Setup

```bash
# Clone the repo
git clone https://github.com/Snipara/snipara-server.git
cd snipara-server

# Install dependencies
uv sync

# Copy environment template
cp .env.example .env
# Edit .env with your database credentials

# Run migrations
prisma db push

# Start the server
uv run uvicorn src.server:app --reload
```

### Environment Variables

| Variable               | Description                      | Default                  |
| ---------------------- | -------------------------------- | ------------------------ |
| `DATABASE_URL`         | PostgreSQL connection string     | Required                 |
| `REDIS_URL`            | Redis connection string          | `redis://localhost:6379` |
| `HOST`                 | Server host                      | `0.0.0.0`                |
| `PORT`                 | Server port                      | `8000`                   |
| `DEBUG`                | Enable debug mode                | `false`                  |
| `RATE_LIMIT_REQUESTS`  | Requests per minute              | `100`                    |
| `CORS_ALLOWED_ORIGINS` | Allowed CORS origins             | `*`                      |
| `SENTRY_DSN`           | Sentry error tracking (optional) | -                        |

### Docker

```bash
docker build -t snipara-server .
docker run -p 8000:8000 --env-file .env snipara-server
```

---

## Rate Limits

| Plan    | Requests/Minute | Queries/Month |
| ------- | --------------- | ------------- |
| Free    | 60              | 100           |
| Pro     | 300             | 10,000        |
| Team    | 600             | 100,000       |
| Partner | 1,000           | Unlimited     |

---

## Support

- Documentation: [snipara.com/docs](https://snipara.com/docs)
- Dashboard: [snipara.com/dashboard](https://snipara.com/dashboard)
- Issues: [github.com/Snipara/snipara-server/issues](https://github.com/Snipara/snipara-server/issues)

---

## License

MIT License - see [LICENSE](LICENSE) for details.
