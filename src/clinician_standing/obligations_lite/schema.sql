-- Obligations engine phase 2 (Obligations Engine PRD, roadmap phase 2): the same tables as the
-- multi-tenant build, on SQLite, so moving to Postgres later is an import, not a rewrite.
-- Provider and practice data only. No table has a field for patient data, SSN or date of birth.
PRAGMA foreign_keys = ON;

-- ---- rules: what each board requires ---------------------------------------
create table if not exists rules (
  rule_key        text not null,              -- stable: JURISDICTION:PROFESSION:CREDENTIAL:TRIGGER
  version         integer not null check (version >= 1),
  jurisdiction    text not null check (length(jurisdiction) = 2 and jurisdiction = upper(jurisdiction)),
  profession      text not null check (profession in ('MD', 'DO', 'NP', 'PA')),
  credential_type text not null,              -- license, csr, dea, aprn_prescriptive, ...
  trigger         text not null check (trigger in ('renewal', 'initial')),
  lead_days       integer not null default 60 check (lead_days >= 0),
  service_price_cents  integer not null check (service_price_cents >= 0),
  government_fee_cents integer,               -- null = not published; never guessed
  cycle_months    integer,
  prerequisites   text,
  form            text,
  delegation_mechanism text,
  source_url      text not null check (source_url like 'http%'),
  last_verified   text not null,              -- YYYY-MM-DD
  verified_by     text not null,
  second_verifier text,                       -- R1: two-pass verification
  effective_date  text,
  change_source   text,
  primary key (rule_key, version)
);

create view if not exists current_rules as
select r.* from rules r
where r.version = (select max(version) from rules x where x.rule_key = r.rule_key);

-- ---- roster: who holds what, as the board says ------------------------------
create table if not exists orgs (
  org_id  text primary key,
  name    text not null,
  type    text not null default 'group' check (type in ('group', 'facility', 'platform')),
  brand   text not null default 'clinician-standing',
  tier    text,
  default_owner text
);

create table if not exists clinicians (
  clinician_id text primary key,
  npi          text unique check (npi is null or (length(npi) = 10 and npi glob '[0-9]*')),
  name         text not null,
  profession   text not null check (profession in ('MD', 'DO', 'NP', 'PA')),
  specialty    text
);

create table if not exists credentials_held (
  clinician_id      text not null references clinicians (clinician_id),
  jurisdiction      text not null,
  credential_type   text not null,
  number            text,
  status            text not null default 'active' check (status in ('active', 'inactive', 'expired', 'pending')),
  expiry_from_board text,                     -- the only expiry source; never computed
  board_read_at     text,
  primary key (clinician_id, jurisdiction, credential_type)
);

create table if not exists roster_memberships (
  org_id          text not null references orgs (org_id),
  clinician_id    text not null references clinicians (clinician_id),
  start_date      text not null,
  end_date        text,
  states_required text not null,              -- comma separated, e.g. 'TX,FL'
  primary key (org_id, clinician_id)
);

-- ---- derived: what is owed. Regenerated, never hand-edited ------------------
create table if not exists obligations (
  obligation_id   text primary key,           -- deterministic: hash of org, clinician, rule_key
  org_id          text not null references orgs (org_id),
  clinician_id    text not null references clinicians (clinician_id),
  rule_key        text not null,
  rule_version    integer not null,
  jurisdiction    text not null,
  credential_type text not null,
  trigger         text not null,
  due_date        text,                       -- null when the board expiry has not been read
  expires_on      text,
  price_cents     integer not null,
  government_fee_cents integer,
  owner           text not null,
  status          text not null default 'open' check (status in ('open', 'needs_board_read', 'filed', 'closed')),
  brand           text not null,
  source_url      text not null,
  last_verified   text not null,
  generated_at    text not null,
  foreign key (rule_key, rule_version) references rules (rule_key, version)
);

create table if not exists events (
  event_id   integer primary key autoincrement,
  type       text not null check (type in ('new_state', 'expiry_window', 'placement_close', 'rule_change')),
  payload    text not null,                   -- JSON
  emitted_at text not null,
  dedupe_key text not null unique
);

-- ---- write-back: what happened on each filing (T909) ------------------------
create table if not exists filings (
  filing_id              integer primary key autoincrement,
  obligation_id          text not null references obligations (obligation_id),
  rule_key               text not null,
  rule_version           integer not null,
  submitted_at           text not null,
  approved_at            text,
  actual_processing_days integer check (actual_processing_days is null or actual_processing_days >= 0),
  actual_fee_paid_cents  integer check (actual_fee_paid_cents is null or actual_fee_paid_cents >= 0),
  rule_was_correct       integer check (rule_was_correct is null or rule_was_correct in (0, 1)),
  blocker_encountered    text,
  rework_count           integer not null default 0 check (rework_count >= 0),
  closed_at              text,
  -- PRD R6: no filing closes without the first two write-back fields.
  constraint filings_close_needs_actuals check (
    closed_at is null or (actual_processing_days is not null and actual_fee_paid_cents is not null and rule_was_correct is not null)
  )
);

create table if not exists rule_review_tickets (
  ticket_id     integer primary key autoincrement,
  rule_key      text not null,
  rule_version  integer not null,
  filing_id     integer not null unique references filings (filing_id),
  note          text,
  opened_at     text not null,
  resolved_at   text
);

-- A filing that says the rule was wrong opens a rule-review ticket (PRD risks: rules decay).
create trigger if not exists filings_rule_wrong_ticket
after update of closed_at on filings
when new.closed_at is not null and new.rule_was_correct = 0
begin
  insert or ignore into rule_review_tickets (rule_key, rule_version, filing_id, note, opened_at)
  values (new.rule_key, new.rule_version, new.filing_id, new.blocker_encountered, new.closed_at);
end;
