-- =============================================================================
-- requirement_conflicts_seed_group_a.sql -- what the group A rules asset does
-- NOT yet know, and where two official sources disagree.
--
-- PA, NJ, GA, MA, CT, MD, DC, DE, RI, NH, VT, ME x { MD, APRN }.
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
-- observed_by is 'research-agent-group-a' throughout: these are desk-research
-- findings, not observed board behaviour. Rows recording actual board behaviour
-- will be written by delivery (PRD 5.3).
--
-- Run AFTER requirements_seed_group_a.sql. Idempotent.
-- =============================================================================

begin;

delete from requirement_conflicts where observed_by = 'research-agent-group-a';

-- ---------------------------------------------------------------------------
-- B. QUALIFIERS on rows that exist.
-- ---------------------------------------------------------------------------
insert into requirement_conflicts
  (requirement_id, published_value, observed_value, observed_at, observed_by,
   occurrences, resolution, notes)
select r.id, c.published_value, c.observed_value,
       timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved', c.notes
from (values

-- ---- PENNSYLVANIA ---------------------------------------------------------
 ('PA','MD','ce_topic_opioid_hours',
  'State Board of Medicine CME Requirements document: at least TWO hours',
  'State Board of Medicine Physician & Surgeon Licensure Snapshot: FOUR hours',
  'TWO OFFICIAL BOARD PAGES DISAGREE ON THE SIZE OF THE SAME DUTY. The Board''s dedicated CME requirements document (MedM - CME MD Unrestricted License) says "all prescribers or dispensers ... complete at least two hours of continuing education in pain management, the identification of addiction or in the practices of prescribing or dispensing of opioids" (Act 124 of 2016, effective 1 January 2017). The Board''s Physician & Surgeon Licensure Snapshot says "4 hours of Board-approved education consisting of 2 hours in pain management or the identification of addiction and 2 hours in the practices of prescribing or dispensing of opioids" -- i.e. it reads the statutory disjunction as a conjunction and doubles the hours. The seeded value is 2, from the document whose sole purpose is to state CME requirements. OPEN: read 49 Pa. Code sec. 16.19 and Act 124 of 2016 directly; pacodeandbulletin.gov is disallowed by robots.txt to automated fetch and was not read. A client told 2 who owes 4 is out of compliance; a client told 4 who owes 2 is overbilled. Neither error is acceptable. Sources: https://www.pa.gov/content/dam/copapwp-pagov/en/dos/department-and-offices/bpoa/medicine/continuing-ed/MedM%20-%20CME%20MD%20Unrestricted%20License.pdf and https://www.pa.gov/agencies/dos/department-and-offices/bpoa/boards-commissions/medicine/physician---surgeon-licensure-snapshot'),

 ('PA','MD','renewal_window_days',
  '60 days ("approximately"), from a compact-licence renewal guide',
  'the Board publishes no renewal-open date for non-compact physician licences',
  'The only Pennsylvania statement of a renewal-open date that could be read on 2026-09-18 is in the BPOA "Renewal Guide for Compact Licenses" (rev. 7/2026): "Renewals are available approximately 60 days prior to the license expiration date." That guide addresses IMLC licensees. The Board''s own Renewal Information page states the expiration date but not when renewal opens. OPEN: confirm that 60 days is the transactional window for an ordinary Pennsylvania MD licence, and confirm whether "approximately" conceals a variable open date. Treat 60 as indicative, not guaranteed. Source: https://www.pa.gov/content/dam/copapwp-pagov/en/dos/department-and-offices/bpoa/medicine/imlc%20renewal%20guide%202026.pdf'),

 ('PA','APRN','collaborative_agreement_required',
  'true ("in collaboration with a licensed physician", CRNP Licensure Snapshot)',
  'the Board''s collaborative agreement guide does not state the agreement is mandatory outside prescribing',
  'Pennsylvania''s CRNP Licensure Snapshot defines a CRNP as performing duties "in collaboration with a licensed physician", and 49 Pa. Code sec. 21.283 and sec. 21.285 govern a PRESCRIPTIVE AUTHORITY collaborative agreement. The Board''s CRNP Prescriptive Authority Collaborative Agreement Application Guide, read on 2026-09-18, describes how to file such an agreement but contains no statement that one is mandatory, and says nothing about non-prescribing practice. The seeded boolean true is the conservative default. OPEN: read 49 Pa. Code ch. 21 subch. C in full (pacodeandbulletin.gov is robots-disallowed to automated fetch) and settle whether a non-prescribing CRNP must hold a collaboration instrument. Sources: https://www.pa.gov/agencies/dos/department-and-offices/bpoa/boards-commissions/nursing/certified-registered-nurse-practitioner-licensure-snapshot and https://www.pa.gov/content/dam/copapwp-pagov/en/dos/department-and-offices/bpoa/nursing/CRNP-Prescriptive-Authority-Collaborative-Agreement-Application-Guide.pdf'),

 ('PA','APRN','ce_topic_organ_donation_hours',
  '2 hours, one time within 5 years, effective 1 May 2026 (RN snapshot)',
  'verified on the RN licensure snapshot, not on the CRNP snapshot',
  'The Pennsylvania organ donation CE requirement was read on the Board of Nursing''s Registered Nurses Licensure Snapshot. A Pennsylvania CRNP must hold and renew a Pennsylvania RN licence, so the duty reaches this population, but the CRNP Licensure Snapshot does not itself list it and no CRNP-specific statement was found. OPEN: confirm the requirement appears on the CRNP renewal attestation, and confirm what "one time within 5 years" anchors to (date of first licensure, or a rolling 5-year lookback). Source: https://www.pa.gov/agencies/dos/department-and-offices/bpoa/boards-commissions/nursing/registered-nurses-licensure-snapshot'),

-- ---- NEW JERSEY -----------------------------------------------------------
 ('NJ','APRN','collaborative_agreement_required',
  'true (joint protocol with a collaborating physician, required before prescribing)',
  'verified only for prescribing; no other New Jersey board page could be reached',
  'The New Jersey Board of Nursing''s Advanced Practice Nurse Certification page states "An A.P.N. in New Jersey has prescriptive authority and is required to have a joint protocol with a collaborating physician who is licensed in New Jersey, prior to prescribing any medication or device." It does not address whether a non-prescribing APN needs the joint protocol, and it does not state whether the requirement has been modified by later legislation. njconsumeraffairs.gov is behind an Imperva/Incapsula bot wall that returned HTTP 403 (Incapsula incident IDs recorded) to every other automated fetch on 2026-09-18, and New Jersey does not publish the N.J.A.C. on a state-hosted site. OPEN: verify against N.J.S.A. 45:11-49 and the current N.J.A.C. 13:37 text; verify whether any 2023-2026 New Jersey enactment has removed or sunset the joint protocol. Source: https://www.njconsumeraffairs.gov/nur/Pages/APN-Certification.aspx'),

-- ---- GEORGIA --------------------------------------------------------------
 ('GA','APRN','ce_hours_total',
  'value_json: 30 hours, one of five continuing competency options',
  'a nationally-certified APRN may owe ZERO continuing education hours',
  'Ga. Comp. R. & Regs. ch. 410-13 offers five alternative ways to satisfy continuing competency: 30 CE hours, maintenance of national certification, an academic program of at least 2 credit hours, employer verification of 500+ practice hours, or a Board-approved reentry/nursing education programme. Every Georgia APRN must hold current national certification to keep APRN authorization (ch. 410-11), so the national-certification option will satisfy continuing competency for essentially the whole APRN population and the 30-hour figure will rarely bind. A consumer that reads the hours out of the JSON and schedules 30 hours of CE every two years for every Georgia APRN is inventing an obligation. OPEN: confirm with the Board whether APRN national certification is accepted as the continuing competency option at renewal. Source: https://rules.sos.ga.gov/gac/410-13'),

 ('GA','APRN','renewal_window_days',
  '92 days (1 November through 31 January)',
  'derived by date arithmetic from the Board''s stated window, not published as a day count',
  'The Georgia Secretary of State publishes the window as dates -- "For RNs and APRNs, the renewal period runs from November 1 through January 31" -- not as a number of days. 92 is 30 + 31 + 31. The derivation is exact, but it assumes the window is inclusive of both endpoints and that the November 1 open date is a standing rule rather than a per-cycle announcement. The Board''s Nursing Renewal Information page for the current cycle is consistent ("renewals opened November 1, 2025 and must be completed by January 31, 2026"). OPEN: confirm the window is fixed across cycles. Source: https://sos.ga.gov/how-to-guide/how-guide-aprn'),

-- ---- CONNECTICUT ----------------------------------------------------------
 ('CT','MD','renewal_cycle_months',
  '12 months (annual, birth month)',
  'partly established by ABSENCE from a published biennial list',
  'Connecticut DPH states generally that "Licenses are renewed annually during the licensee''s month of birth", and Physician/Surgeon does not appear on the Department''s published list of "Health Care Practitioner License Types that Expire Biennially". The affirmative general statement plus the specific negative list is stronger than silence, but DPH publishes no physician-specific renewal-frequency page, and C.G.S. ch. 370 could not be retrieved (cga.ct.gov returned repeated fetch errors for chap_370.htm on 2026-09-18). OPEN: confirm against C.G.S. sec. 19a-88 and sec. 20-10. THIS VALUE MATTERS MORE THAN MOST: Connecticut is the only state in this group that renews physicians annually, and every neighbouring state in this file renews biennially, so a consumer that carries a neighbour''s value across will be wrong by a factor of two. Sources: https://portal.ct.gov/dph/practitioner-licensing--investigations/plis/practitioner-licensure-general-policies-and-procedures and https://portal.ct.gov/dph/practitioner-licensing--investigations/renewal/health-care-practitioner-license-types-that-expire-biennially'),

 ('CT','MD','ce_cycle_months',
  '24 months',
  'the CE cycle is TWICE the 12-month licence renewal cycle',
  'This is not an error and must not be "corrected". C.G.S. sec. 20-10b, as published by DPH, requires "a minimum of fifty contact hours of qualifying continuing medical education within the preceding twenty-four month period", while the licence renews annually. An obligation generator that anchors CME to the renewal cycle will demand 50 hours every year instead of every two. OPEN: confirm how DPH treats the overlap -- whether the 24-month lookback is rolling at each annual renewal (so a given hour can satisfy two consecutive renewals) or whether CME is attested only at alternate renewals. That distinction changes the obligation calendar materially. Source: https://portal.ct.gov/dph/practitioner-licensing--investigations/physician/continuing-medical-education'),

 ('CT','MD','renewal_window_days',
  '60 days',
  'DPH states a notification date, not a renewal-open date',
  'Connecticut DPH says only that "Most licensees can expect to receive renewal notification approximately 60 days prior to expiration". It does not publish the date on which the eLicense renewal transaction opens, and does not say renewal is impossible before 60 days. Same defect as the seeded CA/MD figure in requirements_seed.sql. OPEN: confirm with DPH whether 60 days is the transactional window. Source: https://portal.ct.gov/dph/practitioner-licensing--investigations/renewal/health-care-practitioner-renewal-information'),

 ('CT','APRN','renewal_window_days',
  '60 days',
  'DPH states a notification date, not a renewal-open date',
  'Same defect as CT/MD/renewal_window_days: "You can expect a renewal notification sent to your email 60 days before your license expires" is a notice, not a transactional open date. Source: https://portal.ct.gov/dph/knowledge-base/articles/licensing/renew-a-nursing-license-online'),

 ('CT','APRN','ce_topic_infectious_disease_hours',
  '1 contact hour, seeded as a per-cycle value_num',
  'the analogous physician requirement runs on a first-renewal-then-every-6-years clock',
  'PERIODICITY ASYMMETRY BETWEEN TWO DPH PAGES. The Connecticut physician CME page attaches an explicit clock to each mandated topic: required "during the first renewal period requiring CME" and "not less than once every six years thereafter". The APRN continuing education page lists the same topic set (diseases/AIDS-HIV, risk management, sexual assault, domestic violence, cultural competency, substance abuse) with hour counts but attaches the six-year clock only to the veterans'' behavioral health topic. Either Connecticut genuinely requires these of APRNs every 24 months and of physicians only every six years, or the APRN page omits a qualifier. The five sibling rows CT/APRN/ce_topic_risk_management_hours, ce_topic_sexual_assault_hours, ce_topic_domestic_violence_hours, ce_topic_cultural_competency_hours and ce_topic_substance_abuse_hours carry the SAME defect and are covered by this conflict. Seeded as per-cycle value_num because that is what the APRN page states; if the six-year clock in fact applies, the platform will over-generate these obligations by a factor of three. OPEN: confirm against Regs. Conn. State Agencies sec. 20-94b and C.G.S. sec. 20-94c. Sources: https://portal.ct.gov/dph/practitioner-licensing--investigations/aprn/continuing-education and https://portal.ct.gov/dph/practitioner-licensing--investigations/physician/continuing-medical-education'),

-- ---- MARYLAND -------------------------------------------------------------
 ('MD','MD','ce_hours_total',
  'COMAR 10.32.01.10C(1) and the Board renewal page: 50 credits of Category I OR II, of which at least 25 Category 1',
  'Maryland Board of Physicians Physician Renewal FAQ: "at least 50 Category 1 CME credits"',
  'TWO OFFICIAL SOURCES DISAGREE ON THE COMPOSITION, THOUGH NOT THE TOTAL. The regulation and the Board''s Physician License Renewals page both say 50 credits of Category I or II with at least 25 in Category 1. The Board''s own Physician Renewal FAQ says "Physicians must earn at least 50 Category 1 CME credits two years before their license expires", which would double the Category 1 burden. The seeded row follows the regulation. A licensee who plans to the FAQ over-earns; one who plans to the regulation is compliant. OPEN: ask the Board to correct the FAQ. Sources: https://regs.maryland.gov/us/md/exec/comar/10.32.01.10, https://www.mbp.state.md.us/licensure_phyrenewals.aspx and https://www.mbp.state.md.us/resource_information/faqs/resource_faqs_physician_renewals.aspx'),

 ('MD','MD','renewal_window_days',
  '78 days (15 July through 30 September)',
  'derived by date arithmetic; the Board alternates halves of the alphabet year by year',
  'The Maryland Board of Physicians publishes the window as dates, not as a day count: "The biennial license renewal period starts on July 15, 2025" with the fee due "by 11:59 pm (EST) on September 30, 2025". 78 = 17 (15-31 July) + 31 (August) + 30 (September). The Board renews surnames A-L in one year and M-Z in the next, so an individual physician sees this window every 24 months, not every 12. OPEN: confirm the July 15 open date is fixed across cycles rather than announced per cycle. Sources: https://www.mbp.state.md.us/forms/2025_renewal_info.pdf and https://www.mbp.state.md.us/licensure_phyrenewals.aspx'),

 ('MD','APRN','ce_hours_total',
  'value_json: 30 CEUs, one of several alternatives',
  'COMAR 10.27.07.04 imposes NO CE hour requirement on the nurse practitioner certification itself',
  'Maryland splits the duty across two chapters. COMAR 10.27.01.13 attaches 30 CEUs (or practice hours, or completion of education) to the REGISTERED NURSE licence. COMAR 10.27.07.04 conditions renewal of the NURSE PRACTITIONER certification on current national certification, a completed application and fees -- and states no CE hour count at all. A consumer that treats the 30 as the nurse practitioner''s CE obligation is attributing an RN duty to an APRN credential. OPEN: confirm whether the Board audits the 30 CEUs against nurse practitioners who satisfy renewal through national certification. Sources: https://regs.maryland.gov/us/md/exec/comar/10.27.01.13 and https://regs.maryland.gov/us/md/exec/comar/10.27.07.04'),

-- ---- DISTRICT OF COLUMBIA -------------------------------------------------
 ('DC','MD','renewal_cycle_months',
  '24 months, per 17 DCMR sec. 4601.1 (expiry 31 December of each even-numbered year)',
  'DC Health has moved new credentials to a birth-month anchor as of 16 June 2024',
  'The TERM is two years under both regimes, but the ANCHOR DATE is in transition and the published regulation is stale. 17 DCMR sec. 4601.1, as published in the Board of Medicine regulations compilation, says a licence "shall expire at 12:00 midnight of December 31 of each even-numbered year". The Board of Medicine web page says the Board is "transitioning all professional licenses, certificates, and registrations to a birth-month renewal cycle" and that credentials "issued on or after June 16, 2024, will expire on the last day of the holder''s birth month". A physician licensed before that date and one licensed after it have different expiry dates, and the platform cannot tell them apart without the issue date. OPEN: obtain the transition rule and the treatment of pre-2024 licences. Sources: https://doh.dc.gov/sites/default/files/dc/sites/doh/publication/attachments/title_17_bomed_regs_05072012.pdf and https://dchealth.dc.gov/bomed'),

 ('DC','MD','ce_hours_total',
  '50 hours every two years (Board of Medicine page)',
  '17 DCMR sec. 4614.2 (2012 compilation) says 50 AMA/PRA CATEGORY I hours',
  'The total agrees; the category does not, and the 2012 regulation compilation predates the 3/13/2020 amendment of 17 DCMR sec. 4614. The Board web page describes the 50 hours without a category restriction and adds two mandated topics (LGBTQ cultural competency, public health priority) that the 2012 text does not contain. dcregs.dc.gov serves section metadata but not section text to automated fetch, so the current text of 17-4614 was NOT read. OPEN: retrieve the post-2020 text of 17 DCMR sec. 4614. Sources: https://dchealth.dc.gov/bomed and https://doh.dc.gov/sites/default/files/dc/sites/doh/publication/attachments/title_17_bomed_regs_05072012.pdf'),

 ('DC','APRN','ce_topic_public_health_priority_hours',
  'DC Health licensee notice OS-26-03-05 (2024-2026 cycle): 2.5 hours',
  'DC Health 2024 RN/APRN Renewal FAQ: 3 hours',
  'TWO OFFICIAL DC HEALTH PUBLICATIONS DISAGREE. The 2024 renewal FAQ says RNs and APRNs need "3 hours ... in the public health priority"; the current licensee notice for the cycle ending 30 June 2026 says "2.5 hours must be in the public health priority topics". Both describe the same 24-hour CE total with the same 2-hour LGBTQ component. The seeded value is 2.5, from the more recent notice covering the current cycle. The likely explanation is that the public health priority share is a percentage of the total that DC Health re-states each cycle, but neither document says so. OPEN: obtain the Director''s public health priority designation notice and the percentage rule. Sources: https://dchealth.dc.gov/sites/default/files/dc/sites/doh/publication/attachments/OS-26-03-05%20(2a).pdf and https://dchealth.dc.gov/sites/default/files/dc/sites/doh/service_content/attachments/FAQ_RN_APRN%202024Renewal.pdf'),

 ('DC','APRN','renewal_fee_cents',
  'DC Health licensee notice OS-26-03-05: $263 for an APRN licence renewal',
  'DC Health 2024 RN/APRN Renewal FAQ: $118 renewal application fee plus $50 criminal background check',
  'TWO OFFICIAL DC HEALTH PUBLICATIONS DISAGREE BY MORE THAN A FACTOR OF TWO. The 2024 FAQ gives APRN renewal as a $118 application fee plus a $50 CBC ($168 total, with $130 more for a controlled substance registration). The current notice gives "$263 for a Nurse Practitioner (APRN) License Renewal" plus "$50" CBC. This may be a genuine fee increase between cycles, or the $263 may bundle components the FAQ itemised. The seeded value is the current notice figure because that is what the licensee pays now. OPEN: obtain the DC Health fee schedule for nursing; the Board of Medicine fee schedule page states only "All fees are set by regulation, and can be found on the relevant application" and publishes no amounts. Sources: https://dchealth.dc.gov/sites/default/files/dc/sites/doh/publication/attachments/OS-26-03-05%20(2a).pdf and https://dchealth.dc.gov/sites/default/files/dc/sites/doh/service_content/attachments/FAQ_RN_APRN%202024Renewal.pdf'),

-- ---- DELAWARE -------------------------------------------------------------
 ('DE','MD','csr_fee_cents',
  '$210, which is the CSR APPLICATION fee',
  'the Division does not publish the CSR RENEWAL fee at all',
  'Delaware''s Division of Professional Regulation fee schedules state "You are notified of the amount of the renewal fee at the time of renewal" for every credential it administers, including the controlled substance registration, the medical licence and the nursing licence. The only published number for a practitioner CSR is the $210 application fee. Seeding it lets the platform show a licensee what obtaining a Delaware CSR costs; it must NOT be presented as the biennial renewal cost. The paired row DE/APRN/csr_fee_cents carries the same defect. OPEN: obtain the CSR renewal fee from DELPROS or by request to the Division. Source: https://dpr.delaware.gov/boards/controlledsubstances/fees/'),

 ('DE','MD','csr_renewal_cycle_months',
  '24 months, expiring 30 June of odd years',
  'the CSR clock is three months offset from the medical licence clock (31 March of odd years)',
  'Not a contradiction -- a scheduling hazard. A Delaware physician has TWO biennial state obligations with different anchor dates: the medical licence (expires 31 March, odd years) and the controlled substance registration (expires 30 June, odd years). A generator that assumes one renewal event per state per cycle will miss one of them, and the CSR carries its own 2-hour continuing education attestation on the CSR clock (see DE/MD/ce_topic_controlled_substance_hours). The paired DE/APRN rows are worse: the APRN/RN licence expires on 28 February, 31 May or 30 September of odd years depending on the licensee, so Delaware APRNs have three possible licence anchors against one CSR anchor. Sources: https://dpr.delaware.gov/boards/controlledsubstances/renewal/ and https://dpr.delaware.gov/boards/medicalpractice/renewal/'),

-- ---- NEW HAMPSHIRE --------------------------------------------------------
 ('NH','MD','initial_license_fee_cents',
  'OPLC Board of Medicine License Fees page: $378.00 (including the $28.00 Professional Health Program fee)',
  'N.H. Admin. R. Plc 1002.28: $385',
  'A BOARD FEE PAGE AND THE FEE RULE DISAGREE BY $7. OPLC publishes $378.00 for both the initial physician licence and the biennial renewal, stating that the figure includes the mandatory $28.00 Professional Health Program fee. N.H. Admin. R. Plc 1002.28, as published by the New Hampshire General Court, lists "$385" for "Initial, renewal, or reinstatement after expiration of license" for an unrestricted permanent physician licence. The most likely reconciliation is that one of the two documents is stale following a PHP fee change, but neither states an effective date on its face. The seeded value is the OPLC figure because that is what the licensee is charged. The paired row NH/MD/renewal_fee_cents carries the same defect. OPEN: obtain the current effective fee rule. Sources: https://www.oplc.nh.gov/board-medicine-license-fees and https://gc.nh.gov/rules/state_agencies/plc1000.html'),

 ('NH','APRN','initial_license_fee_cents',
  'N.H. Admin. R. Plc 1002.33: $110 (APRN), 2-year licence duration',
  'the OPLC Board of Nursing License Fees page could not be retrieved to confirm',
  'The APRN fee is seeded from the fee RULE rather than from a board fee page, because www.oplc.nh.gov/board-nursing-license-fees returned HTTP 403 (Akamai "Access Denied") to every automated fetch on 2026-09-18, as did the OPLC nursing FAQ and the APRN renewal checklist PDF. Given that the OPLC page and the rule disagree by $7 for physicians (see NH/MD/initial_license_fee_cents), the APRN rule figure may likewise be stale. The paired row NH/APRN/renewal_fee_cents carries the same defect. OPEN: retrieve the OPLC Board of Nursing fee page by hand or by a browser session. Source: https://gc.nh.gov/rules/state_agencies/plc1000.html'),

 ('NH','APRN','ce_hours_total',
  '30 hours every 2 years (RSA 326-B:31, III)',
  'these 30 hours are IN ADDITION TO the RN continuing education requirement, which is not seeded',
  'RSA 326-B:31, III opens "An APRN, in addition to the continuing education requirements to renew or reinstate a license as an RN, shall complete 30 hours ...". The New Hampshire APRN therefore owes the RN CE requirement PLUS 30 hours. The RN requirement itself could not be read: the OPLC nursing pages returned HTTP 403 and the Nur administrative rules were not retrieved. A consumer that reports 30 as the total New Hampshire APRN CE burden is understating it. OPEN: read RSA 326-B:31, I-II and N.H. Admin. R. Nur 404 for the RN hour count. Source: https://gc.nh.gov/rsa/html/xxx/326-b/326-b-mrg.htm'),

-- ---- VERMONT --------------------------------------------------------------
 ('VT','MD','ce_hours_total',
  '30 hours per two-year licence period',
  'the figure is 15, or zero, for a licensee in a partial first cycle',
  'Vermont graduates the CME total by how long the licence has been held. The Board of Medical Practice CME Hour Requirements FAQ states 30 hours for a physician renewing a licence held for two full years, 15 hours (still including the mandatory topics) for one held one to two years, and no CME at first renewal for a licence held less than one year. The seeded 30 is correct for the steady state and wrong for a newly licensed physician''s first renewal. OPEN: the platform needs a licence-issue-date input before this row can be applied to a first renewal; consider re-seeding as value_json with the tiers once that input exists. Source: https://www.healthvermont.gov/sites/default/files/document/BMP_Licensing_CMEHOURREQUIREMENTSFAQ_08292024.pdf'),

 ('VT','APRN','ce_hours_total',
  '20 hours in the two years immediately preceding the application (Rule 4-8(a))',
  'Rule 4-8(d)(2) separately requires 400 practice hours in two years, which the CE hours do not satisfy',
  'A Vermont APRN renewal has two distinct competency conditions that a single ce_hours_total cannot express: 20 hours of qualifying continuing education (Rule 4-8(a)) AND "Practiced in an APRN role for a minimum of 50 days (400 hours) in the two years preceding application or 120 days (960 hours) in the five years preceding application" (Rule 4-8(d)(2)), plus current national certification (Rule 4-8(d)(3)). The field_key set has no slot for a practice-hours condition. A consumer that checks only CE hours will clear an APRN who fails the practice-hours test. OPEN: add a practice_hours_required key, or record the condition as a structured renewal precondition. Source: https://outside.vermont.gov/dept/sos/office_professional_regulation/professions/nursing/nursing_administrative_rules.pdf'),

-- ---- MAINE ----------------------------------------------------------------
 ('ME','MD','initial_license_fee_cents',
  '$700 ($600 application plus $100 examination)',
  'the two components are charged at different points and the $100 may not apply to every applicant',
  'The Maine Board of Licensure in Medicine MD License page states a $600 application fee and a $100 examination fee. Whether the $100 is charged to every initial applicant -- including those who satisfy the examination requirement by prior USMLE/COMLEX record rather than by sitting a Board examination -- is not stated. The seeded $700 is the full cost to an applicant who pays both. OPEN: confirm the population that pays the examination fee. Source: https://www.maine.gov/md/licensure/md-license'),

 ('ME','APRN','ce_topic_pharmacotherapeutics_hours',
  'value_json: 15 contact hours for a NP or CNM who does NOT prescribe',
  'the condition is inverted relative to every other state in this file',
  'Maine attaches its 15-hour pharmacology requirement to NON-prescribing nurse practitioners and certified nurse midwives -- the opposite subset from Pennsylvania (16 hours for CRNPs WITH prescriptive authority), Connecticut (5 hours for all APRNs), New Hampshire (5 hours for all APRNs) and the District of Columbia (15 hours for all APRNs). A consumer that pattern-matches on the field_key across states and assumes "pharmacology hours apply to prescribers" will assign this requirement to exactly the wrong Maine licensees. Flagged here so the inversion is not silently normalised away. Source: https://www11.maine.gov/boardofnursing/licensing/advanced-practice-rn/faq.html')

) as c(state, license_type, field_key, published_value, observed_value, notes)
join requirements r
  on r.state = c.state
 and r.license_type = c.license_type
 and r.field_key = c.field_key
 and r.is_current
 and r.deleted_at is null
 and r.verified_by = 'research-agent-group-a';

-- ---------------------------------------------------------------------------
-- A. GAPS -- in-scope field_keys with no verified value. requirement_id NULL.
-- ---------------------------------------------------------------------------
insert into requirement_conflicts
  (requirement_id, published_value, observed_value, observed_at, observed_by,
   occurrences, resolution, notes)
values

-- ---- NEW JERSEY -- the largest gap in this group ---------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'SOURCE ACCESS FAILURE, NEW JERSEY -- NJ/MD IS ENTIRELY UNSEEDED and NJ/APRN holds two rows only. www.njconsumeraffairs.gov, which hosts the State Board of Medical Examiners and the Board of Nursing, is behind an Imperva/Incapsula bot wall. On 2026-09-18 it returned HTTP 403 with Incapsula incident IDs to every automated fetch of /bme/Pages/FAQ.aspx, /bme/Pages/renewals.aspx, /nur/pages/continuingeducation.aspx, /nur/Pages/Applications.aspx and /renewals/Pages/Nurse.aspx, from two different clients and two different user agents; a direct curl returned a 1,162-byte Incapsula challenge page. www.nj.gov/lps/ca2/BME/ is reachable but carries only orientation-exam instructions. New Jersey does NOT publish the New Jersey Administrative Code on a state-hosted site -- it is licensed to LexisNexis -- so N.J.A.C. 13:35 (medical examiners) and 13:37 (nursing) could not be read from a primary source, and third-party republishers (Cornell LII, Justia) are excluded by the verification standard. NOT SEEDED for NJ/MD: renewal_cycle_months, renewal_window_days, ce_hours_total, ce_cycle_months, every ce_topic, initial_license_fee_cents, renewal_fee_cents, fingerprint_required, csr_required. NOT SEEDED for NJ/APRN: renewal_cycle_months, renewal_window_days, ce_hours_total, ce_cycle_months, every ce_topic, renewal_fee_cents, supervision_required, csr_required. OPEN: retrieve these by a browser session or by written request to the Division of Consumer Affairs. Do not let any consumer fall back to a neighbouring state for New Jersey.'),

-- ---- csr_required, the negative that cannot be asserted from silence -------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'GAP csr_required for PA, NJ, GA, MA, MD, DC, NH, VT and ME (both licence types). Four of the twelve jurisdictions in this group were verified to have a LIVE state controlled substance registration -- CT (Dept of Consumer Protection, $40, biennial to 28 February odd years), DE (Division of Professional Regulation, $210 application, biennial to 30 June odd years, with a 1-hour mandatory course and a 2-hour CE attestation), RI (Dept of Health, $200 practitioner fee, renewed with the professional licence) -- and those are seeded. For the other nine, no board or statutory page was found that affirmatively states either that a separate state CSR exists or that it does not. Massachusetts is the closest call: 244 CMR 4.00 requires an APRN with prescriptive authority to "register with the Department of Public Health''s Drug Control Program", which is almost certainly a state controlled substance registration, but the Board of Registration in Nursing page does not name it as such and no DPH Drug Control Program page was read, so csr_required was NOT seeded for MA. A negative cannot be asserted from silence and a positive cannot be asserted from an adjacent phrase. OPEN, per state: PA (35 P.S. ch. 780-2), NJ (N.J.S.A. 24:21-10 CDS registration, which almost certainly exists), GA (O.C.G.A. sec. 16-13-35), MA (105 CMR 700, DPH Drug Control Program MCSR), MD (Md. Crim. Law sec. 5-301), DC (D.C. Code sec. 48-903.01), NH (RSA 318-B), VT (26 V.S.A. sec. 2022), ME (32 M.R.S. ch. 117). THIS IS THE SINGLE LARGEST REMAINING GAP IN THIS GROUP: a state CSR is a separately-dated, separately-feed obligation that clients miss, and four of the twelve jurisdictions checked had one.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'GAP csr_renewal_cycle_months and csr_fee_cents for CT/APRN cross-check, and for every jurisdiction where csr_required is unverified. Where csr_required was verified (CT, DE, RI) the cycle and fee are seeded. CT''s CSR fee ($40 initial, $40 renewal) and cycle (biennial, 28 February odd years) are published on one Department of Consumer Protection page and were not corroborated by a second source or by Regs. Conn. State Agencies sec. 21a-243. OPEN: corroborate. Source: https://portal.ct.gov/dcp/license-services-division/all-license-applications/controlled-substance-practitioner-registration'),

-- ---- fingerprint_required -------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'GAP fingerprint_required for PA, NJ, MA, CT, DE, RI, NH, VT and ME (both licence types), for GA/APRN, for MD/APRN and for DC (both licence types). Only three values were verified: GA/MD (the Composite Medical Board requires applicants to "Complete a criminal background check via FBI-compliant fingerprint/biometric results") and MD/MD (the Board of Physicians requires a Criminal History Records check "as a qualification to licensure" and instructs applicants on fingerprint submission). DC is a NEAR MISS deliberately not seeded: DC Health charges a "$50" Criminal Background Check at every RN/APRN renewal and at Board of Medicine renewal, but neither the licensee notice nor the renewal FAQ says the check is FINGERPRINT-based, and this field_key asks specifically about fingerprints. Maine is a PARTIAL: the Board of Licensure in Medicine requires fingerprints of Interstate Medical Licensure Compact applicants only ("The Compact requires that an applicant for licensure submit fingerprints or other biometric-based information"), which is a compact condition rather than a Maine condition, so it was not seeded as a Maine requirement. Rhode Island''s physician application requirements document mentions no fingerprint requirement, but silence is not a no. NOT SEEDED. OPEN: for each state, find an affirmative statement either way.'),

-- ---- renewal_window_days --------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'GAP renewal_window_days for PA/APRN, NJ (both), GA/MD, MA/MD, DC (both), DE (both), RI (both), NH (both), ME (both), and MD/APRN. Seeded only where a board published either a transactional open date (MA/APRN 90 days, VT/APRN 42 days, GA/APRN 92 days from a stated date range, MD/MD 78 days from a stated date range) or a notification date that is flagged as such (PA/MD 60, CT/MD 60, CT/APRN 60). Notable near misses NOT seeded: the Georgia Composite Medical Board says "Renewal notices are sent via email beginning 90 days before expiration and daily until the expiration date" -- a notification cadence, not an open date; the Rhode Island Department of Health says "Renewal notices are sent out 60 days before your expiration date" for both physicians and nurses -- again a notice; the Massachusetts Board of Registration in Medicine says only "You may renew only during the renewal period, and you will have received an email notification", naming no interval at all; the Delaware Division of Professional Regulation names no open date for either board. A notification date is not a renewal window and was not recorded as one except where explicitly flagged.'),

-- ---- PENNSYLVANIA ---------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'GAP PA/MD/ce_topic_implicit_bias_hours, PA/APRN/ce_topic_opioid_hours and PA/APRN/supervision_required. The Board of Nursing Renewal Information page lists "Opioid education for CRNPs with prescriptive authority" as a renewal requirement but publishes NO HOUR COUNT on that page, and the CRNP Licensure Snapshot does not mention it at all; an invented number here would be a fabricated obligation, so it is NOT SEEDED even though the requirement demonstrably exists. Pennsylvania publishes no implicit bias CME mandate for physicians on any page read. supervision_required for CRNPs is not seeded because collaborative_agreement_required carries the substance and duplicating it under a second key would double-count. OPEN: read 49 Pa. Code sec. 21.253 and Act 124 of 2016 as it applies to nursing; pacodeandbulletin.gov is robots-disallowed to automated fetch. Source: https://www.pa.gov/agencies/dos/department-and-offices/bpoa/boards-commissions/nursing/renewal-information'),

-- ---- GEORGIA --------------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'GAP GA/APRN/supervision_required and GA/APRN fingerprint_required. Ga. Comp. R. & Regs. ch. 410-11 requires a written, signed nurse protocol agreement with a DELEGATING PHYSICIAN -- seeded as collaborative_agreement_required. Whether Georgia additionally imposes SUPERVISION distinct from delegation under a protocol was not established from a primary source and was NOT inferred from the word "delegating". Also NOT SEEDED: GA/APRN/ce_topic_controlled_substance_hours. Ch. 410-11 states that APRNs "may not submit prescription drug orders for Schedule I or II controlled substances" -- a SCOPE limit, not a CE requirement, and the field_key set has no slot for a prescribing-schedule restriction, which is a real and material constraint this table cannot express. OPEN: add a prescribing_schedule_restriction key. Source: https://rules.sos.ga.gov/gac/410-11'),

-- ---- MASSACHUSETTS --------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'GAP MA/MD ce_topic_domestic_violence_hours, ce_topic_child_abuse_hours, ce_topic_implicit_bias_hours and an electronic-health-records topic. The Board of Registration in Medicine CME Requirements table lists Domestic Violence and Sexual Violence Training and Recognizing and Reporting Suspected Child Abuse as "REQUIRED" for INITIAL LICENSURE with NO CREDIT AMOUNT PUBLISHED, and lists Implicit Bias Training (2 credits) and Proficiency in Electronic Health Records (3 credits) as initial-licensure requirements rather than renewal requirements. Because they are pre-licensure conditions they generate no renewal-cycle obligation, and two of the four have no hour count at all. NOT SEEDED. The EHR proficiency requirement additionally has no field_key. Source: https://www.mass.gov/doc/borim-cme-requirements-pdf/download'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'GAP MA/APRN mandated CE topics. 244 CMR 5.00, the Board of Registration in Nursing continuing education regulation, sets 15 contact hours over two years and mandates NO topic at all -- it lists acceptable subject matter areas without allocating hours. The Board''s Mandatory Continuing Education for nurses web page separately points licensees at "Domestic and Sexual Violence Training (Chapter 260)" with a training link but publishes no hour count and does not say whether it is one-time or recurring. An hour count invented for it would be a fabricated obligation. NOT SEEDED; the existence of the requirement is recorded here. Sources: https://www.mass.gov/doc/244-cmr-5-continuing-education/download and https://www.mass.gov/info-details/mandatory-continuing-education-for-nurses'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'GAP MA/APRN/collaborative_agreement_required. Massachusetts requires "mutually agreed upon guidelines" with a Qualified Healthcare Professional for a CRNA, CNP or PNMHCS with fewer than two years of supervised practice (244 CMR 4.00) -- seeded under supervision_required as value_json, because the instrument the regulation names is guidelines with a supervisor, not a collaborative practice agreement. Mapping one onto the other would misstate the obligation. NOT SEEDED under a second key. OPEN: decide whether the schema should carry a state-neutral practice_authority_instrument key, which would also resolve the equivalent California standardized-procedures gap already logged against requirements_seed.sql.'),

-- ---- CONNECTICUT ----------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'GAP CT/APRN/renewal_fee_cents, CT/APRN/collaborative_agreement_required and CT/APRN/supervision_required. The DPH APRN Licensure Requirements page publishes the $200 initial application fee but no renewal fee, and no DPH page listing the APRN annual renewal fee was located. Connecticut''s collaboration regime (C.G.S. sec. 20-87a, as amended: an APRN must practise in collaboration with a physician for a transition period of three years and 2,000 hours, after which the APRN may practise independently) is widely described but was NOT found stated on any portal.ct.gov page read on 2026-09-18, and cga.ct.gov returned repeated fetch errors for the chapter text. NOT SEEDED -- a three-year / 2,000-hour threshold written from recall is exactly the kind of value this standard exists to exclude. OPEN: retrieve C.G.S. sec. 20-87a.'),

-- ---- MARYLAND -------------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'GAP MD/MD and MD/APRN ce_topic_implicit_bias_hours. Maryland requires an implicit bias and structural racism training attestation of all health care practitioners at licence renewal (Md. Health-Gen. sec. 1-225; HB 783, Health Occupations - Structural Racism Training; effective 1 April 2026 for the structural racism programme). BOTH Board notices read on 2026-09-18 state explicitly that it is a ONE-TIME requirement -- "You are only required to attest to the completion of the training once, and will not need to repeat this attestation during subsequent renewals" -- and NEITHER states a number of hours or credits. A one-time requirement with an unknown magnitude cannot be written into a field_key that can only hold hours without inventing the magnitude. NOT SEEDED; the existence and the one-time periodicity are recorded here. OPEN: obtain an hour count, or add a ce_topic_implicit_bias_required boolean so the duty can be scheduled without a fabricated hour figure. Sources: https://www.mbp.state.md.us/forms/implicit_bias_notice.pdf and https://health.maryland.gov/mbpme/Documents/implicit2026.pdf'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'GAP MD/APRN/initial_license_fee_cents, MD/APRN/collaborative_agreement_required and MD/APRN/supervision_required. The Maryland Board of Nursing Schedule of Fees (effective 7/1/2025) publishes RN licensure by examination ($187.00), RN by endorsement ($230.00), RN renewal ($191.00) and CRNP renewal ($216.00), but the nurse practitioner INITIAL certification fee was not among the lines retrieved. On practice authority: COMAR 10.27.07.04 conditions renewal only on current national certification and says nothing about an attestation or collaboration agreement, and the Board''s Practice of the Nurse Practitioner page served only a 2017 proposed amendment about the Insect Sting Emergency Treatment Program. Maryland is understood to have removed the NP attestation requirement, but that is not a primary source and a false in this field is as damaging as a false true. NOT SEEDED. OPEN: read COMAR 10.27.07.03 (Scope and Standards of Practice) and Md. Health Occ. sec. 8-302.'),

-- ---- DISTRICT OF COLUMBIA -------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'GAP DC/MD/initial_license_fee_cents and DC/MD/renewal_fee_cents. The DC Health "Medicine Fee Schedule" page publishes NO AMOUNTS: it says only "All fees are set by regulation, and can be found on the relevant application. All current Board of Medicine applications can be found online HERE." The nursing fees are published in the licensee notices and are seeded for DC/APRN; the medicine fees are not published anywhere that could be read on 2026-09-18. NOT SEEDED. OPEN: open a Board of Medicine application form and read the fee off it, or obtain 17 DCMR sec. 4104 (fees). Source: https://dchealth.dc.gov/service/medicine-fee-schedule'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'GAP DC/MD/ce_topic_pharmacology. The DC Board of Medicine states that the 50 hours must include "at least one (1) course in the subject of pharmacology". That is a COURSE COUNT, not an hour count, and this field_key can only hold hours. Converting one course to a number of hours would be an invented value. NOT SEEDED; the requirement is recorded here. Also NOT SEEDED: DC/APRN/initial_license_fee_cents -- the Board of Nursing APRN page publishes a "Dual Application (RN and APRN simultaneous): $145", a "Single Application (adding APRN to existing RN): $230" and a "Reactivation: $34", which are three different initial paths and not a single initial licence fee; recording one of them as the initial fee would misstate the cost for the other two populations. OPEN: decide whether initial_license_fee_cents should become value_json where a board publishes path-dependent fees, as was done for NJ/APRN in this file. Sources: https://dchealth.dc.gov/bomed and https://dchealth.dc.gov/page/advanced-practice-registered-nurse-aprn'),

-- ---- DELAWARE -------------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'GAP DE/MD/renewal_fee_cents and DE/APRN/renewal_fee_cents. The Delaware Division of Professional Regulation publishes application fees for every credential (Physician MD $440; APRN all types $181) but states on every fee schedule that "Renewal Fee - You are notified of the amount of the renewal fee at the time of renewal." No Delaware renewal fee is published anywhere the Division serves. NOT SEEDED. OPEN: obtain renewal fees from DELPROS or by request. Sources: https://dpr.delaware.gov/boards/medicalpractice/fees/ and https://dpr.delaware.gov/boards/nursing/fees/'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'GAP DE/APRN/collaborative_agreement_required and DE/APRN/supervision_required. 24 Del. C. ch. 19 defines "full-practice authority" as "the collection of state practice and licensure laws that allow APRNs to evaluate patients, diagnose, order and interpret diagnostic tests, initiate and manage treatments, including prescribing medications, under exclusive licensure authority of the Delaware Board of Nursing", and the chapter text read on 2026-09-18 contains no physician collaboration or supervision mandate. That is an ABSENCE, not an affirmative statement that no collaborative agreement is required, and Delaware''s full-practice authority statute has historically conditioned independent practice on a transition period. Seeding false from silence is exactly the error this standard forbids. NOT SEEDED. OPEN: read 24 Del. C. sec. 1902 and sec. 1906 and 24 DE Admin. Code 1900 sec. 8 in full. Source: https://delcode.delaware.gov/title24/c019/index.html'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'GAP DE/MD mandated CE topics. The Board of Medical Licensure and Discipline''s Continuing Education and Audit Information page states the 40-hour total and the AMA/AOA approval standard and NO topic mandates, while the Board''s renewal page tells physicians they must attest to completing "the required Continuing Medical Education (CME)" AND "the Mandatory Training" -- naming a mandatory training that the CE page does not describe and that could not be identified. NOT SEEDED. OPEN: identify what "the Mandatory Training" is at Delaware medical licence renewal; it is a real, attested, undescribed obligation. Source: https://dpr.delaware.gov/boards/medicalpractice/renewal/'),

-- ---- RHODE ISLAND ---------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'GAP RI/MD mandated CE topics. The Rhode Island Board of Medical Licensure and Discipline is explicit that there are none for the current cycle: its Physicians licensing page states "40 hours of ACCME-accredited training in any topic areas over a two-year period. There are no specific topics required by the Rhode Island Board of Medical Licensure and Discipline for this license renewal cycle." This is recorded as a GAP RATHER THAN SEEDED AS ZEROS because the Board scopes the statement to "this license renewal cycle", which implies topic mandates that vary cycle to cycle. A consumer must not cache "Rhode Island has no topic CME" as a standing fact. OPEN: re-check each cycle. Source: https://health.ri.gov/licensing/physicians'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'GAP RI/APRN/supervision_required. 216-RICR-40-05-3 affirmatively states that collaboration "does not require such relationship to be evidenced by a written collaboration agreement" -- seeded as collaborative_agreement_required = false. Whether Rhode Island imposes any separate SUPERVISION condition was not established, and false was not carried across from the collaboration finding. NOT SEEDED.'),

-- ---- NEW HAMPSHIRE --------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'GAP NH/MD mandated CE topics, NH/APRN/collaborative_agreement_required and NH/APRN/supervision_required. RSA 329:16-g sets the 100-hour biennial total and mandates no topic; RSA 329:9 authorises the Board to adopt rules on "Procedures for appropriate pain management pursuant to RSA 318-B:10, IX" and "Prescribing controlled drugs pursuant to RSA 318-B:41", so topic mandates may exist in N.H. Admin. R. Med 400 -- which could not be read because www.oplc.nh.gov returned HTTP 403 (Akamai "Access Denied") to every automated fetch on 2026-09-18, including the Board of Medicine laws-and-rules page. On APRN practice authority: RSA 326-B:11, III grants an APRN "plenary authority to possess, compound, prescribe, administer, and dispense and distribute to clients controlled and non-controlled drugs within the scope of the APRN''s practice", and the chapter contains no collaboration mandate. That is strong, but it is still an absence, and false was NOT seeded from it. NOT SEEDED. OPEN: read N.H. Admin. R. Med 400 and Nur 300.'),

-- ---- VERMONT --------------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'GAP VT/MD/renewal_window_days and VT/APRN/supervision_required. The Vermont Board of Medical Practice publishes the expiration date (30 November of even years) but no renewal-open interval. For APRNs, Rule 9-8(a) requires a "formal agreement with a collaborating provider" below the 24-month / 2,400-hour threshold -- seeded as collaborative_agreement_required value_json. Whether Vermont separately imposes SUPERVISION was not established and was not carried across from the collaboration finding. NOT SEEDED.'),

-- ---- MAINE ----------------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'GAP ME/APRN/collaborative_agreement_required. 02-380 CMR ch. 8 imposes a 24-month SUPERVISION condition on nurse practitioners -- seeded as supervision_required value_json -- and names three qualifying arrangements (a licensed physician, a supervising nurse practitioner, or employment by a clinic or hospital with a medical director). None of the three is a collaborative practice agreement, and mapping supervision onto collaboration would misstate the instrument. NOT SEEDED. Also NOT SEEDED: ME/APRN/renewal_window_days -- www1.maine.gov/boardofnursing/licensing/renew-license.html returned HTTP 502 on 2026-09-18.'),

-- ---- CROSS-CUTTING --------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'SCOPE GAP: license_type ''DO'' is NOT COVERED in any of the twelve jurisdictions in this group. In DE, RI, VT, ME, NH, MD, DC and MA a single authority licenses MDs and DOs (Delaware''s renewal page names "Physician M.D & D.O." on one line; Rhode Island''s CME regulation covers physicians "licensed to practice allopathic or osteopathic medicine"), so the seeded MD rows are LIKELY to hold for DOs there, but "likely" is not verified and no DO-specific page was read. In PENNSYLVANIA the State Board of Osteopathic Medicine is a SEPARATE board with its own renewal guide, fee schedule and CME requirements, and the seeded PA/MD rows must NOT be applied to a DO. Georgia, New Jersey, Connecticut and Maryland were not checked for board separation. Any consumer that resolves a DO to the MD rows is producing an unverified obligation.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'SCHEMA GAP: the field_key set has no slot for the PERIODICITY of a mandated CE topic, and this group makes the problem worse than the first four states did. Twenty-one rows in requirements_seed_group_a.sql are value_json for periodicity or population reasons, including six Connecticut physician topics on a "first renewal then every six years" clock, two Georgia once-in-a-career requirements, three Massachusetts one-time requirements, and two Delaware topics that hang on the CONTROLLED SUBSTANCE REGISTRATION clock rather than on the licence clock. ANY CONSUMER THAT READS value_num AND IGNORES value_json WILL SILENTLY DROP ALL OF THEM. Resolving this means a schema change, not a data change.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'SCHEMA GAP: ce_cycle_months and renewal_cycle_months diverge in Connecticut (12-month licence, 24-month CE) and the CSR clock diverges from the licence clock in Connecticut, Delaware and Rhode Island. The obligation generator must treat ce_cycle_months, renewal_cycle_months and csr_renewal_cycle_months as three independent clocks with three independent anchor dates, and the anchor dates are NOT in this table at all -- only the interval lengths are. A Delaware physician renews the medical licence on 31 March of odd years and the controlled substance registration on 30 June of odd years; a Connecticut physician renews the licence in their birth month every year and attests CME over a rolling 24 months and renews the CSR on 28 February of odd years. Without an anchor-date field the platform cannot date any of these duties. OPEN: add renewal_anchor_date / csr_anchor_date keys, or a structured cycle descriptor.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'SCHEMA GAP: several verified requirements in this group are not CE hours at all and have nowhere to live. Vermont requires an APRN to have "Practiced in an APRN role for a minimum of 50 days (400 hours) in the two years preceding application or 120 days (960 hours) in the five years preceding application" (Rule 4-8(d)(2)) and to hold current national certification (Rule 4-8(d)(3)); Georgia, Maryland and Massachusetts all condition APRN renewal on maintaining national certification; Georgia bars APRNs from prescribing Schedule I and II controlled substances; Delaware requires re-entry pharmacotherapeutics hours after an absence from practice (24 hours after 2-5 years, 45 hours after 5+). None of these is expressible with the current field_key set, and all of them can block a renewal. OPEN: add practice_hours_required, national_certification_required and prescribing_schedule_restriction keys.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-a', 1, 'unresolved',
 'METHOD NOTE, SOURCE ACCESS: the following official sources were UNREACHABLE to automated fetch on 2026-09-18 and are the reason for a large share of the gaps above. pacodeandbulletin.gov (the Pennsylvania Code and Bulletin, i.e. 49 Pa. Code chs. 16, 18 and 21) -- disallowed by robots.txt. www.njconsumeraffairs.gov (New Jersey Board of Medical Examiners and Board of Nursing) -- Imperva/Incapsula bot wall, HTTP 403 to every path but two. www.oplc.nh.gov (New Hampshire Board of Nursing fee page, nursing FAQ, APRN checklists, Board of Medicine laws and rules) -- Akamai "Access Denied", HTTP 403. www.cga.ct.gov/current/PUB/chap_370.htm (Connecticut General Statutes ch. 370, Medicine and Surgery) -- repeated server errors. www.dcregs.dc.gov section text (17 DCMR sec. 4601, sec. 4614 current text) -- serves metadata only, no section text. goals.sos.ga.gov fee schedule portal -- JavaScript shell, CSS error, no static content. www1.maine.gov/boardofnursing/licensing/renew-license.html -- HTTP 502. In every case an alternative primary source was sought first and the gap was recorded only when none was found; no third-party republisher (Cornell LII, Justia, regulations.justia.com) was used as a citation anywhere in this group, and no CE aggregator or licence-service marketplace was consulted at all.');

commit;
