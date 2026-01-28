# Snipara MCP Server - Architecture & Deployment

## Repository Structure

```
snipara-fastapi/                    # GitHub: alopez3006/snipara-fastapi
├── src/
│   ├── server.py              # FastAPI application & routes
│   ├── rlm_engine.py          # Core RLM logic & tool handlers
│   ├── models.py              # Pydantic models & enums
│   └── db.py                  # Prisma database client
├── prisma/
│   └── schema.prisma          # Database schema
├── Dockerfile                 # Production Docker image
├── railway.toml               # Railway deployment config
├── requirements.txt           # Python dependencies
└── ARCHITECTURE.md            # This file
```

## Deployment

### Railway Configuration

**Service:** SniparaMCP
**Repository:** `alopez3006/snipara-fastapi`
**Branch:** `main`

#### railway.toml

```toml
[build]
builder = "dockerfile"
dockerfilePath = "Dockerfile"

[deploy]
startCommand = "uvicorn src.server:app --host 0.0.0.0 --port 8000"
healthcheckPath = "/health"
healthcheckTimeout = 30
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3
```

#### Environment Variables (Railway)

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Neon PostgreSQL connection string |
| `OPENAI_API_KEY` | For semantic search embeddings |
| `LOG_LEVEL` | Logging level (default: INFO) |

---

## Troubleshooting Railway Deployments

### Problem: Railway not auto-deploying on git push

**Symptoms:**
- Commits pushed to GitHub but no deployment triggered
- Railway dashboard shows no new deployments

**Common Causes & Solutions:**

#### 1. "Wait for CI" enabled but no CI configured

Railway waits for GitHub Actions to pass before deploying. If no workflows exist, it waits forever.

**Fix:** Disable "Wait for CI" in Railway Settings → Git

#### 2. Repository renamed on GitHub

Railway's webhook points to the old repo URL.

**Fix:**
1. Go to Railway → Service → Settings
2. Disconnect the old repository
3. Reconnect to the new repository name
4. Or delete service and recreate with new repo

#### 3. Watch path misconfigured

If watch path is set to a subdirectory that doesn't exist, deployments won't trigger.

**Fix:** Set watch path to `/` or leave empty for root

#### 4. GitHub webhook not configured

**Check:** GitHub repo → Settings → Webhooks → Look for Railway webhook

**Fix:** Reconnect repository in Railway

### Manual Deployment Options

#### Option 1: Railway CLI

```bash
cd /path/to/snipara-fastapi
railway link          # Interactive: select workspace & service
railway up            # Deploy current directory
```

#### Option 2: Railway Dashboard

1. Go to service → Deployments tab
2. Click "Deploy" or "Trigger Deploy"
3. Or use the "+" button for manual deployment

#### Option 3: Empty commit to trigger webhook

```bash
git commit --allow-empty -m "chore: trigger deployment"
git push origin main
```

---

## API Endpoints

### MCP Protocol

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/{project_id}/mcp` | POST | Main MCP tool endpoint |
| `/v1/{project_id}/mcp/sse` | GET/POST | Server-Sent Events for streaming |

### REST API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/{project_id}/documents` | GET | List all documents |
| `/v1/{project_id}/documents` | POST | Upload single/bulk documents |
| `/v1/{project_id}/webhook/sync` | POST | CI/CD webhook for doc sync |
| `/v1/{project_id}/context` | GET | Get session context |
| `/v1/{project_id}/limits` | GET | Get usage limits |
| `/v1/{project_id}/stats` | GET | Get documentation stats |

### Health & Info

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/` | GET | API info |

---

## MCP Tools

### Primary Tools

| Tool | Description |
|------|-------------|
| `rlm_context_query` | Main context optimization query |
| `rlm_decompose` | Break complex queries into sub-queries |
| `rlm_multi_query` | Execute multiple queries in one call |

### Document Management

| Tool | Description |
|------|-------------|
| `rlm_upload_document` | Upload/update a single document |
| `rlm_sync_documents` | Bulk sync documents |
| `rlm_settings` | Get project settings |

### Supporting Tools

| Tool | Description |
|------|-------------|
| `rlm_ask` | Query with keyword search |
| `rlm_search` | Regex pattern search |
| `rlm_inject` | Inject session context |
| `rlm_context` | Show current context |
| `rlm_clear_context` | Clear session context |
| `rlm_stats` | Documentation statistics |
| `rlm_sections` | List document sections |
| `rlm_read` | Read specific lines |

---

## Database (Prisma)

### Key Models

- **Project** - User projects with settings
- **Document** - Indexed markdown files
- **ApiKey** - Hashed API keys for authentication
- **Query** - Usage tracking
- **SessionContext** - Persisted session state

### Prisma Python Syntax Notes

**IMPORTANT:** Prisma Python uses different syntax than TypeScript:

```python
# CORRECT - Python syntax
await db.model.upsert(
    where={"field": value},
    data={
        "create": {"field": value},
        "update": {"field": value},
    },
)

# WRONG - TypeScript syntax (will fail)
await db.model.upsert(
    where={"field": value},
    create={"field": value},  # ERROR!
    update={"field": value},  # ERROR!
)
```

---

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Generate Prisma client
prisma generate

# Run server
uvicorn src.server:app --reload --port 8000

# Test health
curl http://localhost:8000/health
```

---

## Related Repositories

| Repo | Purpose |
|------|---------|
| `alopez3006/snipara-fastapi` | MCP server (this repo, deployed to Railway) |
| `alopez3006/snipara` | Web app monorepo (deployed to Vercel) |

---

*Last updated: January 2026*
