#!/usr/bin/env bash
set -euo pipefail

echo "=== Snipara Server: local workspace setup ==="

: "${DATABASE_URL:?Set DATABASE_URL before running setup}"
: "${SNIPARA_LOCAL_API_KEY:?Set SNIPARA_LOCAL_API_KEY before running setup}"

bash scripts/init-db.sh

python - <<'PY'
import asyncio
import secrets

async def setup() -> None:
    from src.db import get_db

    db = await get_db()
    existing = await db.query_raw(
        'SELECT "id" FROM "projects" WHERE "slug" = $1 AND "deletedAt" IS NULL LIMIT 1',
        "local",
    )
    if existing:
        project_id = existing[0]["id"]
        print(f"Local workspace already exists: {project_id}")
    else:
        user_rows = await db.query_raw(
            'SELECT "id" FROM "users" WHERE "email" = $1 LIMIT 1',
            "local@localhost",
        )
        user_id = user_rows[0]["id"] if user_rows else f"local_{secrets.token_hex(12)}"
        if not user_rows:
            await db.execute_raw(
                'INSERT INTO "users" ("id", "email", "createdAt", "updatedAt") VALUES ($1, $2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)',
                user_id,
                "local@localhost",
            )

        team_rows = await db.query_raw(
            'SELECT "id" FROM "teams" WHERE "slug" = $1 LIMIT 1',
            "local",
        )
        team_id = team_rows[0]["id"] if team_rows else f"local_{secrets.token_hex(12)}"
        if not team_rows:
            await db.execute_raw(
                'INSERT INTO "teams" ("id", "name", "slug", "isPersonal", "createdAt", "updatedAt") VALUES ($1, $2, $3, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)',
                team_id,
                "Local Workspace",
                "local",
            )

        await db.execute_raw(
            'INSERT INTO "team_members" ("id", "role", "createdAt", "updatedAt", "userId", "teamId") VALUES ($1, CAST($2 AS "Role"), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, $3, $4) ON CONFLICT ("userId", "teamId") DO NOTHING',
            f"local_{secrets.token_hex(12)}",
            "OWNER",
            user_id,
            team_id,
        )
        project_id = f"local_{secrets.token_hex(12)}"
        await db.execute_raw(
            'INSERT INTO "projects" ("id", "name", "slug", "teamId", "createdAt", "updatedAt") VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)',
            project_id,
            "Local Workspace",
            "local",
            team_id,
        )
        print(f"Created local workspace: {project_id}")

    print("")
    print("Configure your MCP client:")
    print("")
    print("  {")
    print('    "mcpServers": {')
    print('      "snipara": {')
    print('        "type": "http",')
    print('        "url": "http://localhost:8000/mcp/local",')
    print('        "headers": { "X-API-Key": "<SNIPARA_LOCAL_API_KEY>" }')
    print("      }")
    print("    }")
    print("  }")

asyncio.run(setup())
PY

echo ""
echo "Health: http://localhost:8000/health"
echo "MCP:    http://localhost:8000/mcp/local"
