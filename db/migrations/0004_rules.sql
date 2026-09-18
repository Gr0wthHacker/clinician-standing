-- =============================================================================
-- 0004_rules.sql -- PRD 5.3, the rules plane.
--
-- "Every assertion the system makes is traceable to a source, a timestamp, and
--  a rule version." (PRD 1.2)  citation is NOT NULL for that reason.
--
-- Enum-like columns are text + named CHECK constraint; see header of 0001.
-- Integrity-bearing unique indexes live with their table; purely performance
-- indexes live in 0007.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- requirements -- what each state / license type demands, versioned.
-- ---------------------------------------------------------------------------
create table if not exists requirements (
  id            uuid primary key default gen_random_uuid(),
  state         char(2) not null,
  license_type  text not null,
  field_key     text not null,                      -- 38 keys: renewal_cycle_months, ce_hours_total,
                                                    -- ce_topic_opioid_hours, csr_required, csr_fee_cents,
                                                    -- supervision_ratio, fingerprint_required, ...
  value_text    text,
  value_num     numeric,
  value_bool    boolean,
  value_json    jsonb,
  citation      text not null,                      -- statute or board rule reference
  citation_url  text,
  effective_date date,
  verified_at   timestamptz not null,
  verified_by   text,
  version       int not null default 1,
  is_current    boolean default true,
  created_at    timestamptz default now(),
  deleted_at    timestamptz,

  constraint requirements_state_chk
    check (state ~ '^[A-Z]{2}$'),
  -- The PRD names 7 of 38 field_keys and does not publish the rest, so the key
  -- set is not enumerable here. Shape is constrained instead; the authoritative
  -- list belongs to the rules-plane author (PRD 15.5).
  constraint requirements_field_key_chk
    check (field_key ~ '^[a-z][a-z0-9_]*$'),
  -- A requirement that asserts nothing is not a requirement.
  constraint requirements_has_value_chk
    check (num_nonnulls(value_text, value_num, value_bool, value_json) >= 1),
  constraint requirements_version_chk
    check (version >= 1),
  -- Citation enforcement (PRD 10, Rules admin screen): a rule with no citation
  -- is not admissible. NOT NULL on the column, non-blank here.
  constraint requirements_citation_chk
    check (length(btrim(citation)) > 0),
  unique (state, license_type, field_key, version)
);

-- INTEGRITY, not performance: PRD 8.1 condition 5 requires "the rule version
-- used is is_current". That is only a decidable test if at most one version of a
-- given (state, license_type, field_key) is current at a time.
create unique index if not exists ux_requirements_current
  on requirements (state, license_type, field_key)
  where is_current and deleted_at is null;

comment on table requirements is
  'Rules plane (PRD 5.3). Versioned; superseding a rule means inserting version+1 and clearing is_current on the prior row.';
comment on column requirements.is_current is
  'Exactly one current row per (state, license_type, field_key), enforced by ux_requirements_current. Auto-clear requires the generating rule to be current (PRD 8.1 condition 5).';
comment on column requirements.version is
  'Copied onto obligations.rule_version so every dated duty is traceable to the rule text that produced it (PRD 1.2).';

-- ---------------------------------------------------------------------------
-- requirement_conflicts -- published rule vs observed board behaviour.
-- "This is the part a competitor cannot scrape and it only accrues through
--  delivery." (PRD 5.3)
-- ---------------------------------------------------------------------------
create table if not exists requirement_conflicts (
  id              uuid primary key default gen_random_uuid(),
  requirement_id  uuid references requirements,
  published_value text,
  observed_value  text,
  observed_at     timestamptz,
  observed_by     text,
  occurrences     int default 1,
  resolution      text,                             -- follow_published | follow_observed | unresolved
  notes           text,
  created_at      timestamptz default now(),
  deleted_at      timestamptz,

  constraint requirement_conflicts_resolution_chk
    check (resolution is null or resolution in
           ('follow_published','follow_observed','unresolved')),
  constraint requirement_conflicts_occurrences_chk
    check (occurrences is null or occurrences >= 1)
);

comment on table requirement_conflicts is
  'Divergence between published rule and observed board behaviour (PRD 5.3). An OPEN conflict is resolution IS NULL OR resolution = ''unresolved''; an open conflict blocks auto-clear (PRD 8.1 condition 6) and raises RULE_UNCERTAIN (PRD 8.3).';
comment on column requirement_conflicts.resolution is
  'NULL or ''unresolved'' means open. Resolving one is how the rules asset improves (PRD 8.3): it may also write a new requirements version.';
