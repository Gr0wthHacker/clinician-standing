-- =============================================================================
-- requirement_conflicts_seed_group_b.sql -- what group B does NOT yet know.
--
-- Companion to requirements_seed_group_b.sql (MI, NC, VA, SC, TN, AL, MS, KY
-- complete; LA and WV partial; AR and OK NOT REACHED).
--
-- Two kinds of row live here, and both are deliberately left OPEN
-- (resolution = 'unresolved'), which blocks auto-clear (PRD 8.1 condition 6)
-- and raises RULE_UNCERTAIN (PRD 8.3):
--
--   A. GAPS -- a field_key in scope for a state/license_type for which no
--      primary source could be found and read on 2026-09-18. requirement_id is
--      NULL because no requirements row was written.
--
--   B. QUALIFIERS -- a requirements row EXISTS but a second official source, or
--      a statutory exception, narrows or contradicts it.
--
-- observed_by is 'research-agent-group-b' throughout, so this file owns only its
-- own rows and does not disturb requirement_conflicts_seed.sql.
--
-- Run AFTER requirements_seed_group_b.sql. Idempotent.
-- =============================================================================

begin;

delete from requirement_conflicts where observed_by = 'research-agent-group-b';

-- ---------------------------------------------------------------------------
-- B. QUALIFIERS on rows that exist.
-- ---------------------------------------------------------------------------
insert into requirement_conflicts
  (requirement_id, published_value, observed_value, observed_at, observed_by,
   occurrences, resolution, notes)
select r.id, c.published_value, c.observed_value,
       timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1,
       'unresolved', c.notes
from (values

 ('NC','APRN','ce_hours_total',
  '21 NCAC 32M .0107: "50 contact hours of continuing education each year"',
  'NC Board of Nursing NP continuing competence page: "50 contact hours of continuing education every two years"',
  'TWO OFFICIAL SOURCES DISAGREE, and the disagreement is a factor of two on an annually-renewed credential. The joint NP rule 21 NCAC 32M .0107, as published by the North Carolina Medical Board, says "the nurse practitioner shall earn 50 contact hours of continuing education each year beginning with the first renewal after initial approval to practice has been granted." The North Carolina Board of Nursing''s own NP continuing competence page says "the NP shall maintain national certification or earn 50 contact hours of continuing education every two years." The Board of Nursing framing also offers national certification as an ALTERNATIVE, which the rule text does not. The seeded value follows the RULE because the rule is the binding instrument and it matches the annual renewal in .0106(a); an annual 50-hour obligation is also the conservative reading. OPEN: ask both Boards which governs, and whether the certification alternative is real. Until resolved, do NOT bill a North Carolina NP for a 50-hour annual duty without flagging the uncertainty. Sources: https://www.ncmedboard.org/images/uploads/other_pdfs/subchapter_m_rules.pdf and https://www.ncbon.com/np-continuing-competence'),

 ('NC','APRN','ce_cycle_months',
  '12 months (21 NCAC 32M .0107, "each year")',
  '24 months (NC Board of Nursing NP continuing competence page, "every two years")',
  'Paired with the ce_hours_total conflict above and open for the same reason. An obligation generator that anchors NP CE to a 12-month clock when the Board of Nursing administers a 24-month one will produce wrong dates in every cycle.'),

 ('SC','MD','ce_topic_controlled_substance_hours',
  'S.C. Board of Medical Examiners CE sheet: "Two hours must be in safe prescribing and monitoring of controlled substances."',
  'S.C. Code Ann. sec. 40-47-37(A)(2)(a): "at least two (2) hours of which MAY be related to approved procedures of prescribing and monitoring controlled substances"',
  'TWO OFFICIAL SOURCES USE DIFFERENT MODAL VERBS on the same two hours. The Board''s published CE requirements sheet states the hours as mandatory ("must"); the statute the Board administers is drafted permissively ("may"), while in the same sentence requiring that "Each renewal form submitted pursuant to Section 40-47-41 must include a certificate of participation with the prescribing and monitoring education requirement issued by the organization from which the education was received" -- which reads as mandatory. The seeded value follows the Board sheet (mandatory, 2 hours) because that is what the Board enforces at renewal and it is the conservative reading. OPEN: confirm with the Board whether a licensee who completes 40 hours with no controlled-substance content can renew. Sources: https://www.llr.sc.gov/med/PDF/Medical_CE_Reqs.pdf and https://www.scstatehouse.gov/code/t40c047.php'),

 ('AL','APRN','csr_required',
  'true (Qualified Alabama Controlled Substances Certificate, annual)',
  'QACSC authority covers Schedules III, IV and V only',
  'The Alabama Board of Medical Examiners describes the QACSC as required "for prescribing Schedule III, IV, or V controlled substances in Alabama". A single boolean says a CRNP needs a state controlled substance credential, which is true, but it does not carry that the credential does not reach Schedule II. A platform that tells a CRNP the QACSC clears them to prescribe controlled substances generally would be wrong. OPEN: the schema needs a schedule-scope attribute on csr_required, or a csr_schedules field_key. Source: https://www.albme.gov/licensing/crnp-cnm/qacsc/'),

 ('AL','APRN','collaborative_agreement_required',
  'true (jointly approved collaborative practice, ABME and ABN)',
  'the approval does not renew and therefore generates no recurring obligation',
  'QUALIFIER, not a contradiction. The Alabama Board of Medical Examiners states: "Collaborative agreements are not renewed. They continue in effect until notification of termination is received." The $200 fee is a one-time fee "for a physician commencing a collaborative practice", and it is charged to the PHYSICIAN, not the CRNP. An obligation generator that schedules an annual or biennial collaborative-agreement renewal for an Alabama CRNP is manufacturing a duty that does not exist. OPEN: confirm whether any periodic re-attestation attaches to the approval. Source: https://www.albme.gov/licensing/crnp-cnm/collaboration/'),

 ('KY','APRN','ce_topic_pharmacotherapeutics_hours',
  '5 contact hours in pharmacology per earning period (201 KAR 20:215 Sec. 5(1)(a))',
  'content of the same 5 hours is constrained for DEA-registered APRNs with a PDMP account',
  'QUALIFIER. 201 KAR 20:215, Section 5(1)(b): "An APRN who is registered with the DEA and has a PDMP account ... shall earn a minimum of five (5) contact hours in pharmacology, INCLUDING at least three (3) contact hours on either pain management or addiction disorders." The COUNT is unchanged at 5; what changes is that 3 of the 5 are content-locked. A consumer that models only hour counts will tell a DEA-registered Kentucky APRN that any 5 pharmacology hours suffice, which is wrong. OPEN: the field_key set has no slot for content constraints within a topic. Source: https://apps.legislature.ky.gov/law/kar/titles/201/020/215/'),

 ('KY','APRN','renewal_fee_cents',
  'Kentucky Board of Nursing: "APRN Renewal ... $55 (Per designation)"',
  'a multi-designation APRN pays $55 for EACH population-focus designation',
  'QUALIFIER. The fee schedule''s "(Per designation)" qualifier means the seeded 5500 is a floor, not the amount every Kentucky APRN pays. An APRN licensed in two population foci pays $110. OPEN: the platform has no per-clinician designation-count attribute, so this fee cannot be resolved to an invoice line without one. Source: https://kbn.ky.gov/KBN%20Documents/fees-for-licensure-applications-and-services.pdf'),

 ('TN','APRN','collaborative_agreement_required',
  'true for prescribing APRNs (Collaborative Request / APRN Supervisory Request)',
  'the non-prescribing case was not established',
  'The Tennessee Board of Nursing''s continuing competence sheet requires a "Copy of current Collaborative Request/APRN Supervisory Request (formerly Notice and Formulary) if prescribing". It does not settle whether a Tennessee APRN who does not prescribe must hold a collaboration or supervision instrument to practise. The seeded value_json is scoped to prescribing for that reason. OPEN: read Tenn. Code Ann. sec. 63-7-123 and Board of Nursing Rules ch. 1000-04 in full. Source: https://www.tn.gov/content/dam/tn/health/documents/ContinuedCompetenceRequirements.pdf'),

 ('VA','APRN','ce_hours_total',
  'value_json: 40 hours, applying only to APRNs licensed before May 8, 2002 without current certification',
  'the default pathway (current national certification) carries no hour count at all',
  'QUALIFIER on a row that is deliberately value_json. 18VAC90-30-105(A) makes maintenance of current professional certification the competency requirement for every APRN "initially licensed on or after May 8, 2002" -- no hours. The 40-hour figure in subsection (B) reaches only pre-2002 licensees and retired-certification clinical nurse specialists, a population that shrinks every year. Any consumer that reads this row as a universal 40-hour Virginia APRN duty is fabricating an obligation for the large majority. OPEN: the platform has no per-clinician initial-licensure-date attribute to resolve this. Source: https://law.lis.virginia.gov/admincode/title18/agency90/chapter30/section105/'),

 ('MI','MD','ce_topic_implicit_bias_hours',
  'value_json: 1 hour for each year of the license or registration cycle',
  'the count is derived from cycle length, not published as a per-cycle figure',
  'QUALIFIER. Mich Admin Code R 338.7004(2) expresses the renewal requirement as a RATE ("1 hour ... for each year of the applicant''s license or registration cycle"), not as a per-cycle total. For a Michigan MD on a 3-year cycle that resolves to 3 hours, and for an RN/NP on a 2-year cycle to 2 hours, but the rule never states either number. The row is value_json carrying the rate so that no consumer records a per-cycle constant that would break if Michigan changed a cycle length. R 338.7004(3) additionally prohibits carrying hours forward between cycles, which a bare hour count cannot express. Source: https://ars.apps.lara.state.mi.us/AdminCode/DownloadAdminCodeFile?FileName=R+338.7001+to+R+338.7005.pdf&ReturnHTML=True'),

 ('LA','MD','csr_fee_cents',
  'Louisiana Board of Pharmacy: $45.00 CDS application fee for MD',
  'application fee only; the renewal fee and licence term are not published on the page read',
  'QUALIFIER. The Board of Pharmacy''s application-transparency page gives the fee "due when submitting the online application" and does not state the CDS licence term or the renewal amount. Seeding csr_renewal_cycle_months from this page would be a guess, so it is absent. A consumer that treats 4500 as a recurring annual charge is asserting something the source does not say. OPEN: read La. R.S. 40:973 and Louisiana Board of Pharmacy regulations for the term and renewal fee. Source: https://www.pharmacy.la.gov/page/application-process-transparency-cds-license-practitioners')

) as c(state, license_type, field_key, published_value, observed_value, notes)
join requirements r
  on r.state = c.state
 and r.license_type = c.license_type
 and r.field_key = c.field_key
 and r.is_current
 and r.deleted_at is null
 and r.verified_by = 'research-agent-group-b';

-- ---------------------------------------------------------------------------
-- A. GAPS -- in-scope field_keys with no verified value. requirement_id NULL.
-- ---------------------------------------------------------------------------
insert into requirement_conflicts
  (requirement_id, published_value, observed_value, observed_at, observed_by,
   occurrences, resolution, notes)
values

-- ---- JURISDICTIONS NOT REACHED --------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'SCOPE GAP: ARKANSAS (AR) IS NOT COVERED AT ALL, for either MD or APRN. No Arkansas State Medical Board or Arkansas State Board of Nursing page was fetched or read in this pass. Every AR field_key is unverified. Do not resolve an Arkansas clinician against a neighbouring state''s rows -- Arkansas differs from its neighbours on at least the state controlled substance question, which was not checked. NOT SEEDED.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'SCOPE GAP: OKLAHOMA (OK) IS NOT COVERED AT ALL, for either MD or APRN. The Oklahoma State Board of Medical Licensure and Supervision and the Oklahoma Board of Nursing were not read. Of particular note, the Oklahoma Bureau of Narcotics and Dangerous Drugs (OBNDD) issues a state controlled substance registration separate from the federal DEA registration; obndd.ok.gov returned an edge-server 403 to every automated fetch attempted on 2026-09-18, so csr_required for Oklahoma is UNVERIFIED and must not be assumed either way. NOT SEEDED.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'SCOPE GAP: WEST VIRGINIA APRN (WV/APRN) IS NOT COVERED AT ALL. The WV Board of Examiners for Registered Professional Nurses was not read. WV/MD is itself only partially covered (renewal cycle, CE total, CE cycle and the controlled substance CME topic). NOT SEEDED.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'SCOPE GAP: LOUISIANA IS ONLY PARTIALLY COVERED. Verified: LA/MD renewal_window_days (56), LA/MD one-time CDS CME, and csr_required plus the CDS application fee for both MD and APRN. NOT VERIFIED and NOT SEEDED for LA/MD: renewal_cycle_months, ce_hours_total, ce_cycle_months, initial_license_fee_cents, renewal_fee_cents, fingerprint_required. The LSBME renewals page states only that "All LSBME licensees have first time CE requirements and then ongoing annual CE requirements" without publishing an hour count, and lsbme.la.gov/content/continuing-medical-education returns 404. NOT VERIFIED and NOT SEEDED for LA/APRN: every field except the two CDS fields -- the Louisiana State Board of Nursing was not read at all. The word "annual" on the LSBME page is suggestive of a 12-month physician cycle but a suggestion is not a verified value.'),

-- ---- MICHIGAN -------------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP MI/MD/fingerprint_required and MI/APRN/fingerprint_required. Both LARA licensing guides describe a "Criminal Background Check" that the applicant is emailed instructions to complete, and neither guide contains the word "fingerprint" anywhere. Michigan''s criminal background check for health professionals is widely understood to be fingerprint-based under MCL 333.16174(3), but legislature.mi.gov served an incomplete TLS chain to the fetcher on 2026-09-18 and the statute text could not be read. A background check is not automatically a fingerprint requirement, and the difference is a real cost and scheduling obligation for the clinician. NOT SEEDED. Sources consulted: https://www.michigan.gov/lara/-/media/Project/Websites/lara/bpl/Medicine/Licensing-Info-and-Forms/MD-Licensing-Guide-FAQ-12626.pdf and https://www.michigan.gov/lara/-/media/Project/Websites/lara/bpl/Nursing/Licensing-Info-and-Forms/Nursing-Licensing-Guide-FAQ-12626.pdf'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP MI/MD and MI/APRN ce_topic_human_trafficking_hours. Mich Admin Code R 338.2413(1) requires, under MCL 333.16148, that "an individual seeking licensure or who is licensed shall have completed training in identifying victims of human trafficking", and LARA''s nursing guide calls it "a one-time training in identifying victims of human trafficking". NEITHER THE RULE NOR THE GUIDE PUBLISHES AN HOUR COUNT -- the rule specifies content, acceptable providers and modalities, and even permits satisfying it by "Reading an article ... published in a peer-reviewed journal", which has no fixed duration. A real one-time obligation with no magnitude this field_key can hold. NOT SEEDED; an invented number here would be a fabricated duty. OPEN: either obtain an hour count or add a topic-completion (boolean) key so the one-time duty can be tracked without hours. Source: https://ars.apps.lara.state.mi.us/AdminCode/DownloadAdminCodeFile?FileName=R%20338.2401%20to%20R%20338.2443.pdf&ReturnHTML=True'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP MI/APRN/initial_license_fee_cents and MI/APRN/renewal_fee_cents. LARA''s Michigan Nursing Licensing Guide publishes the nurse practitioner credential fee as "RN Specialty Certification: $41.35 or $56.55 (Valid for up to 1 to 2 year(s) from date issued)" -- a PRORATED range whose value depends on how much of the RN cycle remains when the certification is issued, and it publishes no separate NP specialty certification RENEWAL fee at all. The RN licence figures ($212.90 application, $131.00 renewal) are real but they are the RN fee, not the APRN fee, and carrying one across to the other is the kind of inference this asset does not make. NOT SEEDED. Source: https://www.michigan.gov/lara/-/media/Project/Websites/lara/bpl/Nursing/Licensing-Info-and-Forms/Nursing-Licensing-Guide-FAQ-12626.pdf'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP MI/APRN/renewal_window_days, MI/APRN/supervision_required, MI/APRN/collaborative_agreement_required. The nursing licensing guide read on 2026-09-18 states none of these. Michigan''s NP practice-authority regime was NOT researched and must not be inferred from the MD-side pages. NOT SEEDED.'),

-- ---- NORTH CAROLINA -------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP NC/MD/renewal_window_days. The North Carolina Medical Board sends "a renewal notice by email to registered physicians approximately two months before their birthday" but does not publish the date on which the renewal transaction opens, and a notification date is not a window. NOT SEEDED (same treatment as CA/MD in the first four states). Source: https://www.ncmedboard.org/licensing-registration/renewals/physicians'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP NC/MD/initial_license_fee_cents and NC/MD/fingerprint_required. The NC Medical Board renewal and CME pages publish the $250 annual renewal fee but no initial licensure fee, and ncmedboard.org/licensing-registration/apply-for-license/physicians returned no body content to the fetcher on 2026-09-18. No fingerprint statement was located. NOT SEEDED.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP NC/MD/csr_required and NC/APRN/csr_required. No North Carolina Medical Board, Board of Nursing or NC DHHS page was found that affirmatively states either that North Carolina issues a state controlled substance registration or that it does not. 21 NCAC 32M .0107 and the NC Medical Board CME FAQ both impose controlled-substance CME on prescribers, which establishes that prescribing is regulated but says nothing about a registration. A negative cannot be asserted from silence, and this field is one the business bills for. NOT SEEDED. OPEN: read G.S. ch. 90 art. 5 (the North Carolina Controlled Substances Act), in particular G.S. 90-101, for whether a practitioner registration exists. The NC Board of Nursing site (ncbon.com) is behind Cloudflare and refused direct fetches, which limited what could be checked.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP NC/APRN/renewal_window_days and NC/APRN/fingerprint_required. 21 NCAC 32M sets the renewal deadline (last day of the birth month) but not an opening date, and says nothing about fingerprints. NOT SEEDED.'),

-- ---- VIRGINIA -------------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP VA/MD and VA/APRN csr_required. Virginia is widely understood to require no separate state controlled substance registration beyond the federal DEA registration, but no Department of Health Professions or Board of Pharmacy page asserting that was located and read, and a negative cannot be asserted from silence. NOT SEEDED. OPEN: read Code of Virginia sec. 54.1-3423 (registration requirement under the Drug Control Act) directly.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP VA/MD ce_topic_opioid_hours / ce_topic_controlled_substance_hours. 18VAC85-20-235, read in full on 2026-09-18, mandates 30 Type 1 hours and NO topic at all; Code of Virginia sec. 54.1-2912.1, also read in full, delegates continued competency to the Board without naming a topic. Virginia prescriber-education requirements enacted after 2017 were NOT located in either instrument. The absence of a topic in the two governing texts is evidence but not proof that none exists elsewhere. NOT SEEDED. OPEN: search Code of Virginia title 54.1 ch. 34 (Drug Control Act) and Board of Medicine guidance documents. Sources: https://law.lis.virginia.gov/admincode/title18/agency85/chapter20/section235/ and https://law.lis.virginia.gov/vacode/title54.1/chapter29/section54.1-2912.1/'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP VA/MD and VA/APRN renewal_window_days and fingerprint_required. Neither 18VAC85-20 nor 18VAC90-30 states when renewal opens or requires fingerprints; 18VAC90-30-100(B) says only that "The renewal notice of the license shall be sent to the last known address of record". NOT SEEDED. Also GAP VA/APRN/ce_cycle_months: because the Virginia APRN default competency pathway is national certification rather than hours, there is no board-stated CE cycle to record.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP VA/APRN/supervision_required. Code of Virginia sec. 54.1-2957(C) requires "collaboration and consultation" under a practice agreement, not supervision, and sec. 54.1-2957(I) removes even that after three years of full-time clinical experience. Recording supervision_required = true would misstate the Virginia instrument, and recording false would assert a negative the statute does not put in those words for every APRN role (certified registered nurse anesthetists, by contrast, "shall practice under the supervision of a licensed doctor" under the same subsection). NOT SEEDED; collaborative_agreement_required carries the substance. Source: https://law.lis.virginia.gov/vacode/title54.1/chapter29/section54.1-2957/'),

-- ---- SOUTH CAROLINA -------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP SC/MD and SC/APRN csr_fee_cents. South Carolina''s controlled substance registration is verified as required and annual (24A S.C. Regs. 60-4 sec. 106; S.C. Code Ann. sec. 44-53-280(D)), but the regulation''s fee provisions (sec. 104, "Time and Method of Payment of Fees", and sec. 105, "Registrants Exempt from Fee") set out procedure without publishing an amount, and the S.C. Department of Public Health drug control pages (dph.sc.gov/professionals/healthcare-quality/drug-control-register-verify/new-registrations and /drug-control-renewals) render their body content client-side and returned only navigation to the fetcher on 2026-09-18. A fee the licensee pays annually and that the business bills for, with no published figure. NOT SEEDED. OPEN: obtain the Bureau of Drug Control fee schedule directly.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP SC/MD/initial_license_fee_cents, SC/MD/renewal_window_days, SC/MD/fingerprint_required. The Board''s renewal schedule PDF publishes the $155 biennial renewal fee and a "March 31 - June 30" renewal period but no initial licensure fee, and no fingerprint statement was located. The "March 31 - June 30" period is a pair of fixed calendar dates against a fixed June 30 expiry rather than an offset from expiration, which renewal_window_days cannot express without inventing an anchor. NOT SEEDED. Source: https://llr.sc.gov/med/pdf/renewalschedule.pdf'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP SC/APRN/ce_hours_total and SC/APRN/ce_cycle_months. South Carolina does not set a general contact-hour total for APRNs: the Board''s Renewals FAQ says competency for an APRN is "an updated National Certification", with the 20 pharmacotherapeutics hours attaching only to prescriptive-authority holders (seeded as a topic row). The 30-hour figure on the same page is the RN/LPN continued competency option ("the Board of Nursing does not mandate continuing education hours (30 contact hours in the 2-year renewal period). It is your choice as to which of the four continued competency options you choose") and is NOT an APRN requirement. Carrying the RN number onto the APRN row would fabricate an obligation. NOT SEEDED. Source: https://llr.sc.gov/nurse/pdf/Renewal_FAQs.pdf'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP SC/APRN/collaborative_agreement_required and SC/APRN/supervision_required. South Carolina''s instrument is a written practice agreement under S.C. Code Ann. sec. 40-33-34, which was NOT read on 2026-09-18 (only ch. 40-47, the medical practice act, and ch. 44-53 were retrieved in full). The Board of Nursing APRN pages read did not state it in terms. NOT SEEDED rather than assumed from the fee schedule''s "Application for Prescriptive Authority" line.'),

-- ---- TENNESSEE ------------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP TN/MD and TN/APRN csr_required. Neither the Tennessee Board of Medical Examiners nor the Board of Nursing pages read on 2026-09-18 state whether Tennessee issues a practitioner controlled substance registration separate from the federal DEA registration. Tennessee''s APRN-side instrument is a "Certificate of Fitness" to prescribe issued under Board of Nursing Rule 1000-01-.18, which is a PRESCRIPTIVE AUTHORITY credential rather than a controlled substance registration in the sense this field_key means, and the two should not be conflated. NOT SEEDED for either licence type. OPEN: read Tenn. Code Ann. title 53 ch. 11 part 3 and Tenn. Code Ann. sec. 63-1-301 et seq.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP TN/MD/initial_license_fee_cents, TN/MD/renewal_fee_cents and TN/MD/fingerprint_required. The Board of Medical Examiners landing page states the biennial cycle and the 60-day renewal window but publishes no fee amounts, and it lists "Criminal Background Check Required for New Applications" as a link without stating whether the check is fingerprint-based. The Board of Nursing publishes a fee schedule PDF; the Board of Medical Examiners equivalent was not located. NOT SEEDED. Source: https://www.tn.gov/health/licensure/me.html'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP TN/APRN/ce_hours_total and TN/APRN/ce_cycle_months. Tennessee validates APRN competency by national certification plus one item from the RN proof-of-competence list, not by a contact-hour total: Board of Nursing Rule 1000-04-.05 requires the APRN to have "obtained or maintained ... certification from a nationally recognized certification body" plus "One (1) additional item from the Registered Nurse proof of competence list". The RN list includes "Certificate/evidence of five contact hours of continuing education" as ONE of fifteen alternatives, which is not a CE total. NOT SEEDED. Also GAP TN/APRN/initial_license_fee_cents: the Board''s fee schedule records the APRN initial application fee as "Fee eliminated as of 08/05/2019", which is a zero the Board does assert -- but it is a zero for the APRN certificate only, and the underlying RN endorsement fee of $115 still applies, so seeding 0 would mislead. OPEN: decide how the schema should record an abolished fee. Sources: https://www.tn.gov/content/dam/tn/health/documents/ContinuedCompetenceRequirements.pdf and https://www.tn.gov/content/dam/tn/health/healthprofboards/nursing/Fee%20Schedule.pdf'),

-- ---- ALABAMA --------------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP AL/MD/renewal_window_days and AL/APRN/renewal_window_days. Alabama expresses both windows as a pair of FIXED CALENDAR DATES against a fixed expiry, not as an offset from expiration: the Board of Medical Examiners opens MD/DO renewal "beginning on Oct. 1" against a December 31 expiry, and the Board of Nursing''s period "begins at 8:00 a.m. on September 1st and ends at 4:30 p.m. on December 31st". Converting either to a day count requires choosing an anchor and an inclusive/exclusive convention that neither board publishes, and the arithmetic would silently break in a leap year. renewal_window_days cannot express a fixed-date window. NOT SEEDED. OPEN: the schema needs a renewal_window_opens_on (month-day) key for fixed-date states; AL, MS and SC all have one. Sources: https://www.albme.gov/licensing/md-do/licensing-md-do-license-renewals/ and https://www.abn.alabama.gov/licensing/renewal/'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP AL/MD/initial_license_fee_cents, AL/MD/fingerprint_required, AL/APRN/initial_license_fee_cents, AL/APRN/renewal_fee_cents, AL/APRN/fingerprint_required. The ALBME renewals page publishes the $300 annual MD/DO renewal but no initial licensure fee and no fingerprint statement; the Alabama Board of Nursing renewal page publishes CE requirements and the renewal period but states no fee amount ("Fees are Non-Refundable" is the only fee text on it), and the Advanced Practice FAQs do not state one either. NOT SEEDED.'),

-- ---- MISSISSIPPI ----------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP MS/MD/csr_required. The Mississippi State Board of Medical Licensure lists "Registrations for Licensed Physicians", "Dispensing Registration" and "Pain Practice Registration" in its navigation -- none of which is a general controlled substance registration -- and no MSBML page states whether a Mississippi Bureau of Narcotics registration is required of a prescribing physician. mbn.ms.gov returned a 502 from the egress proxy on 2026-09-18 and could not be read. This is a live asymmetry: the Mississippi Board of NURSING does require a separate state Controlled Substance Prescriptive Authority of APRNs (seeded), so silence on the physician side is conspicuous and must not be read as a no. NOT SEEDED. OPEN: read Miss. Code Ann. sec. 41-29-125 and the Mississippi Bureau of Narcotics registration pages.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP MS/MD/initial_license_fee_cents, MS/MD/renewal_window_days, MS/MD/fingerprint_required, MS/MD ce topic rows. msbml.ms.gov/licensure/licensing-fees rendered as navigation only to the fetcher on 2026-09-18 and no initial fee was obtained. The renewal window is a fixed-date pair ("Begins May 1 and ends June 30 each year") against a fixed expiry, which renewal_window_days cannot express -- see the Alabama fixed-date gap above. On CME topics, the Board states that "The one-time DEA-required 8-hour opioid/substance use disorder training satisfies the Board''s controlled substance training requirement for DEA-registered practitioners", which describes a FEDERAL one-time duty being accepted in satisfaction of a state one, not a Mississippi hour count of its own; seeding it as a Mississippi topic row would misattribute a federal obligation to the state. NOT SEEDED. Source: https://www.msbml.ms.gov/licensure/md-do-permanent-renewal'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP MS/APRN/fingerprint_required and MS/APRN/csr_renewal_cycle_months. The Mississippi Board of Nursing APRN page lists a "Criminal Background Check : $75.00" fee but does not say the check is fingerprint-based, and it does not state whether the Controlled Substance Prescriptive Authority runs on its own clock or lapses with the APRN licence. NOT SEEDED. Also GAP MS/APRN/renewal_window_days: none published.'),

-- ---- KENTUCKY -------------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP KY/MD/fingerprint_required. 201 KAR 9:041, Section 1(16) prices a "Fee for Federal Bureau of Investigation (FBI) Fingerprint Card - eighteen (18) dollars", which shows the Board handles fingerprint cards but is not itself a statement that fingerprints are required of every applicant. Pricing a service is not mandating it. NOT SEEDED. OPEN: read KRS 311.571 for the criminal background check condition. Source: https://apps.legislature.ky.gov/law/kar/titles/201/009/041/'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP KY/MD and KY/APRN csr_required. Kentucky requires prescribers to hold a KASPER (prescription monitoring) account -- 201 KAR 20:215 Section 5(1)(b) turns on whether an APRN "is registered with the DEA and has a PDMP account" -- but a PDMP account is a database registration, NOT a controlled substance registration in the sense this field_key means, exactly as CURES is not in California. No Kentucky Board of Medical Licensure or Board of Nursing page asserting that Kentucky does or does not issue a state controlled substance registration was located. NOT SEEDED. OPEN: read KRS ch. 218A. Separately: the platform still has no pdmp_registration_required key, and Kentucky, like California, has a real recurring PDMP obligation this field_key set cannot express.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP KY/MD/renewal_window_days and KY/APRN/renewal_window_days. 201 KAR 9:051 sets a March 1 registration deadline and says notice is mailed "On or about January 1 of each year", which is a notification date against a fixed deadline, not a transactional window. The Kentucky Board of Nursing earning period (November 1 - October 31) is a CE clock, not a renewal window. NOT SEEDED.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP KY/APRN/collaborative_agreement_required and KY/APRN/supervision_required. Kentucky''s instruments are the CAPA-NS (Collaborative Agreement for the Advanced Practice Registered Nurse''s Prescriptive Authority for Non-Scheduled Legend Drugs) and CAPA-CS (for controlled substances) under KRS 314.042, which impose different and time-limited obligations -- the non-scheduled agreement falls away after a statutory period while the controlled substance agreement does not. Neither instrument was read on a Board of Nursing page on 2026-09-18, and a single boolean cannot express a regime where one agreement expires and the other persists. NOT SEEDED. OPEN: read KRS 314.042 and 201 KAR 20:057.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP KY/MD/ce_topic_head_trauma_hours (pediatric abusive head trauma). The Board''s CME Requirement Schedule 2024-2026 describes a requirement for "pediatricians, radiologists, family practitioners, and emergency medicine ... physicians to complete a onetime one (1) hour of training". It is one-time and limited to named specialties, and "ce_topic_head_trauma_hours" is NOT in the agreed field_key vocabulary, so no key exists to hold it without extending the vocabulary. NOT SEEDED. OPEN: decide whether to add the key. Source: https://kbml.ky.gov/cme/Documents/CME%20Schedule%202024-2026.pdf'),

-- ---- WEST VIRGINIA --------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP WV/MD/initial_license_fee_cents and WV/MD/renewal_fee_cents. The WV Board of Medicine publishes its fees in a graphical annual-report handout (download_resource.aspx?ID=485) whose fee figures did not survive text extraction on 2026-09-18 -- the amounts render as glyph codes rather than digits. The surrounding prose that DID extract is only comparative ("The national average for initial licensing fees is $545 (based on a 2-year cycle)", "Physicians also pay a $125 fee to the Patient Injury Compensation Fund"), and the national average is not West Virginia''s fee. NOT SEEDED. OPEN: retrieve the fee schedule from the Board directly.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'GAP WV/MD/csr_required, WV/MD/renewal_window_days, WV/MD/fingerprint_required. West Virginia''s controlled substance credential for practitioners is administered by the WV Board of Pharmacy under W. Va. Code ch. 60A; code.wvlegislature.gov served only chapter navigation to the fetcher for sec. 60A-3-301 on 2026-09-18 and the Board of Pharmacy controlled substances FAQ rendered as navigation only. The WV Board of Medicine site separately advertises a "Controlled Substance Dispensing Registration", which is a DISPENSING registration and is not the same thing as a prescriber registration -- conflating the two would be a material error. NOT SEEDED. OPEN: read W. Va. Code sec. 60A-3-301 and 302 and the Board of Pharmacy practitioner CS licence pages.'),

-- ---- CROSS-CUTTING --------------------------------------------------------
(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'SCOPE GAP: license_type ''DO'' is NOT COVERED in any group B state. In NC, VA, SC, TN, AL, MS, KY and WV the medical board that licenses MDs also licenses DOs and in several cases the seeded page names both (the NC renewal fee page says "medical doctors (MDs) and doctors of osteopathic medicine (DOs)", the SC CE sheet is headed MD/DO, the MS renewal page says "Permanent MD and DO licenses", the WV CME sheet says "MDs and DPMs"), so the MD rows are LIKELY to hold for DOs there -- but "likely" is not verified and no DO-specific page was read. In MICHIGAN THE BOARD OF OSTEOPATHIC MEDICINE AND SURGERY IS A SEPARATE BOARD with its own rules (Mich Admin Code R 338.11xx) and its own CE brochure, and the seeded MI/MD rows must NOT be applied to a Michigan DO. Any consumer that resolves a DO to the MD rows is producing an unverified obligation.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'SCHEMA GAP: SEVERAL GROUP B STATES RUN THE CE CLOCK AND THE RENEWAL CLOCK AT DIFFERENT SPEEDS, and ce_cycle_months alone does not warn a consumer of that. North Carolina renews an MD licence every 12 months against a 36-month CME cycle; Kentucky registers annually against a 36-month CME cycle; Mississippi renews annually against a 24-month CME cycle; Alabama registers annually but its controlled substance CME runs every 24 months. An obligation generator that assumes CE is due at each renewal will demand 60 hours a year from a North Carolina physician who owes 60 hours in three, and one that assumes CE is due only at the end of the CE cycle will miss the annual attestation those states require at every renewal. Both failure modes are live. Resolving this means the consumer must read renewal_cycle_months and ce_cycle_months as independent clocks, and it may mean a schema change to carry the attestation duty separately from the earning duty.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'SCHEMA GAP: csr_renewal_cycle_months IS NOT THE LICENCE CYCLE, and in group B it frequently differs. Alabama: the ACSC and QACSC renew annually (Dec 31 and Jan 1 respectively) while the CRNP licence renews every 24 months. South Carolina: the state controlled substance registration expires April 1 every year while the MD licence renews biennially on June 30 and the APRN licence on April 30. Michigan is the exception -- its controlled substance licence "runs concurrently with your professional license". A consumer that renews the CSR with the licence will let an Alabama or South Carolina registration lapse, which stops the clinician prescribing. These are seeded as separate field_keys precisely so that cannot happen silently.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'SCHEMA GAP: the vocabulary has no key for a MANDATED TOPIC WITH NO HOUR COUNT, and group B produced at least three real ones -- Michigan''s one-time human trafficking identification training (R 338.2413, content and providers specified, no duration), Kentucky''s one-time pediatric abusive head trauma hour for named specialties (which has an hour but no key), and Alabama''s named "Navigating Professional Boundaries in Medicine" course (which has hours and was mapped onto ce_topic_ethics_hours for want of a better key). Each is a real obligation the asset currently either drops or files under an approximate name. Fixing this means a schema change: a topic-completion boolean or a named-course key, not a data change.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'SCHEMA GAP: renewal_window_days CANNOT EXPRESS A FIXED-DATE RENEWAL WINDOW, and four of the twelve group B states use one. Alabama (MD opens Oct 1, expires Dec 31; nursing opens Sep 1, expires Dec 31), Mississippi (MD opens May 1, expires Jun 30), South Carolina (MD March 31 - June 30) and Kentucky (notice Jan 1, deadline Mar 1) all publish calendar dates rather than an offset from expiration. Only Michigan (90 days), Tennessee (60 days) and Louisiana (56 days) publish a true offset, and those three are seeded. Converting a fixed date to a day count would invent an anchor and a leap-year convention the boards do not publish. OPEN: add a renewal_window_opens_on month-day key.'),

(null, null, null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-b', 1, 'unresolved',
 'SCHEMA GAP: value_json IS CARRYING NON-CE SHAPES IN THIS FILE, and a consumer must not assume every value_json is {"hours": n, "periodicity": ...}. SC/APRN/renewal_fee_cents is {"cents": ..., "with_prescriptive_authority_cents": ...} because South Carolina charges two different APRN renewal amounts; VA/APRN/collaborative_agreement_required carries an experience threshold; TN/APRN/collaborative_agreement_required carries a scope qualifier; MI implicit bias carries a RATE ("hours_per_year_of_license_cycle") rather than a total. Several CE topic rows also carry "additive": false and "subset_of_field_key" to say the topic hours are carved OUT OF ce_hours_total rather than added to it -- MI/MD controlled substance (inside pain management), NC/MD and NC/APRN controlled substance, SC/APRN controlled substance (inside pharmacotherapeutics), TN/MD controlled substance. A consumer that sums topic hours onto the total will over-bill every one of those states. ANY CONSUMER THAT READS value_num AND IGNORES value_json WILL SILENTLY DROP THESE ROWS ENTIRELY.');

commit;
