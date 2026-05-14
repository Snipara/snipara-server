DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'tenant_snipara' AND t.typname = 'DocumentKind'
    ) THEN
        CREATE TYPE "tenant_snipara"."DocumentKind" AS ENUM ('DOC', 'CODE', 'BINARY');
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'tenant_snipara' AND t.typname = 'IndexJobKind'
    ) THEN
        CREATE TYPE "tenant_snipara"."IndexJobKind" AS ENUM ('DOC', 'CODE');
    ELSIF NOT EXISTS (
        SELECT 1
        FROM pg_enum e
        JOIN pg_type t ON t.oid = e.enumtypid
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'tenant_snipara' AND t.typname = 'IndexJobKind' AND e.enumlabel = 'CODE'
    ) THEN
        ALTER TYPE "tenant_snipara"."IndexJobKind" ADD VALUE 'CODE';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'tenant_snipara' AND t.typname = 'CodeNodeKind'
    ) THEN
        CREATE TYPE "tenant_snipara"."CodeNodeKind" AS ENUM (
            'MODULE',
            'CLASS',
            'FUNCTION',
            'METHOD',
            'IMPORT',
            'VARIABLE'
        );
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'tenant_snipara' AND t.typname = 'CodeEdgeKind'
    ) THEN
        CREATE TYPE "tenant_snipara"."CodeEdgeKind" AS ENUM (
            'CONTAINS',
            'CALLS',
            'IMPORTS',
            'EXTENDS',
            'IMPLEMENTS',
            'REFERENCES'
        );
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'tenant_snipara' AND t.typname = 'EdgeSource'
    ) THEN
        CREATE TYPE "tenant_snipara"."EdgeSource" AS ENUM ('AST', 'HEURISTIC', 'LLM');
    END IF;
END $$;

ALTER TABLE "tenant_snipara"."documents"
    ADD COLUMN IF NOT EXISTS "kind" "tenant_snipara"."DocumentKind";

UPDATE "tenant_snipara"."documents"
SET "kind" = 'DOC'
WHERE "kind" IS NULL;

ALTER TABLE "tenant_snipara"."documents"
    ALTER COLUMN "kind" SET DEFAULT 'DOC',
    ALTER COLUMN "kind" SET NOT NULL;

ALTER TABLE "tenant_snipara"."documents"
    ADD COLUMN IF NOT EXISTS "format" TEXT,
    ADD COLUMN IF NOT EXISTS "language" TEXT;

ALTER TABLE "tenant_snipara"."index_jobs"
    ADD COLUMN IF NOT EXISTS "kind" "tenant_snipara"."IndexJobKind";

UPDATE "tenant_snipara"."index_jobs"
SET "kind" = 'DOC'
WHERE "kind" IS NULL;

ALTER TABLE "tenant_snipara"."index_jobs"
    ALTER COLUMN "kind" SET DEFAULT 'DOC',
    ALTER COLUMN "kind" SET NOT NULL;

CREATE TABLE IF NOT EXISTS "tenant_snipara"."code_nodes" (
    "id" TEXT NOT NULL,
    "projectId" TEXT NOT NULL,
    "documentId" TEXT NOT NULL,
    "kind" "tenant_snipara"."CodeNodeKind" NOT NULL,
    "language" TEXT NOT NULL,
    "modulePath" TEXT NOT NULL,
    "symbolKey" TEXT NOT NULL,
    "qualifiedName" TEXT NOT NULL,
    "localName" TEXT NOT NULL,
    "startLine" INTEGER NOT NULL,
    "endLine" INTEGER NOT NULL,
    "signature" TEXT,
    "docstring" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "code_nodes_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "code_nodes_projectId_fkey"
        FOREIGN KEY ("projectId") REFERENCES "tenant_snipara"."projects"("id")
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "code_nodes_documentId_fkey"
        FOREIGN KEY ("documentId") REFERENCES "tenant_snipara"."documents"("id")
        ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS "tenant_snipara"."code_edges" (
    "id" TEXT NOT NULL,
    "projectId" TEXT NOT NULL,
    "fromNodeId" TEXT NOT NULL,
    "toNodeId" TEXT NOT NULL,
    "kind" "tenant_snipara"."CodeEdgeKind" NOT NULL,
    "source" "tenant_snipara"."EdgeSource" NOT NULL DEFAULT 'AST',
    "confidence" DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "code_edges_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "code_edges_projectId_fkey"
        FOREIGN KEY ("projectId") REFERENCES "tenant_snipara"."projects"("id")
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "code_edges_fromNodeId_fkey"
        FOREIGN KEY ("fromNodeId") REFERENCES "tenant_snipara"."code_nodes"("id")
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "code_edges_toNodeId_fkey"
        FOREIGN KEY ("toNodeId") REFERENCES "tenant_snipara"."code_nodes"("id")
        ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS "tenant_snipara"."code_index_state" (
    "documentId" TEXT NOT NULL,
    "projectId" TEXT NOT NULL,
    "documentHash" TEXT NOT NULL,
    "extractorVersion" INTEGER NOT NULL,
    "indexedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "code_index_state_pkey" PRIMARY KEY ("documentId"),
    CONSTRAINT "code_index_state_documentId_fkey"
        FOREIGN KEY ("documentId") REFERENCES "tenant_snipara"."documents"("id")
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "code_index_state_projectId_fkey"
        FOREIGN KEY ("projectId") REFERENCES "tenant_snipara"."projects"("id")
        ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS "code_nodes_projectId_symbolKey_key"
    ON "tenant_snipara"."code_nodes"("projectId", "symbolKey");

CREATE INDEX IF NOT EXISTS "code_nodes_projectId_language_qualifiedName_idx"
    ON "tenant_snipara"."code_nodes"("projectId", "language", "qualifiedName");

CREATE INDEX IF NOT EXISTS "code_nodes_documentId_idx"
    ON "tenant_snipara"."code_nodes"("documentId");

CREATE UNIQUE INDEX IF NOT EXISTS "code_edges_fromNodeId_toNodeId_kind_key"
    ON "tenant_snipara"."code_edges"("fromNodeId", "toNodeId", "kind");

CREATE INDEX IF NOT EXISTS "code_edges_projectId_kind_idx"
    ON "tenant_snipara"."code_edges"("projectId", "kind");

CREATE INDEX IF NOT EXISTS "code_edges_toNodeId_kind_idx"
    ON "tenant_snipara"."code_edges"("toNodeId", "kind");

CREATE INDEX IF NOT EXISTS "code_index_state_projectId_indexedAt_idx"
    ON "tenant_snipara"."code_index_state"("projectId", "indexedAt");

CREATE INDEX IF NOT EXISTS "code_index_state_projectId_documentHash_idx"
    ON "tenant_snipara"."code_index_state"("projectId", "documentHash");

CREATE INDEX IF NOT EXISTS "documents_projectId_kind_idx"
    ON "tenant_snipara"."documents"("projectId", "kind");

CREATE INDEX IF NOT EXISTS "documents_projectId_kind_format_idx"
    ON "tenant_snipara"."documents"("projectId", "kind", "format");

CREATE INDEX IF NOT EXISTS "index_jobs_projectId_kind_createdAt_idx"
    ON "tenant_snipara"."index_jobs"("projectId", "kind", "createdAt");
