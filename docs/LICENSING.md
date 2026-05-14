# Licensing

Snipara Server is commercial, source-available enterprise software.

## Production Use

Production self-hosted use requires:

- a signed Snipara enterprise license agreement
- a deployment-specific `SNIPARA_LICENSE_KEY`
- `SNIPARA_LICENSE_REQUIRED=true`

The license key must be stored in the customer's secret manager or deployment
environment. It must not be committed to Git.

## Source License

The repository source is distributed under the Functional Source License,
Version 1.1, with an Apache-2.0 future license. See the repository
[LICENSE](../LICENSE) file for the controlling terms.

The Functional Source License permits broad internal use under its terms, but
it does not grant trademark rights and does not permit offering Snipara Server
as a competing hosted or managed context optimization service.

## Runtime Configuration

For local evaluation:

```text
SNIPARA_LICENSE_REQUIRED=false
SNIPARA_LICENSE_KEY=
```

For production:

```text
SNIPARA_LICENSE_REQUIRED=true
SNIPARA_LICENSE_KEY=<issued-by-snipara>
```

The `/license` endpoint reports:

- product name
- license mode
- whether a key is configured
- whether a key is required
- a non-sensitive key fingerprint

It never returns the license key.

## Distribution Rules

Do not publish release artifacts that contain:

- real license keys
- customer data
- API keys
- database credentials
- private certificates
- provider-specific production secrets
- internal evaluation reports or debug payloads
