-- =============================================================================
-- 0016_crm.sql -- the CRM / sales plane (BUILD_PLAN WP1.4).
--
-- `practices` and `clinicians` are the DAC-derived roster (who exists in the
-- Medicare data). This layer is the CRM: the organizations we sell to across
-- every brand, the people we talk to, the deals, the activity log, and the
-- suppression list. An organization links to a practice by CMS org PAC ID where
-- one exists, but it can also be a prospect or a facility that has no practice
-- row yet, so the link is nullable.
--
-- DEDUPE IS ENFORCED BY THE DATABASE (WP1.4 acceptance):
--   * same PAC ID  = same organization  -> unique(org_pac_id)
--   * same email    = same contact       -> unique(lower(email))
--   * a fuzzy name+address match is NEVER auto-merged; it goes to
--     org_review_queue for a human.
-- Loading the same prospects twice therefore creates no duplicates.
--
-- Enum-like columns are text + named CHECK; see header of 0001.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- organizations -- the CRM entity. One per real-world org we sell to.
-- ---------------------------------------------------------------------------
create table if not exists organizations (
  id            uuid primary key default gen_random_uuid(),
  org_pac_id    text,                               -- CMS group PAC ID; links to practices.org_pac_id
  internal_ref  text,                               -- stable key for an org with no PAC ID
  legal_name    text not null,
  dba_name      text,
  website       text,
  segment       text,                               -- practice | facility | agency | other
  created_at    timestamptz default now(),
  deleted_at    timestamptz,

  constraint organizations_segment_chk
    check (segment is null or segment in ('practice', 'facility', 'agency', 'other')),
  -- Same PAC ID is the same organization. Partial so many rows may have a null
  -- PAC ID (prospects without one) without colliding.
  constraint organizations_org_pac_id_key unique (org_pac_id)
);

comment on table organizations is
  'CRM organizations across all brands (BUILD_PLAN WP1.4). Links to practices by org_pac_id where one exists; deals, contacts and activities hang off this.';

create index if not exists ix_organizations_internal_ref
  on organizations (internal_ref) where deleted_at is null;

-- ---------------------------------------------------------------------------
-- org_locations -- addresses for an organization.
-- ---------------------------------------------------------------------------
create table if not exists org_locations (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations on delete cascade,
  address_line1   text,
  address_line2   text,
  city            text,
  state           char(2),
  zip             text,
  phone           text,
  is_primary      boolean default false,
  created_at      timestamptz default now(),
  deleted_at      timestamptz,

  constraint org_locations_state_chk
    check (state is null or state ~ '^[A-Z]{2}$')
);

-- ---------------------------------------------------------------------------
-- contacts -- the people. Deduped on email.
-- ---------------------------------------------------------------------------
create table if not exists contacts (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid references organizations on delete cascade,
  email           text,
  first_name      text,
  last_name       text,
  phone           text,
  title           text,
  source          text,                             -- enrichment | inbound | referral | manual
  confidence      numeric(3,2),                     -- 0..1, from the enrichment vendor
  created_at      timestamptz default now(),
  deleted_at      timestamptz,

  constraint contacts_confidence_chk
    check (confidence is null or (confidence >= 0 and confidence <= 1))
);

-- Same email is the same contact (case-insensitive). A null email (a contact we
-- know by name only) does not collide.
create unique index if not exists ux_contacts_email
  on contacts (lower(email)) where email is not null and deleted_at is null;

-- ---------------------------------------------------------------------------
-- contact_roles -- a contact's role at an organization, and whether they decide.
-- ---------------------------------------------------------------------------
create table if not exists contact_roles (
  id                uuid primary key default gen_random_uuid(),
  contact_id        uuid not null references contacts on delete cascade,
  role              text not null,                  -- practice_manager | administrator | owner_physician | billing | other
  is_decision_maker boolean default false,
  created_at        timestamptz default now(),
  deleted_at        timestamptz,

  constraint contact_roles_role_chk
    check (role in ('practice_manager', 'administrator', 'owner_physician', 'billing', 'other')),
  unique (contact_id, role)
);

-- ---------------------------------------------------------------------------
-- deals -- a sales opportunity, one per (organization, brand, product).
-- ---------------------------------------------------------------------------
create table if not exists deals (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations on delete cascade,
  brand           text not null,
  product_code    text,
  stage           text not null default 'prospect', -- prospect | audit_delivered | quoted | won | lost
  value_cents     integer,
  source          text,
  owner           text,
  created_at      timestamptz default now(),
  closed_at       timestamptz,
  deleted_at      timestamptz,

  constraint deals_stage_chk
    check (stage in ('prospect', 'audit_delivered', 'quoted', 'won', 'lost')),
  constraint deals_value_chk
    check (value_cents is null or value_cents >= 0)
);

create index if not exists ix_deals_org on deals (organization_id) where deleted_at is null;

-- ---------------------------------------------------------------------------
-- activities -- the interaction log: email, reply, meeting, call, note.
-- ---------------------------------------------------------------------------
create table if not exists activities (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid references organizations on delete cascade,
  contact_id      uuid references contacts on delete set null,
  deal_id         uuid references deals on delete set null,
  kind            text not null,                    -- email | reply | meeting | call | note
  brand           text,
  occurred_at     timestamptz not null default now(),
  detail          text,
  created_at      timestamptz default now(),
  deleted_at      timestamptz,

  constraint activities_kind_chk
    check (kind in ('email', 'reply', 'meeting', 'call', 'note'))
);

create index if not exists ix_activities_org on activities (organization_id, occurred_at desc);

-- ---------------------------------------------------------------------------
-- suppression -- do-not-contact, ACROSS ALL BRANDS by default (A2.9, WP1.4).
-- ---------------------------------------------------------------------------
create table if not exists suppression (
  id          uuid primary key default gen_random_uuid(),
  email       text,
  domain      text,
  reason      text not null,                        -- unsubscribe | bounce | complaint | manual | legal
  brand_scope text not null default 'all',          -- 'all' or a specific brand
  created_at  timestamptz default now(),

  constraint suppression_reason_chk
    check (reason in ('unsubscribe', 'bounce', 'complaint', 'manual', 'legal')),
  constraint suppression_target_chk
    check (email is not null or domain is not null)
);

create unique index if not exists ux_suppression_email
  on suppression (lower(email), brand_scope) where email is not null;
create unique index if not exists ux_suppression_domain
  on suppression (lower(domain), brand_scope) where domain is not null;

comment on table suppression is
  'Do-not-contact list. brand_scope defaults to all, so an unsubscribe suppresses across every brand within the honoring window (A2.9).';

-- ---------------------------------------------------------------------------
-- org_review_queue -- a fuzzy name+address match a human must adjudicate. The
-- system NEVER auto-merges two organizations on a fuzzy match (WP1.4).
-- ---------------------------------------------------------------------------
create table if not exists org_review_queue (
  id                uuid primary key default gen_random_uuid(),
  organization_id   uuid references organizations on delete cascade,
  candidate_name    text,
  candidate_pac_id  text,
  candidate_detail  jsonb,
  reason            text not null default 'fuzzy_name_address',
  resolved_at       timestamptz,
  resolution        text,                            -- merged | distinct | unresolved
  created_at        timestamptz default now(),

  constraint org_review_resolution_chk
    check (resolution is null or resolution in ('merged', 'distinct', 'unresolved'))
);

-- ---------------------------------------------------------------------------
-- RLS. Internal-only (sales/ops), same two-gate model as 0008/0013/0015.
-- ---------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array[
    'organizations', 'org_locations', 'contacts', 'contact_roles',
    'deals', 'activities', 'suppression', 'org_review_queue']
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
