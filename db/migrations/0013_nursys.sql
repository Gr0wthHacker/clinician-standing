-- =============================================================================
-- 0013_nursys.sql -- Nursys e-Notify consumption tables (PRD 6.1, build phase 3).
--
-- Nursys e-Notify is the primary source for RN/APRN licensure -- roughly half the
-- clinician base -- and is already seeded in the registry (0009: key 'nursys',
-- is_primary_source true, attests {license_renewal,csr_renewal,ce_cycle}). This
-- migration adds the two tables the connector needs, and nothing that holds PII.
--
-- THE PII BOUNDARY, ENFORCED BY WHAT IS ABSENT HERE
-- -----------------------------------------------------------------------------
-- Enrolling a nurse in Nursys requires last-4 SSN, birth year and home address
-- (Nursys e-Notify File and API Specifications v3.1.5, section 3.2.1: those
-- fields are Required on ManageNurseList). Under the client-owned-account model
-- (the one Clinician Standing operates), the client submits that enrollment file
-- directly into the Nursys web UI; it never reaches this system. The API this
-- system calls -- NurseLookup and NotificationLookup -- keys on NCSBN ID and
-- returns license status with no SSN and no DOB. So there is no ssn, no dob and
-- no dob_hash column below, on purpose: the schema cannot hold what the service
-- must never handle (PRD 2, "no PHI/PII"). The same rule that made
-- clinicians.dob_hash a hash and nothing more (0002) applies here as absence.
--
-- Enum-like columns are text + named CHECK constraint; see header of 0001.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- nursys_account -- one Nursys e-Notify Institution account we consume from.
--
-- One per client practice (Model A: the client owns the account, we hold API
-- credentials to it). The credentials themselves -- the redacted API URL, the
-- username and the 90-day-rotating password -- live in the secret manager, never
-- here: auth_ref is a KEY into that manager, exactly as sources.auth_ref is
-- (0006). password_set_at is not a secret; it is the rotation clock, and the
-- rotation job reads it to change the password before Nursys expires it.
-- ---------------------------------------------------------------------------
create table if not exists nursys_account (
  id                   uuid primary key default gen_random_uuid(),
  practice_id          uuid references practices,      -- the client this account belongs to
  label                text not null,                  -- human label for the account
  auth_ref             text not null,                  -- secret manager key: API url + username + password
  password_set_at      timestamptz,                    -- when the API password was last set; drives 90-day rotation
  last_notification_at timestamptz,                    -- watermark: newest notification consumed
  last_transaction_id  text,                           -- in-flight async NotificationLookup transaction, if any
  enabled              boolean default true,
  created_at           timestamptz default now(),
  deleted_at           timestamptz,

  constraint nursys_account_auth_ref_chk
    check (length(btrim(auth_ref)) > 0)
);

comment on table nursys_account is
  'One Nursys e-Notify Institution account we consume from (PRD 6.1). Client-owned; we hold API credentials only. Holds no PII -- enrollment (SSN4/DOB/address) is done by the client in the Nursys UI, never here.';
comment on column nursys_account.auth_ref is
  'Secret MANAGER KEY only, like sources.auth_ref. The redacted API URL, username and password live in the secret manager. Never a credential in the clear.';
comment on column nursys_account.password_set_at is
  'When the API password was last set. Nursys expires it every 90 days; the rotation job changes it proactively before then (change password method, spec 3.3).';

-- ---------------------------------------------------------------------------
-- nursys_enrollment -- the NCSBN ID <-> clinician bridge.
--
-- NCSBN ID is the durable, globally unique nurse identifier (spec 1.3.1; LOINC
-- 101114-7). NPI is neither a Nursys enrollment key nor a response field, so the
-- roster is joined to Nursys on NCSBN ID, established at client onboarding from
-- the license number the client supplies -- clinician credentialing data, not
-- PII. license_number/jurisdiction/license_type are kept for reconciliation and
-- for deriving the licenses row; status and last_notification_at track what the
-- feed last said.
-- ---------------------------------------------------------------------------
create table if not exists nursys_enrollment (
  id                   uuid primary key default gen_random_uuid(),
  account_id           uuid references nursys_account,
  clinician_id         uuid references clinicians,
  ncsbn_id             bigint not null,                -- Nursys durable id (Integer, up to 10 digits)
  jurisdiction         char(2),
  license_type         text,
  license_number       text,
  status               text,
  record_id            text,                           -- client-provided id the API echoes back
  enrolled_at          timestamptz default now(),
  last_notification_at timestamptz,
  created_at           timestamptz default now(),
  deleted_at           timestamptz,

  constraint nursys_enrollment_jurisdiction_chk
    check (jurisdiction is null or jurisdiction ~ '^[A-Z]{2}$'),
  constraint nursys_enrollment_ncsbn_chk
    check (ncsbn_id > 0),
  -- One enrollment per nurse per account. A nurse holds licenses in several
  -- states, but that is many licenses rows under one NCSBN ID, not many
  -- enrollments.
  unique (account_id, ncsbn_id)
);

comment on table nursys_enrollment is
  'NCSBN ID <-> clinician bridge (PRD 6.1). NCSBN ID is the durable Nursys key; NPI is not in Nursys at all. Established at onboarding from the client-supplied license number.';
comment on column nursys_enrollment.ncsbn_id is
  'Globally unique NCSBN nurse identifier (spec 1.3.1, LOINC 101114-7). The join key between our roster and the Nursys feed.';

create index if not exists ix_nursys_enrollment_clinician
  on nursys_enrollment (clinician_id) where deleted_at is null;
create index if not exists ix_nursys_enrollment_ncsbn
  on nursys_enrollment (ncsbn_id) where deleted_at is null;

-- ---------------------------------------------------------------------------
-- RLS. Both tables are internal-only, like sources and evidence: they carry
-- operational state and a secret-manager pointer, never client-facing data.
-- Same two-gate model as 0008 (grants + policy) and FORCE as 0011, applied to
-- the two new tables so a table owner is filtered too. No app_delivery and no
-- app_client_portal grant: the failure for those roles is a hard permission
-- error, not an empty result.
-- ---------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array['nursys_account','nursys_enrollment']
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

-- ---------------------------------------------------------------------------
-- SELF-CHECK. Fail the migration rather than leave a table reachable by the
-- restricted roles or unprotected by RLS. Mirrors 0011's self-check.
-- ---------------------------------------------------------------------------
do $$
declare
  unforced text;
  leaked   text;
begin
  select string_agg(c.relname, ', ' order by c.relname) into unforced
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public'
    and c.relkind = 'r'
    and c.relname in ('nursys_account','nursys_enrollment')
    and not (c.relrowsecurity and c.relforcerowsecurity);
  if unforced is not null then
    raise exception 'RLS is not enabled and forced on: %', unforced;
  end if;

  -- Neither restricted role may hold any privilege on either table. Read the
  -- ACL straight off pg_class via aclexplode so the check does not depend on
  -- who is running the migration (information_schema views are filtered by the
  -- current user; aclexplode is not).
  select string_agg(format('%s->%s', g.rolname, c.relname), ', ') into leaked
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  cross join lateral aclexplode(c.relacl) acl
  join pg_roles g on g.oid = acl.grantee
  where n.nspname = 'public'
    and c.relname in ('nursys_account','nursys_enrollment')
    and g.rolname in ('app_delivery','app_client_portal');
  if leaked is not null then
    raise exception 'restricted role holds a grant it must not: %', leaked;
  end if;
end $$;
