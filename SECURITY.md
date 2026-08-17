# Security Policy

## Reporting a vulnerability

Please do not open a public issue for a security vulnerability. Use the
[private GitHub security advisory form](https://github.com/Snipara/snipara-server/security/advisories/new)
with a description, reproduction steps and the affected version. Do not
include customer data or credentials.

The self-hosted server is intended to run behind an operator-controlled
network boundary. Always configure `SNIPARA_LOCAL_API_KEY`, restrict CORS,
terminate TLS at a trusted reverse proxy, and rotate keys when access changes.

## Scope

Reports may cover the public server, Docker setup, dependencies and release
artifacts. Private Cloud behavior, customer infrastructure and deployment
credentials are out of scope for this repository.
