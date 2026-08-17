#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
umask 077

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required. Install Docker Desktop and run this script again." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required. Update Docker Desktop and run this script again." >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required to verify the local server. Install curl and run this script again." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

if grep -q 'replace-with-a-long-random-local-key' .env; then
  if command -v openssl >/dev/null 2>&1; then
    local_key="$(openssl rand -hex 32)"
  elif [[ -r /dev/urandom ]] && command -v od >/dev/null 2>&1; then
    local_key="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
  else
    echo "OpenSSL or /dev/urandom is required to generate the local API key." >&2
    exit 1
  fi

  awk -v key="$local_key" \
    '{ sub(/replace-with-a-long-random-local-key/, key); print }' \
    .env > .env.quickstart && mv .env.quickstart .env
fi

chmod 600 .env

echo "Starting Snipara and its local PostgreSQL/Redis services..."
docker compose up -d --build

echo "Waiting for the server..."
ready="false"
for _ in $(seq 1 60); do
  if curl --fail --silent --show-error http://localhost:8000/health >/dev/null 2>&1; then
    ready="true"
    break
  fi
  sleep 2
done

if [[ "$ready" != "true" ]]; then
  echo "Snipara did not become healthy. Inspect the logs with: docker compose logs snipara" >&2
  exit 1
fi

docker compose exec -T snipara bash /app/scripts/setup.sh

echo ""
echo "✓ Snipara running       http://localhost:8000"
echo "✓ Project Brain ready   workspace=local"
echo "✓ MCP endpoint          http://localhost:8000/mcp/local"
echo ""
echo "The local API key is stored in .env. Add it to your MCP client as X-API-Key."
echo "See the README for client configuration examples."
