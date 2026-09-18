-- =============================================================================
-- 0009_seed_sources.sql -- seed the source registry (PRD 5.5, PRD 6).
--
-- is_primary_source IS THE FLAG THE AUTO-CLEAR LOGIC TURNS ON (PRD 8.1
-- condition 1). Read PRD 6 before changing a value here.
--
--   true  -- The body that publishes the fact is the authority on it. That is
--            the contracted primary sources and the state boards themselves
--            (nursys, fsmb_pdc, npdb_cq, state_ca, state_tx, state_nc,
--            state_va, PRD 6.1/6.3) AND the federal publishers of the fact:
--            OIG is the authority on exclusion, SAM.gov on federal debarment,
--            CMS on Medicare enrollment and revalidation. Free does not mean
--            secondary.
--   false -- Derivative extracts that describe rather than adjudicate. cms_dac
--            is the only one today: a monthly public directory extract,
--            published on a lag, useful for building the roster and comparing
--            directory data, never an assertion of standing.
--
-- THESE VALUES ARE PAIRED WITH sources.attests_obligation_types, added in
-- 0010_source_attestation.sql. PRD 8.1 condition 1 must check membership in
-- that array, not is_primary_source alone: a source is authoritative for some
-- obligation types and silent on others. 0010 also adds
-- sources_primary_attests_chk, which refuses a primary source that attests to
-- nothing. The values seeded here are the ones 0010 arrives at, so a fresh
-- build and a re-run of this file agree -- see the ON CONFLICT note at the
-- bottom, which is where the two files used to disagree.
--
-- Do not quietly flip a flag here to hit the 80% auto-clear target in PRD 15.2
-- -- that is the number the business model is validated against. Changing one
-- means changing attests_obligation_types with it, in a new migration.
--
-- freshness_sla_days scheme:
--   daily bulk            7   -- one missed run is still inside SLA
--   monthly bulk / file  45   -- publication cadence plus a two-week grace
--   state board files    30   -- primary source; licensure moves, keep it tight
--   continuous / push    90   -- the subscription itself reports changes, so the
--                               baseline only needs periodic re-confirmation
--
-- `enabled` reflects build status per PRD 14, not permission:
--   true  -- working today (cms_dac, oig_leie, cms_revalidation) or in the
--            10-week build (nursys, Phase 3)
--   false -- "Not yet built" (nppes, pecos, sam_gov) or "Later, funded
--            separately" (fsmb_pdc, npdb_cq, all state_*)
--
-- terms_reviewed_at is NULL for every row: no terms review has happened yet.
-- Any source promoted to kind = 'scrape' must carry one (sources_scrape_terms_chk)
-- and fails closed after 180 days (PRD 6.4, 13). terms_url values below are
-- starting points to confirm at first review, not adjudicated terms.
-- =============================================================================

insert into sources (
  key, display_name, kind, cadence, freshness_sla_days, is_primary_source,
  auth_ref, terms_url, terms_reviewed_at, enabled
) values

-- ---------------------------------------------------------------------------
-- NOTE ON THE is_primary_source COLUMN IN THESE VALUES ROWS
-- Every row below inserts `false`. That is a placeholder, not the seeded
-- value: the real values are asserted by the UPDATE at the bottom of this
-- file. The reason is 0010's sources_primary_attests_chk
-- (not is_primary_source or cardinality(attests_obligation_types) > 0).
-- Postgres evaluates CHECK constraints against the tuple an
-- INSERT ... ON CONFLICT proposes, before it discovers the conflict, and that
-- tuple takes the column's '{}' default. Re-applying this file against a
-- database that already has 0010 would abort on the first primary source in
-- the list even though every stored row is fine. Inserting `false` and then
-- updating keeps the file re-runnable, which db/README.md promises, and keeps
-- the check constraint at full strength.
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- Tier 0 -- buy or subscribe. Primary source, auditable (PRD 6.1).
-- ---------------------------------------------------------------------------
-- Free institution account. Push notifications plus an API for list maintenance.
-- "Highest value per hour of build effort in this document." API password
-- rotates every 90 days -- the rotation job reads auth_ref.
('nursys', 'Nursys e-Notify (NCSBN)', 'push', 'push', 90, false,
 'nursys/enotify_api_credentials', 'https://www.nursys.com/', null, true),

-- 1.2M MD/DO/PA. Licensure, disciplinary, board orders, NPI, DEA. Monthly file
-- plus API. Primary-source verified to NCQA standard; replaces scraping 50+
-- medical boards. PRD 15.1: get the quote before writing any board scraper.
('fsmb_pdc', 'FSMB Physician Data Center', 'api', 'monthly', 45, false,
 'fsmb/pdc_api_key', 'https://www.fsmb.org/physician-data-center/', null, false),

-- Adverse actions and malpractice payments. REQUIRES PRACTITIONER
-- AUTHORIZATION (PRD 2, 13) -- no authorization, no enrollment, no workarounds.
-- Authorization capture belongs in client onboarding.
('npdb_cq', 'NPDB Continuous Query', 'push', 'push', 90, false,
 'npdb/continuous_query_subscription',
 'https://www.npdb.hrsa.gov/orgs/continuousQuery.jsp', null, false),

-- ---------------------------------------------------------------------------
-- Tier 1 -- free federal bulk. Working today (PRD 6.2). Free, but the
-- publisher is the authority on the fact it publishes, so these are primary
-- sources -- except cms_dac, which is a directory extract. See the header.
-- ---------------------------------------------------------------------------
-- 839 MB, 3.39M rows. One row per clinician per location -- dedupe on
-- (NPI, org_pac_id) before counting. Carries phone, address, telehealth flag,
-- num_org_mem. A directory extract: it describes, it does not adjudicate, so
-- is_primary_source stays false and attests_obligation_types stays empty.
('cms_dac', 'CMS Doctors and Clinicians National Downloadable File',
 'bulk_file', 'monthly', 45, false,
 null, 'https://data.cms.gov/provider-data/topics/doctors-clinicians', null, true),

-- 15.6 MB, 84,001 rows, monthly full plus supplement. LATIN-1 ENCODED, NOT
-- UTF-8. Only 8,701 rows carry an NPI, so NPI matching alone finds almost
-- nothing -- name + DOB matching is mandatory (PRD 6.2, 15.3).
('oig_leie', 'OIG List of Excluded Individuals and Entities',
 'bulk_file', 'monthly', 45, false,
 null, 'https://oig.hhs.gov/exclusions/exclusions_list.asp', null, true),

-- 540 MB, 3.39M rows. LATIN-1 ENCODED. Group PAC ID, group due date,
-- individual due date, employer association count. Joins directly to
-- practices.org_pac_id. This file produced the 5,614-practice finding (PRD 9).
('cms_revalidation', 'CMS Revalidation Clinic Group Practice Reassignment',
 'bulk_file', 'monthly', 45, false,
 null,
 'https://data.cms.gov/provider-characteristics/medicare-provider-supplier-enrollment',
 null, true),

-- ~9 GB monthly replicate. Not yet built. Source of truth for taxonomy,
-- practice address and authorized official -- a directory, not an authority.
('nppes', 'NPPES NPI Registry Full Replicate', 'bulk_file', 'monthly', 45, false,
 null, 'https://download.cms.gov/nppes/NPI_Files.html', null, false),

-- Moderate size, monthly. Not yet built. Enrollment extract, not an authority.
-- NOTE: this is the PECOS FILE ingest. The PECOS PORTAL is Tier 4, never
-- automated (PRD 6.5) -- portal work raises PORTAL_REQUIRED and stays human.
('pecos', 'PECOS Enrollment Files', 'bulk_file', 'monthly', 45, false,
 null,
 'https://data.cms.gov/provider-characteristics/medicare-provider-supplier-enrollment',
 null, false),

-- Small, daily. Not yet built. Second exclusion source; disagreement with LEIE
-- is an exception, not a merge (PRD 6.2).
('sam_gov', 'SAM.gov Exclusions', 'bulk_file', 'daily', 7, false,
 'sam_gov/api_key', 'https://sam.gov/content/exclusions', null, false),

-- ---------------------------------------------------------------------------
-- Tier 2 -- state bulk files (PRD 6.3). Placeholders: registered so evidence
-- rows and per-state field mappings have a key to cite, but disabled until the
-- ingest is built and the terms are reviewed. Confirmed live per PRD 6.3.
-- These ARE the licensing authority, hence is_primary_source = true.
-- cadence is set to the conservative default 'monthly'; confirm each board's
-- actual publication cadence when building its ingest and correct this row.
-- ---------------------------------------------------------------------------
('state_ca', 'California Department of Consumer Affairs (DCA) licensee file',
 'bulk_file', 'monthly', 30, false,
 null, 'https://www.dca.ca.gov/', null, false),

('state_tx', 'Texas Medical Board (TMB) licensee file',
 'bulk_file', 'monthly', 30, false,
 null, 'https://www.tmb.state.tx.us/', null, false),

('state_nc', 'North Carolina Medical Board (NCMB) licensee file',
 'bulk_file', 'monthly', 30, false,
 null, 'https://www.ncmedboard.org/', null, false),

('state_va', 'Virginia Department of Health Professions (DHP) licensee file',
 'bulk_file', 'monthly', 30, false,
 null, 'https://www.dhp.virginia.gov/', null, false)

on conflict (key) do update set
  -- Refresh the descriptive contract fields on re-run; leave adjudicated and
  -- operational state alone.
  display_name       = excluded.display_name,
  kind               = excluded.kind,
  cadence            = excluded.cadence,
  freshness_sla_days = excluded.freshness_sla_days,
  terms_url          = excluded.terms_url;
  -- Deliberately NOT updated on conflict: is_primary_source, enabled, auth_ref,
  -- terms_reviewed_at.
  --
  -- is_primary_source is excluded here because `excluded.is_primary_source`
  -- is the placeholder `false` from the VALUES rows, not a seeded value. It is
  -- set by the UPDATE below instead.
  --
  -- WHY THIS MATTERS. When `is_primary_source = excluded.is_primary_source`
  -- was in this list, re-applying 0009 -- which db/README.md calls safe to
  -- re-run -- silently reverted the correction made in
  -- 0010_source_attestation.sql: oig_leie went back to false. That is the flag
  -- PRD 8.1 condition 1 reads, so every monthly exclusion_screen obligation
  -- stopped auto-clearing, for every clinician, with no error anywhere. The
  -- two files now state one set of values, below, so they cannot disagree.
  --
  -- enabled, auth_ref and terms_reviewed_at are changed by operations and by
  -- terms review; a migration re-run must not silently re-enable a source
  -- someone turned off or wipe a review date.

-- ---------------------------------------------------------------------------
-- is_primary_source -- THE SEEDED VALUES.
--
-- These are the values 0010_source_attestation.sql arrives at, restated here
-- so that a fresh build (this file, then 0010) and a re-run of this file agree
-- exactly. 0010 pairs each of them with sources.attests_obligation_types;
-- changing one here without changing that array there re-introduces the
-- disagreement this block exists to prevent, and sources_primary_attests_chk
-- will reject the result.
--
--   true  -- the publisher IS the authority on the fact it publishes. OIG on
--            exclusion, SAM.gov on federal debarment, CMS on Medicare
--            enrollment and revalidation, the boards and the contracted
--            primary-source feeds on licensure.
--   false -- a derivative directory extract. cms_dac only.
-- ---------------------------------------------------------------------------
update sources set is_primary_source = true
 where key in (
   'nursys', 'fsmb_pdc', 'npdb_cq',
   'oig_leie', 'sam_gov', 'cms_revalidation', 'pecos', 'nppes',
   'state_ca', 'state_tx', 'state_nc', 'state_va')
   and is_primary_source is distinct from true;

update sources set is_primary_source = false
 where key = 'cms_dac'
   and is_primary_source is distinct from false;
