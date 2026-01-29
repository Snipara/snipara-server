#!/bin/bash
set -e

echo "=== Snipara Server: First-Run Setup ==="
echo ""
echo "This script creates your initial project and API key."
echo ""

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo "Error: DATABASE_URL environment variable is not set."
    echo "Run: export DATABASE_URL=postgresql://snipara:snipara@localhost:5433/snipara"
    exit 1
fi

# Run database initialization first
echo "Step 1: Initializing database..."
bash scripts/init-db.sh

# Create initial project and API key
echo ""
echo "Step 2: Creating project and API key..."
python -c "
import asyncio
import secrets
import hashlib
from datetime import datetime, timezone

async def setup():
    from src.db import get_db
    db = await get_db()

    # Check if a project already exists
    existing = await db.query_raw('SELECT id FROM \"Project\" LIMIT 1')
    if existing:
        print('A project already exists. Skipping creation.')
        # Show existing API key
        keys = await db.query_raw('SELECT key FROM \"ApiKey\" WHERE \"revoked\" = false LIMIT 1')
        if keys:
            print(f'Existing API key: {keys[0][\"key\"]}')
        return

    # Create a team
    team_id = secrets.token_hex(12)
    await db.execute_raw(
        '''INSERT INTO \"Team\" (id, name, slug, \"createdAt\", \"updatedAt\")
           VALUES (\$1, 'Default Team', 'default', NOW(), NOW())
           ON CONFLICT DO NOTHING''',
        team_id,
    )
    print(f'Created team: Default Team (id: {team_id})')

    # Create a project
    project_id = secrets.token_hex(12)
    slug = 'my-project'
    await db.execute_raw(
        '''INSERT INTO \"Project\" (id, name, slug, \"teamId\", \"createdAt\", \"updatedAt\")
           VALUES (\$1, 'My Project', \$2, \$3, NOW(), NOW())
           ON CONFLICT DO NOTHING''',
        project_id, slug, team_id,
    )
    print(f'Created project: My Project (slug: {slug})')

    # Generate API key
    raw_key = f'rlm_{secrets.token_hex(24)}'
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_id = secrets.token_hex(12)
    await db.execute_raw(
        '''INSERT INTO \"ApiKey\" (id, name, key, \"hashedKey\", \"projectId\", revoked, \"createdAt\", \"updatedAt\")
           VALUES (\$1, 'Default Key', \$2, \$3, \$4, false, NOW(), NOW())
           ON CONFLICT DO NOTHING''',
        key_id, raw_key, key_hash, project_id,
    )
    print(f'')
    print(f'=== Setup Complete ===')
    print(f'')
    print(f'Project slug: {slug}')
    print(f'API Key:      {raw_key}')
    print(f'')
    print(f'Configure your MCP client:')
    print(f'')
    print(f'  {{')
    print(f'    \"mcpServers\": {{')
    print(f'      \"snipara\": {{')
    print(f'        \"type\": \"http\",')
    print(f'        \"url\": \"http://localhost:8000/mcp/{slug}\",')
    print(f'        \"headers\": {{ \"X-API-Key\": \"{raw_key}\" }}')
    print(f'      }}')
    print(f'    }}')
    print(f'  }}')

asyncio.run(setup())
"

echo ""
echo "Check license status: curl http://localhost:8000/license"
