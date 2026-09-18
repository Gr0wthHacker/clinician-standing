-- =============================================================================
-- 0011_ingest_role.sql -- a login role for the ingest, and FORCE RLS.
--
-- WHAT THIS FIXES
-- -----------------------------------------------------------------------------
-- 0008_rls.sql builds a careful three-role model: app_internal, app_delivery
-- and app_client_portal, each gated twice (GRANTs decide which tables, policies
-- decide which rows). None of it applied to the one credential this system
-- actually uses. `.env.example` and both READMEs pointed DATABASE_URL at
--
--     postgresql://postgres.PROJECTREF:...@...pooler.supabase.com:6543/postgres
--
-- which is Supabase's `postgres` role: it owns every table in this schema and
-- carries BYPASSRLS. A monthly ingest job, running unattended from a GitHub
-- Actions runner, held the one credential that reads and writes every row of
-- every table regardless of any policy in 0008 -- and the same credential could
-- DROP the schema. The blast radius of that secret leaking was the entire
-- database; the three-role model contributed nothing to it.
--
-- Two changes here:
--
--   1. app_ingest -- a LOGIN role whose only privilege is membership in
--      app_internal. It owns nothing, it creates nothing, and it does not have
--      BYPASSRLS, so every statement it runs is filtered by the policies in
--      0008. It is the role DATABASE_URL should name.
--
--   2. FORCE ROW LEVEL SECURITY on all 16 tables, so that a connection which
--      happens to own a table is still subject to that table's policies.
--      Without it, RLS is silently inert for the owner -- which is exactly the
--      connection the ingest was using.
--
-- WHAT THIS DOES NOT FIX
-- -----------------------------------------------------------------------------
-- A superuser, and any role with BYPASSRLS (Supabase's `postgres` and
-- `service_role` both have it), still bypasses both RLS and FORCE RLS. That is
-- how Postgres works and it is not something a migration can change. It is why
-- the superuser URI has to stop being the ingest's credential and become a
-- separate, rarely-used, migrations-only secret. See the README table.
--
-- MIGRATIONS still run as the owner/superuser. This file does not change that,
-- and must not: app_ingest has no DDL rights by design.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. THE INGEST LOGIN ROLE
--
-- NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION are spelled out
-- rather than left to defaults, because the defaults are what a future `create
-- role` copied from elsewhere would quietly change. INHERIT is required: the
-- role's entire reach comes from app_internal membership, and without INHERIT
-- it would have to SET ROLE on every connection.
--
-- NO PASSWORD IS SET HERE. A migration is a tracked file; a password in one is
-- a committed secret. After applying this migration, set the password once, out
-- of band, and store it in the secret manager / GitHub Actions secret:
--
--     alter role app_ingest with password '<generated>';
--
-- Until that is done the role exists and cannot authenticate, which is the
-- correct failure. Rotating the ingest credential is that same statement; it
-- does not touch the superuser password, which is the point of splitting them.
-- ---------------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'app_ingest') then
    create role app_ingest
      login
      nosuperuser
      nobypassrls
      nocreatedb
      nocreaterole
      noreplication
      inherit;
  else
    -- Re-runnable, and it re-asserts the attributes in case someone widened
    -- them by hand. Deliberately does not touch the password.
    alter role app_ingest
      login nosuperuser nobypassrls nocreatedb nocreaterole noreplication inherit;
  end if;
end $$;

comment on role app_ingest is
  'Login role for the ingest jobs (PRD 6). Member of app_internal and nothing else: no ownership, no DDL, no BYPASSRLS. DATABASE_URL names this role; the superuser URI is a separate migrations-only secret.';

-- The whole of its reach. app_internal already carries the table grants and the
-- *_internal_all policies from 0008; app_ingest inherits both.
grant app_internal to app_ingest;

-- Explicitly NOT granted, and each for a reason:
--   app_delivery, app_client_portal -- unrelated personas; membership would
--                                      only add policies, never remove any, but
--                                      it would muddy `pg_has_role` checks.
--   create on schema public         -- the ingest creates TEMPORARY tables for
--                                      staging, which needs TEMP on the
--                                      database (granted to PUBLIC by default),
--                                      not CREATE on a schema. It must never be
--                                      able to add a permanent object: the
--                                      schema is defined by db/migrations/ and
--                                      nothing else (CONTRIBUTING.md).
revoke create on schema public from app_ingest;

-- ---------------------------------------------------------------------------
-- 2. FORCE ROW LEVEL SECURITY ON ALL 16 TABLES
--
-- `enable row level security` (0008) exempts the table owner. `force` removes
-- that exemption, so a connection that owns the table is filtered by the same
-- policies as everyone else. With app_internal holding `using (true) with check
-- (true)` on every table, this changes nothing for a correctly configured
-- ingest and closes the hole for a misconfigured one.
--
-- Same table list as 0008, in the same order, on purpose: the two blocks are
-- meant to be read side by side, and a table missing from one is a hole.
-- ---------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array[
    'practices','clinicians','affiliations',
    'licenses','registrations','enrollments','privileges','ce_records','sanctions',
    'requirements','requirement_conflicts',
    'obligations','evidence','exceptions',
    'sources','source_runs']
  loop
    execute format('alter table public.%I force row level security', t);
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- 3. SELF-CHECK
--
-- Fails the migration rather than leaving a half-applied security change. Both
-- of these are cheap and both have been wrong before.
-- ---------------------------------------------------------------------------
do $$
declare
  unforced text;
  bad_attr text;
begin
  select string_agg(c.relname, ', ' order by c.relname) into unforced
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public'
    and c.relkind = 'r'
    and c.relname in (
      'practices','clinicians','affiliations',
      'licenses','registrations','enrollments','privileges','ce_records','sanctions',
      'requirements','requirement_conflicts',
      'obligations','evidence','exceptions',
      'sources','source_runs')
    and not (c.relrowsecurity and c.relforcerowsecurity);
  if unforced is not null then
    raise exception 'RLS is not enabled and forced on: %', unforced;
  end if;

  select string_agg(x, ', ') into bad_attr
  from (
    select 'superuser' as x from pg_roles where rolname = 'app_ingest' and rolsuper
    union all
    select 'bypassrls' from pg_roles where rolname = 'app_ingest' and rolbypassrls
    union all
    select 'createrole' from pg_roles where rolname = 'app_ingest' and rolcreaterole
    union all
    select 'createdb' from pg_roles where rolname = 'app_ingest' and rolcreatedb
  ) s;
  if bad_attr is not null then
    raise exception 'app_ingest must not carry: %', bad_attr;
  end if;
end $$;
