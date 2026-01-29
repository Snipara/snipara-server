# Snipara Server

**Self-hostable context optimization server for LLMs.**

Snipara indexes your documentation and returns the most relevant context within your token budget. Your LLM gets better answers with 90% fewer tokens.

```
Your Docs → Snipara indexes → MCP Client queries → Ranked context returned → Your LLM responds
```

## Quick Start

```bash
git clone https://github.com/snipara/snipara-server.git
cd snipara-server
docker compose up
```

Then run the setup script to create your first project and API key:

```bash
export DATABASE_URL=postgresql://snipara:snipara@localhost:5433/snipara
bash scripts/setup.sh
```

The setup script outputs your MCP configuration. Add it to your AI client (Claude Code, Cursor, Windsurf, etc.).

## 30-Day Trial

All features are unlocked for **30 days** after first startup. No license key required.

After the trial, the server runs in **FREE tier** mode with core features. Purchase a license key at [snipara.com/self-hosted](https://snipara.com/self-hosted) for continued access to all features.

Check your license status:

```bash
curl http://localhost:8000/license
```

## Feature Matrix

| Feature | FREE (no key) | Licensed |
|---------|--------------|----------|
| `rlm_ask` - Quick documentation queries | Yes | Yes |
| `rlm_search` - Regex pattern search | Yes | Yes |
| `rlm_context_query` - Context optimization | Yes (keyword) | Yes (semantic + hybrid) |
| `rlm_read` - Read specific lines | Yes | Yes |
| `rlm_sections` - Browse indexed sections | Yes | Yes |
| `rlm_upload_document` - Upload documents | Yes | Yes |
| `rlm_stats` - Documentation statistics | Yes | Yes |
| Session management (inject, context, clear) | Yes | Yes |
| Semantic & hybrid search modes | No | PRO+ |
| `rlm_decompose` - Query decomposition | No | TEAM+ |
| `rlm_multi_query` - Batch queries | No | TEAM+ |
| `rlm_plan` - Execution planning | No | TEAM+ |
| Shared context & templates | No | PRO+ |
| Agent memory (remember, recall) | No | License required |
| Multi-agent swarms | No | License required |
| Multi-project queries | No | TEAM+ |

## MCP Client Configuration

### Claude Code

```json
{
  "mcpServers": {
    "snipara": {
      "type": "http",
      "url": "http://localhost:8000/mcp/my-project",
      "headers": { "X-API-Key": "rlm_your_key_here" }
    }
  }
}
```

### Cursor / Windsurf

Same format — add to your MCP settings file.

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `DATABASE_URL` | (required) | PostgreSQL connection string |
| `REDIS_URL` | `""` | Redis URL for caching/rate limiting |
| `SNIPARA_LICENSE_KEY` | `""` | License key (30-day trial without) |
| `CORS_ALLOWED_ORIGINS` | `*` | Comma-separated CORS origins |
| `HOST` | `0.0.0.0` | Server bind host |
| `PORT` | `8000` | Server bind port |
| `DEBUG` | `false` | Enable debug mode |
| `RATE_LIMIT_REQUESTS` | `100` | Requests per minute per API key |
| `SENTRY_DSN` | `""` | Sentry error tracking (optional) |

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   MCP Client │────▶│   Snipara    │────▶│  PostgreSQL  │
│ (Claude, etc)│◀────│   Server     │────▶│  + pgvector  │
└──────────────┘     │   :8000      │     └──────────────┘
                     │              │     ┌──────────────┐
                     │              │────▶│    Redis      │
                     └──────────────┘     └──────────────┘
```

- **PostgreSQL + pgvector** — Document storage, embeddings, semantic search
- **Redis** — Rate limiting, query caching (optional)
- **FastAPI** — MCP protocol handler, REST API

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/license` | GET | License status |
| `/mcp/{project_id}` | POST | MCP JSON-RPC endpoint |
| `/mcp/{project_id}` | GET | MCP SSE endpoint |
| `/v1/{project_id}/mcp` | POST | REST MCP endpoint |
| `/v1/{project_id}/mcp/sse` | GET/POST | SSE transport |
| `/v1/{project_id}/context` | GET | Session context |
| `/v1/{project_id}/limits` | GET | Usage limits |
| `/v1/{project_id}/stats` | GET | Usage statistics |
| `/docs` | GET | Interactive API docs |

## Enterprise Support

Need white-glove deployment, 24-hour SLA, or custom features?

See [snipara.com/self-hosted](https://snipara.com/self-hosted) for enterprise support plans starting at $2,000/month.

## Hosted Alternative

Don't want to self-host? Use [snipara.com](https://snipara.com) — fully managed, zero setup.

Free tier includes 100 queries/month. Pro starts at $19/month.

## License

[Functional Source License 1.1 (FSL-1.1-Apache-2.0)](LICENSE)

- **Free to use** for self-hosted deployments within your organization
- **Source-available** — read, modify, and contribute to the code
- **Converts to Apache 2.0** on 2028-01-29 (or 4 years after each release)
- **Not permitted**: offering Snipara as a competing hosted service

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

**Links:** [Website](https://snipara.com) · [Documentation](https://snipara.com/docs) · [Hosted Signup](https://snipara.com/signup)

**Contact:** sales@snipara.com · support@snipara.com
