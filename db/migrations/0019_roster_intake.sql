-- =============================================================================
-- 0019_roster_intake.sql -- clinicians handed to the roster by an outside system.
--
-- Numbered 0019 because 0016, 0017 and 0018 are taken on open branches.
--
-- WHAT THIS IS
-- -----------------------------------------------------------------------------
-- A placement system (first caller: PlaceRail) tells us a clinician was placed
-- with an employer, through `POST /v1/roster` on the standing API. That request
-- lands here, one row per (source_system, external_id), and nowhere else.
--
-- It is deliberately NOT written into `clinicians`, `affiliations` or
-- `licenses`:
--   * `clinicians.npi` is NOT NULL, and a placement may not know the NPI yet.
--   * `licenses.evidence_id` is NOT NULL (PRD 14). A license the placement
--     system reports is a claim, not evidence, and must never look like one.
-- Promoting an intake row onto the monitored roster (matching the NPI, linking
-- the practice) is a reviewed step that sets `review_status` and `clinician_id`.
--
-- NO PHI (PRD 2). Name, NPI, license state/type/number/expiry, employer name.
-- No date of birth, no contact details, no compensation. The API model rejects
-- any other field, and the payload is never logged.
--
-- WHO WRITES IT
-- -----------------------------------------------------------------------------
-- `app_roster_api`, a login role for the API's roster endpoint. It can read,
-- insert and update this one table and nothing else, so the API's read side
-- keeps its read-only role (`API_DATABASE_URL`) and the write credential
-- (`API_ROSTER_DATABASE_URL`) reaches only intake rows. Created with no
-- password; set one out of band as with app_ingest (0011).
-- =============================================================================

create table if not exists roster_intake (
  id                  uuid primary key default gen_random_uuid(),
  source_system       text not null,                -- placerail | ...
  external_id         text not null,                -- the caller's id, e.g. the placement id
  api_key_id          text not null,                -- short digest id of the key that last wrote it
  first_name          text,
  last_name           text not null,
  npi                 text,
  credential          text,                         -- MD, DO, NP, RN ... as the caller states it
  licenses            jsonb not null default '[]'::jsonb,
  states              text[] not null default '{}',
  employer_name       text not null,
  employer_org_pac_id text,
  employment_status   text not null default 'active',
  placed_on           date,
  payload_sha256      text not null,
  review_status       text not null default 'pending',
  clinician_id        uuid references clinicians,
  received_at         timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  deleted_at          timestamptz,

  constraint roster_intake_external_uq unique (source_system, external_id),
  constraint roster_intake_source_system_chk
    check (source_system ~ '^[a-z][a-z0-9_]{1,31}$'),
  constraint roster_intake_external_id_chk
    check (length(external_id) between 1 and 128),
  constraint roster_intake_npi_chk
    check (npi is null or npi ~ '^[0-9]{10}$'),
  constraint roster_intake_licenses_chk
    check (jsonb_typeof(licenses) = 'array' and jsonb_array_length(licenses) <= 50),
  constraint roster_intake_states_chk
    check (array_to_string(states, ',') ~ '^([A-Z]{2}(,[A-Z]{2})*)?$' and cardinality(states) <= 60),
  constraint roster_intake_org_pac_id_chk
    check (employer_org_pac_id is null or employer_org_pac_id ~ '^[0-9]{10}$'),
  constraint roster_intake_employment_status_chk
    check (employment_status in ('active', 'ended')),
  constraint roster_intake_review_status_chk
    check (review_status in ('pending', 'matched', 'rejected')),
  constraint roster_intake_payload_sha256_chk
    check (payload_sha256 ~ '^[0-9a-f]{64}$')
);

comment on table roster_intake is
  'Clinicians handed over by a placement system through POST /v1/roster. Claims, not evidence: promotion onto the monitored roster is a reviewed step. No PHI (PRD 2).';
comment on column roster_intake.licenses is
  'Array of {state, license_type, license_number, expires_on} as the caller reported them. Not verified; never copied into licenses without evidence.';
comment on column roster_intake.payload_sha256 is
  'Digest of the normalized submission. An identical resend leaves the row untouched.';

create index if not exists roster_intake_npi_idx
  on roster_intake (npi) where npi is not null and deleted_at is null;
create index if not exists roster_intake_review_idx
  on roster_intake (review_status, received_at) where deleted_at is null;

-- ---------------------------------------------------------------------------
-- The roster API login role.
-- ---------------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'app_roster_api') then
    create role app_roster_api
      login nosuperuser nobypassrls nocreatedb nocreaterole noreplication noinherit;
  else
    alter role app_roster_api
      login nosuperuser nobypassrls nocreatedb nocreaterole noreplication noinherit;
  end if;
end $$;

comment on role app_roster_api is
  'Login role for POST /v1/roster (API_ROSTER_DATABASE_URL). Select, insert and update on roster_intake only. No membership, no DDL, no BYPASSRLS.';

revoke create on schema public from app_roster_api;

-- ---------------------------------------------------------------------------
-- RLS, same two-gate model as 0008/0015.
-- ---------------------------------------------------------------------------
alter table public.roster_intake enable row level security;
revoke all on public.roster_intake from public;
revoke all on public.roster_intake from app_internal, app_delivery, app_client_portal, app_roster_api;
-- Supabase's bootstrap default privileges can hand a new table to anon and
-- authenticated; 0014 explains why it cannot undo that for future tables.
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    execute 'revoke all on public.roster_intake from anon';
  end if;
  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    execute 'revoke all on public.roster_intake from authenticated';
  end if;
end $$;

grant select, insert, update, delete on public.roster_intake to app_internal;
drop policy if exists roster_intake_internal_all on public.roster_intake;
create policy roster_intake_internal_all on public.roster_intake
  for all to app_internal using (true) with check (true);

-- The API needs select for `on conflict ... do update` and to return the id of
-- an unchanged row. It may not delete and may not touch review fields.
grant select on public.roster_intake to app_roster_api;
grant insert (source_system, external_id, api_key_id, first_name, last_name, npi, credential,
              licenses, states, employer_name, employer_org_pac_id, employment_status,
              placed_on, payload_sha256)
  on public.roster_intake to app_roster_api;
grant update (api_key_id, first_name, last_name, npi, credential, licenses, states,
              employer_name, employer_org_pac_id, employment_status, placed_on,
              payload_sha256, updated_at)
  on public.roster_intake to app_roster_api;
drop policy if exists roster_intake_api_select on public.roster_intake;
create policy roster_intake_api_select on public.roster_intake
  for select to app_roster_api using (deleted_at is null);
drop policy if exists roster_intake_api_insert on public.roster_intake;
create policy roster_intake_api_insert on public.roster_intake
  for insert to app_roster_api with check (review_status = 'pending' and clinician_id is null);
drop policy if exists roster_intake_api_update on public.roster_intake;
create policy roster_intake_api_update on public.roster_intake
  for update to app_roster_api using (deleted_at is null) with check (deleted_at is null);

alter table public.roster_intake force row level security;

-- ---------------------------------------------------------------------------
-- SELF-CHECK. The role must stay narrow: no superuser, no BYPASSRLS, no
-- membership in any app role, and no grant on any other table in public.
-- ---------------------------------------------------------------------------
do $$
declare
  bad text;
begin
  if exists (
    select 1 from pg_roles
    where rolname = 'app_roster_api' and (rolsuper or rolbypassrls or rolcreaterole or rolcreatedb)
  ) then
    raise exception 'app_roster_api carries an elevated attribute';
  end if;
  if exists (
    select 1 from pg_auth_members m join pg_roles r on r.oid = m.member
    where r.rolname = 'app_roster_api'
  ) then
    raise exception 'app_roster_api must not be a member of any role';
  end if;
  select string_agg(distinct c.relname, ', ') into bad
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  cross join lateral aclexplode(c.relacl) acl
  join pg_roles g on g.oid = acl.grantee
  where n.nspname = 'public' and g.rolname = 'app_roster_api' and c.relname <> 'roster_intake';
  if bad is not null then
    raise exception 'app_roster_api holds a grant outside roster_intake: %', bad;
  end if;
  if not exists (
    select 1 from pg_class
    where relname = 'roster_intake' and relrowsecurity and relforcerowsecurity
  ) then
    raise exception 'RLS is not enabled and forced on roster_intake';
  end if;
end $$;
