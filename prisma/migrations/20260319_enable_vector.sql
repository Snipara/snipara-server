-- Migration: Enable pgvector extension
-- Run this on Vaultbrix (tenant_snipara schema)
-- Required for embedding-based semantic search

-- Enable in public schema (where extensions live)
CREATE EXTENSION IF NOT EXISTS vector SCHEMA public;

-- Grant usage to ensure tenant_snipara can use vector type
GRANT USAGE ON SCHEMA public TO postgres;
