-- =============================================================================
-- 0006_sources.sql -- PRD 5.5: source registry and run log.
--
-- sources.is_primary_source is load-bearing: PRD 8.1 condition 1 makes it the
-- first gate on auto-clear, and the auto-clear rate is "the single metric that
-- determines whether this business works" (PRD 1.1). Seed values are in 0009.
--
-- Enum-like columns are text + named CHECK constraint; see header of 0001.
-- =============================================================================

create table if not exists sources (
  key                text primary key,              -- cms_dac | oig_leie | cms_revalidation | nppes |
                                                    -- nursys | fsmb_pdc | npdb_cq | state_ca | state_tx ...
  display_name       text,
  kind               text,                          -- bulk_file | api | push | scrape | manual
  cadence            text,                          -- daily | weekly | monthly | on_demand | push
  freshness_sla_days int not null,                  -- how old an assertion may be before it goes stale
  is_primary_source  boolean not null,              -- false means it cannot alone clear an obligation
  auth_ref           text,                          -- secret manager key
  terms_url          text,
  terms_reviewed_at  date,
  enabled            boolean default true,
  created_at         timestamptz default now(),
  deleted_at         timestamptz,

  constraint sources_kind_chk
    check (kind is null or kind in ('bulk_file','api','push','scrape','manual')),
  constraint sources_cadence_chk
    check (cadence is null or cadence in
           ('daily','weekly','monthly','on_demand','push')),
  constraint sources_freshness_sla_days_chk
    check (freshness_sla_days > 0),
  constraint sources_key_chk
    check (key ~ '^[a-z][a-z0-9_]*$'),
  -- PRD 6.4 / 13: a scrape adapter must carry a terms review date, and the run
  -- fails closed when it is older than 180 days (TERMS_LAPSED, PRD 8.3). The
  -- age test is evaluated at run time -- now() is not immutable, so it cannot be
  -- a CHECK -- but the presence of the date can be, and is, required here.
  constraint sources_scrape_terms_chk
    check (kind is distinct from 'scrape' or terms_reviewed_at is not null)
);

comment on table sources is
  'Source registry (PRD 5.5, 6). One row per connector. A connector never writes a credential row directly; it writes evidence, and the reconciler derives credentials from it (PRD 6).';
comment on column sources.is_primary_source is
  'false means this source cannot alone clear an obligation (PRD 5.5, 8.1 condition 1). Federal bulk enrollment and directory files are derivative; FSMB, Nursys, NPDB and state boards are primary. Getting this flag wrong silently breaks the auto-clear rate.';
comment on column sources.freshness_sla_days is
  'evidence.freshness_expires_at = evidence.fetched_at + this many days. Past it, the assertion is not an assertion (PRD 11) and the obligation raises SOURCE_STALE (PRD 8.3).';
comment on column sources.terms_reviewed_at is
  'Re-review every 180 days. Older than 180 days fails the run closed with TERMS_LAPSED (PRD 6.4, 13).';
comment on column sources.auth_ref is
  'Secret MANAGER KEY only. Never a credential. Secrets never live in Lovable project files (PRD 12).';

-- ---------------------------------------------------------------------------
-- evidence.source_key -> sources.key
-- PRD 5.4 annotates the column "registry key, see section 6" but does not spell
-- the FK. Declaring it makes the reference real: an evidence row citing an
-- unregistered connector is unauditable, and PRD 8.1 has to read
-- sources.is_primary_source and freshness_sla_days through this key.
-- Added here (not in 0002) because sources must exist first. ON UPDATE CASCADE
-- so a registry key can be renamed without orphaning seven years of payloads.
-- ---------------------------------------------------------------------------
do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'evidence_source_key_fkey'
  ) then
    alter table evidence
      add constraint evidence_source_key_fkey
      foreign key (source_key) references sources (key)
      on update cascade on delete restrict;
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- source_runs -- one row per connector execution. Feeds the Source health
-- screen (PRD 10) and the freshness-compliance metric (PRD 11).
-- ---------------------------------------------------------------------------
create table if not exists source_runs (
  id           uuid primary key default gen_random_uuid(),
  source_key   text references sources,
  started_at   timestamptz,
  finished_at  timestamptz,
  status       text,                                -- ok | partial | failed
  rows_in      int,
  rows_changed int,
  rows_new     int,
  error        text,
  diff_ref     text,                                -- object storage path to the change set
  created_at   timestamptz default now(),
  deleted_at   timestamptz,

  constraint source_runs_status_chk
    check (status is null or status in ('ok','partial','failed')),
  constraint source_runs_finished_order_chk
    check (finished_at is null or started_at is null or finished_at >= started_at),
  constraint source_runs_rows_chk
    check (coalesce(rows_in, 0) >= 0
       and coalesce(rows_changed, 0) >= 0
       and coalesce(rows_new, 0) >= 0)
);

comment on table source_runs is
  'Connector run log (PRD 5.5). A failed run must raise SOURCE_STALE on dependent obligations rather than silently passing (PRD 12).';
comment on column source_runs.diff_ref is
  'Object storage path to the change set. Two consecutive runs must produce a diff, not a reload (PRD 14, Phase 2 acceptance).';
