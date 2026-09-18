-- =============================================================================
-- 0003_credentials.sql -- PRD 5.2 credential entities.
--
-- THE CENTRAL INVARIANT (PRD 5.2, PRD 11 "Evidence coverage: 100%",
-- PRD 14 Phase 1 acceptance):
--
--     "Each of these is an assertion that must carry evidence.
--      Never write one without an evidence_id."
--
-- This is enforced by the database, not by application code: on licenses,
-- registrations, enrollments and sanctions, `evidence_id` is NOT NULL and
-- carries a foreign key to evidence(id) with NO ACTION on delete, so:
--   * an INSERT without evidence_id fails (not-null violation);
--   * an INSERT citing a non-existent evidence row fails (FK violation);
--   * deleting an evidence row that a credential cites fails (FK violation) --
--     evidence is soft-deleted via evidence.deleted_at, never removed.
-- No application, no Lovable form and no ingest script can bypass it.
--
-- privileges and ce_records keep evidence_id NULLABLE, exactly as PRD 5.2
-- declares them. See the comments on those tables for why, and for what the
-- classifier must do with an evidence-less row.
--
-- Enum-like columns are text + named CHECK constraint; see header of 0001.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- licenses -- state professional licensure.
-- ---------------------------------------------------------------------------
create table if not exists licenses (
  id                uuid primary key default gen_random_uuid(),
  clinician_id      uuid references clinicians,
  state             char(2) not null,
  license_type      text not null,                  -- MD, DO, RN, APRN, PA...
  license_number    text,
  status            text not null,                  -- active | expired | lapsed | suspended | revoked | probation
  issue_date        date,
  expiry_date       date,
  is_compact        boolean default false,          -- IMLC / NLC privilege
  compact_home_state char(2),
  evidence_id       uuid not null references evidence,
  verified_at       timestamptz not null,
  created_at        timestamptz default now(),
  deleted_at        timestamptz,

  constraint licenses_status_chk
    check (status in ('active','expired','lapsed','suspended','revoked','probation')),
  constraint licenses_state_chk
    check (state ~ '^[A-Z]{2}$'),
  constraint licenses_compact_home_state_chk
    check (compact_home_state is null or compact_home_state ~ '^[A-Z]{2}$'),
  constraint licenses_date_order_chk
    check (expiry_date is null or issue_date is null or expiry_date >= issue_date),
  -- A compact privilege is a privilege to practise in `state` granted by a
  -- different home-state licence (IMLC / NLC). PRD 5.2.
  constraint licenses_compact_chk
    check (is_compact is not true or compact_home_state is not null),
  unique (clinician_id, state, license_type, license_number)
);

comment on table licenses is
  'State licensure assertions (PRD 5.2). evidence_id NOT NULL is the central invariant -- never write a credential row without evidence.';
comment on column licenses.verified_at is
  'When this assertion was last confirmed against its evidence. Compare with evidence.freshness_expires_at for SOURCE_STALE (PRD 8.3).';

-- ---------------------------------------------------------------------------
-- registrations -- DEA and state controlled substance registrations.
-- ---------------------------------------------------------------------------
create table if not exists registrations (
  id            uuid primary key default gen_random_uuid(),
  clinician_id  uuid references clinicians,
  kind          text not null,                      -- dea | state_csr
  state         char(2),                            -- null for DEA
  number        text,
  status        text,
  expiry_date   date,
  schedules     text[],
  evidence_id   uuid not null references evidence,
  verified_at   timestamptz not null,
  created_at    timestamptz default now(),
  deleted_at    timestamptz,

  constraint registrations_kind_chk
    check (kind in ('dea','state_csr')),
  -- PRD 5.2 annotates `state` as "null for DEA". A state CSR is by definition
  -- state-scoped, so the converse is required too.
  constraint registrations_kind_state_chk
    check ((kind = 'dea' and state is null)
        or (kind = 'state_csr' and state is not null)),
  constraint registrations_state_chk
    check (state is null or state ~ '^[A-Z]{2}$')
);

comment on table registrations is
  'DEA and state controlled-substance registrations (PRD 5.2). evidence_id NOT NULL -- central invariant.';
comment on column registrations.status is
  'Free text: the PRD does not enumerate registration statuses, so no CHECK constraint is applied here.';

-- ---------------------------------------------------------------------------
-- enrollments -- payer enrollment, per clinician per practice.
-- ---------------------------------------------------------------------------
create table if not exists enrollments (
  id                uuid primary key default gen_random_uuid(),
  clinician_id      uuid references clinicians,
  practice_id       uuid references practices,
  payer             text not null,                  -- medicare | medicaid_XX | uhc | aetna...
  status            text not null,                  -- approved | pending | rejected | revalidation_due | terminated
  effective_date    date,
  revalidation_due  date,
  par_status        text,                           -- par | non_par
  evidence_id       uuid not null references evidence,
  verified_at       timestamptz not null,
  created_at        timestamptz default now(),
  deleted_at        timestamptz,

  constraint enrollments_status_chk
    check (status in ('approved','pending','rejected','revalidation_due','terminated')),
  constraint enrollments_par_status_chk
    check (par_status is null or par_status in ('par','non_par'))
);

comment on table enrollments is
  'Payer enrollment assertions (PRD 5.2). evidence_id NOT NULL -- central invariant.';
comment on column enrollments.payer is
  'Free text by design: medicare | medicaid_XX (any state) | uhc | aetna | ... -- an open set, so no CHECK constraint.';
comment on column enrollments.revalidation_due is
  'Drives the medicare_revalidation obligation. Past due is critical severity (PRD 7).';

-- ---------------------------------------------------------------------------
-- privileges -- hospital / facility privileges. evidence_id NULLABLE.
-- ---------------------------------------------------------------------------
create table if not exists privileges (
  id                 uuid primary key default gen_random_uuid(),
  clinician_id       uuid references clinicians,
  facility_name      text,
  facility_npi       text,
  status             text,
  granted_date       date,
  reappointment_due  date,
  evidence_id        uuid references evidence,      -- NULLABLE, on purpose. See below.
  created_at         timestamptz default now(),
  deleted_at         timestamptz,

  constraint privileges_facility_npi_chk
    check (facility_npi is null or facility_npi ~ '^[0-9]{10}$'),
  constraint privileges_date_order_chk
    check (reappointment_due is null or granted_date is null
           or reappointment_due >= granted_date)
);

-- WHY NO NOT-NULL / CHECK ON privileges.evidence_id:
--   PRD 5.2 declares `evidence_id uuid references evidence` without `not null`,
--   and the reason is structural, not an oversight. There is no connector in the
--   PRD 6 registry that emits facility privileging data: every source in tiers
--   0-3 covers licensure, registration, enrollment or exclusion. Privileging is
--   supplied by the facility's medical staff office or by the clinician, i.e. it
--   arrives as a DOCUMENT_REQUIRED exception (PRD 8.3), and a client-supplied
--   document is not a primary source. Forcing an evidence row here would mean
--   fabricating evidence for a non-primary assertion, which is worse than a null.
--   CONTRACT FOR THE CLASSIFIER: a privileges row with evidence_id IS NULL can
--   never satisfy PRD 8.1 condition 1, so a privilege_reappointment obligation
--   resting on it must route to the queue, never auto-clear. Enforce that in the
--   classifier; the database only guarantees the null is visible.
--   Should a primary privileging feed ever be licensed, tighten this column to
--   NOT NULL in a later migration rather than relaxing the rule elsewhere.
comment on table privileges is
  'Facility privileges (PRD 5.2). evidence_id is deliberately nullable: no PRD 6 connector emits privileging data. See the migration comment above this table.';
comment on column privileges.evidence_id is
  'Nullable by design. NULL means no primary-source assertion exists, so the row can never auto-clear (PRD 8.1 condition 1).';

-- ---------------------------------------------------------------------------
-- ce_records -- continuing education. evidence_id NULLABLE.
-- ---------------------------------------------------------------------------
create table if not exists ce_records (
  id              uuid primary key default gen_random_uuid(),
  clinician_id    uuid references clinicians,
  state           char(2),
  cycle_start     date,
  cycle_end       date,
  topic           text,                             -- maps to requirements.ce_topic_mandates
  hours           numeric(5,2),
  completed_at    date,
  provider        text,
  certificate_ref text,
  evidence_id     uuid references evidence,         -- NULLABLE, on purpose. See below.
  created_at      timestamptz default now(),
  deleted_at      timestamptz,

  constraint ce_records_state_chk
    check (state is null or state ~ '^[A-Z]{2}$'),
  constraint ce_records_hours_chk
    check (hours is null or hours >= 0),
  constraint ce_records_cycle_order_chk
    check (cycle_end is null or cycle_start is null or cycle_end >= cycle_start)
);

-- WHY NO NOT-NULL / CHECK ON ce_records.evidence_id:
--   Same structural reason as privileges. CE completion is attested by the CE
--   provider's certificate (certificate_ref) or self-reported by the clinician
--   during onboarding; no PRD 6 connector publishes a per-clinician CE ledger.
--   A CE row therefore commonly exists before any primary-source confirmation.
--   CONTRACT FOR THE CLASSIFIER: a ce_cycle obligation whose supporting
--   ce_records all have evidence_id IS NULL fails PRD 8.1 condition 1 and must
--   route to the action queue (collect the certificate), never auto-clear.
--   A CE cycle closing with a topic shortfall is elevated severity (PRD 7).
comment on table ce_records is
  'Continuing education records (PRD 5.2). evidence_id is deliberately nullable: CE completion is attested, not primary-sourced. See the migration comment above this table.';
comment on column ce_records.topic is
  'Maps to a requirements.field_key such as ce_topic_opioid_hours (PRD 5.3).';
comment on column ce_records.evidence_id is
  'Nullable by design. NULL means the certificate has not been verified, so the row cannot auto-clear (PRD 8.1 condition 1).';

-- ---------------------------------------------------------------------------
-- sanctions -- exclusions and disciplinary actions.
-- ---------------------------------------------------------------------------
create table if not exists sanctions (
  id               uuid primary key default gen_random_uuid(),
  clinician_id     uuid references clinicians,
  source           text not null,                   -- leie | sam | npdb | state_board
  action_type      text,
  action_date      date,
  description      text,
  reinstated_date  date,
  match_confidence numeric(3,2),                    -- < 1.0 means name/DOB match, not NPI
  evidence_id      uuid not null references evidence,
  created_at       timestamptz default now(),
  deleted_at       timestamptz,

  constraint sanctions_source_chk
    check (source in ('leie','sam','npdb','state_board')),
  constraint sanctions_match_confidence_chk
    check (match_confidence is null
           or (match_confidence >= 0 and match_confidence <= 1)),
  constraint sanctions_date_order_chk
    check (reinstated_date is null or action_date is null
           or reinstated_date >= action_date)
);

comment on table sanctions is
  'Exclusion and disciplinary hits (PRD 5.2). evidence_id NOT NULL -- central invariant. A hit is HIGH_CONSEQUENCE (PRD 8.3) and critical severity (PRD 7).';
comment on column sanctions.match_confidence is
  'Below 1.0 the match was name+DOB, not NPI. Only 10% of LEIE rows carry an NPI (PRD 6.2, PRD 15.3). A false positive here is a serious accusation about a named clinician -- never auto-clear one.';
