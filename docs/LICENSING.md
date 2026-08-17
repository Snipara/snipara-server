# Licensing

Snipara Server is free and open source software under the Apache License,
Version 2.0.

## What the license allows

The Apache-2.0 license permits personal, educational and commercial use,
including modification, redistribution and operation as a hosted service,
subject to the license terms and notices.

It does not grant rights to Snipara trademarks, logos or branding. Do not imply
endorsement or affiliation without permission.

## Contributions

Contributions are accepted under the repository contribution terms. Do not
submit customer data, private Cloud code, secrets, credentials or proprietary
deployment material.

## Runtime privacy

The server does not require a Snipara account or send data to Snipara Cloud.
Usage tracking, when enabled, writes a local query ledger to PostgreSQL. Sentry,
remote embedding services and other external providers are opt-in through
environment variables.

## Distribution checklist

Do not publish artifacts containing:

- API keys, passwords, tokens or private certificates;
- database URLs with credentials;
- customer documents, prompts or memory contents;
- private Cloud URLs, deployment paths or internal runbooks;
- unreviewed generated reports or debug payloads.

See [LICENSE](../LICENSE) for the controlling license text.
