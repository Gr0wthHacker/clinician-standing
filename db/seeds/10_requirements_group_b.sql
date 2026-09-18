-- =============================================================================
-- requirements_seed_group_b.sql -- the rules asset, group B jurisdictions.
--
-- MI, NC, VA, SC, TN, AL, MS, KY (complete) plus LA and WV (partial)
--   x { physician (MD), nurse practitioner (APRN) }.
-- AR and OK WERE NOT REACHED -- see COVERAGE.md and the conflicts file.
--
-- VERIFICATION STANDARD (read db/seeds/README.md before editing):
--   Every row below carries a citation to a state board page, a state statute,
--   or a board rule that was FETCHED AND READ on 2026-09-18. No row is written
--   from recall, from a CE aggregator, or from inference. Where a value could
--   not be verified from a primary source it is NOT in this file -- it is in
--   requirement_conflicts_seed_group_b.sql as an open conflict. An open conflict
--   blocks auto-clear (PRD 8.1 condition 6) and raises RULE_UNCERTAIN (PRD 8.3),
--   which is the correct behaviour for a value we do not know.
--
-- VALUE COLUMN CONVENTION
--   value_num   a plain per-cycle quantity (months, days, hours, cents).
--   value_bool  a plain yes/no.
--   value_json  a quantity that is NOT simply "this much, every cycle" --
--               one-time requirements, requirements on a different clock than
--               the renewal cycle, and requirements that apply only to a subset
--               of licensees. Recording a one-time 3-hour course as a per-cycle
--               3 would generate a wrong obligation every cycle, so those carry
--               {"hours": n, "periodicity": ...} instead.
--               Consumers MUST branch on the presence of value_json.
--
--   license_type 'MD' and 'APRN' match the vocabulary in 0003_credentials.sql.
--   DO IS NOT COVERED -- see README and the cross-cutting conflict rows.
--
-- CONTROLLED SUBSTANCE REGISTRATION: unlike the CA/FL/TX/NY set, six of these
-- states DO issue a state controlled substance credential separate from the
-- federal DEA registration (MI, SC, AL, MS, LA and -- for APRNs -- the state
-- prescriptive-authority grant). csr_required is seeded true only where a board
-- or statute says so in terms; it is left unseeded, not false, elsewhere.
--
-- Fees are in cents and are the amount the licensee actually pays where the
-- board publishes a single total; component breakdowns are in the citation.
--
-- Idempotent: safe to re-run. Respects ux_requirements_current (one is_current
-- row per state/license_type/field_key). Owns only verified_by =
-- 'research-agent-group-b' rows, so it does not disturb requirements_seed.sql.
-- =============================================================================

begin;

-- Re-running replaces only the rows this file owns. requirement_conflicts rows
-- written by requirement_conflicts_seed_group_b.sql point at these rows, so they
-- are cleared first; re-run that file AFTER this one.
delete from requirement_conflicts
 where observed_by = 'research-agent-group-b'
   and requirement_id in (
         select id from requirements
          where verified_by = 'research-agent-group-b');

delete from requirements
 where verified_by = 'research-agent-group-b'
   and state in ('MI','NC','VA','SC','TN','AL','MS','KY','AR','LA','OK','WV')
   and license_type in ('MD','APRN');

insert into requirements
  (state, license_type, field_key,
   value_text, value_num, value_bool, value_json,
   citation, citation_url, effective_date,
   verified_at, verified_by, version, is_current)
values

-- =============================================================================
-- MICHIGAN -- medical doctor (MD)
-- LARA Bureau of Professional Licensing / Board of Medicine.
-- Public Health Code art. 15 (MCL 333.16101 et seq.); Mich Admin Code R 338.24xx.
-- =============================================================================
('MI','MD','renewal_cycle_months', null, 36, null, null,
 'LARA Bureau of Professional Licensing, Michigan Medical Doctor (MD) Licensing Guide: "Medical Doctor licenses are renewed every 3 years." Confirmed by Mich Admin Code R 338.2441(2), which measures continuing education over "the 3 years immediately preceding the application for renewal".',
 'https://www.michigan.gov/lara/-/media/Project/Websites/lara/bpl/Medicine/Licensing-Info-and-Forms/MD-Licensing-Guide-FAQ-12626.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MI','MD','renewal_window_days', null, 90, null, null,
 'LARA Bureau of Professional Licensing, Michigan Medical Doctor (MD) Licensing Guide, renewal instructions: renewal "Must be completed by visiting www.michigan.gov/miplus no sooner than 90 days prior to the expiration date of current license." This is an explicit transactional open date, not a notification date.',
 'https://www.michigan.gov/lara/-/media/Project/Websites/lara/bpl/Medicine/Licensing-Info-and-Forms/MD-Licensing-Guide-FAQ-12626.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MI','MD','ce_hours_total', null, 150, null, null,
 'Mich Admin Code R 338.2441(2) (Board of Medicine general rules, 2024 AACS): an applicant for renewal "shall accumulate a minimum of 150 hours of continuing education in activities approved under R 338.2443 during the 3 years immediately preceding the application for renewal." R 338.2443(1)(d) further requires "A minimum of 75 continuing education credits must be obtained through category 1 programs".',
 'https://ars.apps.lara.state.mi.us/AdminCode/DownloadAdminCodeFile?FileName=R%20338.2401%20to%20R%20338.2443.pdf&ReturnHTML=True',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MI','MD','ce_cycle_months', null, 36, null, null,
 'Mich Admin Code R 338.2441(2): the 150 hours are measured "during the 3 years immediately preceding the application for renewal", i.e. the CE cycle is the 3-year renewal cycle.',
 'https://ars.apps.lara.state.mi.us/AdminCode/DownloadAdminCodeFile?FileName=R%20338.2401%20to%20R%20338.2443.pdf&ReturnHTML=True',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MI','MD','ce_topic_ethics_hours', null, 1, null, null,
 'Mich Admin Code R 338.2443(1)(b): "A minimum of 1 hour of continuing education must be earned in medical ethics." Per 3-year renewal cycle, within the 150-hour total.',
 'https://ars.apps.lara.state.mi.us/AdminCode/DownloadAdminCodeFile?FileName=R%20338.2401%20to%20R%20338.2443.pdf&ReturnHTML=True',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MI','MD','ce_topic_pain_management_hours', null, 3, null, null,
 'Mich Admin Code R 338.2443(1)(c): "A minimum of 3 hours of continuing education must be earned in pain and symptom management under section 17033(2) of the code, MCL 333.17033. At least 1 of the 3 hours must include controlled substances prescribing." Per 3-year renewal cycle, within the 150-hour total.',
 'https://ars.apps.lara.state.mi.us/AdminCode/DownloadAdminCodeFile?FileName=R%20338.2401%20to%20R%20338.2443.pdf&ReturnHTML=True',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MI','MD','ce_topic_controlled_substance_hours', null, null, null,
 '{"hours": 1, "periodicity": "per_renewal_cycle", "additive": false, "subset_of_field_key": "ce_topic_pain_management_hours", "note": "1 of the 3 pain and symptom management hours, NOT an additional hour"}'::jsonb,
 'Mich Admin Code R 338.2443(1)(c): "At least 1 of the 3 hours must include controlled substances prescribing." This hour is carved OUT OF the 3 pain and symptom management hours, not added to them; recorded as value_json so a consumer cannot sum it with ce_topic_pain_management_hours and invoice 4 hours.',
 'https://ars.apps.lara.state.mi.us/AdminCode/DownloadAdminCodeFile?FileName=R%20338.2401%20to%20R%20338.2443.pdf&ReturnHTML=True',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MI','MD','ce_topic_implicit_bias_hours', null, null, null,
 '{"hours_per_year_of_license_cycle": 1, "periodicity": "per_renewal_cycle", "carry_forward_prohibited": true, "initial_licensure": {"hours": 2, "window_years": 5}, "counts_toward_ce_hours_total": true}'::jsonb,
 'Mich Admin Code R 338.7004(2): a renewal applicant "shall have completed a minimum of 1 hour of implicit bias training for each year of the applicant''s license or registration cycle"; R 338.7004(3): hours may not be carried forward between cycles; R 338.7004(1): an initial applicant needs "a minimum of 2 hours of implicit bias training within the 5 years immediately preceding issuance". R 338.2443(1)(e) allows it to count toward the 150 hours. Expressed per YEAR OF CYCLE, not per cycle, so value_json rather than a bare per-cycle number.',
 'https://ars.apps.lara.state.mi.us/AdminCode/DownloadAdminCodeFile?FileName=R+338.7001+to+R+338.7005.pdf&ReturnHTML=True',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MI','MD','initial_license_fee_cents', null, 37500, null, null,
 'LARA Bureau of Professional Licensing, Michigan Medical Doctor (MD) Licensing Guide: "Application Fee + 3 year license fee: ... MD by Exam or Endorsement : $375.00".',
 'https://www.michigan.gov/lara/-/media/Project/Websites/lara/bpl/Medicine/Licensing-Info-and-Forms/MD-Licensing-Guide-FAQ-12626.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MI','MD','renewal_fee_cents', null, 31400, null, null,
 'LARA Bureau of Professional Licensing, Michigan Medical Doctor (MD) Licensing Guide: "MD Renewal Application Fee: $314.00" for the 3-year cycle.',
 'https://www.michigan.gov/lara/-/media/Project/Websites/lara/bpl/Medicine/Licensing-Info-and-Forms/MD-Licensing-Guide-FAQ-12626.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MI','MD','csr_required', null, null, true, null,
 'LARA Bureau of Professional Licensing, Michigan Controlled Substance Individual Licensing Guide: "A controlled substance license is required for every person who manufactures, distributes, prescribes, or dispenses any controlled substance in Michigan", and "You must obtain a Michigan controlled substance [license] prior to a DEA registration." This is a STATE licence separate from, and prerequisite to, federal DEA registration.',
 'https://www.michigan.gov/lara/-/media/Project/Websites/lara/bpl/Pharmacy/Licensing-Info-and-Forms/Info/Controlled-Substance-Individual-Licensing-Guide-FAQ-12626.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MI','MD','csr_renewal_cycle_months', null, 36, null, null,
 'LARA, Michigan Controlled Substance Individual Licensing Guide: the controlled substance licence is valid "1 - 3 years depending on the licensure cycle of the professional license", "runs concurrently with your professional license" and expires on the same date. The Michigan MD professional cycle is 3 years, so the concurrent CS licence cycle is 36 months.',
 'https://www.michigan.gov/lara/-/media/Project/Websites/lara/bpl/Pharmacy/Licensing-Info-and-Forms/Info/Controlled-Substance-Individual-Licensing-Guide-FAQ-12626.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MI','MD','csr_fee_cents', null, 24810, null, null,
 'LARA, Michigan Controlled Substance Individual Licensing Guide, renewal fee table: "3-Year license cycle - $248.10". (Initial application on a 25-36 month remaining cycle is "$259.10".) The 3-year figure is the one an MD pays because the MD professional cycle is 3 years.',
 'https://www.michigan.gov/lara/-/media/Project/Websites/lara/bpl/Pharmacy/Licensing-Info-and-Forms/Info/Controlled-Substance-Individual-Licensing-Guide-FAQ-12626.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

-- =============================================================================
-- MICHIGAN -- nurse practitioner (APRN)
-- LARA Bureau of Professional Licensing / Board of Nursing. A Michigan NP holds
-- an RN licence plus an RN specialty certification; both run on a 2-year clock.
-- =============================================================================
('MI','APRN','renewal_cycle_months', null, 24, null, null,
 'LARA Bureau of Professional Licensing, Michigan Nursing Licensing Guide: the renewal cycle is "2 years" for both the registered nurse licence and the RN specialty certification (nurse practitioner).',
 'https://www.michigan.gov/lara/-/media/Project/Websites/lara/bpl/Nursing/Licensing-Info-and-Forms/Nursing-Licensing-Guide-FAQ-12626.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MI','APRN','ce_hours_total', null, 25, null, null,
 'LARA Bureau of Professional Licensing, Michigan Nursing Licensing Guide: renewal requires "25 hours of continuing education in courses or programs approved by the board" per 2-year cycle.',
 'https://www.michigan.gov/lara/-/media/Project/Websites/lara/bpl/Nursing/Licensing-Info-and-Forms/Nursing-Licensing-Guide-FAQ-12626.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MI','APRN','ce_cycle_months', null, 24, null, null,
 'LARA, Michigan Nursing Licensing Guide: the 25 hours are required per 2-year renewal cycle, i.e. the CE cycle is the renewal cycle.',
 'https://www.michigan.gov/lara/-/media/Project/Websites/lara/bpl/Nursing/Licensing-Info-and-Forms/Nursing-Licensing-Guide-FAQ-12626.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MI','APRN','ce_topic_pain_management_hours', null, 2, null, null,
 'LARA, Michigan Nursing Licensing Guide: of the 25 hours, "at least 2 hours" must be in pain and symptom management.',
 'https://www.michigan.gov/lara/-/media/Project/Websites/lara/bpl/Nursing/Licensing-Info-and-Forms/Nursing-Licensing-Guide-FAQ-12626.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MI','APRN','ce_topic_implicit_bias_hours', null, null, null,
 '{"hours_per_year_of_license_cycle": 1, "periodicity": "per_renewal_cycle", "carry_forward_prohibited": true, "initial_licensure": {"hours": 2, "window_years": 5}}'::jsonb,
 'Mich Admin Code R 338.7004(2), as restated in LARA''s Michigan Nursing Licensing Guide: a renewal applicant must complete "1 hour of implicit bias training for each year of their license or registration cycle". R 338.7004(1) requires 2 hours within the preceding 5 years at initial licensure; R 338.7004(3) prohibits carry-forward. Expressed per YEAR OF CYCLE, hence value_json.',
 'https://ars.apps.lara.state.mi.us/AdminCode/DownloadAdminCodeFile?FileName=R+338.7001+to+R+338.7005.pdf&ReturnHTML=True',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MI','APRN','csr_required', null, null, true, null,
 'LARA Bureau of Professional Licensing, Michigan Controlled Substance Individual Licensing Guide: "A controlled substance license is required for every person who manufactures, distributes, prescribes, or dispenses any controlled substance in Michigan", and "You must obtain a Michigan controlled substance [license] prior to a DEA registration." The guide is profession-neutral and covers individual prescribers, not physicians only.',
 'https://www.michigan.gov/lara/-/media/Project/Websites/lara/bpl/Pharmacy/Licensing-Info-and-Forms/Info/Controlled-Substance-Individual-Licensing-Guide-FAQ-12626.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MI','APRN','csr_renewal_cycle_months', null, 24, null, null,
 'LARA, Michigan Controlled Substance Individual Licensing Guide: the CS licence "runs concurrently with your professional license" and is valid "1 - 3 years depending on the licensure cycle of the professional license". The Michigan RN/NP cycle is 2 years, so the concurrent CS cycle is 24 months.',
 'https://www.michigan.gov/lara/-/media/Project/Websites/lara/bpl/Pharmacy/Licensing-Info-and-Forms/Info/Controlled-Substance-Individual-Licensing-Guide-FAQ-12626.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MI','APRN','csr_fee_cents', null, 16540, null, null,
 'LARA, Michigan Controlled Substance Individual Licensing Guide, renewal fee table: "2-Year license cycle - $165.40". (Initial application on a 3-24 month remaining cycle is "$176.40".)',
 'https://www.michigan.gov/lara/-/media/Project/Websites/lara/bpl/Pharmacy/Licensing-Info-and-Forms/Info/Controlled-Substance-Individual-Licensing-Guide-FAQ-12626.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

-- =============================================================================
-- NORTH CAROLINA -- physician (MD)
-- North Carolina Medical Board. G.S. ch. 90 art. 1; 21 NCAC 32.
-- NC renews the licence ANNUALLY but runs CME on a separate THREE-YEAR clock --
-- the two do not coincide, which is exactly the case a single cycle field hides.
-- =============================================================================
('NC','MD','renewal_cycle_months', null, 12, null, null,
 'North Carolina Medical Board, Physician License Renewal: "All physicians are required to renew their medical licenses each year by their birthday".',
 'https://www.ncmedboard.org/licensing-registration/renewals/physicians',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('NC','MD','ce_hours_total', null, 60, null, null,
 'North Carolina Medical Board, Professional FAQs - CME: "at least 60 hours of Category I CME completed over a three-year cycle". The Board''s renewal page states the same: "North Carolina physicians must complete 60 hours of continuing medical education (CME) every three years."',
 'https://www.ncmedboard.org/resources-information/faqs/professional-faqs/cme',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('NC','MD','ce_cycle_months', null, 36, null, null,
 'North Carolina Medical Board, Professional FAQs - CME: "Your three-year cycle depends on when you were licensed and typically starts on the first birthday following your initial licensure date and runs for three years." NOTE: the CME cycle is 36 months while the licence renews every 12 months -- the two clocks are NOT the same.',
 'https://www.ncmedboard.org/resources-information/faqs/professional-faqs/cme',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('NC','MD','ce_topic_controlled_substance_hours', null, null, null,
 '{"hours": 3, "periodicity": "per_3_year_cme_cycle", "applies_to": "physicians who write prescriptions for controlled substances", "additive": false, "subset_of_field_key": "ce_hours_total"}'::jsonb,
 'North Carolina Medical Board, Professional FAQs - CME: "if you write prescriptions for CS, you must have three of the required 60 hours specifically focused on CS CME". Conditional on prescribing, carved out of the 60 rather than added to it, and running on the 3-year CME clock rather than the 12-month renewal clock -- three separate reasons this cannot be a bare per-cycle number.',
 'https://www.ncmedboard.org/resources-information/faqs/professional-faqs/cme',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('NC','MD','renewal_fee_cents', null, 25000, null, null,
 'North Carolina Medical Board, Physician License Renewal: "The current annual license renewal fee for medical doctors (MDs) and doctors of osteopathic medicine (DOs) is $250." Physicians who fail to renew within 30 days of their birthday pay an additional $50 late fee.',
 'https://www.ncmedboard.org/licensing-registration/renewals/physicians',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

-- =============================================================================
-- NORTH CAROLINA -- nurse practitioner (APRN)
-- Jointly regulated by the NC Board of Nursing and the NC Medical Board under
-- 21 NCAC 32M (Approval of Nurse Practitioners). NP approval renews ANNUALLY.
-- =============================================================================
('NC','APRN','renewal_cycle_months', null, 12, null, null,
 '21 NCAC 32M .0106(a), as published by the North Carolina Medical Board: "Each registered nurse who is approved to practice as a nurse practitioner in this State shall annually renew each approval to practice with the Board of Nursing no later than the last day of the nurse practitioner''s birth month".',
 'https://www.ncmedboard.org/images/uploads/other_pdfs/subchapter_m_rules.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('NC','APRN','ce_hours_total', null, 50, null, null,
 '21 NCAC 32M .0107: "the nurse practitioner shall earn 50 contact hours of continuing education each year beginning with the first renewal after initial approval to practice has been granted. At least 20 hours of the required 50 hours must be those hours for which approval has been granted by the American Nurses Credentialing Center (ANCC) or Accreditation Council on Continuing Medical Education (ACCME)". SUBJECT TO AN OPEN CONFLICT: the NC Board of Nursing''s own NP continuing competence page states "50 contact hours of continuing education every two years" -- see requirement_conflicts.',
 'https://www.ncmedboard.org/images/uploads/other_pdfs/subchapter_m_rules.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('NC','APRN','ce_cycle_months', null, 12, null, null,
 '21 NCAC 32M .0107: the 50 contact hours are required "each year", i.e. the CE cycle is the annual renewal cycle. SUBJECT TO THE SAME OPEN CONFLICT as ce_hours_total -- the Board of Nursing page says every two years.',
 'https://www.ncmedboard.org/images/uploads/other_pdfs/subchapter_m_rules.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('NC','APRN','ce_topic_controlled_substance_hours', null, null, null,
 '{"hours": 1, "periodicity": "annual", "applies_to": "nurse practitioners who prescribe controlled substances", "additive": false, "subset_of_field_key": "ce_hours_total"}'::jsonb,
 '21 NCAC 32M .0107: "Every nurse practitioner who prescribes controlled substances shall complete at least one hour of the total required continuing education (CE) hours annually consisting of CE designed specifically to address controlled substance prescribing practices, signs of the abuse or misuse of controlled substances, and controlled substance prescribing for chronic pain management." Conditional on prescribing and carved out of the 50, hence value_json.',
 'https://www.ncmedboard.org/images/uploads/other_pdfs/subchapter_m_rules.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('NC','APRN','initial_license_fee_cents', null, 10000, null, null,
 '21 NCAC 32M .0115(a): "An application fee of one hundred dollars ($100.00) shall be paid at the time of initial application for approval to practice and each subsequent application for approval to practice." (Volunteer approval is $20.00.) This is the NP approval fee; the underlying NC RN licence carries its own separate fee.',
 'https://www.ncmedboard.org/images/uploads/other_pdfs/subchapter_m_rules.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('NC','APRN','renewal_fee_cents', null, 5000, null, null,
 '21 NCAC 32M .0115(b): "The fee for annual renewal of approval shall be fifty dollars ($50.00)." (Volunteer approval renewal is $10.00.) This is the NP approval renewal; the underlying RN licence renewal is separate.',
 'https://www.ncmedboard.org/images/uploads/other_pdfs/subchapter_m_rules.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('NC','APRN','collaborative_agreement_required', null, null, true, null,
 '21 NCAC 32M .0110(2): the collaborative practice agreement "shall be agreed upon and signed by both the primary supervising physician and the nurse practitioner, and maintained in each practice site"; it "shall be reviewed at least yearly", "shall include the drugs, devices, medical treatments, tests and procedures that may be prescribed", and "shall include a pre-determined plan for emergency services." North Carolina has no independent-practice pathway for NPs.',
 'https://www.ncmedboard.org/images/uploads/other_pdfs/subchapter_m_rules.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('NC','APRN','supervision_required', null, null, true, null,
 '21 NCAC 32M .0110(1): "The primary or back-up supervising physician(s) and the nurse practitioner shall be continuously available to each other for consultation by direct communication or telecommunication." Rule .0110(4)(c) further requires "scheduled meetings between the primary supervising physician and the nurse practitioner at least every six months" with signed documentation. The rule names a "primary supervising physician" throughout, so supervision is distinct from, and additional to, the written agreement.',
 'https://www.ncmedboard.org/images/uploads/other_pdfs/subchapter_m_rules.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

-- =============================================================================
-- VIRGINIA -- doctor of medicine (MD)
-- Virginia Board of Medicine, DHP. Code of Va. title 54.1 ch. 29; 18VAC85-20.
-- =============================================================================
('VA','MD','renewal_cycle_months', null, 24, null, null,
 '18VAC85-20-235(A): "In order to renew an active license biennially, a practitioner shall attest to completion of ..."; 18VAC85-20-22 states the renewal fee is "due in each even-numbered year in the licensee''s birth month". Biennial, anchored to the birth month of even-numbered years.',
 'https://law.lis.virginia.gov/admincode/title18/agency85/chapter20/section22/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('VA','MD','ce_hours_total', null, 30, null, null,
 '18VAC85-20-235(A) (amended eff. February 27, 2025): "In order to renew an active license biennially, a practitioner shall attest to completion of at least 30 hours of continuing learning activities within the two years immediately preceding renewal. The hours shall be in Type 1 activities or courses offered by an accredited sponsor or organization sanctioned by the profession."',
 'https://law.lis.virginia.gov/admincode/title18/agency85/chapter20/section235/',
 '2025-02-27', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('VA','MD','ce_cycle_months', null, 24, null, null,
 '18VAC85-20-235(A): the 30 hours must fall "within the two years immediately preceding renewal", i.e. the CE cycle is the biennial renewal cycle. 18VAC85-20-235(B) exempts the first biennial renewal following initial Virginia licensure.',
 'https://law.lis.virginia.gov/admincode/title18/agency85/chapter20/section235/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('VA','MD','initial_license_fee_cents', null, 30200, null, null,
 '18VAC85-20-22: "The application fee for licensure in medicine, osteopathic medicine, and podiatry shall be $302".',
 'https://law.lis.virginia.gov/admincode/title18/agency85/chapter20/section22/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('VA','MD','renewal_fee_cents', null, 33700, null, null,
 '18VAC85-20-22: "The fee for biennial renewal shall be $337 for licensure in medicine, osteopathic medicine, and podiatry", "due in each even-numbered year in the licensee''s birth month".',
 'https://law.lis.virginia.gov/admincode/title18/agency85/chapter20/section22/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

-- =============================================================================
-- VIRGINIA -- advanced practice registered nurse (APRN)
-- Jointly licensed by the Board of Nursing and Board of Medicine. Code of Va.
-- sec. 54.1-2957; 18VAC90-30.
-- =============================================================================
('VA','APRN','renewal_cycle_months', null, 24, null, null,
 '18VAC90-30-100(A): "Licensure of an advanced practice registered nurse shall be renewed: 1. Biennially at the same time the license to practice as a registered nurse in Virginia is renewed; or 2. [for multistate privilege holders] a licensee born in even-numbered years shall renew his license by the last day of the birth month in even-numbered years and a licensee born in odd-numbered years shall renew ... in odd-numbered years."',
 'https://law.lis.virginia.gov/admincode/title18/agency90/chapter30/section100/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('VA','APRN','ce_hours_total', null, null, null,
 '{"hours": 40, "periodicity": "per_renewal_cycle", "applies_to": "APRNs licensed before May 8, 2002, and clinical nurse specialists registered with a retired certification, who do not hold current national certification", "default_pathway": "current professional certification in the specialty; no hour requirement"}'::jsonb,
 '18VAC90-30-105(A): an APRN "initially licensed on or after May 8, 2002, shall hold current professional certification in the area of specialty practice" -- no hour count. 18VAC90-30-105(B) permits APRNs licensed BEFORE May 8, 2002 to renew either by holding certification or by completing "at least 40 hours of continuing education in the area of specialty practice". The 40 hours therefore bind only a shrinking subset of licensees; seeding a bare 40 would invoice every Virginia APRN a duty most of them do not have.',
 'https://law.lis.virginia.gov/admincode/title18/agency90/chapter30/section105/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('VA','APRN','initial_license_fee_cents', null, 12500, null, null,
 '18VAC90-30-50(A)(1): APRN licensure "Application $125". The underlying Virginia RN licence carries its own separate fee, and an "Autonomous practice attestation" is a further $100 (18VAC90-30-50(A)(10)).',
 'https://law.lis.virginia.gov/admincode/title18/agency90/chapter30/section50/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('VA','APRN','renewal_fee_cents', null, 8000, null, null,
 '18VAC90-30-50(A)(2): "Biennial licensure renewal $80"; late renewal is a further $25 (subdivision 3). The transitional $60 fee in subsection B applied only "from July 1, 2017, through June 30, 2019" and is spent.',
 'https://law.lis.virginia.gov/admincode/title18/agency90/chapter30/section50/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('VA','APRN','collaborative_agreement_required', null, null, null,
 '{"required": true, "until_full_time_clinical_experience_years": 3, "after_threshold": "may practice without a written or electronic practice agreement, on attestation plus a board fee", "instrument": "written or electronic practice agreement with a patient care team physician", "attestation_fee_cents": 10000, "note": "certified nurse midwives (1,000 hours) and clinical nurse specialists follow different thresholds under the same statute"}'::jsonb,
 'Code of Virginia sec. 54.1-2957(C): "Every nurse practitioner who does not meet the requirements of subsection I shall maintain appropriate collaboration and consultation, as evidenced in a written or electronic practice agreement, with at least one patient care team physician." Sec. 54.1-2957(I): "A nurse practitioner who has completed the equivalent of at least three years of full-time clinical experience, as determined by the Boards, may practice ... without a written or electronic practice agreement upon receipt ... of an attestation". Conditional on an experience threshold, so a bare boolean would misstate the obligation for a large share of the population -- hence value_json.',
 'https://law.lis.virginia.gov/vacode/title54.1/chapter29/section54.1-2957/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

-- =============================================================================
-- SOUTH CAROLINA -- physician (MD)
-- SC Board of Medical Examiners, LLR. S.C. Code title 40 ch. 47; 81 S.C. Code
-- of Regs. Controlled substances: S.C. Code title 44 ch. 53; 24A S.C. Regs 60-4.
-- =============================================================================
('SC','MD','renewal_cycle_months', null, 24, null, null,
 'S.C. Code Ann. sec. 40-47-40(A): "A license issued pursuant to this chapter may be renewed biennially or as otherwise provided by the board and department." Sec. 40-47-37(A)(2) frames the continuing competence test as "For renewal of an active permanent license biennially". The Board''s CE brochure states the cycle runs "every two years in the odd-numbered years" with a June 30 deadline.',
 'https://www.scstatehouse.gov/code/t40c047.php',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('SC','MD','ce_hours_total', null, 40, null, null,
 'S.C. Code Ann. sec. 40-47-37(A)(2)(a): renewal requires "forty hours of Category I continuing medical education sponsored by the American Medical Association, American Osteopathic Association, or another organization approved by the board ..., at least thirty hours of which must be related directly to the licensee''s practice area". The Board''s own CE brochure restates it: "40 Hours of continuing medical education to renew. Thirty of these hours must be in their specialty; 10 may be non-specialty."',
 'https://www.scstatehouse.gov/code/t40c047.php',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('SC','MD','ce_cycle_months', null, 24, null, null,
 'S.C. Code Ann. sec. 40-47-37(A)(2): the forty hours are required "during the renewal period" for biennial renewal of an active permanent licence, i.e. the CE cycle is the biennial renewal cycle.',
 'https://www.scstatehouse.gov/code/t40c047.php',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('SC','MD','ce_topic_controlled_substance_hours', null, 2, null, null,
 'S.C. Board of Medical Examiners / S.C. Board of Podiatry Examiners CE requirements sheet: "Two hours must be in safe prescribing and monitoring of controlled substances." SUBJECT TO AN OPEN CONFLICT: S.C. Code Ann. sec. 40-47-37(A)(2)(a) uses the permissive "at least two (2) hours of which MAY be related to approved procedures of prescribing and monitoring controlled substances" while requiring the certificate of participation at renewal -- see requirement_conflicts.',
 'https://www.llr.sc.gov/med/PDF/Medical_CE_Reqs.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('SC','MD','renewal_fee_cents', null, 15500, null, null,
 'S.C. Board of Medical Examiners renewal schedule: "$155 Renewal Fee" for the MD/DO biennial renewal period. Late renewal adds "$100 Additional Late Renewal Fee Per Month".',
 'https://llr.sc.gov/med/pdf/renewalschedule.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('SC','MD','csr_required', null, null, true, null,
 '24A S.C. Code Ann. Regs. 60-4, sec. 106: "Every person who manufactures, distributes, prescribes or dispenses any controlled substance or who proposes to engage in the manufacture, distribution or dispensing of any controlled substance shall obtain annually a registration unless exempted by law." S.C. Code Ann. sec. 44-53-290(a) is to the same effect. The registration is issued by the S.C. Department of Public Health (formerly DHEC) Bureau of Drug Control and is SEPARATE from federal DEA registration; sec. 40-47-31(A) confirms a physician "is entitled to apply for individual controlled substance registration through the Department".',
 'https://dph.sc.gov/sites/scdph/files/Library/Regulations/R.60-4.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('SC','MD','csr_renewal_cycle_months', null, 12, null, null,
 'S.C. Code Ann. sec. 44-53-280(D): "All registrations other than class 20-28 ... expire on April first of each year. The registration of a registrant who fails to renew by April first is canceled." 24A S.C. Regs. 60-4 sec. 106 likewise says a registrant "shall obtain annually a registration". Note this is a 12-month clock running against an April 1 fixed date, unrelated to the biennial June 30 licence cycle.',
 'https://www.scstatehouse.gov/code/t44c053.php',
 '2018-05-18', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

-- =============================================================================
-- SOUTH CAROLINA -- advanced practice registered nurse (APRN)
-- S.C. Board of Nursing, LLR. S.C. Code title 40 ch. 33.
-- =============================================================================
('SC','APRN','renewal_cycle_months', null, 24, null, null,
 'S.C. Board of Nursing, Renewals Frequently Asked Questions: the Board describes "the 2-year renewal period" and licences expiring "April 30, 2026". S.C. Code Ann. sec. 40-33-30 provides for biennial renewal of nursing authorisations.',
 'https://llr.sc.gov/nurse/pdf/Renewal_FAQs.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('SC','APRN','ce_topic_pharmacotherapeutics_hours', null, null, null,
 '{"hours": 20, "periodicity": "per_renewal_cycle", "applies_to": "APRNs holding prescriptive authority (RX)", "in_addition_to": "current national certification"}'::jsonb,
 'S.C. Board of Nursing, Renewals FAQ: "Competency for an APRN with prescriptive authority (RX) is an updated National Certification in addition to 20 hours of Pharmacotherapeutics with 2 of the 20 hours focused on controlled substances." Conditional on holding prescriptive authority, hence value_json. An APRN without prescriptive authority renews on national certification alone.',
 'https://llr.sc.gov/nurse/pdf/Renewal_FAQs.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('SC','APRN','ce_topic_controlled_substance_hours', null, null, null,
 '{"hours": 2, "periodicity": "per_renewal_cycle", "applies_to": "APRNs holding prescriptive authority (RX)", "additive": false, "subset_of_field_key": "ce_topic_pharmacotherapeutics_hours"}'::jsonb,
 'S.C. Board of Nursing, Renewals FAQ: "20 hours of Pharmacotherapeutics with 2 of the 20 hours focused on controlled substances." The 2 hours are carved OUT OF the 20, not added to them, and apply only to prescriptive-authority holders.',
 'https://llr.sc.gov/nurse/pdf/Renewal_FAQs.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('SC','APRN','initial_license_fee_cents', null, 3000, null, null,
 'S.C. Board of Nursing Fees: "APRN Initial Fee (S.C. licensee only) without Temporary License $30" (with temporary licence $40; by endorsement $140 / $150). "Application for Prescriptive Authority" is a further $20. The underlying RN licence carries its own separate fee.',
 'https://llr.sc.gov/nurse/fees.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('SC','APRN','renewal_fee_cents', null, null, null,
 '{"cents": 10500, "variant": "APRN Renewal without Prescriptive Authority", "with_prescriptive_authority_cents": 14500, "periodicity": "per_renewal_cycle"}'::jsonb,
 'S.C. Board of Nursing Fees: "APRN Renewal without Prescriptive Authority $105" and "APRN Renewal with Prescriptive Authority $145". South Carolina charges two different renewal amounts depending on whether the APRN holds prescriptive authority, so a single number would overcharge or undercharge a large share of licensees; value_json carries both.',
 'https://llr.sc.gov/nurse/fees.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('SC','APRN','csr_required', null, null, true, null,
 '24A S.C. Code Ann. Regs. 60-4, sec. 106: "Every person who manufactures, distributes, prescribes or dispenses any controlled substance ... shall obtain annually a registration unless exempted by law." The regulation is person-neutral and is not limited to physicians; S.C. Code Ann. sec. 44-53-290(a) imposes the same duty on "Every person who manufactures, distributes, or dispenses any controlled substance", and sec. 44-53-110(15) defines "dispense" to include "the prescribing".',
 'https://dph.sc.gov/sites/scdph/files/Library/Regulations/R.60-4.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('SC','APRN','csr_renewal_cycle_months', null, 12, null, null,
 'S.C. Code Ann. sec. 44-53-280(D): "All registrations other than class 20-28 ... expire on April first of each year." 24A S.C. Regs. 60-4 sec. 106 requires the registration to be obtained "annually".',
 'https://www.scstatehouse.gov/code/t44c053.php',
 '2018-05-18', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

-- =============================================================================
-- TENNESSEE -- physician (MD)
-- Tennessee Board of Medical Examiners, Dept of Health. TCA title 63 ch. 6;
-- Rules ch. 0880-02.
-- =============================================================================
('TN','MD','renewal_cycle_months', null, 24, null, null,
 'Tennessee Department of Health, Board of Medical Examiners: "All licensees are required to renew their license every two years. The renewal cycle is set up whereby everyone renews in their birth month."',
 'https://www.tn.gov/health/licensure/me.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('TN','MD','renewal_window_days', null, 60, null, null,
 'Tennessee Department of Health, Board of Medical Examiners: "Licenses can be renewed on-line sixty (60) days prior to expiration." This is a transactional open date, not a notification date.',
 'https://www.tn.gov/health/licensure/me.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('TN','MD','ce_hours_total', null, 40, null, null,
 'Tennessee Board of Medical Examiners, CME FAQs: "All medical doctors must complete forty (40) hours in the twenty-four (24) months preceding their licensure renewal."',
 'https://www.tn.gov/content/dam/tn/health/healthprofboards/medicalexaminers/MDcmefaqs.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('TN','MD','ce_cycle_months', null, 24, null, null,
 'Tennessee Board of Medical Examiners, CME FAQs: the 40 hours run over "the twenty-four (24) months preceding their licensure renewal", i.e. the CE cycle is the biennial renewal cycle.',
 'https://www.tn.gov/content/dam/tn/health/healthprofboards/medicalexaminers/MDcmefaqs.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('TN','MD','ce_topic_controlled_substance_hours', null, null, null,
 '{"hours": 2, "periodicity": "per_renewal_cycle", "additive": false, "subset_of_field_key": "ce_hours_total", "exempt_board_certifications": ["pain management", "anesthesiology", "physical medicine and rehabilitation", "neurology", "rheumatology"]}'::jsonb,
 'Tennessee Board of Medical Examiners, CME FAQs: "two (2) of the forty (40) required hours must relate to controlled substance prescribing, which must include instruction in the Department''s treatment guidelines on opioids, benzodiazepines, barbiturates and carisoprodol", with an exemption for physicians board-certified in pain management, anesthesiology, physical medicine and rehabilitation, neurology or rheumatology. Carved out of the 40 and subject to a specialty exemption, hence value_json.',
 'https://www.tn.gov/content/dam/tn/health/healthprofboards/medicalexaminers/MDcmefaqs.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

-- =============================================================================
-- TENNESSEE -- advanced practice registered nurse (APRN)
-- Tennessee Board of Nursing. TCA title 63 ch. 7; Rules ch. 1000-04.
-- =============================================================================
('TN','APRN','renewal_cycle_months', null, 24, null, null,
 'Tennessee Board of Nursing, APRN Continuing Education Requirements (Rule 1000-04-.05): "All advanced practice nurses must biennially renew their Tennessee Advanced Practice Registered Nurse Certificate. They must also either biennially renew their Tennessee registered nurse license or maintain their license as a registered nurse with the multistate licensure privilege to practice in Tennessee."',
 'https://www.tn.gov/content/dam/tn/health/pdf/APRN-Controlled-Substance-Prescribing-CE-Req-070626.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('TN','APRN','ce_topic_controlled_substance_hours', null, null, null,
 '{"hours": 2, "periodicity": "per_renewal_cycle", "applies_to": "APRNs in possession of a Certificate of Fitness under Rule 1000-01-.18", "required_content": ["Tennessee Department of Health treatment guidelines on opioids, benzodiazepines, barbiturates and carisoprodol"]}'::jsonb,
 'Tennessee Board of Nursing, APRN Continuing Education Requirements (Rules 1000-04-.05 and 1000-01-.18): "If in possession of a Certificate of Fitness pursuant to Rule 1000-01-.18, have successfully completed a minimum of two (2) contact hours of continuing education designed specifically to address controlled substance prescribing practices. The continuing education must include instruction in the Tennessee Department of Health''s treatment guidelines on opioids, benzodiazepines, barbiturates, and carisoprodol." Conditional on holding a Certificate of Fitness, hence value_json.',
 'https://www.tn.gov/content/dam/tn/health/pdf/APRN-Controlled-Substance-Prescribing-CE-Req-070626.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('TN','APRN','renewal_fee_cents', null, 11000, null, null,
 'Tennessee Board of Nursing Fee Schedule: "Advanced Practice Registered Nurse (APRN) ... Renewal $110.00". Initial application fee was "eliminated as of 08/05/2019". The underlying Tennessee RN licence renewal is a separate $100.00.',
 'https://www.tn.gov/content/dam/tn/health/healthprofboards/nursing/Fee%20Schedule.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('TN','APRN','collaborative_agreement_required', null, null, null,
 '{"required": true, "applies_to": "APRNs who prescribe", "instrument": "Collaborative Request / APRN Supervisory Request (formerly Notice and Formulary) filed with the Board", "verified_scope": "prescribing only"}'::jsonb,
 'Tennessee Board of Nursing, Continuing Competence Requirements (Rules 1000-01-.14, 1000-02-.14, 1000-04-.05): an APRN with a Certificate of Fitness must maintain a "Copy of current Collaborative Request/APRN Supervisory Request (formerly Notice and Formulary) if prescribing". The instrument is verified only for the PRESCRIBING case; the non-prescribing case was not established from a primary source -- see requirement_conflicts. Hence value_json rather than a bare boolean.',
 'https://www.tn.gov/content/dam/tn/health/documents/ContinuedCompetenceRequirements.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

-- =============================================================================
-- ALABAMA -- physician (MD)
-- Alabama Board of Medical Examiners / Medical Licensure Commission.
-- Ala. Code title 34 ch. 24; Ala. Admin. Code ch. 540.
-- Alabama is an ANNUAL-registration state with a SEPARATE annual controlled
-- substances certificate on its own December 31 clock.
-- =============================================================================
('AL','MD','renewal_cycle_months', null, 12, null, null,
 'Alabama Board of Medical Examiners & Medical Licensure Commission, Renewals: "All licenses expire annually on Dec. 31." Renewal applications open through the Licensee Gateway "beginning on Oct. 1".',
 'https://www.albme.gov/licensing/md-do/licensing-md-do-license-renewals/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('AL','MD','ce_hours_total', null, 25, null, null,
 'Alabama Board of Medical Examiners, Continuing Medical Education Requirements for Licensees: "Physicians must obtain twenty-five (25) AMA PRA Category 1 Credits, AOA Category 1-A credits or equivalent annually (calendar year)."',
 'https://www.albme.gov/resources/licensees/continuing-medical-education/licensure-cme-requirement',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('AL','MD','ce_cycle_months', null, 12, null, null,
 'Alabama Board of Medical Examiners, CME Requirements for Licensees: the 25 credits are required "annually (calendar year)", the period being "Jan. 1 - Dec. 31 of each year". The CE cycle is the annual registration cycle.',
 'https://www.albme.gov/resources/licensees/continuing-medical-education/licensure-cme-requirement',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('AL','MD','ce_topic_controlled_substance_hours', null, null, null,
 '{"hours": 2, "periodicity": "every_2_years", "applies_to": "physicians holding an Alabama Controlled Substances Certificate (ACSC)", "topics": ["controlled substance prescribing practices", "recognizing signs of abuse or misuse of controlled substances", "controlled substance prescribing for chronic pain management"]}'::jsonb,
 'Alabama Board of Medical Examiners, CME Requirements for Licensees: ACSC holders must complete "Two (2) AMA PRA Category 1 Credits every two years" in controlled substance prescribing practices, recognising signs of abuse or misuse, or prescribing for chronic pain management. Runs on a TWO-year clock against an ANNUAL registration and applies only to ACSC holders -- two reasons this is not a bare per-cycle number.',
 'https://www.albme.gov/resources/licensees/continuing-medical-education/licensure-cme-requirement',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('AL','MD','ce_topic_ethics_hours', null, null, null,
 '{"hours": 2, "periodicity": "one_time", "course": "Navigating Professional Boundaries in Medicine", "deadline_for_existing_licensees": "2025-12-31", "field_key_note": "the Board calls this professional boundaries; mapped to the ethics topic key because the vocabulary has no boundaries key"}'::jsonb,
 'Alabama Board of Medical Examiners, CME Requirements for Licensees: "Beginning in 2025, all actively licensed physicians ... are required to complete the two-hour on-demand course ... entitled ''Navigating Professional Boundaries in Medicine.''" The deadline for existing licensees was "December 31, 2025". ONE-TIME, not annual; recorded as a per-year 2 it would invoice every Alabama physician a fabricated duty every single year.',
 'https://www.albme.gov/resources/licensees/continuing-medical-education/licensure-cme-requirement',
 '2025-01-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('AL','MD','renewal_fee_cents', null, 30000, null, null,
 'Alabama Board of Medical Examiners & Medical Licensure Commission, Renewals: annual MD/DO full licence renewal "$300".',
 'https://www.albme.gov/licensing/md-do/licensing-md-do-license-renewals/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('AL','MD','csr_required', null, null, true, null,
 'Alabama Board of Medical Examiners, Alabama Controlled Substances Certificate (ACSC): "To distribute, prescribe, or dispense any controlled substance in Alabama, physicians must obtain annually an Alabama Controlled Substances Certificate (ACSC)." The ACSC is a PREREQUISITE to the federal registration: applicants "Apply for Alabama-specific DEA registration after receiving the initial ACSC". Waived for U.S. Department of Veterans Affairs employees and, for 18 months, for medical residents.',
 'https://www.albme.gov/licensing/md-do/registrations/acsc/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('AL','MD','csr_renewal_cycle_months', null, 12, null, null,
 'Alabama Board of Medical Examiners, ACSC: "ACSCs are renewed annually on or before Dec. 31" through the Licensee Gateway; the certificate must be obtained "annually".',
 'https://www.albme.gov/licensing/md-do/registrations/acsc/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('AL','MD','csr_fee_cents', null, 15000, null, null,
 'Alabama Board of Medical Examiners, ACSC: initial and renewal cost "$150" each, "Non-Transferable/Non-Refundable".',
 'https://www.albme.gov/licensing/md-do/registrations/acsc/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

-- =============================================================================
-- ALABAMA -- certified registered nurse practitioner (APRN)
-- Alabama Board of Nursing (licence, CE) and Alabama Board of Medical Examiners
-- (collaborative practice approval, QACSC). Ala. Code title 34 ch. 21.
-- =============================================================================
('AL','APRN','renewal_cycle_months', null, 24, null, null,
 'Alabama Board of Nursing, Renewal: "The renewal period begins at 8:00 a.m. on September 1st and ends at 4:30 p.m. on December 31st (RNs/APRN on EVEN years and LPNs on ODD years)." RN and APRN authorisations therefore renew on a two-year clock expiring December 31 of even-numbered years.',
 'https://www.abn.alabama.gov/licensing/renewal/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('AL','APRN','ce_hours_total', null, 24, null, null,
 'Alabama Board of Nursing, Renewal: "The ABN Administrative Code requires Alabama nurses to complete 24 hours of continuing education (CE) credit per license period (in the case of APNs, six of these hours must carry Pharmacology credit)."',
 'https://www.abn.alabama.gov/licensing/renewal/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('AL','APRN','ce_cycle_months', null, 24, null, null,
 'Alabama Board of Nursing, Renewal: the 24 hours are required "per license period", and the RN/APRN licence period is the two-year even-year cycle described on the same page.',
 'https://www.abn.alabama.gov/licensing/renewal/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('AL','APRN','ce_topic_pharmacotherapeutics_hours', null, 6, null, null,
 'Alabama Board of Nursing, Renewal: "in the case of APNs, six of these hours must carry Pharmacology credit". Alabama Board of Nursing, Advanced Practice FAQs: "All APNs are required to document six (6) hours of continuing education in pharmacology for each biennial renewal." Carved out of the 24, per biennial renewal.',
 'https://www.abn.alabama.gov/licensing/advanced-practice/faqs/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('AL','APRN','collaborative_agreement_required', null, null, true, null,
 'Alabama Board of Medical Examiners, Collaboration: "The Board of Medical Examiners and the Board of Nursing jointly approve applications for approval of collaborative practices between qualified physicians and CRNPs and/or CNMs." The agreement specifies "the duties to be performed, work hours, quality assurance plans, and other details". Alabama Board of Nursing, Advanced Practice FAQs: "Only CRNPs and CNMs are subject to the collaborative practice requirements." NOTE the approval does NOT renew: "Collaborative agreements are not renewed. They continue in effect until notification of termination is received."',
 'https://www.albme.gov/licensing/crnp-cnm/collaboration/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('AL','APRN','csr_required', null, null, true, null,
 'Alabama Board of Medical Examiners, Qualified Alabama Controlled Substances Certificate (QACSC): a QACSC is required of "Certified Nurse Practitioners (CRNP) and Certified Nurse Midwives (CNM)" who prescribe Schedule III, IV or V controlled substances in Alabama, and it is a PREREQUISITE to the federal registration -- applicants "Apply for registration with the Drug Enforcement Administration after receiving the initial QACSC". SCOPE NOTE: the QACSC covers Schedules III-V; Alabama CRNP authority does not extend to Schedule II -- see requirement_conflicts.',
 'https://www.albme.gov/licensing/crnp-cnm/qacsc/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('AL','APRN','csr_renewal_cycle_months', null, 12, null, null,
 'Alabama Board of Medical Examiners, QACSC: "QACSC is renewed annually on or before Jan. 1 of each year"; the certificate must be obtained "annually". This 12-month clock does NOT coincide with the 24-month APRN licence cycle.',
 'https://www.albme.gov/licensing/crnp-cnm/qacsc/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('AL','APRN','csr_fee_cents', null, 6000, null, null,
 'Alabama Board of Medical Examiners, QACSC fees: "Renewal: $60" (initial $110; additional certificate $60). The renewal figure is seeded because that is the recurring obligation.',
 'https://www.albme.gov/licensing/crnp-cnm/qacsc/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

-- =============================================================================
-- MISSISSIPPI -- physician (MD)
-- Mississippi State Board of Medical Licensure. Miss. Code title 73 ch. 25;
-- 30 Miss. Admin. Code Part 2610.
-- ANNUAL licence renewal against a TWO-YEAR CME cycle -- the clocks differ.
-- =============================================================================
('MS','MD','renewal_cycle_months', null, 12, null, null,
 'Mississippi State Board of Medical Licensure, MD/DO Permanent License Renewal: "Permanent MD and DO licenses must be renewed annually through MELS (Medical Enforcement & Licensure System)." "Renewal period: Begins May 1 and ends June 30 each year."',
 'https://www.msbml.ms.gov/licensure/md-do-permanent-renewal',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MS','MD','ce_hours_total', null, 40, null, null,
 'Mississippi State Board of Medical Licensure, MD/DO Permanent License Renewal: "Physicians (MD & DO) must complete 40 hours of Category 1 CME per two-year cycle. Compliance is attested at annual renewal and applies to all license statuses, including retired." Requirements sit in 30 Miss. Admin. Code Part 2610, Chapter 2.',
 'https://www.msbml.ms.gov/licensure/md-do-permanent-renewal',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MS','MD','ce_cycle_months', null, 24, null, null,
 'Mississippi State Board of Medical Licensure, MD/DO Permanent License Renewal: the 40 hours run "per two-year cycle", the published cycles being "July 1, 2024 - June 30, 2026", "July 1, 2026 - June 30, 2028" and "July 1, 2028 - June 30, 2030". NOTE the CME cycle is 24 months while the licence renews every 12 months -- the two clocks are NOT the same.',
 'https://www.msbml.ms.gov/licensure/md-do-permanent-renewal',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MS','MD','renewal_fee_cents', null, 30000, null, null,
 'Mississippi State Board of Medical Licensure, MD/DO Permanent License Renewal: "The cost to renew an MD/DO permanent license is $300.00. There is also an additional convenience fee charged." The convenience fee amount is not published on the page and is not included here.',
 'https://www.msbml.ms.gov/licensure/md-do-permanent-renewal',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

-- =============================================================================
-- MISSISSIPPI -- advanced practice registered nurse (APRN)
-- Mississippi Board of Nursing. Miss. Code sec. 73-15-20; 30 Miss. Admin. Code
-- Part 2815 (continuing education) and Part 2840 (advanced practice).
-- =============================================================================
('MS','APRN','renewal_cycle_months', null, 24, null, null,
 '30 Miss. Admin. Code Part 2815, Ch. 1, Rule 1.6(A): "The APRN renewed licensure period is two (2) calendar years beginning January 01st of each odd-numbered year and expiring December 31st of each even-numbered year." The Board''s APRN page confirms the fee is for "Renewal even-numbered years".',
 'https://www.msbn.ms.gov/sites/default/files/documents/Part%202815%20-%20Continuing%20Education%20Requirements.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MS','APRN','ce_hours_total', null, 40, null, null,
 '30 Miss. Admin. Code Part 2815, Ch. 1, Rule 1.6(B): "APRN''s licensed in Mississippi shall complete a minimum of forty (40) contact hours of accepted continuing education per renewed licensure period." A maximum of 20 carryover hours from the prior period may be applied; new graduate APRNs initially licensed by exam are exempt for their initial licensure period.',
 'https://www.msbn.ms.gov/sites/default/files/documents/Part%202815%20-%20Continuing%20Education%20Requirements.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MS','APRN','ce_cycle_months', null, 24, null, null,
 '30 Miss. Admin. Code Part 2815, Ch. 1, Rules 1.6(A) and 1.6(B): the 40 contact hours are required "per renewed licensure period", and the APRN renewed licensure period is "two (2) calendar years".',
 'https://www.msbn.ms.gov/sites/default/files/documents/Part%202815%20-%20Continuing%20Education%20Requirements.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MS','APRN','ce_topic_controlled_substance_hours', null, 10, null, null,
 '30 Miss. Admin. Code Part 2815, Ch. 1, Rule 1.6(B)(3): "At least ten (10) contact hours of accepted continuing education must be directly related to controlled substances every renewed licensure period. Carryover hours may not be used to satisfy this requirement." Required of every Mississippi APRN, not only prescribers, and carved out of the 40 -- hence a plain per-cycle number.',
 'https://www.msbn.ms.gov/sites/default/files/documents/Part%202815%20-%20Continuing%20Education%20Requirements.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MS','APRN','initial_license_fee_cents', null, 10000, null, null,
 'Mississippi Board of Nursing, Advanced Practice Registered Nurse: "APRN Certification - Initial CNP, CRNA, CNM and Reinstatement : $100.00". A "Criminal Background Check : $75.00", a "Controlled Substance Prescriptive Authority (CSPA) : $100.00" and "Practice Site and Collaborative Physician : $25.00 (each)" are charged separately.',
 'https://www.msbn.ms.gov/licensure/advanced-practice-registered-nurse',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MS','APRN','renewal_fee_cents', null, 10000, null, null,
 'Mississippi Board of Nursing, Advanced Practice Registered Nurse: "Renewal even-numbered years : $100.00".',
 'https://www.msbn.ms.gov/licensure/advanced-practice-registered-nurse',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MS','APRN','collaborative_agreement_required', null, null, true, null,
 'Mississippi Board of Nursing, Advanced Practice Registered Nurse: "Collaborative Physician : All APRNs (NPs, CRNAs, and CNMs) must have at least one collaborative physician for each practice site." "You are able to get an APRN license without a practice site and collaborating physician, but you MAY NOT begin work until you have an approved practice site, collaborating physician of compatible practice and a collaborative agreement." Agreements are entered "in accordance with 30 Miss. Admin, Code, Pt. 2840, R. 2.3".',
 'https://www.msbn.ms.gov/licensure/advanced-practice-registered-nurse',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MS','APRN','csr_required', null, null, true, null,
 'Mississippi Board of Nursing, Advanced Practice Registered Nurse: "Every certified APRN authorized to practice in Mississippi who prescribes any controlled substances (Schedules II, III, IV, or V) within Mississippi or who proposes to engage in the prescribing of any controlled substance within Mississippi must be registered with the U.S. Drug Enforcement Administration (DEA) ..., and must also apply for this privilege with the Mississippi Board of Nursing. CSPA is not automatically granted with an APRN license in Mississippi." The Board further directs: "Do Not apply for a DEA registration prior to being issued prescriptive authority by the MBON." A state controlled-substance credential separate from and prerequisite to the DEA registration.',
 'https://www.msbn.ms.gov/licensure/advanced-practice-registered-nurse',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('MS','APRN','csr_fee_cents', null, 10000, null, null,
 'Mississippi Board of Nursing, Advanced Practice Registered Nurse, fee list: "Controlled Substance Prescriptive Authority (CSPA) : $100.00".',
 'https://www.msbn.ms.gov/licensure/advanced-practice-registered-nurse',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

-- =============================================================================
-- KENTUCKY -- physician (MD)
-- Kentucky Board of Medical Licensure. KRS ch. 311; 201 KAR ch. 9.
-- ANNUAL registration against a THREE-YEAR CME cycle -- the clocks differ.
-- =============================================================================
('KY','MD','renewal_cycle_months', null, 12, null, null,
 '201 KAR 9:051, Section 1(1): "On or about January 1 of each year, the executive director shall mail written notification to all physicians holding a regular license ... that annual registration of their license must be executed on or before March 1." 201 KAR 9:041, Section 1(3) prices the "annual registration or renewal of regular license".',
 'https://apps.legislature.ky.gov/law/kar/titles/201/009/051/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('KY','MD','ce_hours_total', null, 60, null, null,
 '201 KAR 9:310, Section 3(1)(a): "For each three (3) year continuing education cycle, a licensee shall complete a total of sixty (60) hours of continuing medical education, if his or her license has been renewed for each year of a continuing medical education cycle." Section 2(1) requires that "thirty (30) of the sixty (60) hours were certified in Category I".',
 'https://apps.legislature.ky.gov/law/kar/titles/201/009/310/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('KY','MD','ce_cycle_months', null, 36, null, null,
 '201 KAR 9:310, Section 3(1)(a) and Section 3(2): the requirement runs on a "three (3) year continuing education cycle", and the licensee certifies compliance "Upon renewal of licensure following the end of a three (3) year continuing education cycle". The Board publishes the current cycle as January 1, 2024 - December 31, 2026. NOTE the CME cycle is 36 months while registration is annual -- the two clocks are NOT the same.',
 'https://apps.legislature.ky.gov/law/kar/titles/201/009/310/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('KY','MD','ce_topic_controlled_substance_hours', null, null, null,
 '{"hours": 4.5, "periodicity": "per_3_year_ce_cycle", "applies_to": "licensees authorized to prescribe or dispense controlled substances in Kentucky at any time during the cycle", "topics": ["use of KASPER", "pain management", "addiction disorders"], "prorated_for_partial_cycle": {"two_years": 3, "one_year": 1.5}}'::jsonb,
 '201 KAR 9:310, Section 5(1): "For each three (3) year continuing education cycle beginning on January 1, 2015, a licensee who is authorized to prescribe or dispense controlled substances within the commonwealth at any time during that cycle shall complete at least four and one-half (4.5) hours of approved continuing education hours relating to the use of KASPER, pain management, addiction disorders, or a combination of two (2) or more of those subjects." Conditional on prescribing authority, prorated for partial cycles, and on the 3-year CE clock rather than the annual registration clock.',
 'https://apps.legislature.ky.gov/law/kar/titles/201/009/310/',
 '2015-01-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('KY','MD','ce_topic_domestic_violence_hours', null, null, null,
 '{"hours": 3, "periodicity": "one_time", "window": "within 3 years of the date of initial licensure", "applies_to": "primary care physicians"}'::jsonb,
 'Kentucky Board of Medical Licensure, Continuing Medical Education Requirement Schedule 2024-2026: "Primary care physicians ... are required to successfully complete a three (3) hour domestic violence training course within 3 years of the date of initial licensure." ONE-TIME and limited to primary care; recorded as a per-cycle 3 it would invoice every Kentucky physician a fabricated duty every cycle.',
 'https://kbml.ky.gov/cme/Documents/CME%20Schedule%202024-2026.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('KY','MD','initial_license_fee_cents', null, 30000, null, null,
 '201 KAR 9:041, Section 1(1): "Fee for initial issuance of regular license - $300." (A graduate of a Kentucky medical school who remains in the state for postgraduate training pays $150 under subsection (15).)',
 'https://apps.legislature.ky.gov/law/kar/titles/201/009/041/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('KY','MD','renewal_fee_cents', null, 15000, null, null,
 '201 KAR 9:041, Section 1(3): "Fee for annual registration or renewal of regular license - $150." Late penalties are $50 (March 1 - April 1) and $100 (after April 1) under subsection (5).',
 'https://apps.legislature.ky.gov/law/kar/titles/201/009/041/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

-- =============================================================================
-- KENTUCKY -- advanced practice registered nurse (APRN)
-- Kentucky Board of Nursing. KRS ch. 314; 201 KAR ch. 20.
-- =============================================================================
('KY','APRN','renewal_cycle_months', null, 12, null, null,
 '201 KAR 20:215, Section 1(2): "''Earning period'' means November 1 through October 31 of a current licensure period", and Section 2(1) requires a licensee to validate continued competency "for each earning period". The Kentucky nursing licensure period is annual.',
 'https://apps.legislature.ky.gov/law/kar/titles/201/020/215/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('KY','APRN','ce_hours_total', null, null, null,
 '{"hours": 14, "periodicity": "per_earning_period", "earning_period": "November 1 through October 31", "note": "one of four alternative competency-validation methods under 201 KAR 20:215 Section 3; the others are national certification, a research project/publication/preceptorship, or 7 hours plus a satisfactory employment evaluation", "mandatory_regardless_of_method": "the Section 5 pharmacology hours"}'::jsonb,
 '201 KAR 20:215, Section 3(1): one method of validating continued competency is "Fourteen (14) contact hours of continuing education" from a board-approved provider, completed during the earning period. Sections 3(2)-(4) offer three alternatives (current national certification; a research project, peer-reviewed publication or 120-hour preceptorship; or seven hours plus a satisfactory employment evaluation). Because 14 is one of four alternatives rather than a universal duty, a bare 14 would invoice APRNs who validate competency another way.',
 'https://apps.legislature.ky.gov/law/kar/titles/201/020/215/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('KY','APRN','ce_cycle_months', null, 12, null, null,
 '201 KAR 20:215, Section 1(2): the "earning period" is "November 1 through October 31 of a current licensure period" -- a 12-month CE clock.',
 'https://apps.legislature.ky.gov/law/kar/titles/201/020/215/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('KY','APRN','ce_topic_pharmacotherapeutics_hours', null, 5, null, null,
 '201 KAR 20:215, Section 5(1)(a): "An Advanced Practice Registered Nurse (APRN) shall earn a minimum of five (5) contact hours in pharmacology, as required by KRS 314.073(9)." Required of every Kentucky APRN in every earning period, whichever competency-validation method is chosen. Section 5(1)(b) narrows the CONTENT for DEA-registered APRNs with a PDMP account (at least three of the five must be pain management or addiction disorders) without changing the count -- see requirement_conflicts.',
 'https://apps.legislature.ky.gov/law/kar/titles/201/020/215/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('KY','APRN','ce_topic_opioid_hours', null, null, null,
 '{"hours": 8, "periodicity": "one_time", "window": "after June 27, 2023 and before the APRN''s next scheduled DEA registration", "applies_to": "APRNs holding a DEA registration", "deemed_satisfied_if": ["graduated from an advanced practice nursing school within 5 years before June 27, 2023 with at least 8 hours in the curriculum", "already earned 8 hours on treating and managing opioid or other substance use disorders, including past DATA-Waiver trainings"]}'::jsonb,
 '201 KAR 20:215, Section 5(2): "After June 27, 2023, and before the APRN''s next scheduled DEA registration, an APRN who has a DEA registration shall earn a minimum of eight (8) hours on the subject of treating and managing patients with opioid or other substance use disorders, including the appropriate clinical use of all drugs approved by the Food and Drug Administration for the treatment of a substance use disorder." ONE-TIME, keyed to the DEA registration date rather than the nursing earning period, and with statutory deemed-satisfied pathways in Section 5(3).',
 'https://apps.legislature.ky.gov/law/kar/titles/201/020/215/',
 '2023-06-27', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('KY','APRN','initial_license_fee_cents', null, 16500, null, null,
 'Kentucky Board of Nursing, Fees for Licensure, Applications and Services: "APRN Initial/Endorsement ... $165". The underlying RN licence is a separate fee ($125 by examination, $165 by endorsement).',
 'https://kbn.ky.gov/KBN%20Documents/fees-for-licensure-applications-and-services.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('KY','APRN','renewal_fee_cents', null, 5500, null, null,
 'Kentucky Board of Nursing, Fees for Licensure, Applications and Services: "APRN Renewal ... $55 (Per designation)". The underlying RN licence renewal is a separate $65. NOTE the "per designation" qualifier: an APRN holding more than one population-focus designation pays $55 for each.',
 'https://kbn.ky.gov/KBN%20Documents/fees-for-licensure-applications-and-services.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

-- =============================================================================
-- LOUISIANA -- physician (MD) and APRN -- PARTIAL COVERAGE
-- Louisiana State Board of Medical Examiners (physicians); Louisiana Board of
-- Pharmacy (state CDS licence for ALL practitioners). La. R.S. 40:973.
-- Renewal cycle, CME totals and fees were NOT verified -- see the conflicts file.
-- =============================================================================
('LA','MD','renewal_window_days', null, 56, null, null,
 'Louisiana State Board of Medical Examiners, Renewals: "You will receive various renewal reminder notices as a courtesy; however, you may only renew 56 days before your expiration date." An explicit transactional open date.',
 'https://www.lsbme.la.gov/content/renewals',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('LA','MD','ce_topic_controlled_substance_hours', null, null, null,
 '{"hours": 3, "periodicity": "one_time", "deadline": "before the prescriber''s first license or permit renewal date", "applies_to": "practitioners holding a Louisiana Controlled Dangerous Substance (CDS) license", "required_content": ["best practices for the prescribing of CDS", "drug diversion training", "appropriate treatment for addiction", "treatment of chronic pain"], "exemption": "attestation of no CDS prescribed, administered or dispensed in Louisiana during the year before expiration, verified against the Louisiana PMP; residents (PGY and GETP) may not claim it"}'::jsonb,
 'Louisiana State Board of Medical Examiners, Board Approved CME Courses for CDS Requirements: "In 2017 the legislature passed a law requiring that all practitioners with a Controlled Dangerous Substance (CDS) license in Louisiana complete at least three hours of Board PRE-APPROVED continuing medical education (CME) ... This is a once in a lifetime requirement under current law." "The three hours of CDS-CME must be completed before the prescriber''s first license/permit renewal date." ONE-TIME (Act 76; Board rule sec. 4005); recorded as an annual 3 it would invoice every Louisiana prescriber a fabricated duty every year.',
 'https://www.lsbme.la.gov/content/board-approved-cme-courses-cds-requirements',
 '2017-01-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('LA','MD','csr_required', null, null, true, null,
 'Louisiana Board of Pharmacy, Application Process Transparency - CDS License - Practitioners: a Louisiana Controlled Dangerous Substances licence is required of "Every person who conducts research with, manufactures, distributes, procures, possesses, prescribes, or dispenses any controlled dangerous substance", the practitioner categories listed including MD. This is a Louisiana state licence issued by the Board of Pharmacy, distinct from federal DEA registration.',
 'https://www.pharmacy.la.gov/page/application-process-transparency-cds-license-practitioners',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('LA','MD','csr_fee_cents', null, 4500, null, null,
 'Louisiana Board of Pharmacy, Application Process Transparency - CDS License - Practitioners: the application fee for practitioner categories including MD is "$45.00" (veterinarians $20.00). SCOPE NOTE: this is the APPLICATION fee; the Board page does not state the renewal fee or the licence term -- see requirement_conflicts.',
 'https://www.pharmacy.la.gov/page/application-process-transparency-cds-license-practitioners',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('LA','APRN','csr_required', null, null, true, null,
 'Louisiana Board of Pharmacy, Application Process Transparency - CDS License - Practitioners: a Louisiana Controlled Dangerous Substances licence is required of "Every person who conducts research with, manufactures, distributes, procures, possesses, prescribes, or dispenses any controlled dangerous substance", and APRN is named among the practitioner categories. Distinct from federal DEA registration.',
 'https://www.pharmacy.la.gov/page/application-process-transparency-cds-license-practitioners',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('LA','APRN','csr_fee_cents', null, 4500, null, null,
 'Louisiana Board of Pharmacy, Application Process Transparency - CDS License - Practitioners: the CDS application fee for APRN is "$45.00". APPLICATION fee only; renewal fee and licence term not published on the page.',
 'https://www.pharmacy.la.gov/page/application-process-transparency-cds-license-practitioners',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

-- =============================================================================
-- WEST VIRGINIA -- physician (MD) -- PARTIAL COVERAGE
-- West Virginia Board of Medicine. W. Va. Code ch. 30 art. 3; 11 CSR 6.
-- Fees, renewal window, CSR status and ALL APRN fields were NOT verified.
-- =============================================================================
('WV','MD','renewal_cycle_months', null, 24, null, null,
 'West Virginia Board of Medicine, Continuing Education - Medical Doctors: "The term ''reporting period'' means the two-year period preceding the renewal deadline for a license issued by the Board. For example, if a license is scheduled to expire on June 30, 2026, the reporting period is July 1, 2024 through the 2026 renewal application submission date." The same page refers to "the biennial CME obligation". The Board''s fee sheet states its fees "are based on a 2-year renewal cycle".',
 'https://wvbom.wv.gov/Cont_Med_Education.asp',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('WV','MD','ce_hours_total', null, 50, null, null,
 'West Virginia Board of Medicine, General CME Requirements: "MDs and DPMs - min. 50 hours in preceding 2 years; include at least 30 hours in area(s) of specialty; min. 3 hours of drug diversion training and best practice prescribing of controlled substances". (Physician assistants are held to 100 hours.)',
 'https://wvbom.wv.gov/www/download_resource.aspx?ID=485',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('WV','MD','ce_cycle_months', null, 24, null, null,
 'West Virginia Board of Medicine, General CME Requirements: the 50 hours are measured "in preceding 2 years"; the Continuing Education - Medical Doctors page defines the "reporting period" as "the two-year period preceding the renewal deadline". The CE cycle is the biennial renewal cycle.',
 'https://wvbom.wv.gov/Cont_Med_Education.asp',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true),

('WV','MD','ce_topic_controlled_substance_hours', null, null, null,
 '{"hours": 3, "periodicity": "per_reporting_period", "applies_to": "physicians who prescribed, administered or dispensed any controlled substance pursuant to a West Virginia license during the two-year reporting period", "one_time": false, "board_preapproved_course_required": true, "new_licensee_rule": "a physician initially licensed after July 1, 2025 completes it within one year of initial licensure"}'::jsonb,
 'West Virginia Board of Medicine, Continuing Education - Medical Doctors: "Physicians who have prescribed, administered, or dispensed any controlled substance pursuant to a West Virginia license in the two-year reporting period preceding renewal, are required to complete 3-hours of Board-approved CME in Risk Assessment and Responsible Prescribing of Controlled Substances Training / Drug Diversion Training and Best Practice Prescribing of Controlled Substances Training during each reporting period. This is not a one-time only requirement." A physician may waive it by attesting that no controlled substances were or will be prescribed in the period. Conditional on actual prescribing activity, hence value_json.',
 'https://wvbom.wv.gov/Cont_Med_Education.asp',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, true);

commit;
