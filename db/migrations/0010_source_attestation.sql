-- 0010_source_attestation.sql
--
-- Two corrections to the sources registry, both arising from a conflation in the
-- PRD that the schema build surfaced.
--
-- 1. The PRD's section 6 grouped sources into "Tier 0 -- buy or subscribe" and
--    "Tier 1 -- free federal bulk", and the seed in 0009 read that grouping as a
--    proxy for is_primary_source. That was wrong. OIG LEIE is published by the
--    OIG itself and IS the authoritative record of exclusion; SAM.gov likewise
--    for federal debarment; CMS is the authority on Medicare enrollment and
--    revalidation. Free does not mean secondary. Left uncorrected, the monthly
--    exclusion_screen obligation emitted for every clinician could never satisfy
--    the auto-clear condition in PRD 8.1 that requires a primary-source
--    assertion -- which would have pushed a large share of all obligations into
--    the exception queue and suppressed the auto-clear rate, the single metric
--    the margin depends on.
--
-- 2. is_primary_source alone is too blunt. A source is authoritative for some
--    obligation types and silent on others: the CMS DAC file is authoritative
--    for directory accuracy and says nothing about license status. Auto-clear
--    must check that the source actually attests to the obligation type in
--    front of it, not merely that the source is "primary" in general.

alter table sources
  add column if not exists attests_obligation_types text[] not null default '{}';

comment on column sources.attests_obligation_types is
  'Obligation types this source can attest to. PRD 8.1 condition 1 must check '
  'membership here, not is_primary_source alone. Empty array means the source '
  'informs the roster but can never by itself clear an obligation.';

-- Correction 1: federal authoritative sources are primary sources.
update sources set is_primary_source = true
 where key in ('oig_leie', 'sam_gov', 'cms_revalidation', 'pecos', 'nppes');

-- cms_dac stays false: it is a monthly public extract that lags, useful for
-- roster construction and directory comparison but not an assertion of standing.
update sources set is_primary_source = false where key = 'cms_dac';

-- Correction 2: what each source can actually clear.
update sources set attests_obligation_types = '{exclusion_screen}'
 where key in ('oig_leie', 'sam_gov');

update sources set attests_obligation_types = '{medicare_revalidation}'
 where key = 'cms_revalidation';

update sources set attests_obligation_types = '{payer_revalidation}'
 where key = 'pecos';

update sources set attests_obligation_types = '{directory_attestation}'
 where key = 'nppes';

update sources set attests_obligation_types = '{}'
 where key = 'cms_dac';

update sources set attests_obligation_types =
    '{license_renewal,csr_renewal,ce_cycle}'
 where key in ('nursys', 'fsmb_pdc', 'state_ca', 'state_tx', 'state_nc', 'state_va');

update sources set attests_obligation_types = '{exclusion_screen}'
 where key = 'npdb_cq';

-- A source that attests to nothing must not be flagged primary: the pairing is
-- what makes PRD 8.1 decidable.
alter table sources drop constraint if exists sources_primary_attests_chk;
alter table sources add constraint sources_primary_attests_chk
  check (not is_primary_source or cardinality(attests_obligation_types) > 0);
