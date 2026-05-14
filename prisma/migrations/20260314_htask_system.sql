-- Migration: Add Hierarchical Task System
-- Run this manually on PostgreSQL (tenant_snipara schema)

-- Create htask enums
DO $$ BEGIN
    CREATE TYPE "tenant_snipara"."HTaskLevel" AS ENUM ('N0_INITIATIVE', 'N1_FEATURE', 'N2_WORKSTREAM', 'N3_TASK');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE "tenant_snipara"."HTaskStatus" AS ENUM ('PENDING', 'IN_PROGRESS', 'BLOCKED', 'FAILED', 'COMPLETED', 'CANCELLED');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE "tenant_snipara"."HTaskPriority" AS ENUM ('P0', 'P1', 'P2');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE "tenant_snipara"."BlockerType" AS ENUM ('TECH', 'DEPENDENCY', 'ACCESS', 'PRODUCT', 'INFRA', 'SECURITY', 'OTHER');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE "tenant_snipara"."WorkstreamType" AS ENUM ('API', 'FRONTEND', 'QA', 'BUGFIX_HARDENING', 'DEPLOY_PROD_VERIFY', 'DATA', 'SECURITY', 'DOCUMENTATION', 'CUSTOM', 'OTHER');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE "tenant_snipara"."ExecutionTarget" AS ENUM ('LOCAL', 'CLOUD', 'HYBRID', 'EXTERNAL');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE "tenant_snipara"."ClosurePolicy" AS ENUM ('STRICT_ALL_CHILDREN', 'ALLOW_EXCEPTIONS');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE "tenant_snipara"."CompatMode" AS ENUM ('LEGACY', 'DUAL', 'SHADOW', 'HTASK');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Create HTaskPolicy table
CREATE TABLE IF NOT EXISTS "tenant_snipara"."htask_policies" (
    "id" TEXT NOT NULL,
    "swarmId" TEXT NOT NULL,
    "maxDepth" INTEGER NOT NULL DEFAULT 4,
    "closurePolicy" "tenant_snipara"."ClosurePolicy" NOT NULL DEFAULT 'STRICT_ALL_CHILDREN',
    "requireEvidenceOnComplete" BOOLEAN NOT NULL DEFAULT true,
    "allowParentCloseWithWaiver" BOOLEAN NOT NULL DEFAULT true,
    "failedIsBlockingDefault" BOOLEAN NOT NULL DEFAULT true,
    "allowStructuralUpdate" BOOLEAN NOT NULL DEFAULT false,
    "allowHardDelete" BOOLEAN NOT NULL DEFAULT false,
    "compatMode" "tenant_snipara"."CompatMode" NOT NULL DEFAULT 'LEGACY',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "htask_policies_pkey" PRIMARY KEY ("id")
);

-- Create HTaskEvent table
CREATE TABLE IF NOT EXISTS "tenant_snipara"."htask_events" (
    "id" TEXT NOT NULL,
    "swarmId" TEXT NOT NULL,
    "taskId" TEXT NOT NULL,
    "eventType" TEXT NOT NULL,
    "payload" JSONB,
    "actorId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "htask_events_pkey" PRIMARY KEY ("id")
);

-- Create HierarchicalTask table
CREATE TABLE IF NOT EXISTS "tenant_snipara"."hierarchical_tasks" (
    "id" TEXT NOT NULL,
    "swarmId" TEXT NOT NULL,
    "level" "tenant_snipara"."HTaskLevel" NOT NULL DEFAULT 'N3_TASK',
    "parentId" TEXT,
    "sequenceNumber" INTEGER NOT NULL DEFAULT 1,
    "workstreamType" "tenant_snipara"."WorkstreamType",
    "customWorkstreamType" TEXT,
    "title" TEXT NOT NULL,
    "description" TEXT NOT NULL,
    "owner" TEXT NOT NULL,
    "executionTarget" "tenant_snipara"."ExecutionTarget",
    "priority" "tenant_snipara"."HTaskPriority" NOT NULL DEFAULT 'P1',
    "etaTarget" TIMESTAMP(3),
    "acceptanceCriteria" JSONB NOT NULL DEFAULT '[]',
    "contextRefs" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "evidenceRequired" JSONB NOT NULL DEFAULT '[]',
    "evidenceProvided" JSONB,
    "status" "tenant_snipara"."HTaskStatus" NOT NULL DEFAULT 'PENDING',
    "isBlocking" BOOLEAN NOT NULL DEFAULT true,
    "blockerType" "tenant_snipara"."BlockerType",
    "blockerReason" TEXT,
    "blockedByTaskId" TEXT,
    "requiredInput" TEXT,
    "etaRecovery" TIMESTAMP(3),
    "escalationTo" TEXT,
    "blockedAt" TIMESTAMP(3),
    "waiverReason" TEXT,
    "waiverApprovedBy" TEXT,
    "waiverApprovedAt" TIMESTAMP(3),
    "result" JSONB,
    "error" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "startedAt" TIMESTAMP(3),
    "completedAt" TIMESTAMP(3),
    "archivedAt" TIMESTAMP(3),
    CONSTRAINT "hierarchical_tasks_pkey" PRIMARY KEY ("id")
);

-- Create unique constraints
CREATE UNIQUE INDEX IF NOT EXISTS "htask_policies_swarmId_key" ON "tenant_snipara"."htask_policies"("swarmId");
CREATE UNIQUE INDEX IF NOT EXISTS "hierarchical_tasks_swarmId_parentId_sequenceNumber_key" ON "tenant_snipara"."hierarchical_tasks"("swarmId", "parentId", "sequenceNumber");

-- Create indexes
CREATE INDEX IF NOT EXISTS "htask_events_swarmId_eventType_idx" ON "tenant_snipara"."htask_events"("swarmId", "eventType");
CREATE INDEX IF NOT EXISTS "htask_events_swarmId_taskId_idx" ON "tenant_snipara"."htask_events"("swarmId", "taskId");
CREATE INDEX IF NOT EXISTS "htask_events_swarmId_createdAt_idx" ON "tenant_snipara"."htask_events"("swarmId", "createdAt");
CREATE INDEX IF NOT EXISTS "hierarchical_tasks_swarmId_level_idx" ON "tenant_snipara"."hierarchical_tasks"("swarmId", "level");
CREATE INDEX IF NOT EXISTS "hierarchical_tasks_swarmId_status_idx" ON "tenant_snipara"."hierarchical_tasks"("swarmId", "status");
CREATE INDEX IF NOT EXISTS "hierarchical_tasks_swarmId_parentId_idx" ON "tenant_snipara"."hierarchical_tasks"("swarmId", "parentId");
CREATE INDEX IF NOT EXISTS "hierarchical_tasks_owner_idx" ON "tenant_snipara"."hierarchical_tasks"("owner");
CREATE INDEX IF NOT EXISTS "hierarchical_tasks_archivedAt_idx" ON "tenant_snipara"."hierarchical_tasks"("archivedAt");

-- Add foreign keys
ALTER TABLE "tenant_snipara"."htask_policies"
    ADD CONSTRAINT "htask_policies_swarmId_fkey"
    FOREIGN KEY ("swarmId") REFERENCES "tenant_snipara"."agent_swarms"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "tenant_snipara"."hierarchical_tasks"
    ADD CONSTRAINT "hierarchical_tasks_swarmId_fkey"
    FOREIGN KEY ("swarmId") REFERENCES "tenant_snipara"."agent_swarms"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "tenant_snipara"."hierarchical_tasks"
    ADD CONSTRAINT "hierarchical_tasks_parentId_fkey"
    FOREIGN KEY ("parentId") REFERENCES "tenant_snipara"."hierarchical_tasks"("id")
    ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE "tenant_snipara"."hierarchical_tasks"
    ADD CONSTRAINT "hierarchical_tasks_blockedByTaskId_fkey"
    FOREIGN KEY ("blockedByTaskId") REFERENCES "tenant_snipara"."hierarchical_tasks"("id")
    ON DELETE SET NULL ON UPDATE CASCADE;
