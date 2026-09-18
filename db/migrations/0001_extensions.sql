-- =============================================================================
-- 0001_extensions.sql
-- Clinician Standing verification platform -- Postgres 15 / Supabase
-- Source of truth: PRD 08-PRD-verification-platform.md, section 5.
-- =============================================================================
--
-- CONVENTIONS USED THROUGHOUT THIS MIGRATION SET
-- -----------------------------------------------------------------------------
-- 1. ENUM APPROACH: **CHECK constraints against text columns**, not Postgres
--    ENUM types. Chosen deliberately and used consistently everywhere:
--      * PRD 5.x declares every one of these columns as `text` with the allowed
--        values in a comment. Honouring the declared type keeps the column
--        contract identical for the Python ingest and the Lovable UI.
--      * PostgREST/Supabase exposes text + CHECK cleanly; ENUM types force
--        clients to know a custom type name and complicate `?status=in.(...)`.
--      * Adding a value later is `ALTER TABLE ... DROP/ADD CONSTRAINT` inside a
--        transaction. `ALTER TYPE ... ADD VALUE` could not run inside a
--        transaction block before PG12 and still cannot be rolled back, which is
--        hostile to a migration tool.
--      * The rules plane is versioned data; the value lists here will move.
--    Every such constraint is named `<table>_<column>_chk` so a later migration
--    can find and replace it mechanically.
--
-- 2. Identifiers are EXACTLY as PRD section 5 spells them. Nothing renamed.
--
-- 3. Columns added beyond the PRD DDL blocks are limited to `created_at` and
--    `deleted_at`, because PRD 5 preamble states: "Soft deletes everywhere
--    (`deleted_at`), because an audit trail cannot lose rows." The per-table
--    snippets only show them on `practices` and `clinicians`; the prose governs.
--    These are additive and nullable/defaulted, so no writer has to know them.
--
-- 4. All timestamps are `timestamptz` (PRD 5: "All timestamps UTC").
--    All UUID primary keys default to `gen_random_uuid()` (pgcrypto).
--
-- 5. Every migration is re-runnable: IF NOT EXISTS on objects, and DO blocks
--    guarding ALTER ... ADD CONSTRAINT.
--
-- 6. Files run strictly in filename order with no forward references. One
--    consequence: `evidence` (PRD 5.4) is created in 0002_core.sql, ahead of the
--    credential tables in 0003 that carry a NOT NULL FK to it. See the note in
--    0002. Nothing about the table differs from PRD 5.4.
-- =============================================================================

-- gen_random_uuid(), digest() for any future payload hashing.
create extension if not exists pgcrypto with schema public;

-- Trigram indexes for clinician/practice name search on the Roster screen (10).
create extension if not exists pg_trgm with schema public;

-- ---------------------------------------------------------------------------
-- `app` schema: helper functions used by the RLS policies in 0008.
-- Created here so every later migration can assume it exists.
-- ---------------------------------------------------------------------------
create schema if not exists app;

comment on schema app is
  'Internal helper functions for row-level security. Not exposed to PostgREST.';
