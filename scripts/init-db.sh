#!/bin/bash
set -e

echo "=== Snipara Server: Database Initialization ==="

# NOTE: Do NOT run `prisma db push` here - it can drop columns if schema drifts.
# Schema migrations are managed via the monorepo's `pnpm db:push` (JS side).
# Prisma client is already generated in Dockerfile build stage.
echo "Verifying Prisma client..."
prisma version 2>/dev/null || echo "Warning: prisma not available"

echo "=== Database initialization complete ==="
