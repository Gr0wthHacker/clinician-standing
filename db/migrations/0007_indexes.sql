-- =============================================================================
-- 0007_indexes.sql -- performance indexes.
--
-- Every index below names the query it exists for. Indexes that enforce
-- integrity rather than speed live with their tables:
--   * ux_requirements_current    (0004) -- one current rule version
--   * ux_obligations_open_duty   (0005) -- one open duty, and the engine's
--                                          ON CONFLICT target
--
-- Postgres indexes primary keys and UNIQUE constraints automatically but never
-- foreign keys, so every FK column is covered here unless an existing composite
-- index already has it as a leading column (noted where that applies).
--
-- Scale is small by design -- 465 clinicians, ~5,000 open obligations, ~50,000
-- evidence rows per month (PRD 12) -- so this set is deliberately modest.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- IDENTITY PLANE
-- ---------------------------------------------------------------------------

-- PRD 7, the outer loop of the nightly engine: "for each active affiliation
-- (clinician x practice)". Also the driving scan for the Roster screen (PRD 10)
-- and the practice-scoped EXISTS subquery in every client-portal RLS policy
-- (0008). The reverse direction (clinician_id, practice_id) is already the
-- leading prefix of the UNIQUE (clinician_id, practice_id, start_date)
-- constraint, so it is not repeated.
create index if not exists ix_affiliations_active_by_practice
  on affiliations (practice_id, clinician_id)
  where end_date is null and deleted_at is null;

-- PRD 7 priority ordering: "billing clinicians before non-billing", and PRD 7
-- severity: a lapse while is_billing is critical.
create index if not exists ix_affiliations_billing
  on affiliations (clinician_id)
  where is_billing and end_date is null and deleted_at is null;

-- PRD 10, Roster screen: clinician lookup by name. NPI is already unique.
create index if not exists ix_clinicians_last_name_trgm
  on clinicians using gin (last_name gin_trgm_ops);

-- PRD 9, the free roster audit: input is "practice name and NPI list, or just
-- org_pac_id". org_pac_id is already unique; name search needs this.
create index if not exists ix_practices_legal_name_trgm
  on practices using gin (legal_name gin_trgm_ops);

-- PRD 10, Roster / account views: active client practices only.
create index if not exists ix_practices_client_status
  on practices (client_status)
  where deleted_at is null;

-- ---------------------------------------------------------------------------
-- CREDENTIAL PLANE
-- ---------------------------------------------------------------------------

-- PRD 7: "for each state the clinician holds a license in". Also covers the
-- licenses.clinician_id FK as a leading prefix, and PRD 10 Clinician detail.
create index if not exists ix_licenses_clinician_state
  on licenses (clinician_id, state);

-- PRD 7 due-date computation for license_renewal: which active licences expire
-- next. Partial, because expired/revoked rows are not renewal candidates.
create index if not exists ix_licenses_expiry
  on licenses (expiry_date)
  where status = 'active' and deleted_at is null;

-- PRD 7: rules = requirements.current(state, clinician.license_type). Joining
-- the roster's licences to the rules plane, and reconciling a state bulk file
-- (PRD 6.3) against the licences it should match.
create index if not exists ix_licenses_state_type
  on licenses (state, license_type);

-- PRD 8.1 condition 3: identity matched on "license number plus state".
create index if not exists ix_licenses_number_state
  on licenses (license_number, state)
  where license_number is not null;

-- FK support: deleting/auditing an evidence row's dependants, and the
-- "evidence coverage 100%" metric (PRD 11).
create index if not exists ix_licenses_evidence
  on licenses (evidence_id);

-- PRD 7 due-date computation for dea_renewal and csr_renewal.
create index if not exists ix_registrations_clinician_kind
  on registrations (clinician_id, kind);
create index if not exists ix_registrations_expiry
  on registrations (expiry_date)
  where deleted_at is null;
create index if not exists ix_registrations_evidence
  on registrations (evidence_id);

-- PRD 7 medicare_revalidation / payer_revalidation, and PRD 9 item 2
-- ("Medicare enrollment reality ... with dates"): enrollment state per practice.
create index if not exists ix_enrollments_practice_status
  on enrollments (practice_id, status)
  where deleted_at is null;

-- PRD 7 severity: "revalidation past due" is critical. This is the scan that
-- finds them -- the same query that found 5,614 overdue practices (PRD 9).
create index if not exists ix_enrollments_revalidation_due
  on enrollments (revalidation_due)
  where status <> 'terminated' and deleted_at is null;

create index if not exists ix_enrollments_clinician_payer
  on enrollments (clinician_id, payer);
create index if not exists ix_enrollments_evidence
  on enrollments (evidence_id);

-- PRD 7 privilege_reappointment due-date computation, and PRD 10 Clinician detail.
create index if not exists ix_privileges_clinician_due
  on privileges (clinician_id, reappointment_due);
create index if not exists ix_privileges_evidence
  on privileges (evidence_id)
  where evidence_id is not null;

-- PRD 7 ce_cycle: hours accrued against the current cycle for a state, and
-- PRD 7 elevated severity: "CE cycle closing with a topic shortfall".
create index if not exists ix_ce_records_clinician_state_cycle
  on ce_records (clinician_id, state, cycle_end);
create index if not exists ix_ce_records_evidence
  on ce_records (evidence_id)
  where evidence_id is not null;

-- PRD 7 exclusion_screen and PRD 7 critical severity ("exclusion hit"): does
-- this clinician have a live sanction? Partial on not-yet-reinstated rows.
create index if not exists ix_sanctions_clinician_open
  on sanctions (clinician_id)
  where reinstated_date is null and deleted_at is null;

-- PRD 9 item 1 and PRD 6.2: SAM.gov disagreement with LEIE is an exception, not
-- a merge -- which means comparing the two sources for one clinician.
create index if not exists ix_sanctions_source_date
  on sanctions (source, action_date desc);

-- PRD 15.3: name+DOB matches below 1.0 confidence need human review before
-- anyone is told a named clinician is excluded.
create index if not exists ix_sanctions_low_confidence
  on sanctions (match_confidence)
  where match_confidence < 1.0;

create index if not exists ix_sanctions_evidence
  on sanctions (evidence_id);

-- ---------------------------------------------------------------------------
-- RULES PLANE
-- ---------------------------------------------------------------------------

-- PRD 8.1 condition 6: "No open requirement_conflicts row for that state,
-- license type and field." This is checked for every obligation on every
-- nightly run, so the open set must be cheap to probe.
create index if not exists ix_requirement_conflicts_open
  on requirement_conflicts (requirement_id)
  where (resolution is null or resolution = 'unresolved') and deleted_at is null;

-- PRD 10, Rules admin screen: version history for a rule.
create index if not exists ix_requirements_history
  on requirements (state, license_type, field_key, version desc);

-- ---------------------------------------------------------------------------
-- OBLIGATION PLANE
-- ---------------------------------------------------------------------------

-- PRD 10, Action queue ("today's work") and Exception queue; PRD 7 priority
-- ordering falls back to days-to-due ascending inside a status.
create index if not exists ix_obligations_status_due
  on obligations (status, due_date);

-- PRD 10, Roster / client portal: standing for one practice at a glance, and
-- the practice-scoped RLS predicate in 0008.
create index if not exists ix_obligations_practice_status
  on obligations (practice_id, status);

-- PRD 7 priority ordering, primary sort: severity, then days-to-due. Partial on
-- the open statuses because terminal rows are never queued.
create index if not exists ix_obligations_open_priority
  on obligations (severity, due_date)
  where status in ('pending','queued','in_progress','exception')
    and deleted_at is null;

-- PRD 10, Obligation calendar: "dated duties per clinician, next 12 months".
create index if not exists ix_obligations_practice_due
  on obligations (practice_id, due_date);
create index if not exists ix_obligations_clinician_due
  on obligations (clinician_id, due_date);

-- PRD 7: the window_opens scan -- which duties became actionable today.
create index if not exists ix_obligations_window_opens
  on obligations (window_opens)
  where status = 'pending' and deleted_at is null;

-- PRD 11, THE metric: auto-clear rate = auto_cleared / generated, by day.
-- "Instrument it from the first week."
create index if not exists ix_obligations_generated_at
  on obligations (generated_at, status);

-- PRD 7: re-evaluating duties whose generating rule version was superseded
-- (PRD 8.1 condition 5 fails for these).
create index if not exists ix_obligations_type_rule_version
  on obligations (obligation_type, rule_version);

create index if not exists ix_obligations_evidence
  on obligations (evidence_id)
  where evidence_id is not null;

-- ---------------------------------------------------------------------------
-- EVIDENCE PLANE
-- ---------------------------------------------------------------------------

-- PRD 8.1 conditions 1-2: find the latest assertion from a given source and
-- check it was fetched inside that source's freshness SLA. Descending, because
-- every read wants the newest row.
create index if not exists ix_evidence_source_fetched
  on evidence (source_key, fetched_at desc);

-- PRD 11, "Source freshness compliance >= 99%", and PRD 8.3 SOURCE_STALE:
-- which evidence has aged out of its SLA.
create index if not exists ix_evidence_freshness_expires
  on evidence (freshness_expires_at)
  where deleted_at is null;

-- PRD 6, connector contract: "fetch, checksum, diff against last run". PRD 14
-- Phase 2 acceptance: two consecutive runs produce a diff, not a reload.
create index if not exists ix_evidence_payload_sha256
  on evidence (payload_sha256);

-- PRD 8.1 condition 3: identity matched on a strong key, single match. The
-- matched keys are recorded in match_keys, so the reconciler probes them by
-- containment (e.g. match_keys @> '{"npi":"1234567890"}').
create index if not exists ix_evidence_match_keys
  on evidence using gin (match_keys jsonb_path_ops);

-- PRD 8.1 condition 4: "No conflicting assertion from any other source" --
-- comparing normalized extractions across sources for the same identity.
create index if not exists ix_evidence_parsed
  on evidence using gin (parsed jsonb_path_ops);

-- ---------------------------------------------------------------------------
-- EXCEPTIONS AND SOURCE HEALTH
-- ---------------------------------------------------------------------------

-- PRD 10, Exception queue "filtered by reason code"; PRD 11, "mean minutes to
-- resolve, by reason code". resolved_at second so open items sort together.
create index if not exists ix_exceptions_reason_resolved
  on exceptions (reason_code, resolved_at);

-- PRD 10, Exception queue for one QA specialist: my open items, oldest first.
create index if not exists ix_exceptions_assignee_open
  on exceptions (assigned_to, raised_at)
  where resolved_at is null and deleted_at is null;

-- FK support, and PRD 10 one-screen resolve: the exception(s) on an obligation.
create index if not exists ix_exceptions_obligation
  on exceptions (obligation_id);

-- PRD 10, Source health screen: "last run, rows changed, freshness compliance".
create index if not exists ix_source_runs_key_started
  on source_runs (source_key, started_at desc);

-- PRD 12 reliability: a failed connector run must raise SOURCE_STALE on
-- dependent obligations -- find the failures since the last check.
create index if not exists ix_source_runs_failed
  on source_runs (started_at desc)
  where status in ('failed','partial');
