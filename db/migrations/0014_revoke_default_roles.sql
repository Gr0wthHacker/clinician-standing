-- =============================================================================
-- 0014_revoke_default_roles.sql -- take the Supabase default roles off the data.
--
-- WHAT THIS FIXES
-- -----------------------------------------------------------------------------
-- 0008 built the three-role model (app_internal / app_delivery /
-- app_client_portal) and revoked the app tables from PUBLIC. It did not touch
-- Supabase's own default roles, `anon` and `authenticated`. On a Supabase
-- project those two roles are granted to `authenticator` and are what PostgREST
-- uses for an unauthenticated (`anon`) or a default-authenticated
-- (`authenticated`) request, and the platform's bootstrap hands them broad
-- privileges on schema public. Left in place, a request that never SET ROLEs to
-- one of the app_* roles could still read app tables directly -- the evidence
-- store, the sanctions table, the rules plane -- straight past the policy model
-- 0008 and 0011 built.
--
-- This system does not use `anon` or `authenticated`. Every persona is a real
-- app_* role reached through the JWT `role` claim (0008). So both defaults are
-- stripped of all access to schema public here, and the default privileges that
-- would re-grant them on future objects are revoked too. There is no frontend
-- yet (the screens are a later phase), so nothing depends on the old grants.
--
-- Idempotent and guarded: on a plain Postgres cluster without these roles the
-- migration is a no-op, so it runs the same in CI as on Supabase.
-- =============================================================================

do $$
begin
  if not exists (select 1 from pg_roles where rolname in ('anon', 'authenticated')) then
    raise notice 'no anon/authenticated roles (not a Supabase cluster); nothing to revoke';
    return;
  end if;

  -- Current privileges on everything already in schema public.
  execute 'revoke all on all tables in schema public from anon, authenticated';
  execute 'revoke all on all sequences in schema public from anon, authenticated';
  execute 'revoke all on all routines in schema public from anon, authenticated';
  -- The ability to see the schema at all.
  execute 'revoke usage on schema public from anon, authenticated';
  execute 'revoke usage on schema app from anon, authenticated';

  -- Future objects. ALTER DEFAULT PRIVILEGES only governs objects created by the
  -- role that runs it, so this covers what THIS migration role creates from now
  -- on; it does not, and cannot, rewrite defaults set by Supabase's bootstrap
  -- role. The explicit revokes above are what handle the objects that exist.
  execute 'alter default privileges in schema public '
          'revoke all on tables from anon, authenticated';
  execute 'alter default privileges in schema public '
          'revoke all on sequences from anon, authenticated';
  execute 'alter default privileges in schema public '
          'revoke all on functions from anon, authenticated';
end $$;

-- ---------------------------------------------------------------------------
-- SELF-CHECK. Fail the migration rather than leave a default role holding a
-- grant on an app table. Reads the ACL off pg_class via aclexplode so the check
-- does not depend on who runs the migration. Skipped when the roles are absent.
-- ---------------------------------------------------------------------------
do $$
declare leaked text;
begin
  if not exists (select 1 from pg_roles where rolname in ('anon', 'authenticated')) then
    return;
  end if;
  select string_agg(format('%s->%s', g.rolname, c.relname), ', ') into leaked
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  cross join lateral aclexplode(c.relacl) acl
  join pg_roles g on g.oid = acl.grantee
  where n.nspname = 'public'
    and c.relkind in ('r', 'v', 'm')
    and g.rolname in ('anon', 'authenticated');
  if leaked is not null then
    raise exception 'anon/authenticated still hold a grant in public: %', leaked;
  end if;
end $$;
