-- =============================================================================
-- requirements_seed_group_d.sql -- the rules asset, western states (group D).
--
-- AZ, WA, OR, CO, UT, NV, NM, ID, WY, AK, HI x { physician (MD),
-- nurse practitioner (APRN) }.
--
-- VERIFICATION STANDARD (read db/seeds/README.md before editing):
--   Every row below carries a citation to a state board page, a state statute,
--   or a board rule that was FETCHED AND READ on 2026-09-18. No row is written
--   from recall, from a CE aggregator, or from inference. Nothing is carried
--   across from a neighbouring state -- this group is mostly full-practice-
--   authority NP territory and the regional pattern was NOT assumed; each
--   state was read on its own. Where a value could not be verified from a
--   primary source it is NOT in this file -- it is in
--   requirement_conflicts_seed_group_d.sql as an open conflict. An open
--   conflict blocks auto-clear (PRD 8.1 condition 6) and raises RULE_UNCERTAIN
--   (PRD 8.3), which is the correct behaviour for a value we do not know.
--
-- VALUE COLUMN CONVENTION
--   value_num   a plain per-cycle quantity (months, days, hours, cents).
--   value_bool  a plain yes/no.
--   value_json  a quantity that is NOT simply "this much, every cycle" --
--               one-time requirements, requirements on a different clock than
--               the renewal cycle, and requirements that apply only to a subset
--               of licensees. Recording a one-time 6-hour suicide prevention
--               course as a per-cycle 6 would generate a wrong obligation every
--               two years, so those carry {"hours": n, "periodicity": ...}.
--               Consumers MUST branch on the presence of value_json.
--
--   A NOTE ON CE CYCLES IN THIS GROUP. Several boards state CE per YEAR while
--   renewing on a multi-year clock (OR/MD 30 hours/year on a 24-month renewal;
--   AK/MD 25 hours/year on a 24-month renewal), and Washington states CE per
--   FOUR years while renewing every two. Those are seeded with ce_cycle_months
--   set to the board's own stated CE period, NOT to the renewal period, and
--   ce_hours_total set to the board's own stated number. No multiplication was
--   performed: 30 hours/year is seeded as 30 / 12 months, not as 60 / 24.
--   ce_cycle_months != renewal_cycle_months is a real and common condition here.
--
--   license_type 'MD' and 'APRN' match the vocabulary in 0003_credentials.sql.
--   DO IS NOT COVERED -- see the cross-cutting conflict row.
--
-- FIELD KEYS INTRODUCED BY THIS FILE (not in the CA/FL/TX/NY vocabulary):
--   ce_topic_suicide_prevention_hours   (WA MD+APRN, NV MD+APRN)
--   ce_topic_health_equity_hours        (WA MD+APRN)
--   ce_topic_cultural_competency_hours  (OR MD+APRN, NV APRN)
--   ce_topic_sbirt_hours                (NV MD+APRN)
--   ce_topic_bioterrorism_hours         (NV APRN)
--   None of these map onto an existing topic name without misstating the
--   mandate: Washington's "health equity" is a statutorily named subject
--   distinct from implicit bias, Oregon's "cultural competency" is its own
--   OAR-defined category, and suicide prevention / SBIRT / bioterrorism have
--   no analogue in the existing list.
--
-- Fees are in cents and are the amount the licensee actually pays where the
-- board publishes a single total; component breakdowns are in the citation.
--
-- Idempotent: safe to re-run. Respects ux_requirements_current (one is_current
-- row per state/license_type/field_key). Scoped to this group's states only, so
-- it does not disturb rows owned by the other seed files.
-- =============================================================================

begin;

-- Re-running replaces only the rows this file owns. requirement_conflicts rows
-- written by requirement_conflicts_seed_group_d.sql point at these rows, so they
-- are cleared first; re-run that file AFTER this one.
delete from requirement_conflicts
 where observed_by = 'research-agent-group-d'
   and requirement_id in (
         select id from requirements
          where verified_by = 'research-agent-group-d'
            and state in ('AZ','WA','OR','CO','UT','NV','NM','ID','WY','AK','HI')
            and license_type in ('MD','APRN'));

delete from requirements
 where verified_by = 'research-agent-group-d'
   and state in ('AZ','WA','OR','CO','UT','NV','NM','ID','WY','AK','HI')
   and license_type in ('MD','APRN');

insert into requirements
  (state, license_type, field_key,
   value_text, value_num, value_bool, value_json,
   citation, citation_url, effective_date,
   verified_at, verified_by, version, is_current)
values

-- =============================================================================
-- ARIZONA -- allopathic physician (MD)
-- Arizona Medical Board. A.R.S. Title 32 ch. 13; A.A.C. Title 4 ch. 16.
-- =============================================================================
('AZ','MD','renewal_cycle_months', null, 24, null, null,
 'A.R.S. sec. 32-1430(A), Arizona State Legislature: "each person holding an active license to practice medicine in this state shall renew the license every other year on or before the licensee''s birthday and shall pay the fee required". The Arizona Medical Board MD renewal page states the same: "every other year on or before the licensee''s birthday".',
 'https://www.azleg.gov/ars/32/01430.htm',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('AZ','MD','ce_hours_total', null, 40, null, null,
 'Arizona Medical Board, MD Renewal Application: a licensee must complete "at least 40 hours of CME" per renewal cycle, a total that includes "the hour of CME required under R4-16-102(A)(1)".',
 'https://azmd.gov/Licensure/Licensure/md-renewal-application',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('AZ','MD','ce_cycle_months', null, 24, null, null,
 'Arizona Medical Board, MD Renewal Application: the 40-hour CME requirement is stated per renewal cycle, and A.R.S. sec. 32-1430(A) makes the renewal cycle two years ("every other year on or before the licensee''s birthday"). CE cycle equals the renewal cycle.',
 'https://azmd.gov/Licensure/Licensure/md-renewal-application',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('AZ','MD','ce_topic_opioid_hours', null, null, null,
 '{"hours": 3, "periodicity": "per_renewal_cycle", "applies_to": "a licensee who is authorized to prescribe Schedule II controlled substances and holds a DEA registration number, or who is authorized to dispense controlled substances", "subjects_any_of": ["opioid-related", "substance use disorder-related", "addiction-related"]}'::jsonb,
 'A.R.S. sec. 32-3248.02, Arizona State Legislature: a health professional who is authorized to prescribe Schedule II controlled substances and holds a DEA registration number, or who is authorized to dispense controlled substances, must complete "a minimum of three hours of opioid-related, substance use disorder-related or addiction-related continuing education" during "each license renewal cycle". Conditional on prescribing/dispensing authority, hence value_json.',
 'https://www.azleg.gov/ars/32/03248-02.htm',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('AZ','MD','renewal_fee_cents', null, 50000, null, null,
 'Arizona Medical Board, MD Renewal Application: "$500.00" for the two-year renewal period.',
 'https://azmd.gov/Licensure/Licensure/md-renewal-application',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

-- =============================================================================
-- ARIZONA -- nurse practitioner (APRN)
-- Arizona State Board of Nursing. A.R.S. Title 32 ch. 15; A.A.C. Title 4 ch. 19.
-- An Arizona RNP holds an RN licence plus an NP certificate.
-- =============================================================================
('AZ','APRN','renewal_cycle_months', null, 48, null, null,
 'Arizona State Board of Nursing, Renew your License: registered nurses are "required to renew their licenses by April 1, every 4 years". SUBJECT TO AN OPEN CONFLICT: the Board also states the APRN certification "expires when the RN license or national certification expires, whichever comes first", so the effective APRN cycle can be shorter than 48 months -- see requirement_conflicts.',
 'https://azbn.gov/licenses-and-certifications/renew-your-license',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('AZ','APRN','renewal_window_days', null, 180, null, null,
 'Arizona State Board of Nursing, Renew your License: a renewal application may be submitted "up to 6 months before the renewal due date or within the 30 days following the due date". Six months recorded as 180 days, following the convention used for CA/APRN.',
 'https://azbn.gov/licenses-and-certifications/renew-your-license',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('AZ','APRN','ce_topic_opioid_hours', null, null, null,
 '{"hours": 3, "periodicity": "per_renewal_cycle", "applies_to": "APRN holding an active DEA registration", "subjects_any_of": ["opioid-related", "substance use disorder-related", "addiction-related"]}'::jsonb,
 'Arizona State Board of Nursing, Renew your License: APRNs holding active DEA licences must complete "a minimum of three hours of opioid-related, substance use disorder-related or addiction-related continuing education" (the A.R.S. sec. 32-3248.02 requirement as applied to nursing). Conditional on DEA registration, hence value_json.',
 'https://azbn.gov/licenses-and-certifications/renew-your-license',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('AZ','APRN','initial_license_fee_cents', null, 15000, null, null,
 'Arizona State Board of Nursing, Agency Fees: Initial Certifications -- "Nurse Practitioner (NP) $150". The underlying RN licence is a separate fee ("RN/LPN Exam and Licensure $300", "RN/LPN Endorsement $150"), and a prescribing/dispensing authority certificate is a further $150.',
 'https://azbn.gov/licenses-and-certifications/agency-fees',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('AZ','APRN','supervision_required', null, null, false, null,
 'Arizona State Board of Nursing, Scope of Practice -- APRN FAQs: "Arizona does not require physician supervision or collaboration for the independent practice of nurse practitioners (regardless of specialty)." The Board adds that an RNP must "consult with or refer clients to other health care providers when appropriate", and that an employing institution may impose its own policies.',
 'https://azbn.gov/sites/default/files/SOP-APRN-FAQs.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('AZ','APRN','collaborative_agreement_required', null, null, false, null,
 'Arizona State Board of Nursing, Scope of Practice -- APRN FAQs: "Arizona does not require physician supervision or collaboration for the independent practice of nurse practitioners (regardless of specialty)." No collaborative practice agreement instrument is required by the Board.',
 'https://azbn.gov/sites/default/files/SOP-APRN-FAQs.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

-- =============================================================================
-- WASHINGTON -- physician and surgeon (MD)
-- Washington Medical Commission. RCW 18.71; WAC 246-919 and 246-12.
-- NOTE: WA renews every 2 years but runs CE on a 4-year clock. These are
-- DIFFERENT CLOCKS and both are seeded.
-- =============================================================================
('WA','MD','renewal_cycle_months', null, 24, null, null,
 'WAC 246-919-421, as published by the Washington State Legislature: "A licensed physician shall renew his or her license every two years in compliance with WAC 246-12-030." The Washington Medical Commission fee schedule confirms a "Two-year renewal".',
 'https://app.leg.wa.gov/wac/default.aspx?cite=246-919&full=true',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('WA','MD','renewal_window_days', null, 90, null, null,
 'Washington Medical Commission, Renewals: "Your credential may be renewed up to 90 days before it expires." Courtesy renewal notices are emailed at the same 90-day point.',
 'https://wmc.wa.gov/licensing/renewals',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('WA','MD','ce_hours_total', null, 200, null, null,
 'WAC 246-919-430 and WAC 246-919-460, as published by the Washington State Legislature: a physician must complete "two hundred hours of continuing education every four years", of which all 200 may be Category I (accredited) and no more than 80 may come from any single non-accredited category. Washington Medical Commission publication DOH 657-128 states the same: "two hundred hours of continuing education every four years".',
 'https://app.leg.wa.gov/wac/default.aspx?cite=246-919&full=true',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('WA','MD','ce_cycle_months', null, 48, null, null,
 'WAC 246-919-430: the 200-hour requirement runs over a FOUR-year continuing education reporting period, while WAC 246-919-421 makes the licence renewal cycle TWO years. The CE cycle is deliberately not the renewal cycle in Washington; a consumer that anchors CE to renewal_cycle_months will double the obligation.',
 'https://app.leg.wa.gov/wac/default.aspx?cite=246-919&full=true',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('WA','MD','ce_topic_suicide_prevention_hours', null, null, null,
 '{"hours": 6, "periodicity": "one_time", "subjects": ["suicide assessment", "treatment and management", "imminent harm via lethal means or self-injurious behaviors", "content on veterans"]}'::jsonb,
 'WAC 246-919-435 (RCW 43.70.442), as published by the Washington State Legislature: a one-time "training in suicide assessment, treatment, and management" that is "at least six hours in length". The Department of Health training-requirements table lists physicians as "Six hours one time". ONE-TIME, not per cycle.',
 'https://doh.wa.gov/public-health-provider-resources/healthcare-professions-and-facilities/suicide-prevention/training-requirements',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('WA','MD','ce_topic_health_equity_hours', null, null, null,
 '{"hours": 2, "periodicity": "every_4_years"}'::jsonb,
 'WAC 246-919-445 and WAC 246-12-820 (RCW 43.70.613), as published by the Washington State Legislature: physicians must complete "two hours of health equity continuing education training every four years"; the general rule states "Health care professionals must complete a minimum of two hours in health equity continuing education training every four years, unless the relevant rule-making authority specifies a higher number of hours in rule." Four years is NOT the 24-month renewal cycle, hence value_json.',
 'https://app.leg.wa.gov/wac/default.aspx?cite=246-12-820',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('WA','MD','ce_topic_opioid_hours', null, null, null,
 '{"hours": 1, "periodicity": "one_time", "window": "by the end of the physician''s first full continuing education reporting period after January 1, 2019, or the first full reporting period after initial licensure, whichever is later"}'::jsonb,
 'WAC 246-919-875, as published by the Washington State Legislature: a one-time continuing education requirement on best practices in opioid prescribing or the associated rules, "at least one hour in length", due "by the end of the physician''s first full continuing education reporting period after January 1, 2019, or during the first full continuing education reporting period after initial licensure, whichever is later". ONE-TIME, not per cycle.',
 'https://app.leg.wa.gov/WAC/default.aspx?cite=246-919-875&pdf=true',
 '2019-01-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('WA','MD','initial_license_fee_cents', null, 51100, null, null,
 'Washington Medical Commission, Fees: Physician and Surgeon (MD) "Application Fee: $511".',
 'https://wmc.wa.gov/licensing/fees',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('WA','MD','renewal_fee_cents', null, 99600, null, null,
 'Washington Medical Commission, Fees: Physician and Surgeon (MD) "Two-year renewal" "$996".',
 'https://wmc.wa.gov/licensing/fees',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

-- =============================================================================
-- WASHINGTON -- advanced registered nurse practitioner (ARNP)
-- Washington State Board of Nursing (NCQAC). RCW 18.79; WAC 246-840, 246-12.
-- A WA ARNP holds an RN licence (renewed ANNUALLY) plus an ARNP licence
-- (renewed BIENNIALLY). The APRN rows below are the ARNP licence.
-- =============================================================================
('WA','APRN','renewal_cycle_months', null, 24, null, null,
 'Washington State Board of Nursing, Renew or Reactivate a License: "All ARNPs in Washington state must renew their license every other year, by their birthday, to remain in active status." The underlying RN licence is on a separate ANNUAL clock: "All registered nurses in Washington state must renew annually by their birthday to remain active."',
 'https://nursing.wa.gov/licensing/renew-or-reactivate-license',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('WA','APRN','ce_hours_total', null, 30, null, null,
 'Washington State Board of Nursing, Renew or Reactivate a License: an ARNP must complete "30 contact hours of continuing education credit during the renewal period".',
 'https://nursing.wa.gov/licensing/renew-or-reactivate-license',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('WA','APRN','ce_cycle_months', null, 24, null, null,
 'Washington State Board of Nursing, Renew or Reactivate a License: the 30 contact hours are required "during the renewal period", and the ARNP renewal period is "every other year". CE cycle equals the ARNP renewal cycle.',
 'https://nursing.wa.gov/licensing/renew-or-reactivate-license',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('WA','APRN','ce_topic_pharmacotherapeutics_hours', null, null, null,
 '{"hours": 15, "periodicity": "per_renewal_cycle", "applies_to": "ARNP with prescriptive authority", "in_addition_to_ce_hours_total": true}'::jsonb,
 'Washington State Board of Nursing, Renew or Reactivate a License: beyond the 30 contact hours, "an additional 15 hours in pharmacology is required if you have prescriptive authority within the last two years". Conditional on prescriptive authority, hence value_json.',
 'https://nursing.wa.gov/licensing/renew-or-reactivate-license',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('WA','APRN','ce_topic_suicide_prevention_hours', null, null, null,
 '{"hours": 6, "periodicity": "one_time", "subjects": ["suicide assessment", "treatment and management", "imminent harm via lethal means or self-injurious behaviors", "content on veterans"]}'::jsonb,
 'Washington State Department of Health, Suicide Prevention Training for Health Professionals -- Training Requirements (RCW 43.70.442): advanced registered nurse practitioners are listed at "Six hours one time", with the same core content as physicians. ONE-TIME, not per cycle.',
 'https://doh.wa.gov/public-health-provider-resources/healthcare-professions-and-facilities/suicide-prevention/training-requirements',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('WA','APRN','ce_topic_health_equity_hours', null, null, null,
 '{"hours": 2, "periodicity": "every_4_years"}'::jsonb,
 'WAC 246-12-820 (RCW 43.70.613), as published by the Washington State Legislature: "Health care professionals must complete a minimum of two hours in health equity continuing education training every four years, unless the relevant rule-making authority specifies a higher number of hours in rule." Four years is NOT the 24-month ARNP renewal cycle, hence value_json.',
 'https://app.leg.wa.gov/wac/default.aspx?cite=246-12-820',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('WA','APRN','initial_license_fee_cents', null, 13000, null, null,
 'Washington State Board of Nursing, Nurse License Fees: ARNP "Application (Initial): $130". The underlying RN licence is a separate $138 (single-state), which includes the legislatively mandated $16 HEAL WA and $8 WCN surcharges.',
 'https://nursing.wa.gov/licensing/nurse-license-fees',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('WA','APRN','renewal_fee_cents', null, 13000, null, null,
 'Washington State Board of Nursing, Nurse License Fees: ARNP "Renewal: $130". The underlying RN licence renewal is a separate $138 per year (single-state).',
 'https://nursing.wa.gov/licensing/nurse-license-fees',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

-- =============================================================================
-- OREGON -- physician (MD)
-- Oregon Medical Board. ORS ch. 677; OAR ch. 847.
-- NOTE: OMB states CME per YEAR while registering biennially. Seeded as the
-- Board states it: 30 hours per 12 months, NOT 60 per 24.
-- =============================================================================
('OR','MD','renewal_cycle_months', null, 24, null, null,
 'Oregon Medical Board, Licensee Renewal Fees (effective 7/2/2026): the fee table is headed "MEDICAL DOCTOR (MD)/DOCTOR OF OSTEOPATHIC MEDICINE (DO) -- TWO-YEAR REGISTRATION PERIOD". The Board''s Renew a License page likewise describes the current registration period as 2026-2028.',
 'https://www.oregon.gov/omb/licensing/Documents/all-fees.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('OR','MD','ce_hours_total', null, 30, null, null,
 'Oregon Medical Board, Continuing Education (OAR 847-008-0070): "30 hours/year" for a Physician (Medical, Osteopathic, Podiatric) in Active status; 15 hours/year in Emeritus status. The Board states the requirement PER YEAR, so 30 is seeded against a 12-month ce_cycle_months rather than multiplied out to a 60-hour biennial figure the Board does not publish.',
 'https://www.oregon.gov/omb/topics-of-interest/pages/continuing-education.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('OR','MD','ce_cycle_months', null, 12, null, null,
 'Oregon Medical Board, Continuing Education (OAR 847-008-0070): the general CME requirement is expressed as "30 hours/year". The CE clock is annual while the registration clock is two years; the two are not the same and are seeded separately.',
 'https://www.oregon.gov/omb/topics-of-interest/pages/continuing-education.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('OR','MD','ce_topic_pain_management_hours', null, null, null,
 '{"hours": 1, "periodicity": "every_2_years", "instrument": "Oregon Pain Management Commission continuing education course"}'::jsonb,
 'Oregon Medical Board, Continuing Education (OAR 847-008-0075): Pain Management -- "1 hour every two years", satisfied by the Oregon Pain Management Commission''s free online course. The two-year topic clock is NOT the 12-month general CE clock seeded above, hence value_json.',
 'https://www.oregon.gov/omb/topics-of-interest/pages/continuing-education.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('OR','MD','ce_topic_cultural_competency_hours', null, null, null,
 '{"hours": 1, "periodicity": "annual_average_over_audit_period", "audit_period": "two renewal cycles", "note": "hours may be completed at any time during the audit period; total obligation scales with years licensed"}'::jsonb,
 'Oregon Medical Board, Continuing Education (OAR 847-008-0077): Cultural Competency -- "1 hour every year", which the Board explains is "an average of one hour yearly during each audit period (typically two renewal cycles)"; licensees may complete the hours at any time during the audit period. An averaged obligation over a four-year audit period is not a fixed per-cycle number, hence value_json.',
 'https://www.oregon.gov/omb/topics-of-interest/pages/continuing-education.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('OR','MD','initial_license_fee_cents', null, 37500, null, null,
 'OAR 847-005-0005 (Oregon Medical Board fee schedule), as published by the Board: "Initial License Application -- $375."',
 'https://www.oregon.gov/omb/statutesrules/Documents/847-005-0005.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('OR','MD','renewal_fee_cents', null, 75600, null, null,
 'Oregon Medical Board, Licensee Renewal Fees (effective 7/2/2026): MD/DO two-year registration period, "Total to Renew License $756", comprising License Registration $608, HPSP Fee $50, OHSU Library $20, Prescription Monitoring $70 and OHA Workforce Database $8. SUBJECT TO AN OPEN CONFLICT: OAR 847-005-0005 states the registration fee as "$314/year" ($628 per biennium), which does not reconcile with the published $608 -- see requirement_conflicts.',
 'https://www.oregon.gov/omb/licensing/Documents/all-fees.pdf',
 '2026-07-02', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

-- =============================================================================
-- OREGON -- nurse practitioner (APRN)
-- Oregon State Board of Nursing. ORS ch. 678; OAR ch. 851.
-- OSBN replaced practice-hour competency with a CE model on 2026-01-01.
-- =============================================================================
('OR','APRN','renewal_cycle_months', null, 24, null, null,
 'Oregon Secretary of State, Business Xpress License Directory entry for "Nurse Practitioners" (issuing agency: Oregon State Board of Nursing), last updated 05/12/2026: "License Renewal Period: 2 years". NOTE: this is a State of Oregon licence directory record rather than an OSBN page; the OSBN renewal page itself 404s. See requirement_conflicts.',
 'https://apps.oregon.gov/SOS/LicenseDirectory/LicenseDetail/230',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('OR','APRN','ce_topic_pain_management_hours', null, null, null,
 '{"hours": 1, "periodicity": "every_36_months", "instrument": "Oregon Pain Management Commission module"}'::jsonb,
 'Oregon State Board of Nursing, Continuing Education Requirements fact sheet (effective January 1, 2026), applying to LPN, RN and APRN renewal applicants: "One-hour pain management education in the last 36 months". A 36-month clock is not the 24-month renewal cycle, hence value_json.',
 'https://www.oregon.gov/osbn/Documents/Resource_Renewal-CE_Fact_Sheet12-31-25.pdf',
 '2026-01-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('OR','APRN','ce_topic_cultural_competency_hours', null, null, null,
 '{"hours": 2, "periodicity": "every_48_months"}'::jsonb,
 'Oregon State Board of Nursing, Continuing Education Requirements fact sheet (effective January 1, 2026), applying to LPN, RN and APRN renewal applicants: "Two hours of cultural competency education in the past 48 months". A 48-month clock is not the 24-month renewal cycle, hence value_json.',
 'https://www.oregon.gov/osbn/Documents/Resource_Renewal-CE_Fact_Sheet12-31-25.pdf',
 '2026-01-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

-- =============================================================================
-- COLORADO -- physician (MD)
-- Colorado Medical Board, DORA Division of Professions and Occupations.
-- C.R.S. Title 12 art. 240; 3 CCR 713-1.
-- =============================================================================
('CO','MD','renewal_cycle_months', null, 24, null, null,
 'Colorado Medical Board, Physician Licensing Requirements: "All physician licenses expire on April 30 of odd-numbered years." The Board''s CME page states the same period from the other side: "during each two-year license period".',
 'https://dpo.colorado.gov/Medical/DRLicenseRequirements',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('CO','MD','ce_hours_total', null, 30, null, null,
 'Colorado Medical Board, Colorado Physician CME: "All Physicians and Compact Physicians with an Active Colorado license must complete at least 30 hours of Continuing Medical Education (CME) during each two-year license period." Physicians licensed for less than 24 months before expiration have a prorated requirement of 5 to 22 hours. The Board states "Physicians have discretion to self-select the topics for their CME requirements" -- there are no mandated subjects.',
 'https://dpo.colorado.gov/Medical/CME',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('CO','MD','ce_cycle_months', null, 24, null, null,
 'Colorado Medical Board, Colorado Physician CME: the 30 hours are required "during each two-year license period", i.e. the CE cycle is the renewal cycle.',
 'https://dpo.colorado.gov/Medical/CME',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

-- =============================================================================
-- COLORADO -- advanced practice registered nurse (APRN)
-- Colorado State Board of Nursing, DORA. C.R.S. Title 12 art. 255; 3 CCR 716-1.
-- Colorado distinguishes the APN licence from RXN prescriptive authority.
-- =============================================================================
('CO','APRN','ce_hours_total', null, 0, null, null,
 'Colorado State Board of Nursing, Nursing FAQs: "Continuing education hours are not currently required in order to renew a Registered Nurse, Practical Nurse, Nurse Aide Certification, or Psychiatric Technician license in Colorado." For advanced practice specifically: "There are no additional continuing education requirements other than what is required to maintain professional certification." This is an AFFIRMATIVE board statement of no state CE hour requirement, not an absence of information -- 0 is therefore seeded. SUBJECT TO AN OPEN CONFLICT on the national-certification caveat; see requirement_conflicts.',
 'https://dpo.colorado.gov/Nursing/FAQ',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('CO','APRN','collaborative_agreement_required', null, null, null,
 '{"required": true, "applies_to": "APRN seeking full prescriptive authority (RXN)", "instrument": "750-hour mentorship documented in writing with a physician mentor", "mentorship_hours": 750, "window": "completed within 3 years of Provisional Prescriptive Authority (RXN-P) being granted", "after_threshold": "full RXN prescriptive authority; no continuing mentorship instrument stated", "not_verified": "whether an APN without prescriptive authority needs any collaboration instrument"}'::jsonb,
 'Colorado State Board of Nursing, Nursing homepage -- Advanced Practice: an Advanced Practice Nurse seeking prescriptive authority (RXN) must "Have national certification", "Hold a graduate or post-graduate nursing degree" and "Complete an 750-hour mentorship", the mentorship being "Completed within 3 years of Provisional Prescriptive Authority (RXN-P) being granted" and documented in writing with a physician mentor. This is a TRANSITION-TO-PRACTICE threshold, not a standing collaborative agreement, and it does not apply to an APN who does not prescribe -- a bare boolean would misstate it for both populations, hence value_json.',
 'https://dpo.colorado.gov/Nursing',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

-- =============================================================================
-- UTAH -- physician and surgeon (MD)
-- Utah Division of Professional Licensing (DOPL). Utah Code 58-67; R156-67.
-- Utah DOES issue a state Controlled Substance Licence.
-- =============================================================================
('UT','MD','renewal_cycle_months', null, 24, null, null,
 'Utah DOPL, Renew a Physician and Surgeon License: "Physician licenses expire on January 31 of even years." The Division''s Renewal Cycle Schedule and Fees table lists Physician and Surgeon as "$193 | 01/31/EVEN", and the Division''s renewal form refers to "each two-year licensure cycle".',
 'https://commerce.utah.gov/dopl/renewal-guide/renewal-cycle-schedule-and-fees/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('UT','MD','ce_hours_total', null, 40, null, null,
 'Utah DOPL, Physician and Surgeon Renewal/Reinstatement Form (R156-67-304): "at least 40 hours of CME are required during each two-year licensure cycle, of which at least 34 hours need to be ACCME category 1 offerings."',
 'http://commerce.utah.gov//wp-content/uploads/2022/08/physician-and-surgeon-renewal.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('UT','MD','ce_cycle_months', null, 24, null, null,
 'Utah DOPL, Physician and Surgeon Renewal/Reinstatement Form (R156-67-304): the 40 hours are required "during each two-year licensure cycle", i.e. the CE cycle is the renewal cycle.',
 'http://commerce.utah.gov//wp-content/uploads/2022/08/physician-and-surgeon-renewal.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('UT','MD','ce_topic_controlled_substance_hours', null, null, null,
 '{"hours": 3.5, "periodicity": "per_licensing_period", "applies_to": "controlled substance prescribers (holders of a Utah Controlled Substance Licence)", "note": "the 3.5-hour SBIRT training, required from 2024-01-01, satisfies this for the licensing period in which it is completed and is itself only required once"}'::jsonb,
 'Utah Department of Commerce, Controlled Substance Toolkit -- License Education Requirements (Utah Code 58-37-6.5): "A controlled substance prescriber shall complete at least 3.5 hours of continuing education in one or more controlled substance prescribing classes, except dentists who shall complete at least two hours." The page adds that "SBIRT training is required (3.5 hours), starting January 1, 2024, which fulfills the licensing requirements for CE for the licensing period it was completed in and is only required to take it one time." Conditional on holding a controlled substance licence, hence value_json.',
 'https://commerce.utah.gov/cs-toolkit/prescriber-education/license-education-requirements/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('UT','MD','csr_required', null, null, true, null,
 'Utah DOPL, Renew a Controlled Substance License: Utah issues a state Controlled Substance Licence separate from the federal DEA registration, and "The Controlled Substance licese [sic] is renewed as part of the associated practitioner license renewal (dentist, physician, etc.)". The Division''s fee schedule lists Controlled Substance as its own licence line with its own application and renewal fees.',
 'https://commerce.utah.gov/dopl/controlled-substance/renew-a-license/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('UT','MD','csr_renewal_cycle_months', null, 24, null, null,
 'Utah DOPL, Renew a Controlled Substance License: "The Controlled Substance licese [sic] is renewed as part of the associated practitioner license renewal", and the associated Physician and Surgeon licence renews on a two-year cycle expiring January 31 of even years. The CSL therefore shares the 24-month practitioner cycle.',
 'https://commerce.utah.gov/dopl/controlled-substance/renew-a-license/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('UT','MD','csr_fee_cents', null, 7800, null, null,
 'Utah DOPL, Division of Professional Licensing Fees (FY 2025-2026): Controlled Substance -- Application $100.00, Renewal $78.00. The renewal figure is seeded.',
 'https://commerce.utah.gov/wp-content/uploads/2022/11/fee-schedule.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('UT','MD','initial_license_fee_cents', null, 20000, null, null,
 'Utah DOPL, Division of Professional Licensing Fees (FY 2025-2026): Physician and Surgeon -- Application "$200.00".',
 'https://commerce.utah.gov/wp-content/uploads/2022/11/fee-schedule.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('UT','MD','renewal_fee_cents', null, 19300, null, null,
 'Utah DOPL, Division of Professional Licensing Fees (FY 2025-2026): Physician and Surgeon -- Renewal "$193.00". The Division''s Renewal Cycle Schedule and Fees table lists the same figure against the 01/31/EVEN cycle.',
 'https://commerce.utah.gov/wp-content/uploads/2022/11/fee-schedule.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

-- =============================================================================
-- UTAH -- advanced practice registered nurse (APRN)
-- Utah DOPL, Board of Nursing. Utah Code 58-31b; R156-31b.
-- =============================================================================
('UT','APRN','renewal_cycle_months', null, 24, null, null,
 'Utah DOPL, Renewal Cycle Schedule and Fees: "Advanced Practice Registered Nurse: $78 | 01/31/EVEN". The Division''s APRN renewal form states the renewal period as "January 31st of even years" and refers to "the two-year renewal period". (The underlying RN licence renews on a different clock: "Registered Nurse: $68 | 01/31/ODD".)',
 'https://commerce.utah.gov/dopl/renewal-guide/renewal-cycle-schedule-and-fees/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('UT','APRN','ce_hours_total', null, null, null,
 '{"hours": 30, "periodicity": "per_renewal_cycle", "applies_to": "APRNs licensed before July 1, 1992, who do not hold current national certification", "also_requires": {"licensed_practice_hours": 400}, "default_pathway": "current certification in the practice specialty under R156-31b-303(3)(b)"}'::jsonb,
 'Utah DOPL, APRN with Controlled Substance Renewal/Reinstatement Form: "In accordance with Subsection R156-31b-303(3)(b), you must have a current certification in your practice specialty. APRNs licensed before July 1, 1992, must complete 30 hours of approved CME and 400 hours of licensed practice during the two-year renewal period." The 30-hour figure applies ONLY to the pre-1992 cohort; the default pathway is national certification. Seeding a bare 30 would invoice every Utah APRN a duty most of them do not have, hence value_json.',
 'http://commerce.utah.gov//wp-content/uploads/2022/10/aprn-with-controlled-substance-renewal.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('UT','APRN','ce_topic_controlled_substance_hours', null, null, null,
 '{"hours": 3.5, "periodicity": "per_licensing_period", "applies_to": "APRN holding a Utah Controlled Substance Licence"}'::jsonb,
 'Utah DOPL, APRN with Controlled Substance Renewal/Reinstatement Form: "Controlled Substance prescribers must complete at least 3.5 hours of continuing education in classes approved by the Division." The Department of Commerce Controlled Substance Toolkit states the same requirement under Utah Code 58-37-6.5. Conditional on holding a controlled substance licence, hence value_json.',
 'http://commerce.utah.gov//wp-content/uploads/2022/10/aprn-with-controlled-substance-renewal.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('UT','APRN','csr_required', null, null, true, null,
 'Utah DOPL, Renew a Controlled Substance License: Utah issues a state Controlled Substance Licence separate from the federal DEA registration, renewed "as part of the associated practitioner license renewal". The Division''s APRN renewal form is issued as a combined "APRN with Controlled Substance" renewal, and the fee schedule carries a Controlled Substance licence line.',
 'https://commerce.utah.gov/dopl/controlled-substance/renew-a-license/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('UT','APRN','csr_renewal_cycle_months', null, 24, null, null,
 'Utah DOPL, Renew a Controlled Substance License: the CSL "is renewed as part of the associated practitioner license renewal", and the associated APRN licence renews on the 01/31/EVEN two-year cycle.',
 'https://commerce.utah.gov/dopl/controlled-substance/renew-a-license/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('UT','APRN','csr_fee_cents', null, 7800, null, null,
 'Utah DOPL, Division of Professional Licensing Fees (FY 2025-2026): Controlled Substance -- Renewal "$78.00". The Division''s APRN renewal form confirms the licensee pays "$78.00" for the APRN licence plus a further "$78.00" for Controlled Substance, $156.00 in total, where both are held.',
 'https://commerce.utah.gov/wp-content/uploads/2022/11/fee-schedule.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('UT','APRN','initial_license_fee_cents', null, 10000, null, null,
 'Utah DOPL, Division of Professional Licensing Fees (FY 2025-2026): Advanced Practice Registered Nurse -- Application "$100.00".',
 'https://commerce.utah.gov/wp-content/uploads/2022/11/fee-schedule.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('UT','APRN','renewal_fee_cents', null, 7800, null, null,
 'Utah DOPL, Division of Professional Licensing Fees (FY 2025-2026): Advanced Practice Registered Nurse -- Renewal "$78.00". The Renewal Cycle Schedule and Fees table lists the same figure against the 01/31/EVEN cycle.',
 'https://commerce.utah.gov/wp-content/uploads/2022/11/fee-schedule.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

-- =============================================================================
-- NEVADA -- physician (MD)
-- Nevada State Board of Medical Examiners. NRS ch. 630; NAC ch. 630.
-- =============================================================================
('NV','MD','renewal_cycle_months', null, 24, null, null,
 'Nevada State Board of Medical Examiners, Licensure Fees: the M.D. fee table is built on a "Registration Fee Full-Biennium" and a "Registration Fee 2nd Half of Biennium", and the Board''s CME Requirements for MDs, PAs, AAs states the CME obligation against a two-year cycle. NRS ch. 630 refers throughout to "biennial registration".',
 'https://medboard.nv.gov/uploadedFiles/medboardnvgov/content/Forms/Licensure%20Fees.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NV','MD','ce_hours_total', null, 40, null, null,
 'Nevada State Board of Medical Examiners, CME Requirements for MDs, PAs, AAs: "40" total CME hours per two-year cycle for licensees whose initial licensure was prior to 7/1/2025 or between 7/1/2025 and 12/31/2025, of which a minimum of 20 hours must be within the licensee''s scope of practice or specialty.',
 'https://medboard.nv.gov/uploadedFiles/mednvgov/content/Licensees/CME_Requirements_MDs_PAs_AAs.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NV','MD','ce_cycle_months', null, 24, null, null,
 'Nevada State Board of Medical Examiners, CME Requirements for MDs, PAs, AAs: the 40-hour requirement is stated against the biennial (2-year) registration cycle, i.e. the CE cycle is the renewal cycle.',
 'https://medboard.nv.gov/uploadedFiles/mednvgov/content/Licensees/CME_Requirements_MDs_PAs_AAs.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NV','MD','ce_topic_ethics_hours', null, null, null,
 '{"hours": 2, "periodicity": "per_renewal_cycle", "topics_any_of": ["ethics", "pain management", "addiction care"]}'::jsonb,
 'Nevada State Board of Medical Examiners, CME Requirements for MDs, PAs, AAs: "Minimum # of hours in Ethics, Pain Management, or Addiction Care" is "2" per cycle. The requirement is a DISJUNCTION of three subjects, any of which satisfies it, so it is not a pure ethics obligation and is recorded as value_json rather than a bare ethics hour count.',
 'https://medboard.nv.gov/uploadedFiles/mednvgov/content/Licensees/CME_Requirements_MDs_PAs_AAs.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NV','MD','ce_topic_controlled_substance_hours', null, null, null,
 '{"hours": 2, "periodicity": "per_renewal_cycle", "applies_to": "licensees registered to dispense controlled substances", "subjects_any_of": ["misuse and abuse of controlled substances", "prescribing of opioids", "addiction"]}'::jsonb,
 'Nevada State Board of Medical Examiners, CME Requirements for MDs, PAs, AAs: "2 hours in Misuse and Abuse of Controlled Substances; Prescribing of Opioids; or Addiction" per two-year cycle, if registered to dispense. Conditional on dispensing registration, hence value_json.',
 'https://medboard.nv.gov/uploadedFiles/mednvgov/content/Licensees/CME_Requirements_MDs_PAs_AAs.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NV','MD','ce_topic_suicide_prevention_hours', null, null, null,
 '{"hours": 2, "periodicity": "every_4_years", "first_due": "within 2 years of initial licensure"}'::jsonb,
 'Nevada State Board of Medical Examiners, CME Requirements for MDs, PAs, AAs: "2 hours: Suicide Detection, Intervention, and Prevention", due within 2 years of initial licensure and then "once every four years". A four-year clock is NOT the two-year registration cycle, hence value_json.',
 'https://medboard.nv.gov/uploadedFiles/mednvgov/content/Licensees/CME_Requirements_MDs_PAs_AAs.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NV','MD','ce_topic_sbirt_hours', null, null, null,
 '{"hours": 2, "periodicity": "one_time", "window": "within 2 years of initial licensure", "subject": "Screening, Brief Intervention, and Referral to Treatment (SBIRT)"}'::jsonb,
 'Nevada State Board of Medical Examiners, CME Requirements for MDs, PAs, AAs: "2 hours: Screening, Brief Intervention, and Referral to Treatment (SBIRT)", a one-time requirement due within 2 years of initial licensure. ONE-TIME, not per cycle.',
 'https://medboard.nv.gov/uploadedFiles/mednvgov/content/Licensees/CME_Requirements_MDs_PAs_AAs.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NV','MD','ce_topic_hiv_aids_hours', null, null, null,
 '{"hours": 2, "periodicity": "per_renewal_cycle", "applies_to": "licensees who provide or supervise the provision of emergency medical services", "subject": "stigma, discrimination and unrecognized bias toward persons who have acquired or are at high risk of acquiring HIV"}'::jsonb,
 'Nevada State Board of Medical Examiners, CME Requirements for MDs, PAs, AAs: "2 hours: Stigma, Discrimination and Unrecognized Bias Toward Persons Who Have Acquired or Are at High Risk of Acquiring Human Immunodeficiency Virus", required only of licensees providing or supervising emergency medical services. Conditional on practice setting, hence value_json.',
 'https://medboard.nv.gov/uploadedFiles/mednvgov/content/Licensees/CME_Requirements_MDs_PAs_AAs.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NV','MD','initial_license_fee_cents', null, 135000, null, null,
 'Nevada State Board of Medical Examiners, Licensure Fees: M.D. (Active) -- "Application Fee $600.00" plus "Registration Fee FullBiennium $750.00", $1,350.00 in total where the licence issues in the first half of the biennium. An applicant licensed in the second half pays the reduced "Registration Fee 2nd Half of Biennium $375.00" instead of $750.00.',
 'https://medboard.nv.gov/uploadedFiles/medboardnvgov/content/Forms/Licensure%20Fees.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NV','MD','renewal_fee_cents', null, 85000, null, null,
 'Nevada State Board of Medical Examiners, Licensure Fees: M.D. biennial renewal "$850.00".',
 'https://medboard.nv.gov/uploadedFiles/medboardnvgov/content/Forms/Licensure%20Fees.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

-- =============================================================================
-- NEVADA -- advanced practice registered nurse (APRN)
-- Nevada State Board of Nursing. NRS ch. 632; NAC ch. 632.
-- =============================================================================
('NV','APRN','renewal_cycle_months', null, 24, null, null,
 'NAC 632.192, as published by the Nevada Legislature: "An original license or certificate is valid for the period from the date of issuance to the licensee''s or certificate holder''s second birthday after issuance. Thereafter, each license or certificate will expire biennially on the licensee''s or certificate holder''s birthday."',
 'https://www.leg.state.nv.us/nac/nac-632.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NV','APRN','ce_hours_total', null, null, null,
 '{"hours": 45, "periodicity": "per_renewal_cycle", "composition": {"general_nursing": 30, "aprn_specialty_additional": 15}}'::jsonb,
 'Nevada State Board of Nursing, Continuing Education: the RN requirement is "30 hrs/renewal" per biennial cycle, and APRNs must take an "additional 15 hrs each renewal cycle" directly related to their specialties (the Board''s APRN Renewal FAQ states "APRNs to take an additional 15 CEs directly related to their specialties"). The 45-hour total is a SUM OF TWO SEPARATELY STATED REQUIREMENTS, not a figure the Board publishes as one number, so the components are carried in value_json rather than flattened.',
 'https://nevadanursingboard.org/continuing-education/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NV','APRN','ce_cycle_months', null, 24, null, null,
 'Nevada State Board of Nursing, Continuing Education: hours are counted "each renewal cycle", and NAC 632.192 makes the renewal cycle biennial. CE cycle equals the renewal cycle.',
 'https://nevadanursingboard.org/continuing-education/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NV','APRN','ce_topic_cultural_competency_hours', null, 4, null, null,
 'Nevada State Board of Nursing, Continuing Education: cultural competency -- "4 hours every renewal cycle", for RNs and APRNs alike. Per cycle, hence a plain hour count.',
 'https://nevadanursingboard.org/continuing-education/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NV','APRN','ce_topic_bioterrorism_hours', null, null, null,
 '{"hours": 4, "periodicity": "one_time"}'::jsonb,
 'Nevada State Board of Nursing, Continuing Education: bioterrorism -- "4 hours one-time", for RNs and APRNs alike. ONE-TIME, not per cycle.',
 'https://nevadanursingboard.org/continuing-education/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NV','APRN','ce_topic_suicide_prevention_hours', null, null, null,
 '{"hours": 2, "periodicity": "every_4_years"}'::jsonb,
 'Nevada State Board of Nursing, Continuing Education and APRN Renewal FAQs: "a 2-hour suicide prevention course completed every 4 years". A four-year clock is NOT the two-year renewal cycle, hence value_json.',
 'https://nevadanursingboard.org/wp-content/uploads/2020/06/APRN-Renewal-FAQ.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NV','APRN','ce_topic_sbirt_hours', null, 2, null, null,
 'Nevada State Board of Nursing, Continuing Education: SBIRT / substance use disorder -- "2 hours every renewal cycle" for APRNs; the Board''s APRN Renewal FAQ describes it as "a 2-hour substance use and abuse course completed every renewal cycle". Per cycle, hence a plain hour count.',
 'https://nevadanursingboard.org/continuing-education/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NV','APRN','ce_topic_opioid_hours', null, null, null,
 '{"hours": 2, "periodicity": "per_renewal_cycle", "applies_to": "APRNs registered to dispense controlled substances"}'::jsonb,
 'Nevada State Board of Nursing, Continuing Education: opioid training -- "2 hours every renewal cycle" for those registered to dispense controlled substances. Conditional on dispensing registration, hence value_json.',
 'https://nevadanursingboard.org/continuing-education/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NV','APRN','initial_license_fee_cents', null, 20000, null, null,
 'Nevada State Board of Nursing, Fee Schedule (1/2023): Initial Application Fees -- "APRN $200". The underlying RN licence is a separate $100 by examination or by endorsement.',
 'https://nevadanursingboard.org/wp-content/uploads/2023/02/Fees.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NV','APRN','renewal_fee_cents', null, 20000, null, null,
 'Nevada State Board of Nursing, Fee Schedule (1/2023): Renewal -- "APRN $200"; the Board''s APRN Renewal FAQ states "The APRN renewal fee is $200." The underlying RN licence renewal is a separate $100.',
 'https://nevadanursingboard.org/wp-content/uploads/2023/02/Fees.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NV','APRN','collaborative_agreement_required', null, null, null,
 '{"required": false, "exception": {"applies_to": "an APRN prescribing Schedule II controlled substances who has less than 2 years or 2,000 hours of clinical experience", "instrument": "a protocol approved by a collaborating physician", "threshold_years": 2, "threshold_hours": 2000}}'::jsonb,
 'NRS 632.237, as published by the Nevada Legislature: an APRN may "prescribe controlled substances, poisons, dangerous drugs and devices", and for Schedule II substances must have "at least 2 years or 2,000 hours of clinical experience" OR prescribe "pursuant to a protocol approved by a collaborating physician". There is NO general collaborative agreement requirement; the collaborating-physician instrument is a TRANSITION-TO-PRACTICE alternative for Schedule II prescribing only, so a bare boolean in either direction would be wrong -- hence value_json.',
 'https://www.leg.state.nv.us/NRS/NRS-632.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

-- =============================================================================
-- NEW MEXICO -- physician (MD)
-- New Mexico Medical Board. NMSA 61-6; 16.10 NMAC. TRIENNIAL renewal.
-- =============================================================================
('NM','MD','renewal_cycle_months', null, 36, null, null,
 '16.10.4 NMAC (New Mexico Medical Board, continuing medical education), as published by the New Mexico State Records Center and Archives: the rule is written throughout against "each triennial renewal cycle", with the CME licensing period running "July 1 through June 30 immediately preceding the triennial renewal date". 16.10.9 NMAC sets a "Triennial license renewal fee". New Mexico physician licensure is a three-year cycle.',
 'https://www.srca.nm.gov/parts/title16/16.010.0004.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NM','MD','ce_hours_total', null, 75, null, null,
 '16.10.4 NMAC, as published by the New Mexico State Records Center and Archives: "Seventy-five hours of continuing medical education are required for all medical licenses during each triennial renewal cycle."',
 'https://www.srca.nm.gov/parts/title16/16.010.0004.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NM','MD','ce_cycle_months', null, 36, null, null,
 '16.10.4 NMAC: the 75 hours are required "during each triennial renewal cycle" and "may be earned at any time during the licensing period, July 1 through June 30 immediately preceding the triennial renewal date". CE cycle equals the renewal cycle.',
 'https://www.srca.nm.gov/parts/title16/16.010.0004.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NM','MD','ce_topic_pain_management_hours', null, 5, null, null,
 '16.10.4 NMAC, as published by the New Mexico State Records Center and Archives: "Each subsequent triennial renewal cycle shall include five hours of CME hours in pain management." The rule permits the five hours to count toward the 75-hour total, applicable "in either the triennial cycle in which these hours are completed, or the triennial cycle immediately thereafter". Per triennial cycle, hence a plain hour count against ce_cycle_months = 36.',
 'https://www.srca.nm.gov/parts/title16/16.010.0004.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NM','MD','ce_topic_laws_and_rules_hours', null, 1, null, null,
 '16.10.4 NMAC, as published by the New Mexico State Records Center and Archives: "One hour of required CME must be earned by reviewing the New Mexico Medical Practice Act and these board rules."',
 'https://www.srca.nm.gov/parts/title16/16.010.0004.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NM','MD','initial_license_fee_cents', null, 40000, null, null,
 '16.10.9.8 NMAC (New Mexico Medical Board fee schedule), as published by the New Mexico State Records Center and Archives: "Application fee of $400."',
 'https://www.srca.nm.gov/parts/title16/16.010.0009.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NM','MD','renewal_fee_cents', null, 60000, null, null,
 '16.10.9.8 NMAC, as published by the New Mexico State Records Center and Archives: "Triennial license renewal fee of $450 plus a triennial fee to support the impaired physicians program of $150" -- $600 in total for the three-year period, which is what the licensee pays.',
 'https://www.srca.nm.gov/parts/title16/16.010.0009.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

-- =============================================================================
-- NEW MEXICO -- certified nurse practitioner (APRN)
-- New Mexico Board of Nursing. NMSA 61-3; 16.12 NMAC.
-- NOTE: the MD cycle is THREE years and the CNP cycle is TWO. They differ.
-- =============================================================================
('NM','APRN','renewal_cycle_months', null, 24, null, null,
 '16.12.2 NMAC (New Mexico Board of Nursing), as published by the New Mexico State Records Center and Archives: "Licensed nurses shall be required to complete the renewal process by the end of their renewal month every two years."',
 'https://www.srca.nm.gov/parts/title16/16.012.0002.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NM','APRN','ce_hours_total', null, 30, null, null,
 '16.12.2 NMAC, as published by the New Mexico State Records Center and Archives: "30 hours of approved CE must be accrued within the 24 months immediately preceding expiration of license."',
 'https://www.srca.nm.gov/parts/title16/16.012.0002.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NM','APRN','ce_cycle_months', null, 24, null, null,
 '16.12.2 NMAC: the 30 hours must be accrued "within the 24 months immediately preceding expiration of license", i.e. the CE cycle is the renewal cycle.',
 'https://www.srca.nm.gov/parts/title16/16.012.0002.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NM','APRN','ce_topic_pain_management_hours', null, null, null,
 '{"hours": 5, "periodicity": "per_renewal_cycle", "applies_to": "a CNP who held a DEA registration at any time during the most recent renewal period", "subject": "management of non-cancer pain"}'::jsonb,
 '16.12.2 NMAC, as published by the New Mexico State Records Center and Archives: "A CNP with DEA registration at any time during their most recent renewal period shall obtain five contact hours in the management of non-cancer pain, in addition to submitting a valid national certification as an APRN." Conditional on DEA registration, hence value_json.',
 'https://www.srca.nm.gov/parts/title16/16.012.0002.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NM','APRN','renewal_fee_cents', null, 11000, null, null,
 '16.12.2 NMAC fee schedule, as published by the New Mexico State Records Center and Archives: renewal -- "Advanced practice: CNP/CNS/CRNA" "$110". The underlying RN licence renewal is a separate $110.',
 'https://www.srca.nm.gov/parts/title16/16.012.0002.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('NM','APRN','supervision_required', null, null, false, null,
 '16.12.2 NMAC, as published by the New Mexico State Records Center and Archives: "The CNP makes independent decisions regarding the health care needs of the client and also makes independent decisions in carrying out health care regimens." The rule imposes consultative rather than supervisory duties: "The CNP collaborates as necessary with other healthcare providers. Collaboration includes discussion of diagnosis and cooperation in managing and delivering healthcare." No physician supervision is required.',
 'https://www.srca.nm.gov/parts/title16/16.012.0002.html',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

-- =============================================================================
-- IDAHO -- physician (MD)
-- Idaho Board of Medicine, Division of Occupational and Professional Licenses.
-- Idaho Code Title 54 ch. 18; IDAPA 24.33.01.
-- =============================================================================
('ID','MD','ce_hours_total', null, 40, null, null,
 'IDAPA 24.33.01 (Rules of the Idaho Board of Medicine), as published by the Idaho Division of Financial Management administrative rules service: a physician must have "Completed no less than forty (40) hours of practice-relevant CME during the prior two (2) years". The rule offers two alternatives to the hour count -- maintaining current ABMS, AOA or Royal College of Physicians and Surgeons of Canada board certification, or full-time participation in an accredited residency or fellowship -- so the 40 hours is one of three compliance pathways.',
 'https://files.dfm.idaho.gov/dfm-admin-website/rules/current/24/243301.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('ID','MD','ce_cycle_months', null, 24, null, null,
 'IDAPA 24.33.01: the 40 hours must be completed "during the prior two (2) years". The CE look-back is 24 months. NOTE: this is the CE clock only; the Idaho physician licence renewal clock was NOT verified and is recorded as an open conflict.',
 'https://files.dfm.idaho.gov/dfm-admin-website/rules/current/24/243301.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('ID','MD','initial_license_fee_cents', null, 20000, null, null,
 'Idaho Division of Occupational and Professional Licenses, State of Idaho January 1, 2025 Fee Changes -- Medicine: "Initial Licensure Fee $200.00".',
 'https://dopl.idaho.gov/wp-content/uploads/2024/12/Fee-Changes_Medicine.pdf',
 '2025-01-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('ID','MD','renewal_fee_cents', null, 16000, null, null,
 'Idaho Division of Occupational and Professional Licenses, State of Idaho January 1, 2025 Fee Changes -- Medicine: "License Renewal Fee -- Curr Yr" reduced from $200.00 to "$160.00" effective January 1, 2025.',
 'https://dopl.idaho.gov/wp-content/uploads/2024/12/Fee-Changes_Medicine.pdf',
 '2025-01-01', timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

-- =============================================================================
-- IDAHO -- advanced practice registered nurse (APRN)
-- Idaho Board of Nursing, DOPL. Idaho Code Title 54 ch. 14; IDAPA 24.34.01.
-- =============================================================================
('ID','APRN','renewal_cycle_months', null, 24, null, null,
 'IDAPA 24.34.01 (Rules of the Idaho Board of Nursing), as published by the Idaho Division of Financial Management administrative rules service: "The advanced practice registered nurse license may be renewed every two (2) years as specified in Section 54-1411, Idaho Code." (The underlying RN licence is on a separate annual clock.)',
 'https://files.dfm.idaho.gov/dfm-admin-website/rules/current/24/243401.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('ID','APRN','supervision_required', null, null, false, null,
 'IDAPA 24.34.01 (Rules of the Idaho Board of Nursing): the rules describe the APRN as a "licensed independent practitioner" who practises within the established standards for the APRN role and population focus, with a duty to "consult and collaborate with and refer to other health care professionals as appropriate". The rules contain no physician supervision requirement. Consultation and referral are professional duties, not a supervisory relationship.',
 'https://files.dfm.idaho.gov/dfm-admin-website/rules/current/24/243401.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

-- =============================================================================
-- WYOMING -- physician (MD)
-- Wyoming Board of Medicine. Wyo. Stat. 33-26; Board Rules chs. 1-5.
-- Wyoming is the only ANNUAL physician renewal in this group.
-- =============================================================================
('WY','MD','renewal_cycle_months', null, 12, null, null,
 'Wyoming Board of Medicine Rules and Regulations, ch. 2 (licence issuance and renewal), as filed with the Wyoming Secretary of State: after the first renewal, "all physician licenses shall be renewed no later than June 30th of each calendar year." First-time renewal is prorated: "Physician licenses originally issued between July 1st and February 28th (29th in leap years) shall be due for first-time renewal no later than the immediately following June 30th. Physician licenses originally issued between March 1st and June 30th shall be valid through, and due for first-time renewal no later than, June 30th of the following calendar year."',
 'https://wyoleg.gov/arules/2012/rules/ERR23-021.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

-- =============================================================================
-- WYOMING -- advanced practice registered nurse (APRN)
-- Wyoming State Board of Nursing. Wyo. Stat. 33-21; WSBN Rules chs. 4-5.
-- =============================================================================
('WY','APRN','renewal_cycle_months', null, 24, null, null,
 'Wyoming State Board of Nursing, Renewal: "renewal of all Nursing licensure and certificates biennially every EVEN calendar year". The Board''s fee rule describes the competency renewal cycle as running "from January 1st of every odd year to December 31st of every even year".',
 'https://wsbn.wyo.gov/renewal',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('WY','APRN','renewal_window_days', null, 92, null, null,
 'Wyoming State Board of Nursing, Renewal: renewal occurs "between October 1st and December 31st" of the renewal year -- "Renewal will take place between October 1st and close on December 31st of 2026". October 1 to December 31 inclusive is 92 days (31 + 30 + 31); the Board states the window as dates, and 92 is the exact day count of those dates, not an approximation.',
 'https://wsbn.wyo.gov/renewal',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('WY','APRN','ce_topic_pharmacotherapeutics_hours', null, null, null,
 '{"hours": 15, "periodicity": "per_renewal_cycle", "applies_to": "APRN with prescriptive authority", "window": "within the two years prior to license expiration", "subject": "pharmacology and clinical management of drug therapy"}'::jsonb,
 'Wyoming State Board of Nursing, Licensure/Certification Requirements and ch. 5 Fees rule, as filed with the Wyoming Secretary of State: an APRN with prescriptive authority must complete "fifteen (15) hours of coursework in pharmacology and clinical management of drug therapy within the two (2) years prior to license expiration". Conditional on prescriptive authority, hence value_json.',
 'https://www.wyoleg.gov/ARules/2012/Rules/ARR17-088.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('WY','APRN','ce_topic_controlled_substance_hours', null, null, null,
 '{"hours": 3, "periodicity": "per_renewal_cycle", "applies_to": "APRN with prescriptive authority", "subjects_any_of": ["responsible prescribing of controlled substances", "treatment of substance abuse disorders"]}'::jsonb,
 'Wyoming State Board of Nursing, Renewal: for prescriptive authority, "Three (3) hours of Continuing Education (CEU''s) related to the responsible prescribing of controlled substances or treatment of substance abuse disorders". Conditional on prescriptive authority, hence value_json.',
 'https://wsbn.wyo.gov/renewal',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('WY','APRN','initial_license_fee_cents', null, 25000, null, null,
 'Wyoming State Board of Nursing, Licensure/Certification Requirements and ch. 5 Fees rule: Licensure/Certification by Examination -- "APRN (includes RN application + APRN initial certification) $250". By endorsement the figure is $255.',
 'https://www.wyoleg.gov/ARules/2012/Rules/ARR17-088.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('WY','APRN','renewal_fee_cents', null, 18000, null, null,
 'Wyoming State Board of Nursing, Licensure/Certification Requirements and ch. 5 Fees rule: Renewal -- "APRN (includes RN application + APRN initial certification) $180". The Board''s Renewal page states the same: "APRN: $180 for initial national certification; add $70 per additional certification; $70 for prescriptive authority".',
 'https://www.wyoleg.gov/ARules/2012/Rules/ARR17-088.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

-- =============================================================================
-- ALASKA -- physician (MD)
-- Alaska State Medical Board, Division of Corporations, Business and
-- Professional Licensing. AS 08.64; 12 AAC 40.
-- NOTE: the Board states CME per YEAR. Seeded as stated: 25 per 12 months.
-- =============================================================================
('AK','MD','renewal_cycle_months', null, 24, null, null,
 'Alaska State Medical Board, Frequently Asked Questions: "All medical licenses in Alaska are on a two-year cycle, with all licenses expiring December 31 of even-numbered years." The Board''s Medical License Renewal Application is headed "January 1, 2025 -- December 31, 2026" and states licences expire "on December 31 of even-numbered years".',
 'https://www.commerce.alaska.gov/web/cbpl/professionallicensing/statemedicalboard/frequentlyaskedquestions.aspx',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('AK','MD','ce_hours_total', null, 25, null, null,
 'Alaska State Medical Board, Medical License Renewal Application: a physician must obtain "an average of 25 credit hours of continuing medical education during each year of the previous license period", from Category 1 AMA-, AOA- or CPME-approved sources. The Board states the requirement PER YEAR, so 25 is seeded against a 12-month ce_cycle_months rather than multiplied out to a 50-hour biennial figure the Board does not itself publish as a single number.',
 'https://www.commerce.alaska.gov/web/portals/5/pub/med0077.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('AK','MD','ce_cycle_months', null, 12, null, null,
 'Alaska State Medical Board, Medical License Renewal Application and FAQ: CME is required as "an average of 25 credit hours ... during each year of the previous license period" / "an average of 25 hours ... for each year of the licensing period (two-year licensing cycle)". The CE quantum is annual while the licence renews every 24 months.',
 'https://www.commerce.alaska.gov/web/portals/5/pub/med0077.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('AK','MD','ce_topic_opioid_hours', null, null, null,
 '{"hours": 2, "periodicity": "per_renewal_cycle", "applies_to": "licensees holding a valid DEA registration", "subject": "pain management and opioid use and addiction", "counts_toward_ce_hours_total": true}'::jsonb,
 'Alaska State Medical Board, Medical License Renewal Application: "at least two of the total hours required to qualify for renewal must be education in pain management and opioid use and addiction." The Board''s FAQ states the requirement "applies to licensees who hold valid DEA registrations" and is mandatory at both initial licensure and renewal. Conditional on DEA registration, hence value_json.',
 'https://www.commerce.alaska.gov/web/portals/5/pub/med0077.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('AK','MD','renewal_fee_cents', null, 35000, null, null,
 'Alaska State Medical Board, Medical License Renewal Application (January 1, 2025 -- December 31, 2026): "Full-Term Biennial License Renewal $350.00" for an active licence issued on or before December 31, 2023.',
 'https://www.commerce.alaska.gov/web/portals/5/pub/med0077.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

-- =============================================================================
-- ALASKA -- advanced practice registered nurse (APRN)
-- Alaska Board of Nursing, Division of Corporations, Business and
-- Professional Licensing. AS 08.68; 12 AAC 44.
-- =============================================================================
('AK','APRN','renewal_cycle_months', null, 24, null, null,
 'Alaska Board of Nursing, Renewal Information: "Renewal of Advanced Practice Registered Nurse licenses will coincide with renewal of registered nurse licenses", and the "Registered Nurse renewal schedule" is "November 30 of even-numbered years". The Board''s Registered Nurse License Renewal form covers the period "December 1, 2026 -- November 30, 2028", a 24-month cycle.',
 'https://www.commerce.alaska.gov/web/cbpl/ProfessionalLicensing/BoardofNursing/RenewalInformation',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('AK','APRN','ce_topic_pharmacotherapeutics_hours', null, null, null,
 '{"hours": 12, "periodicity": "per_renewal_cycle", "applies_to": "advanced nurse practitioner renewing prescriptive authority", "rule": "12 AAC 44.440(f) and 12 AAC 44.400(i)", "paired_requirement": {"clinical_management_of_patients_hours": 12}, "counts_toward": "12 AAC 44.610 continuing education hours"}'::jsonb,
 'Alaska Board of Nursing, Continuing Education Guidelines for RNs, LPNs, and APRNs (12 AAC 44.440(f), 12 AAC 44.400(i)): an advanced nurse practitioner renewing prescriptive authority must complete "12 contact hours of continuing education in advanced pharmacotherapeutics and 12 contact hours of continuing education in clinical management of patients" "during the previous two years"; "These 24 hours of continuing education may be counted as part of the continuing education hours described in 12 AAC 44.610." Conditional on prescriptive authority, hence value_json.',
 'https://www.commerce.alaska.gov/web/Portals/5/pub/NUR_CE-Guidelines_2018.02.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('AK','APRN','initial_license_fee_cents', null, 20000, null, null,
 'Alaska Board of Nursing, Advanced Practice Registered Nurse License Application: "Nonrefundable Application Fee: $100.00" plus "APRN License Fee: $100.00" -- $200.00 in total, which is what the applicant pays. The underlying RN licence is separate.',
 'https://www.commerce.alaska.gov/web/portals/5/pub/nur4028.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

-- =============================================================================
-- HAWAII -- physician (MD)
-- Hawaii Medical Board, DCCA Professional and Vocational Licensing.
-- HRS ch. 453; HAR ch. 16-85.
-- =============================================================================
('HI','MD','renewal_cycle_months', null, 24, null, null,
 'Hawaii Medical Board, DCCA Professional and Vocational Licensing: physicians "Renew by January 31 every even-numbered year", the current biennium running "February 1, 2026 to January 31, 2028".',
 'https://cca.hawaii.gov/pvl/boards/medical/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('HI','MD','ce_hours_total', null, 40, null, null,
 'Hawaii Medical Board, Notice of Audit -- Physician License Renewal / Continuing Medical Education: "40 category 1 or 1A CME hours" for the biennium for a physician licensed before the biennium opened, prorated to "20 category 1 or 1A CME hours" for a physician licensed part-way through it. SUBJECT TO AN OPEN CONFLICT: the figure is taken from the Board''s audit notice for the biennium ending 01/31/24, not from a current rule page; see requirement_conflicts.',
 'https://cca.hawaii.gov/wp-content/uploads/2026/01/2023-MD-Notice-of-Audit.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('HI','MD','ce_cycle_months', null, 24, null, null,
 'Hawaii Medical Board, Notice of Audit -- Physician License Renewal / CME: the CME hour requirement is assessed per biennium (the audited period being the two calendar years preceding the 01/31 renewal deadline), and the Board''s licensing page confirms renewal "by January 31 every even-numbered year". CE cycle equals the renewal cycle.',
 'https://cca.hawaii.gov/wp-content/uploads/2026/01/2023-MD-Notice-of-Audit.pdf',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('HI','MD','renewal_fee_cents', null, 40200, null, null,
 'Hawaii Medical Board, DCCA Professional and Vocational Licensing: physician on-time renewal "$402.00".',
 'https://cca.hawaii.gov/pvl/boards/medical/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

-- =============================================================================
-- HAWAII -- advanced practice registered nurse (APRN)
-- Hawaii Board of Nursing, DCCA Professional and Vocational Licensing.
-- HRS ch. 457; HAR ch. 16-89.
-- NOTE: the MD biennium ends 01/31 of EVEN years; the APRN biennium ends
-- 06/30 of ODD years. The two clocks do not align.
-- =============================================================================
('HI','APRN','renewal_cycle_months', null, 24, null, null,
 'Hawaii Board of Nursing, DCCA Professional and Vocational Licensing: nurses "Renew by June 30 every odd-numbered year", i.e. a two-year cycle expiring June 30 of odd-numbered years.',
 'https://cca.hawaii.gov/pvl/boards/nursing/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true),

('HI','APRN','renewal_fee_cents', null, 3600, null, null,
 'Hawaii Board of Nursing, DCCA Professional and Vocational Licensing: on-time renewal fees -- "APRN (active): $36.00" (inactive $12.00). The underlying RN licence renewal is a separate "RN (active): $196.00", so an APRN who also holds an active Hawaii RN licence pays both.',
 'https://cca.hawaii.gov/pvl/boards/nursing/',
 null, timestamptz '2026-09-18 00:00:00+00', 'research-agent-group-d', 1, true);

commit;
