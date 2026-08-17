#!/bin/bash
set -e

echo "=== Snipara Server: Database Initialization ==="

# This command is intentionally limited to the local/self-hosted database
# declared by DATABASE_URL. Production Cloud migrations use a separate,
# reviewed migration process and must never call this script.
if [ -z "${DATABASE_URL:-}" ]; then
    echo "Error: DATABASE_URL is not set."
    exit 1
fi

echo "Applying the OSS Prisma schema to the configured local database..."
prisma db push --schema prisma/schema.prisma --skip-generate

echo "=== Database initialization complete ==="
