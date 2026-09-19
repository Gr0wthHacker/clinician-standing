-- =============================================================================
-- db/ci/bootstrap.sql -- Supabase-provided roles, recreated for CI.
--
-- The migrations reference roles that Supabase provisions on a real project but
-- that a plain `postgres:15` container does not have: `anon`, `authenticated`
-- and `service_role` (0008 grants to and checks them), `authenticator` (the role
-- PostgREST connects as, 0008 grants the app roles into it), and `supabase_admin`
-- (referenced by some Supabase-managed objects). Creating them here lets every
-- migration apply in CI exactly as it does on Supabase, so a broken migration
-- fails the build rather than surfacing a month later on the real database.
--
-- This is a CI shim only. It never runs against a real Supabase project, where
-- these roles already exist. It is idempotent: re-running it is a no-op.
-- =============================================================================

do $$ begin create role anon nologin; exception when duplicate_object then null; end $$;
do $$ begin create role authenticated nologin; exception when duplicate_object then null; end $$;
do $$ begin
  create role service_role nologin bypassrls; exception when duplicate_object then null;
end $$;
do $$ begin
  create role authenticator noinherit login; exception when duplicate_object then null;
end $$;
do $$ begin create role supabase_admin superuser; exception when duplicate_object then null; end $$;

grant anon, authenticated, service_role to authenticator;
