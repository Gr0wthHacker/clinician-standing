-- =============================================================================
-- requirements_seed_group_c.sql -- the rules asset, GROUP C states.
--
-- IL, OH, IN, WI, MN, IA, MO, KS, NE, ND, SD, MT x { physician (MD),
-- nurse practitioner (APRN) }.
--
-- VERIFICATION STANDARD (read db/seeds/README.md before editing):
--   Every row below carries a citation to a state board page, a state statute,
--   or a board rule that was FETCHED AND READ on 2026-09-18. No row is written
--   from recall, from a CE aggregator, or from inference. Where a value could
--   not be verified from a primary source it is NOT in this file -- it is in
--   requirement_conflicts_seed_group_c.sql as an open conflict. An open conflict
--   blocks auto-clear (PRD 8.1 condition 6) and raises RULE_UNCERTAIN
--   (PRD 8.3), which is the correct behaviour for a value we do not know.
--
--   NOTHING WAS CARRIED ACROSS FROM A NEIGHBOURING STATE. This group contains
--   both full-practice-authority and collaborative-agreement NP regimes and the
--   two are one rule apart on the map; every NP authority row below is from
--   that state's own board or statute.
--
-- VALUE COLUMN CONVENTION
--   value_num   a plain per-cycle quantity (months, days, hours, cents).
--   value_bool  a plain yes/no.
--   value_json  a quantity that is NOT simply "this much, every cycle" --
--               one-time requirements, requirements on a different clock than
--               the renewal cycle, and requirements that apply only to a subset
--               of licensees. Recording a one-time or conditional requirement
--               as a per-cycle number would generate a wrong obligation every
--               cycle, so those carry {"hours": n, "periodicity": ...} instead.
--               Consumers MUST branch on the presence of value_json.
--
--   TIERED NP AUTHORITY IS value_json, NOT A BOOLEAN. Five states in this group
--   (MN, NE, SD, and -- pending -- WI) grant independent practice only after a
--   transition-to-practice hour threshold. The threshold is carried in
--   value_json; a bare boolean would be wrong for whichever side of the
--   threshold a given clinician is on.
--
--   supervision_required and collaborative_agreement_required ARE NOT THE SAME
--   FIELD and are not collapsed. A collaborative / standard care / written
--   practice agreement is a documented relationship between two independent
--   licensees; supervision is a delegation of authority. Where a board's own
--   language names one of them, only that key is written.
--
--   license_type 'MD' and 'APRN' match the vocabulary in 0003_credentials.sql.
--   DO IS NOT COVERED -- see README and the conflicts file.
--
-- Fees are in cents and are the amount the licensee actually pays where the
-- board publishes a single total; component breakdowns are in the citation.
-- A statutory fee CAP is not what the licensee pays and is not seeded as a fee.
--
-- Idempotent: safe to re-run. Respects ux_requirements_current (one is_current
-- row per state/license_type/field_key). Owns only the 12 Group C states, so it
-- coexists with requirements_seed.sql and with other agents' state groups.
-- =============================================================================

begin;

-- Re-running replaces only the rows this file owns. requirement_conflicts rows
-- written by requirement_conflicts_seed_group_c.sql point at these rows, so they
-- are cleared first; re-run that file AFTER this one.
delete from requirement_conflicts
 where observed_by = 'research-agent-group-c'
   and requirement_id in (
         select id from requirements
          where verified_by = 'research-agent-group-c'
            and state in ('IL','OH','IN','WI','MN','IA','MO','KS','NE','ND','SD','MT')
            and license_type in ('MD','APRN'));

delete from requirements
 where verified_by = 'research-agent-group-c'
   and state in ('IL','OH','IN','WI','MN','IA','MO','KS','NE','ND','SD','MT')
   and license_type in ('MD','APRN');

insert into requirements
  (state, license_type, field_key,
   value_text, value_num, value_bool, value_json,
   citation, citation_url, effective_date,
   verified_at, verified_by, version, is_current)
values

-- =============================================================================
-- ILLINOIS -- physician and surgeon (MD)
-- IDFPR Division of Professional Regulation. 225 ILCS 60 (Medical Practice Act
-- of 1987); 68 Ill. Adm. Code 1285.
-- =============================================================================
('IL','MD','renewal_cycle_months', null, 36, null, null,
 'IDFPR, Physician Licensing Frequently Asked Questions: "Physician licenses expire every third year", citing Section 1285.120 of the Board rules. Illinois is one of the few triennial physician states; recording 24 here would understate the cycle by a third.',
 'https://idfpr.illinois.gov/content/dam/soi/en/web/idfpr/faq/dpr/physican-faq.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IL','MD','ce_hours_total', null, 150, null, null,
 'IDFPR Physician and Surgeon instruction sheet (packet updated 2/7/25): "150 hours of CME. All CME hours must have been completed within 3 years prior to the signature date", of which a minimum of 60 hours must be formal programs and a maximum of 90 hours informal. SUBJECT TO AN OPEN CONFLICT: this figure is published in the Department''s reinstatement instruction sheet, not on a renewal CE page; see requirement_conflicts.',
 'https://idfpr.illinois.gov/content/dam/soi/en/web/idfpr/renewals/apply/forms/f2409.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IL','MD','ce_cycle_months', null, 36, null, null,
 'IDFPR Physician and Surgeon instruction sheet: the 150 hours "must have been completed within 3 years prior to the signature date", i.e. the CE cycle matches the triennial renewal cycle stated in Section 1285.120.',
 'https://idfpr.illinois.gov/content/dam/soi/en/web/idfpr/renewals/apply/forms/f2409.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IL','MD','ce_topic_implicit_bias_hours', null, 1, null, null,
 'IDFPR Physician and Surgeon instruction sheet: within the formal CME requirement a physician must include "one (1) hour in the topic of implicit bias awareness training". IDFPR Continuing Education: "one-hour course in implicit bias awareness training per renewal period". Per renewal period, so a plain per-cycle number.',
 'https://idfpr.illinois.gov/content/dam/soi/en/web/idfpr/renewals/apply/forms/f2409.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IL','MD','ce_topic_opioid_hours', null, null, null,
 '{"hours": 3, "periodicity": "per_renewal_cycle", "applies_to": "physicians who hold an Illinois controlled substances registration", "topic": "safe opioid prescribing practices", "first_renewal_exemption": false}'::jsonb,
 'IDFPR Physician and Surgeon instruction sheet: holders of a controlled substances registration must complete "three (3) CME hours in the topic of safe opioid prescribing practices", and unlike the general CME requirement this one carries no first-renewal exemption. Conditional on holding the Illinois controlled substances registration, hence value_json.',
 'https://idfpr.illinois.gov/content/dam/soi/en/web/idfpr/renewals/apply/forms/f2409.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IL','MD','initial_license_fee_cents', null, 50000, null, null,
 'IDFPR, Physician Licensing Frequently Asked Questions: a "$500" non-refundable application fee is required at submission.',
 'https://idfpr.illinois.gov/content/dam/soi/en/web/idfpr/faq/dpr/physican-faq.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

-- =============================================================================
-- ILLINOIS -- advanced practice registered nurse (APRN)
-- IDFPR Division of Professional Regulation. 225 ILCS 65 (Nurse Practice Act);
-- 68 Ill. Adm. Code 1300.
-- =============================================================================
('IL','APRN','renewal_cycle_months', null, 24, null, null,
 'IDFPR, Illinois APRN and FPA-APRN Continuing Education FAQs: continuing education is required "per 2-year license renewal cycle". NOTE the asymmetry with Illinois physicians, who are on a THREE-year cycle -- the two professions do not share a clock in this state.',
 'https://idfpr.illinois.gov/content/dam/soi/en/web/idfpr/faq/dpr/aprn-ce-faqs.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IL','APRN','ce_hours_total', null, 80, null, null,
 'IDFPR, Illinois APRN and FPA-APRN Continuing Education FAQs: "80 hours of approved continuing education in the advanced practice registered nurse''s specialty per 2-year license renewal cycle".',
 'https://idfpr.illinois.gov/content/dam/soi/en/web/idfpr/faq/dpr/aprn-ce-faqs.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IL','APRN','ce_cycle_months', null, 24, null, null,
 'IDFPR, Illinois APRN and FPA-APRN Continuing Education FAQs: the 80 hours run "per 2-year license renewal cycle", i.e. the CE cycle is the renewal cycle.',
 'https://idfpr.illinois.gov/content/dam/soi/en/web/idfpr/faq/dpr/aprn-ce-faqs.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IL','APRN','ce_topic_pharmacotherapeutics_hours', null, 20, null, null,
 'IDFPR, Illinois APRN and FPA-APRN Continuing Education FAQs: "A minimum of 50 hours of the continuing education shall be obtained in continuing education programs that shall include no less than 20 hours of pharmacotherapeutics". The 20 hours are a subset of the 80-hour total, not additional to it.',
 'https://idfpr.illinois.gov/content/dam/soi/en/web/idfpr/faq/dpr/aprn-ce-faqs.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IL','APRN','ce_topic_opioid_hours', null, null, null,
 '{"hours": 10, "periodicity": "per_renewal_cycle", "within": "the 20 pharmacotherapeutics hours", "additional_requirement": {"hours": 3, "topic": "safe opioid prescribing practices", "applies_to": "APRNs who hold an Illinois controlled substances registration"}}'::jsonb,
 'IDFPR, Illinois APRN and FPA-APRN Continuing Education FAQs: "10 hours of opioid prescribing or substance abuse education" forming part of the 20 pharmacotherapeutics hours; SEPARATELY, prescribers with Controlled Substances Registrations must complete "3 hours of continuing education (CE) on safe opioid prescribing practices". Two distinct duties with different populations, so both are carried in value_json rather than summed into one number.',
 'https://idfpr.illinois.gov/content/dam/soi/en/web/idfpr/faq/dpr/aprn-ce-faqs.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IL','APRN','ce_topic_implicit_bias_hours', null, 1, null, null,
 'IDFPR, Illinois APRN and FPA-APRN Continuing Education FAQs: "1 of the 80 hours of CE required for APRN and FPA-APRN license renewal must be an implicit bias awareness training course", applying to all APRNs and FPA-APRNs.',
 'https://idfpr.illinois.gov/content/dam/soi/en/web/idfpr/faq/dpr/aprn-ce-faqs.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

-- =============================================================================
-- OHIO -- doctor of medicine (MD)
-- State Medical Board of Ohio. ORC ch. 4731; OAC ch. 4731-10.
-- =============================================================================
('OH','MD','renewal_cycle_months', null, 24, null, null,
 'Ohio Revised Code sec. 4731.281: "A license shall expire on the date that is two years from the date of issuance and may be renewed for additional two-year periods."',
 'https://codes.ohio.gov/ohio-revised-code/section-4731.281',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('OH','MD','ce_hours_total', null, 50, null, null,
 'Ohio Administrative Code rule 4731-10-02: "During a registration period, a licensee shall be required to complete fifty hours of CME."',
 'https://codes.ohio.gov/ohio-administrative-code/rule-4731-10-02',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('OH','MD','ce_cycle_months', null, 24, null, null,
 'State Medical Board of Ohio, Physicians (MD, DO, DPM): "Licensees are required to complete 50 hours of CME every two-year registration period." Confirms OAC 4731-10-02''s "registration period" is the two-year period of ORC 4731.281.',
 'https://med.ohio.gov/apply-and-renew/licenses-and-certifications/01-physician-(md,-do,-dpm)',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('OH','MD','ce_topic_ethics_hours', null, 1, null, null,
 'Ohio Administrative Code rule 4731-10-02: "A licensee must complete a minimum of one hour of CME, approved by the board, on the topic of a licensee''s duty to report misconduct under section 4731.224 of the Revised Code." SCOPE NOTE: the board''s own topic label is "duty to report misconduct", which is mapped here onto the professional-responsibility sense of ce_topic_ethics_hours because the field_key vocabulary has no duty-to-report slot; see requirement_conflicts.',
 'https://codes.ohio.gov/ohio-administrative-code/rule-4731-10-02',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('OH','MD','initial_license_fee_cents', null, 30500, null, null,
 'State Medical Board of Ohio, Physicians (MD, DO, DPM): "Application $305.00", plus a "$3.50" eLicense transaction fee charged by the portal rather than the Board.',
 'https://med.ohio.gov/apply-and-renew/licenses-and-certifications/01-physician-(md,-do,-dpm)',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('OH','MD','renewal_fee_cents', null, 30500, null, null,
 'State Medical Board of Ohio, Physicians (MD, DO, DPM): "Renewal fee $305.00", plus a "$3.50" eLicense transaction fee. Corroborated by ORC sec. 4731.281, which states a $305 biennial renewal fee.',
 'https://med.ohio.gov/apply-and-renew/licenses-and-certifications/01-physician-(md,-do,-dpm)',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('OH','MD','fingerprint_required', null, null, true, null,
 'State Medical Board of Ohio, Physicians (MD, DO, DPM): "All applicants for licensure are required to complete an FBI and Ohio BCI criminal records check"; "the Board requires submission of fingerprints for a criminal records check completed by both the Ohio Bureau of Criminal Investigation (BCI) and the Federal Bureau of Investigation (FBI)." Verified at INITIAL LICENSURE; the Board does not publish a fingerprint condition on renewal on this page.',
 'https://med.ohio.gov/apply-and-renew/licenses-and-certifications/01-physician-(md,-do,-dpm)',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

-- =============================================================================
-- OHIO -- advanced practice registered nurse (APRN)
-- Ohio Board of Nursing. ORC ch. 4723; OAC ch. 4723-14.
-- =============================================================================
('OH','APRN','renewal_cycle_months', null, 24, null, null,
 'Ohio Revised Code sec. 4723.24: "An active license to practice nursing as a registered nurse is subject to renewal in odd-numbered years", and the continuing education provision speaks of "a license that was issued for a two-year renewal period". APRN licences renew on the RN odd-year clock.',
 'https://codes.ohio.gov/ohio-revised-code/section-4723.24',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('OH','APRN','ce_hours_total', null, 24, null, null,
 'Ohio Revised Code sec. 4723.24: "For renewal of a license that was issued for a two-year renewal period, twenty-four hours of continuing nursing education." Corroborated by OAC 4723-14-03, which requires "twenty-four contact hours of continuing education during the reporting period".',
 'https://codes.ohio.gov/ohio-revised-code/section-4723.24',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('OH','APRN','ce_cycle_months', null, 24, null, null,
 'Ohio Revised Code sec. 4723.24: the twenty-four hours attach to "a license that was issued for a two-year renewal period", i.e. the CE cycle is the renewal cycle.',
 'https://codes.ohio.gov/ohio-revised-code/section-4723.24',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('OH','APRN','ce_topic_laws_and_rules_hours', null, 1, null, null,
 'Ohio Revised Code sec. 4723.24: "at least one hour of the education must be directly related to the statutes and rules pertaining to the practice of nursing in this state". Corroborated by OAC 4723-14-03 ("at least one of the required hours needs to be in category A").',
 'https://codes.ohio.gov/ohio-revised-code/section-4723.24',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('OH','APRN','ce_topic_pharmacotherapeutics_hours', null, null, null,
 '{"hours": 12, "periodicity": "per_renewal_cycle", "applies_to": "APRN designated as a clinical nurse specialist, certified nurse-midwife, or certified nurse practitioner", "source_must_be": "an accredited institution", "within": "the 24-hour total"}'::jsonb,
 'Ohio Revised Code sec. 4723.24: "At least twelve hours of the education must be in advanced pharmacology and be received from an accredited institution", applying to "an advanced practice registered nurse who is designated as a clinical nurse specialist, certified nurse-midwife, or certified nurse practitioner". CRNAs are APRNs in Ohio and are NOT named, so this is a subset of the licence type -- hence value_json.',
 'https://codes.ohio.gov/ohio-revised-code/section-4723.24',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('OH','APRN','collaborative_agreement_required', null, null, true, null,
 'Ohio Revised Code sec. 4723.431: "An advanced practice registered nurse who is designated as a clinical nurse specialist, certified nurse-midwife, or certified nurse practitioner may practice only in accordance with a standard care arrangement entered into with each physician or podiatrist with whom the nurse collaborates." The arrangement must be in writing and a copy retained on file by the employer; the Board does not pre-approve it. This is a COLLABORATION instrument, not supervision -- supervision_required is deliberately not written for Ohio. SUBJECT TO AN OPEN CONFLICT as to CRNAs, who are not named in sec. 4723.431.',
 'https://codes.ohio.gov/ohio-revised-code/section-4723.431',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

-- =============================================================================
-- INDIANA -- physician (MD)
-- Indiana Professional Licensing Agency / Medical Licensing Board. IC 25-22.5.
-- =============================================================================
('IN','MD','renewal_cycle_months', null, 24, null, null,
 'Indiana PLA, Physicians Licensing Information: "Upon issuance of your license, your license will remain valid through October 31 of each odd year." Corroborated by the PLA Top Ten FAQs for Physician License Renewals: "All Physician [Medical Doctor (MD) and Doctor of Osteopathic Medicine (DO)] licenses in the state of Indiana are set to expire at 11:59 p.m. Eastern Daylight Time (EDT) on October 31st." Odd-year expiry on a fixed date is a two-year cycle.',
 'https://www.in.gov/pla/professions/physicians-home/physicians-licensing-information/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IN','MD','initial_license_fee_cents', null, 25000, null, null,
 'Indiana PLA, Physicians Licensing Information: "$250.00" is required for an initial application.',
 'https://www.in.gov/pla/professions/physicians-home/physicians-licensing-information/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IN','MD','renewal_fee_cents', null, 20000, null, null,
 'Indiana PLA, Physicians Licensing Information: the active renewal fee prior to October 31 of odd-numbered years is $200.00. Corroborated by the PLA MD/DO Active Renewal Form, which states "$200.00" as the active renewal fee. A $50 penalty applies to late renewal and $100 renews to inactive status.',
 'https://www.in.gov/pla/professions/physicians-home/physicians-licensing-information/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IN','MD','csr_required', null, null, true, null,
 'Indiana PLA, Controlled Substances Registration: "The practitioner must hold an Indiana CSR and a federal Drug Enforcement Agency (''DEA'') registration ... in order to prescribe, administer, or dispense controlled substances in the State of Indiana." Corroborated by the PLA Top Ten FAQs for Physician License Renewals: "You must renew your physician license and your Controlled Substance Registration (CSR) separately." Indiana is one of the states in this group with a live state CSR.',
 'https://www.in.gov/pla/professions/controlled-substance-registration',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IN','MD','csr_fee_cents', null, 6000, null, null,
 'Indiana PLA, Controlled Substances Registration: "Application fee: $60.00 by credit or debit card. Additional online processing fees apply." The same $60.00 figure is published for renewal.',
 'https://www.in.gov/pla/professions/controlled-substance-registration',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

-- =============================================================================
-- INDIANA -- advanced practice nurse (APRN)
-- Indiana State Board of Nursing. IC 25-23; 848 IAC 5.
-- =============================================================================
('IN','APRN','ce_hours_total', null, 30, null, null,
 'Indiana PLA, Nursing Licensing Information: advanced practice nurses must obtain "at least thirty (30) hours of continuing education, at least eight (8) hours of which must be in pharmacology", "approved by a nationally approved sponsor of continuing education for advanced practice nurses". SUBJECT TO AN OPEN CONFLICT: the page presents this in the context of prescriptive authority and the underlying rule (848 IAC 5) could not be read -- see requirement_conflicts.',
 'https://www.in.gov/pla/professions/nursing-home/nursing-licensing-information',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IN','APRN','ce_topic_pharmacotherapeutics_hours', null, 8, null, null,
 'Indiana PLA, Nursing Licensing Information: of the thirty hours of continuing education, "at least eight (8) hours of which must be in pharmacology". A subset of the 30-hour total, not additional to it.',
 'https://www.in.gov/pla/professions/nursing-home/nursing-licensing-information',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IN','APRN','collaborative_agreement_required', null, null, true, null,
 'Indiana PLA, Nursing Licensing Information: prescriptive authority requires "a written practice agreement" with a licensed practitioner specifying the manner of collaboration, geographic proximity arrangements, the practitioner''s review of prescribing practices including "at least a five percent (5%) random sampling of the charts", and backup coverage. Corroborated by the PLA Collaborative Practice Agreement Checklist, which requires the "Manner of Collaboration between the APN and the LP", provisions for "coverage during absence, incapacity, infirmity, or emergency", documentation of prescribing practices "within seven (7) days", and "Signatures of the APN and the LP with the signing dates". INDIANA IS NOT A FULL-PRACTICE-AUTHORITY STATE for prescribing.',
 'https://www.in.gov/pla/professions/nursing-home/nursing-licensing-information',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IN','APRN','csr_required', null, null, true, null,
 'Indiana PLA, Controlled Substances Registration: "The practitioner must hold an Indiana CSR and a federal Drug Enforcement Agency (''DEA'') registration ... in order to prescribe, administer, or dispense controlled substances in the State of Indiana." The page is practitioner-general and is not limited to physicians.',
 'https://www.in.gov/pla/professions/controlled-substance-registration',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IN','APRN','csr_fee_cents', null, 6000, null, null,
 'Indiana PLA, Controlled Substances Registration: "Application fee: $60.00 by credit or debit card." The same figure is published for renewal. Practitioner-general.',
 'https://www.in.gov/pla/professions/controlled-substance-registration',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

-- =============================================================================
-- WISCONSIN -- physician (medicine and surgery, MD)
-- DSPS / Medical Examining Board. Wis. Stat. ch. 448; Wis. Admin. Code ch. Med 13.
-- =============================================================================
('WI','MD','renewal_cycle_months', null, 24, null, null,
 'Wisconsin DSPS, Renewal Dates and Fees: the Medicine and Surgery (MD) credential carries a renewal date of "10/31/odd year", i.e. a two-year credential renewed every odd-numbered year. Corroborated by DSPS Medicine and Surgery Application Information #570, which speaks of "CE completed in the previous biennium".',
 'https://dsps.wi.gov/Credentialing/Renewal/RenewalDatesFees.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('WI','MD','renewal_fee_cents', null, 12000, null, null,
 'Wisconsin DSPS, Renewal Dates and Fees: Medicine and Surgery (MD), renewal date "10/31/odd year", renewal fee "$120".',
 'https://dsps.wi.gov/Credentialing/Renewal/RenewalDatesFees.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('WI','MD','ce_hours_total', null, 30, null, null,
 'Wisconsin DSPS, Physician Continuing Education: "30 hours of Category 1 AMA or AOA is required." Wisconsin is the lowest physician CE total in this group; the neighbouring states'' 40-50 hour figures do NOT apply here.',
 'https://dsps.wi.gov/Pages/Professions/Physician/CE.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('WI','MD','ce_cycle_months', null, 24, null, null,
 'Wisconsin DSPS, Medicine and Surgery Application Information #570: "Proof of 30 hours of CE completed in the previous biennium". The CE clock is the biennial credential period that the Renewal Dates and Fees schedule fixes at 10/31 of each odd year.',
 'https://dsps.wi.gov/Credentialing/Health/info570.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('WI','MD','ce_topic_opioid_hours', null, null, null,
 '{"hours": 2, "periodicity": "per_renewal_cycle", "within": "the 30-hour total", "board_statement_scoped_to": "the 2025 renewal", "topic": "prescribing opioids and other controlled substances"}'::jsonb,
 'Wisconsin DSPS, Physician Continuing Education: "For the 2025 renewal, each license holder will be required to take two of the required 30 hours related to prescribing opioids and other controlled substances." The Department states the duty for a NAMED renewal rather than as a standing requirement, so it is carried as value_json with that scope recorded rather than as a bare recurring 2; see requirement_conflicts.',
 'https://dsps.wi.gov/Pages/Professions/Physician/CE.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

-- =============================================================================
-- WISCONSIN -- advanced practice registered nurse (APRN)
-- DSPS / Board of Nursing. Wis. Admin. Code ch. N 8.
-- =============================================================================
('WI','APRN','renewal_cycle_months', null, 24, null, null,
 'Wisconsin DSPS, Renewal Dates and Fees: Advanced Practice Registered Nurse (Advanced Practice Prescriber) carries a renewal date of "09/30/even year", i.e. a two-year credential renewed every even-numbered year. NOTE this is a DIFFERENT clock from the Wisconsin physician credential (10/31 odd year) and from the Wisconsin RN credential (02/28 even year).',
 'https://dsps.wi.gov/Credentialing/Renewal/RenewalDatesFees.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('WI','APRN','renewal_fee_cents', null, 7300, null, null,
 'Wisconsin DSPS, Renewal Dates and Fees: Advanced Practice Registered Nurse (Advanced Practice Prescriber), renewal date "09/30/even year", renewal fee "$73".',
 'https://dsps.wi.gov/Credentialing/Renewal/RenewalDatesFees.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('WI','APRN','ce_topic_pharmacotherapeutics_hours', null, 16, null, null,
 'Wisconsin Administrative Code sec. N 8.05(1): "Every advanced practice nurse prescriber shall complete 16 contact hours per biennium in clinical pharmacology or therapeutics relevant to the advanced practice nurse prescriber''s area of practice".',
 'https://docs.legis.wisconsin.gov/code/admin_code/n/8.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('WI','APRN','ce_topic_controlled_substance_hours', null, 2, null, null,
 'Wisconsin Administrative Code sec. N 8.05(1): the 16 contact hours must include "at least 2 contact hours in responsible prescribing of controlled substances". A subset of the 16, not additional to them.',
 'https://docs.legis.wisconsin.gov/code/admin_code/n/8.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('WI','APRN','ce_cycle_months', null, 24, null, null,
 'Wisconsin Administrative Code sec. N 8.05(1): the pharmacology hours are required "per biennium", matching the 09/30-even-year biennial credential in the DSPS Renewal Dates and Fees schedule.',
 'https://docs.legis.wisconsin.gov/code/admin_code/n/8.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('WI','APRN','collaborative_agreement_required', null, null, true, null,
 'Wisconsin Administrative Code sec. N 8.10(7): "Advanced practice nurse prescribers shall work in a collaborative relationship with a physician or dentist. The collaborative relationship is a process in which an advanced practice nurse prescriber is working with a physician or dentist, in each other''s presence when necessary, to deliver health care services within the scope of the practitioner''s training, education, and experience." This is COLLABORATION, not supervision. SUBJECT TO AN OPEN CONFLICT: DSPS''s current APRN page describes a newer APRN credential under which applicants "demonstrate independent practice eligibility through supervised hours", which ch. N 8 does not reflect -- see requirement_conflicts.',
 'https://docs.legis.wisconsin.gov/code/admin_code/n/8.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

-- =============================================================================
-- MINNESOTA -- physician (MD)
-- Minnesota Board of Medical Practice. Minn. Stat. ch. 147; Minn. R. 5605.
-- Minnesota is an ANNUAL renewal state with a THREE-YEAR CME clock. The two
-- numbers below are deliberately different and must not be reconciled.
-- =============================================================================
('MN','MD','renewal_cycle_months', null, 12, null, null,
 'Minnesota Board of Medical Practice, Renew Your License: the Board will "send you an email notice to remind you to complete the annual renewal before your license expiration". Minnesota physicians renew EVERY YEAR; the three-year figure on the Board''s CME page is the CME clock, not the licence clock.',
 'https://mn.gov/boards/medical-practice/renew/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('MN','MD','ce_hours_total', null, 75, null, null,
 'Minnesota Board of Medical Practice, Continuing Education: "Each licensed physician must obtain 75 hours of continuing medical education (CME) category 1 credit every three years as a condition of licensure renewal." Physicians in full-time residency or fellowship and Emeritus registrants are exempt.',
 'https://mn.gov/boards/medical-practice/licensing/continuing-ed/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('MN','MD','ce_cycle_months', null, 36, null, null,
 'Minnesota Board of Medical Practice, Continuing Education: the 75 hours run "every three years", with a newly licensed physician''s cycle commencing "on their birth month following the initial date of licensure". THE CE CYCLE IS THREE TIMES THE RENEWAL CYCLE. A consumer that anchors CME to the annual renewal will over-bill Minnesota physicians threefold.',
 'https://mn.gov/boards/medical-practice/licensing/continuing-ed/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

-- =============================================================================
-- MINNESOTA -- advanced practice registered nurse (APRN)
-- Minnesota Board of Nursing. Minn. Stat. sec. 148.171, 148.211.
-- =============================================================================
('MN','APRN','renewal_cycle_months', null, 24, null, null,
 'Minnesota Board of Nursing, APRN Renewal: "Your RN and APRN registrations expire on the last day of your birth month and in an odd or even year depending on your birth year." An odd/even-year birth-month expiry is a two-year registration. NOTE the asymmetry with Minnesota physicians, who renew ANNUALLY.',
 'https://mn.gov/boards/nursing/advanced-practice/apply-for-an-aprn-license-renewal-reregistration-reauthorization-and-forms/renewal/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('MN','APRN','renewal_fee_cents', null, 8500, null, null,
 'Minnesota Board of Nursing, APRN Renewal: "the APRN renewal fee of $85". The underlying RN registration renewal is a separate fee.',
 'https://mn.gov/boards/nursing/advanced-practice/apply-for-an-aprn-license-renewal-reregistration-reauthorization-and-forms/renewal/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('MN','APRN','collaborative_agreement_required', null, null, null,
 '{"required": true, "until_practice_hours": 2080, "applies_to": ["certified nurse practitioner","clinical nurse specialist"], "not_required_for": ["certified nurse-midwife","certified registered nurse anesthetist"], "cohort": "those who began practice after 2014-07-01", "after_threshold": "no collaborative agreement required", "exception": "a CRNA providing nonsurgical therapies for acute or chronic pain must have a written prescribing agreement with a Minnesota licensed physician", "collaborator_may_be": ["physician","APRN licensed in Minnesota with at least three years of APRN practice"]}'::jsonb,
 'Minnesota Board of Nursing, APRN Licensure General Information: a CNP or CNS who began practice after July 1, 2014 must practise "for at least 2,080 hours, within the context of a collaborative agreement" after licensure; a collaborative agreement is "a mutually agreed upon plan for the overall working relationship" with a physician or with an APRN of at least three years'' practice. CNMs and CRNAs do not require a collaborative management agreement, except a CRNA providing nonsurgical pain therapies, who needs "a written prescribing agreement with a Minnesota licensed physician". MINNESOTA IS A TIERED STATE: the duty ends at an hours threshold and does not apply to two of the four APRN roles, so a bare boolean would be wrong for most of the population -- hence value_json.',
 'https://mn.gov/boards/nursing/advanced-practice/advanced-practice-registered-nurse-(aprn)-licensure-general-information/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

-- =============================================================================
-- IOWA -- physician (MD)
-- Iowa Board of Medicine / DIAL. Iowa Code ch. 147, 148; IAC 481 ch. 652, 654.
-- =============================================================================
('IA','MD','renewal_cycle_months', null, 24, null, null,
 'Iowa DIAL, Continuing Education for Physicians: "Forty hours of Category 1 credits are required for a two-year license renewal period." Corroborated by IAC 481--652.12(147,148), under which a licence "expires on the first day of the licensee''s birth month" at the end of a two-year licence period.',
 'https://dial.iowa.gov/licenses/health-professions/physicians/continuing-education-physicians',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IA','MD','ce_hours_total', null, 40, null, null,
 'Iowa DIAL, Continuing Education for Physicians: "Forty hours of Category 1 credits are required for a two-year license renewal period." Up to 20 carryover hours from the previous cycle may be applied; a SPECIAL licence carries 20 hours with no carryover, which is a different licence class and is not seeded here.',
 'https://dial.iowa.gov/licenses/health-professions/physicians/continuing-education-physicians',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IA','MD','ce_cycle_months', null, 24, null, null,
 'Iowa DIAL, Continuing Education for Physicians: the forty hours attach to "a two-year license renewal period", i.e. the CE cycle is the renewal cycle.',
 'https://dial.iowa.gov/licenses/health-professions/physicians/continuing-education-physicians',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IA','MD','ce_topic_opioid_hours', null, null, null,
 '{"hours": 2, "periodicity": "every_5_years", "applies_to": "physicians who prescribe opioids to patients during the license period", "topic": "CDC guidelines for prescribing opioids for chronic pain", "transition": "licensees holding a permanent or special license as of 2019-01-01 had until 2024-01-01 for the initial training"}'::jsonb,
 'Iowa DIAL, Chronic Pain and End-of-Life Training: "at least two hours of category 1 credits regarding the United States Center for Disease Control and Prevention (CDC) guidelines for prescribing opioids for chronic pain", required once every five years of physicians who prescribe opioids to patients during a licence period. FIVE-YEAR CLOCK ON A TWO-YEAR LICENCE, and conditional on prescribing -- hence value_json.',
 'https://dial.iowa.gov/chronic-pain-and-end-life-training',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IA','MD','ce_topic_pain_management_hours', null, null, null,
 '{"hours": 2, "periodicity": "every_5_years", "topic": "end-of-life care", "applies_to": "physicians in emergency medicine, family medicine, general practice, internal medicine, neurology, pain medicine or psychiatry, and any physician who has provided or expects to provide end-of-life care regardless of specialty, including those reporting as retired or not in clinical practice", "effective_date": "2011-08-17"}'::jsonb,
 'Iowa DIAL, Chronic Pain and End-of-Life Training: "two hours of Category 1 credits for end-of-life care every five years", applying to the named specialties and to any physician who has provided or expects to provide end-of-life care. SPECIALTY-CONDITIONAL AND ON A FIVE-YEAR CLOCK -- hence value_json. This is a SEPARATE duty from the chronic-pain/opioid two hours above; the two do not substitute for each other.',
 'https://dial.iowa.gov/chronic-pain-and-end-life-training',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

-- =============================================================================
-- IOWA -- advanced registered nurse practitioner (APRN)
-- Iowa Board of Nursing / DIAL. Iowa Code ch. 152; IAC 655 ch. 5, 7 (now 481).
-- =============================================================================
('IA','APRN','renewal_cycle_months', null, 36, null, null,
 'Iowa DIAL, Nursing License Renewals: "License renewals are on a three-year renewal cycle"; "Expiration is the 15th day of the licensee''s birth month." IOWA NURSES ARE ON A THREE-YEAR CLOCK while Iowa physicians are on two years -- the two professions do not share a cycle in this state.',
 'https://dial.iowa.gov/licenses/health-professions/nursing-professional-midwifery/nursing-licensure/renewals',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IA','APRN','ce_hours_total', null, 36, null, null,
 'Iowa DIAL, Nursing License Renewals: "The requirement is 36 contact hours of continuing education to renew any license." Corroborated by DIAL, CE Basic Requirements: "Renewal or reactivation of all licenses requires 36 contact hours of continuing education."',
 'https://dial.iowa.gov/licenses/health-professions/nursing-professional-midwifery/nursing-licensure/renewals',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IA','APRN','ce_cycle_months', null, 36, null, null,
 'Iowa DIAL, Nursing License Renewals: the 36 contact hours are the requirement "to renew any license" on a three-year renewal cycle, i.e. the CE cycle is the renewal cycle.',
 'https://dial.iowa.gov/licenses/health-professions/nursing-professional-midwifery/nursing-licensure/renewals',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IA','APRN','renewal_fee_cents', null, 9900, null, null,
 'Iowa DIAL, Nursing License Renewals: the standard renewal fee is $99, with a $50 late fee if renewed during the 30-day grace period after expiration.',
 'https://dial.iowa.gov/licenses/health-professions/nursing-professional-midwifery/nursing-licensure/renewals',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IA','APRN','renewal_window_days', null, 60, null, null,
 'Iowa Administrative Code 655 ch. 7 (Advanced Registered Nurse Practitioners): "An ARNP license may be renewed beginning 60 days prior to the license expiration date and ending 30 days after the expiration date." This is a transactional open date, not merely a notice date.',
 'https://www.legis.iowa.gov/docs/iac/chapter/05-28-2025.655.7.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('IA','APRN','ce_topic_opioid_hours', null, null, null,
 '{"hours": 2, "periodicity": "per_renewal_cycle", "applies_to": "ARNP who has prescribed opioids to a patient during the renewal cycle", "topic": "U.S. Centers for Disease Control and Prevention guideline for prescribing opioids for chronic pain"}'::jsonb,
 'Iowa Administrative Code 655 ch. 7: "An ARNP who has prescribed opioids to a patient during the renewal cycle is required to complete a minimum of two contact hours of continuing education regarding the U.S. Centers for Disease Control and Prevention guideline for prescribing opioids for chronic pain". Corroborated by Iowa DIAL, ARNP Continuing Education Requirements: ARNPs who prescribe opioids must complete "at least two hours" addressing "the current CDC prescribing guidelines". Conditional on having prescribed -- hence value_json.',
 'https://www.legis.iowa.gov/docs/iac/chapter/05-28-2025.655.7.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

-- =============================================================================
-- MISSOURI -- physician and surgeon (MD)
-- Missouri State Board of Registration for the Healing Arts. RSMo ch. 334;
-- 20 CSR 2150.
-- =============================================================================
('MO','MD','ce_hours_total', null, 50, null, null,
 '20 CSR 2150-2.125: "Each licensee shall complete and report at least fifty (50) hours of continuing medical education every two (2) years. A total of at least one (1) hour, within the required fifty (50) hours, must pertain to the topic of the health benefits of nutrition."',
 'https://www.sos.mo.gov/cmsimages/adrules/csr/current/20csr/20c2150-2.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('MO','MD','ce_cycle_months', null, 24, null, null,
 '20 CSR 2150-2.125: the fifty hours are reported for "the twenty-four (24)-month period beginning January 1 of each even-numbered year and ending December 31 of each odd-numbered year". THIS IS A FIXED CALENDAR WINDOW, not a rolling period anchored to the licensee''s own dates.',
 'https://www.sos.mo.gov/cmsimages/adrules/csr/current/20csr/20c2150-2.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('MO','MD','initial_license_fee_cents', null, 10200, null, null,
 '20 CSR 2150-2.080 (Physician Licensure Fees), permanent physician: "Licensure Fee $102".',
 'https://www.sos.mo.gov/cmsimages/adrules/csr/current/20csr/20c2150-2.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('MO','MD','renewal_fee_cents', null, 14700, null, null,
 '20 CSR 2150-2.080 (Physician Licensure Fees), permanent physician: "Renewal Fee $147".',
 'https://www.sos.mo.gov/cmsimages/adrules/csr/current/20csr/20c2150-2.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

-- =============================================================================
-- MISSOURI -- advanced practice registered nurse (APRN)
-- Missouri State Board of Nursing. RSMo ch. 335, sec. 334.104; 20 CSR 2200-4.
-- =============================================================================
('MO','APRN','renewal_cycle_months', null, 24, null, null,
 '20 CSR 2200-4: professional nurse (RN) and APRN licences expire "April 30 of each odd-numbered year", on a biennial renewal period. (Licensed practical nurses expire May 31 of each even-numbered year; that is a different licence class.)',
 'https://www.sos.mo.gov/cmsimages/adrules/csr/current/20csr/20c2200-4.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('MO','APRN','ce_hours_total', null, null, null,
 '{"hours": 60, "periodicity": "per_renewal_cycle", "applies_to": "APRNs who are NOT nationally certified in their advanced practice nursing population focus area", "note": "nationally certified APRNs satisfy the requirement through certification and have no separate contact-hour count published by the Board"}'::jsonb,
 '20 CSR 2200-4: "uncertified APRNs" must complete "a minimum of sixty (60) contact hours in their advanced practice nursing population focus area of practice" during each biennial renewal period. THIS DOES NOT APPLY TO THE NATIONALLY CERTIFIED MAJORITY. Recording 60 as a bare per-cycle number would invoice every Missouri APRN a duty most of them do not have -- hence value_json.',
 'https://www.sos.mo.gov/cmsimages/adrules/csr/current/20csr/20c2200-4.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('MO','APRN','collaborative_agreement_required', null, null, true, null,
 'Missouri Division of Professional Registration, Board of Nursing -- Advanced Practice Nursing / Collaborative Practice: "the Missouri Legislature and Governor provided statutory authority for physicians and registered professional nurses who were advanced practice registered nurses to engage in written collaborative practice arrangements", under sec. 334.104.2 RSMo and 20 CSR 2200-4.200 / 20 CSR 2150-5.100. The arrangement carries a geographic proximity limit of "Thirty (non-HPSA) or fifty (HPSA) road mile distance from one another" and "Physician two week review provisions". 20 CSR 2200-4 further requires the agreement be "signed and dated by the collaborating physician and collaborating RN or APRN before it is implemented", "reviewed at least annually", that the physician be "immediately available for consultation", and that the physician review "a minimum of twenty percent (20%) of the cases in which the APRN" prescribes controlled substances. MISSOURI IS NOT A FULL-PRACTICE-AUTHORITY STATE and has no hours threshold that retires the arrangement.',
 'https://pr.mo.gov/nursing-advanced-practice-nursing-collaborative.asp',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

-- =============================================================================
-- KANSAS -- advanced practice registered nurse (APRN)
-- Kansas State Board of Nursing. K.S.A. 65-1113 et seq.
-- Kansas is the SPARSEST state in this group. See the conflicts file: the
-- Board of Healing Arts publishes its physician CE and fee figures only in
-- regulations that were not reachable, and nothing was carried over.
-- =============================================================================
('KS','APRN','renewal_cycle_months', null, 24, null, null,
 'K.S.A. 65-1132: "All licenses issued under the provisions of this act, whether initial or renewal, shall expire every two years", the board establishing the specific expiration date by regulation. The same section conditions renewal on "evidence of completion of continuing education in the advanced practice registered nurse role" without publishing an hour count.',
 'https://ksrevisor.gov/statutes/chapters/ch65/065_011_0032.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

-- =============================================================================
-- NEBRASKA -- medicine and surgery (MD)
-- Nebraska DHHS Division of Public Health, Licensure Unit. Neb. Rev. Stat.
-- ch. 38; 172 NAC.
-- =============================================================================
('NE','MD','renewal_cycle_months', null, 24, null, null,
 'Nebraska DHHS Licensure, Medicine and Surgery: "Licenses expire October 1 of every even year, regardless of when the license was issued."',
 'https://dhhs.ne.gov/licensure/pages/medicine-and-surgery.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('NE','MD','ce_hours_total', null, 50, null, null,
 'Nebraska DHHS Licensure, Medicine and Surgery: physicians must complete "50 hours of Category 1 AMA approved continuing education" for renewal.',
 'https://dhhs.ne.gov/licensure/pages/medicine-and-surgery.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('NE','MD','ce_cycle_months', null, 24, null, null,
 'Nebraska DHHS Licensure, Medicine and Surgery: the same page states both that "Licenses expire October 1 of every even year" and that the 50 Category 1 hours are required for renewal, so the CE clock is the biennial renewal period. NOTE the Department does not itself use the word "biennium" for the CE requirement; see requirement_conflicts.',
 'https://dhhs.ne.gov/licensure/pages/medicine-and-surgery.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('NE','MD','ce_topic_opioid_hours', null, null, null,
 '{"hours": 3, "periodicity": "per_renewal_cycle", "periodicity_confirmed": false, "applies_to": "all professionals who prescribe controlled substances", "includes": {"topic": "Prescription Drug Monitoring Program", "hours": 0.5}, "authority": "LB 731, Neb. Rev. Stat. sec. 38-145(6)"}'::jsonb,
 'Nebraska DHHS Licensure, Controlled Substances Continuing Competency Requirement: "3 hours of the continuing education (CE) are required to be on the subject of opioids and .5 hours of the 3 required hours are to be on the subject Prescription Drug Monitoring Program (PDMP)", applying to "All Professionals Who Prescribe Controlled Substances" under LB 731 (38-145(6)). Conditional on prescribing controlled substances, and the Department does not state the recurrence interval on the face of the document -- hence value_json with periodicity_confirmed false, and an open conflict.',
 'https://dhhs.ne.gov/licensure/Documents/ControlledSubstancesContCompReq.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

-- =============================================================================
-- NEBRASKA -- advanced practice registered nurse / nurse practitioner (APRN)
-- Nebraska DHHS Licensure Unit. Nurse Practitioner Practice Act,
-- Neb. Rev. Stat. sec. 38-2301 et seq.
-- =============================================================================
('NE','APRN','renewal_cycle_months', null, 24, null, null,
 'Nebraska DHHS Licensure, Nurse Licensing Renewal and Continuing Education: "APRN licenses expire on October 31st of each even-numbered year." Corroborated by the Department''s APRN-Nurse Practitioner application information: "All APRN licenses expire on October 31 of each even-numbered year", with an initial licence "valid after issuance for anywhere from 1 day to 24 months". NOTE the APRN date (Oct 31) is NOT the physician date (Oct 1).',
 'https://dhhs.ne.gov/licensure/Pages/Nurse-Licensing-Renewal-and-Continuing-Education.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('NE','APRN','ce_hours_total', null, null, null,
 '{"hours": 20, "periodicity": "per_2_years", "conditional": true, "pathway": "practice of at least 500 hours of nursing within five years PLUS 20 contact hours of continuing education within two years", "alternative_pathways": ["graduation within the last two years (no CE required)", "graduation within 2-5 years plus 20 contact hours within two years", "an approved refresher course within five years", "current national specialty certification", "a professional portfolio demonstrating competency goals"]}'::jsonb,
 'Nebraska DHHS Licensure, Nurse Licensing Renewal and Continuing Education: continuing competency is satisfied by ONE OF several alternatives, of which contact hours are only one -- "Practice nursing at least 500 hours within five years AND complete 20 contact hours of continuing education within two years", or graduation recency, or an approved refresher course, or "Maintain current national specialty certification", or a professional portfolio. NEBRASKA HAS NO UNCONDITIONAL CONTACT-HOUR MANDATE. Seeding 20 as a bare per-cycle number would manufacture a duty for every nationally certified Nebraska APRN, who has none -- hence value_json.',
 'https://dhhs.ne.gov/licensure/Pages/Nurse-Licensing-Renewal-and-Continuing-Education.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('NE','APRN','supervision_required', null, null, null,
 '{"required": true, "until_practice_hours": 2000, "instrument": "formal, written Transition to Practice agreement with a supervising provider", "supervising_provider_may_be": ["physician","osteopathic physician","nurse practitioner"], "supervising_provider_must": "be licensed in Nebraska and practise in the same or a related specialty", "after_threshold": "no transition-to-practice agreement required", "hours_measured_from": "graduation and initial certification as a Nurse Practitioner"}'::jsonb,
 'Nebraska DHHS Licensure, APRN-Nurse Practitioner application information: an applicant who has "not practiced a minimum of 2000 hours following graduation and initial certification as a Nurse Practitioner" must attest to having "a formal, written Transition to Practice agreement with a supervising provider", who must be a physician, osteopathic physician or nurse practitioner licensed in Nebraska and practising in the same or a related specialty. NEBRASKA IS A TIERED STATE: the duty ends at 2,000 hours, after which the NP has full practice authority. The Department''s own word is SUPERVISING, not collaborating, so this is supervision_required and NOT collaborative_agreement_required. A bare boolean would be wrong on one side of the threshold or the other -- hence value_json.',
 'https://dhhs.ne.gov/licensure/Documents/APRNNPapp.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

-- =============================================================================
-- NORTH DAKOTA -- physician (MD)
-- North Dakota Board of Medicine. NDCC ch. 43-17; NDAC title 50.
-- =============================================================================
('ND','MD','renewal_cycle_months', null, 24, null, null,
 'North Dakota Board of Medicine, Physician FAQ: "physician licenses expire on your birthday every other year". Renewal notices are sent 59 days and again 14 days before expiration.',
 'https://www.ndbom.org/practitioners/physicians/faqs.asp',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('ND','MD','ce_hours_total', null, 40, null, null,
 'North Dakota Board of Medicine, Continuing Medical Education: "40 AMA Category 1 hours of continuing medical education every two years", under NDCC sec. 43-17-27.1 and NDAC ch. 50-04-01, effective April 1, 2024. Prorated to 20 hours for a licensee of 1-2 years and to none for a licensee of under 1 year. Since August 1, 2023 the Board accepts current ABMS, AOA or Royal College certification or maintenance of certification in lieu of submitting hours.',
 'https://www.ndbom.org/practitioners/physicians/current/cme.asp',
 '2024-04-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('ND','MD','ce_cycle_months', null, 24, null, null,
 'North Dakota Board of Medicine, Continuing Medical Education: the 40 hours run "every two years", matching the biennial birthday expiry in the Board''s Physician FAQ.',
 'https://www.ndbom.org/practitioners/physicians/current/cme.asp',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('ND','MD','fingerprint_required', null, null, true, null,
 'North Dakota Board of Medicine, Physician FAQ: "No license of any type will be issued without the Board having the results of the federal and state background checks", with an initial background check fee of $43 submitted with "two required fingerprint cards". Verified at INITIAL LICENSURE; the Board does not publish a fingerprint condition on renewal on this page.',
 'https://www.ndbom.org/practitioners/physicians/faqs.asp',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

-- =============================================================================
-- NORTH DAKOTA -- advanced practice registered nurse (APRN)
-- North Dakota Board of Nursing. NDCC ch. 43-12.1; NDAC ch. 54-05-03.1.
-- =============================================================================
('ND','APRN','renewal_cycle_months', null, 24, null, null,
 'North Dakota Board of Nursing, Nursing Renewal FAQs: continuing education must be "completed within the 2 years prior to the expiration date on the license", i.e. a two-year renewal cycle. Corroborated by NDAC sec. 54-05-03.1-06: "The advanced practice registered nurse license is valid for the same period of time as the applicant''s registered nurse license."',
 'https://www.ndbon.org/licensing/renewal/nurse-renewal-faq/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('ND','APRN','ce_hours_total', null, 12, null, null,
 'North Dakota Board of Nursing, Continuing Education for Renewal: "all individuals renewing a nursing license must complete 12 contact hours of CE obtained within the preceding two (2) years". The Board separately requires 400 hours of nursing practice in the preceding four years, which is a practice-hours condition rather than a CE hour count and is not seeded here.',
 'https://ndbon.org/licensing/renewal/ce/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('ND','APRN','ce_cycle_months', null, 24, null, null,
 'North Dakota Board of Nursing, Continuing Education for Renewal: contact hours must be "obtained within the preceding two (2) years", i.e. the CE cycle is the renewal cycle.',
 'https://ndbon.org/licensing/renewal/ce/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('ND','APRN','ce_topic_pharmacotherapeutics_hours', null, null, null,
 '{"hours": 15, "periodicity": "per_2_years", "applies_to": "APRN with prescriptive authority", "in_addition_to_ce_hours_total": true}'::jsonb,
 'NDAC sec. 54-05-03.1-11, as published by the North Dakota Board of Nursing, Continuing Education for Renewal: an APRN with prescriptive authority must "Provide evidence of completion of fifteen contact hours of education during the previous two years in pharmacotherapy related to the scope of practice". Conditional on prescriptive authority, hence value_json. The Board notes APRN contact hours may also satisfy the registered nurse renewal CE obligation.',
 'https://ndbon.org/licensing/renewal/ce/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

-- =============================================================================
-- SOUTH DAKOTA -- physician (MD)
-- South Dakota Board of Medical and Osteopathic Examiners. SDCL ch. 36-4;
-- ARSD art. 20:47.
-- =============================================================================
('SD','MD','renewal_cycle_months', null, 24, null, null,
 'South Dakota Administrative Rules art. 20:47 fee schedule: "Biennial renewal of the license, $400". The Board''s own fee rule names the renewal as biennial.',
 'https://sdlegislature.gov/api/Rules/Rule/20:47.html?all=true',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('SD','MD','renewal_window_days', null, 90, null, null,
 'South Dakota Administrative Rules sec. 20:47:03:13: "Any licensee may renew through the state renewal process ninety days prior to the expiration date of the license." This is a transactional open date, not a notice date.',
 'https://sdlegislature.gov/api/Rules/Rule/20:47.html?all=true',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('SD','MD','initial_license_fee_cents', null, 40000, null, null,
 'South Dakota Administrative Rules art. 20:47 fee schedule: "Application for the initial license, $400".',
 'https://sdlegislature.gov/api/Rules/Rule/20:47.html?all=true',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('SD','MD','renewal_fee_cents', null, 40000, null, null,
 'South Dakota Administrative Rules art. 20:47 fee schedule: "Biennial renewal of the license, $400".',
 'https://sdlegislature.gov/api/Rules/Rule/20:47.html?all=true',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

-- =============================================================================
-- SOUTH DAKOTA -- certified nurse practitioner (APRN)
-- South Dakota Board of Nursing. SDCL ch. 36-9A; ARSD art. 20:48.
-- =============================================================================
('SD','APRN','renewal_cycle_months', null, 24, null, null,
 'South Dakota Administrative Rules sec. 20:48:03:10: a nursing licence "expires on the licensee''s birth date in the second calendar year following issuance, and biennially on the licensee''s birth date thereafter."',
 'https://sdlegislature.gov/api/Rules/Rule/20:48:03.html?all=true',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('SD','APRN','initial_license_fee_cents', null, 10000, null, null,
 'South Dakota Board of Nursing, Certified Nurse Practitioner examination licensure instructions: "The fee for licensure is $100 and must accompany application."',
 'https://doh.sd.gov/media/biflhr4o/cnpexamlicensureinstructionsapp42022.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('SD','APRN','collaborative_agreement_required', null, null, null,
 '{"required": true, "until_practice_hours": 1040, "hours_measured_as": "practice as a licensed CNP", "collaborator_may_be": ["South Dakota licensed physician","South Dakota licensed CNP"], "collaborator_must": "hold an unencumbered SD license and have at least two years of licensed experience in a comparable practice area", "after_threshold": "the collaborative agreement may be retired on request (Board Form 3)"}'::jsonb,
 'South Dakota Board of Nursing, Certified Nurse Practitioner examination licensure instructions: "All applicants for licensure are required to practice a minimum of 1,040 hours as a licensed CNP to practice without a collaborative agreement"; until then a collaborative agreement with a South Dakota licensed physician or CNP holding "an unencumbered SD license" and at least two years'' experience in a comparable practice area is required, and once the threshold is met the agreement may be retired through Form 3. SOUTH DAKOTA IS A TIERED STATE with a much lower threshold than Nebraska (1,040 vs 2,000) and a different instrument (collaboration, not supervision) -- hence value_json, and hence no supervision_required row.',
 'https://doh.sd.gov/media/biflhr4o/cnpexamlicensureinstructionsapp42022.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

-- =============================================================================
-- MONTANA -- physician (MD)
-- Montana DLI Board of Medical Examiners. MCA title 37 ch. 3; ARM 24.156.
-- Montana verifies a genuine ZERO for physician CME -- the Board states the
-- negative in terms, which is different from a board simply being silent.
-- =============================================================================
('MT','MD','renewal_cycle_months', null, 24, null, null,
 'Montana Board of Medical Examiners, FAQs: physician renewal is biennial, with licences expiring "March 31" of the expiration year. Corroborated by the Board''s Renewal Process page: physicians renew "between Feb. 1 and March 31 of their renewal year".',
 'https://boards.bsd.dli.mt.gov/medical-examiners/faq',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('MT','MD','ce_hours_total', null, 0, null, null,
 'Montana Board of Medical Examiners, FAQs, answering whether CME is required: "No. Montana does not require Physicians to acquire CME in order to acquire or renew a license." THIS IS AN AFFIRMATIVE NEGATIVE PUBLISHED BY THE BOARD, not an inference from silence, which is why a zero is written here and not in the conflicts file.',
 'https://boards.bsd.dli.mt.gov/medical-examiners/faq',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('MT','MD','renewal_fee_cents', null, 37500, null, null,
 'Montana Board of Medical Examiners, FAQs: active physician renewal "$375"; inactive renewal "$190". A 100% late fee is added on top of the renewal fee after expiration.',
 'https://boards.bsd.dli.mt.gov/medical-examiners/faq',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('MT','MD','initial_license_fee_cents', null, 37500, null, null,
 'ARM 24.156.409(2) fee schedule, as published in the Montana State Board of Medical Examiners rules: physician licence application fee "$375".',
 'https://boards.bsd.dli.mt.gov/_docs/med/CH-156-MED-as-of-09-30-22.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

-- =============================================================================
-- MONTANA -- advanced practice registered nurse (APRN)
-- Montana DLI Board of Nursing. MCA title 37 ch. 8; ARM 24.159.
-- =============================================================================
('MT','APRN','renewal_cycle_months', null, 24, null, null,
 'Montana Board of Nursing, APRN: renewal "Occurs every other year. If you are an ''odd'' licensee, your license must be renewed by December 31st of odd numbered years, if you are an ''even'' licensee, your license must be renewed by December 31st of even numbered years." NOTE this is a DIFFERENT date from the Montana physician credential (March 31).',
 'https://boards.bsd.dli.mt.gov/nursing/license-information/aprn',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('MT','APRN','renewal_fee_cents', null, 5000, null, null,
 'Montana Board of Nursing, APRN: renewal fee "$50.00 per APRN certification type"; adding a certification is "$75.00 per additional APRN certification". A clinician holding two APRN certifications pays twice.',
 'https://boards.bsd.dli.mt.gov/nursing/license-information/aprn',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true),

('MT','APRN','ce_hours_total', null, 0, null, null,
 'Montana Board of Nursing, Continuing Education: "While the Montana Board of Nursing no longer requires continuing education contact hours to be completed as a requirement for renewal of a nursing license, the Board will continue to provide the free contact hours below." THIS IS AN AFFIRMATIVE NEGATIVE PUBLISHED BY THE BOARD. Montana is the only state in this group where BOTH professions have a verified zero CE requirement.',
 'https://boards.bsd.dli.mt.gov/nursing/continuing-education',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-c', 1, true);

commit;
