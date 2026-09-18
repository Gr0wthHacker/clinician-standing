-- =============================================================================
-- requirements_seed_group_e.sql -- the rules asset, group E: the five states
-- earlier passes could not reach.
--
-- AR, OK, KS, NJ, WV x { physician (MD), nurse practitioner (APRN) }.
--
-- Companion to requirements_seed.sql (CA, FL, TX, NY) and the group A-D files,
-- whose conventions this file follows exactly. This file owns ONLY rows tagged
-- verified_by = 'research-agent-group-e' and deletes only those.
--
-- WHAT THIS FILE IS FOR
--   AR and OK had ZERO rows. KS had one (APRN renewal period). NJ had two.
--   WV had four, physician only. Every row below is NEW: no row here duplicates
--   or contradicts an is_current row written by another agent, because
--   ux_requirements_current permits exactly one current row per
--   (state, license_type, field_key). Where this pass found something that
--   CONTRADICTS an existing row owned by another agent -- and it did, twice,
--   in West Virginia -- the finding is recorded in
--   requirement_conflicts_seed_group_e.sql instead of being written here.
--
-- VERIFICATION STANDARD (read db/seeds/README.md before editing):
--   Every row below carries a citation to a state board page, a state statute,
--   or a board rule that was FETCHED AND READ on 2026-09-18. No row is written
--   from recall, from a CE aggregator, from a licence-service marketplace, from
--   a third-party code republisher (Cornell LII, Justia, Casetext were used for
--   NOTHING, not even orientation citations), or from a neighbouring state.
--   Where a value could not be verified from a primary source it is NOT in this
--   file -- it is in requirement_conflicts_seed_group_e.sql as an open conflict.
--   An open conflict blocks auto-clear (PRD 8.1 condition 6) and raises
--   RULE_UNCERTAIN (PRD 8.3), which is the correct behaviour for a value we do
--   not know.
--
-- VALUE COLUMN CONVENTION
--   value_num   a plain per-cycle quantity (months, days, hours, cents).
--   value_bool  a plain yes/no.
--   value_json  a quantity that is NOT simply "this much, every cycle" --
--               one-time requirements, requirements on a different clock than
--               the renewal cycle, requirements that apply only to a subset of
--               licensees, and (in this file) FEES AND HOUR COUNTS THAT ARE NOT
--               SCALARS. Five of this group's states publish at least one such
--               value: Kansas prices the same physician renewal at two amounts
--               (paper $430 / online $360); Kansas states its physician CE duty
--               as three alternative credit/lookback pairs; Arkansas and
--               Oklahoma both state the nurse's continuing-competency duty as a
--               menu of alternatives of which continuing education is only one;
--               West Virginia prices its controlled-substance dispensing
--               registration at $30 or $15 per location depending on which
--               alphabetical renewal cohort the physician is in.
--               Consumers MUST branch on the presence of value_json.
--
--   license_type 'MD' and 'APRN' match the vocabulary in 0003_credentials.sql.
--   DO IS NOT COVERED. Note in particular that OKLAHOMA HAS A SEPARATE
--   OSTEOPATHIC BOARD (OAC Title 510, State Board of Osteopathic Examiners);
--   the OK/MD rows below come from OAC Title 435 and must NOT be applied to an
--   Oklahoma DO. See the conflicts file.
--
-- NEW field_key introduced by this file -- ONE:
--   ce_topic_nutrition_hours   (WV/MD)
-- West Virginia's Board of Medicine adopted an emergency legislative rule
-- (11 CSR 6, filed 30 June 2026, effective 11 August 2026) that inserts a
-- mandatory 2 hours of Nutrition CME into ALL THREE of the physician CME
-- options. No existing field_key covers it; ce_topic_nutrition_hours satisfies
-- requirements_field_key_chk. It is reported in the agent report and in
-- COVERAGE.md.
--
-- Fees are in cents and are the amount the licensee actually pays where the
-- board publishes a single total; component breakdowns are in the citation.
-- WHERE A CREDENTIAL SITS ON TOP OF ANOTHER CREDENTIAL (an Arkansas, Kansas,
-- Oklahoma or West Virginia APRN must also hold and renew an RN licence) the
-- fee seeded is the fee for the ADVANCED credential, following the convention
-- set by CA/APRN in requirements_seed.sql, and the citation names the other
-- amounts the licensee pays at the same time. A linked conflict says so.
--
-- Idempotent: safe to re-run. Respects ux_requirements_current (one is_current
-- row per state/license_type/field_key).
-- =============================================================================

begin;

-- Re-running replaces only the rows this file owns. requirement_conflicts rows
-- written by requirement_conflicts_seed_group_e.sql point at these rows, so
-- they are cleared first; re-run the conflicts file AFTER this one.
delete from requirement_conflicts
 where observed_by = 'research-agent-group-e'
   and requirement_id in (
         select id from requirements
          where verified_by = 'research-agent-group-e'
            and state in ('AR','OK','KS','NJ','WV')
            and license_type in ('MD','APRN'));

delete from requirements
 where verified_by = 'research-agent-group-e'
   and state in ('AR','OK','KS','NJ','WV')
   and license_type in ('MD','APRN');

insert into requirements
  (state, license_type, field_key,
   value_text, value_num, value_bool, value_json,
   citation, citation_url, effective_date,
   verified_at, verified_by, version, is_current)
values

-- =============================================================================
-- ARKANSAS -- medical doctor (MD)
-- Arkansas State Medical Board. Ark. Code title 17 ch. 95; ASMB Regulation 17.
-- ARKANSAS RENEWS PHYSICIANS ANNUALLY, IN THE BIRTH MONTH, WITH NO GRACE
-- PERIOD. Every other state in this file renews physicians annually (OK, KS)
-- or biennially (NJ, WV); do not carry a value across.
-- =============================================================================
('AR','MD','renewal_cycle_months', null, 12, null, null,
 'Arkansas State Medical Board, Instructions - Physician Licensure Applications (MD_AppPack, rev. 4/15/2026): physicians renew annually, before the last day of the birth month, with no grace period, and "Your first renewal notification will be sent to you via email 60 days prior to the end of your birth month." Corroborated by the Board''s Licensing FAQ, which states the CME requirement as "20 hours annually" measured "from birth month of previous year through birth month of current year", and by the Board''s Fee Schedule, which lists a single "License Renewal - M.D./ D.O. $11".',
 'https://www.armedicalboard.org/Professionals/pdf/MD_AppPack.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('AR','MD','ce_hours_total', null, 20, null, null,
 'Arkansas State Medical Board, Licensing FAQ (MD/DO): "20 hours annually. Reference Regulation 17 in the Arkansas Medical Practices Acts & Regulations. CME hours must be from birth month of previous year through birth month of current year." The same answer adds that "50% of CME hours must be Category 1 and in the physician''s primary area of practice."',
 'https://armedicalboard.adh.arkansas.gov/faq.aspx?type=1',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('AR','MD','ce_cycle_months', null, 12, null, null,
 'Arkansas State Medical Board, Licensing FAQ (MD/DO): the 20 hours are required "annually" and "CME hours must be from birth month of previous year through birth month of current year", i.e. the CE cycle is the 12-month birth-month renewal cycle.',
 'https://armedicalboard.adh.arkansas.gov/faq.aspx?type=1',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('AR','MD','ce_topic_opioid_hours', null, null, null,
 '{"hours": 1, "periodicity": "annual", "subjects": ["prescribing opioids", "benzodiazepines"], "additive": false, "subset_of_field_key": "ce_hours_total", "note": "carved OUT OF the 20 annual hours, not added to them"}'::jsonb,
 'Arkansas State Medical Board, Licensing FAQ (MD/DO): "One of the 20 annual credits must be in the area prescribing opioids and/or benzodiazepines." Recorded as value_json because the hour is carved out of ce_hours_total rather than added to it; summing this onto the 20 over-bills every Arkansas physician by an hour a year.',
 'https://armedicalboard.adh.arkansas.gov/faq.aspx?type=1',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('AR','MD','initial_license_fee_cents', null, 12000, null, null,
 'Arkansas State Medical Board, Fee Schedule (PDF last modified 10 August 2026), Applications for License: "M.D./D.O. $20 Application + $100 CCVS Assessment = $120". Corroborated by the Board''s physician licensure instructions: "The fee for medical licensure is $120 ($20 (twenty) application fee plus $100 Centralized Credentials Verification Service (CCVS) Assessment)." CAVEAT ON THE SAME PAGE: the fee schedule states that a fee REDUCTION under Act 114 of 2023 "will be in effect beginning July 1, 2023 and end June 30, 2026 and the reduction may or may not apply in future years" -- a window that closed before this value was read. See the linked open conflict.',
 'https://www.armedicalboard.org/Professionals/pdf/Fees.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('AR','MD','renewal_fee_cents', null, 1100, null, null,
 'Arkansas State Medical Board, Fee Schedule (PDF last modified 10 August 2026), License Renewal: "M.D./ D.O. $11 ($50 late fee)". This is the lowest physician renewal fee in any of the 49 jurisdictions seeded across groups A-E and is stated plainly by the Board. SAME CAVEAT as the initial fee: the schedule''s Act 114 of 2023 reduction is stated to "end June 30, 2026", and the Board has published no post-reduction schedule. See the linked open conflict.',
 'https://www.armedicalboard.org/Professionals/pdf/Fees.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

-- =============================================================================
-- ARKANSAS -- advanced practice registered nurse (APRN)
-- Arkansas State Board of Nursing (ASBN), an Arkansas Department of Health
-- board. Ark. Code title 17 ch. 87; ASBN Rules ch. 2 and ch. 4.
-- An Arkansas APRN must hold BOTH an APRN licence and an active RN licence
-- (Arkansas RN or a compact multistate RN licence), and prescriptive authority
-- is a THIRD, separately-feed credential.
-- =============================================================================
('AR','APRN','renewal_cycle_months', null, 24, null, null,
 'Arkansas State Board of Nursing Rules ch. 2 sec. VII: "Each person licensed under the provisions of the Nurse Practice Act shall renew biennially." The Board''s Renewal of Arkansas License page adds the staggering rule: "The ASBN renews licenses on a staggered biennial birth date system. The first license that is issued may be valid from three (3) months to twenty-seven (27) months depending upon one''s birth date." The 24 months is the STEADY-STATE cycle; a first licence is not 24 months.',
 'https://healthy.arkansas.gov/wp-content/uploads/ASBN_Rules.Chapter02.SectionVII.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('AR','APRN','renewal_window_days', null, 60, null, null,
 'Arkansas State Board of Nursing, Renewal of Arkansas License: "The renewal link will be available 60 days prior to license expiration." This is a TRANSACTIONAL open date, not merely a notice date; the Board separately states in Rules ch. 2 sec. VII that renewal notices are mailed "Sixty (60) days prior to the expiration date."',
 'https://healthy.arkansas.gov/boards-commissions/boards/nursing-arkansas-state-board/renewal-of-arkansas-license/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('AR','APRN','ce_hours_total', null, null, null,
 '{"options": [{"contact_hours": 15, "description": "appropriately accredited practice-focused activities"}, {"national_certification": true, "description": "hold a current nationally recognized certification/recertification"}, {"college_credit_hours": 1, "description": "minimum of one college credit hour course in nursing with a grade of C or better during the licensure period"}], "periodicity": "per_renewal_cycle", "attaches_to": "the underlying RN licence", "aprn_additional": "5 contact hours of pharmacotherapeutics, seeded separately as ce_topic_pharmacotherapeutics_hours"}'::jsonb,
 'Arkansas State Board of Nursing, Continuing Education: RN/LPN renewal requires "15 contact hours of appropriately accredited practice-focused activities, OR (2) Hold a current nationally recognized certification/recertification, OR (3) Completed a minimum of one college credit hour course in nursing with a grade of C or better during licensure period." The same page states APRNs owe "an additional five contact hours of pharmacotherapeutics related to their specialty certification" with each renewal. Recorded as value_json because continuing education is ONE OF THREE alternatives -- an Arkansas APRN who holds current national certification (which the Board separately requires at APRN renewal) may owe zero contact hours under this head. A consumer that schedules 15 hours for every Arkansas APRN is inventing an obligation.',
 'https://healthy.arkansas.gov/boards-commissions/boards/nursing-arkansas-state-board/education/continuing-education/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('AR','APRN','ce_cycle_months', null, 24, null, null,
 'Arkansas State Board of Nursing, Continuing Education: the RN/LPN continuing-education alternatives are stated for "Bi-annual renewal" and the APRN pharmacotherapeutics hours are required "with each renewal"; the Board''s APRN Renewal Application Information page states the pharmacotherapeutics hours must be obtained "within the last two (2) years". The CE cycle is the biennial renewal cycle.',
 'https://healthy.arkansas.gov/boards-commissions/boards/nursing-arkansas-state-board/renewal-of-arkansas-license/aprn-renewal-application-information/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('AR','APRN','ce_topic_pharmacotherapeutics_hours', null, null, null,
 '{"hours": 5, "periodicity": "per_renewal_cycle", "lookback_months": 24, "applies_to": "APRNs with prescriptive authority", "additive": true, "embedded_requirement": {"hours": 2, "of_the": 5, "subject": "maintaining professional boundaries and the prescribing rules, regulations, and laws that apply to APRNs in Arkansas"}}'::jsonb,
 'Arkansas State Board of Nursing, APRN Renewal Application Information: "Five (5) hours of pharmacotherapeutics continuing education in your area of APRN certification within the last two (2) years", and "Two (2) of the five (5) hours must contain information related to maintaining professional boundaries and the prescribing rules, regulations, and laws that apply to APRNs in Arkansas." Recorded as value_json because the duty applies only to the prescribing subset and carries an embedded 2-hour topic inside the 5.',
 'https://healthy.arkansas.gov/boards-commissions/boards/nursing-arkansas-state-board/renewal-of-arkansas-license/aprn-renewal-application-information/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('AR','APRN','initial_license_fee_cents', null, 12500, null, null,
 'Arkansas State Board of Nursing, Fees: "Original License - APRN $125.00". The Board''s footnote to the APRN column reads "* Must also hold a valid RN license", and the RN licence is separately feed ($100 by examination, $125 by endorsement). A Certificate of Prescriptive Authority for an APRN is a further $160.00. The seeded number is the ADVANCED credential''s own fee, per the CA/APRN convention.',
 'https://healthy.arkansas.gov/boards-commissions/boards/nursing-arkansas-state-board/licensing/fees/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('AR','APRN','renewal_fee_cents', null, 6500, null, null,
 'Arkansas State Board of Nursing, Fees: "License/Cert Renewal - APRN $65.00", footnoted "* Must also hold a valid RN license". The Arkansas RN licence renews at $100.00 on the same biennial clock, so an Arkansas APRN holding an Arkansas RN licence pays $165.00 in total at renewal; an APRN whose underlying RN licence is a compact multistate licence from another state pays only the $65.00 here. The seeded number is the APRN credential''s own fee. See the linked open conflict.',
 'https://healthy.arkansas.gov/boards-commissions/boards/nursing-arkansas-state-board/licensing/fees/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('AR','APRN','collaborative_agreement_required', null, null, null,
 '{"required": true, "instrument": "collaborative practice agreement submitted with the prescriptive authority application", "exception": "an APRN granted full independent practice authority by the Arkansas Full Independent Practice Credentialing Committee", "exception_threshold_hours": 6240, "exception_threshold_basis": "hours practised under a collaborative practice agreement", "statute": "Act 412 of 2021, expanded by Act 872 of 2023 to include Clinical Nurse Specialists"}'::jsonb,
 'Arkansas Department of Health, Full Independent Practice Credentialing Committee: full independent practice authority is available on completion of "6,240 hours under a collaborative practice agreement"; until approval is granted, APRNs "are required to maintain a current collaborative practice agreement". The Board of Nursing''s Prescriptive Authority / Collaborative Practice page states that "Prescriptive authority is not automatically issued with an APRN license in Arkansas" and directs applicants to submit a collaborative practice agreement with the prescriptive authority application. Recorded as value_json because the duty is extinguished for an identifiable, and growing, subset of the population.',
 'https://healthy.arkansas.gov/boards-commissions/committees/full-independent-practice-credentialing-committee/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

-- =============================================================================
-- OKLAHOMA -- medical doctor (MD)
-- Oklahoma State Board of Medical Licensure and Supervision.
-- 59 O.S. secs. 480-518.1; OAC Title 435 (rules effective 1 September 2026,
-- downloaded from the Board and cross-read against the Secretary of State's
-- Title 435 PDF).
-- OKLAHOMA RENEWS THE LICENCE ANNUALLY AND RUNS CME ON A THREE-YEAR CLOCK.
-- These are two different clocks; read renewal_cycle_months and
-- ce_cycle_months independently.
-- =============================================================================
('OK','MD','renewal_cycle_months', null, 12, null, null,
 'OAC 435:10-7-10 (Annual reregistration), Board rules effective 1 September 2026: "On an annual basis, each person licensed by the Board shall reregister with the Board. Reregistration shall be conducted during the month of initial licensure of each individual licensee by the Board." Subsection (b): "It shall be the affirmative duty of each licensee to comply with reregistration requirements. No grace period shall be allowed." The fee rule calls the same transaction an "Application for annual reregistration".',
 'https://www.okmedicalboard.org/download/2501/EFFECTIVE+RULES-MD+Rules_Eff._09.01.2026.pdf',
 '2026-09-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('OK','MD','initial_license_fee_cents', null, 50000, null, null,
 'OAC 435:1-1-7(a)(1)(A)(i), Board rules effective 1 September 2026: "Medical Doctor - Full license ... Initial application licensure fee - $500.00". A temporary licence is a further $250.00. The rule caps rather than merely states the amount: 435:1-1-7(a) provides that "the Board shall not set the fees at an amount in excess of the amounts listed in this subsection."',
 'https://www.okmedicalboard.org/download/2501/EFFECTIVE+RULES-MD+Rules_Eff._09.01.2026.pdf',
 '2026-09-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('OK','MD','renewal_fee_cents', null, 20000, null, null,
 'OAC 435:1-1-7(a)(2)(A), Board rules effective 1 September 2026: "Medical License - Full Licensure ... (i) Application for annual reregistration fee - $200.00; (ii) Late fee - $350.00; (iii) Reinstatement of license - $500.00."',
 'https://www.okmedicalboard.org/download/2501/EFFECTIVE+RULES-MD+Rules_Eff._09.01.2026.pdf',
 '2026-09-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('OK','MD','ce_hours_total', null, 60, null, null,
 'OAC 435:10-15-1(a)(2), Board rules effective 1 September 2026: "Requisite hours of CME shall be sixty (60) hours of Category I obtained during the preceding three (3) years as defined by the American Medical Association, Oklahoma State Medical Association, or the American Academy of Family Physicians." Subsection (a)(1): "Each applicant for re-registration (renewal) of licensure shall certify every three years that he/she has completed the requisite hours". Corroborated by the Board''s Licensing FAQ ("Each physician must have at least 60 Category 1 hours within the preceding three years") and by the Board''s CME Guidelines handout.',
 'https://www.okmedicalboard.org/download/2501/EFFECTIVE+RULES-MD+Rules_Eff._09.01.2026.pdf',
 '2026-09-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('OK','MD','ce_cycle_months', null, 36, null, null,
 'OAC 435:10-15-1(a)(1)-(2): certification is made "every three years" and the 60 Category I hours are "obtained during the preceding three (3) years". THE CE CYCLE IS THREE TIMES THE LICENCE CYCLE. An obligation generator that anchors CME to the annual reregistration in 435:10-7-10 will demand 60 hours a year instead of 60 every three years. 435:10-15-1(a)(3) adds that "Newly licensed physicians will be required to begin reporting three years from the date licensure was granted."',
 'https://www.okmedicalboard.org/download/2501/EFFECTIVE+RULES-MD+Rules_Eff._09.01.2026.pdf',
 '2026-09-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('OK','MD','ce_topic_pain_management_hours', null, null, null,
 '{"hours": 1, "periodicity": "annual", "alternatives": ["pain management", "opioid use or addiction"], "applies_to": "each licensee who has a current, valid federal Drug Enforcement Administration registration number", "statute": "59 O.S. sec. 495a.1(C)", "runs_on": "the 12-month reregistration clock, NOT the 36-month CME clock"}'::jsonb,
 'OAC 435:10-15-1(a)(4), Board rules effective 1 September 2026: "Each licensee who has a current, valid federal Drug Enforcement Administration registration number shall comply with 59 O.S sec. 495a.1(C) regarding education requirements for pain management or opioid use or addiction." The Board''s CME Guidelines handout states the statutory duty as "not less than one (1) hour of education in pain management or one (1) hour of education in opioid use or addiction each year", waived for licensees without a valid DEA registration. Recorded as value_json because it is ANNUAL while the general CME duty is triennial, and because it applies only to DEA registrants.',
 'https://www.okmedicalboard.org/cme/CMEguidelines.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('OK','MD','csr_required', null, null, true, null,
 'Oklahoma Bureau of Narcotics and Dangerous Drugs Control (OBN), Registration: "Every person who manufactures, distributes, dispenses, prescribes, administers or uses for scientific purposes any controlled dangerous substance" must obtain an OBN registration, and the published fee table charges "Practitioners and mid-level practitioners: $140.00 annually". THE REGISTRATION IS ISSUED BY OBNDD, NOT BY THE MEDICAL BOARD, AND RUNS ON ITS OWN CLOCK -- see csr_renewal_cycle_months.',
 'https://www.obndd.ok.gov/registration-pmp/registration',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('OK','MD','csr_fee_cents', null, 14000, null, null,
 'Oklahoma Bureau of Narcotics and Dangerous Drugs Control, Registration: "Practitioners and mid-level practitioners: $140.00 annually". (Medical facility owners and distributors pay $300.00, manufacturers $2,500.00.)',
 'https://www.obndd.ok.gov/registration-pmp/registration',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('OK','MD','csr_renewal_cycle_months', null, 12, null, null,
 'Oklahoma Bureau of Narcotics and Dangerous Drugs Control, Registration: "All registrations expire October 31st. New registrations approved prior to July 1st will expire October 31st of the same year. Registrations approved July 1st or after will expire the following year." OAC 475:10-1-9(e), read on the Bureau''s published 2025 Title 475, states that registrations "shall expire on October 31st of each year" and that "Renewal applications shall be considered timely only if submitted by September 1st of each year". THIS IS A FIXED-DATE ANNUAL CLOCK AND DOES NOT COINCIDE WITH THE BIRTH-MONTH LICENCE CLOCK: an Oklahoma physician has two separate annual renewals on two separate dates.',
 'https://www.obndd.ok.gov/registration-pmp/registration',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

-- =============================================================================
-- OKLAHOMA -- advanced practice registered nurse (APRN)
-- Oklahoma Board of Nursing. 59 O.S. secs. 567.1-567.19; OAC Title 485
-- (Board's rules effective 11 July 2026, downloaded from the Board).
-- Oklahoma splits the APRN into THREE credentials that renew together: the
-- APRN licence, prescriptive authority, and (for a minority) independent
-- prescriptive authority. Each carries its own fee and its own CE condition.
-- =============================================================================
('OK','APRN','renewal_cycle_months', null, 24, null, null,
 'OAC 485:10-15-5(a)(1), Board rules effective 11 July 2026: "Advanced Practice Registered Nurse renewal shall: (1) be concurrent with the two-year licensure renewal for Registered Nurse." OAC 485:10-16-6(1) says the same of prescriptive authority: renewal "shall be concurrent with the two-year RN licensure renewal and renewal of advanced practice registered nurse licensure." 485:10-15-5(a)(2) adds that renewal must "include a statement that the nurse''s national certification is current and that certification will be maintained during the period of licensure renewal."',
 'https://oklahoma.gov/content/dam/ok/en/nursing/documents/485rulesunofficialagencycopy26.pdf',
 '2026-07-11', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('OK','APRN','initial_license_fee_cents', null, 7000, null, null,
 'OAC 485:10-1-3(a)(1)(C), Board rules effective 11 July 2026: "Advanced Practice Registered Nurses (i) Licensure fee - $70.00; (ii) Prescriptive authority fee - $85.00; (iii) Authority to order, select, obtain and administer drugs - $85.00." The seeded number is the APRN licence itself; an Oklahoma APRN who will prescribe pays $155.00 or $240.00 at initial application, and the underlying RN licence is a separate $85.00 by examination.',
 'https://oklahoma.gov/content/dam/ok/en/nursing/documents/485rulesunofficialagencycopy26.pdf',
 '2026-07-11', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('OK','APRN','renewal_fee_cents', null, 4000, null, null,
 'OAC 485:10-1-3(a)(2), Board rules effective 11 July 2026, renewal fees charged "in accordance to the biennial licensure/certificate/recognition renewal schedule established by the Board": "(C) Advanced Practice Registered Nurse licensure - $40.00; (D) Prescriptive authority - $40.00; (E) Authority to order, select, obtain and administer drugs - $40.00." The underlying "(A) Registered Nurse/Licensed Practical Nurse license - $75.00" renews on the same clock. An Oklahoma APRN with prescriptive authority and an Oklahoma RN licence therefore pays $155.00 every two years. The seeded number is the APRN credential''s own fee. See the linked open conflict.',
 'https://oklahoma.gov/content/dam/ok/en/nursing/documents/485rulesunofficialagencycopy26.pdf',
 '2026-07-11', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('OK','APRN','ce_hours_total', null, null, null,
 '{"options": [{"work_hours": 520, "description": "employment in a position that requires a nursing license at the highest level of licensure"}, {"contact_hours": 24, "description": "continuing education applicable to nursing practice"}, {"national_certification": true, "description": "current certification in a nursing specialty area"}, {"refresher_course": true, "description": "Board-approved refresher course"}, {"academic_semester_credit_hours": 6, "description": "nursing coursework at the licensee''s current level of licensure or higher"}], "periodicity": "per_renewal_cycle", "lookback_months": 24, "attaches_to": "the underlying RN licence (OAC 485:10-7-3(d))", "aprn_licence_itself": "OAC 485:10-15-5 imposes NO continuing education hour count on the APRN licence; it conditions renewal on current national certification"}'::jsonb,
 'OAC 485:10-7-3(d), Board rules effective 11 July 2026: "each licensee shall demonstrate evidence of continuing qualifications for practice through completion of one or more of the following requirements within the past two years prior to the expiration date of the license: (1) Verify employment ... with verification of at least 520 work hours; or (2) Verify the completion of at least twenty-four (24) contact hours of continuing education applicable to nursing practice; or (3) Verify current certification in a nursing specialty area; or (4) Verify completion of a Board-approved refresher course; or (5) Verify completion of at least six (6) academic semester credit hours of nursing coursework". OAC 485:10-15-5, which governs APRN renewal, states NO hour count of its own. Recorded as value_json: continuing education is one of five alternatives and attaches to the RN credential, so a consumer that schedules 24 hours for every Oklahoma APRN is attributing an RN duty to an APRN credential and inventing an obligation for the majority who satisfy it by certification or by working.',
 'https://oklahoma.gov/content/dam/ok/en/nursing/documents/485rulesunofficialagencycopy26.pdf',
 '2026-07-11', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('OK','APRN','ce_cycle_months', null, 24, null, null,
 'OAC 485:10-7-3(d): the continuing-qualification alternatives must be satisfied "within the past two years prior to the expiration date of the license". OAC 485:10-16-6(2)(B) uses the same "two-year period immediately preceding the effective date of application for renewal" for the pharmacotherapeutics hours. The CE cycle is the biennial renewal cycle.',
 'https://oklahoma.gov/content/dam/ok/en/nursing/documents/485rulesunofficialagencycopy26.pdf',
 '2026-07-11', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('OK','APRN','ce_topic_pharmacotherapeutics_hours', null, null, null,
 '{"tiers": [{"applies_to": "APRNs with prescriptive authority who have NOT been granted independent prescriptive authority", "contact_hours": 15, "or_academic_credit_hours": 1, "subject": "pharmacotherapeutics, clinical application and use of pharmacological agents in the prevention of illness, and in the restoration and maintenance of health", "rule": "OAC 485:10-16-6(2)(B)"}, {"applies_to": "APRNs granted independent prescriptive authority", "category_i_cme_hours": 40, "rule": "OAC 485:10-16-6(2)(C)", "note": "may include the 15 contact hours if they meet Category I criteria"}], "periodicity": "per_renewal_cycle", "lookback_months": 24, "exemption": "does not apply to individuals renewing within twenty-four (24) months of initial prescriptive authority approval", "initial_application_requirement": {"contact_hours": 45, "category": "B", "or_academic_credit_hours": 3, "lookback_months": 36, "rule": "OAC 485:10-16-3(4)"}}'::jsonb,
 'OAC 485:10-16-6(2), Board rules effective 11 July 2026: renewal of prescriptive authority requires, "for applicants who have not been granted independent prescriptive authority by the Board, documentation approved by the Board verifying a minimum of fifteen (15) contact hours, or one academic credit hour of education, or the equivalent, in pharmacotherapeutics ... within the two-year period immediately preceding the effective date of application for renewal", and "for applicants who have been granted independent prescriptive authority by the Board, documentation approved by the Board verifying a minimum of forty (40) hours of Category I continuing medical education hours within the two-year period". The rule adds: "This documentation requirement does not apply to individuals renewing within twenty-four (24) months of initial prescriptive authority approval." Initial application requires 45 Category B contact hours or 3 academic credit hours within 3 years (485:10-16-3(4)). Recorded as value_json because the hour count depends on which of two prescriptive-authority tiers the APRN holds.',
 'https://oklahoma.gov/content/dam/ok/en/nursing/documents/485rulesunofficialagencycopy26.pdf',
 '2026-07-11', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('OK','APRN','ce_topic_pain_management_hours', null, null, null,
 '{"hours": 2, "periodicity": "per_renewal_cycle", "alternatives": ["pain management", "opioid use or addiction"], "applies_to": "APRNs renewing prescriptive authority", "waiver": "unless the APRN has demonstrated to the satisfaction of the Board that the APRN does not currently hold a valid federal Drug Enforcement Administration registration number", "rule": "OAC 485:10-16-6(2)(D)"}'::jsonb,
 'OAC 485:10-16-6(2)(D), Board rules effective 11 July 2026: renewal of prescriptive authority requires "documentation approved by the Board verifying two (2) hours of education in pain management or two (2) hours of education in opioid use or addiction, unless the Advanced Practice Registered Nurse has demonstrated to the satisfaction of the Board that the Advanced Practice Registered Nurse does not currently hold a valid federal Drug Enforcement Administration registration number." Recorded as value_json because it hangs on the PRESCRIPTIVE AUTHORITY credential and is waivable on the DEA condition. NOTE THE ASYMMETRY WITH THE PHYSICIAN: an Oklahoma MD owes 1 hour a YEAR (59 O.S. sec. 495a.1(C)); an Oklahoma APRN owes 2 hours every TWO years.',
 'https://oklahoma.gov/content/dam/ok/en/nursing/documents/485rulesunofficialagencycopy26.pdf',
 '2026-07-11', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('OK','APRN','supervision_required', null, null, null,
 '{"required": true, "instrument": "a written statement from an Oklahoma-licensed physician supervising prescriptive authority, on file with the Board", "scope": "prescribing only", "exception": "an APRN granted independent prescriptive authority by the Board", "exception_threshold_hours": 6240, "exception_threshold_basis": "clinical practice hours with prescriptive authority supervised by a physician", "exception_additional_condition": "evidence of insurance or proof of financial responsibility under 59 O.S. sec. 567.5b(A)", "change_notification_days": 30, "rules": ["OAC 485:10-16-5(b)", "OAC 485:10-16-3(3)", "OAC 485:10-16-3.2"]}'::jsonb,
 'OAC 485:10-16-5(b), Board rules effective 11 July 2026: "The Advanced Practice Registered Nurse must have a supervising physician on file with the Board, unless they have been granted independent prescriptive authority by the Board, prior to prescribing drugs or medical supplies. Changes to the written statement between the Advanced Practice Registered Nurse and supervising physician shall be filed with the Board within thirty (30) days of the change". OAC 485:10-16-3.2 sets the independent route: "completion of six thousand two hundred forty (6,240) clinical practice hours with prescriptive authority supervised by a physician", plus insurance or proof of financial responsibility. This is SUPERVISION of prescriptive authority, not a collaborative practice agreement, and collaborative_agreement_required is deliberately NOT seeded for Oklahoma -- see the conflicts file.',
 'https://oklahoma.gov/content/dam/ok/en/nursing/documents/485rulesunofficialagencycopy26.pdf',
 '2026-07-11', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('OK','APRN','csr_required', null, null, true, null,
 'Oklahoma Bureau of Narcotics and Dangerous Drugs Control, Registration: registration is required of "Every person who manufactures, distributes, dispenses, prescribes, administers or uses for scientific purposes any controlled dangerous substance", and the fee table charges "Practitioners and mid-level practitioners: $140.00 annually". OAC 475:10-1-4(c)(1), read on the Bureau''s published 2025 Title 475, uses the same phrase "practitioners and mid-level practitioners". The Board of Nursing separately provides at OAC 485:10-16-5(c) that an APRN prescribing Schedules III-V "will comply with state and Federal Drug Enforcement Administration (DEA) requirements prior to prescribing controlled substances."',
 'https://www.obndd.ok.gov/registration-pmp/registration',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('OK','APRN','csr_fee_cents', null, 14000, null, null,
 'Oklahoma Bureau of Narcotics and Dangerous Drugs Control, Registration: "Practitioners and mid-level practitioners: $140.00 annually".',
 'https://www.obndd.ok.gov/registration-pmp/registration',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('OK','APRN','csr_renewal_cycle_months', null, 12, null, null,
 'Oklahoma Bureau of Narcotics and Dangerous Drugs Control, Registration: "All registrations expire October 31st." THE OBN REGISTRATION RENEWS ANNUALLY WHILE THE APRN LICENCE RENEWS BIENNIALLY. An Oklahoma APRN who renews the OBN registration alongside the nursing licence will let it lapse in the intervening year.',
 'https://www.obndd.ok.gov/registration-pmp/registration',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

-- =============================================================================
-- KANSAS -- medical doctor (MD)
-- Kansas State Board of Healing Arts. K.S.A. ch. 65 art. 28 (Healing Arts Act);
-- K.A.R. agency 100.
-- The Board's web host (www.ksbha.ks.gov) refuses automated clients at the
-- Akamai edge; its regulation PDFs on the Board's legacy host (ksbha.org) do
-- not. Both were read. The Kansas Secretary of State's regulation site
-- (rules.ks.gov) is a JavaScript application with no server-rendered text and
-- its API rejects unauthenticated requests, so K.A.R. 100-15 was read from the
-- Board's own published PDFs.
-- =============================================================================
('KS','MD','renewal_cycle_months', null, 12, null, null,
 'Kansas State Board of Healing Arts, License Fees: the physician line items are "Annual renewal of active or federally active license" ($430.00 paper / $360.00 on-line) and "Late renewal of active or federally active license". K.S.A. 65-2809(a) is consistent: "In each case in which a license is renewed for a period of time of more or less than 12 months, the board may prorate the amount of the fee", i.e. 12 months is the standard period. The Board''s Renewal Dates table places every MD in one annual window (see renewal_window_days).',
 'https://www.ksbha.ks.gov/departments/licensing/license-fees',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('KS','MD','renewal_window_days', null, 47, null, null,
 'DERIVED BY DATE ARITHMETIC FROM THE BOARD''S OWN TABLE, NOT PUBLISHED AS A DAY COUNT. Kansas State Board of Healing Arts, Renewal Dates: the row "MD, MD Resident Active, TW" gives Renewal Cycle "May 15 - July 31" and Late Renewal "July 1 - July 31". On-time renewal therefore runs 15 May to 30 June: 17 days in May plus 30 in June = 47. K.S.A. 65-2809(d) supports the reading -- it gives a licensee who misses the renewal date a 30-day cure period on payment of an additional fee, which is the July window. See the linked open conflict; treat 47 as indicative.',
 'https://www.ksbha.ks.gov/departments/licensing/renewal-dates',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('KS','MD','initial_license_fee_cents', null, 30000, null, null,
 'Kansas State Board of Healing Arts, License Fees, Medical Doctor: "Application for active or federal active license: $300.00".',
 'https://www.ksbha.ks.gov/departments/licensing/license-fees',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('KS','MD','renewal_fee_cents', null, null, null,
 '{"online_cents": 36000, "paper_cents": 43000, "periodicity": "annual", "late_surcharge_online_cents": 10000, "late_surcharge_paper_cents": 23000, "note": "the Board prices the same renewal at two amounts depending on the channel used"}'::jsonb,
 'Kansas State Board of Healing Arts, License Fees, Medical Doctor: "Annual renewal of active or federally active license: Paper $430.00; On-line $360.00", and "Late renewal of active or federally active license: Paper +$230.00; On-line +$100.00". Recorded as value_json because there is no single amount: a Kansas physician pays $360 or $430 for the same act depending on whether the renewal is filed on-line. A scalar here would be wrong for whichever population it did not describe.',
 'https://www.ksbha.ks.gov/departments/licensing/license-fees',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('KS','MD','ce_hours_total', null, null, null,
 '{"options": [{"credits": 50, "lookback_months": 18, "category_i_min": 20, "category_iii_min": 1}, {"credits": 100, "lookback_months": 30, "category_i_min": 40, "category_iii_min": 2}, {"credits": 150, "lookback_months": 42, "category_i_min": 60, "category_iii_min": 3}], "credit_definition": "one credit for each 50 minutes actually spent in attendance at a continuing education activity (K.A.R. 100-15-4)", "first_renewal_exempt": true, "note": "the lookback windows are 18/30/42 months and NONE of them equals the 12-month licence renewal cycle"}'::jsonb,
 'K.A.R. 100-15-5(a)(1), as published by the Kansas State Board of Healing Arts: each licensee must show, for subparagraph (A), "During the 18-month period immediately preceding the license expiration date, the person completed at least 50 credits of continuing education, of which at least one credit shall be in category III, at least 20 credits shall be in category I"; for (B) "During the 30-month period ... at least 100 credits ... at least two credits ... category III, at least 40 credits ... category I"; for (C) "During the 42-month period ... at least 150 credits ... at least three credits ... category III, at least 60 credits ... category I". Subparagraph (a)(2) exempts a first-time renewal. Recorded as value_json because the duty is three alternative credit/lookback pairs and NONE of the lookbacks is the 12-month renewal cycle; a scalar 50 with an implied 12-month window would misstate the measurement period. See the linked open conflict.',
 'http://www.ksbha.org/documents/misc/100-15-5.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('KS','MD','ce_topic_opioid_hours', null, null, null,
 '{"credits": 1, "category": "III", "subjects": ["pain management", "opioid prescribing", "prescription drug monitoring programs"], "lookback_months": 18, "additive": false, "subset_of_field_key": "ce_hours_total", "scales_with_option": {"50_credits": 1, "100_credits": 2, "150_credits": 3}}'::jsonb,
 'K.A.R. 100-15-5(a)(1)(A), as published by the Kansas State Board of Healing Arts: of the 50 credits, "at least one credit shall be in category III". K.A.R. 100-15-4, as published by the same Board, defines category III as "an internet or live continuing education activity that also meets the requirements of either a category I or category II continuing education activity" while addressing pain management, opioid prescribing, or prescription drug monitoring programs. Recorded as value_json because the credit is carved OUT OF the total rather than added to it, and because the number scales with which of the three 100-15-5 options the licensee uses.',
 'http://www.ksbha.org/documents/misc/100-15-4.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

-- =============================================================================
-- KANSAS -- advanced practice registered nurse (APRN)
-- Kansas State Board of Nursing. K.S.A. 65-1113 to 65-1164; K.A.R. agency 60.
-- KS/APRN/renewal_cycle_months is owned by research-agent-group-c and is NOT
-- re-seeded here.
-- =============================================================================
('KS','APRN','renewal_window_days', null, 90, null, null,
 'Kansas State Board of Nursing, Renewal Application, Renewal Application Checklist: the first item a licensee must have is "An open renewal window? (90 days or less prior to your expiration date)". This is a transactional open date stated by the Board on the page a licensee uses to renew.',
 'https://ksbn.kansas.gov/renewal-application/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('KS','APRN','ce_hours_total', null, 30, null, null,
 'Kansas State Board of Nursing, Continuing Nursing Education: "Advanced Practice CNE renewal requirements: 30 contact hours of approved CNE related to the advanced practice registered nurse role during the most recent prior license period." (The RN licence underneath carries its own 30 contact hours, with the exception that no hours are owed "if license expires within 30 months following initial licensure examination or for renewal of license that expires within the first 9 months following licensure reinstatement or endorsement".) The Board defines 1 CNE contact hour as 50 minutes of learning and states that "CME ... [is] Not an acceptable for any licensure requirement in KS, unless approved through the IOA process".',
 'https://ksbn.kansas.gov/cnes/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('KS','APRN','ce_cycle_months', null, 24, null, null,
 'Kansas State Board of Nursing, Continuing Nursing Education: the 30 APRN contact hours are required "during the most recent prior license period", and the Board''s fee schedule and renewal application both describe the licence period as biennial ("Biennial renewal of license"). Consistent with K.S.A. 65-1132 as already seeded for KS/APRN/renewal_cycle_months.',
 'https://ksbn.kansas.gov/cnes/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('KS','APRN','initial_license_fee_cents', null, 5000, null, null,
 'Kansas State Board of Nursing, Agency Fees, "Advanced Practice Registered Nurses (APRNs) [KAR 60-11-119]": "Initial application for licensure: $50.00". The underlying RN licence is separately feed at $100.00 single-state or $125.00 multistate under K.A.R. 60-4-101, and all applicants owe a $57.00 criminal background check.',
 'https://ksbn.kansas.gov/fees/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('KS','APRN','renewal_fee_cents', null, 5500, null, null,
 'Kansas State Board of Nursing, Agency Fees, "Advanced Practice Registered Nurses (APRNs) [KAR 60-11-119]": "Biennial renewal of license: $55.00". Corroborated by the Board''s mail-in License Renewal Application (rev. 2026-03), which prices "NP: $55" and "RN: $85" as separate line items on the same form. The Board''s Renewal Application page states that "APRNs with Kansas RN licenses must fill out a renewal application for both licenses", so a Kansas APRN holding a Kansas RN licence pays $140.00 at renewal. The seeded number is the APRN credential''s own fee. See the linked open conflict.',
 'https://ksbn.kansas.gov/fees/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('KS','APRN','fingerprint_required', null, null, true, null,
 'Kansas State Board of Nursing, Fingerprints & Background Check: "All applicants must submit a criminal background check prior to issuance of a license. The cost for a criminal background check is $57." The page requires FBI Form FD-258 fingerprint cards and links an APRN-specific waiver and fingerprint instruction sheet ("APRN applications must use this Waiver Agreement and Fingerprint Instructions instead!"). Verified at INITIAL LICENSURE; the Board does not publish a fingerprint condition on renewal.',
 'https://ksbn.kansas.gov/fingerprints/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('KS','APRN','collaborative_agreement_required', null, null, false, null,
 'K.S.A. 65-1130(d)(1), Kansas Office of Revisor of Statutes (as amended L. 2022, ch. 65, sec. 1): "An advanced practice registered nurse may prescribe durable medical equipment and prescribe, procure and administer any drug consistent with such licensee''s specific role and population focus, except an advanced practice registered nurse shall not prescribe any drug that is intended to cause an abortion." Subsection (d)(3) states the ONLY conditions the statute attaches to prescribing controlled substances: "(A) Register with the federal drug enforcement administration; and (B) comply with federal drug enforcement administration requirements". The section imposes no collaborating physician, protocol or supervision condition; it does impose a malpractice insurance condition (d)(5). THIS IS AN AFFIRMATIVE GRANT PLUS A 2022 AMENDMENT, NOT MERE SILENCE, but it is partly established by what the statute does not say -- see the linked open conflict before relying on the false.',
 'https://ksrevisor.gov/statutes/chapters/ch65/065_011_0030.html',
 '2022-07-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

-- =============================================================================
-- NEW JERSEY -- medical doctor (MD) and advanced practice nurse (APRN)
-- Division of Consumer Affairs: State Board of Medical Examiners, Board of
-- Nursing, and the Drug Control Unit.
-- NEW JERSEY REMAINS THE THINNEST JURISDICTION IN THE WHOLE ASSET and this
-- pass improves it only partly. www.njconsumeraffairs.gov serves PDF assets to
-- automated clients but returns an Imperva/Incapsula challenge (HTTP 403, or a
-- 212-byte _Incapsula_Resource stub) for every .aspx page, and New Jersey
-- licenses the N.J.A.C. to LexisNexis rather than hosting it -- the Office of
-- Administrative Law's own "Access to Rules" page directs the public to
-- lexisnexis.com and warns that "the online version of the Code is not the
-- official Code." The rows below come from PDFs on the Division's own host.
-- =============================================================================
('NJ','MD','renewal_cycle_months', null, 24, null, null,
 'New Jersey State Board of Medical Examiners, "The Board of Medical Examiners LICENSING and the APPLICATION PROCESS" (Division of Consumer Affairs, August 2017), Renewals: "Renewal - Every two years"; "Licenses expire on June 30 of the ODD years"; "Every 2 years on odd years"; and "IF YOU DO NOT RENEW YOUR LICENSE WITHIN 30 DAYS OF EXPIRATION IT WILL BE AUTOMATICALLY SUSPENDED-EXPIRED WITHOUT FURTHER NOTICE TO YOU." THE SOURCE IS A BOARD DOCUMENT DATED AUGUST 2017 -- the only New Jersey physician renewal statement that could be retrieved on 2026-09-18. The biennial odd-year structure is a structural fact rather than a periodically re-set amount, which is why it is seeded and the fees on the same document are not. See the linked open conflict.',
 'https://www.njconsumeraffairs.gov/documents/licenseprocess/bme-licensing-august-2017.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('NJ','MD','csr_required', null, null, true, null,
 'New Jersey Office of the Attorney General, Division of Consumer Affairs, Drug Control Unit, Controlled Dangerous Substance Registration Initial Application (rev. 4/25): "Registration is required for every person who or firm that prescribes, manufactures, distributes, conducts research or analysis, or dispenses controlled dangerous substances within this State", pursuant to N.J.S.A. 24:21-1 et seq. "A dispenser/prescriber/practitioner includes medical doctors, doctors of osteopathy, dentists, optometrists, veterinarians, and podiatrists." CRITICALLY: "A New Jersey CDS registration is the prerequisite to the federal DEA registration" -- a New Jersey physician cannot obtain or keep a DEA registration without it. Federal facilities are excepted. The registration attaches to a physical practice location, not to the person: "A New Jersey CDS registration is issued to an actual location where controlled dangerous substances will be stored, prescribed, dispensed, etc."',
 'https://www.njconsumeraffairs.gov/dcu/Applications/Initial-Application-for-Registration-for-Dispenser-Prescriber-MidLevel-Practitioner.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('NJ','MD','csr_fee_cents', null, 4000, null, null,
 'New Jersey Drug Control Unit, CDS Registration Initial Application (rev. 4/25): "The CDS application fee is $40.00." The Unit''s registration FAQ states the same amount for renewal: "$40.00 for physicians, dentists, pharmacies, podiatrists, veterinarians, APNs, CNMs, PAs, researchers, analytical labs, narcotic treatment programs/methadone clinics, animal shelters and dog trainers/handlers."',
 'https://www.njconsumeraffairs.gov/dcu/Applications/Initial-Application-for-Registration-for-Dispenser-Prescriber-MidLevel-Practitioner.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('NJ','APRN','csr_required', null, null, true, null,
 'New Jersey Drug Control Unit, CDS Registration Initial Application (rev. 4/25): "A mid-level dispenser/prescriber/practitioner includes physician assistants, advanced practice nurses and certified nurse midwives", and registration is required of "every person who or firm that prescribes ... controlled dangerous substances within this State" under N.J.S.A. 24:21-1 et seq. "A New Jersey CDS registration is the prerequisite to the federal DEA registration." The same application corroborates the already-seeded NJ/APRN/collaborative_agreement_required: "Mid-Level practitioners are required to collaborate with and/or be supervised by physicians, consistent with agreed upon parameters of their respective practices."',
 'https://www.njconsumeraffairs.gov/dcu/Applications/Initial-Application-for-Registration-for-Dispenser-Prescriber-MidLevel-Practitioner.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('NJ','APRN','csr_fee_cents', null, 4000, null, null,
 'New Jersey Drug Control Unit, CDS Registration Initial Application (rev. 4/25): "The CDS application fee is $40.00." The Unit''s registration FAQ lists "APNs" and "CNMs" among the categories charged $40.00 on renewal.',
 'https://www.njconsumeraffairs.gov/dcu/Applications/Initial-Application-for-Registration-for-Dispenser-Prescriber-MidLevel-Practitioner.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

-- =============================================================================
-- WEST VIRGINIA -- medical doctor (MD)
-- West Virginia Board of Medicine. W. Va. Code ch. 30 art. 3; 11 CSR 1A, 4, 5,
-- and 6. WV/MD renewal_cycle_months, ce_hours_total, ce_cycle_months and
-- ce_topic_controlled_substance_hours are owned by research-agent-group-b and
-- are NOT re-seeded here; two of them are qualified in the conflicts file
-- because the Board's EMERGENCY LEGISLATIVE RULE effective 11 August 2026 does
-- not say what the Board's website says.
-- The fee handout that defeated the earlier pass is not the right document:
-- the fees are in the Board's legislative rule, 11 CSR 4, which extracts
-- cleanly.
-- =============================================================================
('WV','MD','initial_license_fee_cents', null, 40000, null, null,
 '11 CSR 4 sec. 2.1 (Board of Medicine, Series 4, Fees for Services Rendered, filed 6 April 2010, effective 1 May 2010): "Medical Licensure Application Fee - $400.00, $50.00 of which shall be promptly disbursed by the board to the physician health program." Corroborated by the Board''s Instructions - Physician Licensure Applications (rev. July 2025): "The initial application fee is $400." A temporary medical licence is $100.00 (sec. 2.3) and a medical school faculty licence $150.00 (sec. 2.6). W. Va. Code sec. 30-1-23 and 11 CSR 13 provide low-income and military-family waivers of the initial fee only.',
 'https://wvbom.wv.gov/download_resource.asp?id=263',
 '2010-05-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('WV','MD','renewal_fee_cents', null, 40000, null, null,
 '11 CSR 4 sec. 2.4 (Board of Medicine, Series 4, Fees for Services Rendered): "Active Medical and/or Podiatry Biennial Renewal Fee - $400.00, $50.00 of which shall be promptly disbursed by the board to the physician health program." An inactive renewal is $150.00 (sec. 2.5). The rule''s own words confirm the biennial cycle already seeded at WV/MD/renewal_cycle_months.',
 'https://wvbom.wv.gov/download_resource.asp?id=263',
 '2010-05-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('WV','MD','fingerprint_required', null, null, true, null,
 'West Virginia Board of Medicine, Instructions - Physician Licensure Applications (rev. July 2025), Initial License Application Components: "1. Fingerprint-Based Criminal History Record Check. Fingerprinting services are provided by IdentoGo for a fee. The 6-digit service code for the West Virginia Board of Medicine is 228Q9Z ... The Board is not permitted to utilize background checks performed for other entities. Background checks are valid for one year." The same document states under statutory requirements that "Applicants are required to request and submit to the Board the results of a fingerprint-based state and national/federal criminal history record check." Verified at INITIAL LICENSURE; on reactivation the check is required only if the licence has been expired 5 years or more, and the Board publishes no fingerprint condition on ordinary biennial renewal.',
 'https://wvbom.wv.gov/download_resource.asp?id=686',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('WV','MD','ce_topic_nutrition_hours', null, null, null,
 '{"hours": 2, "periodicity": "per_reporting_period", "reporting_period_months": 24, "additive_under_option_1": false, "subset_of_field_key_under_option_1": "ce_hours_total", "additive_under_options_2_and_3": true, "applies_to": "all physicians, under every one of the three CME options the Board recognises", "rule": "11 CSR 6 secs. 4.1.1.b, 4.1.2.a and 4.1.3.a", "status": "EMERGENCY RULE, filed 30 June 2026, effective 11 August 2026, sunset 1 August 2032"}'::jsonb,
 'NEW FIELD KEY. 11 CSR 6 (Board of Medicine, Series 6, Continuing Education for Physicians and Podiatric Physicians, EMERGENCY RULE, filing date 30 June 2026, effective date 11 August 2026): Option 1 requires 50 hours of AMA/AAFP Category I CME of which "At least 2 hours of the required 50 hours must be completed in the subject matter of Nutrition" (sec. 4.1.1.b); Option 2 (ABMS certification/recertification/MOC) requires "a minimum of 2 hours of Nutrition CME which is designated as Category I by the AMA or the AAFP" in addition (sec. 4.1.2.a); Option 3 (12 months of ACGME training) requires the same 2 hours in addition (sec. 4.1.3.a). The rule defines "Nutrition CME" as "continuing medical education which provides instruction in the role nutrition can play in the prevention, management and treatment of health conditions and diseases, and which provides strategies for incorporating nutrition into clinical practice" (sec. 2.12). Recorded as value_json because the 2 hours are carved out of the 50 under Option 1 but stand alone under Options 2 and 3. This duty is NOT on the Board''s Continuing Education - Medical Doctors web page, which is the source the earlier pass read.',
 'https://wvbom.wv.gov/download_resource.asp?id=904',
 '2026-08-11', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('WV','MD','csr_required', null, null, null,
 '{"required": false, "conditionally_required": true, "condition": "to dispense or administer a controlled substance in an office-based setting", "registration_is_per": "each office location where the practitioner dispenses or administers controlled substances", "not_required_for": ["inpatient hospital practice", "writing prescriptions which are to be dispensed by a pharmacy"], "credential": "Controlled Substance Dispensing Practitioner Registration, West Virginia Board of Medicine", "prerequisite": "a valid, unexpired and unrestricted federal DEA registration", "also_required": "current registration to access the West Virginia Controlled Substances Monitoring Program database"}'::jsonb,
 'West Virginia Board of Medicine, Controlled Substance Dispensing Practitioner Registration Application for Physicians, Podiatric Physicians and Physician Assistants: "To dispense or administer a controlled substance in an office-based setting, licensees of the Board must be registered as a controlled substance dispensing practitioner at each office location where the practitioner dispenses or administers controlled substances. Please note that this credential is only required if you administer and/or dispense controlled substances in an office-based practice. It is not required for: (1) inpatient hospital practice; or (2) to write prescriptions which are to be dispensed by a pharmacy." Recorded as value_json and as a QUALIFIED false: most West Virginia physicians do NOT need this credential, and a consumer that reads a bare true here will bill an obligation the majority of the population does not owe. Eligibility also requires that the applicant''s "DEA controlled substance registration number ... is valid, unexpired and is not subject to any restrictions or limitations" and that the applicant is "currently registered to access the West Virginia Controlled Substance Monitoring Program Database".',
 'https://wvbom.wv.gov/download_resource.asp?id=710',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('WV','MD','csr_fee_cents', null, null, null,
 '{"per_dispensing_location": true, "cohort_a_to_l_cents": 3000, "cohort_m_to_z_cents": 1500, "basis": "the fee depends on which biennial alphabetical renewal cohort the physician is in, because the registration is pro-rated to the licence expiry", "as_stated_for_applications_received_before": "2027-07-01", "note": "medical doctors whose last names begin A-L renew in even years and pay $30 per location; M-Z renew in odd years and pay $15 per location"}'::jsonb,
 'West Virginia Board of Medicine, Controlled Substance Dispensing Practitioner Registration Application: "Because controlled substance dispensing practitioner registrations renew at the same time as your license, the registration fee is based upon your renewal year. For applications received and processed prior to July 1, 2027, the registration fee is $30 per dispensing location for providers renewing in 2028 (medical doctors whose last names begin with the letters A through L). The registration fee for providers registering prior to July 1, 2027, and who will renew in 2027 (medical doctors whose last names begin with the letters M through Z, all podiatric physicians, and all physician assistants) is $15 per dispensing location." Recorded as value_json because the amount is per location AND depends on the licensee''s alphabetical cohort; no scalar is correct for the whole population.',
 'https://wvbom.wv.gov/download_resource.asp?id=710',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('WV','MD','csr_renewal_cycle_months', null, 24, null, null,
 'West Virginia Board of Medicine, Controlled Substance Dispensing Practitioner Registration Application: "controlled substance dispensing practitioner registrations renew at the same time as your license". The licence cycle is biennial, and the same paragraph confirms the alphabetical split that dates it: A-L physicians renew in even years, M-Z physicians in odd years, both by 30 June. UNLIKE Oklahoma and New Jersey, West Virginia does NOT run this registration on a clock separate from the licence.',
 'https://wvbom.wv.gov/download_resource.asp?id=710',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

-- =============================================================================
-- WEST VIRGINIA -- advanced practice registered nurse (APRN)
-- West Virginia Board of Registered Nurses (the Board of Examiners for
-- Registered Professional Nurses). W. Va. Code ch. 30 art. 7; 19 CSR 1, 3, 8.
-- Entirely new: the earlier pass never read this board.
-- WEST VIRGINIA RENEWS RNs AND APRNs IN DIFFERENT YEARS -- RNs in even years,
-- APRNs in odd years -- while making the APRN licence depend on the RN licence.
-- =============================================================================
('WV','APRN','renewal_cycle_months', null, 24, null, null,
 'West Virginia Board of Registered Nurses, Renewals: "Advanced Practice (APRN) May 1 - June 30 (Every Odd Year). APRN licenses (and Prescriptive Authority) renew biennially during odd-numbered years (e.g., 2027, 2029). Maintain active RN status to remain eligible." The Board adds the dependency that dates the real risk: "Your APRN license depends directly on maintaining an active RN license -- either a West Virginia RN license or an active multistate RN license from a Compact state. If your underlying RN license lapses or becomes invalid, your APRN license and Prescriptive Authority will automatically lapse as well, regardless of the APRN odd-year renewal schedule." The RN licence renews in EVEN years, so the two credentials are never due in the same year.',
 'https://wvrnboard.wv.gov/licensing/renewals',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('WV','APRN','renewal_window_days', null, 61, null, null,
 'DERIVED BY DATE ARITHMETIC FROM THE BOARD''S PUBLISHED WINDOW, NOT PUBLISHED AS A DAY COUNT. West Virginia Board of Registered Nurses, Renewals: "Advanced Practice (APRN) May 1 - June 30 (Every Odd Year)". 31 days in May plus 30 in June = 61. The Board states the open date explicitly and in terms that exclude an earlier one: "official West Virginia renewal windows open strictly on May 1", and warns that e-Notify notices sent on 1 April "are system-generated ... Please disregard early notices until the portal officially opens." See the linked open conflict.',
 'https://wvrnboard.wv.gov/licensing/renewals',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('WV','APRN','ce_hours_total', null, 24, null, null,
 'West Virginia Board of Registered Nurses, Continuing Education: "Each APRN must complete 24 contact hours of CE every two years -- specifically broken down as: 12 hours in pharmacotherapeutics (advanced pharmacology). 12 hours in clinical management (assessment, diagnosis, planning, and evaluation)." The 24 is fully allocated by the Board: there is no discretionary remainder. A West Virginia RN, by contrast, owes 12 contact hours per renewal cycle.',
 'https://wvrnboard.wv.gov/education/continuing-education',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('WV','APRN','ce_cycle_months', null, 24, null, null,
 'West Virginia Board of Registered Nurses, Continuing Education: the 24 contact hours are required "every two years", and the Board states the boundary explicitly: "the APRN license renewal period runs from July 1 of an odd year to June 30 of the next odd year." The CE cycle is the biennial renewal cycle.',
 'https://wvrnboard.wv.gov/education/continuing-education',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('WV','APRN','ce_topic_pharmacotherapeutics_hours', null, null, null,
 '{"hours": 12, "periodicity": "per_renewal_cycle", "reporting_period_months": 24, "additive": false, "subset_of_field_key": "ce_hours_total", "companion_allocation": {"hours": 12, "subject": "clinical management (assessment, diagnosis, planning, and evaluation)"}, "prescriptive_authority_condition": true, "initial_application_requirement": {"contact_hours": 45, "subject": "advanced pharmacology", "of_which_within_24_months": 15}}'::jsonb,
 'West Virginia Board of Registered Nurses, Continuing Education: of the APRN''s 24 contact hours every two years, "12 hours in pharmacotherapeutics (advanced pharmacology)". The Board''s Prescriptive Authority page states the same duty as a condition of keeping prescriptive authority: "12 contact hours in pharmacotherapeutics every 2 years ... Includes mandatory hours on Drug Diversion & Best Practice Prescribing", and sets the initial threshold at "45 contact hours of advanced pharmacology, 15 of which need to have been completed within 2 years of the application date." Recorded as value_json because the 12 hours are carved OUT OF the 24, not added to them: summing them over-bills every West Virginia APRN by half a cycle''s CE.',
 'https://wvrnboard.wv.gov/education/continuing-education',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('WV','APRN','ce_topic_controlled_substance_hours', null, null, null,
 '{"hours": 3, "periodicity": "one_time", "window": "within 1 year of initial licensure", "subjects": ["drug diversion", "best-practice prescribing", "opioid antagonist training"], "applies_to": "APRNs who prescribe, administer, or dispense controlled substances", "waiver": "an APRN licensed within the last year who did not prescribe, administer or dispense controlled substances may request a waiver by signed statement uploaded to CE Broker", "waiver_does_not_excuse": "the full 12 hours of pharmacotherapeutics and 12 hours of clinical management"}'::jsonb,
 'West Virginia Board of Registered Nurses, Continuing Education: "Controlled Substances Requirement: If you prescribe, administer, or dispense controlled substances, you must complete 3 hours in drug diversion, best-practice prescribing, and opioid antagonist training within 1 year of initial licensure." The Board publishes the exact waiver text and adds: "Even if granted a waiver for drug diversion training, APRNs must still complete the full 12 hours of pharmacotherapeutics and 12 hours of clinical management." Recorded as value_json because it is a ONE-TIME, first-year duty conditional on prescribing -- NOT a per-cycle duty. NOTE THE DIVERGENCE FROM WV/MD/ce_topic_controlled_substance_hours, which the earlier pass seeded as recurring every reporting period from the Board of Medicine''s website; see the conflicts file.',
 'https://wvrnboard.wv.gov/education/continuing-education',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('WV','APRN','initial_license_fee_cents', null, 3500, null, null,
 'West Virginia Board of Registered Nurses, Fees and Waivers, Official Schedule of Fees: "Initial APRN License Application $35.00". Initial Prescriptive Authority (APRN) is a separate $125.00, and the underlying RN licence is $70.00 by examination or $125.00 by endorsement. W. Va. Code sec. 30-1-23 waivers of the initial fee are available to low-income applicants and military families and "apply strictly to initial licensure applications".',
 'https://wvrnboard.wv.gov/licensing/fees-waivers',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('WV','APRN','renewal_fee_cents', null, 9000, null, null,
 'West Virginia Board of Registered Nurses, Fees and Waivers, Official Schedule of Fees: "APRN Renewal (Biennial) $90.00"; "APRN Prescriptive Authority Renewal (Biennial) $125.00"; "RN Renewal (Biennial) $90.00". West Virginia is the ONE state in this file where the advanced credential does not stack a second renewal fee on the licensee: "APRNs maintaining an active West Virginia APRN license have their prerequisite WV RN Renewal Fee waived ($90 savings) during the biennial RN renewal cycle." A West Virginia APRN with prescriptive authority therefore pays $215.00 per biennium in total. The Board also notes that "$20.00 of every biennial RN/APRN license renewal fee directly supports state Nurse Health Programs".',
 'https://wvrnboard.wv.gov/licensing/fees-waivers',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('WV','APRN','collaborative_agreement_required', null, null, null,
 '{"required": true, "instrument": "Collaborative Agreement for Prescriptive Authority with a collaborating physician, on the Board''s form", "scope": "prescriptive authority", "exception": "an APRN approved by the Board to have the collaborative agreement requirement removed", "notarisation_required": true, "held": "on-site at the practice location(s), not filed as the primary record", "notification_required_on": ["starting an agreement", "ending an agreement", "changing practice locations"], "authority": ["W. Va. Code sec. 30-7-1 et seq.", "Legislative Rule 19-08"]}'::jsonb,
 'West Virginia Board of Registered Nurses, Prescriptive Authority: "APRNs practicing under prescriptive authority must maintain a Collaborative Agreement for Prescriptive Authority with a collaborating physician, unless they have been approved by the Board to have the collaborative agreement requirement removed." The agreement "Must be signed by APRN and collaborating physician", the "APRN signature must be notarized", it is "Maintained on-site at practice location(s)", and "Notification [is] required upon starting or ending agreement". Recorded as value_json because the duty attaches to prescriptive authority rather than to the licence, and because the Board can remove it for an individual APRN.',
 'https://wvrnboard.wv.gov/licensing/prescriptive-authority',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true),

('WV','APRN','fingerprint_required', null, null, true, null,
 'West Virginia Board of Registered Nurses, Licensure Requirements: under "Statutory Eligibility Requirements ... In accordance with W. Va. Code sec. 30-7-1 et seq. and 19CSR03, all applicants for initial licensure must satisfy the following general qualifications: ... Criminal Background Check: Completed state and federal criminal history records checks via fingerprint submission", with the documentation item "State & Federal Background Check: Fingerprint completion via IdentoGO using the Board''s required service code." Verified at INITIAL LICENSURE; the Board publishes no fingerprint condition on biennial renewal.',
 'https://wvrnboard.wv.gov/licensing/requirements',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-e', 1, true);

commit;
