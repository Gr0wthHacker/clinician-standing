-- =============================================================================
-- requirements_seed.sql -- the rules asset, first four states (PRD 5.3).
--
-- CA, FL, TX, NY x { physician (MD), nurse practitioner (APRN) }.
--
-- VERIFICATION STANDARD (read db/seeds/README.md before editing):
--   Every row below carries a citation to a state board page, a state statute,
--   or a board rule that was FETCHED AND READ on 2026-09-18. No row is written
--   from recall, from a CE aggregator, or from inference. Where a value could
--   not be verified from a primary source it is NOT in this file -- it is in
--   requirement_conflicts_seed.sql as an open conflict. An open conflict blocks
--   auto-clear (PRD 8.1 condition 6) and raises RULE_UNCERTAIN (PRD 8.3), which
--   is the correct behaviour for a value we do not know.
--
-- VALUE COLUMN CONVENTION
--   value_num   a plain per-cycle quantity (months, days, hours, cents).
--   value_bool  a plain yes/no.
--   value_json  a quantity that is NOT simply "this much, every cycle" --
--               one-time requirements, requirements on a different clock than
--               the renewal cycle, and requirements that apply only to a subset
--               of licensees. Recording a one-time 12-hour course as a per-cycle
--               12 would generate a wrong obligation every two years, so those
--               carry {"hours": n, "periodicity": ...} instead.
--               Consumers MUST branch on the presence of value_json.
--
--   license_type 'MD' and 'APRN' match the vocabulary in 0003_credentials.sql
--   ("MD, DO, RN, APRN, PA..."). DO IS NOT COVERED -- see README.
--
-- Fees are in cents and are the amount the licensee actually pays where the
-- board publishes a single total; component breakdowns are in the citation.
--
-- Idempotent: safe to re-run. Respects ux_requirements_current (one is_current
-- row per state/license_type/field_key).
-- =============================================================================

begin;

-- Re-running replaces only the rows this file owns. requirement_conflicts rows
-- written by requirement_conflicts_seed.sql point at these rows, so they are
-- cleared first; re-run requirement_conflicts_seed.sql AFTER this file.
delete from requirement_conflicts
 where observed_by = 'research-agent'
   and requirement_id in (
         select id from requirements
          where verified_by = 'research-agent'
            and state in ('CA','FL','TX','NY')
            and license_type in ('MD','APRN'));

delete from requirements
 where verified_by = 'research-agent'
   and state in ('CA','FL','TX','NY')
   and license_type in ('MD','APRN');

insert into requirements
  (state, license_type, field_key,
   value_text, value_num, value_bool, value_json,
   citation, citation_url, effective_date,
   verified_at, verified_by, version, is_current)
values

-- =============================================================================
-- CALIFORNIA -- physician and surgeon (MD)
-- Medical Board of California. B&P Code Div. 2 Ch. 5; 16 CCR Div. 13.
-- =============================================================================
('CA','MD','renewal_cycle_months', null, 24, null, null,
 'Medical Board of California, Physicians and Surgeons - Renew (Current Status): "you must renew your license every two years"; standard licenses are "valid for a 24-month period until the next renewal".',
 'https://www.mbc.ca.gov/Licensing/Physicians-and-Surgeons/Renew/Current-Status/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('CA','MD','renewal_window_days', null, 180, null, null,
 'Medical Board of California, Physicians and Surgeons - Renew: "The Board will send you email notifications to renew your license online starting 180 days prior to your expiration date." NOTE: the Board states a NOTIFICATION start, not an explicit renewal-open date; see open conflict CA/MD/renewal_window_days.',
 'https://www.mbc.ca.gov/Licensing/Physicians-and-Surgeons/Renew/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('CA','MD','ce_hours_total', null, 50, null, null,
 '16 CCR sec. 1336, as published by the Medical Board of California, Continuing Medical Education: "minimum of 50 hours of approved Continuing Medical Education (CME) hours during each biennial renewal cycle".',
 'https://www.mbc.ca.gov/Licensing/Physicians-and-Surgeons/Renew/Current-Status/Continuing-Medical-Education.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('CA','MD','ce_cycle_months', null, 24, null, null,
 '16 CCR sec. 1336, as published by the Medical Board of California: the 50-hour requirement runs "during each biennial renewal cycle", i.e. the CE cycle is the renewal cycle.',
 'https://www.mbc.ca.gov/Licensing/Physicians-and-Surgeons/Renew/Current-Status/Continuing-Medical-Education.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('CA','MD','ce_topic_pain_management_hours', null, null, null,
 '{"hours": 12, "periodicity": "one_time", "exempt": ["pathology","radiology"], "note": "must include the risks of addiction associated with Schedule II drugs"}'::jsonb,
 'Medical Board of California, Continuing Medical Education: one-time 12 hours in pain management and the treatment of terminally ill and dying patients; "must include the risks of addiction associated with the use of Schedule II drugs"; pathologists and radiologists exempt. ONE-TIME, not per cycle.',
 'https://www.mbc.ca.gov/Licensing/Physicians-and-Surgeons/Renew/Current-Status/Continuing-Medical-Education.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('CA','MD','initial_license_fee_cents', null, 117600, null, null,
 'Medical Board of California, Physicians and Surgeons - Fees: initial license fee "$1,176 before the Board can issue your license", including the mandatory $25 Steven M. Thompson Physician Corps Loan Repayment Program fee. A separate non-refundable application fee of $674 (which includes the $49 fingerprint-processing fee) is payable earlier in the process.',
 'https://www.mbc.ca.gov/Licensing/Physicians-and-Surgeons/Apply/Physicians-and-Surgeons-License/Fees.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('CA','MD','renewal_fee_cents', null, 120600, null, null,
 'Medical Board of California, Physicians and Surgeons - Renew - Fees: biennial renewal total "$1,206", comprising a $1,151 base renewal fee, a $25 Steven M. Thompson Program fee and a $30 CURES fee. Cites BPC sections 2435, 2436.5, 2439, 2440, 2441, 2442 and 208.',
 'https://www.mbc.ca.gov/Licensing/Physicians-and-Surgeons/Renew/Current-status/Fees.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('CA','MD','fingerprint_required', null, null, true, null,
 'Medical Board of California, Physicians and Surgeons - Fees: the application fee "includes the required $49 fingerprint-processing fee". Verified at INITIAL LICENSURE; the Board does not publish a fingerprint condition on renewal on this page.',
 'https://www.mbc.ca.gov/Licensing/Physicians-and-Surgeons/Apply/Physicians-and-Surgeons-License/Fees.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

-- =============================================================================
-- CALIFORNIA -- nurse practitioner (APRN)
-- Board of Registered Nursing. B&P Code Div. 2 Ch. 6; 16 CCR Div. 14.
-- A California NP holds an RN license plus an NP certificate; both renew on the
-- same biennial clock and each carries its own fee.
-- =============================================================================
('CA','APRN','renewal_cycle_months', null, 24, null, null,
 'California Board of Registered Nursing, License/Certificate Renewal: the license "will expire every two years, if renewed timely" (B&P Code sec. 2811.1).',
 'https://www.rn.ca.gov/licensees/lic-renewal.shtml',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('CA','APRN','renewal_window_days', null, 90, null, null,
 'California Board of Registered Nursing, License/Certificate Renewal: renewal notices are sent "approximately three months prior to the expiration date" and a licensee "may not renew earlier than three months prior to the expiration date". Three months recorded as 90 days.',
 'https://www.rn.ca.gov/licensees/lic-renewal.shtml',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('CA','APRN','ce_hours_total', null, 30, null, null,
 '16 CCR sec. 1451, as published by the California Board of Registered Nursing, Continuing Education for License Renewal: "30 contact hours of continuing education every two years".',
 'https://www.rn.ca.gov/licensees/ce-renewal.shtml',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('CA','APRN','ce_cycle_months', null, 24, null, null,
 '16 CCR sec. 1451, as published by the California Board of Registered Nursing: the 30 contact hours are required "every two years", i.e. the CE cycle is the renewal cycle.',
 'https://www.rn.ca.gov/licensees/ce-renewal.shtml',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('CA','APRN','ce_topic_implicit_bias_hours', null, null, null,
 '{"hours": 1, "periodicity": "one_time", "window": "within first two years post-licensure"}'::jsonb,
 'B&P Code sec. 2811.5 (AB 1407, Burke, Chapter 445, Statutes of 2021), as published by the California Board of Registered Nursing: "one hour of direct participation in an implicit bias course" for licensees within their first 2 years post-licensure. ONE-TIME, not per cycle.',
 'https://www.rn.ca.gov/licensees/ce-renewal.shtml',
 '2022-01-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('CA','APRN','initial_license_fee_cents', null, 50000, null, null,
 'California Board of Registered Nursing, Fee Schedule: Nurse Practitioner certification application fee "$500". The underlying RN licence application is a separate fee ($300 California graduate / $350 out-of-state graduate / $750 international graduate), and an NP furnishing number is a further $400.',
 'https://www.rn.ca.gov/consumers/fees.shtml',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('CA','APRN','renewal_fee_cents', null, 15000, null, null,
 'California Board of Registered Nursing, Fee Schedule: Nurse Practitioner renewal (timely) "$150"; delinquent "$225". The underlying RN licence renewal is a separate $190 timely / $280 delinquent, and furnishing number renewal a further $180 timely.',
 'https://www.rn.ca.gov/consumers/fees.shtml',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('CA','APRN','fingerprint_required', null, null, true, null,
 'California Board of Registered Nursing, License/Certificate Renewal (B&P Code sec. 144, sec. 121): "If you are renewing your license to an ACTIVE status, you are required to furnish to the Department of Justice, a full set of fingerprints." Waived for inactive-status renewal.',
 'https://www.rn.ca.gov/licensees/lic-renewal.shtml',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('CA','APRN','supervision_required', null, null, true, null,
 'B&P Code sec. 2725.5 / sec. 2836.1, as described by the California Board of Registered Nursing, Assembly Bill 890: a traditional California NP practises under standardized procedures -- "NPs can continue to work under physician supervision with the use of standardized procedures in their existing settings". SUBJECT TO AN OPEN CONFLICT: B&P sec. 2837.103 (103 NP) and sec. 2837.104 (104 NP) permit practice WITHOUT standardized procedures; a single boolean cannot express California tiered NP authority. See requirement_conflicts.',
 'https://www.rn.ca.gov/practice/ab890.shtml',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

-- =============================================================================
-- FLORIDA -- medical doctor (MD)
-- Florida Board of Medicine, DOH/MQA. F.S. ch. 458 and ch. 456; F.A.C. 64B8.
-- =============================================================================
('FL','MD','renewal_cycle_months', null, 24, null, null,
 'Florida Board of Medicine, General Renewal Requirements - Medical Doctor: licences are "renewed every two years"; Group 1 expires January 31 in even-numbered years, Group 2 January 31 in odd-numbered years.',
 'https://flboardofmedicine.gov/general-renewal-requirements-medical-doctor-2/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('FL','MD','renewal_window_days', null, 90, null, null,
 'Florida Board of Medicine, Medical Doctor (MD) Renewal: the "Renew My License" option becomes available in the online portal "no later than 90 days prior to your license expiration date".',
 'https://flboardofmedicine.gov/medical-doctor-renewal/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('FL','MD','ce_hours_total', null, 40, null, null,
 'Florida Board of Medicine, General Renewal Requirements - Medical Doctor: 40 hours of continuing medical education per biennial cycle.',
 'https://flboardofmedicine.gov/general-renewal-requirements-medical-doctor-2/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('FL','MD','ce_cycle_months', null, 24, null, null,
 'Florida Board of Medicine, General Renewal Requirements - Medical Doctor: the 40 hours are required per biennial cycle, i.e. the CE cycle is the renewal cycle.',
 'https://flboardofmedicine.gov/general-renewal-requirements-medical-doctor-2/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('FL','MD','ce_topic_medical_errors_hours', null, 2, null, null,
 'Florida Board of Medicine, General Renewal Requirements - Medical Doctor: "2-hour board-approved CME course on the prevention of medical errors", each biennium.',
 'https://flboardofmedicine.gov/general-renewal-requirements-medical-doctor-2/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('FL','MD','ce_topic_controlled_substance_hours', null, null, null,
 '{"hours": 2, "periodicity": "per_renewal_cycle", "applies_to": "physicians registered with the DEA to prescribe controlled substances"}'::jsonb,
 'Florida Board of Medicine, General Renewal Requirements - Medical Doctor: "2-hour board-approved CME course on prescribing controlled substances", required of DEA-registered physicians (s. 456.0301, F.S.). Conditional on DEA registration, hence value_json.',
 'https://flboardofmedicine.gov/general-renewal-requirements-medical-doctor-2/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('FL','MD','ce_topic_domestic_violence_hours', null, null, null,
 '{"hours": 2, "periodicity": "every_third_biennium"}'::jsonb,
 'Florida Board of Medicine, General Renewal Requirements - Medical Doctor: "2-hour course on domestic violence every third biennial cycle". NOT every cycle.',
 'https://flboardofmedicine.gov/general-renewal-requirements-medical-doctor-2/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('FL','MD','renewal_fee_cents', null, 35500, null, null,
 'Florida Board of Medicine, Medical Doctor (MD) Renewal: "$355.00" active-to-active if renewing before the licence expires; "$705.00" if renewing after expiration.',
 'https://flboardofmedicine.gov/medical-doctor-renewal/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('FL','MD','fingerprint_required', null, null, true, null,
 'Florida Board of Medicine, Medical Doctor (MD) Renewal: "Florida passed House Bill 975 following the 2024 legislative session, which requires this profession to complete electronic fingerprinting"; a "$43.25 fee is required for FDLE to retain your fingerprint for background screening" per section 456.0135(6)(1), Florida Statutes.',
 'https://flboardofmedicine.gov/medical-doctor-renewal/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

-- =============================================================================
-- FLORIDA -- advanced practice registered nurse (APRN)
-- Florida Board of Nursing. F.S. ch. 464 and ch. 456; F.A.C. 64B9.
-- =============================================================================
('FL','APRN','renewal_cycle_months', null, 24, null, null,
 'Florida Board of Nursing, Advanced Practice Registered Nurse (APRN) Renewal: renewal is biennial (s. 464.013, F.S., Renewal of License or Certificate); the current Group 1 licence "will expire at midnight, Eastern Standard Time, April 30, 2028".',
 'https://floridasnursing.gov/advanced-practice-registered-nurse-renewal/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('FL','APRN','ce_hours_total', null, 24, null, null,
 'Florida Board of Nursing, Continuing Education (APRN): 24 contact hours per biennium; the page states the domestic violence hours are "in addition to the 24 hours", confirming 24 as the base total.',
 'https://floridasnursing.gov/continuing-education-aaprn/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('FL','APRN','ce_cycle_months', null, 24, null, null,
 'Florida Board of Nursing, Continuing Education (APRN): contact hours are counted per biennium, i.e. the CE cycle is the renewal cycle.',
 'https://floridasnursing.gov/continuing-education-aaprn/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('FL','APRN','ce_topic_medical_errors_hours', null, 2, null, null,
 'Florida Board of Nursing, Continuing Education (APRN): "Prevention of Medical Errors" 2 hours, every renewal, board-approved.',
 'https://floridasnursing.gov/continuing-education-aaprn/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('FL','APRN','ce_topic_laws_and_rules_hours', null, 2, null, null,
 'Florida Board of Nursing, Continuing Education (APRN): "Florida Laws & Rules" 2 hours, every renewal, board-approved.',
 'https://floridasnursing.gov/continuing-education-aaprn/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('FL','APRN','ce_topic_human_trafficking_hours', null, 2, null, null,
 'Florida Board of Nursing, Continuing Education (APRN): "Human Trafficking" 2 hours every renewal, per s. 464.013, F.S.; the course "does not have to be a Florida Board of Nursing approved course".',
 'https://floridasnursing.gov/continuing-education-aaprn/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('FL','APRN','ce_topic_controlled_substance_hours', null, 3, null, null,
 'Florida Board of Nursing, Continuing Education (APRN): "Safe and Effective Prescription of Controlled Substances" 3 hours per renewal, from an accredited organisation (AMA, ANCC, AANA or AANP).',
 'https://floridasnursing.gov/continuing-education-aaprn/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('FL','APRN','ce_topic_impairment_hours', null, null, null,
 '{"hours": 2, "periodicity": "every_other_renewal"}'::jsonb,
 'Florida Board of Nursing, Continuing Education (APRN): "Recognition of Impairment in the Workplace" 2 hours, "required every other renewal". NOT every cycle.',
 'https://floridasnursing.gov/continuing-education-aaprn/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('FL','APRN','ce_topic_hiv_aids_hours', null, null, null,
 '{"hours": 1, "periodicity": "one_time", "window": "prior to first renewal"}'::jsonb,
 'Florida Board of Nursing, Continuing Education (APRN): "HIV/AIDS" 1 hour, "one-time requirement prior to the first renewal". ONE-TIME, not per cycle.',
 'https://floridasnursing.gov/continuing-education-aaprn/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('FL','APRN','ce_topic_domestic_violence_hours', null, null, null,
 '{"hours": 2, "periodicity": "every_third_biennium", "in_addition_to_ce_hours_total": true}'::jsonb,
 'Florida Board of Nursing, Continuing Education (APRN): "Domestic Violence" 2 hours "required every third biennium and the hours are in addition to the 24 hours".',
 'https://floridasnursing.gov/continuing-education-aaprn/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('FL','APRN','renewal_fee_cents', null, 6000, null, null,
 'Florida Board of Nursing, APRN Renewal: "Active to Active" status renewing before expiration "$60.00". SUBJECT TO AN OPEN CONFLICT: s. 464.012, F.S. caps the biennial renewal fee at "not to exceed $50" -- see requirement_conflicts.',
 'https://floridasnursing.gov/advanced-practice-registered-nurse-renewal/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('FL','APRN','initial_license_fee_cents', null, 11000, null, null,
 'Florida Board of Nursing, Advanced Practice Registered Nurse (APRN): "$110.00 application and licensure fee". SUBJECT TO AN OPEN CONFLICT: s. 464.012, F.S. sets "an application fee not to exceed $100" -- see requirement_conflicts.',
 'https://floridasnursing.gov/advanced-practice-registered-nurse/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('FL','APRN','fingerprint_required', null, null, true, null,
 'Florida Board of Nursing, APRN Renewal, citing section 456.0135(6)(1), Florida Statutes (fingerprint retention).',
 'https://floridasnursing.gov/advanced-practice-registered-nurse-renewal/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('FL','APRN','collaborative_agreement_required', null, null, true, null,
 'Florida Statutes s. 464.012: "An advanced practice registered nurse shall perform those functions authorized in this section within the framework of an established protocol that must be maintained on site at the location or locations at which an advanced practice registered nurse practices". SUBJECT TO AN OPEN CONFLICT: s. 464.0123, F.S. autonomous practice registration removes the protocol requirement for qualifying APRNs -- see requirement_conflicts.',
 'https://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute&URL=0400-0499%2F0464%2FSections%2F0464.012.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

-- =============================================================================
-- TEXAS -- physician (MD)
-- Texas Medical Board. Tex. Occ. Code ch. 155-157; 22 TAC part 9.
-- =============================================================================
('TX','MD','renewal_cycle_months', null, 24, null, null,
 'Texas Medical Board, Physician Renewal: registration is biennial, "every two years"; the TMB CME page states the cycle is "every 24 months (24 month timeline is in relation to the biennial registration period, not the calendar year)".',
 'https://www.tmb.texas.gov/apply-renew/physician/physician-renewal',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('TX','MD','ce_hours_total', null, 48, null, null,
 'Texas Medical Board, Continuing Education Requirements for Physicians (22 TAC sec. 166.2): 48 credits of CME per registration period, of which a minimum of 24 hours must be formal Category 1 or 1A and up to 24 hours may be informal.',
 'https://www.tmb.texas.gov/apply-renew/physician/continuing-education-requirements-for-physicians',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('TX','MD','ce_cycle_months', null, 24, null, null,
 'Texas Medical Board, Continuing Education Requirements for Physicians: the 48-credit requirement runs "every 24 months (24 month timeline is in relation to the biennial registration period, not the calendar year)".',
 'https://www.tmb.texas.gov/apply-renew/physician/continuing-education-requirements-for-physicians',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('TX','MD','ce_topic_ethics_hours', null, 2, null, null,
 'Texas Medical Board, Continuing Education Requirements for Physicians, Board rule 161.35: 2 formal hours in medical ethics and/or professional responsibility per registration period.',
 'https://www.tmb.texas.gov/apply-renew/physician/continuing-education-requirements-for-physicians',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('TX','MD','ce_topic_opioid_hours', null, null, null,
 '{"hours": 2, "periodicity": "every_8_years", "formal": true}'::jsonb,
 'Texas Occupations Code sec. 156.055, as published by the Texas Medical Board, Continuing Education Requirements for Physicians: 2 formal hours in pain management and opioid prescribing, required every 8 years. NOT per registration period.',
 'https://www.tmb.texas.gov/apply-renew/physician/continuing-education-requirements-for-physicians',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('TX','MD','ce_topic_human_trafficking_hours', null, null, null,
 '{"hours": 1, "periodicity": "every_6_years"}'::jsonb,
 'Texas Occupations Code sec. 156.060, as published by the Texas Medical Board, Continuing Education Requirements for Physicians: 1 hour of human trafficking prevention every 6 years. NOT per registration period.',
 'https://www.tmb.texas.gov/apply-renew/physician/continuing-education-requirements-for-physicians',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('TX','MD','renewal_fee_cents', null, 49148, null, null,
 'Texas Medical Board, Physician Renewal: $491.48 for the 24-month biennial renewal, comprising a $370 agency fee, $80 SB 104 fee, $2 Office of Patient Protection fee, $21 NPDB fee, $7 PHP fee and $11.48 PMP fee.',
 'https://www.tmb.texas.gov/apply-renew/physician/physician-renewal',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('TX','MD','initial_license_fee_cents', null, 86700, null, null,
 'Texas Medical Board, Full Texas Medical License Application: "As of 9/1/2025, the fee for physician licensure in Texas is $867.00 and includes the Jurisprudence Exam fee." Additional non-refundable surcharges totalling $28.00 are assessed separately, as is the third-party fingerprint vendor fee.',
 'https://www.tmb.texas.gov/apply-renew/physician/physician-apply/full-texas-medical-license-application',
 '2025-09-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('TX','MD','fingerprint_required', null, null, true, null,
 'Texas Medical Board, Physician Renewal: fingerprint background check results are required before a physician can access the online registration system. Texas Medical Board, Full Texas Medical License Application: applicants submit fingerprints through IdentoGo by IDEMIA for the criminal history check.',
 'https://www.tmb.texas.gov/apply-renew/physician/physician-renewal',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('TX','MD','csr_required', null, null, false, null,
 'Texas Medical Board, Prescribing and Supervision: "the requirement for controlled substances registration (CSR) with the Texas Department of Public Safety (DPS) was eliminated on September 1, 2016. DPS has stopped accepting applications for the Texas Controlled Substances Registration under Chapter 481.061 of the Health and Safety Code." (SB 195, 84th Legislature.) Federal DEA registration is still required.',
 'https://www.tmb.texas.gov/apply-renew/physician/prescribing-and-supervision',
 '2016-09-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

-- =============================================================================
-- TEXAS -- advanced practice registered nurse (APRN)
-- Texas Board of Nursing. Tex. Occ. Code ch. 301 and 157; 22 TAC part 11.
-- =============================================================================
('TX','APRN','renewal_cycle_months', null, 24, null, null,
 'Texas Board of Nursing Rule 216.1(14), as published by the Board: "subsequent licensing periods will be 2 years in length".',
 'https://www.bon.texas.gov/education_continuing_education.asp.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('TX','APRN','renewal_window_days', null, 60, null, null,
 'Texas Board of Nursing, Licensure Renewal Information: the timely renewal application becomes accessible "within sixty (60) days" before licence expiration.',
 'https://www.bon.texas.gov/licensure_renewal.asp.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('TX','APRN','ce_hours_total', null, 20, null, null,
 'Texas Board of Nursing Rule 216.3(a), as published by the Board: "complete 20 contact hours of continuing nursing education (CNE) in the nurse''s area of practice within the licensing period".',
 'https://www.bon.texas.gov/education_continuing_education.asp.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('TX','APRN','ce_cycle_months', null, 24, null, null,
 'Texas Board of Nursing Rules 216.1(14) and 216.3(a): the 20 contact hours are required "within the licensing period", and the licensing period is 2 years.',
 'https://www.bon.texas.gov/education_continuing_education.asp.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('TX','APRN','ce_topic_pharmacotherapeutics_hours', null, null, null,
 '{"hours": 5, "periodicity": "per_licensing_period", "applies_to": "APRN with prescriptive authority", "in_addition_to_ce_hours_total": true}'::jsonb,
 'Texas Board of Nursing Rule 216.3, as published by the Board: an APRN with prescriptive authority must complete "at least 5 additional contact hours of continuing education in pharmacotherapeutics" beyond the base 20 hours. Conditional on prescriptive authority, hence value_json.',
 'https://www.bon.texas.gov/education_continuing_education.asp.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('TX','APRN','ce_topic_jurisprudence_ethics_hours', null, null, null,
 '{"hours": 2, "periodicity": "every_third_licensure_renewal_cycle"}'::jsonb,
 'Texas Board of Nursing Rule 216.3(g), as published by the Board: "at least two contact hours in nursing jurisprudence and ethics prior to the end of every third licensure renewal cycle"; certification may not be substituted for it. NOT every cycle.',
 'https://www.bon.texas.gov/faq_education_continuing_ed_and_competency.asp.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('TX','APRN','ce_topic_opioid_hours', null, null, null,
 '{"hours": 2, "periodicity": "annual", "applies_to": "APRN prescribing opioids under a Tex. Occ. Code sec. 157.0513 delegation", "note": "narrow applicability; see requirement_conflicts"}'::jsonb,
 'Texas Occupations Code sec. 157.0513(a)(4): an advanced practice registered nurse or physician assistant prescribing opioids must complete "not less than two hours of continuing education annually" regarding safe pain management. Applies only to the sec. 157.0513 delegation pathway, not to every Texas APRN -- see requirement_conflicts.',
 'https://statutes.capitol.texas.gov/docs/OC/htm/OC.157.htm',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('TX','APRN','collaborative_agreement_required', null, null, true, null,
 'Texas Occupations Code sec. 157.0512: a physician may delegate prescriptive authority to an advanced practice registered nurse only through a prescriptive authority agreement, which sec. 157.0512(e) requires to be in writing. Scope note: verified for PRESCRIBING; see requirement_conflicts for non-prescribing practice.',
 'https://statutes.capitol.texas.gov/docs/OC/htm/OC.157.htm',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('TX','APRN','csr_required', null, null, false, null,
 'Texas Health and Safety Code sec. 481.061 (Texas Controlled Substances Registration) was repealed by SB 195, 84th Legislature, effective September 1, 2016; DPS stopped accepting applications and no longer issues a Texas CSR to any practitioner. Quoted from the Texas Medical Board, Prescribing and Supervision page: "the requirement for controlled substances registration (CSR) with the Texas Department of Public Safety (DPS) was eliminated on September 1, 2016." The repeal is statute-wide, not physician-specific. Federal DEA registration is still required.',
 'https://www.tmb.texas.gov/apply-renew/physician/prescribing-and-supervision',
 '2016-09-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

-- =============================================================================
-- NEW YORK -- physician (MD)
-- NYSED Office of the Professions. Education Law Title VIII art. 131.
-- NY registers rather than "renews"; the registration period is the cycle.
-- =============================================================================
('NY','MD','renewal_cycle_months', null, 24, null, null,
 'NYSED Office of the Professions, Online Registration Renewal: the registration period is "two years for physicians" (most other professions are three years).',
 'https://www.op.nysed.gov/registration-renewal/online-registration-renewal',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('NY','MD','ce_topic_opioid_hours', null, null, null,
 '{"hours": 3, "periodicity": "every_3_years", "applies_to": "prescribers with a DEA registration", "topics": ["pain management","palliative care","addiction"]}'::jsonb,
 'Public Health Law sec. 3309-a(3), as published by NYSED Office of the Professions, NYSDOH Mandatory Prescriber Education: "at least three (3) hours of course work or training in pain management, palliative care, and addiction", "once every three (3) years", for prescribers licensed under Title 8 of the Education Law who have a DEA registration number. The 3-year topic clock does NOT align with the 2-year physician registration cycle.',
 'https://www.op.nysed.gov/professions/physicians/nysdoh-mandatory-prescriber-education',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('NY','MD','initial_license_fee_cents', null, 73500, null, null,
 'NYSED Office of the Professions, Fees: Medicine initial licence "Application fee $135 plus registration $600 totaling $735".',
 'https://www.op.nysed.gov/about/fees',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('NY','MD','renewal_fee_cents', null, 60000, null, null,
 'NYSED Office of the Professions, Fees: Medicine registration renewal "$600" for a two-year registration period.',
 'https://www.op.nysed.gov/about/fees',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('NY','MD','csr_required', null, null, false, null,
 'New York State Department of Health, Bureau of Narcotic Enforcement, Licensing and Certification: "The requirement to prescribe a controlled substance in New York State is the appropriate practitioner license and a DEA registration. There is not a separate state controlled substance license needed for practitioners in New York State."',
 'https://www.health.ny.gov/professionals/narcotic/licensing_and_certification/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

-- =============================================================================
-- NEW YORK -- nurse practitioner (APRN)
-- NYSED Office of the Professions. Education Law art. 139; 8 NYCRR part 64.
-- A NY NP holds an RN licence plus NP certification; both register on the same
-- three-year clock and each carries its own fee.
-- =============================================================================
('NY','APRN','renewal_cycle_months', null, 36, null, null,
 'NYSED Office of the Professions, NYS Nursing RN License Requirements: the registration period is "3 years in New York State. The second registration after licensure is shortened to move your re-registration period to align with your month of birth." Confirmed by the Online Registration Renewal page, which states three years for all professions except Medicine and Medical Physics.',
 'https://www.op.nysed.gov/professions/registered-professional-nursing/license-requirements',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('NY','APRN','ce_topic_opioid_hours', null, null, null,
 '{"hours": 3, "periodicity": "every_3_years", "applies_to": "prescribers with a DEA registration", "topics": ["pain management","palliative care","addiction"]}'::jsonb,
 'Public Health Law sec. 3309-a(3), as published by NYSED Office of the Professions, Mandatory Prescriber Education for Nurse Practitioners: "at least three (3) hours of course work or training in pain management, palliative care, and addiction", required "by July 1, 2017, and once every three (3) years thereafter", for prescribers licensed under Title 8 of the Education Law who have a DEA registration number.',
 'https://www.op.nysed.gov/professions/nurse-practitioners/mandatory-prescriber-education-nurse',
 '2017-07-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('NY','APRN','initial_license_fee_cents', null, 8500, null, null,
 'NYSED Office of the Professions, Fees: Nurse Practitioner initial certification "Application fee $50 plus registration $35 totaling $85". The underlying RN licence is a separate $143 ($70 application plus $73 registration).',
 'https://www.op.nysed.gov/about/fees',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('NY','APRN','renewal_fee_cents', null, 3500, null, null,
 'NYSED Office of the Professions, Fees: Nurse Practitioner registration renewal "$35". The underlying RN registration renewal is a separate "$73".',
 'https://www.op.nysed.gov/about/fees',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('NY','APRN','csr_required', null, null, false, null,
 'New York State Department of Health, Bureau of Narcotic Enforcement, Licensing and Certification: "The requirement to prescribe a controlled substance in New York State is the appropriate practitioner license and a DEA registration. There is not a separate state controlled substance license needed for practitioners in New York State."',
 'https://www.health.ny.gov/professionals/narcotic/licensing_and_certification/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('NY','APRN','supervision_required', null, null, false, null,
 'NYSED Office of the Professions, Practice Requirements for Nurse Practitioners: "New York State Education Law holds nurse practitioners (NPs) independently responsible for the diagnosis and treatment of their patients and does not require an NP to practice under physician supervision." (Education Law sec. 6902.) A written collaborative practice agreement is a separate requirement -- see collaborative_agreement_required.',
 'https://www.op.nysed.gov/professions/nurse-practitioners/professional-practice/practice-requirements',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true),

('NY','APRN','collaborative_agreement_required', null, null, null,
 '{"required": true, "until_practice_hours": 3600, "after_threshold": "no written practice agreement required", "instrument": "written practice protocols plus a written practice agreement with a collaborating physician"}'::jsonb,
 'Education Law sec. 6902, as published by NYSED Office of the Professions, Practice Requirements for Nurse Practitioners: NPs must "practice in accordance with written practice protocols and a written practice agreement with a collaborating physician unless and until the NP has completed 3,600 hours of experience"; thereafter "the NP may practice independently". Conditional on an hours threshold, so a plain boolean would be wrong for a large share of the population -- hence value_json.',
 'https://www.op.nysed.gov/professions/nurse-practitioners/professional-practice/practice-requirements',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent', 1, true);

commit;
