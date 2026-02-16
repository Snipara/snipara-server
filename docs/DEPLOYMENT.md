# Snipara Deployment Architecture

## Overview

Snipara consists of **two separate codebases** deployed to **two different Railway services**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          SNIPARA ECOSYSTEM                                  │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────┐    ┌─────────────────────────────────┐
│  REPO 1: RLMSaas (this repo)        │    │  REPO 2: snipara-fastapi             │
│  github.com/Snipara/snipara         │    │  github.com/Snipara/snipara-server   │
├─────────────────────────────────────┤    ├─────────────────────────────────┤
│  Contains:                          │    │  Contains:                      │
│  - apps/web (Next.js dashboard)     │    │  - FastAPI server               │
│  - apps/mcp-server/snipara-mcp      │    │  - RLM engine                   │
│    (PyPI thin client)               │    │  - Context optimization         │
│  - packages/database (Prisma)       │    │  - Prisma Python client         │
├─────────────────────────────────────┤    ├─────────────────────────────────┤
│  Deploys to:                        │    │  Deploys to:                    │
│  - www.snipara.com (Railway)        │    │  - api.snipara.com (Railway)    │
│  - PyPI (snipara-mcp package)       │    │                                 │
└─────────────────────────────────────┘    └─────────────────────────────────┘
                │                                       │
                │                                       │
                └───────────────────┬───────────────────┘
                                    │
                                    ▼
                        ┌─────────────────────┐
                        │  Shared Database    │
                        │  (Vaultbrix 🇨🇭)    │
                        │  PostgreSQL+pgvector│
                        │  Switzerland-hosted │
                        └─────────────────────┘
```

## Repository Details

### Repo 1: RLMSaas (This Repository)

| Attribute      | Value                              |
| -------------- | ---------------------------------- |
| **GitHub**     | `github.com/Snipara/snipara`       |
| **Local Path** | `/Users/alopez/Devs/RLMSaas`       |
| **Purpose**    | Web dashboard + PyPI MCP client    |
| **Deployment** | Railway (web) + PyPI (snipara-mcp) |

**Key directories:**

- `apps/web/` - Next.js 14 dashboard (www.snipara.com)
- `apps/mcp-server/snipara-mcp/` - PyPI package (thin HTTP client)
- `packages/database/` - Prisma schema (source of truth)

### Repo 2: snipara-fastapi (Separate Repository)

| Attribute      | Value                                        |
| -------------- | -------------------------------------------- |
| **GitHub**     | `github.com/Snipara/snipara-server`          |
| **Purpose**    | FastAPI MCP server with context optimization |
| **Deployment** | Railway (api.snipara.com)                    |
| **Domain**     | `api.snipara.com`                            |

**Key files:**

- `src/server.py` - FastAPI application entry point
- `src/auth.py` - API key and OAuth validation
- `src/rlm_engine.py` - Context optimization engine
- `src/mcp_transport.py` - MCP HTTP transport layer
- `prisma/schema.prisma` - Copy of Prisma schema (must stay in sync)

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  User's Machine (Claude Desktop, Cursor, VS Code, etc.)                     │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  snipara-mcp (PyPI package from RLMSaas repo)                          │ │
│  │  - Runs locally as MCP stdio server                                    │ │
│  │  - Translates MCP tool calls → HTTP requests                           │ │
│  └─────────────────────────────┬──────────────────────────────────────────┘ │
└────────────────────────────────┼────────────────────────────────────────────┘
                                 │ HTTPS (X-API-Key header)
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Railway - FastAPI Server (snipara-fastapi repo)                                 │
│  - Hosted at: https://api.snipara.com                                       │
│  - Handles all tool logic (search, embeddings, summaries, etc.)             │
│  - Connects to PostgreSQL (Neon) and Redis                                  │
│  - Uses Prisma Python client for database queries                           │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │ Database queries
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Vaultbrix PostgreSQL 🇨🇭 + Redis                                           │
│  - Projects, documents, embeddings, API keys, OAuth tokens                  │
│  - Hosted in Switzerland (Geneva/Zurich data centers)                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Database: Vaultbrix (Switzerland)

As of February 2026, all Snipara data is stored on **Vaultbrix**, our Swiss cloud PostgreSQL DBaaS in Switzerland.

### Connection Details

| Environment     | Database URL                                                                                    |
| --------------- | ----------------------------------------------------------------------------------------------- |
| **Production**  | `postgresql://tenant_snipara:***@snipara.api.vaultbrix.com:5433/postgres?schema=tenant_snipara` |
| **Development** | Same as production (shared database, tenant isolation via schema)                               |

### Data Sovereignty & Compliance

| Compliance          | Status            | Description                                                              |
| ------------------- | ----------------- | ------------------------------------------------------------------------ |
| **GDPR**            | ✅ Compliant      | Data stored in Switzerland, adequate protection per EU adequacy decision |
| **LPD** (Swiss DPA) | ✅ Compliant      | Swiss Federal Act on Data Protection - strictest privacy laws in Europe  |
| **Cloud Act**       | ✅ Not applicable | Swiss data centers are NOT subject to US Cloud Act jurisdiction          |
| **Data Residency**  | 🇨🇭 Switzerland    | All customer data stays in Swiss territory                               |

### Why Switzerland?

1. **No Cloud Act** — US law cannot compel disclosure of data stored in Switzerland
2. **GDPR Adequacy** — EU recognizes Switzerland as providing adequate data protection
3. **LPD Protection** — Swiss privacy law provides additional protections beyond GDPR
4. **Neutrality** — Switzerland's political neutrality extends to data sovereignty
5. **Swiss Cloud** — Vaultbrix is our own database infrastructure in Swiss data centers

### Migration from Neon

| Aspect        | Before (Neon)             | After (Vaultbrix)       |
| ------------- | ------------------------- | ----------------------- |
| **Provider**  | Neon (US company)         | Vaultbrix (Swiss cloud) |
| **Location**  | EU (Frankfurt)            | Switzerland             |
| **Cloud Act** | ⚠️ Potentially applicable | ✅ Not applicable       |
| **Control**   | Managed service           | Full control            |
| **Port**      | 5432 (pooler)             | 5433 (pooler)           |

### Configuration

```bash
# .env (both environments)
DATABASE_URL=postgresql://tenant_snipara:***@snipara.api.vaultbrix.com:5433/postgres?sslmode=disable&schema=tenant_snipara
```

**Note:** The schema `tenant_snipara` provides tenant isolation within the shared Vaultbrix PostgreSQL cluster.

---

## Critical: Prisma Model Naming

### The Problem

The Prisma Python client uses **lowercase model accessors**, NOT camelCase:

| Prisma Model      | Python Accessor      | ❌ WRONG             |
| ----------------- | -------------------- | -------------------- |
| `ApiKey`          | `db.apikey`          | `db.apiKey`          |
| `TeamApiKey`      | `db.teamapikey`      | `db.teamApiKey`      |
| `OAuthToken`      | `db.oauthtoken`      | `db.oauthToken`      |
| `Project`         | `db.project`         | `db.Project`         |
| `SessionContext`  | `db.sessioncontext`  | `db.sessionContext`  |
| `DocumentSummary` | `db.documentsummary` | `db.documentSummary` |

### Correct Usage (auth.py)

```python
# ✅ CORRECT - Lowercase model accessors
api_key_record = await db.apikey.find_first(...)
team_key = await db.teamapikey.find_first(...)
oauth_token = await db.oauthtoken.find_first(...)
project = await db.project.find_first(...)

# ❌ WRONG - CamelCase will cause AttributeError
api_key_record = await db.apiKey.find_first(...)      # FAILS
team_key = await db.teamApiKey.find_first(...)         # FAILS
oauth_token = await db.oauthToken.find_first(...)      # FAILS
```

### How to Verify

```python
# In Python REPL with Prisma client
from prisma import Prisma
db = Prisma()
await db.connect()

# Check available model accessors
print([attr for attr in dir(db) if not attr.startswith('_')])
# Output includes: 'apikey', 'teamapikey', 'oauthtoken', 'project', etc.
```

---

## Keeping Repos in Sync

### Prisma Schema

**⚠️ CRITICAL: Different Generators for Different Repos**

| Repo                           | Generator          | Why                     |
| ------------------------------ | ------------------ | ----------------------- |
| RLMSaas (`packages/database/`) | `prisma-client-js` | Next.js uses JavaScript |
| snipara-fastapi (`prisma/`)    | `prisma-client-py` | FastAPI uses Python     |

When copying schema from RLMSaas to snipara-fastapi, **you MUST change the generator**:

```prisma
# In snipara-fastapi/prisma/schema.prisma - use Python generator:
generator client {
  provider             = "prisma-client-py"
  interface            = "asyncio"
  recursive_type_depth = 5
  previewFeatures      = ["postgresqlExtensions"]
}
```

The Prisma schema in `packages/database/prisma/schema.prisma` (RLMSaas) is the **source of truth** for models. When making schema changes:

1. **Update RLMSaas first** - `packages/database/prisma/schema.prisma`
2. **Run migrations** - `pnpm db:migrate --name <migration_name>`
3. **Copy schema to snipara-fastapi** - `snipara-fastapi/prisma/schema.prisma`
4. **⚠️ CHANGE GENERATOR** - Replace `prisma-client-js` with `prisma-client-py` (see above)
5. **Regenerate Python client** - `cd snipara-fastapi && prisma generate`
6. **Deploy snipara-fastapi** - Push to trigger Railway deployment

### Code Changes

When updating MCP tools or auth logic:

| Change Type      | Update In                                   |
| ---------------- | ------------------------------------------- |
| Tool definitions | Both repos (PyPI client + FastAPI handlers) |
| Auth logic       | snipara-fastapi only (auth.py)              |
| API routes       | RLMSaas only (Next.js routes)               |
| Database queries | snipara-fastapi only (Python)               |

---

## Deployment Triggers

### RLMSaas → Railway + PyPI + CI

| Trigger                                      | Result                                          |
| -------------------------------------------- | ----------------------------------------------- |
| Push to `main`                               | Railway deploys www.snipara.com                 |
| MCP server files change on push/PR           | GitHub Actions runs lint (ruff) + test (pytest) |
| Version bump in `snipara-mcp/pyproject.toml` | GitHub Actions publishes to PyPI                |

### Railway Services Overview

**⚠️ CRITICAL: All Snipara Railway services require manual/force deployment. GitHub integration for builds is unreliable and often fails to trigger.**

| GitHub Repo                 | Railway Service (Prod)   | Railway Service (Dev)       |
| --------------------------- | ------------------------ | --------------------------- |
| `alopez3006/snipara-webapp` | `snipara` (main)         | `snipara-webapp` (dev)      |
| `Snipara/snipara-server`    | `snipara-fastapi` (main) | `snipara-fastapi-dev` (dev) |

**URLs:**

- **Prod frontend**: snipara.com / www.snipara.com
- **Dev frontend**: snipara-webapp-dev.up.railway.app
- **Prod backend**: api.snipara.com
- **Dev backend**: snipara-fastapi-dev-dev.up.railway.app

### Deployment Commands

Always use the Railway CLI for deployments. Git push auto-deploy is unreliable for all Snipara projects:

```bash
# Backend (snipara-fastapi) - Production
cd /Users/alopez/Devs/snipara-fastapi
railway link -p snipara -e production
railway up

# Backend (snipara-fastapi) - Dev
cd /Users/alopez/Devs/snipara-fastapi
railway link -p snipara -e dev
railway up

# Frontend (snipara-webapp) - typically auto-deploys but use this if stuck
cd /Users/alopez/Devs/Snipara
railway link -p snipara -s snipara
railway up
```

| Method           | Command                                    | Status      |
| ---------------- | ------------------------------------------ | ----------- |
| **Manual (use)** | `railway up`                               | ✅ Reliable |
| Git push (avoid) | Push to branch → Railway auto-deploy       | ❌ Flaky    |
| Dashboard        | Railway dashboard → Deploy → Deploy latest | ✅ Backup   |

**After code changes to MCP server:**

1. Copy files: `cp apps/mcp-server/src/*.py /Users/alopez/Devs/snipara-fastapi/src/`
2. **Pull first**: `cd snipara-fastapi && git pull origin main`
3. Commit: `git add . && git commit -m "message"`
4. Push: `git push origin main`
5. **Deploy: `railway up`** (don't rely on git push auto-deploy)

---

## Troubleshooting

### "Invalid API key" Error

**Symptom:** MCP queries return `{"detail": "Invalid API key"}`

**Likely cause:** Prisma model names are camelCase instead of lowercase in snipara-fastapi's auth.py

**Fix:**

1. Clone snipara-fastapi repo
2. Update `src/auth.py` to use lowercase model accessors
3. Push to trigger Railway deployment

### "Field required" Pydantic Error

**Symptom:** `{"detail":[{"type":"missing","loc":["header","authorization"],"msg":"Field required"}]}`

**Cause:** FastAPI headers not marked as optional

**Fix in mcp_transport.py:**

```python
# ✅ CORRECT - Optional headers
x_api_key: str | None = Header(None, alias="X-API-Key")
authorization: str | None = Header(None)

# ❌ WRONG - Required headers
x_api_key: str = Header(alias="X-API-Key")  # Missing None default
authorization: str = Header()                # Missing None default
```

### Schema Out of Sync

**Symptom:** Python code references fields that don't exist

**Fix:**

1. Copy latest schema from RLMSaas to snipara-fastapi
2. Run `prisma generate` in snipara-fastapi
3. Deploy

### Prisma Client Not Generated (Docker)

**Symptom:** Railway deployment fails with:

```
RuntimeError: The Client hasn't been generated yet, you must run `prisma generate` before you can use the client.
```

**Most Common Cause: Wrong Generator in Schema**

Check your `prisma/schema.prisma` - if it says `prisma-client-js`, that's the JavaScript client, not Python!

```prisma
# ❌ WRONG - This generates JavaScript client (goes to node_modules/)
generator client {
  provider = "prisma-client-js"
}

# ✅ CORRECT - This generates Python client
generator client {
  provider             = "prisma-client-py"
  interface            = "asyncio"
  recursive_type_depth = 5
}
```

**How to spot this:** In build logs, if you see:

```
✔ Generated Prisma Client (v5.17.0) to ./node_modules/@prisma/client
```

That's the JS client! Python client output looks different.

**Other Possible Causes:**

If the generator is correct but still failing, the runtime stage may be missing required files:

1. **Virtual environment** with generated Prisma client (`/opt/venv`)
2. **Prisma cache** with query engine binaries (`/home/appuser/.cache`)
3. **Prisma schema directory** (`/app/prisma`)

**Correct Dockerfile pattern:**

```dockerfile
# ============ BUILD STAGE ============
FROM python:3.12-slim AS builder
WORKDIR /app

# Set HOME for Prisma cache location
RUN mkdir -p /home/appuser/.cache
ENV HOME="/home/appuser"

# Install deps and generate Prisma client
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY prisma ./prisma
RUN prisma generate

# ============ RUNTIME STAGE ============
FROM python:3.12-slim AS runtime
WORKDIR /app

# Copy virtual environment (includes generated Prisma client)
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy Prisma cache (query engine binaries)
COPY --from=builder /home/appuser/.cache /home/appuser/.cache
ENV HOME="/home/appuser"

# Copy application code
COPY src ./src
```

### pgvector "type vector does not exist" (Vaultbrix Multi-Tenant)

**Symptom:** MCP queries fail with:

```
type "vector" does not exist
```

**Cause:** Vaultbrix uses multi-tenant schema isolation. The `search_path` is set to only `tenant_snipara`, but pgvector extension is installed in the `public` schema. PostgreSQL cannot find the `vector` type because `public` is not in the search path.

**Verification:**

```sql
-- Check current search_path
SHOW search_path;
-- Returns: "tenant_snipara" (missing public!)

-- Check where pgvector is installed
SELECT extnamespace::regnamespace FROM pg_extension WHERE extname = 'vector';
-- Returns: public
```

**Fix (implemented in `db.py`):**

The Prisma client connection handler automatically appends `public` to the search path:

```python
# After connecting, check and fix search_path
result = await client.query_raw("SHOW search_path;")
current_path = result[0]["search_path"] if result else ""
if "public" not in current_path.lower():
    new_path = f"{current_path}, public" if current_path else "public"
    await client.execute_raw(f"SET search_path TO {new_path};")
```

**Note:** An earlier attempt used fully-qualified type names (`public.vector`) but this fails because pgvector operators (`<->`, `<#>`) are also in the `public` schema and cannot be qualified. The search_path approach is the correct fix.

### Rate Limit Stuck Keys (TTL=-1)

**Symptom:** All MCP queries fail with HTTP 429 "Rate limit exceeded" even for users who haven't hit their limits.

**Cause:** Redis rate limit keys can get stuck with `TTL=-1` (no expiry) after database migration, Redis failover, or network partitions. The counter increments but never resets.

**Verification:**

```bash
# Check a specific rate limit key
redis-cli GET "rate_limit:user_id_here"
# Returns: "100" (at max)

redis-cli TTL "rate_limit:user_id_here"
# Returns: -1 (STUCK - should be positive seconds remaining)
```

**Immediate Fix (delete stuck key):**

```bash
redis-cli DEL "rate_limit:user_id_here"
```

**Permanent Fix (implemented in `usage.py`):**

A safeguard was added to auto-fix stuck TTLs on every rate limit check:

```python
# Increment counter
await r.incr(key)

# Safeguard: ensure TTL is set (fixes stuck keys from migration/failover)
if await r.ttl(key) < 0:
    await r.expire(key, window)
```

This ensures that even if a key loses its TTL, it will be reset on the next request.

### API Key Issues After Migration

**Symptom:** API keys return "Invalid API key" even though they exist in the database.

**Possible causes:**

1. **Key is revoked** - Check `revokedAt` field in `ApiKey` table
2. **Orphaned user reference** - Key's `userId` points to a non-existent user
3. **Wrong project** - Key belongs to a different project than the one being queried

**Verification:**

```sql
-- Check if key exists and is valid
SELECT id, name, "projectId", "userId", "revokedAt"
FROM "ApiKey"
WHERE key = 'rlm_your_key_here';

-- Check if userId exists
SELECT id, email FROM "User" WHERE id = 'user_id_from_above';

-- Check project ownership
SELECT p.id, p.slug, p."ownerId"
FROM "Project" p
WHERE p.id = 'project_id_from_above';
```

**Fix:**

- If `revokedAt` is set, create a new API key
- If `userId` is orphaned, update to correct user ID or create new key
- If project doesn't exist, the key is invalid

### Optional Prisma Fields - AttributeError

**Symptom:** Runtime error when accessing optional fields:

```
AttributeError: 'ModelName' object has no attribute 'optionalField'
```

**Cause:** Prisma Python client may not include optional fields (`DateTime?`, `String?`) on the model object if:

- The Prisma client wasn't regenerated after schema changes
- The field was recently added and doesn't exist on older records

**Fix:** Use `getattr()` with a default value for optional fields:

```python
# ❌ WRONG - Direct access fails if field missing
def _model_to_dict(record):
    return {
        "id": record.id,
        "grace_period_end": record.gracePeriodEnd,  # AttributeError!
    }

# ✅ CORRECT - Safe access with default
def _model_to_dict(record):
    return {
        "id": record.id,
        "grace_period_end": getattr(record, "gracePeriodEnd", None),
    }
```

**When to use `getattr()`:**

- All optional fields (`DateTime?`, `String?`, `Int?`) in Prisma schema
- Recently added fields that may not exist on all records
- Fields that may be missing if Prisma client is out of sync

---

## Reliability Architecture

### Health Endpoints

The MCP server exposes two health endpoints:

| Endpoint  | Type      | Checks                     | Status Codes | Use Case                          |
| --------- | --------- | -------------------------- | ------------ | --------------------------------- |
| `/health` | Liveness  | None (static JSON)         | Always 200   | Load balancer, uptime monitors    |
| `/ready`  | Readiness | Database + embedding model | 200 or 503   | Railway health check, deploy gate |

**`/ready` response:**

```json
{
  "status": "ready",
  "version": "1.0.0",
  "timestamp": "2026-02-05T12:00:00Z",
  "checks": {
    "database": true,
    "embedding_model": true
  }
}
```

Returns 503 with `"status": "not_ready"` if any check fails.

### Startup Sequence

The FastAPI lifespan handler runs this sequence before accepting traffic:

1. **Database connection** — `get_db()` establishes Prisma connection
2. **Embedding models preload** — `EmbeddingsService.preload_all()` loads both `bge-large-en-v1.5` (~2GB) and `bge-small-en-v1.5` (~130MB). Light model failure is non-fatal.
3. **Server ready** — `/ready` returns 200

Both embedding models are pre-downloaded into the Docker image at build time (~1.4GB total) to avoid HuggingFace network dependency at runtime. The preload step loads the weights from disk into memory.

### Docker Configuration

```
Workers:        4 (gunicorn -w 4, each ~2.1GB with both models)
HEALTHCHECK:    /ready, interval=30s, timeout=10s, start-period=120s, retries=3
Models:         bge-large + bge-small pre-downloaded to /home/appuser/.cache/huggingface/
User:           appuser (non-root, UID 1000)
```

### Railway Configuration

```toml
[build]
builder = "dockerfile"
dockerfilePath = "Dockerfile"

[deploy]
healthcheckPath = "/ready"
healthcheckTimeout = 120
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3
```

### ⚠️ CRITICAL: Never Add `startCommand` to railway.toml

Railway's `startCommand` **overrides** the Dockerfile CMD entirely. This means:

- Dockerfile CMD: `gunicorn src.server:app -w 4 -k uvicorn.workers.UvicornWorker` (4 workers)
- `startCommand`: `uvicorn src.server:app --host 0.0.0.0 --port 8000` (1 worker)

A single-worker server is unable to recover from embedding model cold-start — one blocked request = complete replica failure (zombie replica). This was the primary cause of production outages.

**Rule: The Dockerfile CMD is the single source of truth for the start command. Never override it via `startCommand` in railway.toml.**

### Zombie Replica Prevention

A "zombie replica" accepts TCP/TLS connections but never responds to HTTP requests, causing clients to hang until timeout.

**Root causes (all addressed):**

| Cause                                                                 | Fix                                                |
| --------------------------------------------------------------------- | -------------------------------------------------- |
| Embedding model lazy-loads on first query, blocking worker for 30-40s | Pre-download in Docker build + preload in lifespan |
| Single gunicorn worker (all capacity blocked by one request)          | 4 workers (`gunicorn -w 4`)                        |
| `startCommand` in railway.toml forces single uvicorn process          | Removed — Dockerfile CMD is authoritative          |
| HEALTHCHECK uses `/health` (always 200, doesn't detect blocked state) | Changed to `/ready` (verifies DB + model)          |
| `start-period` too short (5s), health check fails before model loads  | Increased to 120s                                  |
| Sync `embed_text()` in async code blocks event loop                   | Use `embed_text_async()`/`embed_texts_async()`     |
| On-the-fly embedding of 600+ sections exceeds 60s batch timeout       | Dual-model: bge-small for on-the-fly (~10x faster) |

### Dual-Model Embedding Architecture

The MCP server uses two embedding models:

| Model               | Dims | Params | Use Case                                | Speed on CPU |
| ------------------- | ---- | ------ | --------------------------------------- | ------------ |
| `bge-large-en-v1.5` | 1024 | 335M   | pgvector indexing, memory, chunk search | ~2s/text     |
| `bge-small-en-v1.5` | 384  | 33M    | On-the-fly fallback path                | ~0.2s/text   |

**Why two models:** `bge-large` takes ~2s per text on Railway CPU. Even with a 20-section cap, the on-the-fly fallback in `_calculate_semantic_scores()` timed out at 60s in production. `bge-small` is ~10x faster and used exclusively for the on-the-fly path where both query and section embeddings are computed fresh (no stored vectors involved, so dimension mismatch with pgvector is not an issue).

**What stays on `bge-large`:**

- `DocumentChunk.embedding` pgvector column (1024 dims) — no migration
- `indexer.py` — indexing and pgvector similarity search
- `agent_memory.py` — memory embeddings
- `_calculate_semantic_scores_from_chunks()` — pre-computed chunk path

**Architecture:**

```python
# embeddings.py — Registry-based singleton
get_embeddings_service()       # → bge-large (pgvector, memory, indexer)
get_light_embeddings_service() # → bge-small (on-the-fly fallback only)

# rlm_engine.py
_calculate_semantic_scores()          # uses bge-small (on-the-fly)
_calculate_semantic_scores_from_chunks()  # uses bge-large (via indexer/pgvector)
```

**Safeguards (on-the-fly path):**

1. **Keyword score drop-off threshold** — Candidates scoring < 10% of the top keyword score (min 2.0) are excluded. This eliminates weakly-matching sections from broad queries (e.g. "search modes" where "search" matches hundreds of sections).
2. **Hard cap (`max_sections=30`)** — After drop-off filter, at most 30 sections go through embedding. RRF at k=60 makes tail candidates (position 30+) negligible.
3. **Stop words filter** — Common English stop words ("what", "are", "is", etc.) are excluded from keyword scoring to prevent false title matches.
4. **Basic stemming** — `_stem_keyword()` strips common English suffixes (-ing, -tion, -ment, -ed, -es, -s, -e, etc.) so "prices" (stem "pric") matches "pricing" in titles/content via substring matching. Minimum-length guards prevent short words from being over-stripped. Applied in `_calculate_keyword_score()`, `_classify_query_weights()`, and shared context filtering.
5. **Shared context title-only filtering** — Non-MANDATORY shared context docs are only included if at least one query keyword (after stop words + stemming) matches the doc **title**. Previously checked title + content body, causing false positives when generic keywords (like the project name) appeared in all team docs.

**Performance:** Typical 10-25 candidates × bge-small ≈ 1-3s on CPU. Worst case (30 candidates) ≈ 3-5s.

**Memory impact:** bge-small adds ~130MB per worker (4 workers = ~520MB). Total: 8GB → 8.5GB (within 32GB Railway instance).

**Long-term fix:** Index pre-computed chunks via `DocumentIndexer.index_document()` so the fast `_calculate_semantic_scores_from_chunks()` path (pgvector similarity with bge-large) is used instead.

### Async Embedding Pattern (CRITICAL)

The `EmbeddingsService` exposes both sync and async methods:

```python
# SYNC — blocks the event loop if called from async code
embeddings_service.embed_text(query)        # ❌ Never use in async def
embeddings_service.embed_texts(texts)       # ❌ Never use in async def

# ASYNC — runs inference in thread pool executor via asyncio.to_thread()
await embeddings_service.embed_text_async(query)   # ✅ Always use in async def
await embeddings_service.embed_texts_async(texts)  # ✅ Always use in async def
```

**Why this matters:** The embedding model inference takes 100-500ms per call. Calling the sync version inside an `async def` function blocks the entire uvicorn event loop — no other requests (including health checks) can be processed. With 4 workers, 4 simultaneous search requests block all workers → complete replica failure.

**Files with async embedding calls (keep in sync across repos):**

| File                      | Method                         | Call                                                                    |
| ------------------------- | ------------------------------ | ----------------------------------------------------------------------- |
| `src/services/indexer.py` | `search()` (async)             | `await self.embeddings.embed_text_async()`                              |
| `src/rlm_engine.py`       | `_calculate_semantic_scores()` | `await embeddings_service.embed_text_async()` and `embed_texts_async()` |

**Rule: Any new code that calls embedding methods from an `async def` function MUST use the `_async` variants.**

---

## Quick Reference

| What                | RLMSaas Repo            | snipara-fastapi Repo     |
| ------------------- | ----------------------- | ------------------------ |
| **GitHub**          | `Snipara/snipara`       | `Snipara/snipara-server` |
| **Deploys to**      | www.snipara.com, PyPI   | api.snipara.com          |
| **Language**        | TypeScript, Python      | Python                   |
| **Prisma Client**   | JS (`@prisma/client`)   | Python (`prisma`)        |
| **Model accessors** | `db.apiKey` (camelCase) | `db.apikey` (lowercase)  |

---

## Checklist: After Schema Changes

- [ ] Update `packages/database/prisma/schema.prisma` (RLMSaas)
- [ ] Run `pnpm db:migrate --name <name>` (RLMSaas)
- [ ] Copy schema to `snipara-fastapi/prisma/schema.prisma`
- [ ] **⚠️ Change generator from `prisma-client-js` to `prisma-client-py`** (see above)
- [ ] Run `prisma generate` in snipara-fastapi
- [ ] Test locally with `uvicorn src.server:app --reload`
- [ ] Push snipara-fastapi to deploy to Railway
- [ ] Verify api.snipara.com responds correctly

---

_Last updated: February 2026_
