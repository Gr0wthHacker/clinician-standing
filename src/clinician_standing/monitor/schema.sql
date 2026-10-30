-- Clinician Standing Monitor (T620). SQLite, the same pattern as obligations_lite, so the move
-- to the numbered Postgres migrations is an import. Provider data only: NPI, name, state,
-- credential. No column holds a date of birth, an SSN or any patient data.
PRAGMA foreign_keys = ON;

create table if not exists monitor_rosters (
  roster_id      text primary key,
  org_name       text not null,
  alert_email    text,                        -- set by the client; never inferred
  status         text not null default 'active' check (status in ('active', 'paused', 'cancelled')),
  stripe_subscription_id text,
  created_at     text not null
);

create table if not exists monitor_roster_members (
  roster_id   text not null references monitor_rosters (roster_id),
  npi         text not null check (length(npi) = 10 and npi glob '[0-9]*'),
  name        text,
  state       text check (state is null or (length(state) = 2 and state = upper(state))),
  credential  text,
  added_at    text not null,
  removed_at  text,
  primary key (roster_id, npi)
);

-- The last standing read per NPI. The diff runs against this table, never against connector
-- state in a CI cache, so an evicted cache cannot fake a "new" alert.
create table if not exists monitor_snapshots (
  npi         text primary key,
  taken_at    text not null,
  hash        text not null,
  snapshot    text not null                   -- JSON, see snapshot.py
);

create table if not exists monitor_alerts (
  alert_id    text primary key,               -- hash of roster, npi, kind, detail
  roster_id   text not null references monitor_rosters (roster_id),
  npi         text,
  kind        text not null check (kind in (
                'exclusion_new', 'exclusion_reinstated', 'license_adverse', 'license_discipline',
                'license_expiring', 'npi_missing', 'npi_returned', 'source_stale')),
  delivery    text not null check (delivery in ('immediate', 'digest')),
  status      text not null default 'pending' check (status in ('held', 'pending', 'sent', 'acknowledged')),
  detail      text not null,                  -- JSON: before, after, message
  source_key  text,                           -- registry key of the evidence behind it
  source_as_of text,
  created_at  text not null,
  sent_at     text,
  acknowledged_at text,
  acknowledged_by text
);

create index if not exists monitor_alerts_roster on monitor_alerts (roster_id, created_at);

create table if not exists monitor_runs (
  run_id      integer primary key autoincrement,
  started_at  text not null,
  finished_at text,
  trigger     text not null,                  -- monthly_ingest | nursys | manual
  npis_read   integer not null default 0,
  alerts_written integer not null default 0
);
