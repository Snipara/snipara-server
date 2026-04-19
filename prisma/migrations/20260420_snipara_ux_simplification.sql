-- Migration: Snipara UX simplification (one-key + auto-resolved projects)
--
-- Adds:
--   teams.autoCreateProjects           — gate for MCP auto-create of unknown slugs
--   projects.deletedAt                 — soft-delete for stale auto-created projects
--   projects @@index(githubRepo)       — lookup by "owner/repo" at auth time
--   projects @@index(deletedAt)        — cleanup cron scan window
--   github_installations               — GitHub App installations per team
--
-- Purely additive. Idempotent. Safe for concurrent Snipara backend traffic.
-- Apply via: ./deploy/infomaniak/migrate-vaultbrix.sh <this-file>

-- Team: gate for MCP auto-create-on-unknown-slug
ALTER TABLE "tenant_snipara"."teams"
    ADD COLUMN IF NOT EXISTS "autoCreateProjects" BOOLEAN NOT NULL DEFAULT true;

-- Project: soft-delete + new indexes
ALTER TABLE "tenant_snipara"."projects"
    ADD COLUMN IF NOT EXISTS "deletedAt" TIMESTAMP(3);

CREATE INDEX IF NOT EXISTS "projects_githubRepo_idx"
    ON "tenant_snipara"."projects"("githubRepo");

CREATE INDEX IF NOT EXISTS "projects_deletedAt_idx"
    ON "tenant_snipara"."projects"("deletedAt");

-- GitHub App installations (one per GitHub account/org that installed
-- the Snipara App). Tied to a team; cascade on team delete.
CREATE TABLE IF NOT EXISTS "tenant_snipara"."github_installations" (
    "id"             TEXT         NOT NULL,
    "installationId" BIGINT       NOT NULL,
    "accountLogin"   TEXT         NOT NULL,
    "accountType"    TEXT         NOT NULL,
    "suspendedAt"    TIMESTAMP(3),
    "createdAt"      TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt"      TIMESTAMP(3) NOT NULL,
    "teamId"         TEXT         NOT NULL,

    CONSTRAINT "github_installations_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "github_installations_installationId_key"
    ON "tenant_snipara"."github_installations"("installationId");

CREATE INDEX IF NOT EXISTS "github_installations_teamId_idx"
    ON "tenant_snipara"."github_installations"("teamId");

-- FK last so CREATE TABLE is idempotent with IF NOT EXISTS; only add FK if
-- the constraint doesn't already exist.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'github_installations_teamId_fkey'
          AND table_schema   = 'tenant_snipara'
    ) THEN
        ALTER TABLE "tenant_snipara"."github_installations"
            ADD CONSTRAINT "github_installations_teamId_fkey"
            FOREIGN KEY ("teamId")
            REFERENCES "tenant_snipara"."teams"("id")
            ON DELETE CASCADE
            ON UPDATE CASCADE;
    END IF;
END
$$;
