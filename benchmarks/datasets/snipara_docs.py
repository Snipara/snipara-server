"""Snipara documentation dataset for benchmarking.

Contains Q&A pairs based on Snipara's own documentation (CLAUDE.md, specs.md, etc.)
Each test case includes:
- query: The question to ask
- expected_answer: Reference answer
- relevant_sections: Section titles that should be retrieved
- ground_truth_claims: Verifiable facts for hallucination detection
- difficulty: easy, medium, hard (for analysis)
- category: factual, reasoning, multi_hop, edge_case
"""

from pathlib import Path
from typing import Optional


# ============ BASIC FACTUAL TEST CASES ============
BASIC_TEST_CASES = [
    {
        "id": "tech_stack",
        "query": "What is Snipara's tech stack?",
        "context_query": "tech stack Next.js PostgreSQL FastAPI framework database deployment",
        "expected_answer": (
            "Snipara uses Next.js 14 with App Router in a Turborepo monorepo with pnpm workspaces. "
            "Database is PostgreSQL on Neon with Prisma ORM. Authentication is via NextAuth.js "
            "(GitHub, Google, Email). UI uses Tailwind CSS, DaisyUI, and Tremor. Billing is "
            "handled by Stripe. The MCP server is Python FastAPI. Deployment is on Vercel (web) "
            "and Railway (MCP server)."
        ),
        "relevant_sections": [
            "Tech Stack",
            "Quick Reference",
            "Schema Sync",
            "Understanding the Deployment",
            "MCP Server Outage Prevention Checklist",
        ],
        "ground_truth_claims": [
            "Snipara uses Next.js 14 with App Router",
            "Database is PostgreSQL on Neon",
            "Authentication uses NextAuth.js",
            "MCP server is Python FastAPI",
            "Web app is deployed on Vercel",
            "MCP server is deployed on Railway",
        ],
    },
    {
        "id": "core_value_prop",
        "query": "What is Snipara's core value proposition?",
        "context_query": "core value proposition context optimization 90% reduction LLM-agnostic business model",
        "expected_answer": (
            "Snipara provides 90% context reduction - from 500K tokens to ~5K tokens of highly "
            "relevant content. Clients use their own LLM (Claude, GPT, Gemini), so there's no "
            "vendor lock-in and no LLM API costs for Snipara. This enables high margins since "
            "Snipara only charges for context optimization, not LLM inference."
        ),
        "relevant_sections": [
            "Overview & Value Proposition",
            "Solution: Context Optimization as a Service",
            "Competitive Advantages",
        ],
        "ground_truth_claims": [
            "90% context reduction",
            "From 500K tokens to ~5K tokens",
            "Clients use their own LLM",
            "No vendor lock-in",
            "LLM-agnostic",
        ],
    },
    {
        "id": "mcp_tools",
        "query": "What MCP tools does Snipara expose?",
        "context_query": "MCP tools rlm_context_query rlm_decompose rlm_search rlm_multi_query exposed",
        "expected_answer": (
            "The primary tool is rlm_context_query which returns optimized context for a query. "
            "Supporting tools include rlm_search (regex patterns), rlm_decompose (break queries "
            "into sub-queries), rlm_multi_query (parallel queries), rlm_plan (execution plans), "
            "rlm_store_summary (save summaries), rlm_shared_context (team best practices), "
            "rlm_list_templates and rlm_get_template (prompt templates)."
        ),
        "relevant_sections": [
            "Snipara Tools Reference",
            "Snipara MCP Tools (39 total)",
            "MCP Tools Reference",
            "MCP Tools for Memory",
            "Use Snipara MCP for Documentation Queries",
        ],
        "ground_truth_claims": [
            "rlm_context_query is the main tool",
            "rlm_search searches for regex patterns",
            "rlm_decompose breaks queries into sub-queries",
            "rlm_shared_context gets team best practices",
        ],
    },
    {
        "id": "pricing",
        "query": "What are Snipara's pricing tiers?",
        "context_query": "Snipara pricing plans $0 $19 $49 $499 FREE PRO TEAM ENTERPRISE hosted context queries month",
        "expected_answer": (
            "Free: $0 with 100 queries/month. Pro: $19/month with 5,000 queries. "
            "Team: $49/month with 20,000 queries. Enterprise: $499/month with unlimited queries."
        ),
        "relevant_sections": [
            "Context Plans (Context Optimization)",
            "Pricing Tiers",
            "Rate Limits",
            "Pricing Configuration",
            "License Key System",
        ],
        "ground_truth_claims": [
            "Free tier is $0",
            "Free tier has 100 queries per month",
            "Pro tier is $19 per month",
            "Pro tier has 5,000 queries per month",
            "Team tier is $49 per month",
            "Team tier has 20,000 queries per month",
            "Enterprise tier is $499 per month",
        ],
    },
    {
        "id": "architecture",
        "query": "Describe Snipara's three-component architecture.",
        "context_query": "architecture components snipara-mcp FastAPI server web app deployment Railway Vercel",
        "expected_answer": (
            "1. snipara-mcp (PyPI package) - runs locally on user's machine as MCP stdio server, "
            "translates MCP tool calls to HTTP requests. 2. FastAPI Server on Railway - handles "
            "all tool logic including search, embeddings, summaries, connects to PostgreSQL and "
            "Redis. 3. Web App on Vercel - dashboard for users to manage projects, teams, and "
            "billing at snipara.com."
        ),
        "relevant_sections": [
            "Three-Component Architecture",
            "System Architecture",
            "MCP Server Deployment Architecture",
            "Client MCP (snipara-mcp)",
            "snipara-fastapi → Railway",
        ],
        "ground_truth_claims": [
            "snipara-mcp is a PyPI package",
            "snipara-mcp runs locally on user's machine",
            "FastAPI server is deployed on Railway",
            "Web app is deployed on Vercel",
            "Dashboard is at snipara.com",
        ],
    },
    {
        "id": "token_budgeting",
        "query": "How does Snipara's token budgeting work?",
        "context_query": "rlm_context_query max_tokens token budget algorithm greedy selection smart truncation sentence boundaries section ranking",
        "expected_answer": (
            "Token budgeting follows this flow: 1. Account for session context (~20% max). "
            "2. Query shared context FIRST (30% default budget). 3. Query local project scope "
            "with remaining budget. 4. Greedy selection: add sections until budget exceeded. "
            "5. Smart truncation: cut at sentence boundaries."
        ),
        "relevant_sections": [
            "Token Budget Algorithm",
            "4.1 Token Budgeting & Metadata Response",
            "Article #3: Understanding Token Budgets: A Practical Guide",
            "Token Budgets",
            "Phase 5: Token Budget Allocator (Est. 1 day)",
        ],
        "ground_truth_claims": [
            "Session context uses ~20% max",
            "Shared context uses 30% default budget",
            "Greedy selection adds sections until budget exceeded",
            "Smart truncation cuts at sentence boundaries",
        ],
    },
    {
        "id": "shared_context",
        "query": "What are shared context collections and how do they work?",
        "context_query": "shared context collections reusable documentation coding standards GLOBAL TEAM USER scopes MANDATORY BEST_PRACTICES GUIDELINES REFERENCE categories linked projects",
        "expected_answer": (
            "Shared Context Collections allow teams to create reusable documentation, coding "
            "standards, and prompt templates that can be linked to multiple projects. Scopes "
            "include GLOBAL (public templates), TEAM (shared within team), and USER (personal). "
            "Documents are categorized by importance: MANDATORY (40% budget), BEST_PRACTICES "
            "(30%), GUIDELINES (20%), REFERENCE (10%)."
        ),
        "relevant_sections": [
            "Team Best Practices with Shared Context Collections",
            "Shared Context Collections",
            "Shared Context Tools (Phase 7)",
            "SharedContextCollection",
            "1.1 New Prisma Models",
        ],
        "ground_truth_claims": [
            "Shared context collections are reusable across projects",
            "GLOBAL scope is for public templates",
            "TEAM scope is shared within a team",
            "MANDATORY category gets 40% of budget",
            "BEST_PRACTICES category gets 30% of budget",
        ],
    },
    {
        "id": "oauth_device_flow",
        "query": "How does OAuth Device Flow authentication work in Snipara?",
        "context_query": "OAuth device flow authentication RFC 8628 snipara-mcp-login tokens CLI",
        "expected_answer": (
            "OAuth Device Flow (RFC 8628) enables secure MCP authentication without copying API "
            "keys. Users run snipara-mcp-login, CLI requests device code, displays URL and code, "
            "user visits URL and enters code in browser, selects project, clicks authorize. "
            "CLI polls until authorized, then stores tokens in ~/.snipara/tokens.json."
        ),
        "relevant_sections": [
            "OAuth Device Flow",
            "Device Flow",
            "Flow Steps",
            "OAuthToken",
            "Common Issues",
        ],
        "ground_truth_claims": [
            "OAuth Device Flow follows RFC 8628",
            "User runs snipara-mcp-login command",
            "Tokens stored in ~/.snipara/tokens.json",
            "Access token lifetime is 1 hour",
            "Refresh token lifetime is 30 days",
        ],
    },
    {
        "id": "database_models",
        "query": "What are the main database models in Snipara?",
        "context_query": "Database Schema Reference core models User Team Project Document ApiKey Subscription Prisma ORM PostgreSQL",
        "expected_answer": (
            "Main models include: User (accounts), Team (organizations), Project (documentation "
            "projects), Document (indexed markdown), DocumentSummary (LLM summaries), ApiKey "
            "(MCP access), Query (usage tracking), Subscription (Stripe billing), "
            "SharedContextCollection (reusable contexts), PromptTemplate (reusable prompts)."
        ),
        "relevant_sections": [
            "Database Models",
            "Language Model Tools",
            "Phase 0: GitHub Organization",
            "Snipara VS Code Extension",
            "Database Backup",
        ],
        "ground_truth_claims": [
            "User model stores user accounts",
            "Project model stores documentation projects",
            "Document model stores indexed markdown",
            "ApiKey model stores API keys for MCP access",
            "Subscription model handles Stripe billing",
        ],
    },
    {
        "id": "layered_architecture",
        "query": "What is the layered architecture pattern used in Snipara?",
        "context_query": "layered architecture pattern route handlers services repository lib/jobs lib/services lib/db",
        "expected_answer": (
            "The layers from top to bottom are: app/api/ (thin HTTP route handlers, max 50 lines), "
            "lib/jobs/ (orchestrators/processors), lib/services/ (external API adapters), "
            "lib/db/queries (repository pattern for centralized CRUD), and types/utils/ (shared, "
            "no dependencies). Each layer can only import from layers below it."
        ),
        "relevant_sections": [
            "Layered Architecture (Web App)",
            "Three-Component Architecture",
            "Key Rules",
            "Example Structure",
            "Use Snipara MCP for Documentation Queries",
        ],
        "ground_truth_claims": [
            "Route handlers should be max 50 lines",
            "Services layer handles external APIs",
            "Repository pattern for database queries",
            "Each layer imports only from layers below",
        ],
        "difficulty": "easy",
        "category": "factual",
    },
]


# ============ COMPLEX REASONING TEST CASES ============
REASONING_TEST_CASES = [
    {
        "id": "cost_benefit_analysis",
        "query": "If I have a 500K token codebase and my LLM has a 128K context window, how does Snipara help and what are the cost savings?",
        "context_query": "Snipara 90% context reduction 500K tokens 5K tokens context window LLM cost savings token budget optimization",
        "expected_answer": (
            "Snipara provides 90% context reduction, reducing 500K tokens to ~5K tokens of highly "
            "relevant content. Without Snipara, you can't fit everything in the 128K context window. "
            "With Snipara, you get focused 4-8K token responses per query. At $3/1M input tokens "
            "(Claude Sonnet), a query with 50K tokens costs ~$0.15, while Snipara's 5K tokens costs "
            "~$0.015 - a 10x cost reduction per query."
        ),
        "relevant_sections": [
            "Solution: Context Optimization as a Service",
            "Overview & Value Proposition",
            "Quick Overview",
            "With Snipara Context Optimization",
            "Token Efficiency",
        ],
        "ground_truth_claims": [
            "90% context reduction",
            "500K to 5K tokens",
            "Codebase larger than context window",
            "Cost savings from token reduction",
        ],
        "difficulty": "hard",
        "category": "reasoning",
    },
    {
        "id": "when_to_use_decompose",
        "query": "When should I use rlm_decompose vs rlm_context_query?",
        "context_query": "rlm_decompose rlm_context_query when to use complex simple sub-queries MCP tools",
        "expected_answer": (
            "Use rlm_context_query for simple, focused questions that can be answered with one "
            "context retrieval. Use rlm_decompose for complex questions that require understanding "
            "multiple topics - it breaks the question into sub-queries, identifies dependencies, "
            "and suggests execution order. For example, 'explain the full auth system' should use "
            "decompose to handle login, JWT, sessions, and logout separately."
        ),
        "relevant_sections": [
            "When to Use RLM-Runtime vs Direct Snipara MCP Tools",
            "Use Snipara MCP for Documentation Queries",
            "Use Direct Snipara MCP Tools (rlm_context_query, etc.) For:",
            "VS Code Extension",
            "Type vs Interface",
        ],
        "ground_truth_claims": [
            "rlm_context_query for simple questions",
            "rlm_decompose for complex questions",
            "Decompose breaks into sub-queries",
            "Decompose identifies dependencies",
        ],
        "difficulty": "medium",
        "category": "reasoning",
    },
    {
        "id": "search_mode_selection",
        "query": "What search mode should I use for different types of queries?",
        "context_query": "search mode keyword semantic hybrid embeddings context optimization features",
        "expected_answer": (
            "Keyword search is best for exact term matching and is available on all plans. "
            "Semantic search uses embeddings for conceptual similarity - good when exact terms "
            "might differ (e.g., 'auth' vs 'authentication'). Hybrid combines both for best "
            "results. Semantic and hybrid are Pro+ features. If you're on Free tier, use keyword "
            "with synonyms in your query."
        ),
        "relevant_sections": [
            "Use Snipara MCP for Documentation Queries",
            "When to Use Each Mode",
            "Search Modes",
            "Workflow Mode Selection",
            "Type vs Interface",
        ],
        "ground_truth_claims": [
            "Keyword search for exact matching",
            "Semantic search uses embeddings",
            "Hybrid combines keyword and semantic",
            "Semantic search is Pro+ feature",
        ],
        "difficulty": "medium",
        "category": "reasoning",
    },
]


# ============ MULTI-HOP TEST CASES (require combining info from multiple sections) ============
MULTI_HOP_TEST_CASES = [
    {
        "id": "full_request_flow",
        "query": "Trace the full flow of an MCP request from a user's Claude Desktop to database query and back.",
        "expected_answer": (
            "1. User asks question in Claude Desktop. 2. Claude calls MCP tool (e.g., rlm_context_query). "
            "3. snipara-mcp (local PyPI package) receives stdio call. 4. snipara-mcp translates to HTTP "
            "request to FastAPI server on Railway. 5. FastAPI validates API key, checks usage limits. "
            "6. RLM engine queries PostgreSQL on Neon via Prisma, optionally checks Redis cache. "
            "7. Engine scores and ranks sections, applies token budget. 8. Response flows back through "
            "HTTP → snipara-mcp → stdio → Claude. 9. Claude synthesizes answer using optimized context."
        ),
        "relevant_sections": [
            "Three-Component Architecture",
            "MCP Request Flow",
            "Data Flow",
            "Access Request Flow",
            "Claude Desktop / Claude Code Integration",
        ],
        "ground_truth_claims": [
            "snipara-mcp runs locally",
            "HTTP request to Railway",
            "PostgreSQL on Neon",
            "Token budget applied",
            "Response flows back through HTTP",
        ],
        "difficulty": "hard",
        "category": "multi_hop",
    },
    {
        "id": "security_authentication_chain",
        "query": "What are all the authentication options available and how do they differ in security?",
        "context_query": "authentication methods API key OAuth device flow MCP auth NextAuth SHA-256 hash tokens.json 0600 permissions access token refresh token",
        "expected_answer": (
            "Snipara supports: 1. API Keys (rlm_...) - stored as SHA-256 hash, long-lived, "
            "suitable for server-to-server. 2. OAuth Device Flow - user visits URL, enters code, "
            "tokens stored in ~/.snipara/tokens.json with 0600 permissions. Access tokens last "
            "1 hour, refresh tokens 30 days. OAuth is more secure for CLI tools. "
            "User auth via NextAuth.js supports GitHub, Google, and Email."
        ),
        "relevant_sections": [
            "Authentication",
            "Auth",
            "OAuth Device Flow",
            "MCP Authentication (Quick Reference)",
            "Auth Resolution Order",
        ],
        "ground_truth_claims": [
            "API keys stored as SHA-256 hash",
            "OAuth access tokens last 1 hour",
            "Refresh tokens last 30 days",
            "Tokens stored with 0600 permissions",
        ],
        "difficulty": "hard",
        "category": "multi_hop",
    },
    {
        "id": "shared_context_budget_allocation",
        "query": "How does token budget allocation work when using shared context collections?",
        "context_query": "shared context collections document categories MANDATORY 40% BEST_PRACTICES 30% GUIDELINES 20% REFERENCE 10% budget allocation priority",
        "expected_answer": (
            "Token budget is allocated by category: MANDATORY gets 40%, BEST_PRACTICES 30%, "
            "GUIDELINES 20%, REFERENCE 10%. Shared context is queried FIRST with 30% of total "
            "budget by default (configurable via shared_context_budget_percent). Then local "
            "project scope gets remaining 70%. Within each category, documents are ranked by "
            "relevance score and selected greedily until category budget is exhausted."
        ),
        "relevant_sections": [
            "Token Budget Algorithm",
            "MCP Query Order (Shared Context First)",
            "Shared Context Tools",
            "SharedDocument",
        ],
        "ground_truth_claims": [
            "MANDATORY gets 40%",
            "BEST_PRACTICES gets 30%",
            "Shared context queried first",
            "Default 30% budget for shared context",
        ],
        "difficulty": "hard",
        "category": "multi_hop",
    },
]


# ============ EDGE CASE TEST CASES ============
EDGE_CASE_TEST_CASES = [
    {
        "id": "nonexistent_feature",
        "query": "How do I configure real-time collaborative editing in Snipara?",
        "context_query": "Snipara overview features capabilities context optimization what we do",
        "expected_answer": (
            "Snipara does not currently support real-time collaborative editing. "
            "Snipara is a Context Optimization as a Service platform focused on "
            "retrieving and optimizing documentation context for LLMs. It does not "
            "include document editing features."
        ),
        "relevant_sections": [
            "Feature Implementation Workflow (Snipara + RLM-Runtime)",
            "When to Use RLM-Runtime vs Direct Snipara MCP Tools",
            "RLM Runtime + Snipara Integration Guide",
            "Snipara Integration",
            "Use Direct Snipara MCP Tools (rlm_context_query, etc.) For:",
        ],
        "ground_truth_claims": [
            "Snipara is context optimization service",
            "Does not include editing features",
        ],
        "difficulty": "medium",
        "category": "edge_case",
        "expect_no_answer": True,
    },
    {
        "id": "ambiguous_acronym",
        "query": "What does RLM stand for?",
        "context_query": "RLM stands for Recursive Language Models project codename",
        "expected_answer": (
            "RLM stands for Recursive Language Models. It is the internal project "
            "codename for Snipara's context optimization engine and MCP server. "
            "All MCP tools are prefixed with rlm_ (e.g., rlm_context_query, "
            "rlm_search, rlm_decompose). The name reflects the recursive "
            "decomposition approach used in the search and query engine."
        ),
        "relevant_sections": [
            "Coding Standards",
            "Workflow Mode Selection",
            "Naming: What RLM Stands For",
            "Tool Permissions",
            "Feature Implementation Workflow",
        ],
        "ground_truth_claims": [
            "RLM stands for Recursive Language Models",
            "Internal project codename for Snipara",
            "Tools prefixed with rlm_",
        ],
        "difficulty": "easy",
        "category": "edge_case",
    },
    {
        "id": "version_specific",
        "query": "What version of Python is required for the MCP server?",
        "context_query": "Python version required MCP server FastAPI 3.10",
        "expected_answer": (
            "Python 3.10 or higher is required for the MCP server, as specified in "
            "pyproject.toml (requires-python >= 3.10). The MCP server uses Python FastAPI."
        ),
        "relevant_sections": [
            "Snipara MCP Server",
            "3.1 MCP Server Setup",
            "MCP Server Outage Prevention Checklist",
            "Tech Stack",
            "MCP Server Security Features",
        ],
        "ground_truth_claims": [
            "Python 3.10 or higher required",
            "MCP server uses FastAPI",
        ],
        "difficulty": "easy",
        "category": "edge_case",
    },
    {
        "id": "error_handling",
        "query": "What happens when a user exceeds their query limit?",
        "context_query": "query limit exceeded usage limits rate limit pricing plans free pro team 429",
        "expected_answer": (
            "When usage limits are exceeded, the API returns a 429 response with an error "
            "indicating the monthly query limit has been reached. The response includes "
            "current usage count, max allowed, an exceeded boolean, and reset time. "
            "Users on Free tier get 100 queries/month, Pro gets 5,000, Team gets 20,000, "
            "Enterprise gets unlimited."
        ),
        "relevant_sections": [
            "What Happens When Limits Are Exceeded",
            "What Happens When No Documents Are Found",
            "Rate Limits",
            "Rate Limit Headers",
            "Error Response Codes",
        ],
        "ground_truth_claims": [
            "API returns 429 on exceeded limits",
            "Free tier has 100 queries per month",
            "Response includes exceeded boolean",
        ],
        "difficulty": "medium",
        "category": "edge_case",
    },
    {
        "id": "empty_context",
        "query": "What happens if no relevant documents are found for a query?",
        "context_query": "rlm_context_query empty sections array total_tokens zero no-results response suggestions alternative query formulations",
        "expected_answer": (
            "If no relevant documents are found, rlm_context_query returns an empty "
            "sections array with total_tokens=0. The response still includes the query "
            "and search_mode used. The suggestions array may contain alternative query "
            "formulations. The LLM should acknowledge that no relevant documentation was found "
            "rather than hallucinating an answer."
        ),
        "relevant_sections": [
            "Document",
            "What Happens When No Documents Are Found",
            "Use Snipara MCP for Documentation Queries",
            "Query",
            "Documentation",
        ],
        "ground_truth_claims": [
            "Empty sections array returned",
            "total_tokens will be 0",
            "Suggestions array may contain alternatives",
        ],
        "difficulty": "medium",
        "category": "edge_case",
    },
    {
        "id": "rlm_runtime_execution",
        "query": "How does the execute_python tool work in RLM-Runtime?",
        "context_query": "execute_python RLM-Runtime RestrictedPython sandboxed code execution safe imports REPL context",
        "expected_answer": (
            "execute_python runs Python code in a sandboxed environment using RestrictedPython. "
            "Safe for math, data processing, and algorithms. Allowed imports include json, re, "
            "math, datetime, collections, itertools. Blocked: os, subprocess, socket, file I/O, "
            "network access. Use 'result = <value>' to return values. Context persists across "
            "calls via session_id. Profiles: quick (5s), default (30s), analysis (120s), extended (300s)."
        ),
        "relevant_sections": [
            "RLM-Runtime Tools (partial — v1.2.0)",
            "When to Use RLM-Runtime vs Direct Snipara MCP Tools",
            "Processing Large Documentation with RLM-Runtime",
            "In rlm-runtime, after execute_python completes:",
            "Available in every execute_python session with Snipara context:",
        ],
        "ground_truth_claims": [
            "Uses RestrictedPython for sandboxing",
            "Blocks os subprocess socket",
            "Context persists across calls",
            "Has execution profiles with timeouts",
        ],
        "difficulty": "medium",
        "category": "edge_case",
    },
    {
        "id": "repl_context_management",
        "query": "How do I manage REPL context in RLM-Runtime?",
        "context_query": "REPL context get_repl_context set_repl_context clear_repl_context session_id variables persist",
        "expected_answer": (
            "RLM-Runtime provides REPL context tools: get_repl_context returns all variables "
            "from previous execute_python calls. set_repl_context stores a variable (JSON-encoded). "
            "clear_repl_context resets to clean state. Use session_id to maintain separate contexts "
            "for different tasks. Variables defined in execute_python persist automatically."
        ),
        "relevant_sections": [
            "Phase 10: REPL Context Bridge (Planned — February 2026)",
            "10.1 Auto-Inject Snipara Context into REPL",
            "RLM-Runtime Tools (partial — v1.2.0)",
            "MCP Tools for Shared Context",
            "Recursive Context Tools (Near-Infinite Context)",
        ],
        "ground_truth_claims": [
            "get_repl_context returns stored variables",
            "set_repl_context takes JSON-encoded value",
            "session_id isolates contexts",
            "Variables persist across execute_python calls",
        ],
        "difficulty": "medium",
        "category": "edge_case",
    },
    {
        "id": "memory_persistence",
        "query": "How do agent memories persist across sessions in Snipara?",
        "context_query": "rlm_remember rlm_recall agent memory persistence TTL days scope project team user semantic recall",
        "expected_answer": (
            "Use rlm_remember to store memories with types: fact, decision, learning, preference, "
            "todo, context. Memories have scope (agent, project, team, user) and optional ttl_days. "
            "rlm_recall retrieves relevant memories using semantic search with confidence decay. "
            "Memory types have suggested TTLs: context (7d), learnings (14d), decisions (30d), "
            "preferences (90d)."
        ),
        "relevant_sections": [
            "5.1 Agent Memory Layer",
            "Agent Memory",
            "Phase 8.2: Agent Memory (4 tools)",
            "Agent Memory Commands",
            "Memory Protocol",
        ],
        "ground_truth_claims": [
            "rlm_remember stores memories",
            "rlm_recall uses semantic search",
            "Memories have scope and TTL",
            "Supports fact decision learning preference types",
        ],
        "difficulty": "medium",
        "category": "edge_case",
    },
    {
        "id": "swarm_coordination",
        "query": "How do multi-agent swarms work in Snipara?",
        "context_query": "swarm multi-agent coordination rlm_swarm_create rlm_claim rlm_task_create distributed collaboration",
        "expected_answer": (
            "Swarms allow multiple agents to collaborate via shared state and task queues. "
            "rlm_swarm_create initializes a swarm. rlm_claim acquires exclusive resource locks "
            "to prevent conflicts. rlm_task_create adds tasks to a distributed queue. "
            "rlm_state_get/set manage shared state with optimistic locking. Agents can broadcast "
            "events and claim tasks by priority."
        ),
        "relevant_sections": [
            "Phase 9.1: Multi-Agent Swarms (10 tools)",
            "Multi-Agent Swarms",
            "Multi-Agent Coordination",
            "rlm_swarm_create",
            "Article #8: Multi-Agent Coordination: Swarms, Claims, and Shared State",
        ],
        "ground_truth_claims": [
            "Swarms enable multi-agent collaboration",
            "rlm_claim provides exclusive resource locks",
            "Tasks have priority ordering",
            "State uses optimistic locking",
        ],
        "difficulty": "hard",
        "category": "edge_case",
    },
    {
        "id": "deprecated_api_keys",
        "query": "Should I use API keys or OAuth for MCP authentication?",
        "context_query": "API key OAuth authentication deprecated device flow preferred snipara-mcp-login tokens",
        "expected_answer": (
            "OAuth Device Flow is the preferred authentication method. API keys are still "
            "supported but OAuth provides better security with auto-refresh tokens. "
            "Run snipara-mcp-login to authenticate via device flow. Tokens are stored in "
            "~/.snipara/tokens.json with 0600 permissions. Access tokens expire in 1 hour "
            "and are auto-refreshed."
        ),
        "relevant_sections": [
            "Auth",
            "Authentication",
            "OAuth Device Flow",
            "MCP Authentication",
            "API Keys",
        ],
        "ground_truth_claims": [
            "OAuth is preferred over API keys",
            "snipara-mcp-login for authentication",
            "Tokens auto-refresh",
            "Access tokens expire in 1 hour",
        ],
        "difficulty": "easy",
        "category": "edge_case",
    },
    {
        "id": "webhook_integration",
        "query": "Does Snipara support webhooks for real-time notifications?",
        "context_query": "webhooks notifications real-time events callbacks Snipara features integrations",
        "expected_answer": (
            "Snipara does not currently support webhooks for real-time notifications. "
            "It is a Context Optimization as a Service platform focused on query-time "
            "context retrieval. For event-driven workflows, you can use Claude Code hooks "
            "(PreCompact, PostToolUse) to trigger actions after MCP tool calls."
        ),
        "relevant_sections": [
            "7.4.1 Claude Code Hooks Integration",
            "Claude Code",
            "Automation",
            "Integrations",
            "Executive Summary",
        ],
        "ground_truth_claims": [
            "No webhook support currently",
            "Context optimization service",
            "Claude Code hooks available",
        ],
        "difficulty": "medium",
        "category": "edge_case",
        "expect_no_answer": True,
    },
]


# ============ COMBINE ALL TEST CASES ============
TEST_CASES = BASIC_TEST_CASES + REASONING_TEST_CASES + MULTI_HOP_TEST_CASES + EDGE_CASE_TEST_CASES

# Add difficulty and category to basic test cases (backwards compatibility)
for case in BASIC_TEST_CASES:
    if "difficulty" not in case:
        case["difficulty"] = "easy"
    if "category" not in case:
        case["category"] = "factual"


class SniparaDocsDataset:
    """Dataset of Q&A pairs from Snipara documentation."""

    def __init__(self, docs_dir: Optional[Path] = None):
        """Initialize dataset.

        Args:
            docs_dir: Directory containing documentation files.
                     Defaults to project root.
        """
        self.docs_dir = docs_dir or Path(__file__).parents[4]
        self._full_docs: Optional[str] = None

    @property
    def test_cases(self) -> list[dict]:
        """Get all test cases."""
        return TEST_CASES

    def get_test_case(self, case_id: str) -> Optional[dict]:
        """Get a specific test case by ID."""
        for case in TEST_CASES:
            if case["id"] == case_id:
                return case
        return None

    def get_by_difficulty(self, difficulty: str) -> list[dict]:
        """Get test cases by difficulty level.

        Args:
            difficulty: 'easy', 'medium', or 'hard'
        """
        return [c for c in TEST_CASES if c.get("difficulty") == difficulty]

    def get_by_category(self, category: str) -> list[dict]:
        """Get test cases by category.

        Args:
            category: 'factual', 'reasoning', 'multi_hop', or 'edge_case'
        """
        return [c for c in TEST_CASES if c.get("category") == category]

    def get_summary(self) -> dict:
        """Get summary statistics of the dataset."""
        difficulties = {}
        categories = {}
        for case in TEST_CASES:
            diff = case.get("difficulty", "unknown")
            cat = case.get("category", "unknown")
            difficulties[diff] = difficulties.get(diff, 0) + 1
            categories[cat] = categories.get(cat, 0) + 1

        return {
            "total_cases": len(TEST_CASES),
            "by_difficulty": difficulties,
            "by_category": categories,
        }

    def load_full_docs(self) -> str:
        """Load full documentation content for hallucination grounding.

        IMPORTANT: This must include ALL docs that Snipara indexes, otherwise
        the hallucination check will mark accurate claims as "incorrect" when
        they reference docs not in this reference set.

        Includes:
        - CLAUDE.md, specs.md, ROADMAP.md (project root)
        - All docs/**/*.md files (recursively, same as what Snipara indexes)
        """
        if self._full_docs is not None:
            return self._full_docs

        content_parts = []

        # Load root-level docs
        for name in ["CLAUDE.md", "specs.md", "ROADMAP.md"]:
            path = self.docs_dir / name
            if path.exists():
                content_parts.append(f"# FILE: {name}\n\n{path.read_text()}")

        # Load ALL docs/**/*.md files recursively (same as what Snipara indexes)
        docs_folder = self.docs_dir / "docs"
        if docs_folder.exists():
            for md_file in sorted(docs_folder.glob("**/*.md")):
                try:
                    content = md_file.read_text()
                    rel_path = md_file.relative_to(self.docs_dir)
                    content_parts.append(f"# FILE: {rel_path}\n\n{content}")
                except Exception:
                    pass  # Skip files that can't be read

        self._full_docs = "\n\n---\n\n".join(content_parts)
        return self._full_docs

    def get_relevant_context(self, case_id: str, max_tokens: int = 4000) -> str:
        """Get relevant context for a test case (simulates 'with Snipara').

        This simulates what Snipara's context optimization would return -
        only the sections relevant to the query.

        Improved extraction algorithm:
        1. Match section headers by keyword overlap
        2. Also extract sections containing ground truth claims
        3. Score and rank sections by relevance
        4. Select top sections within token budget
        """
        case = self.get_test_case(case_id)
        if not case:
            return ""

        full_docs = self.load_full_docs()
        relevant_sections = case.get("relevant_sections", [])
        ground_truth = case.get("ground_truth_claims", [])
        query = case.get("query", "")

        # Parse document into sections
        sections = self._parse_into_sections(full_docs)

        # Score each section
        scored_sections = []
        for section in sections:
            score = self._score_section(
                section=section,
                relevant_titles=relevant_sections,
                ground_truth=ground_truth,
                query=query,
            )
            if score > 0:
                scored_sections.append((score, section))

        # Sort by score descending
        scored_sections.sort(key=lambda x: x[0], reverse=True)

        # Balanced filtering for precision and recall
        if scored_sections:
            max_score = scored_sections[0][0]
            # Keep sections with at least 38% of max score
            score_threshold = max_score * 0.38
            scored_sections = [(s, sec) for s, sec in scored_sections if s >= score_threshold]

        # Select sections within token budget (use 3.8 chars/token)
        context_parts = []
        total_chars = 0
        max_chars = int(max_tokens * 3.8)

        # Focus on top sections for precision (up to 5)
        max_sections = min(5, len(scored_sections))

        for i, (score, section) in enumerate(scored_sections[:max_sections]):
            section_text = f"## {section['title']}\n\n{section['content']}"
            section_chars = len(section_text)

            if total_chars + section_chars > max_chars:
                # Try to fit partial section only if it's highly relevant
                remaining = max_chars - total_chars
                if remaining > 800 and score >= max_score * 0.5:
                    # Smart truncation at paragraph boundary
                    paragraphs = section['content'].split('\n\n')
                    truncated_content = []
                    para_chars = len(f"## {section['title']}\n\n")
                    for para in paragraphs:
                        if para_chars + len(para) + 2 < remaining:
                            truncated_content.append(para)
                            para_chars += len(para) + 2
                        else:
                            break
                    if truncated_content:
                        context_parts.append(f"## {section['title']}\n\n" + "\n\n".join(truncated_content))
                break

            context_parts.append(section_text)
            total_chars += section_chars

        return "\n\n---\n\n".join(context_parts)

    def _parse_into_sections(self, content: str) -> list[dict]:
        """Parse document content into sections."""
        sections = []
        lines = content.split("\n")
        current_section = None
        current_content = []
        current_level = 0

        for i, line in enumerate(lines):
            if line.startswith("#"):
                # Save previous section
                if current_section:
                    sections.append({
                        "title": current_section,
                        "content": "\n".join(current_content).strip(),
                        "level": current_level,
                    })
                # Start new section
                level = len(line) - len(line.lstrip("#"))
                current_section = line.lstrip("#").strip()
                current_content = []
                current_level = level
            else:
                current_content.append(line)

        # Save last section
        if current_section:
            sections.append({
                "title": current_section,
                "content": "\n".join(current_content).strip(),
                "level": current_level,
            })

        return sections

    def _score_section(
        self,
        section: dict,
        relevant_titles: list[str],
        ground_truth: list[str],
        query: str,
    ) -> float:
        """Score a section by relevance.

        IMPROVED scoring factors:
        - Exact title match with relevant_sections: +10
        - Partial title match: +5
        - Content contains ground truth claims: +4 per claim (higher threshold)
        - Query bigram overlap in title: +3 per bigram
        - Query term overlap in title: +2 per term
        - Query term overlap in content: +0.3 per term
        - Penalty for very short sections: -2
        - Penalty for overly generic sections: -3
        """
        score = 0.0
        title_lower = section["title"].lower()
        content_lower = section["content"].lower()
        content_words = content_lower.split()

        # Skip very short sections (likely not useful)
        if len(content_words) < 10:
            return 0

        # Title matching (improved with flexible matching)
        for title in relevant_titles:
            title_norm = title.lower().strip()
            if title_norm == title_lower:
                score += 10  # Exact match
            elif title_norm in title_lower or title_lower in title_norm:
                score += 6  # Partial/substring match
            else:
                # Check word overlap for related titles
                title_words = set(word for word in title_norm.split() if len(word) > 2)
                section_title_words = set(word for word in title_lower.split() if len(word) > 2)
                if title_words and section_title_words:
                    word_overlap = len(title_words & section_title_words) / len(title_words)
                    if word_overlap >= 0.5:  # At least half the words match
                        score += 4 * word_overlap

        # Ground truth in content (improved matching with key phrase detection)
        for claim in ground_truth:
            claim_lower = claim.lower()
            claim_terms = set(word for word in claim_lower.split() if len(word) > 3)
            content_terms_set = set(content_words)

            # Check for exact phrase match first (very strong signal)
            if claim_lower in content_lower:
                score += 6
                continue

            # Check for key phrase fragments (2+ consecutive words from claim)
            claim_words_list = [w for w in claim_lower.split() if len(w) > 2]
            for i in range(len(claim_words_list) - 1):
                phrase = f"{claim_words_list[i]} {claim_words_list[i+1]}"
                if phrase in content_lower:
                    score += 3
                    break

            # Fall back to term overlap
            if claim_terms:
                overlap = len(claim_terms & content_terms_set) / len(claim_terms)
                if overlap > 0.5:  # 50% threshold for term overlap
                    score += 3 * overlap

        # Query analysis - extract meaningful terms
        query_words = [word.lower() for word in query.split() if len(word) > 3]
        query_terms = set(query_words)

        # Generate query bigrams for better phrase matching
        query_bigrams = set()
        for i in range(len(query_words) - 1):
            query_bigrams.add(f"{query_words[i]} {query_words[i+1]}")

        title_terms = set(word.lower() for word in section["title"].split())

        # Check bigrams in title (strong signal)
        for bigram in query_bigrams:
            if bigram in title_lower:
                score += 3

        # Single term overlap in title
        query_in_title = len(query_terms & title_terms)
        score += query_in_title * 2

        # Term overlap in content (lower weight, only first 300 words)
        content_first_300 = set(content_words[:300])
        query_in_content = len(query_terms & content_first_300)
        score += query_in_content * 0.3

        # Penalty for generic/overview sections unless specifically requested
        generic_titles = {"overview", "introduction", "summary", "table of contents", "contents"}
        if title_lower in generic_titles and not any(t.lower() in generic_titles for t in relevant_titles):
            score -= 3

        # Minimum score threshold - must have meaningful relevance
        if score < 2.8:
            return 0

        return score

    def prepare_contexts(self, max_tokens_with: int = 4000) -> dict:
        """Prepare both context versions for all test cases.

        Returns:
            Dict mapping case_id to {'with_snipara': str, 'without_snipara': str}
        """
        full_docs = self.load_full_docs()
        contexts = {}

        for case in self.test_cases:
            case_id = case["id"]
            contexts[case_id] = {
                "with_snipara": self.get_relevant_context(case_id, max_tokens_with),
                "without_snipara": full_docs,
            }

        return contexts


# Convenience function
def load_dataset() -> SniparaDocsDataset:
    """Load the Snipara docs dataset."""
    return SniparaDocsDataset()
