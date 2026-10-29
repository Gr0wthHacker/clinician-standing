-- =============================================================================
-- 0018_leie_npi_candidates.sql -- possible NPI links for LEIE rows with no NPI,
-- and the NPPES weekly incremental source.
--
-- About 90% of OIG LEIE rows carry no NPI (oig_leie.py), so an NPI-only screen
-- cannot see most of the file. NPPES (0016) names every individual NPI with a
-- practice state and the license states the provider self-reported, which is
-- enough to propose candidates by name and state. It is not enough to assert an
-- exclusion: NPPES carries no date of birth, and two clinicians with the same
-- name in the same state are common.
--
-- So this table holds CANDIDATES, never exclusions:
--
--   * nothing here writes `sanctions`. Only an NPI match (match_confidence 1.0)
--     does, and that path is unchanged (oig_leie.py).
--   * match_confidence is bounded strictly below 1.0 by a CHECK. 1.0 is the
--     marker for an NPI match everywhere else in the schema (PRD 8.1), and a
--     name match must never be able to look like one.
--   * review_status starts at needs_review. The API reports a needs_review or
--     confirmed row as a possible match that needs human review, separate from
--     the exclusion matches, and never as an open exclusion.
--
-- Rows are keyed on (leie_key, npi). leie_key is the sha256 of the oig_leie
-- connector's identity key, so a rerun over the same LEIE row updates the same
-- candidate and keeps its review decision. A candidate the latest run no longer
-- produced (the LEIE row left the file, the NPPES name changed, a new same-name
-- clinician pushed the row over the ambiguity cap) is stamped superseded_at and
-- hidden from the API; its review history stays.
--
-- Public data only: LEIE and NPPES are both published files. No raw date of
-- birth is stored; the LEIE DOB never leaves oig_leie.parse().
--
-- Enum-like columns are text + named CHECK constraint; see header of 0001.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. app.name_key -- the surname blocking key, shared with Python.
--
-- leie_match.name_key() in Python must return exactly what this returns; a
-- unit test compares the literals below with the Python constants and a
-- database test compares outputs. Steps: fold the common Latin accents, upper-
-- case ASCII, turn every run of non-letters into one space, trim, drop trailing
-- generational suffixes, remove the spaces. "O'Brien", "OBRIEN" and "O BRIEN"
-- share a key; so do "Peña" and "PENA", and "Garcia-Lopez" and "GARCIA LOPEZ".
-- ---------------------------------------------------------------------------
create or replace function app.name_key(raw text)
returns text
language sql
immutable
parallel safe
as $$
  select nullif(
    replace(
      regexp_replace(
        btrim(
          regexp_replace(
            upper(translate(
              coalesce(raw, ''),
              'ÀÁÂÃÄÅàáâãäåÇçÈÉÊËèéêëÌÍÎÏìíîïÑñÒÓÔÕÖØòóôõöøÙÚÛÜùúûüÝýÿ',
              'AAAAAAaaaaaaCcEEEEeeeeIIIIiiiiNnOOOOOOooooooUUUUuuuuYyy'
            )),
            '[^A-Z]+', ' ', 'g'
          )
        ),
        '( (JR|SR|II|III|IV))+$', ''
      ),
      ' ', ''
    ),
    ''
  );
$$;

comment on function app.name_key(text) is
  'Surname blocking key for LEIE to NPPES candidate matching (0018). Matches leie_match.name_key in Python.';

grant usage on schema app to app_internal;
grant execute on function app.name_key(text) to app_internal;

-- The candidate query joins LEIE surnames to individual NPIs on this key. On a
-- full NPPES table (~8M individuals) the build takes a minute or two.
create index if not exists ix_nppes_providers_individual_name_key
  on nppes_providers (app.name_key(last_name))
  where entity_type = 1;

-- ---------------------------------------------------------------------------
-- 2. leie_npi_candidates
-- ---------------------------------------------------------------------------
create table if not exists leie_npi_candidates (
  id                     uuid primary key default gen_random_uuid(),
  leie_key               text not null,         -- sha256 hex of the oig_leie identity key
  npi                    text not null,
  -- The LEIE row as published, so a reviewer can compare without the file.
  leie_last_name         text not null,
  leie_first_name        text,
  leie_middle_name       text,
  leie_state             text not null,
  leie_general_category  text,
  leie_specialty         text,
  exclusion_type         text,
  exclusion_date         date,
  reinstatement_date     date,
  waiver_date            date,
  -- The NPPES side at match time.
  nppes_last_name        text,
  nppes_first_name       text,
  nppes_middle_name      text,
  nppes_practice_state   text,
  nppes_is_active        boolean,
  match_basis            text not null default 'name_state',
  -- {"first_name": "exact|prefix|initial", "middle_name": "agrees|unknown",
  --  "state": "practice|license|practice_and_license", "base_confidence": 0.85}
  match_detail           jsonb not null default '{}'::jsonb,
  match_confidence       numeric(4,3) not null,
  -- How many NPIs this LEIE row produced in the run. Confidence is divided by it.
  candidate_count        integer not null,
  review_status          text not null default 'needs_review',
  reviewed_by            text,
  reviewed_at            timestamptz,
  review_note            text,
  leie_evidence_id       uuid references evidence,
  first_seen_at          timestamptz not null default now(),
  last_seen_at           timestamptz not null default now(),
  superseded_at          timestamptz,
  created_at             timestamptz default now(),
  updated_at             timestamptz default now(),
  constraint leie_npi_candidates_pair_key unique (leie_key, npi),
  constraint leie_npi_candidates_npi_chk check (npi ~ '^[0-9]{10}$'),
  constraint leie_npi_candidates_basis_chk check (match_basis in ('name_state')),
  -- Strictly below 1.0: 1.0 means an NPI match (PRD 8.1). See header.
  constraint leie_npi_candidates_confidence_chk
    check (match_confidence > 0 and match_confidence < 1),
  constraint leie_npi_candidates_count_chk check (candidate_count >= 1),
  constraint leie_npi_candidates_review_chk
    check (review_status in ('needs_review', 'confirmed', 'rejected')),
  constraint leie_npi_candidates_reviewed_chk
    check (review_status = 'needs_review' or reviewed_at is not null)
);

comment on table leie_npi_candidates is
  'Possible NPI links for OIG LEIE rows that carry no NPI, proposed by name and state against NPPES (0018). Candidates only: never written to sanctions, confidence always below 1.0, surfaced by the API as needing human review.';
comment on column leie_npi_candidates.review_status is
  'needs_review until a person decides. confirmed still does not write sanctions; rejected hides the row from the API.';

create index if not exists ix_leie_npi_candidates_npi_live
  on leie_npi_candidates (npi) where superseded_at is null;

-- ---------------------------------------------------------------------------
-- 3. RLS -- internal only, same pattern as 0013, 0015 and 0016.
-- ---------------------------------------------------------------------------
do $$
begin
  alter table public.leie_npi_candidates enable row level security;
  revoke all on public.leie_npi_candidates from public;
  revoke all on public.leie_npi_candidates from app_internal, app_delivery, app_client_portal;
  grant select, insert, update, delete on public.leie_npi_candidates to app_internal;
  drop policy if exists leie_npi_candidates_internal_all on public.leie_npi_candidates;
  create policy leie_npi_candidates_internal_all on public.leie_npi_candidates
    for all to app_internal using (true) with check (true);
  alter table public.leie_npi_candidates force row level security;
end $$;

do $$
begin
  if exists (select 1 from pg_roles where rolname in ('anon', 'authenticated')) then
    execute 'revoke all on leie_npi_candidates from anon, authenticated';
    execute 'revoke all on function app.name_key(text) from anon, authenticated';
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- 4. Source registry: the NPPES weekly incremental.
--
-- Same authority as the monthly replicate it updates (0009/0010: primary,
-- attesting to directory_attestation). Inserted with both values in one tuple
-- so sources_primary_attests_chk holds, and never updated on conflict, so a
-- re-run cannot fight a later correction (CONTRIBUTING.md).
-- ---------------------------------------------------------------------------
insert into sources (
  key, display_name, kind, cadence, freshness_sla_days, is_primary_source,
  attests_obligation_types, auth_ref, terms_url, terms_reviewed_at, enabled
) values
('nppes_weekly', 'NPPES NPI Registry Weekly Incremental', 'bulk_file', 'weekly', 14, true,
 '{directory_attestation}', null, 'https://download.cms.gov/nppes/NPI_Files.html', null, true)
on conflict (key) do nothing;

-- ---------------------------------------------------------------------------
-- 5. SELF-CHECK.
-- ---------------------------------------------------------------------------
do $$
declare
  leaked text;
begin
  if not exists (
    select 1 from pg_class c join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public' and c.relname = 'leie_npi_candidates'
       and c.relrowsecurity and c.relforcerowsecurity
  ) then
    raise exception 'RLS is not enabled and forced on leie_npi_candidates';
  end if;

  select string_agg(g.rolname, ', ') into leaked
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  cross join lateral aclexplode(c.relacl) acl
  join pg_roles g on g.oid = acl.grantee
  where n.nspname = 'public'
    and c.relname = 'leie_npi_candidates'
    and g.rolname in ('app_delivery', 'app_client_portal');
  if leaked is not null then
    raise exception 'restricted role holds a grant on leie_npi_candidates: %', leaked;
  end if;

  if app.name_key('O''Brien Jr.') is distinct from 'OBRIEN'
     or app.name_key('Peña') is distinct from 'PENA'
     or app.name_key('  ') is not null then
    raise exception 'app.name_key does not normalize as documented';
  end if;
end $$;
