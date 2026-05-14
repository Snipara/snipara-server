-- Migration: restore legacy AgentMemory status column for MCP smoke tests.
-- Keep idempotent so it can be applied safely on existing instances.

ALTER TABLE "tenant_snipara"."agent_memories"
    ADD COLUMN IF NOT EXISTS "status" "tenant_snipara"."MemoryStatus" NOT NULL DEFAULT 'ACTIVE';

ALTER TABLE "tenant_snipara"."agent_memories"
    ADD COLUMN IF NOT EXISTS "invalidatedAt" TIMESTAMP(3),
    ADD COLUMN IF NOT EXISTS "invalidatedReason" TEXT,
    ADD COLUMN IF NOT EXISTS "supersededByMemoryId" TEXT;
