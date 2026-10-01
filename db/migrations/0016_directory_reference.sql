-- =============================================================================
-- 0016_directory_reference.sql -- the public directory layer.
--
-- Three federal reference files that describe the whole U.S. clinician
-- population, not just client rosters:
--
--   nppes                     NPPES full replicate. Every NPI ever issued, with
--                             taxonomy, self-reported license numbers and
--                             states, practice address, authorized official,
--                             and deactivation status.
--   cms_hospitals             CMS Hospital General Information. Names the
--                             certification numbers (CCNs) that facility
--                             affiliations point at.
--   cms_facility_affiliation  CMS Facility Affiliation Data. Which clinician is
--                             affiliated with which hospital, nursing home,
--                             home health agency, hospice, IRF, LTCH or
--                             dialysis facility, by CCN.
--
-- Plus two DAC columns the cms_dac connector used to drop: medical school and
-- graduation year (and the secondary specialties string).
--
-- WHY THESE ARE REFERENCE TABLES AND NOT ROSTER TABLES
-- -----------------------------------------------------------------------------
-- `affiliations` drives the nightly obligations engine: an open row on a
-- billing clinician generates obligations at critical severity. A hospital
-- affiliation in a CMS directory file is not a billing relationship with a
-- client practice and must never generate one. So the facility affiliations
-- land in their own table, keyed on NPI and CCN, joined to the roster at read
-- time through `clinician_directory`. Same rule for NPPES: it is a directory,
-- not the roster, so it lives beside `clinicians` rather than writing into it.
--
-- None of these tables has a foreign key to `clinicians` or to `facilities`.
-- The source files describe populations wider than either (NPPES has ~9M NPIs
-- against ~2M DAC clinicians; affiliations point at nursing homes and dialysis
-- facilities that `facilities` does not name), and a reference load must not
-- fail because the roster is narrower than the directory.
--
-- PROVIDER DATA ONLY. Nothing here identifies a patient. NPPES publishes an
-- EIN column and a parent-organization TIN; neither is loaded, because a sole
-- proprietor's TIN can be an SSN and nothing in this product needs either.
--
-- Enum-like columns are text + named CHECK constraint; see header of 0001.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. clinicians -- the DAC columns that were being dropped on the floor.
--
-- Owned by ingest (cms_dac), never by the UI (CONTRIBUTING.md).
-- ---------------------------------------------------------------------------
alter table clinicians add column if not exists medical_school text;
alter table clinicians add column if not exists graduation_year smallint;
alter table clinicians add column if not exists secondary_specialties text;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'clinicians_graduation_year_chk') then
    alter table clinicians add constraint clinicians_graduation_year_chk
      check (graduation_year is null or graduation_year between 1900 and 2100);
  end if;
end $$;

comment on column clinicians.medical_school is
  'CMS DAC Med_sch, as published (often "OTHER"). Directory data, not a verified credential.';
comment on column clinicians.graduation_year is
  'CMS DAC Grd_yr. Directory data, not a verified credential.';
comment on column clinicians.secondary_specialties is
  'CMS DAC sec_spec_all, the published string unparsed. Directory data.';

-- ---------------------------------------------------------------------------
-- 2. nppes_providers -- one row per NPI in the NPPES full replicate.
-- ---------------------------------------------------------------------------
create table if not exists nppes_providers (
  npi                          text primary key,
  entity_type                  smallint,             -- 1 individual | 2 organization | null when deactivated
  replacement_npi              text,
  organization_name            text,                 -- Provider Organization Name (Legal Business Name)
  other_organization_name      text,
  last_name                    text,
  first_name                   text,
  middle_name                  text,
  name_prefix                  text,
  name_suffix                  text,
  credential                   text,                 -- free text, self-reported: "M.D.", "MD, PHD" ...
  practice_address_line1       text,
  practice_address_line2       text,
  practice_city                text,
  practice_state               text,                 -- not char(2): foreign addresses carry other values
  practice_postal_code         text,
  practice_country_code        text,
  practice_phone               text,
  enumeration_date             date,
  last_update_date             date,
  certification_date           date,
  deactivation_reason_code     text,
  deactivation_date            date,
  reactivation_date            date,
  is_sole_proprietor           boolean,
  is_organization_subpart      boolean,
  parent_organization_lbn      text,
  authorized_official_last_name   text,
  authorized_official_first_name  text,
  authorized_official_middle_name text,
  authorized_official_title       text,
  authorized_official_phone       text,
  primary_taxonomy_code        text,
  -- [{"slot": 1, "code": "2084N0400X", "license_number": "...", "license_state": "NY",
  --   "primary": true, "group": "..."}], slot order. Self-reported by the provider.
  taxonomies                   jsonb not null default '[]'::jsonb,
  is_active                    boolean generated always as (
                                 deactivation_date is null
                                 or (reactivation_date is not null
                                     and reactivation_date >= deactivation_date)
                               ) stored,
  -- Set when an NPI stops appearing in the replicate; cleared when it returns.
  -- NPPES does not delete NPIs, so this should stay empty. If it fills up, the
  -- file changed shape, which is worth knowing.
  absent_since                 date,
  evidence_id                  uuid references evidence,
  created_at                   timestamptz default now(),
  updated_at                   timestamptz default now(),

  constraint nppes_providers_npi_chk
    check (npi ~ '^[0-9]{10}$'),
  constraint nppes_providers_entity_type_chk
    check (entity_type is null or entity_type in (1, 2)),
  constraint nppes_providers_replacement_npi_chk
    check (replacement_npi is null or replacement_npi ~ '^[0-9]{10}$'),
  constraint nppes_providers_taxonomies_chk
    check (jsonb_typeof(taxonomies) = 'array')
);

comment on table nppes_providers is
  'NPPES full replicate, one row per NPI (0016). A directory, not the roster: join to clinicians on npi. Self-reported by providers; license numbers and states here are not verified.';
comment on column nppes_providers.taxonomies is
  'Up to 15 taxonomy slots as published, with the self-reported license number and state per slot. The NPPES license state is the "self-reported and unreliable" field the roster audit compares against.';
comment on column nppes_providers.is_active is
  'False when NPPES lists a deactivation with no later reactivation. A deactivated NPI on a billing roster is a finding.';

create index if not exists ix_nppes_providers_primary_taxonomy
  on nppes_providers (primary_taxonomy_code);
create index if not exists ix_nppes_providers_practice_state
  on nppes_providers (practice_state);
create index if not exists ix_nppes_providers_org_name_trgm
  on nppes_providers using gin (organization_name gin_trgm_ops)
  where entity_type = 2;
create index if not exists ix_nppes_providers_taxonomies
  on nppes_providers using gin (taxonomies jsonb_path_ops);
create index if not exists ix_nppes_providers_inactive
  on nppes_providers (npi) where not is_active;

-- ---------------------------------------------------------------------------
-- 3. facilities -- named facilities by CMS Certification Number.
--
-- Today only hospitals (Hospital General Information). Other facility types
-- named by future connectors write here under their own source_key.
-- ---------------------------------------------------------------------------
create table if not exists facilities (
  ccn                  text primary key,
  name                 text not null,
  address_line1        text,
  city                 text,
  state                char(2),
  zip                  text,
  county               text,
  phone                text,
  facility_type        text,                         -- as published, e.g. "Acute Care Hospitals"
  ownership            text,                         -- as published, e.g. "Voluntary non-profit - Private"
  emergency_services   boolean,
  overall_rating       smallint,                     -- CMS star rating; null when "Not Available"
  source_key           text not null references sources (key) on update cascade,
  absent_since         date,
  evidence_id          uuid references evidence,
  created_at           timestamptz default now(),
  updated_at           timestamptz default now(),

  constraint facilities_ccn_chk
    check (ccn ~ '^[0-9A-Z]{6}$'),
  constraint facilities_state_chk
    check (state is null or state ~ '^[A-Z]{2}$'),
  constraint facilities_overall_rating_chk
    check (overall_rating is null or overall_rating between 1 and 5)
);

comment on table facilities is
  'Facilities named by CMS Certification Number (0016). Reference data; a CCN in clinician_facility_affiliations may have no row here (non-hospital types are not yet named).';

create index if not exists ix_facilities_state on facilities (state);
create index if not exists ix_facilities_name_trgm on facilities using gin (name gin_trgm_ops);

-- ---------------------------------------------------------------------------
-- 4. clinician_facility_affiliations -- NPI x facility, from CMS.
--
-- Same open/close semantics as `affiliations` under cms_dac: a row is open
-- while the pair is in the current file, and closed (end_date = run date) when
-- the pair leaves the file while the clinician is still in it. A clinician who
-- leaves the file entirely keeps their rows open; absence of a clinician is
-- ambiguous. A pair that returns after being closed gets a new open row, so the
-- history survives.
-- ---------------------------------------------------------------------------
create table if not exists clinician_facility_affiliations (
  id              uuid primary key default gen_random_uuid(),
  npi             text not null,
  ind_pac_id      text,
  facility_type   text not null,                     -- as published: "Hospital", "Hospice", "Dialysis facility" ...
  ccn             text not null,                     -- Facility Affiliations Certification Number
  parent_ccn      text,                              -- Facility Type Certification Number: the hospital a unit sits in
  first_seen      date not null default current_date,
  last_seen       date not null default current_date,
  end_date        date,
  evidence_id     uuid references evidence,
  created_at      timestamptz default now(),

  constraint cfa_npi_chk
    check (npi ~ '^[0-9]{10}$'),
  constraint cfa_ccn_chk
    check (ccn ~ '^[0-9A-Z]{6}$'),
  constraint cfa_parent_ccn_chk
    check (parent_ccn is null or parent_ccn ~ '^[0-9A-Z]{6}$'),
  constraint cfa_facility_type_chk
    check (length(btrim(facility_type)) > 0),
  constraint cfa_date_order_chk
    check (last_seen >= first_seen and (end_date is null or end_date >= first_seen))
);

comment on table clinician_facility_affiliations is
  'CMS Facility Affiliation Data (0016). Directory data: a hospital privilege or facility link as CMS publishes it. Never drives obligations; the roster table for that is affiliations.';

-- One open row per pair. coalesce because a null parent_ccn is the common case
-- and nulls never collide in a plain unique index.
create unique index if not exists ux_cfa_open_pair
  on clinician_facility_affiliations (npi, facility_type, ccn, coalesce(parent_ccn, ''))
  where end_date is null;
create index if not exists ix_cfa_npi on clinician_facility_affiliations (npi);
create index if not exists ix_cfa_ccn on clinician_facility_affiliations (ccn) where end_date is null;

-- ---------------------------------------------------------------------------
-- 5. RLS -- internal only, same pattern as 0013 and 0015.
--
-- Neither the offshore delivery role nor the client portal needs the national
-- directory; the portal sees its own roster through clinician_directory only
-- if a later migration decides it should.
-- ---------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array['nppes_providers','facilities','clinician_facility_affiliations']
  loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from public', t);
    execute format('revoke all on public.%I from app_internal, app_delivery, app_client_portal', t);
    execute format('grant select, insert, update, delete on public.%I to app_internal', t);
    execute format('drop policy if exists %I on public.%I', t || '_internal_all', t);
    execute format(
      'create policy %I on public.%I for all to app_internal using (true) with check (true)',
      t || '_internal_all', t);
    execute format('alter table public.%I force row level security', t);
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- 6. clinician_directory -- the roster joined to the directory layer.
--
-- One row per clinician. What the free roster audit and Whitecoat's school
-- analysis read: NPPES status, primary taxonomy, the license states the
-- clinician self-reported to NPPES, school and year, and every open facility
-- affiliation with the facility name where CMS publishes one.
--
-- security_invoker, like enrollments_current (0012): the caller's RLS applies.
-- ---------------------------------------------------------------------------
drop view if exists clinician_directory;
create view clinician_directory
  with (security_invoker = true)
as
select
  c.id                                    as clinician_id,
  c.npi,
  c.first_name,
  c.last_name,
  c.credential,
  c.clinician_type,
  c.primary_specialty,
  c.secondary_specialties,
  c.medical_school,
  c.graduation_year,
  (n.npi is not null)                     as in_nppes,
  n.is_active                             as nppes_active,
  n.deactivation_date                     as nppes_deactivation_date,
  n.primary_taxonomy_code,
  n.last_update_date                      as nppes_last_update_date,
  coalesce(
    (select array_agg(distinct t ->> 'license_state' order by t ->> 'license_state')
       from jsonb_array_elements(n.taxonomies) t
      where coalesce(t ->> 'license_state', '') <> ''),
    '{}'::text[]
  )                                       as nppes_license_states,
  coalesce(
    (select jsonb_agg(
              jsonb_build_object(
                'facility_type', a.facility_type,
                'ccn',           a.ccn,
                'parent_ccn',    a.parent_ccn,
                'name',          f.name,
                'state',         f.state)
              order by a.facility_type, a.ccn)
       from clinician_facility_affiliations a
       left join facilities f on f.ccn = coalesce(a.parent_ccn, a.ccn)
      where a.npi = c.npi and a.end_date is null),
    '[]'::jsonb
  )                                       as facility_affiliations
from clinicians c
left join nppes_providers n on n.npi = c.npi
where c.deleted_at is null;

comment on view clinician_directory is
  'Roster joined to the directory layer (0016): NPPES status and self-reported license states, DAC school and year, open CMS facility affiliations with names. security_invoker, so RLS on the underlying tables applies.';

revoke all on clinician_directory from public;
grant select on clinician_directory to app_internal;

-- Supabase's anon/authenticated (0014). Default privileges set there cover
-- objects this role creates, but Supabase's own bootstrap defaults may not be
-- this role's, so revoke explicitly. Guarded for plain Postgres.
do $$
begin
  if exists (select 1 from pg_roles where rolname in ('anon', 'authenticated')) then
    execute 'revoke all on nppes_providers, facilities, clinician_facility_affiliations, '
            'clinician_directory from anon, authenticated';
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- 7. Source registry.
--
-- nppes is already seeded (0009) and paired with directory_attestation (0010);
-- it is built now, so it is enabled. `enabled` is build status, not permission
-- (0009 header).
--
-- The two new CMS files are directories that describe, never adjudicate: not
-- primary, attesting to nothing, exactly like cms_dac. Inserted false/empty and
-- never updated on conflict, so a re-run cannot fight a later correction (the
-- 0009/0010 lesson in CONTRIBUTING.md).
-- ---------------------------------------------------------------------------
update sources set enabled = true where key = 'nppes' and enabled is distinct from true;

insert into sources (
  key, display_name, kind, cadence, freshness_sla_days, is_primary_source,
  auth_ref, terms_url, terms_reviewed_at, enabled
) values
('cms_hospitals', 'CMS Hospital General Information', 'bulk_file', 'monthly', 45, false,
 null, 'https://data.cms.gov/provider-data/terms-of-service', null, true),
('cms_facility_affiliation', 'CMS Facility Affiliation Data', 'bulk_file', 'monthly', 45, false,
 null, 'https://data.cms.gov/provider-data/terms-of-service', null, true)
on conflict (key) do nothing;

-- ---------------------------------------------------------------------------
-- 8. SELF-CHECK.
-- ---------------------------------------------------------------------------
do $$
declare
  unforced text;
  leaked   text;
begin
  select string_agg(c.relname, ', ' order by c.relname) into unforced
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public'
    and c.relkind = 'r'
    and c.relname in ('nppes_providers','facilities','clinician_facility_affiliations')
    and not (c.relrowsecurity and c.relforcerowsecurity);
  if unforced is not null then
    raise exception 'RLS is not enabled and forced on: %', unforced;
  end if;

  select string_agg(format('%s->%s', g.rolname, c.relname), ', ') into leaked
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  cross join lateral aclexplode(c.relacl) acl
  join pg_roles g on g.oid = acl.grantee
  where n.nspname = 'public'
    and c.relname in ('nppes_providers','facilities','clinician_facility_affiliations',
                      'clinician_directory')
    and g.rolname in ('app_delivery','app_client_portal');
  if leaked is not null then
    raise exception 'restricted role holds a grant it must not: %', leaked;
  end if;

  if not exists (
    select 1 from pg_class c join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public' and c.relname = 'clinician_directory'
       and c.reloptions @> array['security_invoker=true']
  ) then
    raise exception 'clinician_directory must be created with security_invoker = true';
  end if;
end $$;
