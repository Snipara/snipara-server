# Self-Hosted Enterprise

Snipara Self-Hosted Enterprise is for organizations that need Snipara Server
inside their own infrastructure boundary.

## Typical Requirements

- data residency or sovereignty controls
- private network or air-gapped deployment
- internal model and agent platforms
- existing PostgreSQL, Redis, monitoring, and secret management
- enterprise security review and support commitments

## Included Server Capabilities

- streamable HTTP MCP endpoint
- source-backed project context retrieval
- reviewed durable project memory
- shared team context
- document indexing and chunk retrieval
- code graph retrieval when indexing is enabled
- audit metadata and rate limiting
- Docker-based local evaluation setup

## Commercial Terms

Production use is paid enterprise software and requires a Snipara commercial
agreement. The agreement defines:

- licensed deployment scope
- support level
- update cadence
- permitted users and environments
- renewal and termination terms
- any customer-specific add-ons

The software enforces license configuration through deployment settings:

```text
SNIPARA_LICENSE_REQUIRED=true
SNIPARA_LICENSE_KEY=<issued-by-snipara>
```

## Infrastructure Responsibilities

Self-hosted operators are responsible for:

- database backups and restore testing
- Redis persistence and sizing
- TLS termination
- secret rotation
- patching base images and dependencies
- observability and alerting
- access control and audit retention
- release promotion through staging before production

## Security Boundary

Do not publish or redistribute artifacts containing:

- real `.env` files
- license keys
- API keys
- database URLs with credentials
- private certificates
- customer documents or embeddings
- generated evaluation reports
- debug payloads
- private deployment runbooks

## Getting Started

1. Review [README.md](README.md).
2. Review [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).
3. Configure secrets through your deployment platform.
4. Set `SNIPARA_LICENSE_REQUIRED=true` for production.
5. Verify `/health`, `/ready`, and `/license`.

For enterprise licensing and support, contact Snipara through the official
commercial channel.
