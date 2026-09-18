-- =============================================================================
-- 0008_rls.sql -- Row-level security. PRD 12:
--   "Row-level security in Supabase by practice."
--   "Offshore associates access the action queue only, never the evidence store
--    or the rules admin."
--
-- THREE APPLICATION ROLES
-- -----------------------------------------------------------------------------
--   app_internal       QA specialist, team lead, account lead, and the ingest
--                      jobs. Full read/write on everything.
--   app_delivery       Offshore delivery associate ($4/hr, ~5 FTE, PRD 3).
--                      Action queue plus the roster fields needed to pre-fill a
--                      form. NO grant whatsoever on evidence, sanctions,
--                      requirements, requirement_conflicts, exceptions, sources
--                      or source_runs -- not a policy that returns zero rows, no
--                      table privilege at all, so the failure is a hard
--                      permission error rather than a silent empty result.
--   app_client_portal  Client administrator (PRD 3). Read-only, and only rows
--                      belonging to its own practice.
--
-- Two independent gates are used, because RLS alone is not access control:
--   1. GRANTs decide which tables a role may touch at all.
--   2. POLICIES decide which rows, within the tables it may touch.
-- Supabase's `service_role` has BYPASSRLS and is unaffected; it should be used
-- only by trusted server-side jobs, never handed to a browser.
--
-- Practice scoping comes from the JWT: claim `practice_id` (uuid) and/or
-- `practice_ids` (array of uuid). Role identity comes from real Postgres role
-- membership, so it works for a PostgREST request that SET ROLEs from the JWT
-- `role` claim and equally for a direct connection from a job.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Roles. NOLOGIN: they are assumed, never connected to directly.
-- ---------------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'app_internal') then
    create role app_internal nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'app_delivery') then
    create role app_delivery nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'app_client_portal') then
    create role app_client_portal nologin;
  end if;
end $$;

comment on role app_internal is 'Internal staff and ingest jobs. Full access.';
comment on role app_delivery is 'Offshore delivery associate. Action queue only -- never evidence or rules (PRD 12).';
comment on role app_client_portal is 'Client administrator. Read-only, own practice only.';

-- On Supabase, PostgREST switches roles from the JWT `role` claim, which
-- requires the `authenticator` role to be a member of each target role.
-- Guarded so this migration also runs on a plain Postgres cluster.
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'authenticator') then
    grant app_internal, app_delivery, app_client_portal to authenticator;
  end if;
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant app_internal to service_role;
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- Claim helpers (schema `app`, created in 0001).
-- ---------------------------------------------------------------------------
create or replace function app.jwt_claims()
returns jsonb
language sql
stable
as $$
  select coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb,
                  '{}'::jsonb);
$$;

comment on function app.jwt_claims() is
  'The verified JWT claim set for this request, or {} outside a PostgREST request.';

-- Practices this session may see. Reads `practice_id` and/or `practice_ids`.
create or replace function app.portal_practice_ids()
returns uuid[]
language sql
stable
as $$
  select coalesce(
    array_remove(
      array(select (jsonb_array_elements_text(
                      case jsonb_typeof(app.jwt_claims() -> 'practice_ids')
                        when 'array' then app.jwt_claims() -> 'practice_ids'
                        else '[]'::jsonb
                      end))::uuid)
      || case
           when (app.jwt_claims() ->> 'practice_id') is not null
             then array[(app.jwt_claims() ->> 'practice_id')::uuid]
           else array[]::uuid[]
         end,
      null),
    array[]::uuid[]);
$$;

comment on function app.portal_practice_ids() is
  'Practice ids this request is scoped to, from the JWT. Empty array means no practice scope, which denies every client-portal policy.';

create or replace function app.is_internal()
returns boolean language sql stable as
$$ select pg_has_role(current_user, 'app_internal', 'member'); $$;

create or replace function app.is_delivery()
returns boolean language sql stable as
$$ select pg_has_role(current_user, 'app_delivery', 'member'); $$;

create or replace function app.is_client_portal()
returns boolean language sql stable as
$$ select pg_has_role(current_user, 'app_client_portal', 'member'); $$;

revoke all on schema app from public;
grant usage on schema app to app_internal, app_delivery, app_client_portal;
grant execute on function app.jwt_claims(), app.portal_practice_ids(),
                         app.is_internal(), app.is_delivery(),
                         app.is_client_portal()
  to app_internal, app_delivery, app_client_portal;

-- =============================================================================
-- 1. ENABLE RLS ON ALL 16 TABLES
-- =============================================================================
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
    execute format('alter table public.%I enable row level security', t);
  end loop;
end $$;

-- =============================================================================
-- 2. BASELINE GRANTS -- nothing is reachable unless granted below.
-- =============================================================================
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
    execute format('revoke all on public.%I from public', t);
    execute format('revoke all on public.%I from app_internal, app_delivery, app_client_portal', t);
    execute format('grant select, insert, update, delete on public.%I to app_internal', t);
  end loop;
end $$;

grant usage on schema public to app_internal, app_delivery, app_client_portal;

-- =============================================================================
-- 3. INTERNAL POLICIES -- full access on every table.
-- =============================================================================
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
    execute format('drop policy if exists %I on public.%I', t || '_internal_all', t);
    execute format(
      'create policy %I on public.%I for all to app_internal using (true) with check (true)',
      t || '_internal_all', t);
  end loop;
end $$;

-- =============================================================================
-- 4. CLIENT PORTAL -- read-only, own practice only (PRD 3, PRD 10).
-- Scope reaches clinicians and their credentials through an active-or-past
-- affiliation to a permitted practice. Soft-deleted rows are never returned.
-- =============================================================================

grant select on
  practices, clinicians, affiliations,
  licenses, registrations, enrollments, privileges, ce_records, obligations
to app_client_portal;

-- Deliberately NOT granted to app_client_portal:
--   evidence               -- the evidence store is internal (PRD 12)
--   sanctions              -- an exclusion or discipline hit is HIGH_CONSEQUENCE
--                             and reaches the client through the account lead,
--                             not through a self-serve portal (PRD 8.3)
--   requirements, requirement_conflicts  -- rules admin is QA-only (PRD 10)
--   exceptions             -- internal work state
--   sources, source_runs   -- Source health is an engineering screen (PRD 10)

drop policy if exists practices_portal_select on practices;
create policy practices_portal_select on practices
  for select to app_client_portal
  using (deleted_at is null and id = any (app.portal_practice_ids()));

drop policy if exists affiliations_portal_select on affiliations;
create policy affiliations_portal_select on affiliations
  for select to app_client_portal
  using (deleted_at is null and practice_id = any (app.portal_practice_ids()));

drop policy if exists clinicians_portal_select on clinicians;
create policy clinicians_portal_select on clinicians
  for select to app_client_portal
  using (deleted_at is null and exists (
    select 1 from affiliations a
    where a.clinician_id = clinicians.id
      and a.deleted_at is null
      and a.practice_id = any (app.portal_practice_ids())));

drop policy if exists licenses_portal_select on licenses;
create policy licenses_portal_select on licenses
  for select to app_client_portal
  using (deleted_at is null and exists (
    select 1 from affiliations a
    where a.clinician_id = licenses.clinician_id
      and a.deleted_at is null
      and a.practice_id = any (app.portal_practice_ids())));

drop policy if exists registrations_portal_select on registrations;
create policy registrations_portal_select on registrations
  for select to app_client_portal
  using (deleted_at is null and exists (
    select 1 from affiliations a
    where a.clinician_id = registrations.clinician_id
      and a.deleted_at is null
      and a.practice_id = any (app.portal_practice_ids())));

-- enrollments carries practice_id directly: scope on it, not on the affiliation,
-- so one practice never sees a clinician's enrollment under another employer.
drop policy if exists enrollments_portal_select on enrollments;
create policy enrollments_portal_select on enrollments
  for select to app_client_portal
  using (deleted_at is null and practice_id = any (app.portal_practice_ids()));

drop policy if exists privileges_portal_select on privileges;
create policy privileges_portal_select on privileges
  for select to app_client_portal
  using (deleted_at is null and exists (
    select 1 from affiliations a
    where a.clinician_id = privileges.clinician_id
      and a.deleted_at is null
      and a.practice_id = any (app.portal_practice_ids())));

drop policy if exists ce_records_portal_select on ce_records;
create policy ce_records_portal_select on ce_records
  for select to app_client_portal
  using (deleted_at is null and exists (
    select 1 from affiliations a
    where a.clinician_id = ce_records.clinician_id
      and a.deleted_at is null
      and a.practice_id = any (app.portal_practice_ids())));

-- PRD 10, Client portal: "read-only calendar and standing report".
drop policy if exists obligations_portal_select on obligations;
create policy obligations_portal_select on obligations
  for select to app_client_portal
  using (deleted_at is null and practice_id = any (app.portal_practice_ids()));

-- =============================================================================
-- 5. OFFSHORE DELIVERY ASSOCIATE -- action queue only (PRD 12).
-- "Works the action queue. Never decides what is required; executes pre-filled
--  work." (PRD 3)
-- =============================================================================

-- Read the roster fields a pre-filled form needs, and the action queue itself.
grant select on
  practices, clinicians, affiliations,
  licenses, registrations, enrollments, privileges, ce_records, obligations
to app_delivery;

-- Move a queue item along. Column-level UPDATE: an associate may change the
-- work state and nothing else -- not the due date, not the severity, not the
-- cited evidence. There is no INSERT and no DELETE anywhere for this role.
grant update (status, completed_at) on obligations to app_delivery;

-- Deliberately NOT granted to app_delivery, at the privilege level, so the
-- error is "permission denied for table X" and not an empty result set:
--   evidence                             -- PRD 12: never the evidence store
--   requirements, requirement_conflicts  -- PRD 12: never the rules admin
--   exceptions                           -- the exception queue is QA-only (PRD 10)
--   sanctions                            -- exclusion and discipline hits are
--                                           HIGH_CONSEQUENCE, QA-only (PRD 8.3)
--   sources, source_runs                 -- engineering only (PRD 10)
-- PRD 12 also notes: "Several states restrict offshore handling of certain data
-- categories; scope access by state before scaling delivery." When that lands,
-- add a state predicate to the policies below -- do not widen the grants.

-- The action queue IS these two statuses. Nothing pending, auto_cleared,
-- exception, complete or waived is visible to this role.
drop policy if exists obligations_delivery_select on obligations;
create policy obligations_delivery_select on obligations
  for select to app_delivery
  using (deleted_at is null and status in ('queued','in_progress'));

-- An associate may pick work up and put it down, or hand it back. Promoting an
-- item to auto_cleared or waived is a judgement call and is not available here.
drop policy if exists obligations_delivery_update on obligations;
create policy obligations_delivery_update on obligations
  for update to app_delivery
  using (deleted_at is null and status in ('queued','in_progress'))
  with check (status in ('queued','in_progress','complete','exception'));

-- Roster visibility is limited to clinicians who actually have queued work, so
-- the role cannot enumerate the whole book of business.
drop policy if exists obligations_delivery_scope_practices on practices;
create policy obligations_delivery_scope_practices on practices
  for select to app_delivery
  using (deleted_at is null and exists (
    select 1 from obligations o
    where o.practice_id = practices.id
      and o.deleted_at is null
      and o.status in ('queued','in_progress')));

drop policy if exists clinicians_delivery_select on clinicians;
create policy clinicians_delivery_select on clinicians
  for select to app_delivery
  using (deleted_at is null and exists (
    select 1 from obligations o
    where o.clinician_id = clinicians.id
      and o.deleted_at is null
      and o.status in ('queued','in_progress')));

drop policy if exists affiliations_delivery_select on affiliations;
create policy affiliations_delivery_select on affiliations
  for select to app_delivery
  using (deleted_at is null and exists (
    select 1 from obligations o
    where o.clinician_id = affiliations.clinician_id
      and o.practice_id = affiliations.practice_id
      and o.deleted_at is null
      and o.status in ('queued','in_progress')));

drop policy if exists licenses_delivery_select on licenses;
create policy licenses_delivery_select on licenses
  for select to app_delivery
  using (deleted_at is null and exists (
    select 1 from obligations o
    where o.clinician_id = licenses.clinician_id
      and o.deleted_at is null
      and o.status in ('queued','in_progress')));

drop policy if exists registrations_delivery_select on registrations;
create policy registrations_delivery_select on registrations
  for select to app_delivery
  using (deleted_at is null and exists (
    select 1 from obligations o
    where o.clinician_id = registrations.clinician_id
      and o.deleted_at is null
      and o.status in ('queued','in_progress')));

drop policy if exists enrollments_delivery_select on enrollments;
create policy enrollments_delivery_select on enrollments
  for select to app_delivery
  using (deleted_at is null and exists (
    select 1 from obligations o
    where o.clinician_id = enrollments.clinician_id
      and o.practice_id = enrollments.practice_id
      and o.deleted_at is null
      and o.status in ('queued','in_progress')));

drop policy if exists privileges_delivery_select on privileges;
create policy privileges_delivery_select on privileges
  for select to app_delivery
  using (deleted_at is null and exists (
    select 1 from obligations o
    where o.clinician_id = privileges.clinician_id
      and o.deleted_at is null
      and o.status in ('queued','in_progress')));

drop policy if exists ce_records_delivery_select on ce_records;
create policy ce_records_delivery_select on ce_records
  for select to app_delivery
  using (deleted_at is null and exists (
    select 1 from obligations o
    where o.clinician_id = ce_records.clinician_id
      and o.deleted_at is null
      and o.status in ('queued','in_progress')));

-- =============================================================================
-- 6. DEFAULTS FOR FUTURE TABLES
-- A table added later without an explicit grant is unreachable by the two
-- restricted roles, which is the correct default. Internal keeps working.
-- =============================================================================
alter default privileges in schema public
  grant select, insert, update, delete on tables to app_internal;
