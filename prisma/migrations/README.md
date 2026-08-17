# Database setup in OSS mode

The public server uses `prisma/schema.prisma` as its local schema source of
truth. Run `scripts/init-db.sh` (or `scripts/setup.sh`) against the local
PostgreSQL instance to create or update the schema during development.

Historical Cloud migration scripts were intentionally not copied into this
repository. They target private deployment schemas and are not a safe or
portable migration path for self-hosted installations. Production Cloud
migrations remain private operational artifacts and must be applied through
the Cloud deployment process.
