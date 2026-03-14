# Snipara SDK

**Unified Python SDK for Snipara — Context Optimization and Agent Infrastructure for LLMs.**

The `snipara` package consolidates 5 separate configuration systems into a single `.snipara.toml` file, provides a unified async/sync Python API wrapping the Snipara MCP server, event-driven file synchronization, and an auto-feedback loop (query → execute → remember).

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
  - [.snipara.toml Reference](#sniparatoml-reference)
  - [Resolution Order](#resolution-order)
  - [Environment Variables](#environment-variables)
  - [Legacy rlm.toml Migration](#legacy-rlmtoml-migration)
- [SDK API Reference](#sdk-api-reference)
  - [Snipara (Async Client)](#snipara-async-client)
  - [SniparaSync (Sync Client)](#sniparasync-sync-client)
  - [Context Optimization](#context-optimization)
  - [Document Management](#document-management)
  - [Agent Memory](#agent-memory)
  - [Code Execution](#code-execution)
  - [Auto-Feedback Loop](#auto-feedback-loop)
  - [Result Types](#result-types)
- [CLI Reference](#cli-reference)
  - [snipara init](#snipara-init)
  - [snipara config](#snipara-config)
  - [snipara status](#snipara-status)
  - [snipara login / logout](#snipara-login--logout)
  - [snipara query](#snipara-query)
  - [snipara sync](#snipara-sync)
  - [snipara watch](#snipara-watch)
- [File Watcher & Sync](#file-watcher--sync)
  - [Pattern Matching](#pattern-matching)
  - [Sync Modes](#sync-modes)
  - [Watcher Architecture](#watcher-architecture)
- [Architecture](#architecture)
  - [Design Decisions](#design-decisions)
  - [Package Structure](#package-structure)
  - [Dependency Graph](#dependency-graph)
- [Development](#development)
  - [Setup](#setup)
  - [Testing](#testing)
  - [Linting](#linting)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Installation

```bash
# Core SDK (context queries, memory, config)
pip install snipara

# With file watching support
pip install snipara[watch]

# With rlm-runtime code execution
pip install snipara[runtime]

# Everything
pip install snipara[all]

# Development (includes tests and linting)
pip install snipara[all,dev]
```

### Requirements

- **Python 3.10+** (3.11+ recommended for native TOML support)
- **snipara-mcp >= 2.3.0** (installed automatically)
- **watchfiles >= 0.21.0** (optional, for `snipara watch`)
- **rlm-runtime >= 0.1.0** (optional, for `snipara execute`)

---

## Quick Start

### 1. Initialize Configuration

```bash
snipara init
```

This creates `.snipara.toml` in your project root interactively. You'll be prompted for:

- Project slug (from your Snipara dashboard)
- API key (`rlm_...`)
- Default token budget and search mode
- Optional rlm-runtime settings

### 2. Query Context (Async)

```python
from snipara import Snipara

async with Snipara() as s:
    # Query for optimized context
    result = await s.query("how does authentication work?")
    for section in result.get("sections", []):
        print(f"[{section['relevance']:.0%}] {section['title']}")
        print(section["content"][:200])
        print()
```

### 3. Query Context (Sync)

```python
from snipara import SniparaSync

with SniparaSync() as s:
    result = s.query("how does authentication work?")
    print(result)
```

### 4. Full Feedback Loop

```python
from snipara import Snipara

async with Snipara() as s:
    # query → execute → remember (all in one call)
    result = await s.run(
        "fix the rate limiting bug in the API",
        remember_learnings=True,
    )
    print(f"Context tokens: {result.context.total_tokens}")
    print(f"Execution: {result.execution.summary}")
    print(f"Memories stored: {len(result.memories_stored)}")
```

---

## Configuration

### .snipara.toml Reference

The `.snipara.toml` file is the single source of truth for all Snipara settings. Place it in your project root (alongside `.git/`).

```toml
# ============================================================
# PROJECT — Authentication and API connection
# ============================================================
[project]
slug = "my-project"                          # Project identifier from dashboard
api_key = "rlm_abc123def456..."              # API key (keep out of version control!)
api_url = "https://api.snipara.com"          # API endpoint (rarely changed)
auth_url = "https://www.snipara.com"         # OAuth endpoint (rarely changed)

# ============================================================
# CONTEXT — Query defaults for context optimization
# ============================================================
[context]
max_tokens = 4000                            # Default token budget per query
search_mode = "hybrid"                       # "keyword" | "semantic" | "hybrid"
include_summaries = true                     # Include stored summaries in results
shared_context = true                        # Include team shared context
shared_context_budget_percent = 30           # % of budget for shared context

# ============================================================
# RUNTIME — rlm-runtime code execution settings
# ============================================================
[runtime]
backend = "anthropic"                        # "anthropic" | "openai" | "litellm"
model = "claude-sonnet-4-20250514"           # LLM model for execution
environment = "local"                        # "local" | "docker"
max_depth = 4                                # Max recursive execution depth
max_subcalls = 10                            # Max tool subcalls per depth
token_budget = 8000                          # Token budget for execution
verbose = false                              # Enable verbose logging

# Docker-specific settings (when environment = "docker")
[runtime.docker]
image = "python:3.11-slim"                   # Docker image for sandboxed execution
cpus = 2.0                                   # CPU limit
memory = "1g"                                # Memory limit
timeout = 300                                # Execution timeout in seconds

# ============================================================
# SYNC — File watcher and sync patterns
# ============================================================
[sync]
include = ["docs/**/*.md", "*.md"]           # Glob patterns to include
exclude = [                                  # Glob patterns to exclude
    "node_modules/**",
    ".git/**",
    "dist/**",
    "__pycache__/**",
]
debounce_ms = 500                            # Debounce interval for file watcher
delete_missing = false                       # Delete remote docs not in local
```

### Resolution Order

Configuration is resolved with layered priority (highest wins):

| Priority        | Source                          | Description                                   |
| --------------- | ------------------------------- | --------------------------------------------- |
| **1 (highest)** | Environment variables           | `SNIPARA_API_KEY`, `SNIPARA_PROJECT_ID`, etc. |
| **2**           | `.snipara.toml` (project)       | Walk up from CWD to git root                  |
| **3**           | `~/.config/snipara/config.toml` | Global user defaults                          |
| **4**           | `rlm.toml` (legacy)             | Deprecated — emits warning                    |
| **5 (lowest)**  | Built-in defaults               | Hardcoded in Pydantic models                  |

This means:

- Environment variables **always** override file-based config
- Project-local `.snipara.toml` overrides global and legacy configs
- A single missing field falls through to the next layer

### Environment Variables

| Variable               | Maps to               | Type  | Example                   |
| ---------------------- | --------------------- | ----- | ------------------------- |
| `SNIPARA_API_KEY`      | `project.api_key`     | `str` | `rlm_abc123...`           |
| `SNIPARA_PROJECT_ID`   | `project.slug`        | `str` | `my-project`              |
| `SNIPARA_PROJECT_SLUG` | `project.slug`        | `str` | `my-project` (alias)      |
| `SNIPARA_API_URL`      | `project.api_url`     | `str` | `https://api.snipara.com` |
| `SNIPARA_SEARCH_MODE`  | `context.search_mode` | `str` | `hybrid`                  |
| `SNIPARA_MAX_TOKENS`   | `context.max_tokens`  | `int` | `6000`                    |

Both `SNIPARA_PROJECT_ID` and `SNIPARA_PROJECT_SLUG` map to `project.slug` — use whichever you prefer. Integer values are automatically coerced from strings.

### Legacy rlm.toml Migration

If you have an existing `rlm.toml`, migrate with:

```bash
snipara init --migrate
```

This will:

1. Find `rlm.toml` (walking up to git root)
2. Map `[rlm]` section fields to the new `.snipara.toml` format
3. Create `.snipara.toml` in your current directory
4. Print instructions to delete the old file

**Field mapping:**

| rlm.toml (`[rlm]` section)              | .snipara.toml                             |
| --------------------------------------- | ----------------------------------------- |
| `snipara_api_key`                       | `[project] api_key`                       |
| `snipara_project_slug`                  | `[project] slug`                          |
| `backend`                               | `[runtime] backend`                       |
| `model`                                 | `[runtime] model`                         |
| `environment`                           | `[runtime] environment`                   |
| `max_depth`                             | `[runtime] max_depth`                     |
| `max_subcalls`                          | `[runtime] max_subcalls`                  |
| `token_budget`                          | `[runtime] token_budget`                  |
| `verbose`                               | `[runtime] verbose`                       |
| `snipara_include_shared_context`        | `[context] shared_context`                |
| `snipara_shared_context_budget_percent` | `[context] shared_context_budget_percent` |

---

## SDK API Reference

### Snipara (Async Client)

The primary SDK class. Uses `async/await` for all operations.

```python
from snipara import Snipara

# Option 1: Auto-discover .snipara.toml
s = Snipara()

# Option 2: Explicit parameters (override config)
s = Snipara(
    api_key="rlm_...",
    project_slug="my-project",
    api_url="https://api.snipara.com",
)

# Option 3: Pass a pre-built config
from snipara import load_config
cfg = load_config()
s = Snipara(config=cfg)
```

**Lifecycle management:**

```python
# Context manager (recommended)
async with Snipara() as s:
    result = await s.query("...")

# Manual lifecycle
s = Snipara()
try:
    result = await s.query("...")
finally:
    await s.close()
```

### SniparaSync (Sync Client)

Synchronous wrapper for scripts, notebooks, and non-async code. Same API as `Snipara` but blocking.

```python
from snipara import SniparaSync

# Context manager
with SniparaSync() as s:
    result = s.query("how does auth work?")

# Works in Jupyter notebooks (handles nested event loops)
s = SniparaSync()
result = s.query("...")
s.close()
```

### Context Optimization

#### `query(query, *, max_tokens=None, search_mode=None)`

Query Snipara for optimized, ranked context sections.

```python
result = await s.query(
    "how does the payment system work?",
    max_tokens=6000,          # Override default budget
    search_mode="semantic",   # "keyword" | "semantic" | "hybrid"
)

# result is a dict:
# {
#     "sections": [
#         {
#             "title": "Payment Processing",
#             "content": "...",
#             "relevance": 0.95,
#             "file": "docs/payments.md",
#             "line_start": 10,
#             "line_end": 45,
#         }
#     ],
#     "total_tokens": 3847,
#     "suggestions": ["Try also: 'billing integration'"],
# }
```

#### `search(pattern, *, max_results=20)`

Search documentation with regex patterns.

```python
result = await s.search(r"rate.*limit", max_results=10)
```

#### `plan(query, *, strategy="relevance_first", max_tokens=16000)`

Generate an execution plan for complex queries.

```python
result = await s.plan(
    "implement OAuth2 integration",
    strategy="depth_first",  # "relevance_first" | "depth_first" | "breadth_first"
    max_tokens=20000,
)
```

#### `multi_query(queries, *, max_tokens=8000)`

Execute multiple queries with a shared token budget.

```python
result = await s.multi_query(
    ["how does auth work?", "what are the API endpoints?", "database schema"],
    max_tokens=12000,
)
```

#### `shared_context(*, categories=None, max_tokens=4000)`

Get merged context from team shared collections.

```python
result = await s.shared_context(
    categories=["MANDATORY", "BEST_PRACTICES"],
    max_tokens=4000,
)
```

### Document Management

#### `upload(path, content)`

Upload or update a single document.

```python
await s.upload("docs/api-guide.md", content="# API Guide\n\n...")
```

#### `sync_documents(documents, *, delete_missing=False)`

Bulk sync multiple documents.

```python
await s.sync_documents(
    [
        {"path": "docs/auth.md", "content": "# Auth\n..."},
        {"path": "docs/api.md", "content": "# API\n..."},
    ],
    delete_missing=True,  # Remove remote docs not in this list
)
```

### Agent Memory

#### `remember(content, *, type="fact", scope="project", category=None, ttl_days=None)`

Store a memory for later semantic recall.

```python
# Decision memory
await s.remember(
    "Chose JWT over session cookies for auth due to microservices architecture",
    type="decision",
    scope="project",
    category="architecture",
)

# Learning with expiration
await s.remember(
    "The /api/v2/users endpoint requires admin scope",
    type="learning",
    ttl_days=30,
)

# Context for session continuity
await s.remember(
    "Completed auth module. Next: implement rate limiting. Blocker: need Redis config.",
    type="context",
    category="sprint-progress",
)
```

**Memory types:** `fact`, `decision`, `learning`, `preference`, `todo`, `context`

**Scopes:** `agent`, `project`, `team`, `user`

#### `recall(query, *, limit=5, min_relevance=0.5, type=None)`

Semantically recall relevant memories.

```python
memories = await s.recall(
    "authentication decisions",
    limit=10,
    min_relevance=0.7,
    type="decision",
)
```

### Code Execution

#### `execute(task, *, context=None, environment=None, max_depth=None)`

Execute a task via rlm-runtime (requires `pip install snipara[runtime]`).

```python
# Simple execution
result = await s.execute("write a Python function to validate email addresses")
print(result.response)
print(f"Cost: ${result.total_cost:.4f}")

# With context from a previous query
context = await s.query("email validation patterns")
result = await s.execute(
    "implement email validation following our patterns",
    context=context,
    environment="docker",  # Sandboxed execution
    max_depth=6,
)
```

**Returns:** `ExecuteResult` with `.response`, `.trajectory`, `.total_tokens`, `.total_cost`, `.duration_ms`, `.summary`

### Auto-Feedback Loop

#### `run(task, *, context_query=None, remember_learnings=True, memory_types=None)`

Complete feedback loop: **query context → execute task → remember learnings**.

```python
result = await s.run(
    "fix the rate limiting bug in middleware",
    context_query="rate limiting implementation",  # Custom context query
    remember_learnings=True,
    memory_types=["learning", "decision"],
)

# Access each stage
print(f"Context: {result.context.total_tokens} tokens")
print(f"Execution: {result.execution.summary}")
print(f"Memories: {result.memories_stored}")
```

**Flow:**

1. **Query**: Fetches relevant context from Snipara using `context_query` (defaults to `task`)
2. **Execute**: Passes context + task to rlm-runtime for code execution
3. **Remember**: Stores learnings from execution result as agent memories

### Result Types

All result types are dataclasses importable from `snipara`:

| Type            | Fields                                                                                  | Description               |
| --------------- | --------------------------------------------------------------------------------------- | ------------------------- |
| `QueryResult`   | `sections`, `total_tokens`, `suggestions`, `raw`                                        | Context query result      |
| `SearchResult`  | `matches`, `total_matches`, `raw`                                                       | Regex search result       |
| `PlanResult`    | `steps`, `total_tokens`, `raw`                                                          | Execution plan            |
| `MemoryResult`  | `memory_id`, `memories`, `raw`                                                          | Remember/recall result    |
| `UploadResult`  | `path`, `status`, `raw`                                                                 | Document upload result    |
| `SyncResult`    | `created`, `updated`, `unchanged`, `deleted`, `raw`                                     | Bulk sync result          |
| `ExecuteResult` | `response`, `trajectory`, `total_tokens`, `total_cost`, `duration_ms`, `raw`, `summary` | Code execution result     |
| `RunResult`     | `context`, `execution`, `memories_stored`                                               | Full feedback loop result |

---

## CLI Reference

### snipara init

Create or migrate `.snipara.toml`.

```bash
# Interactive creation
snipara init

# Specify directory
snipara init --dir /path/to/project

# Migrate from rlm.toml
snipara init --migrate
```

### snipara config

View and manage configuration.

```bash
# Show resolved config (all layers merged)
snipara config show

# Print path to active config file
snipara config path
```

### snipara status

Show authentication, configuration, and runtime status.

```bash
snipara status
```

**Output includes:**

- Config file location (or instructions to create one)
- Project slug and API URL
- Masked API key
- OAuth token status
- Runtime backend and model
- rlm-runtime and watchfiles installation status

### snipara login / logout

Manage OAuth authentication.

```bash
# Authenticate via browser (device flow)
snipara login

# Clear stored tokens
snipara logout
```

### snipara query

Query Snipara from the command line.

```bash
# Basic query
snipara query "how does authentication work?"

# With token budget
snipara query "API endpoints" --max-tokens 8000

# With search mode
snipara query "rate limiting" --mode keyword
```

### snipara sync

One-shot sync of local files to Snipara.

```bash
# Preview what would be synced
snipara sync --dry-run

# Sync all matching files
snipara sync
```

Uses `[sync]` patterns from `.snipara.toml` to determine which files to upload.

### snipara watch

Watch local files and sync changes to Snipara in real-time.

```bash
# Foreground watcher
snipara watch

# Daemon mode (background — not yet implemented)
snipara watch --daemon
```

---

## File Watcher & Sync

### Pattern Matching

File matching uses [fnmatch](https://docs.python.org/3/library/fnmatch.html) glob patterns configured in `[sync]`:

```toml
[sync]
include = ["docs/**/*.md", "*.md", "src/**/*.py"]
exclude = ["node_modules/**", ".git/**", "dist/**", "__pycache__/**"]
```

**Rules:**

1. Exclude patterns are checked **first** — if a file matches any exclude pattern, it's skipped
2. Include patterns are checked **second** — the file must match at least one include pattern
3. Patterns are matched against the **relative path** from the project root
4. `**` matches any number of directories
5. `*` matches any characters within a single path segment

### Sync Modes

| Mode         | Command                  | Behavior                                       |
| ------------ | ------------------------ | ---------------------------------------------- |
| **Dry run**  | `snipara sync --dry-run` | Lists files that would be synced, no uploads   |
| **One-shot** | `snipara sync`           | Syncs all matching files once, then exits      |
| **Watch**    | `snipara watch`          | Continuous: syncs on file create/modify events |

### Watcher Architecture

The file watcher uses [watchfiles](https://watchfiles.helpmanual.io/) (Rust-based, cross-platform, async):

```
┌─────────────────────────────────────────────────────────────────┐
│  watchfiles.awatch(root, debounce=500ms)                       │
│                                                                 │
│  Event: (Change.modified, "/project/docs/api.md")              │
│    ↓                                                            │
│  matches_patterns(path, include, exclude, root)                │
│    ↓ (matched)                                                  │
│  client.upload("docs/api.md", content)                         │
│    ↓                                                            │
│  Print: "Synced: docs/api.md"                                  │
│                                                                 │
│  Event: (Change.deleted, "/project/docs/old.md")               │
│    ↓                                                            │
│  Print: "Deleted: docs/old.md (not synced)"                    │
└─────────────────────────────────────────────────────────────────┘
```

**Key behaviors:**

- **Debounce**: Configurable via `sync.debounce_ms` (default 500ms)
- **Binary files**: Skipped with a warning (UnicodeDecodeError)
- **Upload errors**: Logged but don't stop the watcher
- **Delete events**: Logged but not synced (use `snipara sync --delete-missing`)

---

## Architecture

### Design Decisions

| Decision                               | Rationale                                                                                                |
| -------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| **SDK wraps SniparaClient**            | No HTTP duplication — all API calls go through the existing `snipara_mcp.rlm_tools.SniparaClient`        |
| **Config is independently importable** | `from snipara.config import load_config` works standalone; `snipara-mcp` can optionally `try: import` it |
| **rlm-runtime is optional**            | `execute()` raises `ImportError` with install instructions if not available                              |
| **watchfiles is optional**             | `snipara watch` raises helpful error if not installed                                                    |
| **Click for CLI**                      | Standard Python CLI framework with built-in test runner (CliRunner)                                      |
| **tomli backport**                     | Python 3.10 compatibility (3.11+ uses stdlib `tomllib`)                                                  |
| **Pydantic for config**                | Type safety, validation, and serialization for all config sections                                       |
| **Layered resolution**                 | env vars > local file > global file > legacy file > defaults — familiar pattern from tools like git      |

### Package Structure

```
apps/mcp-server/snipara-sdk/
├── pyproject.toml                        # Package metadata, deps, build config
├── README.md                             # This file
├── LICENSE                               # MIT
├── src/snipara/
│   ├── __init__.py                       # Public API exports
│   ├── _version.py                       # Version string ("0.1.0")
│   ├── config.py                         # Config models + resolution logic
│   ├── client.py                         # Snipara async client + result types
│   ├── sync_client.py                    # SniparaSync wrapper
│   ├── watcher.py                        # File watcher + sync engine
│   └── cli/
│       ├── __init__.py
│       ├── main.py                       # Click group + command registration
│       └── commands/
│           ├── __init__.py
│           ├── init.py                   # snipara init [--migrate]
│           ├── config_cmd.py             # snipara config show|path
│           ├── login.py                  # snipara login
│           ├── logout.py                 # snipara logout
│           ├── status.py                # snipara status
│           ├── watch.py                  # snipara watch [--daemon]
│           └── sync.py                   # snipara sync [--dry-run]
└── tests/
    ├── conftest.py                       # Shared fixtures
    ├── test_config.py                    # Config loading, resolution, generation
    ├── test_client.py                    # Async client methods
    ├── test_sync_client.py               # Sync wrapper
    ├── test_watcher.py                   # Pattern matching, file collection, sync
    └── test_cli_init.py                  # CLI command integration tests
```

### Dependency Graph

```
snipara (this package)
├── snipara-mcp >= 2.3.0          # MCP client (SniparaClient)
│   ├── httpx >= 0.26.0           # HTTP client
│   └── ...
├── pydantic >= 2.5.0             # Config models
├── click >= 8.0.0                # CLI framework
├── tomli >= 2.0.0 (py3.10 only) # TOML parser backport
│
├── [optional] rlm-runtime >= 0.1.0   # Code execution
│   ├── anthropic / openai / litellm
│   └── docker (for sandboxed execution)
│
└── [optional] watchfiles >= 0.21.0   # File watcher (Rust-based)
```

---

## Development

### Setup

```bash
cd apps/mcp-server/snipara-sdk

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in dev mode with all extras
pip install -e ".[all,dev]"
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=snipara --cov-report=term-missing

# Run specific test file
pytest tests/test_config.py -v

# Run specific test class
pytest tests/test_config.py::TestDefaults -v

# Run specific test
pytest tests/test_config.py::TestDefaults::test_project_defaults -v
```

**Test structure:**

| File                  | Tests | Description                                                                  |
| --------------------- | ----- | ---------------------------------------------------------------------------- |
| `test_config.py`      | 25+   | Config defaults, TOML loading, layered resolution, env overrides, generation |
| `test_client.py`      | 25+   | Client init, validation, all SDK methods, execution, feedback loop           |
| `test_sync_client.py` | 10+   | Sync wrapper delegation, context manager                                     |
| `test_watcher.py`     | 15+   | Pattern matching, file collection, sync_all modes, error handling            |
| `test_cli_init.py`    | 15+   | CLI commands: init, migrate, config, status, version                         |

### Linting

```bash
# Check for errors
ruff check src/ tests/

# Auto-fix
ruff check src/ tests/ --fix

# Format
ruff format src/ tests/
```

---

## Troubleshooting

### "No API key configured"

```
ValueError: No API key configured. Set SNIPARA_API_KEY env var,
add api_key to .snipara.toml, or pass api_key= to Snipara().
```

**Solutions:**

1. Run `snipara init` to create `.snipara.toml` with your API key
2. Set `SNIPARA_API_KEY` environment variable
3. Pass `api_key=` directly to `Snipara()` constructor

### "No project slug configured"

Similar to above — set via config file, env var, or constructor argument.

### "watchfiles is required"

```
ImportError: watchfiles is required for file watching.
Install with: pip install snipara[watch]
```

Install the optional dependency: `pip install snipara[watch]`

### "rlm-runtime is required"

```
ImportError: rlm-runtime is required for execute().
Install with: pip install snipara[runtime]
```

Install the optional dependency: `pip install snipara[runtime]`

### Legacy rlm.toml warning

```
DeprecationWarning: Found legacy rlm.toml at /path/to/rlm.toml.
Migrate to .snipara.toml with: snipara init --migrate.
rlm.toml support will be removed in v1.0.
```

Run `snipara init --migrate` to convert automatically.

### Config not found from subdirectory

The SDK walks up from your current directory to the git root looking for `.snipara.toml`. Make sure:

1. You have a `.git` directory in your project root
2. `.snipara.toml` is in or above your current directory (up to git root)

---

## License

MIT License. See [LICENSE](LICENSE) for details.
