# Snipara Server Architecture

This document describes the self-hosted Snipara Server distribution. It does
not describe SaaS production infrastructure, private runbooks,
internal evaluation data, or SaaS monetization systems.

## Runtime Topology

```text
MCP clients and internal apps
        |
        v
Snipara Server
        |
        +--> PostgreSQL with pgvector
        |
        +--> Redis
        |
        +--> optional embedding service
```

## Main Components

| Path | Responsibility |
| --- | --- |
| `src/server.py` | FastAPI app, middleware, health endpoints, REST routes |
| `src/mcp_transport.py` | Streamable HTTP MCP transport |
| `src/rlm_engine.py` | Tool orchestration and context assembly |
| `src/engine/` | Modular tool handlers, scoring, token utilities |
| `src/mcp/` | JSON-RPC helpers, tool definitions, request validation |
| `src/services/` | Indexing, embeddings, memory, code graph, cache, background jobs |
| `prisma/schema.prisma` | Database schema |
| `scripts/` | Local setup and maintenance scripts |

## Request Flow

```text
Client request
  -> FastAPI middleware
  -> API key validation and rate limiting
  -> MCP transport or REST route
  -> RLM engine
  -> retrieval, memory, shared context, or code graph service
  -> structured tool response
```

## Data Boundary

The self-hosted server stores project documents, indexed chunks, embeddings,
memory records, audit metadata, and tool usage in the customer's PostgreSQL
database. Redis is used for cache, rate limiting, and transient coordination.

The repository does not contain customer data, production secrets, evaluation
reports, private SaaS deployment configuration, or cloud-provider-specific
operations material.

## Licensing Boundary

Production deployments should set:

```text
SNIPARA_LICENSE_REQUIRED=true
SNIPARA_LICENSE_KEY=<issued-by-snipara>
```

The `/license` endpoint reports non-sensitive license configuration state. It
never returns the license key.
