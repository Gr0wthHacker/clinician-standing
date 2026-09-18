-- =============================================================================
-- 0005_obligations.sql -- PRD 5.4: obligations and exceptions.
-- `evidence` (also PRD 5.4) was created in 0002 because 0003 needs it; see the
-- note at the top of 0002_core.sql.
--
-- Enum-like columns are text + named CHECK constraint; see header of 0001.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- obligations -- the dated work queue. Everything delivery does comes out of
-- this table, and everything a client sees is rendered from it (PRD 1).
-- ---------------------------------------------------------------------------
create table if not exists obligations (
  id              uuid primary key default gen_random_uuid(),
  clinician_id    uuid references clinicians,
  practice_id     uuid references practices,
  obligation_type text not null,                    -- license_renewal | csr_renewal | dea_renewal |
                                                    -- medicare_revalidation | payer_revalidation |
                                                    -- ce_cycle | privilege_reappointment |
                                                    -- exclusion_screen | directory_attestation
  state           char(2),
  payer           text,
  due_date        date,
  window_opens    date,                             -- earliest actionable date
  severity        text not null,                    -- routine | elevated | critical
  status          text not null,                    -- pending | auto_cleared | queued | in_progress |
                                                    -- exception | complete | waived
  rule_version    int,                              -- which requirements version generated this
  generated_at    timestamptz not null,
  completed_at    timestamptz,
  evidence_id     uuid references evidence,
  created_at      timestamptz default now(),
  deleted_at      timestamptz,

  constraint obligations_obligation_type_chk
    check (obligation_type in (
      'license_renewal','csr_renewal','dea_renewal',
      'medicare_revalidation','payer_revalidation',
      'ce_cycle','privilege_reappointment',
      'exclusion_screen','directory_attestation')),
  constraint obligations_severity_chk
    check (severity in ('routine','elevated','critical')),
  constraint obligations_status_chk
    check (status in ('pending','auto_cleared','queued','in_progress',
                      'exception','complete','waived')),
  constraint obligations_state_chk
    check (state is null or state ~ '^[A-Z]{2}$'),
  constraint obligations_window_chk
    check (window_opens is null or due_date is null or window_opens <= due_date),
  constraint obligations_rule_version_chk
    check (rule_version is null or rule_version >= 1)
);

-- INTEGRITY, not performance. PRD 7: the nightly engine does
--   "upsert obligation(clinician, practice, type, state, due, rule_version)".
-- An upsert needs a conflict target. The identity of a duty is
--   (clinician, practice, type, state, payer)
-- and at most ONE of those may be open at a time -- two open license_renewal
-- rows for the same clinician in the same state is a duplicated queue item, and
-- the queue is the product. due_date is deliberately NOT in the key so that a
-- rule change moves the date on the existing row instead of forking a second
-- obligation. Terminal rows (auto_cleared / complete / waived) drop out of the
-- predicate, so next month's exclusion_screen inserts cleanly.
-- Engine usage:
--   insert into obligations (...) values (...)
--   on conflict (clinician_id, practice_id, obligation_type,
--                coalesce(state, ''), coalesce(payer, ''))
--   where status in ('pending','queued','in_progress','exception')
--         and deleted_at is null
--   do update set due_date = excluded.due_date, ...;
create unique index if not exists ux_obligations_open_duty
  on obligations (clinician_id, practice_id, obligation_type,
                  coalesce(state, ''), coalesce(payer, ''))
  where status in ('pending','queued','in_progress','exception')
    and deleted_at is null;

comment on table obligations is
  'Obligation plane (PRD 5.4). Priority ordering in the queue is severity, then days-to-due ascending, then billing clinicians first, then account tier (PRD 7).';
comment on column obligations.severity is
  'critical: exclusion hit, license expired/suspended while is_billing, enrollment terminated, revalidation past due. elevated: due inside 30 days, first-pass rejection, CE topic shortfall. routine: everything else (PRD 7). Only routine may auto-clear (PRD 8.1 condition 7).';
comment on column obligations.status is
  'auto_cleared rows are logged with their evidence and never shown to a person (PRD 8.1).';
comment on column obligations.rule_version is
  'requirements.version that generated this duty. Auto-clear requires that version to still be is_current (PRD 8.1 condition 5).';
comment on column obligations.evidence_id is
  'Nullable: an obligation exists before anything has been verified. It is populated when the obligation is cleared or completed.';

-- ---------------------------------------------------------------------------
-- exceptions -- the QA specialist's entire world (PRD 10).
-- ---------------------------------------------------------------------------
create table if not exists exceptions (
  id                 uuid primary key default gen_random_uuid(),
  obligation_id      uuid references obligations,
  reason_code        text not null,                 -- see PRD 8.3
  detail             text,
  raised_at          timestamptz not null,
  assigned_to        text,
  resolved_at        timestamptz,
  resolution         text,
  resolution_note    text,
  minutes_to_resolve int generated always as
    (extract(epoch from (resolved_at - raised_at))/60) stored,
  created_at         timestamptz default now(),
  deleted_at         timestamptz,

  constraint exceptions_reason_code_chk
    check (reason_code in (
      'IDENTITY_AMBIGUOUS',   -- zero or multiple matches on identity keys
      'SOURCE_CONFLICT',      -- two sources disagree on status or date
      'SOURCE_STALE',         -- no assertion inside the freshness SLA
      'RULE_UNCERTAIN',       -- open requirement_conflicts for this rule
      'HIGH_CONSEQUENCE',     -- exclusion hit, discipline, lapse while billing
      'PORTAL_REQUIRED',      -- needs a human inside a payer portal
      'DOCUMENT_REQUIRED',    -- needs something only the clinician can supply
      'TERMS_LAPSED')),       -- a scrape adapter's terms review is over 180 days old
  constraint exceptions_resolved_order_chk
    check (resolved_at is null or resolved_at >= raised_at)
);

comment on table exceptions is
  'Exception queue (PRD 8.3). Capacity ceiling is 80 exceptions per specialist per day (PRD 11).';
comment on column exceptions.minutes_to_resolve is
  'Generated, stored. Feeds "mean minutes to resolve, by reason code" (PRD 11) -- which tells you which code to engineer away next.';
comment on column exceptions.resolution is
  'Free text: the PRD does not enumerate resolutions. A RULE_UNCERTAIN resolution must also write back to requirement_conflicts and, where warranted, a new requirements version (PRD 8.3).';
