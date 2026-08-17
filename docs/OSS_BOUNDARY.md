# OSS boundary and compatibility schema

The public compatibility identifier is `snipara-server-oss-v2`. It describes
the self-hosted transport and capability contract; it is not the private Cloud
adapter and it does not grant access to Snipara Cloud.

Snipara Server is the portable, self-hosted runtime. Its public execution
boundary is deliberately smaller than the historical Snipara Cloud backend:

- authentication is a static operator API key (`SNIPARA_LOCAL_API_KEY`);
- `scripts/setup.sh` creates one local workspace and one local principal;
- the MCP contract is project-scoped;
- Cloud-only team traversal, integrator tools, OAuth/device flow, billing,
  partner/reseller administration and internal admin routes are not exposed;
- usage records are local PostgreSQL data and are disabled by default.

## Why the Prisma schema still contains compatibility tables

The first OSS extraction retains a legacy relational compatibility schema around
the project, memory and agent engines. Existing internal memory code uses
`userId` and `teamId` fields to distinguish local ownership scopes, while the
generated Prisma client is shared across those services. Some historical model
definitions therefore remain in the public schema even though their Cloud
routes and tools are not part of the OSS runtime.

The presence of a compatibility model in `prisma/schema.prisma` does not make
the corresponding Cloud feature part of the public product. In particular,
the OSS runtime does not create or manage Cloud users, teams, subscriptions,
integrator clients, partners or OAuth identities. The historical Cloud
migrations were removed; a fresh local database is initialized from the public
schema only.

The Prisma schema is not an authorization boundary. The runtime route and MCP
tool filters, local API-key authentication and the boundary regression checks
are the security boundary. A future schema-major release may remove additional
legacy models after the memory and code-graph dependencies are isolated.

This is an intentional extraction boundary for the `2.0.0` OSS release. A
future schema-major release may replace the compatibility shell with explicit
installation/workspace identifiers, but that migration must be designed and
tested separately so that local memory and code-graph data are not lost.

## Public-surface verification

The release checks must continue to verify that:

```text
tools/list contains no multi-project or integrator tool
REST exposes no /v1/admin/* route
no runtime request accepts external_user_id
no local startup requires api.snipara.com, Vaultbrix, Upstash or a license key
```

This document is the authoritative explanation for the compatibility shell;
it prevents a schema grep from being mistaken for a reintroduction of Cloud
identity or commercial functionality.
