-- =============================================================================
-- 0002_core.sql -- PRD 5.1 core entities, plus `evidence` (PRD 5.4).
--
-- WHY `evidence` LIVES HERE AND NOT IN 0005:
--   PRD 5.2 declares `licenses.evidence_id uuid references evidence not null`
--   and the same on registrations / enrollments / sanctions. That is the
--   platform's central invariant (PRD 14, Phase 1 acceptance: "a credential row
--   cannot be inserted without a valid evidence_id"). Migrations must run
--   top-to-bottom with no forward references, so the referenced table has to be
--   created before 0003. The table definition is verbatim PRD 5.4.
--
-- Enum-like columns are text + named CHECK constraint; see header of 0001.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- practices -- client practices. `org_pac_id` is the universal join key.
-- ---------------------------------------------------------------------------
create table if not exists practices (
  id                uuid primary key default gen_random_uuid(),
  org_pac_id        text unique,                    -- CMS group PAC ID, the universal join key
  npi_org           text,                           -- Type 2 organizational NPI
  legal_name        text not null,
  dba_name          text,
  address_line1     text,
  address_line2     text,
  city              text,
  state             char(2),
  zip               text,
  phone             text,
  client_status     text,                           -- prospect | audit | active | churned
  tier              text,                           -- essential | standard | complete
  size_discount     numeric(4,3) default 0,         -- 0.00 / 0.05 / 0.10 / 0.15
  onboarded_at      timestamptz,
  created_at        timestamptz default now(),
  deleted_at        timestamptz,

  constraint practices_client_status_chk
    check (client_status is null or client_status in
           ('prospect','audit','active','churned')),
  constraint practices_tier_chk
    check (tier is null or tier in ('essential','standard','complete')),
  constraint practices_size_discount_chk
    check (size_discount is null or size_discount in (0, 0.05, 0.10, 0.15)),
  constraint practices_state_chk
    check (state is null or state ~ '^[A-Z]{2}$'),
  constraint practices_npi_org_chk
    check (npi_org is null or npi_org ~ '^[0-9]{10}$')
);

comment on table practices is
  'Client practices (PRD 5.1). org_pac_id joins the CMS revalidation and DAC bulk files.';
comment on column practices.org_pac_id is
  'CMS group PAC ID. Universal join key to the CMS Revalidation and DAC files (PRD 6.2).';
comment on column practices.tier is
  'Account tier. Feeds queue priority ordering (PRD 7, "then account tier").';

-- ---------------------------------------------------------------------------
-- clinicians -- individual clinicians.
-- ---------------------------------------------------------------------------
create table if not exists clinicians (
  id                uuid primary key default gen_random_uuid(),
  npi               text unique not null,
  ind_pac_id        text,
  ind_enrl_id       text,
  first_name        text,
  last_name         text,
  middle_name       text,
  suffix            text,
  credential        text,                           -- MD, DO, NP, PA, CRNA...
  clinician_type    text not null,                  -- physician | np | pa | crna | other
  primary_specialty text,
  dob_hash          text,                           -- sha256, for LEIE name+DOB matching only
  created_at        timestamptz default now(),
  deleted_at        timestamptz,

  constraint clinicians_clinician_type_chk
    check (clinician_type in ('physician','np','pa','crna','other')),
  constraint clinicians_npi_chk
    check (npi ~ '^[0-9]{10}$'),
  -- NO PHI. dob_hash is a sha256 hex digest, never a date of birth (PRD 2).
  constraint clinicians_dob_hash_chk
    check (dob_hash is null or dob_hash ~ '^[0-9a-f]{64}$')
);

comment on table clinicians is
  'Individual clinicians (PRD 5.1). Provider data only -- no PHI ever enters this system (PRD 2).';
comment on column clinicians.dob_hash is
  'sha256 hex digest, used solely for OIG LEIE name+DOB matching (PRD 6.2). Never store a raw DOB.';

-- ---------------------------------------------------------------------------
-- affiliations -- who works where. Drives the nightly engine loop (PRD 7).
-- ---------------------------------------------------------------------------
create table if not exists affiliations (
  id              uuid primary key default gen_random_uuid(),
  clinician_id    uuid references clinicians,
  practice_id     uuid references practices,
  start_date      date,
  end_date        date,
  employment_type text,                             -- employed | contracted | locum
  is_billing      boolean default true,             -- drives lapse severity
  created_at      timestamptz default now(),
  deleted_at      timestamptz,

  constraint affiliations_employment_type_chk
    check (employment_type is null or employment_type in
           ('employed','contracted','locum')),
  constraint affiliations_date_order_chk
    check (end_date is null or start_date is null or end_date >= start_date),
  unique (clinician_id, practice_id, start_date)
);

comment on table affiliations is
  'Clinician-to-practice affiliation (PRD 5.1). An affiliation with end_date null is "active" for the nightly engine (PRD 7).';
comment on column affiliations.is_billing is
  'True when the clinician bills under this practice. A lapse while is_billing is critical severity (PRD 7).';

-- ---------------------------------------------------------------------------
-- evidence -- PRD 5.4. The evidence plane. Every assertion cites a row here.
-- Connectors write evidence; the reconciler derives credentials from it (PRD 6).
-- ---------------------------------------------------------------------------
create table if not exists evidence (
  id                    uuid primary key default gen_random_uuid(),
  source_key            text not null,              -- registry key, see PRD section 6
  fetched_at            timestamptz not null,
  request_ref           text,                       -- URL or API call made
  payload_ref           text not null,              -- object storage path to the raw response
  payload_sha256        text not null,
  parsed                jsonb,                      -- normalized extraction
  match_keys            jsonb,                      -- which identity keys matched, and how
  freshness_expires_at  timestamptz not null,
  created_at            timestamptz default now(),
  deleted_at            timestamptz,

  constraint evidence_payload_sha256_chk
    check (payload_sha256 ~ '^[0-9a-f]{64}$'),
  -- freshness_expires_at = fetched_at + sources.freshness_sla_days (PRD 5.5, 8.1).
  constraint evidence_freshness_chk
    check (freshness_expires_at >= fetched_at)
);

comment on table evidence is
  'Evidence plane (PRD 5.4). Raw payloads retained 7 years (PRD 12). A FK from source_key to sources.key is added in 0006.';
comment on column evidence.freshness_expires_at is
  'fetched_at + sources.freshness_sla_days. Past this instant the assertion is stale and cannot auto-clear (PRD 8.1 condition 2).';
comment on column evidence.match_keys is
  'Which identity keys matched and how. Auto-clear requires a strong single match (PRD 8.1 condition 3).';
