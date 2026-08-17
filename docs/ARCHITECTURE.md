# Snipara Server Architecture

This document describes the portable, self-hosted server. It does not describe
the private Snipara Cloud application or its commercial operations.

## Runtime topology

```text
MCP client
    |
    v
Snipara Server (FastAPI + MCP)
    |             |              |
    v             v              v
PostgreSQL     Redis        local/opt-in
+ pgvector     (optional)   embeddings
```

## Main components

| Path | Responsibility |
| --- | --- |
| src/server.py | FastAPI app, health endpoints and project-local REST routes |
| src/mcp_transport.py | Streamable HTTP MCP transport |
| src/rlm_engine.py | Tool orchestration and context assembly |
| src/engine/ | Modular handlers, scoring and token utilities |
| src/mcp/ | JSON-RPC helpers, local tool contract and request validation |
| src/services/ | Indexing, embeddings, memory, code graph, cache and jobs |
| prisma/schema.prisma | PostgreSQL schema in the standard public schema |
| scripts/ | Local initialization and maintenance scripts |

## Request flow

```text
Client request
  -> FastAPI middleware
  -> local API-key validation and rate limiting
  -> MCP transport or REST route
  -> RLM engine
  -> retrieval, memory or code-graph service
  -> structured response
```

## Data boundary

Documents, chunks, embeddings, memories, session context, local audit metadata
and optional usage records are stored in the operator's PostgreSQL database.
Redis is used for cache, rate limiting and transient coordination when enabled.

The server does not require a Snipara Cloud account and does not call a
Snipara-managed database, cache, vault or billing service.

The first OSS release retains a compatibility shell in the Prisma schema for
the memory and agent engines' local ownership fields. It is not a public Cloud
identity or billing surface; see [OSS_BOUNDARY.md](OSS_BOUNDARY.md).

## Cloud boundary

The private Cloud owns web/UI, login and OAuth, SaaS tenancy, billing, plans,
partners, resellers, integrators, customer analytics and production
deployment. It consumes tagged, immutable Snipara Server artifacts rather than
importing private Cloud modules into this repository.
