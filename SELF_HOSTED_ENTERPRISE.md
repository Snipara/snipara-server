# Self-Hosted Snipara Server

Snipara Server is the open source, self-hosted runtime for organizations and
individual operators who want project context and memory inside their own
infrastructure boundary.

## Included capabilities

- streamable HTTP MCP endpoint
- source-backed project context retrieval
- persistent project memory and decisions
- document indexing and chunk retrieval
- optional code graph and multi-agent tools
- local PostgreSQL/pgvector and Redis Compose setup
- local API-key authentication and local-only usage tracking

## Operator responsibilities

Operators are responsible for:

- database backups and restore testing
- TLS termination and network access control
- secret rotation
- patching base images and dependencies
- observability and alerting
- Redis sizing and persistence when enabled
- release promotion and rollback

## Security boundary

Configure SNIPARA_LOCAL_API_KEY, restrict CORS, and put internet-facing
deployments behind a trusted TLS reverse proxy. Do not publish environment
files, credentials, customer documents, embeddings or private Cloud runbooks.

## License

The server is distributed under Apache-2.0. See [LICENSE](LICENSE) and
[docs/LICENSING.md](docs/LICENSING.md).
