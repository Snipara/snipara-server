# Snipara Deployment Guide

## Overview

Production deployment is now Infomaniak VPS only.

- Web app: `https://snipara.com` and `https://www.snipara.com`
- Hosted MCP backend: `https://api.snipara.com`
- Reverse proxy / TLS: Traefik
- Database: Vaultbrix PostgreSQL
- Cache and rate limiting: Upstash Redis

## Source Of Truth

- Monorepo backend source: `/Users/alopez/Devs/Snipara/apps/mcp-server/`
- Monorepo frontend source: `/Users/alopez/Devs/Snipara/apps/web/`
- VPS deploy tooling: `/Users/alopez/Devs/Snipara/deploy/infomaniak/`
- Public backend mirror: `Snipara/snipara-server`

This `snipara-fastapi/` folder is a mirror, not the deploy entrypoint.

## Standard Production Flow

1. Make code changes in the monorepo source of truth.
2. If Prisma schema changed, sync the Python schema and prepare the matching Vaultbrix SQL migration.
3. Deploy from the monorepo with the Infomaniak tooling.
4. Run hosted MCP smoke tests after rollout.

## Deploy Commands

Backend only:

```bash
./deploy/infomaniak/deploy-zero-downtime.sh backend
```

Frontend only:

```bash
./deploy/infomaniak/deploy-zero-downtime.sh frontend
```

Full stack:

```bash
./deploy/infomaniak/deploy-zero-downtime.sh all
```

Useful flags:

```bash
./deploy/infomaniak/deploy-zero-downtime.sh backend --latest-migration
./deploy/infomaniak/deploy-zero-downtime.sh backend --migrate path/to/file.sql
./deploy/infomaniak/deploy-zero-downtime.sh backend --skip-mcp-smoke
```

## Schema And Migration Rules

- JS Prisma schema remains the primary source: `packages/database/prisma/schema.prisma`
- Python Prisma schema must stay aligned: `apps/mcp-server/prisma/schema.prisma`
- Apply Vaultbrix SQL before validating new backend code when schema changed

Recommended helpers:

```bash
./deploy/infomaniak/migrate-vaultbrix.sh path/to/migration.sql
python deploy/infomaniak/check_hosted_mcp.py
```

## Mirror Sync

Keep the in-repo mirror aligned:

```bash
uv run --project apps/mcp-server python apps/mcp-server/scripts/sync_snipara_fastapi_mirror.py
uv run --project apps/mcp-server python apps/mcp-server/scripts/sync_snipara_fastapi_mirror.py --check
```

If you also maintain the standalone backend repo checkout, sync and push it separately after the monorepo change.

## Verification

Basic health:

```bash
curl -fsS https://api.snipara.com/health
curl -fsS https://api.snipara.com/ready
```

Hosted MCP:

```bash
python deploy/infomaniak/check_hosted_mcp.py
```

Expected verification points:

- `tools/list` succeeds on the hosted transport
- the full hosted tool surface is available
- a simple tool call such as `rlm_help` returns successfully

## VPS Paths

- Deploy root: `/opt/snipara`
- Build workspace: `/opt/snipara-build`
- Backend source on host: `/opt/snipara/mcp-backend`

## Notes

- Do not reintroduce obsolete provider-specific config files.
- Production deployment documentation should point to `deploy/infomaniak/`.
- Smoke-test both the `/mcp` and `/v1` backend surfaces after deploy when backend code changes.
