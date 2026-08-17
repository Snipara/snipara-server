# Releasing Snipara Server

Releases are tag-driven. The repository is the source of truth for the public
runtime; the private Cloud consumes only the immutable image digest produced by
the release workflow.

The release contract is `snipara-server-oss-v2`. The public repository contains
the contract identifier and capability document, but never the private Cloud
adapter, customer identity mapping or deployment credentials.

## Before tagging

Run the same checks used by CI:

```bash
ruff check src tests
python -m compileall -q src scripts
pytest -q
DATABASE_URL="postgresql://..." prisma validate --schema prisma/schema.prisma
docker build -t snipara-server:local .
```

Confirm that the change does not introduce Cloud credentials, private URLs,
customer data, hosted-only migrations or a new public tool that depends on
Cloud identity.

Run the public-boundary check before tagging:

```bash
python scripts/verify_oss_boundary.py
```

## Release workflow

Push an annotated semantic-version tag such as `v2.0.0`. The workflow:

1. checks out the exact tag and runs tests, lint and package validation;
2. builds the Python distribution and a multi-architecture container;
3. publishes the container to `ghcr.io/snipara/snipara-server`;
4. sends the source commit, tag and image digest to the private Cloud through
   `repository_dispatch`.

The dispatch is rejected by the Cloud consumer unless the repository, tag,
commit, image name and digest match the expected contract. The Cloud must
deploy the digest, never `latest` and never a fresh build from a moving branch.

## Required repository configuration

- GHCR package permissions for the repository;
- a narrowly scoped `CLOUD_RELEASE_DISPATCH_TOKEN` secret, or an equivalent
  GitHub App identity, with permission to dispatch the private Cloud workflow;
- protected `main` and release tags;
- staging and production environments in the private Cloud repository;
- required production reviewers before the first live rollout.

No Cloud secret, VPS credential, Vaultbrix credential or production deployment
key belongs in this repository.

## Rollback

Record the previous image digest and source tag in every Cloud deployment. A
rollback redeploys that known-good digest and does not rebuild from `main`.
Schema changes must remain backward-compatible for one rollout window or carry
an explicit migration and rollback plan.
