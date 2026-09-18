-- =============================================================================
-- requirement_conflicts_seed.sql -- what the rules asset does NOT yet know.
--
-- Two kinds of row live here, and both are deliberately left OPEN
-- (resolution = 'unresolved'), which blocks auto-clear (PRD 8.1 condition 6)
-- and raises RULE_UNCERTAIN (PRD 8.3):
--
--   A. GAPS -- a field_key in scope for a state/license_type for which no
--      primary source could be found and read on 2026-09-18. requirement_id is
--      NULL because no requirements row was written. published_value is NULL;
--      notes say what was searched and what remains open.
--
--   B. QUALIFIERS -- a requirements row EXISTS but a second official source, or
--      a statutory exception, narrows or contradicts it. requirement_id points
--      at the row. These are the rows that stop a confidently-wrong obligation.
--
-- observed_by is 'research-agent' throughout: these are desk-research findings,
-- not observed board behaviour. Rows recording actual board behaviour will be
-- written by delivery, which is the part a competitor cannot scrape (PRD 5.3).
--
-- Run AFTER requirements_seed.sql. Idempotent.
-- =============================================================================

begin;

delete from requirement_conflicts where observed_by = 'research-agent';

-- ---------------------------------------------------------------------------
-- B. QUALIFIERS on rows that exist.
-- ---------------------------------------------------------------------------
insert into requirement_conflicts
  (requirement_id, published_value, observed_value, observed_at, observed_by,
   occurrences, resolution, notes)
select r.id, c.published_value, c.observed_value,
       timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved', c.notes
from (values

 ('CA','MD','renewal_window_days',
  '180 days',
  'Board states a notification start date, not a renewal-open date',
  'The Medical Board of California says only that it "will send you email notifications to renew your license online starting 180 days prior to your expiration date". It does not publish the date on which the online renewal transaction actually opens, and does not say renewal is impossible before 180 days. OPEN: confirm with the Board whether 180 days is the transactional window. Until then treat 180 as an upper bound on notice, not a guaranteed open date.'),

 ('CA','APRN','supervision_required',
  'true (standardized procedures required)',
  'false for 103 NP and 104 NP certificate holders',
  'A single boolean cannot express California tiered NP authority. AB 890 (2020) added B&P Code sec. 2837.103 (103 NP, independent clinical decisions within a group setting containing at least one physician and surgeon) and sec. 2837.104 (104 NP, independent practice outside a group setting); both practise WITHOUT standardized procedures. Both require 4,600 hours or three full-time-equivalent years of transition-to-practice, and the Board cannot certify 104 NPs until 2026. The seeded value true is the conservative default that matches a traditional NP. OPEN: the schema needs either a per-clinician certificate-tier attribute or a value_json shape before this boolean can be trusted for a 103/104 NP. Source: https://www.rn.ca.gov/practice/ab890.shtml'),

 ('FL','APRN','renewal_fee_cents',
  'Florida Board of Nursing: $60.00 active-to-active',
  'Florida Statutes s. 464.012: "a biennial renewal fee not to exceed $50"',
  'TWO OFFICIAL SOURCES DISAGREE. The Board of Nursing publishes $60.00 for an active-to-active APRN renewal; s. 464.012, F.S. caps the board-set biennial renewal fee at $50. The most likely reconciliation is that the posted $60 bundles statutory add-ons outside the board fee cap (for example the s. 456.065(3) unlicensed activity fee), but neither source states the breakdown. The seeded value is the Board figure because that is what the licensee pays. OPEN: obtain the fee breakdown from DOH/MQA. Sources: https://floridasnursing.gov/advanced-practice-registered-nurse-renewal/ and https://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute&URL=0400-0499%2F0464%2FSections%2F0464.012.html'),

 ('FL','APRN','initial_license_fee_cents',
  'Florida Board of Nursing: $110.00 application and licensure fee',
  'Florida Statutes s. 464.012: "an application fee not to exceed $100"',
  'TWO OFFICIAL SOURCES DISAGREE, same pattern as the renewal fee above. Board publishes $110.00; s. 464.012, F.S. caps the application fee at $100. Seeded value is the Board figure. OPEN: obtain the fee breakdown from DOH/MQA.'),

 ('FL','APRN','collaborative_agreement_required',
  'true (established protocol required, s. 464.012, F.S.)',
  'false for APRNs registered for autonomous practice under s. 464.0123, F.S.',
  'Florida grants autonomous practice registration to an APRN who holds a clear active Florida APRN licence, has at least 3,000 clinical hours under the supervision of an allopathic or osteopathic physician within the past 5 years, holds three graduate semester hours each in differential diagnosis and pharmacology completed within the last five years, and has no disciplinary action in the past five years. An autonomously registered APRN is not bound by the s. 464.012 protocol. The seeded boolean true is the conservative default. OPEN: the platform needs a per-clinician autonomous-registration attribute; also confirm whether autonomous practice carries its own registration fee, which the Board page does not state. Source: https://floridasnursing.gov/advanced-practice-registered-nurse/'),

 ('TX','APRN','collaborative_agreement_required',
  'true (written prescriptive authority agreement, Tex. Occ. Code sec. 157.0512)',
  'verified only for prescribing, not for non-prescribing practice',
  'Tex. Occ. Code sec. 157.0512 requires a written prescriptive authority agreement before a physician may delegate prescriptive authority to an APRN. It does not, on its face, settle whether an APRN who does not prescribe must still hold a delegation or collaboration instrument to practise in Texas. OPEN: read Tex. Occ. Code ch. 301 and 22 TAC ch. 221 for the non-prescribing case. The Texas Board of Nursing rule pages under /rr_current/ are blocked to automated fetch by robots.txt and were not read.'),

 ('TX','APRN','ce_topic_opioid_hours',
  '2 hours annually (Tex. Occ. Code sec. 157.0513(a)(4))',
  'applicability is narrower than all Texas APRNs',
  'Sec. 157.0513(a)(4) requires "not less than two hours of continuing education annually" on safe pain management for an APRN or PA prescribing opioids, but the obligation is attached to the sec. 157.0513 delegation pathway rather than stated as a universal APRN CE requirement, and the Texas Board of Nursing CE pages that were read do not mention it. OPEN: confirm with the Board of Nursing whether it enforces this at renewal and against which population. Do not generate an annual obligation for every Texas APRN from this row until resolved.'),

 ('NY','MD','ce_topic_opioid_hours',
  '3 hours every 3 years (PHL sec. 3309-a(3))',
  'topic clock does not align with the 2-year NY physician registration cycle',
  'New York physicians register every two years, but the mandatory prescriber education runs on an independent three-year clock and is administered by the Department of Health, not by NYSED. An obligation generator that anchors this topic to the registration cycle will produce wrong dates. OPEN: confirm the anchor date -- whether the three years runs from the licensee''s last completion or from a fixed statutory date.')

) as c(state, license_type, field_key, published_value, observed_value, notes)
join requirements r
  on r.state = c.state
 and r.license_type = c.license_type
 and r.field_key = c.field_key
 and r.is_current
 and r.deleted_at is null;

-- ---------------------------------------------------------------------------
-- A. GAPS -- in-scope field_keys with no verified value. requirement_id NULL.
-- ---------------------------------------------------------------------------
insert into requirement_conflicts
  (requirement_id, published_value, observed_value, observed_at, observed_by,
   occurrences, resolution, notes)
values

-- ---- CALIFORNIA -----------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'GAP CA/MD/csr_required and CA/APRN/csr_required. California requires prescribers to register with CURES, the state PDMP (Health & Safety Code sec. 11165; Medical Board of California, CURES 101, https://www.mbc.ca.gov/Resources/Medical-Resources/CURES/CURES-101.aspx). CURES registration is a database-access registration, NOT a controlled substance registration in the sense this field_key means. No Medical Board or BRN page was found that affirmatively states California issues no separate state CSR, and a negative cannot be asserted from the absence of a page. NOT SEEDED. Separately: CURES registration is a real recurring obligation this field_key set does not model at all -- consider a pdmp_registration_required key.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'GAP CA/APRN/collaborative_agreement_required. California''s instrument is "standardized procedures" (B&P Code sec. 2725.5, 16 CCR sec. 1480), not a collaborative practice agreement. The two are functionally similar but legally distinct, and mapping one onto the other would misstate the obligation. NOT SEEDED; supervision_required carries the substance instead. OPEN: decide whether the schema should carry a state-neutral practice_authority_instrument key.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'GAP CA/MD/ce_topic_geriatrics_hours. The Medical Board of California states that general internists and family physicians whose patient population is more than 25 percent aged 65 or older must complete "at least 20 percent of their mandatory CME in the field of geriatric medicine". This is a conditional PERCENTAGE of the 50-hour total, not a fixed hour count, and it depends on a specialty-and-panel-composition test the platform does not hold data for. NOT SEEDED. Source: https://www.mbc.ca.gov/Licensing/Physicians-and-Surgeons/Renew/Current-Status/Continuing-Medical-Education.aspx'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'GAP CA/MD/ce_topic_implicit_bias_hours. AB 241 (2019) added an implicit bias requirement to California CME, but the Medical Board CME page read on 2026-09-18 does not state an hour count for physicians, and no hour count was found on a Board page. NOT SEEDED -- an invented number here would be a fabricated obligation. OPEN: read B&P Code sec. 2190.1 directly.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'GAP CA/APRN/ce_topic_gerontology_hours. The BRN states that an Advanced Practice certificate holder with a gerontology focus must take "at least 6 of the 30 continuing education hours required" in gerontology, dementia care or care of older patients. This is a subset of the 30, conditional on the certificate focus, and applies to a population the platform cannot currently identify. NOT SEEDED. Source: https://www.rn.ca.gov/licensees/ce-renewal.shtml'),

-- ---- FLORIDA --------------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'GAP FL/MD/csr_required and FL/APRN/csr_required. Neither the Florida Board of Medicine nor the Board of Nursing controlled-substance-prescriber FAQ answers whether a separate Florida state controlled substance registration exists; both pages discuss only E-FORCSE (PDMP) reporting and consultation duties. A negative cannot be asserted from silence. NOT SEEDED. OPEN: read F.S. ch. 893 (in particular s. 893.04 and s. 893.05) and the s. 456.44 chronic nonmalignant pain registration, which is a separate designation that may map to this key. Sources consulted: https://flboardofmedicine.gov/help-center/how-do-i-register-as-a-controlled-substance-prescriber/ and https://floridasnursing.gov/help-center/how-do-i-register-as-a-controlled-substance-prescriber/'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'GAP FL/MD/initial_license_fee_cents. The Florida Board of Medicine renewal page publishes renewal fees ($355 active-to-active, $705 after expiration) but no initial licensure application fee, and no Board fee schedule page for initial MD licensure was located. NOT SEEDED.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'GAP FL/MD/ce_topic_hiv_aids_hours. The Board of Medicine states a board-approved HIV/AIDS course is required "prior to the first renewal" but publishes no hour count for physicians (the Board of Nursing publishes 1 hour for APRNs). A one-time requirement with an unknown hour count. NOT SEEDED; the existence of the requirement is recorded here.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'GAP FL/MD/ce_topic_human_trafficking_hours. Florida requires human trafficking education of nurses by s. 464.013, F.S. (2 hours, seeded for APRN). The Board of Medicine general renewal page read on 2026-09-18 does NOT list a human trafficking CME requirement for MDs. This is an asymmetry between two Florida boards that may be real or may be an omission on the Board of Medicine page. NOT SEEDED for MD. OPEN: read F.S. s. 456.0342 and F.A.C. 64B8-13.005.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'GAP FL/APRN/renewal_window_days. The Board of Nursing APRN renewal page does not state how far before expiration renewal opens. The Board of Medicine publishes 90 days for MDs; whether DOH/MQA applies the same window to nursing was not verified and was NOT assumed. NOT SEEDED.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'GAP FL/APRN/supervision_required. s. 464.012, F.S. requires practice "within the framework of an established protocol" -- seeded as collaborative_agreement_required. Whether Florida additionally imposes physician SUPERVISION distinct from the protocol, and whether the answer differs by practice setting, was not established from a primary source. NOT SEEDED rather than duplicating the protocol finding under a second key.'),

-- ---- TEXAS ----------------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'GAP TX/MD/renewal_window_days. The Texas Medical Board publishes two different figures on one page: physicians may register online "up to 60-90 days prior to expiration", and "registration reminders will be sent out on postcards at least 60 days in advance of the expiration date". A range is not a value and picking an endpoint would be a guess. NOT SEEDED. Source: https://www.tmb.texas.gov/apply-renew/physician/physician-renewal'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'GAP TX/APRN/initial_license_fee_cents, TX/APRN/renewal_fee_cents, TX/APRN/fingerprint_required. The Texas Board of Nursing schedule of fees (https://www.bon.texas.gov/forms_fees.asp.html) and the licensure eligibility page could not be retrieved: the host returned repeated robots.txt fetch failures and an incomplete TLS chain to every client tried on 2026-09-18. The full text of 22 TAC 216.3 was likewise unreachable -- the Texas Secretary of State TAC viewer has moved to an Appian portal that serves no static text, and bon.texas.gov/rr_current/ is disallowed by robots.txt. NOT SEEDED. OPEN: retrieve these by hand or by a browser session.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'GAP TX/APRN/supervision_required. See the paired qualifier on collaborative_agreement_required: only the prescribing case is established. NOT SEEDED.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'GAP TX/MD and TX/APRN ce_topic_forensic_evidence_hours. The Texas Medical Board lists a 2-hour forensic evidence collection requirement for emergency and urgent care physicians under House Bill 47, effective 2/28/2027 -- a FUTURE effective date and a setting-conditional population. The Texas Board of Nursing references a targeted forensic evidence CE requirement at Rule 216.3(d) without an hour count on the page that was readable. NOT SEEDED for either. OPEN: seed the TMB row with effective_date 2027-02-28 once the population test is modelled. Source: https://www.tmb.texas.gov/apply-renew/physician/continuing-education-requirements-for-physicians'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'GAP TX/MD/ce_topic_obstetrics_hours. The Texas Medical Board lists a one-time "Life of the Mother Act" (SB 31) CME requirement for obstetric specialties, with no hour count published on the CME page. NOT SEEDED.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'CITATION DISCREPANCY TX/APRN/ce_hours_total. The Texas Board of Nursing continuing education page attributes the 20-contact-hour requirement to Board Rule 216.3(a); the Board''s own continuing education FAQ attributes the same 20 hours to Board Rule 216.5. The VALUE agrees (20 hours) -- only the rule number differs between two Board pages. Seeded citation says 216.3(a). OPEN: confirm against the rule text, which was unreachable (see the TX BON access gap above). Sources: https://www.bon.texas.gov/education_continuing_education.asp.html and https://www.bon.texas.gov/faq_education_continuing_ed_and_competency.asp.html'),

-- ---- NEW YORK -------------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'GAP NY/MD/ce_hours_total and NY/APRN/ce_hours_total. NYSED Office of the Professions publishes no general continuing education hour requirement for physicians or for registered nurses and nurse practitioners -- only mandated topic training (infection control, child abuse, prescriber education). New York is widely understood to have no general CME mandate for physicians, but the ABSENCE of a published number is not a verified zero, and seeding 0 would assert something no source states. NOT SEEDED. OPEN: obtain a written statement from NYSED, or cite Education Law sec. 6524 and 8 NYCRR part 60 directly.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'GAP NY/MD and NY/APRN ce_topic_infection_control_hours. NYSED requires infection control and barrier precautions training on a RECURRING four-year cycle -- for physicians under Public Health Law sec. 239 and for RNs under Education Law sec. 6505-b -- and licensees must attest to it "at every subsequent registration". NYSED publishes NO HOUR COUNT. A real recurring obligation with an unknown magnitude: the four-year cycle is verified, the hours are not, and this field_key can only hold hours. NOT SEEDED. OPEN: either obtain the hour count or add a ce_topic_infection_control_cycle_months key so the four-year duty can be scheduled without inventing hours. Sources: https://www.op.nysed.gov/about/training-continuing-education/mandated-training-related-infection-control and https://www.op.nysed.gov/professions/registered-professional-nursing/license-requirements'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'GAP NY/MD and NY/APRN ce_topic_child_abuse_hours. NYSED requires child abuse identification and reporting coursework as a ONE-TIME condition of initial licensure (with exemptions for graduates of NYSED-registered programs after 1 September 1990). No hour count is published. Because it is one-time and pre-licensure it generates no renewal-cycle obligation, and no hour value could be verified. NOT SEEDED.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'GAP NY/MD and NY/APRN renewal_window_days. NYSED expresses the window in months, not days, and gives two different figures: a renewal application is mailed "approximately four months before your registration expires", while online renewal is available during "the final 5 months of their current registration period". Converting either to days would be an invented precision. NOT SEEDED. Source: https://www.op.nysed.gov/registration-renewal/online-registration-renewal'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'GAP NY/MD and NY/APRN fingerprint_required. No NYSED Office of the Professions page was found stating either that fingerprints are required or that they are not, for medicine or for nursing. A negative cannot be asserted from silence. NOT SEEDED.'),

-- ---- CROSS-CUTTING --------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'SCOPE GAP: license_type ''DO'' is NOT COVERED in any of the four states. In Texas the TMB and in New York NYSED license MDs and DOs under the same authority, so the seeded MD rows are LIKELY to hold for DOs, but "likely" is not verified and no DO-specific page was read. In California the Osteopathic Medical Board of California and in Florida the Board of Osteopathic Medicine are SEPARATE boards with their own rules and fee schedules, and the seeded MD rows must NOT be applied to DOs there. Any consumer that resolves a DO to the MD rows is producing an unverified obligation.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'SCHEMA GAP: csr_renewal_cycle_months and csr_fee_cents are unseeded everywhere because the three states where csr_required was verified (TX, NY) all verified to FALSE, and the two where it is unknown (CA, FL) have no verified registration to attach a cycle or fee to. These keys become relevant only when a state with a live CSR is added.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, 'unresolved',
 'SCHEMA GAP: the field_key set has no slot for the PERIODICITY of a mandated CE topic. Several verified requirements are one-time (CA/MD pain management 12h, CA/APRN implicit bias 1h, FL/APRN HIV-AIDS 1h) or run on a clock other than the renewal cycle (FL domestic violence every third biennium, FL impairment every other renewal, TX ethics every third cycle, TX opioid every 8 years, TX human trafficking every 6 years, NY prescriber education every 3 years). These are seeded as value_json with an explicit periodicity rather than as a bare hour count, because a one-time 12-hour course recorded as a per-cycle 12 would generate a wrong obligation every two years for every California physician. ANY CONSUMER THAT READS value_num AND IGNORES value_json WILL SILENTLY DROP THESE REQUIREMENTS. Resolving this means a schema change, not a data change.');

commit;
