#!/bin/bash
set -e

echo "=== Snipara Server: Database Initialization ==="

echo "Running Prisma migrations..."
prisma db push --accept-data-loss --skip-generate 2>/dev/null || {
    echo "Warning: prisma db push failed, retrying..."
    sleep 3
    prisma db push --accept-data-loss --skip-generate
}

echo "Creating license state table..."
python -c "
import asyncio
from src.license import ensure_license_table
asyncio.run(ensure_license_table())
" 2>/dev/null || echo "Warning: License table creation skipped (will retry on first request)"

echo "=== Database initialization complete ==="
