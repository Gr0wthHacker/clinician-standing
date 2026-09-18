-- =============================================================================
-- requirements_seed_group_a.sql -- the rules asset, group A expansion states.
--
-- PA, NJ, GA, MA, CT, MD, DC, DE, RI, NH, VT, ME x { physician (MD),
-- nurse practitioner (APRN) }.
--
-- Companion to requirements_seed.sql (CA, FL, TX, NY), whose conventions this
-- file follows exactly. Other agents are seeding other state groups in
-- parallel; this file owns ONLY the twelve jurisdictions listed above and
-- deletes only its own rows.
--
-- VERIFICATION STANDARD (read db/seeds/README.md before editing):
--   Every row below carries a citation to a state board page, a state statute,
--   or a board rule that was FETCHED AND READ on 2026-09-18. No row is written
--   from recall, from a CE aggregator, or from inference. Nothing was carried
--   across from a sibling state -- the twelve jurisdictions here are mostly
--   contiguous and superficially similar, which makes inference tempting and
--   wrong (CT renews physicians ANNUALLY on a 24-month CE clock; its neighbours
--   RI, MA, NH, VT and ME all renew biennially). Where a value could not be
--   verified from a primary source it is NOT in this file -- it is in
--   requirement_conflicts_seed_group_a.sql as an open conflict. An open
--   conflict blocks auto-clear (PRD 8.1 condition 6) and raises RULE_UNCERTAIN
--   (PRD 8.3), which is the correct behaviour for a value we do not know.
--
-- VALUE COLUMN CONVENTION
--   value_num   a plain per-cycle quantity (months, days, hours, cents).
--   value_bool  a plain yes/no.
--   value_json  a quantity that is NOT simply "this much, every cycle" --
--               one-time requirements, requirements on a different clock than
--               the renewal cycle, and requirements that apply only to a subset
--               of licensees. Recording a one-time course as a per-cycle number
--               would generate a wrong obligation every cycle, so those carry
--               {"hours": n, "periodicity": ...} instead.
--               Consumers MUST branch on the presence of value_json.
--               This file also uses value_json for one FEE (NJ/APRN initial),
--               because New Jersey's initial certificate fee is one of two
--               amounts depending on the remaining term of the applicant's RN
--               licence; a single number there would be wrong for half the
--               population.
--
--   license_type 'MD' and 'APRN' match the vocabulary in 0003_credentials.sql.
--   DO IS NOT COVERED -- see the conflicts file. Note that in DE, RI, VT, ME,
--   NH, MD, DC and MA a single board licenses MDs and DOs, but "likely" is not
--   verified and no DO-specific page was read.
--
-- NEW field_keys introduced by this file (the brief's topic vocabulary had no
-- slot for these state mandates; every one of them is a real published duty):
--   ce_topic_risk_management_hours          (PA, MA, CT)
--   ce_topic_child_abuse_hours              (PA)
--   ce_topic_organ_donation_hours           (PA)
--   ce_topic_infectious_disease_hours       (CT)
--   ce_topic_sexual_assault_hours           (CT)
--   ce_topic_cultural_competency_hours      (CT)
--   ce_topic_veterans_behavioral_health_hours (CT)
--   ce_topic_substance_abuse_hours          (CT, DE, RI)
--   ce_topic_abuse_and_trafficking_recognition_hours (DE)
--   ce_topic_lgbtq_cultural_competency_hours (DC)
--   ce_topic_public_health_priority_hours   (DC)
--   ce_topic_end_of_life_care_hours         (MA, VT)
--   ce_topic_alzheimers_hours               (MA)
--   ce_topic_professional_boundaries_hours  (GA)
--   ce_topic_medication_administration_hours (VT)
-- They all satisfy requirements_field_key_chk. See the report / COVERAGE.md.
--
-- Fees are in cents and are the amount the licensee actually pays where the
-- board publishes a single total; component breakdowns are in the citation.
--
-- Idempotent: safe to re-run. Respects ux_requirements_current (one is_current
-- row per state/license_type/field_key).
-- =============================================================================

begin;

-- Re-running replaces only the rows this file owns. requirement_conflicts rows
-- written by requirement_conflicts_seed_group_a.sql point at these rows, so
-- they are cleared first; re-run the conflicts file AFTER this one.
delete from requirement_conflicts
 where observed_by = 'research-agent-group-a'
   and requirement_id in (
         select id from requirements
          where verified_by = 'research-agent-group-a'
            and state in ('PA','NJ','GA','MA','CT','MD','DC','DE','RI','NH','VT','ME')
            and license_type in ('MD','APRN'));

delete from requirements
 where verified_by = 'research-agent-group-a'
   and state in ('PA','NJ','GA','MA','CT','MD','DC','DE','RI','NH','VT','ME')
   and license_type in ('MD','APRN');

insert into requirements
  (state, license_type, field_key,
   value_text, value_num, value_bool, value_json,
   citation, citation_url, effective_date,
   verified_at, verified_by, version, is_current)
values

-- =============================================================================
-- PENNSYLVANIA -- medical doctor (MD)
-- State Board of Medicine, Bureau of Professional and Occupational Affairs.
-- 63 P.S. ch. 13 (Medical Practice Act); 49 Pa. Code ch. 16-18.
-- =============================================================================
('PA','MD','renewal_cycle_months', null, 24, null, null,
 'Pennsylvania Department of State, State Board of Medicine - Renewal Information: "Licenses expire December 31 of every even-numbered year." The Board''s CME requirements document states the same period as "the biennial period, which runs from January 1 of the odd year through December 31 of the next even year".',
 'https://www.pa.gov/agencies/dos/department-and-offices/bpoa/boards-commissions/medicine/renewal-information',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('PA','MD','renewal_window_days', null, 60, null, null,
 'Bureau of Professional and Occupational Affairs, Renewal Guide for Compact Licenses (rev. 7/2026): "Renewals are available approximately 60 days prior to the license expiration date." NOTE: the Board says "approximately", and this guide is addressed to compact (IMLC) licensees; see open conflict PA/MD/renewal_window_days.',
 'https://www.pa.gov/content/dam/copapwp-pagov/en/dos/department-and-offices/bpoa/medicine/imlc%20renewal%20guide%202026.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('PA','MD','ce_hours_total', null, 100, null, null,
 'State Board of Medicine, Continuing Medical Education Requirements for an Unrestricted MD License: "completion of 100 credit hours of continuing medical education in the preceding biennial period" is required of medical doctors. Twenty of the 100 must be AMA PRA Category 1.',
 'https://www.pa.gov/content/dam/copapwp-pagov/en/dos/department-and-offices/bpoa/medicine/continuing-ed/MedM%20-%20CME%20MD%20Unrestricted%20License.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('PA','MD','ce_cycle_months', null, 24, null, null,
 'State Board of Medicine, CME Requirements for an Unrestricted MD License: the 100 credit hours are counted over "the preceding biennial period, which runs from January 1 of the odd year through December 31 of the next even year", i.e. the CE cycle is the renewal cycle.',
 'https://www.pa.gov/content/dam/copapwp-pagov/en/dos/department-and-offices/bpoa/medicine/continuing-ed/MedM%20-%20CME%20MD%20Unrestricted%20License.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('PA','MD','ce_topic_child_abuse_hours', null, 2, null, null,
 'State Board of Medicine, CME Requirements for an Unrestricted MD License (Act 31 of 2014): "two (2) hours of Board-approved continuing education in child abuse recognition and reporting requirements must be completed for renewal or reactivation of a license", effective January 1, 2015. These hours may not be counted toward the 12 patient safety / risk management hours.',
 'https://www.pa.gov/content/dam/copapwp-pagov/en/dos/department-and-offices/bpoa/medicine/continuing-ed/MedM%20-%20CME%20MD%20Unrestricted%20License.pdf',
 '2015-01-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('PA','MD','ce_topic_risk_management_hours', null, 12, null, null,
 'State Board of Medicine, CME Requirements for an Unrestricted MD License: "At least 12 of the 100 hours must be completed in activities related to patient safety or risk management and may be completed in either Category 1 or 2." The child abuse and opioid hours "cannot be counted toward the 12 credit hours".',
 'https://www.pa.gov/content/dam/copapwp-pagov/en/dos/department-and-offices/bpoa/medicine/continuing-ed/MedM%20-%20CME%20MD%20Unrestricted%20License.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('PA','MD','ce_topic_opioid_hours', null, null, null,
 '{"hours": 2, "periodicity": "per_renewal_cycle", "applies_to": "prescribers and dispensers of opioids", "topics": ["pain management", "identification of addiction", "practices of prescribing or dispensing of opioids"]}'::jsonb,
 'State Board of Medicine, CME Requirements for an Unrestricted MD License (Act 124 of 2016): "all prescribers or dispensers ... complete at least two hours of continuing education in pain management, the identification of addiction or in the practices of prescribing or dispensing of opioids", effective January 1, 2017. Conditional on prescribing/dispensing, hence value_json. SUBJECT TO AN OPEN CONFLICT: the Board''s own Physician & Surgeon Licensure Snapshot publishes FOUR hours for the same duty -- see requirement_conflicts.',
 'https://www.pa.gov/content/dam/copapwp-pagov/en/dos/department-and-offices/bpoa/medicine/continuing-ed/MedM%20-%20CME%20MD%20Unrestricted%20License.pdf',
 '2017-01-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('PA','MD','initial_license_fee_cents', null, 3500, null, null,
 'Pennsylvania Department of State, Physician & Surgeon Licensure Snapshot: application fee "$35.00 - Graduate of Accredited Medical School"; "$85.00 - Graduate of Unaccredited Medical School". The seeded figure is the accredited-graduate fee, which is the population this platform serves.',
 'https://www.pa.gov/agencies/dos/department-and-offices/bpoa/boards-commissions/medicine/physician---surgeon-licensure-snapshot',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('PA','MD','renewal_fee_cents', null, 36000, null, null,
 'Pennsylvania Department of State, Physician & Surgeon Licensure Snapshot: "Biennial renewal of license" fee "$360.00". Confirmed by the BPOA Renewal Guide for Compact Licenses, which states "Medicine Compact Renewal - $360.00 + $25.00 IMLC Renewal fee" (the $25 surcharge applies only to compact licensees).',
 'https://www.pa.gov/agencies/dos/department-and-offices/bpoa/boards-commissions/medicine/physician---surgeon-licensure-snapshot',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

-- =============================================================================
-- PENNSYLVANIA -- certified registered nurse practitioner (APRN)
-- State Board of Nursing. 63 P.S. ch. 12A; 49 Pa. Code ch. 21 subch. C.
-- A PA CRNP holds an RN licence plus a CRNP licence; each carries its own fee,
-- and prescriptive authority is a further separately-renewed approval.
-- =============================================================================
('PA','APRN','renewal_cycle_months', null, 24, null, null,
 'Pennsylvania Department of State, Certified Registered Nurse Practitioner Licensure Snapshot: renewal occurs "every two years". The Board of Nursing Renewal Information page states "A notice for renewal will be sent biennially prior to the expiration date."',
 'https://www.pa.gov/agencies/dos/department-and-offices/bpoa/boards-commissions/nursing/certified-registered-nurse-practitioner-licensure-snapshot',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('PA','APRN','ce_hours_total', null, 30, null, null,
 'Pennsylvania Department of State, CRNP Licensure Snapshot: "30 hours of continuing education applicable to the licensee''s CRNP specialty, which must include 2 hours of approved training in how to recognize and report child abuse".',
 'https://www.pa.gov/agencies/dos/department-and-offices/bpoa/boards-commissions/nursing/certified-registered-nurse-practitioner-licensure-snapshot',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('PA','APRN','ce_cycle_months', null, 24, null, null,
 'Pennsylvania Department of State, CRNP Licensure Snapshot: the 30 hours are required for renewal "every two years", i.e. the CE cycle is the renewal cycle.',
 'https://www.pa.gov/agencies/dos/department-and-offices/bpoa/boards-commissions/nursing/certified-registered-nurse-practitioner-licensure-snapshot',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('PA','APRN','ce_topic_child_abuse_hours', null, 2, null, null,
 'Pennsylvania Department of State, CRNP Licensure Snapshot (Act 31 of 2014): the 30 hours "must include 2 hours of approved training in how to recognize and report child abuse". Board of Nursing Tips for Renewal: "Complete a Department of Human Services-approved Child Abuse Recognition and Reporting continuing education (Child Abuse CE) course."',
 'https://www.pa.gov/agencies/dos/department-and-offices/bpoa/boards-commissions/nursing/certified-registered-nurse-practitioner-licensure-snapshot',
 '2015-01-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('PA','APRN','ce_topic_pharmacotherapeutics_hours', null, null, null,
 '{"hours": 16, "periodicity": "per_renewal_cycle", "applies_to": "CRNP holding prescriptive authority approval", "subset_of_ce_hours_total": true}'::jsonb,
 'Pennsylvania Department of State, CRNP Licensure Snapshot: "If licensee has prescriptive authority approval, a minimum of 16 of the 30 hours of continuing education must be completed in pharmacology every two years." Conditional on prescriptive authority and carved OUT of (not added to) the 30-hour total, hence value_json.',
 'https://www.pa.gov/agencies/dos/department-and-offices/bpoa/boards-commissions/nursing/certified-registered-nurse-practitioner-licensure-snapshot',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('PA','APRN','ce_topic_organ_donation_hours', null, null, null,
 '{"hours": 2, "periodicity": "one_time", "window": "once within 5 years", "effective": "2026-05-01", "verified_for": "registered nurse licence"}'::jsonb,
 'Pennsylvania Department of State, Registered Nurses Licensure Snapshot: "2 hours of organ donation education one time within 5 years", effective May 1, 2026. Verified on the RN snapshot; a PA CRNP must hold and renew a PA RN licence, so the duty reaches this population through that licence. ONE-TIME, not per cycle. See requirement_conflicts for the scope caveat.',
 'https://www.pa.gov/agencies/dos/department-and-offices/bpoa/boards-commissions/nursing/registered-nurses-licensure-snapshot',
 '2026-05-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('PA','APRN','initial_license_fee_cents', null, 10000, null, null,
 'Pennsylvania Department of State, CRNP Licensure Snapshot: "$100.00 - Fee for applicants educated in-state"; "$140.00 - Fee for applicants educated in another state or jurisdiction". Seeded figure is the in-state fee. The underlying RN licence application is a separate fee ($95 for a Pennsylvania nursing-school graduate, per the RN snapshot).',
 'https://www.pa.gov/agencies/dos/department-and-offices/bpoa/boards-commissions/nursing/certified-registered-nurse-practitioner-licensure-snapshot',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('PA','APRN','renewal_fee_cents', null, 8100, null, null,
 'Pennsylvania Department of State, CRNP Licensure Snapshot: biennial CRNP renewal "$81.00", plus "$41" for renewal of prescriptive authority where held. The underlying RN licence renewal is a separate "$122.00 every two years" (RN snapshot). Seeded figure is the CRNP renewal alone.',
 'https://www.pa.gov/agencies/dos/department-and-offices/bpoa/boards-commissions/nursing/certified-registered-nurse-practitioner-licensure-snapshot',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('PA','APRN','collaborative_agreement_required', null, null, true, null,
 'Pennsylvania Department of State, CRNP Licensure Snapshot: a CRNP performs duties "in collaboration with a licensed physician". Prescriptive authority is separately conditioned on a prescriptive authority collaborative agreement (49 Pa. Code sec. 21.283, sec. 21.285; Board of Nursing CRNP Prescriptive Authority Collaborative Agreement Application Guide). SUBJECT TO AN OPEN CONFLICT: the Board''s application guide describes the agreement process but does not state that an agreement is mandatory for non-prescribing CRNP practice -- see requirement_conflicts.',
 'https://www.pa.gov/agencies/dos/department-and-offices/bpoa/boards-commissions/nursing/certified-registered-nurse-practitioner-licensure-snapshot',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

-- =============================================================================
-- NEW JERSEY -- advanced practice nurse (APRN)
-- NJ Board of Nursing, Division of Consumer Affairs. N.J.S.A. 45:11-45 et seq.
-- NEW JERSEY IS ALMOST ENTIRELY UNSEEDED. njconsumeraffairs.gov is behind an
-- Imperva/Incapsula bot wall that returned HTTP 403 to every automated fetch on
-- 2026-09-18 except the two pages cited below, and New Jersey does not publish
-- the N.J.A.C. on a state-hosted site (it is licensed to LexisNexis). No MD rows
-- could be written at all. See requirement_conflicts for the full list.
-- =============================================================================
('NJ','APRN','collaborative_agreement_required', null, null, true, null,
 'New Jersey Board of Nursing, Advanced Practice Nurse Certification: "An A.P.N. in New Jersey has prescriptive authority and is required to have a joint protocol with a collaborating physician who is licensed in New Jersey, prior to prescribing any medication or device." Scope note: verified for PRESCRIBING; the page does not address non-prescribing practice. See requirement_conflicts.',
 'https://www.njconsumeraffairs.gov/nur/Pages/APN-Certification.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('NJ','APRN','initial_license_fee_cents', null, null, null,
 '{"application_fee_cents": 10000, "certificate_fee_cents_options": [8000, 16000], "total_cents_options": [18000, 26000], "varies_by": "the remaining term of the applicant''s New Jersey RN licence"}'::jsonb,
 'New Jersey Board of Nursing, Application for Advanced Practice Nurse Certification: application fee "$100.00, made payable to the New Jersey Board of Nursing"; initial certification fee "either $80.00 or $160.00, based on the expiration date of your RN license". A single number would be wrong for roughly half the applicant population, hence value_json.',
 'https://www.njconsumeraffairs.gov/nur/Applications/Application-for-Advanced-Practice-Nurse-Certification.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

-- =============================================================================
-- GEORGIA -- physician (MD)
-- Georgia Composite Medical Board. O.C.G.A. tit. 43 ch. 34; Ga. Comp. R. & Regs.
-- ch. 360.
-- =============================================================================
('GA','MD','renewal_cycle_months', null, 24, null, null,
 'Georgia Composite Medical Board, Physician: "License renews biennially by the last day of your birth month."',
 'https://medicalboard.georgia.gov/licensure-information/physician',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('GA','MD','ce_hours_total', null, 40, null, null,
 'Georgia Composite Medical Board, Continuing Education and Other Required Training for Physicians (Board Rule 360-15): "not less than 40 hours biennially" of Board-approved CME. Confirmed on the Board''s Physician page: "40 hours biennially of Board-approved CME".',
 'https://medicalboard.georgia.gov/professional-resources/continuing-education-and-other-required-training-physicians',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('GA','MD','ce_cycle_months', null, 24, null, null,
 'Georgia Composite Medical Board, Continuing Education and Other Required Training for Physicians: the 40 hours are required "biennially", i.e. the CE cycle is the renewal cycle.',
 'https://medicalboard.georgia.gov/professional-resources/continuing-education-and-other-required-training-physicians',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('GA','MD','ce_topic_controlled_substance_hours', null, null, null,
 '{"hours": 3, "periodicity": "one_time", "window": "once during the physician''s career", "credit_type": "AMA/AOA PRA Category 1", "counts_toward_ce_hours_total": true}'::jsonb,
 'Georgia Composite Medical Board, Continuing Education and Other Required Training for Physicians: "at least three hours of AMA/AOA PRA Category 1 CME" on prescribing controlled substances, required once during a physician''s career; the hours may count toward the 40-hour biennial requirement. ONE-TIME, not per cycle.',
 'https://medicalboard.georgia.gov/professional-resources/continuing-education-and-other-required-training-physicians',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('GA','MD','ce_topic_professional_boundaries_hours', null, null, null,
 '{"hours": 2, "periodicity": "one_time", "window": "once during the physician''s career", "topics": ["professional boundaries", "sexual misconduct"], "counts_toward_ce_hours_total": true}'::jsonb,
 'Georgia Composite Medical Board, Continuing Education and Other Required Training for Physicians: "at least two hours of education and training" in professional boundaries and sexual misconduct, required once during a physician''s career. ONE-TIME, not per cycle.',
 'https://medicalboard.georgia.gov/professional-resources/continuing-education-and-other-required-training-physicians',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('GA','MD','ce_topic_pain_management_hours', null, null, null,
 '{"hours": 20, "periodicity": "per_renewal_cycle", "applies_to": "physicians practising in a pain management clinic who are not certified in pain medicine or palliative medicine"}'::jsonb,
 'Georgia Composite Medical Board, Continuing Education and Other Required Training for Physicians: a physician working in a pain clinic without certification in pain medicine or palliative medicine must complete "20 hours of continuing medical education pertaining to pain management or palliative medicine" biennially. Applies only to that setting-and-certification subset, hence value_json.',
 'https://medicalboard.georgia.gov/professional-resources/continuing-education-and-other-required-training-physicians',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('GA','MD','initial_license_fee_cents', null, 50000, null, null,
 'Georgia Composite Medical Board, Fee Schedule: physician initial application fee "$500".',
 'https://medicalboard.georgia.gov/licensure-information/fee-schedule',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('GA','MD','renewal_fee_cents', null, 23000, null, null,
 'Georgia Composite Medical Board, Fee Schedule and Physician page: "Renewal $230 | Late Renewal $455".',
 'https://medicalboard.georgia.gov/licensure-information/fee-schedule',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('GA','MD','fingerprint_required', null, null, true, null,
 'Georgia Composite Medical Board, Physician: applicants must "Complete a criminal background check via FBI-compliant fingerprint/biometric results". Verified at INITIAL LICENSURE; the Board does not publish a fingerprint condition on renewal on this page.',
 'https://medicalboard.georgia.gov/licensure-information/physician',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

-- =============================================================================
-- GEORGIA -- advanced practice registered nurse (APRN)
-- Georgia Board of Nursing, Secretary of State. O.C.G.A. tit. 43 ch. 26;
-- Ga. Comp. R. & Regs. ch. 410. A Georgia APRN holds an RN licence plus an APRN
-- authorization and renews both; the continuing competency duty attaches to the
-- RN licence.
-- =============================================================================
('GA','APRN','renewal_cycle_months', null, 24, null, null,
 'Georgia Secretary of State, How to Guide: APRN: "APRN licenses must be renewed every two years."',
 'https://sos.ga.gov/how-to-guide/how-guide-aprn',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('GA','APRN','renewal_window_days', null, 92, null, null,
 'Georgia Secretary of State, How to Guide: APRN: "For RNs and APRNs, the renewal period runs from November 1 through January 31." That is 92 days (30 in November, 31 in December, 31 in January). Confirmed by the Board''s Nursing Renewal Information page for the current cycle: "RN, APRN, and GAA renewals opened November 1, 2025 and must be completed by January 31, 2026."',
 'https://sos.ga.gov/how-to-guide/how-guide-aprn',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('GA','APRN','ce_hours_total', null, null, null,
 '{"hours": 30, "periodicity": "per_renewal_cycle", "applies_to": "licensees who satisfy continuing competency by the continuing-education option", "alternatives": ["national certification maintenance", "academic program of at least 2 credit hours", "employer verification of 500+ practice hours", "Board-approved reentry or nursing education program"], "attaches_to": "the underlying registered nurse licence"}'::jsonb,
 'Ga. Comp. R. & Regs. ch. 410-13 (Continuing Competency), as published by the Georgia Secretary of State: "Completion of thirty (30) continuing education hours by a Board approved provider" during the "biennial renewal period" is ONE OF FIVE alternative continuing competency options (Georgia Board of Nursing, Nursing Continuing Education: "Georgia law provides five options from which licensees may choose to satisfy the continuing competency requirements. Licensees must satisfy one of the options during the biennial renewal period."). Recording a bare 30 would invoice every Georgia nurse a CE duty that a nationally-certified APRN does not owe, hence value_json.',
 'https://rules.sos.ga.gov/gac/410-13',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('GA','APRN','ce_cycle_months', null, 24, null, null,
 'Ga. Comp. R. & Regs. ch. 410-13: continuing competency is satisfied "during the biennial renewal period", i.e. the CE cycle is the renewal cycle.',
 'https://rules.sos.ga.gov/gac/410-13',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('GA','APRN','collaborative_agreement_required', null, null, true, null,
 'Ga. Comp. R. & Regs. ch. 410-11 (Regulation of Advanced Practice Registered Nurses): the nurse protocol agreement "Shall be in writing and signed by the advanced practice nurse and the delegating physician" and must specify "parameters under which medical acts delegated by the physician may be performed", including "a provision for immediate consultation with the delegating physician or a physician designated in the absence of the delegating physician".',
 'https://rules.sos.ga.gov/gac/410-11',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('GA','APRN','initial_license_fee_cents', null, 7500, null, null,
 'Georgia Board of Nursing Fee Schedule: "APRN Authorization $75.00"; Georgia Secretary of State, How to Guide: APRN: "$75" non-refundable application fee for initial licensure, plus a $10.00 online processing fee. The underlying RN licence is a separate fee ($40 by examination, $75 by endorsement).',
 'https://sos.ga.gov/sites/default/files/forms/Nursing%20Board%20Fee%20Schedule%20(2).pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('GA','APRN','renewal_fee_cents', null, 6500, null, null,
 'Georgia Board of Nursing Fee Schedule: "License Renewal $65.00"; "Late Renewal $75.00". Georgia Secretary of State, How to Guide: APRN: "$65" non-refundable application fee for renewal, plus a $10.00 online processing fee. An APRN files TWO renewal applications (RN and APRN), each carrying this fee.',
 'https://sos.ga.gov/sites/default/files/forms/Nursing%20Board%20Fee%20Schedule%20(2).pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

-- =============================================================================
-- MASSACHUSETTS -- physician (MD)
-- Board of Registration in Medicine. M.G.L. c. 112; 243 CMR.
-- =============================================================================
('MA','MD','renewal_cycle_months', null, 24, null, null,
 'Massachusetts Board of Registration in Medicine, Renew my Physician Full License: "A Full medical license allows a physician to practice medicine independently in the Commonwealth of Massachusetts, and must be renewed every two years."',
 'https://www.mass.gov/how-to/renew-my-physician-full-license',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('MA','MD','ce_hours_total', null, 50, null, null,
 'Massachusetts Board of Registration in Medicine, Continuing Medical Education Pilot Program (effective January 1, 2018): "50 CME Credits" per biennial renewal, of which "10 Credits in Risk Mgmt, Cat. 1 or 2". The Board''s CME Requirements table states "50 CREDITS" for full licence renewal.',
 'https://www.mass.gov/info-details/continuing-medical-education-pilot-program',
 '2018-01-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('MA','MD','ce_cycle_months', null, 24, null, null,
 'Massachusetts Board of Registration in Medicine, Continuing Medical Education Pilot Program: the 50 credits are required "on a biennial basis"; the full licence "must be renewed every two years". CE cycle equals the renewal cycle.',
 'https://www.mass.gov/info-details/continuing-medical-education-pilot-program',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('MA','MD','ce_topic_risk_management_hours', null, 10, null, null,
 'Massachusetts Board of Registration in Medicine, Continuing Medical Education Pilot Program: "10 Credits in Risk Mgmt, Cat. 1 or 2", included within the 50-credit biennial total. Confirmed on the Board''s CME Requirements table ("Risk Management: 10 CREDITS" for renewal).',
 'https://www.mass.gov/info-details/continuing-medical-education-pilot-program',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('MA','MD','ce_topic_opioid_hours', null, null, null,
 '{"hours": 3, "periodicity": "per_renewal_cycle", "applies_to": "physicians who prescribe", "topics": ["opioid education", "pain management"]}'::jsonb,
 'Massachusetts Board of Registration in Medicine, CME Requirements: "Opioid Education and Pain Management -- 3 credits -- REQUIRED IF PRESCRIBING". Conditional on prescribing, hence value_json.',
 'https://www.mass.gov/doc/borim-cme-requirements-pdf/download',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('MA','MD','ce_topic_end_of_life_care_hours', null, null, null,
 '{"hours": 2, "periodicity": "one_time", "note": "required only if not completed previously"}'::jsonb,
 'Massachusetts Board of Registration in Medicine, CME Requirements: "End of Life Care -- 2 credits", required only if not completed previously. ONE-TIME, not per cycle.',
 'https://www.mass.gov/doc/borim-cme-requirements-pdf/download',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('MA','MD','ce_topic_alzheimers_hours', null, null, null,
 '{"hours": 1, "periodicity": "one_time", "applies_to": "physicians who serve adult populations", "exempt": ["initial licensure", "limited licensure"]}'::jsonb,
 'Massachusetts Board of Registration in Medicine, Renewal Requirement for Alzheimer''s Disease Continuing Medical Education (CME): "a minimum of 1.00 CME credit (1 hour)" on Alzheimer''s disease and related dementias for physicians renewing who serve adult populations; "This is a One-time requirement." Does not apply to initial or limited licensure. ONE-TIME, not per cycle.',
 'https://www.mass.gov/info-details/renewal-requirement-for-alzheimers-disease-continuing-medical-education-cme',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('MA','MD','initial_license_fee_cents', null, 60000, null, null,
 'Massachusetts Board of Registration in Medicine, Schedule of Fees: Physician - Full License Registration "$600 for initial".',
 'https://www.mass.gov/info-details/board-of-registration-in-medicine-schedule-of-fees',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('MA','MD','renewal_fee_cents', null, 60000, null, null,
 'Massachusetts Board of Registration in Medicine, Schedule of Fees: Physician - Renewal of License "$600 biennial". Confirmed on Renew my Physician Full License: "$600" per licence.',
 'https://www.mass.gov/info-details/board-of-registration-in-medicine-schedule-of-fees',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

-- =============================================================================
-- MASSACHUSETTS -- advanced practice registered nurse (APRN)
-- Board of Registration in Nursing. M.G.L. c. 112 sec. 80B; 244 CMR 4.00, 5.00.
-- A Massachusetts APRN holds an RN licence plus APRN authorization, renewed
-- together on the RN clock.
-- =============================================================================
('MA','APRN','renewal_cycle_months', null, 24, null, null,
 'Massachusetts Board of Registration in Nursing, Renew your nursing license: "Your RN license and APRN authorization expires at 11:59PM on your birthday in even numbered years", i.e. a two-year cycle.',
 'https://www.mass.gov/how-to/renew-your-nursing-license',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('MA','APRN','renewal_window_days', null, 90, null, null,
 'Massachusetts Board of Registration in Nursing, Renew your nursing license: "You can renew starting 90 days before expiration." This is a transactional open date, not merely a notification date.',
 'https://www.mass.gov/how-to/renew-your-nursing-license',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('MA','APRN','ce_hours_total', null, 15, null, null,
 '244 CMR 5.00 (Continuing Education), as published by the Massachusetts Board of Registration in Nursing: "15 hours of continuing education within the two years immediately preceding renewal of registration are required for licensure." Confirmed on the Board''s Mandatory Continuing Education for nurses page ("all licensed nurses in Massachusetts to complete 15 contact hours (CH)").',
 'https://www.mass.gov/doc/244-cmr-5-continuing-education/download',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('MA','APRN','ce_cycle_months', null, 24, null, null,
 '244 CMR 5.00: the 15 hours must be earned "within the two years immediately preceding renewal of registration", i.e. the CE cycle is the renewal cycle.',
 'https://www.mass.gov/doc/244-cmr-5-continuing-education/download',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('MA','APRN','supervision_required', null, null, null,
 '{"required": true, "until_supervised_practice_years": 2, "scope": "prescriptive practice only", "supervisor": "Qualified Healthcare Professional (physician with an unrestricted BORIM licence who is board-certified in a related specialty or holds related hospital admitting privileges, or a qualifying CRNA, CNP or PNMHCS)", "instrument": "mutually agreed upon guidelines", "after_threshold": "may engage in prescriptive practice without supervision"}'::jsonb,
 '244 CMR 4.00 (Advanced Practice Registered Nursing): "CRNAs, CNPs or PNMHCSs with less than two years of supervised practice experience ... may engage in prescriptive practice with supervision by a Qualified Healthcare Professional", and "with less than two years supervised practice will develop mutually agreed upon guidelines with the Qualified Healthcare Professional"; "CRNAs, CNPs or PNMHCSs with a minimum of two years of supervised practice may engage in prescriptive practice without supervision." Conditional on an experience threshold AND limited to prescriptive practice, so a plain boolean would be wrong for most of the population -- hence value_json.',
 'https://www.mass.gov/doc/244-cmr-4-advanced-practice-registered-nursing/download',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('MA','APRN','initial_license_fee_cents', null, 15000, null, null,
 'Massachusetts Board of Registration in Nursing, Apply for APRN authorization: "APRN authorization fee | $150 | per application". The underlying RN licence is a separate fee.',
 'https://www.mass.gov/how-to/apply-for-aprn-authorization',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('MA','APRN','renewal_fee_cents', null, 18000, null, null,
 'Massachusetts Board of Registration in Nursing, Renew your nursing license: "RN with APRN renewal" costs "$180 per renewal" (an RN-only renewal is "$120 per renewal"). Seeded figure is the combined RN + APRN renewal, which is what an APRN actually pays.',
 'https://www.mass.gov/how-to/renew-your-nursing-license',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

-- =============================================================================
-- CONNECTICUT -- physician (MD)
-- CT DPH Practitioner Licensing and Investigations. C.G.S. ch. 370.
-- CONNECTICUT IS THE STATE THAT BREAKS THE PATTERN: the licence renews ANNUALLY
-- but the CME obligation runs on a 24-MONTH clock. An obligation generator that
-- assumes ce_cycle_months == renewal_cycle_months will be wrong here.
-- =============================================================================
('CT','MD','renewal_cycle_months', null, 12, null, null,
 'Connecticut DPH, Practitioner Licensure General Policies and Procedures: "Licenses are renewed annually during the licensee''s month of birth." Confirmed negatively by the Department''s list of Health Care Practitioner License Types that Expire Biennially, on which Physician/Surgeon does NOT appear (the list is acupuncturist, barber, electrologist, esthetician, eye lash technician, hairdresser/cosmetician, hearing instrument specialist, nursing home administrator, marital and family therapist associate, massage therapist, occupational therapist, occupational therapy assistant, tattoo technician).',
 'https://portal.ct.gov/dph/practitioner-licensing--investigations/plis/practitioner-licensure-general-policies-and-procedures',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','MD','renewal_window_days', null, 60, null, null,
 'Connecticut DPH, Health Care Practitioner Renewal Information: "Most licensees can expect to receive renewal notification approximately 60 days prior to expiration"; physicians "receive renewal notifications by email only". NOTE: the Department states a NOTIFICATION start, not an explicit renewal-open date; see open conflict CT/MD/renewal_window_days.',
 'https://portal.ct.gov/dph/practitioner-licensing--investigations/renewal/health-care-practitioner-renewal-information',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','MD','ce_hours_total', null, 50, null, null,
 'Connecticut DPH, Continuing Medical Education (C.G.S. sec. 20-10b): "A licensed physician applying for renewal shall earn a minimum of fifty contact hours of qualifying continuing medical education within the preceding twenty-four month period." "One contact hour means a minimum of fifty minutes of continuing education activity."',
 'https://portal.ct.gov/dph/practitioner-licensing--investigations/physician/continuing-medical-education',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','MD','ce_cycle_months', null, 24, null, null,
 'Connecticut DPH, Continuing Medical Education: the fifty contact hours are earned "within the preceding twenty-four month period". THE CE CYCLE IS TWICE THE 12-MONTH RENEWAL CYCLE; these two values deliberately disagree.',
 'https://portal.ct.gov/dph/practitioner-licensing--investigations/physician/continuing-medical-education',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','MD','ce_topic_infectious_disease_hours', null, null, null,
 '{"hours": 1, "periodicity": "first_renewal_then_every_6_years", "topics": ["infectious diseases", "AIDS", "HIV"]}'::jsonb,
 'Connecticut DPH, Continuing Medical Education: "at least one contact hour of training or education" in infectious diseases, including AIDS and HIV, required during the first renewal period requiring CME and "not less than once every six years thereafter". NOT every cycle.',
 'https://portal.ct.gov/dph/practitioner-licensing--investigations/physician/continuing-medical-education',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','MD','ce_topic_risk_management_hours', null, null, null,
 '{"hours": 1, "periodicity": "first_renewal_then_every_6_years", "topics": ["risk management", "prescribing controlled substances", "pain management"]}'::jsonb,
 'Connecticut DPH, Continuing Medical Education: "at least one contact hour" in risk management, including controlled substance prescribing and pain management, required during the first renewal period requiring CME and "not less than once every six years thereafter". NOT every cycle.',
 'https://portal.ct.gov/dph/practitioner-licensing--investigations/physician/continuing-medical-education',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','MD','ce_topic_sexual_assault_hours', null, null, null,
 '{"hours": 1, "periodicity": "first_renewal_then_every_6_years"}'::jsonb,
 'Connecticut DPH, Continuing Medical Education: one contact hour in sexual assault, required during the first renewal period requiring CME and "not less than once every six years thereafter". NOT every cycle.',
 'https://portal.ct.gov/dph/practitioner-licensing--investigations/physician/continuing-medical-education',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','MD','ce_topic_domestic_violence_hours', null, null, null,
 '{"hours": 1, "periodicity": "first_renewal_then_every_6_years"}'::jsonb,
 'Connecticut DPH, Continuing Medical Education: one contact hour in domestic violence, required during the first renewal period requiring CME and "not less than once every six years thereafter". NOT every cycle.',
 'https://portal.ct.gov/dph/practitioner-licensing--investigations/physician/continuing-medical-education',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','MD','ce_topic_cultural_competency_hours', null, null, null,
 '{"hours": 1, "periodicity": "first_renewal_then_every_6_years"}'::jsonb,
 'Connecticut DPH, Continuing Medical Education: one contact hour in cultural competency, required during the first renewal period requiring CME and "not less than once every six years thereafter". NOT every cycle.',
 'https://portal.ct.gov/dph/practitioner-licensing--investigations/physician/continuing-medical-education',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','MD','ce_topic_veterans_behavioral_health_hours', null, null, null,
 '{"hours": 2, "periodicity": "first_renewal_then_every_6_years", "topics": ["mental health conditions common to veterans and their families", "PTSD screening", "suicide risk assessment", "suicide prevention training"]}'::jsonb,
 'Connecticut DPH, Continuing Medical Education: "at least two contact hours" of behavioral health training on mental health conditions common to veterans and their families -- including PTSD screening, suicide risk assessment and suicide prevention -- required during the first renewal period requiring CME and "not less than once every six years thereafter". NOT every cycle.',
 'https://portal.ct.gov/dph/practitioner-licensing--investigations/physician/continuing-medical-education',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','MD','initial_license_fee_cents', null, 56500, null, null,
 'Connecticut DPH, Physician Licensure: "Initial Application Fee: $565.00".',
 'https://portal.ct.gov/dph/practitioner-licensing--investigations/physician/physician-licensure',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','MD','renewal_fee_cents', null, 57500, null, null,
 'Connecticut DPH, Physician Licensure: "Renewal Application Fee: $575.00". This is an ANNUAL fee -- see CT/MD/renewal_cycle_months.',
 'https://portal.ct.gov/dph/practitioner-licensing--investigations/physician/physician-licensure',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','MD','csr_required', null, null, true, null,
 'Connecticut Department of Consumer Protection, Controlled Substance Practitioner Registration: "This is a mandatory requirement for licensed medical personnel who prescribe controlled substances in Connecticut." Connecticut''s CSR is issued by DCP, not by DPH, and is separate from both the DPH licence and the federal DEA registration.',
 'https://portal.ct.gov/dcp/license-services-division/all-license-applications/controlled-substance-practitioner-registration',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','MD','csr_renewal_cycle_months', null, 24, null, null,
 'Connecticut Department of Consumer Protection, Controlled Substance Practitioner Registration: "All registrations expire biennially on February 28th of every odd-numbered year." THE CSR CLOCK (24 months, fixed calendar date) DOES NOT ALIGN WITH THE 12-MONTH BIRTH-MONTH LICENCE CLOCK.',
 'https://portal.ct.gov/dcp/license-services-division/all-license-applications/controlled-substance-practitioner-registration',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','MD','csr_fee_cents', null, 4000, null, null,
 'Connecticut Department of Consumer Protection, Controlled Substance Practitioner Registration: initial application fee $40; "Renewal Fee - $40."',
 'https://portal.ct.gov/dcp/license-services-division/all-license-applications/controlled-substance-practitioner-registration',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

-- =============================================================================
-- CONNECTICUT -- advanced practice registered nurse (APRN)
-- CT DPH. C.G.S. ch. 378. Same annual-licence / 24-month-CE split as physicians.
-- =============================================================================
('CT','APRN','renewal_cycle_months', null, 12, null, null,
 'Connecticut DPH, knowledge base article "Renew a nursing license online": "Most licenses expire in the first birth month after they''re issued, and are renewed annually after that." Confirmed negatively by the Department''s list of Health Care Practitioner License Types that Expire Biennially, on which Advanced Practice Registered Nurse does NOT appear.',
 'https://portal.ct.gov/dph/knowledge-base/articles/licensing/renew-a-nursing-license-online',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','APRN','renewal_window_days', null, 60, null, null,
 'Connecticut DPH, knowledge base article "Renew a nursing license online": "You can expect a renewal notification sent to your email 60 days before your license expires." NOTE: a NOTIFICATION date, not a stated renewal-open date; see open conflict.',
 'https://portal.ct.gov/dph/knowledge-base/articles/licensing/renew-a-nursing-license-online',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','APRN','ce_hours_total', null, 50, null, null,
 'Connecticut DPH, APRN Continuing Education: "a minimum of fifty (50) contact hours of continuing education within the preceding twenty-four (24) month period".',
 'https://portal.ct.gov/dph/practitioner-licensing--investigations/aprn/continuing-education',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','APRN','ce_cycle_months', null, 24, null, null,
 'Connecticut DPH, APRN Continuing Education: the fifty contact hours are earned "within the preceding twenty-four (24) month period". THE CE CYCLE IS TWICE THE 12-MONTH RENEWAL CYCLE.',
 'https://portal.ct.gov/dph/practitioner-licensing--investigations/aprn/continuing-education',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','APRN','ce_topic_pharmacotherapeutics_hours', null, 5, null, null,
 'Connecticut DPH, APRN Continuing Education: "at least five (5) contact hours" in pharmacotherapeutics, within the 50-hour / 24-month total.',
 'https://portal.ct.gov/dph/practitioner-licensing--investigations/aprn/continuing-education',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','APRN','ce_topic_infectious_disease_hours', null, 1, null, null,
 'Connecticut DPH, APRN Continuing Education: "at least one contact hour" in diseases, including AIDS and HIV. The APRN page states no six-year qualifier for this topic, unlike the physician page; see requirement_conflicts.',
 'https://portal.ct.gov/dph/practitioner-licensing--investigations/aprn/continuing-education',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','APRN','ce_topic_risk_management_hours', null, 1, null, null,
 'Connecticut DPH, APRN Continuing Education: "at least one contact hour" in risk management. The APRN page states no six-year qualifier for this topic, unlike the physician page; see requirement_conflicts.',
 'https://portal.ct.gov/dph/practitioner-licensing--investigations/aprn/continuing-education',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','APRN','ce_topic_sexual_assault_hours', null, 1, null, null,
 'Connecticut DPH, APRN Continuing Education: "at least one contact hour" in sexual assault. The APRN page states no six-year qualifier for this topic, unlike the physician page; see requirement_conflicts.',
 'https://portal.ct.gov/dph/practitioner-licensing--investigations/aprn/continuing-education',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','APRN','ce_topic_domestic_violence_hours', null, 1, null, null,
 'Connecticut DPH, APRN Continuing Education: "at least one contact hour" in domestic violence. The APRN page states no six-year qualifier for this topic, unlike the physician page; see requirement_conflicts.',
 'https://portal.ct.gov/dph/practitioner-licensing--investigations/aprn/continuing-education',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','APRN','ce_topic_cultural_competency_hours', null, 1, null, null,
 'Connecticut DPH, APRN Continuing Education: "at least one contact hour" in cultural competency. The APRN page states no six-year qualifier for this topic, unlike the physician page; see requirement_conflicts.',
 'https://portal.ct.gov/dph/practitioner-licensing--investigations/aprn/continuing-education',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','APRN','ce_topic_substance_abuse_hours', null, 1, null, null,
 'Connecticut DPH, APRN Continuing Education: "at least one contact hour" in substance abuse, including controlled substance prescribing and pain management.',
 'https://portal.ct.gov/dph/practitioner-licensing--investigations/aprn/continuing-education',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','APRN','ce_topic_veterans_behavioral_health_hours', null, null, null,
 '{"hours": 2, "periodicity": "first_renewal_then_every_6_years", "topics": ["mental health conditions common to veterans and their families"]}'::jsonb,
 'Connecticut DPH, APRN Continuing Education: "not less than two contact hours" on veterans'' mental health during the first renewal period requiring CE, then "not less than once every six years thereafter". NOT every cycle.',
 'https://portal.ct.gov/dph/practitioner-licensing--investigations/aprn/continuing-education',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','APRN','initial_license_fee_cents', null, 20000, null, null,
 'Connecticut DPH, APRN Licensure Requirements: "A completed application and fee in the amount of $200.00."',
 'https://portal.ct.gov/dph/practitioner-licensing--investigations/aprn/aprn-licensure-requirements',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','APRN','csr_required', null, null, true, null,
 'Connecticut Department of Consumer Protection, Controlled Substance Practitioner Registration: "This is a mandatory requirement for licensed medical personnel who prescribe controlled substances in Connecticut", and the registration applies to practitioners including Advanced Practice Registered Nurses.',
 'https://portal.ct.gov/dcp/license-services-division/all-license-applications/controlled-substance-practitioner-registration',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','APRN','csr_renewal_cycle_months', null, 24, null, null,
 'Connecticut Department of Consumer Protection, Controlled Substance Practitioner Registration: "All registrations expire biennially on February 28th of every odd-numbered year."',
 'https://portal.ct.gov/dcp/license-services-division/all-license-applications/controlled-substance-practitioner-registration',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('CT','APRN','csr_fee_cents', null, 4000, null, null,
 'Connecticut Department of Consumer Protection, Controlled Substance Practitioner Registration: initial application fee $40; "Renewal Fee - $40."',
 'https://portal.ct.gov/dcp/license-services-division/all-license-applications/controlled-substance-practitioner-registration',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

-- =============================================================================
-- MARYLAND -- physician (MD)
-- Maryland Board of Physicians. Md. Health Occ. tit. 14; COMAR 10.32.
-- =============================================================================
('MD','MD','renewal_cycle_months', null, 24, null, null,
 'Maryland Board of Physicians, Physician License Renewals: biennial renewal; "The biennial license renewal period starts on July 15, 2025, for physicians whose last name begins with the letters M - Z" and licences expire September 30 at 11:59 pm. The Board alternates halves of the alphabet year by year.',
 'https://www.mbp.state.md.us/licensure_phyrenewals.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('MD','MD','renewal_window_days', null, 78, null, null,
 'Maryland Board of Physicians, 2025 Physician License Renewal Information: "The biennial license renewal period starts on July 15, 2025" and the licensee must "pay the renewal fee of $512.00 to the Board by 11:59 pm (EST) on September 30, 2025". July 15 through September 30 inclusive is 78 days (17 in July, 31 in August, 30 in September). The 2026 renewal page states the same pattern with a July 15 open and September 30 expiry.',
 'https://www.mbp.state.md.us/forms/2025_renewal_info.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('MD','MD','ce_hours_total', null, 50, null, null,
 'COMAR 10.32.01.10C(1): "in a 2-year period, an applicant shall earn at least 50 credit hours of Category I or II CME, with at least 25 of those CME credit hours being Category 1." Confirmed on the Board''s Physician License Renewals page. SUBJECT TO AN OPEN CONFLICT: the Board''s Physician Renewal FAQ states "at least 50 Category 1 CME credits" -- see requirement_conflicts.',
 'https://regs.maryland.gov/us/md/exec/comar/10.32.01.10',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('MD','MD','ce_cycle_months', null, 24, null, null,
 'COMAR 10.32.01.10C(1): the 50 credit hours are earned "in a 2-year period" preceding expiration, i.e. the CE cycle is the renewal cycle.',
 'https://regs.maryland.gov/us/md/exec/comar/10.32.01.10',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('MD','MD','initial_license_fee_cents', null, 31000, null, null,
 'Maryland Board of Physicians, Physician Licensure Information: "A non-refundable $310 application processing fee". The Criminal History Records Check is a separate third-party fee.',
 'https://www.mbp.state.md.us/licensure_phyapp.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('MD','MD','renewal_fee_cents', null, 51200, null, null,
 'Maryland Board of Physicians, Physician License Renewals: biennial renewal total "$512.00", comprising a $436 renewal fee, a $50 physician rehabilitation / peer review program fee and a $26 Maryland Health Care Commission assessment.',
 'https://www.mbp.state.md.us/licensure_phyrenewals.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('MD','MD','fingerprint_required', null, null, true, null,
 'Maryland Board of Physicians, Physician Licensure Information: "All applicants are required to submit a Criminal History Records check (CHRC) as a qualification to licensure"; the Board instructs applicants to submit fingerprints no earlier than six weeks before completing the application and to match the name on the fingerprint request to the application. Verified at INITIAL LICENSURE.',
 'https://www.mbp.state.md.us/licensure_phyapp.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

-- =============================================================================
-- MARYLAND -- nurse practitioner (APRN)
-- Maryland Board of Nursing. Md. Health Occ. tit. 8; COMAR 10.27.01, 10.27.07.
-- =============================================================================
('MD','APRN','renewal_cycle_months', null, 24, null, null,
 'COMAR 10.27.07.04 (Renewal of Certification): "A certification as a nurse practitioner expires at the same time as the nurse practitioner''s registered nursing license" and is renewed biennially. COMAR 10.27.01.13: "The Board shall renew licenses biennially", expiring "not later than the 28th day of the licensee''s birth month" in odd or even years depending on birth year.',
 'https://regs.maryland.gov/us/md/exec/comar/10.27.07.04',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('MD','APRN','ce_hours_total', null, null, null,
 '{"hours": 30, "periodicity": "per_renewal_cycle", "applies_to": "licensees who satisfy the requirement by the continuing-education option", "alternatives": ["practice hours", "completion of education"], "attaches_to": "the underlying registered nurse licence"}'::jsonb,
 'COMAR 10.27.01.13 (Renewal of License): a nurse must complete "30 continuing education units (CEUs) within the 2 years immediately preceding the date of the renewal application", or alternatively satisfy practice hours or education completion requirements instead. Because the CEU route is one of several alternatives, a bare 30 would invoice a duty many licensees do not owe -- hence value_json. COMAR 10.27.07.04 imposes no separate CE hour count on the nurse practitioner certification itself, only current national certification.',
 'https://regs.maryland.gov/us/md/exec/comar/10.27.01.13',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('MD','APRN','ce_cycle_months', null, 24, null, null,
 'COMAR 10.27.01.13: the continuing education units are counted "within the 2 years immediately preceding the date of the renewal application", i.e. the CE cycle is the renewal cycle.',
 'https://regs.maryland.gov/us/md/exec/comar/10.27.01.13',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('MD','APRN','renewal_fee_cents', null, 21600, null, null,
 'Maryland Board of Nursing, Schedule of Fees (effective 7/1/2025): Nurse Practitioner (CRNP) biennial renewal "$216.00", which includes the $26 MHCC fee, a $15 preceptorship surcharge and $10 for initial advanced practice certification. The underlying RN renewal is a separate "$191.00".',
 'https://health.maryland.gov/mbon/pages/services-fees.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

-- =============================================================================
-- DISTRICT OF COLUMBIA -- physician (MD)
-- DC Health, Board of Medicine. D.C. Code tit. 3 ch. 12; 17 DCMR ch. 46.
-- =============================================================================
('DC','MD','renewal_cycle_months', null, 24, null, null,
 '17 DCMR sec. 4601.1 (Term of License): "a license issued pursuant to this chapter shall expire at 12:00 midnight of December 31 of each even-numbered year", i.e. a two-year term. The Board of Medicine page confirms the two-year period ("Fifty (50) hours of CE every two (2) years") and states that the Board is "transitioning all professional licenses, certificates, and registrations to a birth-month renewal cycle": credentials issued on or after June 16, 2024 expire on the last day of the holder''s birth month. See requirement_conflicts -- the TERM is two years under both regimes, but the ANCHOR DATE differs.',
 'https://doh.dc.gov/sites/default/files/dc/sites/doh/publication/attachments/title_17_bomed_regs_05072012.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DC','MD','ce_hours_total', null, 50, null, null,
 'DC Health, Board of Medicine: physicians must complete "Fifty (50) hours of CE every two (2) years". 17 DCMR sec. 4614.2 states the same total as "fifty (50) American Medical Association Physician Recognition Award (AMA/PRA) Category I hours" during the two-year period before expiration.',
 'https://dchealth.dc.gov/bomed',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DC','MD','ce_cycle_months', null, 24, null, null,
 'DC Health, Board of Medicine: the fifty hours are required "every two (2) years", i.e. the CE cycle is the renewal cycle.',
 'https://dchealth.dc.gov/bomed',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DC','MD','ce_topic_lgbtq_cultural_competency_hours', null, 2, null, null,
 'DC Health, Board of Medicine: of the 50 hours, "two (2) hours in the subject of LGBTQ cultural competency" (D.C. Law 21-95, LGBTQ Cultural Competency Continuing Education Amendment Act).',
 'https://dchealth.dc.gov/bomed',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DC','MD','ce_topic_public_health_priority_hours', null, 5, null, null,
 'DC Health, Board of Medicine: of the 50 hours, "five (5) hours in a topic designated as a public health priority" by the Director of the Department of Health. The Board frames this as "at least 10% of their required total continuing education hours in topics identified by the Director ... as public health priorities".',
 'https://dchealth.dc.gov/bomed',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

-- =============================================================================
-- DISTRICT OF COLUMBIA -- advanced practice registered nurse (APRN)
-- DC Health, Board of Nursing. D.C. Code tit. 3 ch. 12; 17 DCMR ch. 54-59.
-- =============================================================================
('DC','APRN','renewal_cycle_months', null, 24, null, null,
 'DC Health, Board of Nursing licensee notice OS-26-03-05: "your license is set to expire on June 30, 2026" and continuing education "must be taken between July 1, 2024, and June 30, 2026" -- a two-year term. The 2024 RN/APRN Renewal FAQ records the prior cycle (renewal opened April 3, 2024, deadline June 30, 2024, "2026 expiration date"). Licences issued on or after June 16, 2024 move to a birth-month anchor; the TERM remains two years.',
 'https://dchealth.dc.gov/sites/default/files/dc/sites/doh/publication/attachments/OS-26-03-05%20(2a).pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DC','APRN','ce_hours_total', null, 24, null, null,
 'DC Health, Board of Nursing, FREQUENTLY ASKED QUESTIONS RN/APRN 2024 RENEWAL: APRNs must complete "Twenty-four (24) hours of CE". Confirmed by licensee notice OS-26-03-05 for the 2026 cycle ("Twenty-four (24) hours of CE").',
 'https://dchealth.dc.gov/sites/default/files/dc/sites/doh/service_content/attachments/FAQ_RN_APRN%202024Renewal.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DC','APRN','ce_cycle_months', null, 24, null, null,
 'DC Health, Board of Nursing licensee notice OS-26-03-05: "CEs must be taken between July 1, 2024, and June 30, 2026", i.e. a 24-month CE cycle matching the renewal cycle.',
 'https://dchealth.dc.gov/sites/default/files/dc/sites/doh/publication/attachments/OS-26-03-05%20(2a).pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DC','APRN','ce_topic_lgbtq_cultural_competency_hours', null, 2, null, null,
 'DC Health, Board of Nursing licensee notice OS-26-03-05 and the 2024 RN/APRN Renewal FAQ: of the 24 hours, "2 HOURS of LGBTQ" cultural competency.',
 'https://dchealth.dc.gov/sites/default/files/dc/sites/doh/publication/attachments/OS-26-03-05%20(2a).pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DC','APRN','ce_topic_public_health_priority_hours', null, 2.5, null, null,
 'DC Health, Board of Nursing licensee notice OS-26-03-05 (current 2024-2026 cycle): of the 24 hours, "2.5 hours must be in the public health priority topics". SUBJECT TO AN OPEN CONFLICT: the Board''s own 2024 Renewal FAQ states 3 hours for the same duty -- see requirement_conflicts.',
 'https://dchealth.dc.gov/sites/default/files/dc/sites/doh/publication/attachments/OS-26-03-05%20(2a).pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DC','APRN','ce_topic_pharmacotherapeutics_hours', null, 15, null, null,
 'DC Health, Board of Nursing licensee notice OS-26-03-05: APRNs must complete "Fifteen (15) hours in pharmacology". The 2024 Renewal FAQ states the same: APRNs need "Twenty-four (24) hours of CE, which must include 2 hours of LGBTQ, fifteen (15) hours in pharmacology, and 3 hours ... in the public health priority".',
 'https://dchealth.dc.gov/sites/default/files/dc/sites/doh/publication/attachments/OS-26-03-05%20(2a).pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DC','APRN','renewal_fee_cents', null, 26300, null, null,
 'DC Health, Board of Nursing licensee notice OS-26-03-05 (current cycle): "$263 for a Nurse Practitioner (APRN) License Renewal", plus a "$50" criminal background check and an "$85 late fee effective after license expiration date". SUBJECT TO AN OPEN CONFLICT: the Board''s 2024 Renewal FAQ published an APRN renewal application fee of $118 -- see requirement_conflicts.',
 'https://dchealth.dc.gov/sites/default/files/dc/sites/doh/publication/attachments/OS-26-03-05%20(2a).pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

-- =============================================================================
-- DELAWARE -- physician (MD)
-- Board of Medical Licensure and Discipline, Division of Professional
-- Regulation. 24 Del. C. ch. 17; 24 DE Admin. Code 1700.
-- DELAWARE OPERATES A LIVE STATE CONTROLLED SUBSTANCE REGISTRATION on a clock
-- that does NOT align with the medical licence.
-- =============================================================================
('DE','MD','renewal_cycle_months', null, 24, null, null,
 'Delaware Division of Professional Regulation, Board of Medical Licensure and Discipline - License Renewal: "Physician M.D & D.O., Physician Assistant, Administrative Medical, Acupuncture Practitioner, Eastern Medicine Practitioners, and Telehealth Registration (MD, DO, PA, Other) licenses expire on March 31 of odd-numbered years (2019, 2021, etc.)"; physicians renew every two years.',
 'https://dpr.delaware.gov/boards/medicalpractice/renewal/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DE','MD','ce_hours_total', null, 40, null, null,
 'Delaware Division of Professional Regulation, Board of Medical Licensure and Discipline - Continuing Education and Audit Information: "Active Physician''s must complete 40 hours of approved CME during each full licensure renewal period" (AMA or AOA approved).',
 'https://dpr.delaware.gov/boards/medicalpractice/continuing-education-and-audit-information/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DE','MD','ce_cycle_months', null, 24, null, null,
 'Delaware Division of Professional Regulation, Board of Medical Licensure and Discipline - Continuing Education and Audit Information: the licensure renewal period runs "between April 1 and March 31 odd-numbered years (2019-2021, etc.)", i.e. 24 months, and the CE cycle is that period.',
 'https://dpr.delaware.gov/boards/medicalpractice/continuing-education-and-audit-information/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DE','MD','initial_license_fee_cents', null, 44000, null, null,
 'Delaware Division of Professional Regulation, Board of Medical Licensure and Discipline - Fee Schedule: "Physician - MD" application fee "$440". The Division does not publish the renewal fee ("You are notified of the amount of the renewal fee at the time of renewal").',
 'https://dpr.delaware.gov/boards/medicalpractice/fees/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DE','MD','csr_required', null, null, true, null,
 'Delaware Division of Professional Regulation, Controlled Substances Registration - Practitioners: "You must have both a Delaware CSR and DEA registration for Delaware before you prescribe controlled substances in Delaware."',
 'https://dpr.delaware.gov/boards/controlledsubstances/practitioner_csr/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DE','MD','csr_renewal_cycle_months', null, 24, null, null,
 'Delaware Division of Professional Regulation, Controlled Substances - License Renewal: "Controlled Substance registrations expire on June 30 of odd years" and must be renewed "every two years before the expiration date". THE CSR CLOCK (June 30, odd years) IS THREE MONTHS OFFSET FROM THE MEDICAL LICENCE CLOCK (March 31, odd years); an obligation generator that folds them together will produce wrong dates.',
 'https://dpr.delaware.gov/boards/controlledsubstances/renewal/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DE','MD','csr_fee_cents', null, 21000, null, null,
 'Delaware Division of Professional Regulation, Controlled Substances - Fee Schedule: physician controlled substance registration application fee "$210". THE DIVISION DOES NOT PUBLISH THE CSR RENEWAL FEE ("You are notified of the amount of the renewal fee at the time of renewal"), so the seeded figure is the APPLICATION fee -- see requirement_conflicts before using it as a renewal cost.',
 'https://dpr.delaware.gov/boards/controlledsubstances/fees/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DE','MD','ce_topic_controlled_substance_hours', null, null, null,
 '{"hours": 2, "periodicity": "per_csr_renewal_cycle", "csr_renewal_cycle_months": 24, "applies_to": "holders of an active Delaware controlled substance registration", "plus_one_time": {"hours": 1, "trigger": "on application for a Delaware CSR", "course": "Mandatory Course on Delaware law, regulation and programs on prescribing and distribution of controlled substances", "note": "the Mandatory Course is no longer accepted as continuing education credit"}}'::jsonb,
 'Delaware Division of Professional Regulation, Controlled Substances - Mandatory Course: "All ACTIVE Controlled Substance Registrations upon renewal every two years are asked to attest to completing TWO hours of continuing education (CE) in the areas of controlled substance prescribing practices, treatment of chronic pain, or other topics related to prescribing controlled substances", and separately "All practitioners who are APPLYING for a Delaware controlled substance registration (CSR) must complete a mandatory ONE-hour, two-part course". This duty hangs on the CSR clock, not on the medical licence clock, and applies only to CSR holders -- hence value_json.',
 'https://dpr.delaware.gov/boards/controlledsubstances/mandatory_course/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

-- =============================================================================
-- DELAWARE -- advanced practice registered nurse (APRN)
-- Delaware Board of Nursing. 24 Del. C. ch. 19; 24 DE Admin. Code 1900.
-- =============================================================================
('DE','APRN','renewal_cycle_months', null, 24, null, null,
 '24 Del. C. ch. 19 (Delaware Board of Nursing): "The advanced practice registered nurses'' licensure or prescriptive authority is subject to biennial renewal coinciding with RN license renewal." The Board''s License Renewal page states APRN licences "expire on the same date as your Delaware RN license. If you do not hold a Delaware RN license, your APRN license expires on September 30 of odd years."',
 'https://delcode.delaware.gov/title24/c019/index.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DE','APRN','ce_hours_total', null, 30, null, null,
 'Delaware Division of Professional Regulation, Board of Nursing - Continuing Education and Audit Information: "30 contact hours during your renewal period". This is the nursing CE requirement attaching to the licence an APRN renews.',
 'https://dpr.delaware.gov/boards/nursing/continuing-education-and-audit-information/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DE','APRN','ce_cycle_months', null, 24, null, null,
 'Delaware Division of Professional Regulation, Board of Nursing: the renewal period runs March 1 to February 28, June 1 to May 31, or October 1 to September 30 of odd-numbered years -- a 24-month period -- and the 30 contact hours are earned "during your renewal period".',
 'https://dpr.delaware.gov/boards/nursing/continuing-education-and-audit-information/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DE','APRN','ce_topic_substance_abuse_hours', null, 3, null, null,
 'Delaware Division of Professional Regulation, Board of Nursing - Continuing Education and Audit Information: "At least 3 of these contact hours must be in the area of substance abuse", within the 30-hour total.',
 'https://dpr.delaware.gov/boards/nursing/continuing-education-and-audit-information/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DE','APRN','ce_topic_abuse_and_trafficking_recognition_hours', null, 1, null, null,
 'Delaware Division of Professional Regulation, Board of Nursing - Continuing Education and Audit Information: "at least one hour on the recognition of and response to suspected or known sexual abuse, physical abuse, exploitation, trafficking, or domestic violence", within the 30-hour total. Seeded under a combined key because Delaware mandates ONE course covering all five topics; splitting it across the human_trafficking and domestic_violence keys would double-count the hour.',
 'https://dpr.delaware.gov/boards/nursing/continuing-education-and-audit-information/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DE','APRN','initial_license_fee_cents', null, 18100, null, null,
 'Delaware Division of Professional Regulation, Board of Nursing - Fee Schedule: "Advanced Practice Registered Nurse (All Types) | $181" application fee ("Registered Nurse | $181" for the underlying RN licence; APRN reinstatement $272). The Division does not publish the renewal fee.',
 'https://dpr.delaware.gov/boards/nursing/fees/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DE','APRN','csr_required', null, null, true, null,
 'Delaware Division of Professional Regulation, Controlled Substances Registration - Advanced Practice Registered Nurse: "You need a Delaware CSR to prescribe or to store/dispense controlled substances in Delaware." A CSR or DEA registration held in another jurisdiction does not substitute.',
 'https://dpr.delaware.gov/boards/controlledsubstances/apn_csr/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DE','APRN','csr_renewal_cycle_months', null, 24, null, null,
 'Delaware Division of Professional Regulation, Controlled Substances - License Renewal: "Controlled Substance registrations expire on June 30 of odd years" and must be renewed "every two years before the expiration date". This does NOT align with the Delaware APRN/RN renewal anchor (February 28, May 31 or September 30 of odd years).',
 'https://dpr.delaware.gov/boards/controlledsubstances/renewal/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DE','APRN','csr_fee_cents', null, 21000, null, null,
 'Delaware Division of Professional Regulation, Controlled Substances - Fee Schedule: Advanced Practice Registered Nurse controlled substance registration application fee "$210". THE DIVISION DOES NOT PUBLISH THE CSR RENEWAL FEE; the seeded figure is the APPLICATION fee -- see requirement_conflicts.',
 'https://dpr.delaware.gov/boards/controlledsubstances/fees/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('DE','APRN','ce_topic_controlled_substance_hours', null, null, null,
 '{"hours": 2, "periodicity": "per_csr_renewal_cycle", "csr_renewal_cycle_months": 24, "applies_to": "holders of an active Delaware controlled substance registration", "plus_one_time": {"hours": 1, "trigger": "on application for a Delaware CSR", "course": "Mandatory Course on Delaware law, regulation and programs on prescribing and distribution of controlled substances"}}'::jsonb,
 'Delaware Division of Professional Regulation, Controlled Substances - Mandatory Course: "All ACTIVE Controlled Substance Registrations upon renewal every two years are asked to attest to completing TWO hours of continuing education (CE) in the areas of controlled substance prescribing practices, treatment of chronic pain, or other topics related to prescribing controlled substances"; applicants must first "Complete the one-hour Mandatory Course training on Delaware law, regulation and programs on prescribing and distribution of controlled substances" (stated on the APRN CSR page). Hangs on the CSR clock and applies only to CSR holders -- hence value_json.',
 'https://dpr.delaware.gov/boards/controlledsubstances/mandatory_course/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

-- =============================================================================
-- RHODE ISLAND -- physician (MD)
-- RI Department of Health, Board of Medical Licensure and Discipline.
-- R.I. Gen. Laws ch. 5-37; 216-RICR-40-05-1.
-- =============================================================================
('RI','MD','renewal_cycle_months', null, 24, null, null,
 'Rhode Island Department of Health, Physician Application Requirements: "Physician licenses are two-year licenses and renewed on June 30th of every even-numbered year." 216-RICR-40-05-1 states licences expire "biennially on the first (1st) day of July of the next even-numbered year".',
 'https://health.ri.gov/sites/g/files/xkgbur1006/files/publications/requirements/PhysicianApplicationRequirements.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('RI','MD','ce_hours_total', null, 40, null, null,
 '216-RICR-40-05-1 (Licensure and Discipline of Physicians), Rhode Island Department of State: "Every physician licensed to practice allopathic or osteopathic medicine in Rhode Island under the provisions of the Act and this Part, shall on or before the first (1st) day of June of every even-numbered year, on a biennial basis, earn a minimum of forty (40) hours of AMA PRA Category 1 Credit(TM)/AOA Category 1a continuing medical education credits". Participation in an ABMS Maintenance of Certification program is treated as equivalent.',
 'https://rules.sos.ri.gov/regulations/part/216-40-05-1',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('RI','MD','ce_cycle_months', null, 24, null, null,
 '216-RICR-40-05-1: the forty hours are earned "on a biennial basis" on or before June 1 of every even-numbered year, i.e. the CE cycle is the renewal cycle.',
 'https://rules.sos.ri.gov/regulations/part/216-40-05-1',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('RI','MD','initial_license_fee_cents', null, 109000, null, null,
 'Rhode Island Department of Health, Physician Application Requirements: "The fee for a full medical license is $1090.00 (or $1290.00 if you are also applying for a Controlled Substance Registration (CSR))." Confirmed by 216-RICR-10-05-2 (Fee Structure), Physician - Allopathic initial application "$1,090.00".',
 'https://health.ri.gov/sites/g/files/xkgbur1006/files/publications/requirements/PhysicianApplicationRequirements.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('RI','MD','renewal_fee_cents', null, 109000, null, null,
 '216-RICR-10-05-2 (Fee Structure for Licensing, Laboratory and Administrative Services Provided by the Department of Health): Physician - Allopathic renewal "$1,090.00".',
 'https://rules.sos.ri.gov/regulations/part/216-10-05-2',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('RI','MD','csr_required', null, null, true, null,
 'Rhode Island Department of Health, Rhode Island Uniform Controlled Substances Act Registration (CSR) application: "Licensed drug facilities and licensed practitioners with prescriptive privileges cannot dispense, possess, store or ship controlled substances in or into the State of Rhode Island without a valid drug facility or professional license, Rhode Island Controlled Substances Registration (CSR), and a federal Drug Enforcement Administration (DEA) Registration."',
 'https://health.ri.gov/sites/g/files/xkgbur1006/files/applications/ControlledSubstances.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('RI','MD','csr_renewal_cycle_months', null, 24, null, null,
 'Rhode Island Department of Health, CSR application: "The CSR is renewed at the same time as the professional or facility license is renewed." The Rhode Island physician licence is a two-year licence renewed June 30 of every even-numbered year (Physician Application Requirements), so the CSR runs on the same 24-month clock.',
 'https://health.ri.gov/sites/g/files/xkgbur1006/files/applications/ControlledSubstances.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('RI','MD','csr_fee_cents', null, 20000, null, null,
 'Rhode Island Department of Health, CSR application: "PRACTITIONER FEE - $200.00". Consistent with the Physician Application Requirements, which state the combined licence-plus-CSR application is $1,290.00 against $1,090.00 for the licence alone.',
 'https://health.ri.gov/sites/g/files/xkgbur1006/files/applications/ControlledSubstances.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

-- =============================================================================
-- RHODE ISLAND -- advanced practice registered nurse (APRN)
-- RI Department of Health, Board of Nurse Registration and Nursing Education.
-- R.I. Gen. Laws ch. 5-34 and 5-34.2; 216-RICR-40-05-3.
-- =============================================================================
('RI','APRN','renewal_cycle_months', null, 24, null, null,
 '216-RICR-40-05-3 (Licensing of Nurses ...), Rhode Island Department of State: a nursing licence "shall expire on the first (1st) day of March of every other year following the date of issuance of the original license". Renewal notices are sent on or before January 1 and applications are due by February 15.',
 'https://rules.sos.ri.gov/regulations/part/216-40-05-3',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('RI','APRN','ce_hours_total', null, 10, null, null,
 '216-RICR-40-05-3: "Every person seeking renewal of a license under the provisions of the Act and this Part, shall provide satisfactory evidence to the Department that in the preceding two years the practitioner (i.e., licensee) has completed the ten (10) required continuing education hours." Confirmed on the RI Department of Health Nurses page: "Nurses seeking to renew a nursing license must complete 10 continuing education hours during every two year licensing cycle".',
 'https://rules.sos.ri.gov/regulations/part/216-40-05-3',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('RI','APRN','ce_cycle_months', null, 24, null, null,
 '216-RICR-40-05-3: the ten hours are counted "in the preceding two years", i.e. the CE cycle is the renewal cycle.',
 'https://rules.sos.ri.gov/regulations/part/216-40-05-3',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('RI','APRN','ce_topic_substance_abuse_hours', null, 2, null, null,
 'Rhode Island Department of Health, Nurses - Licensing: "Nurses seeking to renew a nursing license must complete 10 continuing education hours during every two year licensing cycle, two of those hours must be about substance abuse."',
 'https://health.ri.gov/licensing/nurses',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('RI','APRN','collaborative_agreement_required', null, null, false, null,
 '216-RICR-40-05-3: "''Collaboration'' means an independent working relationship between an Advanced Practice Registered Nurse and other licensed health care professionals, including but not limited to, physicians, pharmacists, podiatrists, dentists and nurses, but does not require such relationship to be evidenced by a written collaboration agreement, to be with a specific designated physician, or for services to be performed at the same physical location as any collaborating licensed health care practitioner." This is an AFFIRMATIVE statement that no written agreement is required, not an inference from silence.',
 'https://rules.sos.ri.gov/regulations/part/216-40-05-3',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('RI','APRN','initial_license_fee_cents', null, 14500, null, null,
 '216-RICR-10-05-2 (Fee Structure ...): Advanced Practice Registered Nurse initial application "$145.00". The underlying RN licence is a separate "$135.00".',
 'https://rules.sos.ri.gov/regulations/part/216-10-05-2',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('RI','APRN','renewal_fee_cents', null, 14500, null, null,
 '216-RICR-10-05-2 (Fee Structure ...): Advanced Practice Registered Nurse renewal "$145.00". The underlying RN licence renewal is a separate "$135.00".',
 'https://rules.sos.ri.gov/regulations/part/216-10-05-2',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('RI','APRN','csr_required', null, null, true, null,
 'Rhode Island Department of Health, Rhode Island Uniform Controlled Substances Act Registration (CSR) application: "licensed practitioners with prescriptive privileges cannot dispense, possess, store or ship controlled substances in or into the State of Rhode Island without a valid ... professional license, Rhode Island Controlled Substances Registration (CSR), and a federal Drug Enforcement Administration (DEA) Registration." A Rhode Island APRN holds prescriptive privileges under R.I. Gen. Laws ch. 5-34.2.',
 'https://health.ri.gov/sites/g/files/xkgbur1006/files/applications/ControlledSubstances.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('RI','APRN','csr_renewal_cycle_months', null, 24, null, null,
 'Rhode Island Department of Health, CSR application: "The CSR is renewed at the same time as the professional or facility license is renewed." The Rhode Island nursing licence expires "on the first (1st) day of March of every other year" (216-RICR-40-05-3), so the CSR runs on the same 24-month clock.',
 'https://health.ri.gov/sites/g/files/xkgbur1006/files/applications/ControlledSubstances.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('RI','APRN','csr_fee_cents', null, 20000, null, null,
 'Rhode Island Department of Health, CSR application: "PRACTITIONER FEE - $200.00".',
 'https://health.ri.gov/sites/g/files/xkgbur1006/files/applications/ControlledSubstances.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

-- =============================================================================
-- NEW HAMPSHIRE -- physician (MD)
-- NH Board of Medicine / Office of Professional Licensure and Certification.
-- RSA 329; N.H. Admin. R. Med and Plc.
-- =============================================================================
('NH','MD','renewal_cycle_months', null, 24, null, null,
 'RSA 329:16-g, as published by the New Hampshire General Court: the CME requirement is tied to "biennial license renewal" and runs over "the preceding 2 years". N.H. Admin. R. Plc 1002.28 lists the unrestricted permanent physician licence with a "2 year" licence duration for "Initial, renewal, or reinstatement after expiration of license".',
 'https://www.gc.nh.gov/rsa/html/XXX/329/329-mrg.htm',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('NH','MD','ce_hours_total', null, 100, null, null,
 'RSA 329:16-g: a physician must complete "100 hours of approved continuing medical education program within the preceding 2 years", from programs "certified by a national, state, or county medical society or college or university".',
 'https://www.gc.nh.gov/rsa/html/XXX/329/329-mrg.htm',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('NH','MD','ce_cycle_months', null, 24, null, null,
 'RSA 329:16-g: the 100 hours are earned "within the preceding 2 years" and are reported at biennial licence renewal, i.e. the CE cycle is the renewal cycle.',
 'https://www.gc.nh.gov/rsa/html/XXX/329/329-mrg.htm',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('NH','MD','initial_license_fee_cents', null, 37800, null, null,
 'New Hampshire Office of Professional Licensure and Certification, Board of Medicine License Fees: physician initial licence fee "$378.00", including the mandatory $28.00 Professional Health Program (PHP) fee. SUBJECT TO AN OPEN CONFLICT: N.H. Admin. R. Plc 1002.28 states "$385" for the same licence -- see requirement_conflicts.',
 'https://www.oplc.nh.gov/board-medicine-license-fees',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('NH','MD','renewal_fee_cents', null, 37800, null, null,
 'New Hampshire Office of Professional Licensure and Certification, Board of Medicine License Fees: physician biennial renewal fee "$378.00", including the mandatory $28.00 Professional Health Program (PHP) fee. SUBJECT TO AN OPEN CONFLICT: N.H. Admin. R. Plc 1002.28 states "$385" -- see requirement_conflicts.',
 'https://www.oplc.nh.gov/board-medicine-license-fees',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

-- =============================================================================
-- NEW HAMPSHIRE -- advanced practice registered nurse (APRN)
-- NH Board of Nursing / OPLC. RSA 326-B; N.H. Admin. R. Nur and Plc.
-- =============================================================================
('NH','APRN','renewal_cycle_months', null, 24, null, null,
 'RSA 326-B:22, I (Nurse Practice Act), as published by the New Hampshire General Court: "All license renewals shall be issued every 2 years in accordance with RSA 310:8." N.H. Admin. R. Plc 1002.33 lists the APRN licence with a "2 year" duration.',
 'https://gc.nh.gov/rsa/html/xxx/326-b/326-b-mrg.htm',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('NH','APRN','ce_hours_total', null, 30, null, null,
 'RSA 326-B:31, III: "An APRN, in addition to the continuing education requirements to renew or reinstate a license as an RN, shall complete 30 hours of continuing education every 2 years, 20 hours of which shall be specific to the specialty for which renewal or reinstatement is sought, and 5 hours of which shall be training in pharmacology appropriate to the specialty". NOTE: these 30 hours are IN ADDITION TO the RN continuing education requirement.',
 'https://gc.nh.gov/rsa/html/xxx/326-b/326-b-mrg.htm',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('NH','APRN','ce_cycle_months', null, 24, null, null,
 'RSA 326-B:31, III: the 30 hours are required "every 2 years", i.e. the CE cycle is the renewal cycle.',
 'https://gc.nh.gov/rsa/html/xxx/326-b/326-b-mrg.htm',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('NH','APRN','ce_topic_pharmacotherapeutics_hours', null, 5, null, null,
 'RSA 326-B:31, III: of the 30 APRN hours, "5 hours of which shall be training in pharmacology appropriate to the specialty for which license renewal or reinstatement is sought".',
 'https://gc.nh.gov/rsa/html/xxx/326-b/326-b-mrg.htm',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('NH','APRN','initial_license_fee_cents', null, 11000, null, null,
 'N.H. Admin. R. Plc 1002.33 (Board of Nursing fees), as published by the New Hampshire General Court: "Initial, renewal, or reinstatement after expiration of license" for an APRN licence is "$110" for a 2-year licence duration (RN/LPN licences are "$88"). The OPLC Board of Nursing License Fees web page returned HTTP 403 to every automated fetch on 2026-09-18 and could not be used to confirm -- see requirement_conflicts.',
 'https://gc.nh.gov/rules/state_agencies/plc1000.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('NH','APRN','renewal_fee_cents', null, 11000, null, null,
 'N.H. Admin. R. Plc 1002.33: "Initial, renewal, or reinstatement after expiration of license" for an APRN licence is "$110", 2-year duration. The OPLC fee web page could not be retrieved to confirm -- see requirement_conflicts.',
 'https://gc.nh.gov/rules/state_agencies/plc1000.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

-- =============================================================================
-- VERMONT -- physician (MD)
-- Vermont Board of Medical Practice, Department of Health. 26 V.S.A. ch. 23.
-- =============================================================================
('VT','MD','renewal_cycle_months', null, 24, null, null,
 'Vermont Department of Health, Board of Medical Practice - Applications, Licensing and Fees: MDs renew biennially, with licences expiring "November 30th of Even Years". The Board''s CME Hour Requirements FAQ refers throughout to "two-year license periods".',
 'https://www.healthvermont.gov/systems/board-medical-practice/applications-licensing-and-fees',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('VT','MD','ce_hours_total', null, 30, null, null,
 'Vermont Board of Medical Practice, CME Hour Requirements FAQ (29 August 2024): "30 hours of AMA PRA Category 1(TM)" for a physician who has held the licence for two full years. Physicians licensed less than one year owe no CME at first renewal; those licensed one to two years owe 15 hours including the mandatory topics -- see requirement_conflicts.',
 'https://www.healthvermont.gov/sites/default/files/document/BMP_Licensing_CMEHOURREQUIREMENTSFAQ_08292024.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('VT','MD','ce_cycle_months', null, 24, null, null,
 'Vermont Board of Medical Practice, CME Hour Requirements FAQ: the 30 hours are earned over the two-year licence period, i.e. the CE cycle is the renewal cycle.',
 'https://www.healthvermont.gov/sites/default/files/document/BMP_Licensing_CMEHOURREQUIREMENTSFAQ_08292024.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('VT','MD','ce_topic_controlled_substance_hours', null, null, null,
 '{"hours": 2, "periodicity": "per_renewal_cycle", "applies_to": "licensees who have or have applied for a DEA registration"}'::jsonb,
 'Vermont Board of Medical Practice, CME Hour Requirements FAQ: controlled substances "2 credits required only for licensees who have or have applied for DEA registration". Conditional on DEA registration, hence value_json.',
 'https://www.healthvermont.gov/sites/default/files/document/BMP_Licensing_CMEHOURREQUIREMENTSFAQ_08292024.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('VT','MD','ce_topic_end_of_life_care_hours', null, 1, null, null,
 'Vermont Board of Medical Practice, CME Hour Requirements FAQ: "1 credit required for all licensees" covering "hospice/palliative care/end-of-life care/pain management". Required of every licensee every cycle, hence value_num.',
 'https://www.healthvermont.gov/sites/default/files/document/BMP_Licensing_CMEHOURREQUIREMENTSFAQ_08292024.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('VT','MD','initial_license_fee_cents', null, 65000, null, null,
 'Vermont Department of Health, Board of Medical Practice - Applications, Licensing and Fees: MD initial licence fee "$650.00".',
 'https://www.healthvermont.gov/systems/board-medical-practice/applications-licensing-and-fees',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('VT','MD','renewal_fee_cents', null, 52500, null, null,
 'Vermont Department of Health, Board of Medical Practice - Applications, Licensing and Fees: MD biennial renewal fee "$525.00".',
 'https://www.healthvermont.gov/systems/board-medical-practice/applications-licensing-and-fees',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

-- =============================================================================
-- VERMONT -- advanced practice registered nurse (APRN)
-- Vermont Board of Nursing, Office of Professional Regulation, Secretary of
-- State. 26 V.S.A. ch. 28; Administrative Rules of the Board of Nursing.
-- =============================================================================
('VT','APRN','renewal_cycle_months', null, 24, null, null,
 'Administrative Rules of the Vermont Board of Nursing, Rule 4-3: "Licenses are valid for fixed, two-year periods. Expiration dates are printed on licenses."',
 'https://outside.vermont.gov/dept/sos/office_professional_regulation/professions/nursing/nursing_administrative_rules.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('VT','APRN','renewal_window_days', null, 42, null, null,
 'Vermont Secretary of State, Office of Professional Regulation, Nursing Applications and Renewals: "Renewal applications open 6 weeks prior to the expiration", i.e. 42 days. This is a transactional open date, not a notification date.',
 'https://sos.vermont.gov/nursing/apply-renew',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('VT','APRN','ce_hours_total', null, 20, null, null,
 'Administrative Rules of the Vermont Board of Nursing, Rule 4-8(a): "20 hours of qualifying continuing education in the two years immediately preceding the application". This attaches to the nursing licence an APRN renews; Rule 4-8(c) adds a separate 4-hour medication administration requirement for APRNs.',
 'https://outside.vermont.gov/dept/sos/office_professional_regulation/professions/nursing/nursing_administrative_rules.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('VT','APRN','ce_cycle_months', null, 24, null, null,
 'Administrative Rules of the Vermont Board of Nursing, Rule 4-8(a): the 20 hours are earned "in the two years immediately preceding the application", i.e. the CE cycle is the renewal cycle.',
 'https://outside.vermont.gov/dept/sos/office_professional_regulation/professions/nursing/nursing_administrative_rules.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('VT','APRN','ce_topic_medication_administration_hours', null, 4, null, null,
 'Administrative Rules of the Vermont Board of Nursing, Rule 4-8(c): an APRN must "have completed 4 hours qualifying continuing education specific to medication administration" as part of renewal.',
 'https://outside.vermont.gov/dept/sos/office_professional_regulation/professions/nursing/nursing_administrative_rules.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('VT','APRN','collaborative_agreement_required', null, null, null,
 '{"required": true, "until_months": 24, "until_hours": 2400, "instrument": "formal agreement with a collaborating provider", "after_threshold": "no collaborating provider agreement required", "scope": "an initial APRN role"}'::jsonb,
 'Administrative Rules of the Vermont Board of Nursing, Rule 9-8(a): "An APRN with fewer than 24 months and 2,400 hours of licensed active advanced nursing practice in an initial role ... shall have a formal agreement with a collaborating provider." 26 V.S.A. sec. 1614 requires an APRN renewal application to include "a current collaborative provider agreement if required for transition to practice". Conditional on a transition-to-practice threshold, so a plain boolean would be wrong for most of the population -- hence value_json.',
 'https://outside.vermont.gov/dept/sos/office_professional_regulation/professions/nursing/nursing_administrative_rules.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('VT','APRN','initial_license_fee_cents', null, 11500, null, null,
 '26 V.S.A. sec. 1577 (Fees), Vermont Statutes Online: advanced practice registered nurse initial endorsement "$115.00". The underlying RN licence is a separate fee ($75.00 by examination, $175.00 by endorsement).',
 'https://legislature.vermont.gov/statutes/section/26/028/01577',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('VT','APRN','renewal_fee_cents', null, 14500, null, null,
 '26 V.S.A. sec. 1577 (Fees): advanced practice registered nurse biennial renewal "$145.00". The underlying RN biennial renewal is a separate "$220.00".',
 'https://legislature.vermont.gov/statutes/section/26/028/01577',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

-- =============================================================================
-- MAINE -- physician (MD)
-- Maine Board of Licensure in Medicine. 32 M.R.S. ch. 48; 02-373 CMR.
-- =============================================================================
('ME','MD','renewal_cycle_months', null, 24, null, null,
 'Maine Board of Licensure in Medicine, License FAQ: "licenses are issued for a two-year period" and expire "on the last day of the month of their birth in an even-numbered year" or odd-numbered year depending on birth year. The Board''s MD License page states "Licenses must be renewed every two years."',
 'https://www.maine.gov/md/licensure/license-faq',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('ME','MD','ce_hours_total', null, 40, null, null,
 'Maine Board of Licensure in Medicine, License FAQ: physicians must complete "40 hours of Category 1 CME, including 3 hours of CME regarding opioid prescribing, during each renewal cycle". "Applicants for initial licensure do not need to submit proof of CME."',
 'https://www.maine.gov/md/licensure/license-faq',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('ME','MD','ce_cycle_months', null, 24, null, null,
 'Maine Board of Licensure in Medicine, License FAQ: the 40 hours are required "during each renewal cycle" and "This requirement applies every two years during the renewal period", i.e. the CE cycle is the renewal cycle.',
 'https://www.maine.gov/md/licensure/license-faq',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('ME','MD','ce_topic_opioid_hours', null, 3, null, null,
 'Maine Board of Licensure in Medicine, License FAQ: the 40 hours must include "3 hours of CME regarding opioid prescribing", each renewal cycle. Stated without a prescriber condition, hence value_num.',
 'https://www.maine.gov/md/licensure/license-faq',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('ME','MD','initial_license_fee_cents', null, 70000, null, null,
 'Maine Board of Licensure in Medicine, MD License: "$600" application fee plus "$100" examination fee, totalling "$700". See requirement_conflicts for the composition caveat.',
 'https://www.maine.gov/md/licensure/md-license',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('ME','MD','renewal_fee_cents', null, 50000, null, null,
 'Maine Board of Licensure in Medicine, License FAQ: the standard biennial renewal fee is "$500"; "Individuals who are issued an initial license that expires less than six (6) months following its issuance pay only a pro-rated renewal fee of $150."',
 'https://www.maine.gov/md/licensure/license-faq',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

-- =============================================================================
-- MAINE -- advanced practice registered nurse (APRN)
-- Maine State Board of Nursing. 32 M.R.S. ch. 31; 02-380 CMR ch. 8.
-- =============================================================================
('ME','APRN','renewal_cycle_months', null, 24, null, null,
 '32 M.R.S. sec. 2206 (Renewals), Maine Legislature: "The license of every registered nurse licensed under this chapter is renewable every 2 years", expiring "on the anniversary of the applicant''s birth". 02-380 CMR ch. 8 requires that "Request for continuing approval must be made concurrently with renewal of the registered nurse license."',
 'https://legislature.maine.gov/statutes/32/title32sec2206.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('ME','APRN','ce_hours_total', null, 50, null, null,
 '02-380 CMR ch. 8 (Regulations Relating to Advanced Practice Registered Nursing), Maine State Board of Nursing: a minimum of "50 contact hours of continuing education in nursing, medicine or allied health" during the 2-year licensure period, of which "30 contact hours must be in Category I" and "No more than 20 contact hours may be in Category II". Confirmed on the Board''s APRN FAQ: "An APRN seeking renewal of license(s) to practice must have completed during the 2 year period a minimum of 50 CEUs in nursing, medicine or allied health in the area of practice for which the individual has been licensed as an APRN."',
 'https://www.maine.gov/boardofnursing/sites/boardofnursing/files/2026-06/Chapter%208%20Regulations%20Relating%20Advanced%20Practice%20Registered%20Nursing%20final%20rule.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('ME','APRN','ce_cycle_months', null, 24, null, null,
 '02-380 CMR ch. 8: the 50 contact hours are earned "during the 2 year licensure period", i.e. the CE cycle is the renewal cycle.',
 'https://www.maine.gov/boardofnursing/sites/boardofnursing/files/2026-06/Chapter%208%20Regulations%20Relating%20Advanced%20Practice%20Registered%20Nursing%20final%20rule.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('ME','APRN','ce_topic_opioid_hours', null, null, null,
 '{"hours": 3, "periodicity": "per_renewal_cycle", "applies_to": "APRNs with prescriptive authority", "category": "Category I"}'::jsonb,
 '02-380 CMR ch. 8: "3 contact hours of Category I continuing education on the prescribing of opioid medication", required by December 31, 2017 and thereafter, of APRNs holding prescriptive authority. Conditional on prescriptive authority, hence value_json.',
 'https://www.maine.gov/boardofnursing/sites/boardofnursing/files/2026-06/Chapter%208%20Regulations%20Relating%20Advanced%20Practice%20Registered%20Nursing%20final%20rule.pdf',
 '2017-12-31', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('ME','APRN','ce_topic_pharmacotherapeutics_hours', null, null, null,
 '{"hours": 15, "periodicity": "per_renewal_cycle", "applies_to": "a nurse practitioner or certified nurse midwife who does NOT prescribe", "note": "inverted condition -- this duty falls on NON-prescribers; prescribers owe the 3-hour opioid requirement instead"}'::jsonb,
 'Maine State Board of Nursing, Advanced Practice Registered Nurse FAQs: "If a NP or CNM does not prescribe they must submit documentation of 15 contact hours of continuing education in pharmacology every two years when they renew their license to practice." Applies only to non-prescribing APRNs -- the opposite subset from most states'' pharmacology mandates -- hence value_json.',
 'https://www11.maine.gov/boardofnursing/licensing/advanced-practice-rn/faq.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('ME','APRN','supervision_required', null, null, null,
 '{"required": true, "until_months": 24, "supervisor": ["licensed physician", "supervising nurse practitioner"], "alternative": "employment by a clinic or hospital that has a medical director", "after_threshold": "independent practice", "attestation": "the supervising physician or nurse practitioner submits documentation of completion of the supervision requirement to the Board"}'::jsonb,
 '02-380 CMR ch. 8: "A nurse practitioner must practice for a minimum of 24 months under the supervision of a licensed physician, or a supervising nurse practitioner, or must be employed by a clinic or hospital that has a medical director." Maine State Board of Nursing APRN FAQs: "When a NP completes 24 months of full time physician or nurse practitioner supervision he/she must ensure that his/her supervising physician or nurse practitioner submits documentation of completion of the supervision requirement to the board." Conditional on a 24-month threshold, so a plain boolean would be wrong for the established majority -- hence value_json.',
 'https://www.maine.gov/boardofnursing/sites/boardofnursing/files/2026-06/Chapter%208%20Regulations%20Relating%20Advanced%20Practice%20Registered%20Nursing%20final%20rule.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('ME','APRN','initial_license_fee_cents', null, 10000, null, null,
 'Maine State Board of Nursing, Fees: "APRN Licensure | $100". The underlying RN licence is a separate "$75" (RN Exam / RN Endorsement).',
 'https://www.maine.gov/boardofnursing/board-information/fees.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true),

('ME','APRN','renewal_fee_cents', null, 10000, null, null,
 'Maine State Board of Nursing, Fees: "APRN Renewal | $100". The underlying RN renewal is a separate "$75". 32 M.R.S. sec. 2206 caps the board-set renewal fee at "not to exceed $100".',
 'https://www.maine.gov/boardofnursing/board-information/fees.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, true);

commit;
