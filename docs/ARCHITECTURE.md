# MCP Server Architecture

> Documentation of the modular architecture after the 6-step refactoring.

## Overview

The MCP Server has been refactored from a monolithic structure into a clean, modular architecture with clear separation of concerns. This document describes the new structure and how components interact.

## Directory Structure

```
apps/mcp-server/src/
├── __init__.py              # Package version
├── server.py                # FastAPI app, endpoints, middleware setup (1,060 lines)
├── rlm_engine.py            # Main engine orchestrator (3,200 lines)
├── mcp_transport.py         # MCP Streamable HTTP transport (301 lines)
│
├── api/                     # API utilities
│   ├── __init__.py          # Package exports
│   └── deps.py              # Dependency injection, validation, error handling
│
├── engine/                  # RLM engine modules
│   ├── __init__.py          # Engine package exports
│   ├── core/                # Core utilities
│   │   ├── __init__.py
│   │   ├── document.py      # Document loading helpers
│   │   ├── query.py         # Query decomposition
│   │   ├── tips.py          # Usage tips generator
│   │   └── tokens.py        # Token counting
│   ├── handlers/            # Tool handlers by category
│   │   ├── __init__.py      # Handler registry
│   │   ├── base.py          # Base handler class
│   │   ├── document.py      # Document management
│   │   ├── memory.py        # Agent memory
│   │   ├── session.py       # Session management
│   │   ├── summary.py       # Summary storage
│   │   └── swarm.py         # Multi-agent coordination
│   └── scoring/             # Relevance scoring
│       ├── __init__.py      # Scoring exports
│       ├── constants.py     # Scoring constants/weights
│       ├── keyword_scorer.py# Keyword-based scoring
│       ├── rrf_fusion.py    # Reciprocal Rank Fusion
│       ├── semantic_scorer.py# Semantic similarity scoring
│       └── stemmer.py       # Basic stemmer
│
├── mcp/                     # MCP protocol
│   ├── __init__.py          # JSON-RPC exports
│   ├── jsonrpc.py           # JSON-RPC 2.0 helpers
│   ├── tool_defs.py         # 43 tool definitions
│   └── validation.py        # Request validation
│
├── middleware/              # Security middleware
│   ├── __init__.py
│   ├── ip_rate_limit.py     # IP-based rate limiting
│   └── security_headers.py  # Security headers (HSTS, etc.)
│
├── models/                  # Pydantic models
│   ├── __init__.py          # All model exports
│   ├── agent.py             # Agent/swarm models
│   ├── context.py           # Context/query models
│   ├── documents.py         # Document models
│   ├── enums.py             # Enums (Plan, ToolName, etc.)
│   ├── requests.py          # Request models
│   ├── responses.py         # Response models
│   ├── shared.py            # Shared models
│   └── summary.py           # Summary models
│
└── services/                # External services (unchanged)
    ├── __init__.py
    ├── agent_limits.py
    ├── agent_memory.py
    ├── background_jobs.py
    ├── cache.py
    ├── chunker.py
    ├── embeddings.py
    ├── indexer.py
    ├── query_router.py
    ├── shared_context.py
    ├── swarm_coordinator.py
    └── swarm_events.py
```

## Module Responsibilities

### Core Application

| Module             | Responsibility                                      | Lines |
| ------------------ | --------------------------------------------------- | ----- |
| `server.py`        | FastAPI app, routes, middleware, exception handlers | 1,060 |
| `rlm_engine.py`    | Tool orchestration, context queries, search         | 3,200 |
| `mcp_transport.py` | MCP Streamable HTTP protocol handlers               | 301   |

### API Layer (`api/`)

| Module    | Responsibility                                                      |
| --------- | ------------------------------------------------------------------- |
| `deps.py` | FastAPI dependencies, validation, rate limiting, error sanitization |

### Engine Layer (`engine/`)

#### Core Utilities (`engine/core/`)

| Module        | Responsibility                        |
| ------------- | ------------------------------------- |
| `document.py` | Load documents by path/ID             |
| `query.py`    | Query decomposition into sub-queries  |
| `tips.py`     | Generate usage tips for empty results |
| `tokens.py`   | Token counting for budget management  |

#### Tool Handlers (`engine/handlers/`)

| Module        | Responsibility                                                   |
| ------------- | ---------------------------------------------------------------- |
| `base.py`     | Abstract base handler with common logic                          |
| `document.py` | `rlm_upload_document`, `rlm_sync_documents`, `rlm_load_*`        |
| `memory.py`   | `rlm_remember`, `rlm_recall`, `rlm_memories`, `rlm_forget`       |
| `session.py`  | `rlm_inject`, `rlm_context`, `rlm_clear_context`, `rlm_settings` |
| `summary.py`  | `rlm_store_summary`, `rlm_get_summaries`, `rlm_delete_summary`   |
| `swarm.py`    | `rlm_swarm_*`, `rlm_claim`, `rlm_release`, `rlm_task_*`          |

#### Scoring (`engine/scoring/`)

| Module               | Responsibility                    |
| -------------------- | --------------------------------- |
| `constants.py`       | Weights, thresholds, stop words   |
| `keyword_scorer.py`  | TF-IDF-like keyword matching      |
| `semantic_scorer.py` | Embedding-based similarity        |
| `rrf_fusion.py`      | Combine keyword + semantic scores |
| `stemmer.py`         | Basic word stemming               |

### MCP Protocol (`mcp/`)

| Module          | Responsibility                          |
| --------------- | --------------------------------------- |
| `jsonrpc.py`    | JSON-RPC 2.0 response/error helpers     |
| `tool_defs.py`  | 43 MCP tool definitions with schemas    |
| `validation.py` | API key/OAuth validation, rate limiting |

### Middleware (`middleware/`)

| Module                | Responsibility                                     |
| --------------------- | -------------------------------------------------- |
| `security_headers.py` | Add security headers (HSTS, X-Frame-Options, etc.) |
| `ip_rate_limit.py`    | Per-IP rate limiting                               |

### Models (`models/`)

| Module         | Contents                                       |
| -------------- | ---------------------------------------------- |
| `enums.py`     | `Plan`, `ToolName`, `SearchMode`, `MemoryType` |
| `requests.py`  | `MCPRequest`, `MultiProjectQueryParams`        |
| `responses.py` | `MCPResponse`, `HealthResponse`, `ToolResult`  |
| `context.py`   | `SectionResult`, `ContextQueryResult`          |
| `documents.py` | `DocumentInfo`, `ChunkInfo`                    |
| `agent.py`     | `SwarmInfo`, `TaskInfo`, `ClaimInfo`           |
| `summary.py`   | `StoredSummary`                                |
| `shared.py`    | `UsageInfo`, `LimitsInfo`                      |

## Data Flow

### MCP Request Flow

```
Client Request
      │
      ▼
┌─────────────────┐
│  server.py      │  ← Security middleware, CORS
│  (FastAPI)      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ mcp_transport.py│  ← JSON-RPC parsing
│                 │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  rlm_engine.py  │  ← Tool dispatch
│                 │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌───────┐ ┌──────────┐
│scoring│ │ handlers │
└───────┘ └──────────┘
```

### Query Processing Flow

```
rlm_context_query(query, max_tokens)
           │
           ▼
    ┌──────────────┐
    │ Load sections │ ← from database
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ Keyword score │ ← scoring/keyword_scorer.py
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ Semantic score│ ← scoring/semantic_scorer.py
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ RRF fusion   │ ← scoring/rrf_fusion.py
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ Token budget │ ← engine/core/tokens.py
    └──────┬───────┘
           │
           ▼
    Return ranked sections
```

## Testing

```
tests/
├── test_scoring.py      # 26 tests - Scoring module
├── test_handlers.py     # 26 tests - Handler module
├── test_core.py         # 23 tests - Core utilities
├── test_mcp.py          # 34 tests - MCP protocol
├── test_middleware.py   # 9 tests  - Middleware
├── test_api_deps.py     # 22 tests - API dependencies
└── conftest_handlers.py # Test fixtures for handlers
```

**Total: 140 refactoring tests**

Run tests:

```bash
cd apps/mcp-server
uv run pytest tests/test_scoring.py tests/test_handlers.py tests/test_core.py tests/test_mcp.py tests/test_middleware.py tests/test_api_deps.py -v
```

## Import Patterns

### From engine (inside rlm_engine.py):

```python
from .engine.scoring import compute_keyword_score, compute_semantic_score, fuse_scores
from .engine.core import count_tokens, decompose_query, generate_usage_tips
from .engine.handlers import HANDLER_REGISTRY
```

### From MCP transport:

```python
from .mcp import TOOL_DEFINITIONS, jsonrpc_error, jsonrpc_response
from .mcp.validation import validate_request
```

### From server.py:

```python
from .api.deps import validate_and_rate_limit, sanitize_error_message
from .middleware import SecurityHeadersMiddleware, IPRateLimitMiddleware
from .mcp import jsonrpc_response, jsonrpc_error
```

## Migration Notes

### Breaking Changes

- `models.py` deleted → Use `from .models import ...`
- Scoring functions moved → Use `from .engine.scoring import ...`
- JSON-RPC helpers centralized → Use `from .mcp import jsonrpc_response, jsonrpc_error`

### Backward Compatibility

- All public APIs maintained
- All tool definitions unchanged
- MCP protocol unchanged

## Metrics

| Metric             | Before      | After       | Change  |
| ------------------ | ----------- | ----------- | ------- |
| `rlm_engine.py`    | 5,676 lines | 3,200 lines | -44%    |
| `mcp_transport.py` | 1,230 lines | 301 lines   | -76%    |
| `server.py`        | 1,529 lines | 1,060 lines | -31%    |
| `models.py`        | 700 lines   | 8 modules   | Modular |
| Test coverage      | 0           | 140 tests   | New     |
