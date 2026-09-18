-- =============================================================================
-- requirement_conflicts_seed_group_d.sql -- what the rules asset does NOT yet
-- know about AZ, WA, OR, CO, UT, NV, NM, ID, WY, AK and HI.
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
-- observed_by is 'research-agent-group-d' throughout: these are desk-research
-- findings, not observed board behaviour.
--
-- Run AFTER requirements_seed_group_d.sql. Idempotent. Scoped to this group's
-- states only, so it does not disturb rows owned by the other seed files.
-- =============================================================================

begin;

delete from requirement_conflicts where observed_by = 'research-agent-group-d';

-- ---------------------------------------------------------------------------
-- B. QUALIFIERS on rows that exist.
-- ---------------------------------------------------------------------------
insert into requirement_conflicts
  (requirement_id, published_value, observed_value, observed_at, observed_by,
   occurrences, resolution, notes)
select r.id, c.published_value, c.observed_value,
       timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1,
       'unresolved', c.notes
from (values

 ('AZ','APRN','renewal_cycle_months',
  'Arizona State Board of Nursing: RN licences renew "by April 1, every 4 years"',
  'the APRN certification "expires when the RN license or national certification expires, whichever comes first"',
  'TWO CLOCKS, ONE FIELD. The Board publishes a 4-year RN renewal cycle, but also states that the advanced practice certification expires when the RN licence OR the national certification expires, WHICHEVER COMES FIRST. National certification bodies (AANP, ANCC) run 5-year cycles that do not align with the Arizona 4-year clock, so for any APRN whose national certification lapses first the effective renewal cycle is shorter than the seeded 48 months and is set by a body that is not the Board. An obligation generator that treats 48 months as the APRN''s controlling deadline will be late for part of the population. OPEN: the platform needs a per-clinician national-certification expiry attribute before this field can be trusted. Source: https://azbn.gov/licenses-and-certifications/renew-your-license'),

 ('OR','MD','renewal_fee_cents',
  'Oregon Medical Board, Licensee Renewal Fees (eff. 7/2/2026): License Registration $608 per two-year period, total to renew $756',
  'OAR 847-005-0005 (Board fee rule): "Registration: Active ... $314/year", i.e. $628 per two-year period',
  'TWO OFFICIAL SOURCES DISAGREE. The Board''s published renewal fee sheet breaks the $756 biennial total down with a "License Registration" line of $608 ($304/year). The Board''s own fee RULE, OAR 847-005-0005, states the registration fee as "$314/year" ($628/biennium), rising to $375/year on 1 March 2028. $608 and $628 cannot both be right for the same period. The most likely reconciliation is that the rule text and the fee sheet were adopted at different times, but neither document carries a note reconciling them. The seeded value is the fee sheet total ($756) because that is the figure the licensee is asked to pay at renewal. OPEN: ask the Board which document is current. Sources: https://www.oregon.gov/omb/licensing/Documents/all-fees.pdf and https://www.oregon.gov/omb/statutesrules/Documents/847-005-0005.pdf'),

 ('OR','APRN','renewal_cycle_months',
  'Oregon Secretary of State Business Xpress License Directory: "License Renewal Period: 2 years" for Nurse Practitioners',
  'no Oregon State Board of Nursing page stating the renewal period could be retrieved',
  'CITATION IS A STATE DIRECTORY, NOT THE BOARD. The value is 2 years on an official State of Oregon licence-directory record whose issuing agency is named as the Oregon State Board of Nursing, but OSBN''s own renewal pages (oregon.gov/osbn/Pages/renewals.aspx, /Pages/renew.aspx) return 404 and the OSBN renewal instructions PDF does not state the cycle length. The same directory record shows "$0.00" for both the application and renewal fee, which is plainly a placeholder rather than a real fee, so the record is known to contain unmaintained fields. That undermines confidence in every field on it, including this one. OPEN: confirm the 2-year cycle against OAR ch. 851 or a working OSBN page before this row is used to date an obligation. Source: https://apps.oregon.gov/SOS/LicenseDirectory/LicenseDetail/230'),

 ('CO','APRN','ce_hours_total',
  'Colorado State Board of Nursing: "Continuing education hours are not currently required in order to renew a Registered Nurse ... license in Colorado"',
  'for advanced practice: "no additional continuing education requirements other than what is required to maintain professional certification"',
  'THE SEEDED ZERO IS A STATE-LAW ZERO, NOT A REAL-WORLD ZERO. Colorado imposes no state CE hour requirement, which is why 0 is seeded rather than omitted -- the Board says so affirmatively, so this is not silence. But the Board''s advanced-practice answer explicitly defers to "what is required to maintain professional certification", and an APN in Colorado must hold national certification. The certifying body''s CE requirement (typically 75 or 100 hours per 5-year cycle, on the certifier''s clock, not the Board''s) is a real obligation that this field reports as zero. A client told "Colorado requires 0 CE hours" will draw the wrong conclusion. OPEN: the schema needs a way to express "no state requirement, certification requirement applies" distinctly from "no requirement". Source: https://dpo.colorado.gov/Nursing/FAQ'),

 ('CO','APRN','collaborative_agreement_required',
  '750-hour physician mentorship for full prescriptive authority (RXN), within 3 years of RXN-P',
  'verified only for the prescriptive-authority pathway; the non-prescribing APN case is unestablished',
  'SCOPE LIMIT ON A TRANSITION-TO-PRACTICE ROW. The Colorado Board of Nursing publishes the 750-hour mentorship as a condition of moving from provisional prescriptive authority (RXN-P) to full prescriptive authority (RXN). It does not state whether an APN who does not prescribe needs any collaboration instrument at all, nor whether the mentorship must persist after the 750 hours are logged. The seeded value_json says "required: true" scoped to the prescribing population and records the threshold, which is why it is not a bare boolean. OPEN: read C.R.S. 12-255-112 and 3 CCR 716-1 for the non-prescribing case and for what, if anything, survives the mentorship. Source: https://dpo.colorado.gov/Nursing'),

 ('NV','APRN','ce_hours_total',
  '45 hours per renewal cycle (30 general nursing + 15 APRN specialty)',
  'the Board never publishes 45 as a single figure; it is the sum of two separately stated requirements',
  'THE TOTAL IS DERIVED, THE COMPONENTS ARE NOT. The Nevada State Board of Nursing publishes "30 hrs/renewal" as the RN requirement and separately requires APRNs to take "an additional 15 hrs each renewal cycle" in their specialty. 45 is arithmetic, not a quoted figure, which is why the components are carried inside value_json rather than flattened into value_num. It is also not certain whether the mandated topic hours below (4 cultural competency, 2 SBIRT, 2 opioid, 4 one-time bioterrorism) count toward the 30 or sit on top of it -- the Board''s CE page lists them in the same table without saying. OPEN: confirm the composition with the Board. Source: https://nevadanursingboard.org/continuing-education/'),

 ('NV','APRN','collaborative_agreement_required',
  'false in general; protocol approved by a collaborating physician required for Schedule II prescribing below the experience threshold',
  'NRS 632.237 threshold is stated as "2 years OR 2,000 hours" -- two different units, and the Board does not say how it measures them',
  'A TRANSITION-TO-PRACTICE THRESHOLD WITH AN AMBIGUOUS UNIT. NRS 632.237 lets an APRN prescribe Schedule II controlled substances once they have "at least 2 years or 2,000 hours of clinical experience", or otherwise "pursuant to a protocol approved by a collaborating physician". 2 years and 2,000 hours are not equivalent (2,000 hours is roughly one full-time year), and the statute uses "or", so a part-time APRN and a full-time APRN cross the line at different points. The platform cannot date the end of the protocol requirement without knowing which limb the licensee is relying on. OPEN: confirm with the Board how it evidences the threshold. Source: https://www.leg.state.nv.us/NRS/NRS-632.html'),

 ('UT','APRN','ce_hours_total',
  '30 hours CME plus 400 licensed practice hours per two-year renewal period',
  'applies ONLY to APRNs licensed before July 1, 1992; everyone else renews on national certification',
  'A SUBSET REQUIREMENT THAT MUST NOT BE GENERALISED. Utah DOPL''s APRN renewal form states: "In accordance with Subsection R156-31b-303(3)(b), you must have a current certification in your practice specialty. APRNs licensed before July 1, 1992, must complete 30 hours of approved CME and 400 hours of licensed practice during the two-year renewal period." The 30-hour figure therefore applies to a cohort licensed more than 34 years ago and to nobody else. Seeded as value_json with an explicit applies_to for exactly this reason: a bare value_num 30 would invoice every Utah APRN a CE duty the Division does not impose on them. OPEN: the platform has no licensure-date attribute to resolve which pathway a given APRN is on. Source: http://commerce.utah.gov//wp-content/uploads/2022/10/aprn-with-controlled-substance-renewal.pdf'),

 ('HI','MD','ce_hours_total',
  'Hawaii Medical Board: 40 category 1 or 1A CME hours per biennium',
  'the only Board document found stating an hour count is an audit notice for the biennium ending 01/31/2024',
  'THE NUMBER IS RIGHT BUT THE DOCUMENT IS STALE. The Hawaii Medical Board''s CME landing page says only that "MD''s must meet CME requirements contained in Subchapter 5 of the Board''s rules" and publishes no hour count; HAR ch. 16-85 subchapter 5 itself was not retrievable. The 40-hour figure comes from the Board''s own Notice of Audit for the 2022-2023 biennium, which also sets a prorated 20 hours for physicians licensed between 02/01/2022 and 01/31/2023. That is a primary Board document, but it governs a biennium that has closed, and a board can change an hour count between biennia. OPEN: obtain the current subchapter 5 text or a current-biennium audit notice. Sources: https://cca.hawaii.gov/wp-content/uploads/2026/01/2023-MD-Notice-of-Audit.pdf and https://cca.hawaii.gov/pvl/boards/medical/physician-podiatrist-and-emt-continuing-education-requirements/'),

 ('ID','MD','ce_cycle_months',
  '40 hours of practice-relevant CME during the prior two (2) years (IDAPA 24.33.01)',
  'the CE look-back is 24 months but the Idaho physician LICENCE renewal period was never established',
  'A CE CLOCK WITHOUT A VERIFIED RENEWAL CLOCK. IDAPA 24.33.01 gives a clean 24-month CME look-back, and DOPL publishes an annual-sounding "License Renewal Fee -- Curr Yr". Those two facts are consistent with either an annual renewal carrying a two-year CE look-back or a biennial renewal, and nothing read on 2026-09-18 settles it: the DOPL Board of Medicine licensing page carries no renewal-period statement, the DOPL press release on renewal-cycle changes covers Veterinary Medicine only, and Idaho Code Title 54 ch. 18 has no section headed for renewal in the chapter index. ID/MD/renewal_cycle_months is therefore NOT SEEDED. Do not infer it from ce_cycle_months. Sources: https://files.dfm.idaho.gov/dfm-admin-website/rules/current/24/243301.pdf, https://dopl.idaho.gov/bom/bom-licensing/, https://dopl.idaho.gov/pressrelease/fee-changes-and-renewal-cycle-reminders/'),

 ('ID','MD','ce_hours_total',
  '40 hours of practice-relevant CME during the prior two (2) years',
  'one of three alternative compliance pathways, not a universal hour requirement',
  'THE 40 HOURS ARE OPTIONAL FOR MOST IDAHO PHYSICIANS. IDAPA 24.33.01 lets a physician satisfy continued competence by ANY of: 40 hours of practice-relevant CME in the prior two years; maintaining current board certification from ABMS, the AOA or the Royal College of Physicians and Surgeons of Canada; or full-time participation in an accredited residency or fellowship. A board-certified physician owes no CME hours at all under this rule. The row is seeded as value_num because 40 is a genuine per-cycle figure for the population that uses that pathway, but a consumer that treats it as universal will invoice board-certified Idaho physicians a duty they do not have. OPEN: decide whether alternative-pathway requirements need a value_json shape of their own. Source: https://files.dfm.idaho.gov/dfm-admin-website/rules/current/24/243301.pdf'),

 ('AK','MD','ce_hours_total',
  'an average of 25 credit hours of CME during each year of the previous license period',
  'the Board states the quantum per year while renewing every 24 months',
  'CE CLOCK AND RENEWAL CLOCK DIFFER, AND THE BOARD SAYS "AVERAGE". Alaska licences renew every two years (expiring 31 December of even-numbered years) but the CME requirement is expressed as an ANNUAL AVERAGE of 25 hours across the license period. 25/12 months is seeded rather than 50/24 months because 50 is not a figure the Board publishes, and because "average" means a licensee may lawfully complete 10 hours in one year and 40 in the next. Any consumer generating an annual 25-hour milestone will raise false alarms against a compliant licensee. OPEN: confirm whether the Board audits the annual average or only the two-year total. Source: https://www.commerce.alaska.gov/web/portals/5/pub/med0077.pdf'),

 ('WY','MD','renewal_cycle_months',
  'Wyoming Board of Medicine rules: "all physician licenses shall be renewed no later than June 30th of each calendar year"',
  'the Board''s own renewal page is headed "2026-2027 Physician license renewals"',
  'READS AS A CONTRADICTION BUT PROBABLY IS NOT -- AND THAT "PROBABLY" IS THE POINT. The Board rule filed with the Wyoming Secretary of State makes renewal annual, due 30 June each year, with a prorated first renewal depending on issue date. The Board''s live renewal page refers to "2026-2027 Physician license renewals", which reads as biennial at a glance but is consistent with a licensure YEAR running 1 July 2026 to 30 June 2027. The seeded value is 12 months, from the rule. OPEN: confirm against a current Board page that says "annual" in so many words, because a 12-vs-24-month error here doubles or halves every Wyoming physician''s renewal calendar. Sources: https://wyoleg.gov/arules/2012/rules/ERR23-021.pdf and https://wyomedboard.wyo.gov/physicians/renew-license'),

 ('WY','APRN','renewal_window_days',
  'renewal takes place "between October 1st and December 31st" of the renewal year',
  '92 days is the exact span of those dates, computed, not published',
  'A COMPUTED DAY COUNT. The Wyoming State Board of Nursing publishes the window as two calendar dates, not as a number of days. October 1 to December 31 inclusive is 92 days (31 + 30 + 31), so the conversion is exact rather than approximate, but it is still a conversion: the Board has not said "92 days" and the window is anchored to fixed calendar dates rather than to the individual licensee''s expiration date, unlike every other renewal_window_days row in this asset. A consumer that computes "expiry minus 92 days" will get the right answer only because Wyoming expirations fall on 31 December. OPEN: consider a window shape that can express fixed-date windows. Source: https://wsbn.wyo.gov/renewal')

) as c(state, license_type, field_key, published_value, observed_value, notes)
join requirements r
  on r.state = c.state
 and r.license_type = c.license_type
 and r.field_key = c.field_key
 and r.is_current
 and r.deleted_at is null
 and r.verified_by = 'research-agent-group-d';

-- ---------------------------------------------------------------------------
-- A. GAPS -- in-scope field_keys with no verified value. requirement_id NULL.
-- ---------------------------------------------------------------------------
insert into requirement_conflicts
  (requirement_id, published_value, observed_value, observed_at, observed_by,
   occurrences, resolution, notes)
values

-- ---- ARIZONA --------------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP AZ/MD/renewal_window_days and AZ/MD/fingerprint_required. The Arizona Medical Board MD renewal application page states the cycle and the fee but says nothing about when the online renewal transaction opens, and lists "Fingerprint Requirements" only as a navigation item with no substantive text on the page. A.R.S. sec. 32-1430 is silent on both. NOT SEEDED. Source consulted: https://azmd.gov/Licensure/Licensure/md-renewal-application'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP AZ/MD/initial_license_fee_cents. The Arizona Medical Board publishes the $500 biennial renewal fee on its renewal page but no initial licensure application fee was located on a Board page. NOT SEEDED.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP AZ/APRN/ce_hours_total and AZ/APRN/ce_cycle_months. The Arizona State Board of Nursing renewal page sets out the 4-year RN cycle and the DEA-conditional 3-hour opioid CE requirement but publishes NO general continuing education hour requirement for RNs or APRNs on that page. Arizona is widely understood not to impose general nursing CE, but absence of a published number is not a verified zero and 0 is NOT seeded here (contrast CO/APRN, where the Board states the negative in terms). OPEN: obtain an affirmative statement from AZBN or read A.A.C. R4-19-... directly. Source consulted: https://azbn.gov/licenses-and-certifications/renew-your-license'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP AZ/APRN/renewal_fee_cents. The Arizona State Board of Nursing Agency Fees page has a complete Renewals table -- CNA, LHA, LNA, CMA, RN/LPN ($160 every 4 years), School Nurse, Telehealth RN, Telehealth APRN -- and there is NO Nurse Practitioner renewal row on it. Either NP certification renews at no charge alongside the RN licence, or the fee is published elsewhere. A missing table row is not a verified $0. NOT SEEDED. Source: https://azbn.gov/licenses-and-certifications/agency-fees'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP AZ/MD/csr_required and AZ/APRN/csr_required. No Arizona Medical Board or Board of Nursing page was found stating either that Arizona issues a state controlled substance registration or that it does not. A.R.S. sec. 32-3248.02 imposes opioid CE on DEA registrants without referring to any state registration, which is suggestive but not dispositive. A negative cannot be asserted from silence. NOT SEEDED.'),

-- ---- WASHINGTON -----------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP WA/APRN/renewal_window_days. The Washington State Board of Nursing says "You can renew your license online 85-90 days before your license expires." A range is not a value and picking an endpoint would be a guess, so this is NOT SEEDED -- the same treatment given to the TX/MD 60-90 day range in the first seed file. (WA/MD is seeded at 90 because the Medical Commission states a single figure: "may be renewed up to 90 days before it expires".) Source: https://nursing.wa.gov/licensing/renew-or-reactivate-license'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP WA/APRN/supervision_required and WA/APRN/collaborative_agreement_required. Washington is universally described as a full-practice-authority state, and THAT IS EXACTLY WHY THIS ROW EXISTS RATHER THAN A SEEDED false. Four sources were read on 2026-09-18 and none of them states the proposition: RCW 18.79.050 defines advanced practice registered nursing as "an expanded role ... the scope of which is defined by rule by the board" and says nothing about supervision; the Board of Nursing FAQ page carries only POLST-signing questions; the Board''s ARNP Guidance page says only "The broadly written laws and rules allow nurses to practice to their full scope of practice in any setting" and refers the reader onward to RCW 18.79 and WAC 246-840; and WAC 246-840 was not retrieved. Reputation is not a citation. NOT SEEDED. OPEN: read WAC 246-840-300 (ARNP scope) directly. Sources: https://app.leg.wa.gov/RCW/default.aspx?cite=18.79.050, https://nursing.wa.gov/practicing-nurses/frequently-asked-questions, https://nursing.wa.gov/practicing-nurses/arnp-guidance'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP WA/MD and WA/APRN fingerprint_required and csr_required. Neither the Washington Medical Commission licensing pages nor the Board of Nursing licensing pages read on 2026-09-18 state a fingerprint condition, and neither addresses whether Washington issues a state controlled substance registration separate from the DEA. NOT SEEDED for either profession.'),

-- ---- OREGON ---------------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP OR/MD/renewal_window_days. The Oregon Medical Board''s renewal page says only "Please complete your renewal by December 1 to ensure Board staff have time to review and process the renewal application" -- a processing courtesy, not the date renewal opens. NOT SEEDED. Source: https://www.oregon.gov/omb/licensing/pages/renew.aspx'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP OR/APRN/ce_hours_total and OR/APRN/ce_cycle_months. Oregon replaced nursing practice-hour competency with a CE model effective 2026-01-01, and in the current phase the ONLY CE required of an APRN renewal applicant is the 1-hour pain management module and the 2-hour cultural competency course (both seeded). There is no general APRN hour figure to seed. From 2028-01-01 the OSBN fact sheet provides that "CRNA or NP applicants" satisfy CE by holding current national certification, with RN applicants moving to 20 hours within two years and CNS applicants to 75 hours within five years -- an alternative-pathway requirement with no APRN hour count at all. NOT SEEDED. OPEN: revisit on 2028-01-01; also decide how to represent "national certification satisfies CE". Source: https://www.oregon.gov/osbn/Documents/Resource_Renewal-CE_Fact_Sheet12-31-25.pdf'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP OR/APRN/initial_license_fee_cents, OR/APRN/renewal_fee_cents, OR/APRN/supervision_required, OR/APRN/collaborative_agreement_required. The OSBN fee schedule could not be read: the Oregon Secretary of State administrative rules site (secure.sos.state.or.us/oard/) returned repeated robots.txt fetch failures and connect timeouts on 2026-09-18, and OSBN''s own fee and renewal pages 404. The only fee figures available were "$0.00" placeholders on the Business Xpress licence directory, which are not real. Nothing on OSBN or in retrievable Oregon law was found addressing NP supervision or collaboration. NOT SEEDED. OPEN: retrieve OAR ch. 851 div. 11 (fees) and div. 50 (nurse practitioner scope) by hand or by browser session.'),

-- ---- COLORADO -------------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP CO/APRN/renewal_cycle_months. This is the most consequential gap in this file. The Colorado Board of Nursing homepage states only that "RN, APN and RXN Renewal is now open. Licenses expire on 9/30/26" -- an expiration DATE with no period. dpo.colorado.gov/Nursing/Renewals 404s, the Nursing Licensing Services page carries no renewal-period statement, the Nursing FAQ addresses CE but not renewal frequency, the Nursing Laws page links the Nurse Practice Act only through a Google Drive document, and the DORA division-wide FAQ mentions only "within 6 weeks of the license expiration date" for online renewal. A single expiry date does not establish a cycle length, and inferring 24 months from the CO physician cycle or from a neighbouring state is exactly the inference this asset forbids. NOT SEEDED. OPEN: read C.R.S. 12-255-119 or 3 CCR 716-1 directly. Sources consulted: https://dpo.colorado.gov/Nursing, https://dpo.colorado.gov/Nursing/FAQ, https://dpo.colorado.gov/Nursing/Laws, https://dpo.colorado.gov/FAQ'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP CO/MD and CO/APRN initial_license_fee_cents and renewal_fee_cents. DORA does not publish a fee schedule as a retrievable document for either board: dpo.colorado.gov/Medical/LicensingServices returns HTTP 403 to automated fetch, the Medical Applications and Forms page says only that "All fees and mailing instructions are available on the respective applications and forms", the Physician Licensing Requirements page says "All fees are subject to review and change on July 1 each year" without naming an amount, and the actual figures live inside the apps2.colorado.gov licensing application, which requires a session. NOT SEEDED for either profession. OPEN: retrieve by hand or by browser session.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP CO/MD/fingerprint_required and CO/MD/renewal_window_days, and CO/MD and CO/APRN csr_required. The Colorado Medical Board''s Physician Licensing Requirements page makes no mention of a fingerprint or criminal history background check, and neither board page addresses a state controlled substance registration. No renewal window is published. Silence is not a "no". NOT SEEDED.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP CO/APRN/supervision_required. Colorado''s instrument is the RXN prescriptive-authority mentorship, seeded under collaborative_agreement_required as value_json. Whether Colorado additionally imposes physician SUPERVISION on an APN, and whether the answer differs for an APN without prescriptive authority, was not established from a primary source. NOT SEEDED rather than duplicating the mentorship finding under a second key.'),

-- ---- UTAH -----------------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP UT/MD/ce_topic_suicide_prevention_hours. Utah DOPL''s physician renewal page requires completion of "at least one suicide prevention training course" and lists three named half-credit courses -- "Suicide Safety Planning with Patients (0.5 credit)", "Talking to Patients About Suicide (0.5 credit)", "Counseling on Access to Lethal Means (0.5 credit)". Whether the obligation is 0.5 hours (one course) or 1.5 hours (all three), and whether it recurs each cycle or is one-time, is not stated on the page. An hour count cannot be picked from a list of alternatives. NOT SEEDED. Source: https://commerce.utah.gov/dopl/physician-and-surgeon/renew-a-license/'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP UT/APRN/supervision_required and UT/APRN/collaborative_agreement_required. Utah Code ch. 58-31b was read in full on 2026-09-18. Sec. 58-31b-302(2)(b) authorises a licensed APRN to "maintain and promote health and prevention of disease; diagnose, treat, correct, consult, and provide a referral" and sec. 58-31b-803(1) provides that "a licensed advanced practice registered nurse may prescribe or administer a prescription drug" with no physician-oversight condition attached; the only supervision-type constraint in the chapter applies to CRNAs, whose prescriptive authority is limited to five-day supplies around a procedure. That is a strong affirmative grant, but the chapter nowhere states in terms that supervision or a collaborative agreement is NOT required, and asserting the negative from a grant of authority is an inference rather than a citation. NOT SEEDED. OPEN: find a DOPL or Board of Nursing page that says it, or cite R156-31b directly. Source: https://le.utah.gov/xcode/Title58/Chapter31b/C58-31b_1800010118000101.pdf'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP UT/MD and UT/APRN renewal_window_days and fingerprint_required, and UT/APRN/ce_cycle_months. Utah DOPL publishes fixed expiration dates (01/31 of even years) rather than a rolling renewal window, and no fingerprint condition appears on the renewal pages read. UT/APRN/ce_cycle_months is not seeded because the only CE hour figure for Utah APRNs (the pre-1992 cohort''s 30 hours) is itself a value_json subset row, and seeding a bare CE cycle alongside it would imply a general hour requirement that does not exist. NOT SEEDED.'),

-- ---- NEVADA ---------------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP NV/MD/fingerprint_required. NRS ch. 630 contains a section headed "Submission of fingerprints; conditions and limitations on information provided by Board" (NRS 630.167) and a separate disciplinary-context fingerprint provision (NRS 630.342). A SECTION HEADING IS NOT A REQUIREMENT: the heading establishes that the Board handles fingerprints, not that every applicant or renewing licensee must submit them, and the body text was not read. NOT SEEDED. Source: https://www.leg.state.nv.us/nrs/nrs-630.html'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP NV/MD/renewal_window_days and NV/APRN/renewal_window_days. The Nevada State Board of Medical Examiners publishes no renewal window. The Board of Nursing''s RN/LPN Renewal FAQ states "Renewal applications can be submitted online within 60 days from your current expiration date", but that FAQ is scoped to RN and LPN; the APRN Renewal FAQ does not state a window, and the RN figure was NOT carried across to the APRN licence. NOT SEEDED for either. Sources: https://nevadanursingboard.org/wp-content/uploads/2020/06/RN.LPN-Renewal-FAQ.pdf and https://nevadanursingboard.org/wp-content/uploads/2020/06/APRN-Renewal-FAQ.pdf'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP NV/MD and NV/APRN csr_required. Nevada historically issued a state controlled substance registration through the Board of Pharmacy, and the Medical Board''s CME table refers to licensees "registered to dispense" controlled substances, which implies some state registration exists. Neither the Board of Medical Examiners nor the Board of Nursing publishes a statement of what that registration is, whether it is still issued, what it costs or how often it renews, and the Board of Pharmacy was not read. NOT SEEDED -- and csr_renewal_cycle_months and csr_fee_cents are consequently unseeded too. OPEN: read NRS ch. 453 and the Nevada State Board of Pharmacy.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP NV/APRN/supervision_required. NRS 632.237 addresses the collaborating-physician protocol only in the narrow Schedule II prescribing context (seeded under collaborative_agreement_required as value_json). It does not state whether a Nevada APRN practises under physician supervision generally, and no Board of Nursing page addressing supervision was read. NOT SEEDED.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP NV/MD/ce_topic_* prorated cohorts. The Board''s CME table sets a 40-hour total for licensees initially licensed "Prior to 7/1/2025 or 7/1/2025-12/31/2025" and implies different (prorated) totals for later cohorts, which the table''s remaining columns were not fully legible for. The seeded 40 is the established-licensee figure. OPEN: obtain the prorated figures for licensees first licensed on or after 1/1/2026. Source: https://medboard.nv.gov/uploadedFiles/mednvgov/content/Licensees/CME_Requirements_MDs_PAs_AAs.pdf'),

-- ---- NEW MEXICO -----------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP NM/APRN/initial_license_fee_cents. 16.12.2 NMAC carries a fee schedule in which the advanced practice application fee reads as $100 while the RN application fee reads as $150 -- the inverse of the renewal relationship, where both are $110. The reading may be correct (an advanced practice certificate layered on an existing RN licence can reasonably cost less than an initial RN licence) or it may be a misread of an adjacent table row. Because the mapping could not be confirmed against a second source, the figure is NOT SEEDED rather than seeded at a plausible-looking number. NM/APRN/renewal_fee_cents IS seeded, because $110 appears consistently. Source: https://www.srca.nm.gov/parts/title16/16.012.0002.html'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP NM/APRN/collaborative_agreement_required. 16.12.2 NMAC states that "The CNP collaborates as necessary with other healthcare providers. Collaboration includes discussion of diagnosis and cooperation in managing and delivering healthcare." That is a professional duty of collaboration, NOT a collaborative practice AGREEMENT with a named physician, and the two are legally distinct instruments. Mapping the former onto this field_key would misstate the obligation as a document a client must hold. NOT SEEDED; supervision_required carries the substance instead (seeded false). Source: https://www.srca.nm.gov/parts/title16/16.012.0002.html'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP NM/MD and NM/APRN csr_required, csr_renewal_cycle_months and csr_fee_cents. New Mexico is one of the states most likely in this group to operate a live state controlled substance registration (through the Board of Pharmacy under NMSA ch. 30 art. 31), which would make csr_renewal_cycle_months and csr_fee_cents meaningful for the first time in this asset. Neither 16.10 NMAC (medical board) nor 16.12 NMAC (nursing board) states it, and the Board of Pharmacy was not read. NOT SEEDED. OPEN: read 16.19 NMAC and NMSA 30-31-11.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP NM/MD and NM/APRN renewal_window_days and fingerprint_required. Neither 16.10.4 NMAC nor 16.12.2 NMAC states when renewal opens, and neither board rule read on 2026-09-18 imposes a fingerprint condition. NOT SEEDED.'),

-- ---- IDAHO ----------------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP ID/MD/renewal_cycle_months. See the paired qualifier on ID/MD/ce_cycle_months: a 24-month CME look-back was verified but the licence renewal period was not, and the two are not the same thing. NOT SEEDED. This is the single most important missing value for Idaho.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP ID/APRN/ce_hours_total and ID/APRN/ce_cycle_months. IDAPA 24.34.01 conditions APRN renewal on submitting "evidence of current APRN certification by a national organization recognized by the Board" and "evidence, satisfactory to the Board, of participation in a peer review process acceptable to the Board". Neither is an hour count, and the rule sets none. There is nothing to seed and 0 would be wrong, because the national certifier''s CE requirement is real. NOT SEEDED. Source: https://files.dfm.idaho.gov/dfm-admin-website/rules/current/24/243401.pdf'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP ID/APRN/initial_license_fee_cents, ID/APRN/renewal_fee_cents and ID/APRN/collaborative_agreement_required. The DOPL fee-change document retrieved on 2026-09-18 covers Medicine only; no equivalent Nursing fee document was located. IDAPA 24.34.01 contains no physician supervision requirement and describes the APRN as a "licensed independent practitioner" -- seeded as supervision_required = false -- but it does not separately address whether a collaboration instrument is required, so that key is left empty rather than duplicated. NOT SEEDED.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP ID/MD and ID/APRN renewal_window_days, fingerprint_required and csr_required. None of the Idaho DOPL pages or IDAPA chapters read on 2026-09-18 addresses any of these. NOT SEEDED.'),

-- ---- WYOMING --------------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP WY/MD/ce_hours_total, WY/MD/ce_cycle_months, WY/MD/initial_license_fee_cents, WY/MD/renewal_fee_cents, WY/MD/renewal_window_days. Wyoming is the least-covered jurisdiction in this file. The Board of Medicine''s rules filing indexes a CME provision at Chapter 3 Section 7, but the Secretary of State rule PDFs that were retrievable (ERR23-021, AR11-018medicine) contain Chapters 1, 2 and only fragments of Chapter 3, and none of them includes Section 7. The Board''s fee schedule is published only as a PDF behind a path that 404s ("Fee Schedule for Website 8-25-2026.pdf"), and the Board''s renewal page carries deadline notices rather than requirements. The only Wyoming physician value verified is the annual 30 June renewal cycle. NOT SEEDED. OPEN: retrieve the complete Board of Medicine Rules Chapter 3 and the current fee schedule by hand. Sources consulted: https://wyomedboard.wyo.gov/physicians/renew-license, https://wyomedboard.wyo.gov/resources/fee-schedule, https://wyoleg.gov/arules/2012/rules/ERR23-021.pdf, https://www.wyoleg.gov/ARULES/2011/AR11-018medicine.pdf'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP WY/APRN/ce_hours_total and WY/APRN/ce_cycle_months. The Wyoming State Board of Nursing states that Wyoming has no mandatory continuing education requirement: continued competency is demonstrated by ANY ONE of several methods -- for an APRN, "Current national Certification in role and population focus", or (for APRNs recognised before 1 July 2005 without national certification) "Completion of sixty (60) or more contact hours" plus "Completion of four hundred (400) or more hours practicing as an APRN during the last two (2) years". A menu of alternatives is not an hour requirement, and the 60-hour figure applies only to a pre-2005 cohort. NOT SEEDED. The two topic requirements that ARE unconditional for prescribers (15 pharmacology hours, 3 controlled substance hours) are seeded as value_json. Sources: https://wsbn.wyo.gov/renewal and https://www.wyoleg.gov/ARules/2012/Rules/ARR17-088.pdf'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP WY/APRN/supervision_required and WY/APRN/collaborative_agreement_required. Neither the Board''s renewal page nor its licensure/fees rule addresses supervision or a collaboration instrument, and Wyo. Stat. ch. 33-21 was not read. NOT SEEDED.'),

-- ---- ALASKA ---------------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP AK/APRN/ce_hours_total and AK/APRN/ce_cycle_months. Alaska''s continued competency rule is a CHOICE, not an hour count: under 12 AAC 44.610 a nurse must complete a board-approved refresher course, OR any two of (a) "30 contact hours of continuing education", (b) "30 hours of participation in uncompensated professional activities", (c) "320 hours of employment as an RN or LPN" -- or alternatively attain a nursing credential or pass the NCLEX. A licensee who chooses employment plus professional activities owes zero CE hours. Seeding 30 would invoice a duty that is optional. NOT SEEDED. The 12 pharmacotherapeutics hours that ARE unconditional for prescribing APRNs are seeded as value_json. Sources: https://www.commerce.alaska.gov/web/cbpl/ProfessionalLicensing/BoardofNursing/RenewalInformation and https://www.commerce.alaska.gov/web/portals/5/pub/nur4121.pdf'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP AK/APRN/renewal_fee_cents. The Alaska Board of Nursing''s Registered Nurse License Renewal form publishes "$200.00" biennial and "$100.00" prorated for the RN licence and carries no APRN line. Because the APRN licence is a separate credential that merely renews on the same date as the RN licence, the RN figure was NOT carried across. NOT SEEDED. Source: https://www.commerce.alaska.gov/web/portals/5/pub/nur4121.pdf'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP AK/APRN/supervision_required and AK/APRN/collaborative_agreement_required. The Board''s APRN licence application defines an APRN as "a licensed independent practitioner", which is suggestive, but a definitional phrase in an application form is weaker than the Idaho and New Mexico rule text that was seeded, and the form does not address collaborative practice arrangements at all. Alaska has historically required a collaborative plan for APRN prescriptive authority under 12 AAC 44.430, which was not read. NOT SEEDED -- this is the one full-practice-authority assumption in this group that would be easiest to get wrong. OPEN: read 12 AAC 44.400 and 12 AAC 44.430. Source: https://www.commerce.alaska.gov/web/portals/5/pub/nur4028.pdf'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP AK/MD/initial_license_fee_cents, AK/MD/renewal_window_days, AK/MD/fingerprint_required, and AK/MD and AK/APRN csr_required. The Alaska State Medical Board''s renewal application publishes the $350 biennial renewal fee but no initial licensure fee, and the Board''s main page and FAQ carry neither a renewal window nor a fingerprint statement. Neither board addresses a state controlled substance registration. NOT SEEDED.'),

-- ---- HAWAII ---------------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP HI/APRN/ce_hours_total and HI/APRN/ce_cycle_months. The Hawaii Board of Nursing states that "all Hawaii nurse licensees are required to complete one of the learning activity options for continuing competency prior to the renewal of their Hawaii nurse license" and directs licensees to a Continuing Competency Manual that was not retrieved. "One of the learning activity options" is a menu, not an hour count, and no number is published on the Board page. NOT SEEDED. OPEN: retrieve the Hawaii Board of Nursing Continuing Competency Manual and HAR ch. 16-89. Source: https://cca.hawaii.gov/pvl/boards/nursing/'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP HI/APRN/supervision_required and HI/APRN/collaborative_agreement_required. HRS sec. 457-8.6 (advanced practice registered nurse prescriptive authority) returned HTTP 403 to every attempt on 2026-09-18, and the Board of Nursing page carries no statement on supervision or collaboration. The only other candidate source located was a DRAFT of Hawaii Administrative Rules ch. 16-89, which is not a citable current rule. NOT SEEDED. OPEN: retrieve HRS 457-8.5 and 457-8.6 by hand. Source attempted: https://www.capitol.hawaii.gov/hrscurrent/Vol10_Ch0436-0474/HRS0457/HRS_0457-0008_0006.htm'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP HI/MD/initial_license_fee_cents and HI/APRN/initial_license_fee_cents, and HI/MD and HI/APRN renewal_window_days, fingerprint_required and csr_required. The DCCA board pages publish renewal fees but not application fees, state fixed biennial expiration dates rather than a rolling renewal window, and address neither fingerprints nor a state controlled substance registration. NOT SEEDED.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'GAP HI/MD/ce_topic_* (all). No mandated CME subject for Hawaii physicians was found on any Board page or in the Board''s audit notice, which speaks only to Category 1/1A hour totals. Hawaii may genuinely mandate no subjects, but that was not verified. NOT SEEDED.'),

-- ---- CROSS-CUTTING --------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'SCOPE GAP: license_type ''DO'' is NOT COVERED in any of these eleven states. In Oregon the Medical Board licenses MD, DO and DPM under one fee schedule and one CME rule, so the seeded MD rows are LIKELY to hold for Oregon DOs, and Washington runs a parallel but SEPARATE osteopathic chapter (WAC 246-853 / 246-921) whose numbers differ from the allopathic ones. Arizona, Nevada and Utah have SEPARATE osteopathic boards with their own rules and fee schedules, and applying the MD rows to a DO there would be wrong. "Likely" is not verified and no DO-specific page was read for any state. Any consumer that resolves a DO to the MD rows is manufacturing an unverified obligation.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'CE CYCLE != RENEWAL CYCLE IN FOUR OF THESE ELEVEN STATES, AND THAT IS THE MOST LIKELY SOURCE OF A WRONG OBLIGATION DATE FROM THIS FILE. WA/MD renews every 24 months but runs CE on a 48-month clock (200 hours). OR/MD renews every 24 months but the Board states CME as 30 hours/YEAR. AK/MD renews every 24 months but the Board states CME as an average of 25 hours/YEAR. NM/MD renews every 36 months while NM/APRN renews every 24. HI/MD renews on a biennium ending 01/31 of even years while HI/APRN renews on one ending 06/30 of odd years. In every case ce_cycle_months is seeded to the BOARD''S OWN stated CE period and ce_hours_total to the BOARD''S OWN stated number, with no multiplication performed. A consumer that reads ce_hours_total and silently anchors it to renewal_cycle_months will double Oregon and Alaska physicians'' CME obligation and halve Washington''s. Consumers MUST read ce_cycle_months.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'FULL PRACTICE AUTHORITY WAS NOT ASSUMED, AND MOSTLY COULD NOT BE VERIFIED. All eleven of these states are commonly listed as full-practice-authority NP states. Only THREE supervision_required = false rows are seeded, each from a source that states the proposition in terms: Arizona ("Arizona does not require physician supervision or collaboration for the independent practice of nurse practitioners", AZBN scope-of-practice FAQ), New Mexico ("The CNP makes independent decisions regarding the health care needs of the client", 16.12.2 NMAC) and Idaho (APRN described as a "licensed independent practitioner", IDAPA 24.34.01). For WA, OR, CO, UT, NV, WY, AK and HI the proposition is UNSEEDED because no primary source stating it was retrieved -- see the per-state gap rows. Three states in this group turn out to carry a conditional instrument that a flat "full practice authority" label hides entirely: Colorado''s 750-hour RXN mentorship, Nevada''s 2-year/2,000-hour Schedule II threshold, and Utah''s CRNA-only prescribing limit. The regional pattern is real but it is not uniform, and it is not a citation.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'FIRST LIVE STATE CSR IN THE ASSET: UTAH. csr_required, csr_renewal_cycle_months and csr_fee_cents were previously unseeded everywhere (TX and NY verified false; CA and FL unknown). Utah verifies TRUE for both MD and APRN: DOPL issues a state Controlled Substance Licence, renewed "as part of the associated practitioner license renewal" on the same 24-month clock, at $78 renewal / $100 application, and carrying its own 3.5-hour CE obligation under Utah Code 58-37-6.5. NOTE FOR CONSUMERS: because the Utah CSL renews inside the practitioner renewal, a licensee sees ONE transaction and TWO fees; csr_fee_cents is additive to renewal_fee_cents, not a component of it. The remaining ten states in this group are unseeded for csr_required because no board affirmatively addressed it; do not read that as false.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'NEW FIELD KEYS INTRODUCED BY THIS FILE, for the rules-plane author to ratify (PRD 15.5): ce_topic_suicide_prevention_hours (WA MD+APRN, NV MD+APRN), ce_topic_health_equity_hours (WA MD+APRN), ce_topic_cultural_competency_hours (OR MD+APRN, NV APRN), ce_topic_sbirt_hours (NV MD+APRN), ce_topic_bioterrorism_hours (NV APRN). None of the five maps onto an existing topic name without misstating the mandate. In particular, Washington''s "health equity" (RCW 43.70.613, WAC 246-12-820) and Oregon''s "cultural competency" (OAR 847-008-0077) are DISTINCT statutory subjects with different hour counts and different clocks, and neither is the same thing as the implicit bias requirement already seeded for California -- Oregon explicitly lists implicit bias training as only ONE of several ways to satisfy its cultural competency hours. Collapsing the three into ce_topic_implicit_bias_hours would produce a single wrong number for three states.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, 'unresolved',
 'SCHEMA GAP, RESTATED FOR THIS GROUP: the field_key set still has no slot for CE topic PERIODICITY, and this group leans on value_json harder than the first four states did. One-time: WA suicide prevention (6h, both professions), WA opioid (1h, MD), NV SBIRT (2h, MD), NV bioterrorism (4h, APRN). Off-renewal-cycle: WA health equity (every 4 years, both), NV suicide prevention (every 4 years, both), OR pain management (every 2 years against a 12-month CE clock), OR cultural competency (averaged over a 4-year audit period), OR/APRN pain management (every 36 months) and cultural competency (every 48 months) against a 24-month renewal. Population-conditional: AZ opioid (DEA), AK opioid (DEA), NM/APRN pain (DEA), NV controlled substance (dispensing registration), NV HIV stigma (emergency services setting), UT controlled substance (CSL holders), WA/APRN + WY/APRN + AK/APRN pharmacotherapeutics (prescriptive authority), UT/APRN CE total (pre-1992 cohort). ANY CONSUMER THAT READS value_num AND IGNORES value_json WILL SILENTLY DROP ALL OF THESE. Fixing it is a schema change, not a data change.');

commit;
