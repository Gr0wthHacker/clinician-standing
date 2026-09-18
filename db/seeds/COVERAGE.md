# `db/seeds` — coverage

Per-agent coverage of the rules asset. Each section below is owned by the agent
that wrote it; add your own section rather than editing someone else's.

The verification standard is in `README.md`. In short:

> **A missing value is correct. An invented value is a defect.**

---

## Group C — IL, OH, IN, WI, MN, IA, MO, KS, NE, ND, SD, MT

Files: `requirements_seed_group_c.sql`, `requirement_conflicts_seed_group_c.sql`
`verified_by` / `observed_by`: `research-agent-group-c`
Verified: 2026-09-18. Applied against PostgreSQL 16.13; all migrations plus the
CA/FL/TX/NY seeds plus these two apply with no constraint violation, re-running
all four twice is a no-op, and `ux_requirements_current` holds.

**100 `requirements` rows, 58 open `requirement_conflicts` rows** (46 gaps, 12
qualifiers/disagreements). Every open conflict blocks auto-clear (PRD 8.1
condition 6) and raises `RULE_UNCERTAIN` (PRD 8.3).

### Coverage matrix

| State | MD | APRN | Total | Note |
|-------|---:|-----:|------:|------|
| IL | 6 | 6 | 12 | Triennial MD cycle, biennial APRN cycle — the professions do not share a clock |
| OH | 7 | 6 | 13 | Best-covered state in the group |
| IN | 5 | 5 | 10 | Live state CSR, verified for both professions |
| WI | 5 | 6 | 11 | APRN practice authority is mid-transition; see open conflicts |
| MN | 3 | 3 |  6 | **Annual** MD renewal vs **three-year** CME clock |
| IA | 5 | 6 | 11 | Two independent five-year CME topic clocks on a two-year MD licence |
| MO | 4 | 3 |  7 | MD renewal cycle NOT verified — see below |
| KS | **0** | 1 |  1 | Deliberately near-empty; see below |
| NE | 4 | 3 |  7 | NP supervision tier (2,000 h) |
| ND | 4 | 4 |  8 | No fee row in either direction — two official sources use different units |
| SD | 4 | 3 |  7 | NP collaboration tier (1,040 h) |
| MT | 4 | 3 |  7 | Only state with a **verified zero** CE requirement for both professions |
| **Total** | **51** | **49** | **100** | |

Value-column mix: 78 `value_num`, 14 `value_json`, 8 `value_bool`. Every row
carries a `citation_url` that was fetched and read on 2026-09-18.

### Field keys seeded

`renewal_cycle_months` (21), `ce_hours_total` (17), `ce_cycle_months` (13),
`renewal_fee_cents` (10), `initial_license_fee_cents` (7),
`ce_topic_opioid_hours` (6), `collaborative_agreement_required` (6),
`ce_topic_pharmacotherapeutics_hours` (5), `csr_fee_cents` (2),
`csr_required` (2), `ce_topic_implicit_bias_hours` (2),
`fingerprint_required` (2), `renewal_window_days` (2),
`ce_topic_controlled_substance_hours` (1), `ce_topic_ethics_hours` (1),
`ce_topic_laws_and_rules_hours` (1), `ce_topic_pain_management_hours` (1),
`supervision_required` (1).

No new `field_key` was invented. Two rows are mapped onto the nearest permitted
topic name and both say so in their own `citation` text and in a linked
conflict: Ohio's duty-to-report-misconduct hour sits under
`ce_topic_ethics_hours`, and Iowa's end-of-life-care hours sit under
`ce_topic_pain_management_hours` with `"topic": "end-of-life care"` in the
`value_json`. `csr_renewal_cycle_months` is unseeded everywhere in this group.

### Sources used

| Jurisdiction | Authorities read |
|---|---|
| IL | IDFPR Division of Professional Regulation (`idfpr.illinois.gov`) — physician licensing FAQ, physician and APRN renewal/reinstatement packets, APRN & FPA-APRN CE FAQs, Continuing Education page |
| OH | State Medical Board of Ohio (`med.ohio.gov`); Ohio Revised Code and Administrative Code (`codes.ohio.gov`) — ORC 4731.281, 4723.08, 4723.24, 4723.431; OAC 4731-10-02, 4723-14-03 |
| IN | Indiana Professional Licensing Agency (`in.gov/pla`) — physician licensing information, physician renewal FAQs and renewal form, nursing licensing information, Collaborative Practice Agreement checklist, Controlled Substances Registration |
| WI | DSPS (`dsps.wi.gov`) — physician CE, Renewal Dates and Fees, Medicine & Surgery #570, APRN pages; Wis. Admin. Code ch. N 8 (`docs.legis.wisconsin.gov`) |
| MN | Board of Medical Practice and Board of Nursing (`mn.gov/boards`) — CME, renewal, APRN licensure general information, APRN renewal, nursing CE |
| IA | DIAL (`dial.iowa.gov`) — physician CE, chronic pain and end-of-life training, nursing renewals, nursing and ARNP CE; Iowa Administrative Code (`legis.iowa.gov`) — 481—652.12, 653 ch. 9, 655 ch. 7 |
| MO | Division of Professional Registration (`pr.mo.gov`); Code of State Regulations (`sos.mo.gov`) — 20 CSR 2150-2, 20 CSR 2200-4; RSMo 334.075, 334.285 (`revisor.mo.gov`) |
| KS | Board of Healing Arts (`ksbha.ks.gov`) — renewal dates, MD licensing FAQ, MD licence type, General Counsel FAQ; K.S.A. 65-2809, 65-1131, 65-1132 (`ksrevisor.gov`) |
| NE | DHHS Licensure Unit (`dhhs.ne.gov`) — medicine and surgery, nurse licensing renewal and CE, Controlled Substances Continuing Competency Requirement, APRN-NP application information |
| ND | Board of Medicine (`ndbom.org`) — CME, physician FAQ; Board of Nursing (`ndbon.org`) — CE for renewal, renewal FAQs; NDAC 50-02-07.1, 54-05-03.1 and NDCC ch. 43-12.1 (`ndlegis.gov`) |
| SD | Board of Medical and Osteopathic Examiners rules ARSD art. 20:47 and Board of Nursing rules ARSD 20:48:03, 20:48:06 (`sdlegislature.gov` rules API); Board of Nursing CNP licensure instructions (`doh.sd.gov`) |
| MT | Board of Medical Examiners (`boards.bsd.dli.mt.gov`) — FAQ, renewal process, ARM ch. 24.156 rules PDF; Board of Nursing — APRN, continuing education |

No CE aggregator, licence-service marketplace or renewal-guide site was used,
and nothing was carried across from a neighbouring state, from one profession to
another, or from one board to another board in the same state.

### The four things a consumer must know about this group

**1. `supervision_required` and `collaborative_agreement_required` are not
interchangeable here, and four states are tiered.** Nebraska's instrument is a
written *Transition to Practice agreement with a supervising provider* ending at
2,000 hours → `supervision_required`, `value_json`. Minnesota's is a
*collaborative agreement* ending at 2,080 hours, binding only CNPs and CNSs →
`collaborative_agreement_required`, `value_json`. South Dakota's is a
*collaborative agreement* ending at 1,040 hours, retired on Board Form 3 →
`collaborative_agreement_required`, `value_json`. Ohio (standard care
arrangement), Indiana (written practice agreement) and Missouri (collaborative
practice arrangement) have **no threshold at all** and are bare booleans. Do not
normalise the two shapes together. Wisconsin's threshold exists but its value
was not readable and is therefore **not** in the table.

**2. Renewal clock ≠ CE clock, twice over.** Minnesota physicians renew
**annually** but carry a **three-year** 75-hour CME requirement — anchoring CME
to renewal over-bills them threefold. Missouri's physician CME runs on a **fixed
calendar window** (1 January even year – 31 December odd year), not on the
licensee's own dates. Iowa runs two independent **five-year** topic clocks on a
**two-year** licence.

**3. Two zeros in this group are real, and two absences are not.** Montana's
board writes *"Montana does not require Physicians to acquire CME"* and its
nursing board writes that it *"no longer requires continuing education contact
hours"* — those are seeded as `0`. South Dakota's and Indiana's physician CE
requirements are **absent from every source read**, which is not the same thing,
and are seeded as nothing at all. A consumer that treats `value_num = 0` as
falsy will show a Montana physician "unknown" when the correct answer is "none".

**4. Kansas is nearly empty on purpose.** One row: the two-year APRN licence
period from K.S.A. 65-1132. Four Board of Healing Arts pages and three statutes
were read and none publishes a physician CE hour count, fee or cycle length —
K.S.A. 65-2809 delegates all of it to K.A.R. 100-15, which is not served in
retrievable form. Kansas populated from Nebraska or Missouri would be a defect;
an empty Kansas is visibly empty.

### Not verified — the headline items

Full detail, with what was searched and what remains open, is in
`requirement_conflicts_seed_group_c.sql`. The ones that matter most:

| What | Why it is not seeded |
|---|---|
| **MO/MD `renewal_cycle_months`** | The 24-month figure in the table is the *CME* window. No Missouri source read states the licence renewal frequency; `revisor.mo.gov` blocked automated access after two requests. Deriving the licence cycle from the CME cycle is exactly the failure Minnesota disproves. |
| **WI/APRN practice-authority threshold** | DSPS describes an APRN credential with an independent-practice tier reached through supervised hours; ch. N 8 still describes an unconditional collaborative relationship. The hour count is in 2023 AB 154 / SB 145, which `docs.legis.wisconsin.gov` refused. No number invented. Highest-value open item in the group. |
| **IL/APRN practice authority** | Illinois runs an ordinary-APRN / FPA-APRN two-tier regime. The instrument and threshold are in 68 Ill. Adm. Code 1300.465 and 225 ILCS 65/65-43; `ilga.gov` refused every URL form tried and IDFPR's FPA packet 404s. Neither `true` nor `false` would be right. |
| **IL `csr_required` / `csr_fee_cents`** | Illinois plainly issues a Licensed Physician Controlled Substance licence and a $5/$15 fee appears in a reinstatement packet, but no source read says a prescriber *must* hold it. Required-ness is not inferred from a credential's existence. |
| **IA/APRN and ND/APRN practice authority** | Iowa's IAC 655 ch. 7, North Dakota's NDAC 54-05-03.1 and NDCC ch. 43-12.1 were each read in full and contain **no** collaboration or supervision requirement. Both are almost certainly full-practice-authority states and `false` is probably right — but an absence in a chapter is not a board assertion. Low-effort, high-value to close. |
| **ND fees (both professions)** | NDAC 50-02-07.1-01 prices licensure at "two hundred dollars per year"; the Board says licences expire "every other year". $200 and $400 are both defensible. No fee row written in either direction. |
| **OH/APRN fees** | ORC 4723.08 gives $150/$135 but its own words are *"may impose fees **not to exceed**"* — a statutory cap, not the amount charged. The Board of Nursing's fee page is JavaScript-only. Contrast the Ohio MD fees, which the medical board publishes as charged amounts and which *are* seeded. |
| **NE/APRN `initial_license_fee_cents`** | The Department publishes two amounts, $68 and $25, selected by issue month because the initial licence is prorated to the next even-year 31 October. No single scalar is correct. |
| **SD/MD `ce_hours_total`** | The whole of ARSD art. 20:47 was read and contains no CME requirement. That is an absence in the rules, not a published negative — unlike Montana. |
| `fingerprint_required` | Verified only for OH/MD and ND/MD (both at initial licensure). Unverified for every other state/profession in the group. |
| `csr_required` | Verified only for IN (both professions, `true`). Unknown everywhere else in the group; no negative asserted from silence. |
| `renewal_window_days` | Verified only for IA/APRN (60 days, ARNP-specific) and SD/MD (90 days, medical-board-specific). Several boards publish a *pair of calendar dates* or a *notice* schedule; neither is a window. |
| `csr_renewal_cycle_months` | Unseeded everywhere. Indiana's CSR is required and priced but its period is only implied by "renewal information at the same time as the professional license". |

### Where two official sources disagreed

| Field | Source A | Source B | Seeded |
|---|---|---|---|
| ND physician fee | Board of Medicine: licence expires "on your birthday **every other year**" | NDAC 50-02-07.1-01: "two hundred dollars **per year**" | **Nothing.** Cycle seeded as 24 months; no fee row in either direction. |
| OH/APRN fees | ORC 4723.08: $150 application / $135 renewal | …but as a cap — "may impose fees **not to exceed**" | **Nothing.** A cap is not what the licensee pays. |
| WI/APRN authority | Wis. Admin. Code N 8.10(7): unconditional collaborative relationship | DSPS APRN page: independent practice "through supervised hours" | `true` (the conservative default), with the divergence recorded as an open conflict. |
| WI/MD opioid CME | DSPS: "For the **2025 renewal** … two of the required 30 hours" | Med 13 (unreadable) — recurrence unconfirmed | `value_json` carrying the board's own scope, not a bare recurring `2`. |
| NE opioid CME | DHHS: 3 hours, 0.5 on PDMP, for all controlled-substance prescribers | No source states the **interval** | `value_json` with `"periodicity_confirmed": false`. Must not generate a dated duty yet. |

### Explicitly not covered

- **`license_type = 'DO'` — no coverage.** In OH, IN, WI, MN, IA, NE, ND, SD and
  MT one authority licenses MDs and DOs (Wisconsin's fee schedule even prints
  identical lines for both), so the MD rows are *likely* to hold — "likely" is
  not verified and no DO-specific page was read. **IL, KS and MO regulate
  osteopathy separately** and the MD rows must not be applied there.
- **Only the licence itself.** DEA registration, CMS/Medicare enrolment,
  hospital privileges, malpractice and board certification are out of scope.
- **Five real, board-published CE duties have no `field_key` to live in** and are
  therefore absent from the table: Missouri's 1-hour nutrition CME, Illinois's
  1-hour dementia CME and 1-hour sexual-harassment-prevention CME (both
  professions), Iowa's five-yearly mandatory-reporter training, and Iowa's
  end-of-life care hours (parked under `ce_topic_pain_management_hours` and
  flagged). Adding `ce_topic_nutrition_hours`, `ce_topic_dementia_hours`,
  `ce_topic_sexual_harassment_hours`, `ce_topic_end_of_life_hours` and
  `ce_topic_mandatory_reporter_hours` would close it. Inventing them in a data
  seed would not.
- **Practice-hour conditions the schema cannot hold**: North Dakota's 400 hours
  of nursing practice in the preceding four years, and every
  transition-to-practice threshold above — the platform holds no per-clinician
  cumulative-practice-hours attribute, so no consumer can decide which side of a
  threshold a given NP is on. Those rows should raise `RULE_UNCERTAIN` rather
  than generate an obligation.

---

## Group B — MI, NC, VA, SC, TN, AL, MS, KY, AR, LA, OK, WV

Files: `requirements_seed_group_b.sql`, `requirement_conflicts_seed_group_b.sql`
Owner tag: `verified_by = 'research-agent-group-b'` / `observed_by = 'research-agent-group-b'`
Verified: 2026-09-18. 121 `requirements` rows, 52 open `requirement_conflicts` rows.

### Coverage matrix

| State | MD fields | APRN fields | Status |
|-------|----------:|------------:|--------|
| MI | 13 |  8 | complete |
| NC |  5 |  8 | complete |
| VA |  5 |  5 | complete |
| SC |  7 |  7 | complete |
| TN |  5 |  4 | complete |
| AL |  9 |  8 | complete |
| MS |  4 |  9 | complete |
| KY |  7 |  7 | complete |
| LA |  4 |  2 | **partial** — see below |
| WV |  4 |  — | **partial** — MD only |
| AR |  — |  — | **NOT REACHED** |
| OK |  — |  — | **NOT REACHED** |

15 of the 121 rows are `value_json`.

### Not reached, and what that means

- **AR (Arkansas) — no coverage, either licence type.** No Arkansas State Medical
  Board or Board of Nursing page was fetched. Every Arkansas field is unverified.
- **OK (Oklahoma) — no coverage, either licence type.** Of note, the Oklahoma
  Bureau of Narcotics and Dangerous Drugs issues a state controlled substance
  registration; `obndd.ok.gov` returned edge-server 403 to every automated fetch
  on 2026-09-18, so `csr_required` for OK is unknown and must not be assumed.
- **WV/APRN — no coverage.** The WV Board of Examiners for Registered
  Professional Nurses was not read. WV/MD itself carries only cycle, CE total,
  CE cycle and the controlled-substance CME topic; **no WV fees, no WV `csr_required`.**
- **LA — partial.** Verified: MD renewal window (56 days), the one-time CDS CME,
  and `csr_required` + CDS application fee for both licence types. **Not verified:**
  LA renewal cycle, CE totals, licence fees, and the entire Louisiana State Board
  of Nursing side beyond the CDS fields.

### Controlled substance registration — the finding that matters

Unlike CA/FL/TX/NY, most of this set **does** require a state credential beyond
the federal DEA registration, and several run it on a **different clock from the
licence**:

| State | `csr_required` | State cycle | Licence cycle | Instrument |
|---|---|---|---|---|
| MI | true (MD, APRN) | 36 mo (MD) / 24 mo (APRN) | same | Michigan controlled substance licence, **prerequisite to DEA** |
| SC | true (MD, APRN) | **12 mo, expires Apr 1** | 24 mo | DPH Bureau of Drug Control registration |
| AL | true (MD, APRN) | **12 mo** (ACSC Dec 31 / QACSC Jan 1) | 12 mo MD, **24 mo APRN** | ACSC / QACSC, **prerequisite to DEA** |
| MS | true (APRN) | not published | 24 mo | Board of Nursing CSPA, **prerequisite to DEA** |
| LA | true (MD, APRN) | not published | not verified | Board of Pharmacy CDS licence |
| NC, VA, TN, KY, WV, MS/MD | **unknown — not seeded** | — | — | no affirmative source either way |

A consumer that renews the CSR alongside the licence will let an Alabama or
South Carolina registration lapse. They are separate `field_key`s for that reason.

### Where two official sources disagreed

| Field | Source A | Source B | Seeded |
|---|---|---|---|
| `NC/APRN/ce_hours_total` and `ce_cycle_months` | 21 NCAC 32M .0107: "50 contact hours … **each year**" | NC Board of Nursing NP page: "50 contact hours … **every two years**" (and offers certification as an alternative) | the rule (50/yr) — binding instrument, matches the annual renewal in .0106(a), conservative |
| `SC/MD/ce_topic_controlled_substance_hours` | Board CE sheet: "Two hours **must** be…" | S.C. Code 40-47-37(A)(2)(a): "at least two (2) hours of which **may** be…" (while requiring the certificate at renewal) | the Board sheet (mandatory) — what is enforced at renewal |

Both are open conflicts.

### Clocks that do not coincide (read `renewal_cycle_months` and `ce_cycle_months` independently)

- **NC/MD** — licence renews every **12** months, CME runs on a **36**-month cycle.
- **KY/MD** — registration every **12** months, CME cycle **36** months.
- **MS/MD** — renewal every **12** months, CME cycle **24** months.
- **AL/MD** — registration every **12** months, but the controlled-substance CME
  runs **every 2 years**.

An obligation generator that assumes CE is due at each renewal will demand a full
cycle's hours annually in all four.

### Schema gaps this pass surfaced

1. **No key for a fixed-date renewal window.** AL, MS, SC and KY publish calendar
   dates (e.g. "begins Oct 1", expiry Dec 31), not an offset. `renewal_window_days`
   was seeded only for MI (90), TN (60) and LA (56), which publish true offsets.
   Needs a `renewal_window_opens_on` month-day key.
2. **No key for a mandated topic with no hour count.** Michigan's one-time human
   trafficking training (R 338.2413) specifies content and providers but no
   duration — and permits satisfying it by reading a journal article.
3. **Topic hours are often carved OUT OF the total, not added to it.** Flagged in
   `value_json` as `"additive": false` + `"subset_of_field_key"` on MI/MD,
   NC/MD, NC/APRN, SC/APRN and TN/MD. **Summing topic hours onto `ce_hours_total`
   over-bills every one of those.**
4. **`value_json` in this file is not always `{"hours", "periodicity"}`.**
   `SC/APRN/renewal_fee_cents` carries a two-tier fee; `MI` implicit bias carries
   a *rate* (1 hour per year of cycle, never a per-cycle total in the rule);
   `VA/APRN/collaborative_agreement_required` carries an experience threshold.
5. **`DO` is not covered.** In NC, VA, SC, TN, AL, MS, KY and WV the same board
   licenses MDs and DOs and several seeded pages name both, so the MD rows are
   *likely* to hold — but **Michigan's osteopathic board is separate**, and the
   MI/MD rows must not be applied to a Michigan DO.

### Verified against PostgreSQL 16.13 on 2026-09-18

Fresh cluster, all `db/migrations/*.sql` in order, then `00_requirements_base.sql`,
then this pass. No constraint violation; `ux_requirements_current` holds; every
row populates exactly one value column; re-running both files twice is a no-op.
Also applied alongside groups A, C and D in one database (595 `requirements`
rows across 49 states) with no unique-index collision.

### Authorities read

| Jurisdiction | Authorities |
|---|---|
| MI | LARA Bureau of Professional Licensing (`michigan.gov/lara`); Michigan Administrative Rules (`ars.apps.lara.state.mi.us`) — Board of Medicine R 338.24xx, R 338.7001–7005, controlled substance individual licensing guide |
| NC | NC Medical Board (`ncmedboard.org`), incl. 21 NCAC 32M as the Board publishes it |
| VA | Virginia Law (`law.lis.virginia.gov`) — 18VAC85-20, 18VAC90-30, Code of Va. §§ 54.1-2912.1, 54.1-2957; Board of Medicine (`dhp.virginia.gov`) |
| SC | SC Board of Medical Examiners and Board of Nursing (`llr.sc.gov`); S.C. Code titles 40 and 44 (`scstatehouse.gov`); 24A S.C. Regs. 60-4 (`dph.sc.gov`) |
| TN | TN Dept of Health, Boards of Medical Examiners and Nursing (`tn.gov/health`) |
| AL | Board of Medical Examiners / Medical Licensure Commission (`albme.gov`); Board of Nursing (`abn.alabama.gov`) |
| MS | State Board of Medical Licensure (`msbml.ms.gov`); Board of Nursing (`msbn.ms.gov`), incl. 30 Miss. Admin. Code Part 2815 |
| KY | Board of Medical Licensure (`kbml.ky.gov`); Board of Nursing (`kbn.ky.gov`); 201 KAR chs. 9 and 20 (`apps.legislature.ky.gov`) |
| LA | State Board of Medical Examiners (`lsbme.la.gov`); Board of Pharmacy (`pharmacy.la.gov`) |
| WV | Board of Medicine (`wvbom.wv.gov`) |

### Hosts that blocked verification on 2026-09-18

`ncbon.com` (Cloudflare challenge to every direct fetch), `obndd.ok.gov`
(edge-server 403), `mbn.ms.gov` (502 from the egress proxy),
`legislature.mi.gov` (incomplete TLS chain), `dph.sc.gov` drug-control pages and
`msbml.ms.gov/licensure/licensing-fees` (body rendered client-side; only
navigation retrieved), and the WV Board of Medicine fee handout (fee digits do
not survive text extraction). Each is named in the relevant conflict row.

---

## Group D — AZ, WA, OR, CO, UT, NV, NM, ID, WY, AK, HI

Files: `requirements_seed_group_d.sql`, `requirement_conflicts_seed_group_d.sql`
Owner tag: `verified_by = 'research-agent-group-d'` / `observed_by = 'research-agent-group-d'`
Verified: 2026-09-18. **121 `requirements` rows, 62 open `requirement_conflicts`
rows** (48 gaps, 14 qualifiers/disagreements).

Value-column mix: 84 `value_num`, 31 `value_json`, 6 `value_bool`, 0 `value_text`.
Every row carries a `citation_url` that was fetched and read on 2026-09-18.

### Coverage matrix

| State | MD | APRN | Total | Note |
|-------|---:|-----:|------:|------|
| NV | 10 | 11 | 21 | Best-covered state in the group; six mandated CE topics per profession |
| WA |  9 |  8 | 17 | MD renews every **24** months, CME runs on a **48**-month clock |
| UT |  9 |  8 | 17 | **First live state CSR in the asset** — `csr_required` true, with cycle and fee |
| NM |  7 |  6 | 13 | MD cycle is **36** months, APRN cycle is **24** — the professions do not share a clock |
| OR |  7 |  3 | 10 | Board states CME as 30 hours **per year** on a 24-month registration |
| AZ |  5 |  6 | 11 | APRN renews every **48** months (4-year RN clock) |
| AK |  5 |  3 |  8 | Board states CME as an **average** of 25 hours per year |
| WY |  1 |  6 |  7 | Only **annual** physician renewal in the group; MD otherwise near-empty |
| HI |  4 |  2 |  6 | MD biennium ends 01/31 even years, APRN biennium ends 06/30 odd years |
| ID |  4 |  2 |  6 | MD **renewal cycle not verified** — see below |
| CO |  3 |  2 |  5 | APRN **renewal cycle not verified** — see below |
| **Total** | **64** | **57** | **121** | |

All eleven jurisdictions were reached. Depth varies sharply: NV, WA and UT are
substantially complete; WY/MD, CO and ID are thin because the boards do not
publish the values in retrievable form, not because they were skipped.

### Field keys seeded

`renewal_cycle_months` (20), `ce_hours_total` (15), `renewal_fee_cents` (15),
`ce_cycle_months` (13), `initial_license_fee_cents` (12),
`ce_topic_opioid_hours` (5), `ce_topic_controlled_substance_hours` (4),
`ce_topic_pain_management_hours` (4), `ce_topic_suicide_prevention_hours` (4),
`ce_topic_cultural_competency_hours` (3),
`ce_topic_pharmacotherapeutics_hours` (3),
`collaborative_agreement_required` (3), `renewal_window_days` (3),
`supervision_required` (3), `ce_topic_health_equity_hours` (2),
`ce_topic_sbirt_hours` (2), `csr_fee_cents` (2),
`csr_renewal_cycle_months` (2), `csr_required` (2),
`ce_topic_bioterrorism_hours` (1), `ce_topic_ethics_hours` (1),
`ce_topic_hiv_aids_hours` (1), `ce_topic_laws_and_rules_hours` (1).

**Five new `field_key`s were introduced**, each named in the seed file header and
in a dedicated open conflict for the rules-plane author to ratify (PRD 15.5):
`ce_topic_suicide_prevention_hours`, `ce_topic_health_equity_hours`,
`ce_topic_cultural_competency_hours`, `ce_topic_sbirt_hours`,
`ce_topic_bioterrorism_hours`. None maps onto an existing topic name without
misstating the mandate — in particular Washington's statutory **health equity**
(RCW 43.70.613), Oregon's **cultural competency** (OAR 847-008-0077) and
California's already-seeded **implicit bias** are three distinct subjects on
three different clocks, and Oregon explicitly lists implicit bias training as
only *one* of several ways to satisfy its cultural competency hours. Collapsing
them would produce one wrong number for three states.

### The five things a consumer must know about this group

**1. CE clock ≠ renewal clock in five of eleven states, and this is the most
likely source of a wrong date from this file.** `ce_hours_total` is always the
board's own number and `ce_cycle_months` is always the board's own period — no
multiplication was performed anywhere.

| State | Renewal cycle | CE cycle | Seeded CE total |
|---|---|---|---|
| WA/MD | 24 mo | **48 mo** | 200 hours |
| OR/MD | 24 mo | **12 mo** | 30 hours/year |
| AK/MD | 24 mo | **12 mo** | 25 hours/year (an *average*) |
| NM/MD | **36 mo** | 36 mo | 75 hours |
| NM/APRN | 24 mo | 24 mo | 30 hours |

A consumer that reads `ce_hours_total` and silently anchors it to
`renewal_cycle_months` will **double** Oregon and Alaska physicians' CME
obligation and **halve** Washington's.

**2. Full practice authority was NOT assumed, and mostly could not be verified.**
All eleven states are commonly listed as full-practice-authority NP states. Only
**three** `supervision_required = false` rows are seeded, each from a source that
states the proposition in terms — **AZ** ("Arizona does not require physician
supervision or collaboration for the independent practice of nurse
practitioners", AZBN scope-of-practice FAQ), **NM** ("The CNP makes independent
decisions regarding the health care needs of the client", 16.12.2 NMAC) and
**ID** (APRN is a "licensed independent practitioner", IDAPA 24.34.01). For WA,
OR, CO, UT, NV, WY, AK and HI the proposition is **unseeded**: the boards were
read and none of them says it. Reputation is not a citation.

**3. Three states in this group carry a conditional instrument that a flat
"full practice authority" label hides entirely.** All three are `value_json`
carrying the threshold, never a bare boolean:

- **CO** — 750-hour physician mentorship, completed within 3 years of provisional
  prescriptive authority (RXN-P), to reach full prescriptive authority (RXN).
- **NV** — Schedule II prescribing needs "2 years **or** 2,000 hours of clinical
  experience", *or* a protocol approved by a collaborating physician (NRS
  632.237). Two different units joined by "or"; part-time and full-time APRNs
  cross at different points.
- **UT** — the only prescribing-supervision constraint in Utah Code ch. 58-31b
  applies to CRNAs (five-day supplies around a procedure), not to NPs.

**4. Utah is the first live state CSR in the whole asset.** `csr_required`,
`csr_renewal_cycle_months` and `csr_fee_cents` were previously unseeded
everywhere (TX and NY verified `false`; CA and FL unknown). Utah verifies **true**
for both professions: DOPL issues a Controlled Substance Licence renewed "as part
of the associated practitioner license renewal" on the same 24-month clock, at
$78 renewal / $100 application, carrying its own 3.5-hour CE duty under Utah Code
58-37-6.5. **`csr_fee_cents` is additive to `renewal_fee_cents`, not a component
of it** — the licensee sees one transaction and two fees. The other ten states
are unseeded for `csr_required`; do not read that as `false`.

**5. Two APRN licences in this group renew on a clock the board does not
control.** Arizona's NP certificate "expires when the RN license or national
certification expires, **whichever comes first**" — the seeded 48 months is the
RN clock, and a national certifier's 5-year cycle can truncate it. Utah's APRN
renewal is conditioned on "current certification in your practice specialty"
under R156-31b-303(3)(b). Both are flagged as open conflicts.

### Not verified — the headline items

Full detail, with what was searched and what remains open, is in
`requirement_conflicts_seed_group_d.sql`.

| What | Why it is not seeded |
|---|---|
| **ID/MD `renewal_cycle_months`** | IDAPA 24.33.01 gives a clean 24-month *CME look-back* and DOPL publishes an annual-sounding "License Renewal Fee – Curr Yr". Neither settles the licence period: the DOPL Board of Medicine licensing page carries no renewal statement, DOPL's renewal-cycle press release covers Veterinary Medicine only, and Idaho Code Title 54 ch. 18 has no section indexed for renewal. Deriving the licence cycle from the CE cycle is exactly the failure this group's other states disprove. |
| **CO/APRN `renewal_cycle_months`** | The Board publishes an expiration **date** ("Licenses expire on 9/30/26") and no period. `/Nursing/Renewals` 404s, the FAQ covers CE but not frequency, the Laws page links the Practice Act only through Google Drive, and the DORA-wide FAQ gives only "within 6 weeks of the license expiration date". A date is not a cycle. |
| **WY/MD everything but the cycle** | Board of Medicine rules index CME at Chapter 3 Section 7, but every Secretary-of-State rules PDF retrievable on 2026-09-18 contains Chapters 1, 2 and fragments of 3 without Section 7. The fee schedule is published only behind a 404ing PDF path. One verified value: annual renewal by 30 June. |
| **CO fees, both professions** | DORA publishes no retrievable fee schedule: `/Medical/LicensingServices` returns 403, the forms page says fees are "available on the respective applications and forms", and the figures live inside the `apps2.colorado.gov` session-gated application. |
| **OR/APRN fees and practice authority** | `secure.sos.state.or.us/oard/` returned repeated robots.txt fetch failures and connect timeouts; OSBN's own fee and renewal pages 404. The only fee figures available were `$0.00` placeholders on the Business Xpress licence directory, which are not real. |
| **HI/APRN CE, HI/APRN practice authority** | The Board of Nursing publishes "one of the learning activity options for continuing competency" and points to a Continuing Competency Manual that was not retrieved — a menu, not an hour count. HRS 457-8.6 returned HTTP 403 to every attempt. |
| **AK/APRN practice authority** | The Board's application form calls an APRN "a licensed independent practitioner", but Alaska has historically required a collaborative plan for APRN prescriptive authority under 12 AAC 44.430, which was not read. **This is the one full-practice-authority assumption in this group that would be easiest to get wrong**, so nothing was seeded. |
| **WA/APRN practice authority** | Four sources read, none states the proposition: RCW 18.79.050 defers scope to board rule, the Board's FAQ carries only POLST questions, the ARNP Guidance page says only "The broadly written laws and rules allow nurses to practice to their full scope of practice in any setting", and WAC 246-840 was not retrieved. |
| **Alternative-pathway CE requirements** (ID/MD, ID/APRN, WY/APRN, AK/APRN, CO/APRN, OR/APRN, HI/APRN) | Seven of the eleven states let a licensee satisfy continued competence by a **choice** rather than an hour count — board certification, peer review, practice hours, uncompensated professional activity, a refresher course, or the NCLEX. Where the board still publishes a usable hour figure for one pathway it is seeded (ID/MD 40); where it does not, nothing is. `0` would be wrong in every case, because the national certifier's CE requirement is real. |
| `fingerprint_required` | **Verified nowhere in this group.** NV has an NRS section *heading* on fingerprints; a heading is not a requirement and the body was not read. |
| `csr_required` | Verified only for UT (both professions, `true`). Unknown in the other ten; no negative asserted from silence. NM and NV are the two most likely to have a live CSR and are flagged for follow-up. |
| `renewal_window_days` | Verified only for AZ/APRN (180), WA/MD (90) and WY/APRN (92, computed from two calendar dates and flagged). WA/APRN publishes an "85-90 days" **range**, which is not a value — the same treatment the first seed file gave TX/MD's 60-90 range. |

### Where two official sources disagreed

| Field | Source A | Source B | Seeded |
|---|---|---|---|
| **OR/MD `renewal_fee_cents`** | Oregon Medical Board renewal fee sheet (eff. 7/2/2026): "License Registration **$608**" per two-year period, "Total to Renew License **$756**" | OAR 847-005-0005, the Board's own fee **rule**: "Registration: Active … **$314/year**" — $628 per biennium | **$756**, the fee-sheet total, because that is what the licensee is asked to pay. Recorded as an open conflict; $608 and $628 cannot both be right for the same period. |
| **AZ/APRN `renewal_cycle_months`** | AZBN: RN licences renew "by April 1, **every 4 years**" | AZBN, same page: APRN certification "expires when the RN license or national certification expires, **whichever comes first**" | **48 months**, the Board's RN clock, with the truncation recorded as an open conflict. |
| **WY/MD `renewal_cycle_months`** | Board of Medicine rules: "all physician licenses shall be renewed no later than **June 30th of each calendar year**" | Board renewal page headed "**2026-2027** Physician license renewals" | **12 months**, from the rule. The page is consistent with a licensure *year* running 1 July – 30 June, but the ambiguity is logged because a 12-vs-24 error doubles or halves every Wyoming physician's calendar. |
| **HI/MD `ce_hours_total`** | Board Notice of Audit: "**40** category 1 or 1A CME hours" (20 prorated) | The Board's CME landing page publishes **no** hour count, only "Subchapter 5 of the Board's rules"; HAR 16-85 subch. 5 not retrievable | **40**, from the Board's own audit notice — but that notice governs the biennium ending 01/31/2024, and a board can change an hour count between biennia. Logged. |

### Explicitly not covered

- **`license_type = 'DO'` — no coverage, any state.** Oregon licenses MD, DO and
  DPM under one fee schedule and one CME rule, so the OR/MD rows are *likely* to
  hold there; Washington runs a **separate** osteopathic chapter (WAC 246-853 /
  246-921) whose numbers differ from the allopathic ones, and **AZ, NV and UT
  have separate osteopathic boards**. "Likely" is not verified and no DO-specific
  page was read for any state.
- **Only the licence itself.** DEA registration, CMS/Medicare enrolment, hospital
  privileges, malpractice and board certification are out of scope.
- **Practice-hour and certification-date conditions the schema cannot resolve.**
  Colorado's 750 mentorship hours, Nevada's 2,000 experience hours, Utah's
  pre-1992 licensure cohort, and Arizona's and Utah's dependence on a national
  certification expiry date. The platform holds no per-clinician cumulative-hours
  or certification-expiry attribute, so no consumer can decide which side of a
  threshold a given NP is on. These rows should raise `RULE_UNCERTAIN` rather
  than generate an obligation.

### Sources used

| Jurisdiction | Authorities read |
|---|---|
| AZ | Arizona Medical Board (`azmd.gov`); Arizona State Board of Nursing (`azbn.gov`), incl. the Scope of Practice APRN FAQ; Arizona Revised Statutes (`azleg.gov`) — A.R.S. 32-1430, 32-3248.02 |
| WA | Washington Medical Commission (`wmc.wa.gov`) and DOH 657-128; Washington State Board of Nursing (`nursing.wa.gov`); WA DOH suicide prevention training requirements (`doh.wa.gov`); WAC 246-919, 246-919-875 and 246-12-820, RCW 18.79.050 (`app.leg.wa.gov`) |
| OR | Oregon Medical Board (`oregon.gov/omb`) — Continuing Education, Renew, all-fees.pdf, OAR 847-005-0005; Oregon State Board of Nursing (`oregon.gov/osbn`) — Competency Requirements, CE fact sheet, renewal instructions; Oregon SOS Business Xpress licence directory (`apps.oregon.gov/SOS`) |
| CO | DORA Division of Professions and Occupations (`dpo.colorado.gov`) — Colorado Physician CME, Physician Licensing Requirements, Nursing homepage, Nursing FAQ, Nursing Laws, division FAQ |
| UT | Utah DOPL (`commerce.utah.gov/dopl`) — physician and APRN renewal forms, Renewal Cycle Schedule and Fees, Controlled Substance renewal, DOPL fee schedule; Utah Dept of Commerce Controlled Substance Toolkit; Utah Code ch. 58-31b (`le.utah.gov`) |
| NV | Nevada State Board of Medical Examiners (`medboard.nv.gov`) — CME Requirements for MDs/PAs/AAs, Licensure Fees; Nevada State Board of Nursing (`nevadanursingboard.org`) — Continuing Education, APRN and RN/LPN Renewal FAQs, Fee Schedule; NRS 630, NRS 632.237, NAC 632.192 (`leg.state.nv.us`) |
| NM | 16.10.4, 16.10.9 and 16.12.2 NMAC as published by the New Mexico State Records Center and Archives (`srca.nm.gov`); New Mexico Medical Board (`nmmb.state.nm.us`) |
| ID | Idaho DOPL (`dopl.idaho.gov`) — Board of Medicine licensing, 2025 Medicine fee changes, renewal-cycle press release; IDAPA 24.33.01 and 24.34.01 (`files.dfm.idaho.gov`); Idaho Code Title 54 ch. 18 (`legislature.idaho.gov`) |
| WY | Wyoming Board of Medicine (`wyomedboard.wyo.gov`) and its rules as filed with the Secretary of State (`wyoleg.gov`); Wyoming State Board of Nursing (`wsbn.wyo.gov`) and its Licensure/Certification and ch. 5 Fees rule |
| AK | Alaska State Medical Board (`commerce.alaska.gov/web/cbpl`) — FAQ, Medical License Renewal Application; Alaska Board of Nursing — Renewal Information, RN renewal form, APRN licence application, CE Guidelines for RNs/LPNs/APRNs |
| HI | Hawaii Medical Board and Hawaii Board of Nursing, DCCA Professional and Vocational Licensing (`cca.hawaii.gov`), incl. the Board's physician CME Notice of Audit |

No CE aggregator, licence-service marketplace or "renewal guide" site was used,
and nothing was carried across from a neighbouring state, from one profession to
another, or from one board to another board in the same state.

### Hosts that blocked verification on 2026-09-18

`secure.sos.state.or.us/oard/` (robots.txt fetch failure, connect timeout —
cost the entire OSBN fee schedule and NP scope rules); `dpo.colorado.gov`
licensing-services pages (HTTP 403 — cost all Colorado fees);
`capitol.hawaii.gov` HRS 457 sections (HTTP 403 — cost Hawaii NP practice
authority); `www.nmmb.state.nm.us` (robots.txt DNS failure — worked around via
`srca.nm.gov`, which serves the same NMAC text); `azbn.gov` and `azmd.gov`
(Cloudflare challenge to direct `curl`; readable through the fetch tool only);
`wyomedboard.wyo.gov` fee-schedule PDF (404 at the published path); Wyoming
Board of Medicine Rules Chapter 3 Section 7 (not present in any retrievable
Secretary-of-State filing). Each is named in the relevant conflict row.

### Verified against PostgreSQL 16.13 on 2026-09-18

Fresh cluster under a non-root user, all `db/migrations/*.sql` in order, then
`00_requirements_base.sql`, `20_conflicts_base.sql`, then this pass. No
constraint violation; `ux_requirements_current` holds (0 duplicate current rows);
every row populates exactly one value column; every row has a non-null
`citation_url`; re-running all four files twice is a no-op, and re-running the
group D pair alone leaves the CA/FL/TX/NY rows untouched. Also applied alongside
groups A, B and C in one database — 595 `requirements` rows across 49 states,
still 0 duplicate current rows.

---

## Group A — PA, NJ, GA, MA, CT, MD, DC, DE, RI, NH, VT, ME

Files: `requirements_seed_group_a.sql`, `requirement_conflicts_seed_group_a.sql`
Owner tag: `verified_by = 'research-agent-group-a'` / `observed_by = 'research-agent-group-a'`
Verified: 2026-09-18. Applied against PostgreSQL 16.13 on a fresh cluster: all
`db/migrations/*.sql` in order, then `00_requirements_base.sql`,
`20_conflicts_base.sql`, then these two. No constraint violation,
`ux_requirements_current` holds (0 duplicate current keys), every row populates
exactly one value column, every row has a non-blank `citation` and a non-null
`citation_url`, and re-running all four files twice is a no-op.

**182 `requirements` rows, 56 open `requirement_conflicts` rows** (28 qualifiers
attached to seeded rows, 28 gaps with `requirement_id IS NULL`). Every open
conflict blocks auto-clear (PRD 8.1 condition 6) and raises `RULE_UNCERTAIN`
(PRD 8.3).

Value-column mix: 143 `value_num`, 27 `value_json`, 12 `value_bool`, 0
`value_text`.

### Coverage matrix

| Jurisdiction | MD | APRN | Total | Note |
|---|---:|---:|---:|---|
| PA | 9 | 9 | 18 | Two board pages disagree on the size of the opioid CME duty |
| NJ | **0** | 2 | 2 | **Board site is behind a bot wall — deliberately near-empty** |
| GA | 9 | 7 | 16 | Two once-in-a-career CME topics; nurse protocol agreement |
| MA | 9 | 7 | 16 | Three one-time physician CME topics |
| CT | 15 | 16 | 31 | **Annual licence, 24-month CE clock, biennial state CSR — three clocks** |
| MD | 7 | 4 | 11 | Renewal window published as dates; implicit bias has no hour count |
| DC | 5 | 7 | 12 | Two DC Health publications disagree on APRN fee and topic hours |
| DE | 8 | 10 | 18 | **Live state CSR on a clock offset from the licence** |
| RI | 8 | 10 | 18 | Live state CSR; APRN collaboration affirmatively *not* required |
| NH | 5 | 6 | 11 | Board fee page and fee rule disagree by $7 |
| VT | 7 | 8 | 15 | APRN transition-to-practice agreement (24 mo / 2,400 h) |
| ME | 6 | 8 | 14 | APRN pharmacology hours fall on **non**-prescribers |
| **Total** | **88** | **94** | **182** | 23 of 24 jurisdiction × licence-type pairs |

All twelve jurisdictions were reached. NJ/MD is the only pair with zero rows,
and that is a source-access failure, not an omission of effort.

### Field keys seeded

`renewal_cycle_months` (22), `ce_hours_total` (22), `ce_cycle_months` (22),
`initial_license_fee_cents` (20), `renewal_fee_cents` (18),
`renewal_window_days` (7), `csr_required` (6), `csr_renewal_cycle_months` (6),
`csr_fee_cents` (6), `collaborative_agreement_required` (5),
`ce_topic_pharmacotherapeutics_hours` (5), `ce_topic_controlled_substance_hours` (4),
`ce_topic_opioid_hours` (4), `ce_topic_risk_management_hours` (4),
`ce_topic_substance_abuse_hours` (3), `fingerprint_required` (2),
`supervision_required` (2), `ce_topic_child_abuse_hours` (2),
`ce_topic_cultural_competency_hours` (2), `ce_topic_domestic_violence_hours` (2),
`ce_topic_end_of_life_care_hours` (2), `ce_topic_infectious_disease_hours` (2),
`ce_topic_lgbtq_cultural_competency_hours` (2),
`ce_topic_public_health_priority_hours` (2), `ce_topic_sexual_assault_hours` (2),
`ce_topic_veterans_behavioral_health_hours` (2),
`ce_topic_abuse_and_trafficking_recognition_hours` (1),
`ce_topic_alzheimers_hours` (1), `ce_topic_medication_administration_hours` (1),
`ce_topic_organ_donation_hours` (1), `ce_topic_pain_management_hours` (1),
`ce_topic_professional_boundaries_hours` (1).

**Fifteen `ce_topic_*` keys are new** and are listed in the header of
`requirements_seed_group_a.sql`. Every one of them is a real published mandate
that the brief's topic vocabulary had no slot for; none was invented to pad the
table, and none is a synonym of an existing key:
`ce_topic_risk_management_hours`, `ce_topic_child_abuse_hours`,
`ce_topic_organ_donation_hours`, `ce_topic_infectious_disease_hours`,
`ce_topic_sexual_assault_hours`, `ce_topic_cultural_competency_hours`,
`ce_topic_veterans_behavioral_health_hours`, `ce_topic_substance_abuse_hours`,
`ce_topic_abuse_and_trafficking_recognition_hours`,
`ce_topic_lgbtq_cultural_competency_hours`,
`ce_topic_public_health_priority_hours`, `ce_topic_end_of_life_care_hours`,
`ce_topic_alzheimers_hours`, `ce_topic_professional_boundaries_hours`,
`ce_topic_medication_administration_hours`.

Note `ce_topic_abuse_and_trafficking_recognition_hours`: Delaware mandates ONE
hour covering "sexual abuse, physical abuse, exploitation, trafficking, or
domestic violence". Splitting it across `ce_topic_human_trafficking_hours` and
`ce_topic_domestic_violence_hours` would double-count a single hour, so it has
its own key.

### The five things a consumer must know about this group

**1. Connecticut runs three independent clocks and none of them is 24 months
together.** The physician and APRN licences renew **annually** in the birth
month. CME runs on a **24-month** lookback. The Department of Consumer
Protection controlled substance registration renews **biennially on 28
February of odd years**. Every neighbouring state in this file renews
biennially, so anything that infers Connecticut from a neighbour is wrong by a
factor of two on the licence and wrong on the anchor date for the CSR.

**2. Four of twelve jurisdictions have a live state controlled substance
registration, and in three of them it does not share the licence clock.**

| State | Issuer | Fee | Cycle / anchor | Licence anchor |
|---|---|---|---|---|
| CT | Dept of Consumer Protection | $40 / $40 | 24 mo, 28 Feb odd years | **12 mo, birth month** |
| DE | Div. of Professional Regulation | $210 application (renewal fee unpublished) | 24 mo, **30 Jun odd years** | MD **31 Mar odd years**; APRN 28 Feb / 31 May / 30 Sep odd years |
| RI | Dept of Health | $200 practitioner | renewed with the licence | MD 30 Jun even years; APRN 1 Mar |
| MA | *(unverified — near miss)* | — | — | — |

Delaware's CSR additionally carries its own CE duty: a one-hour mandatory course
at application and a **two-hour attestation at each CSR renewal**, on the CSR
clock, not the licence clock. That is seeded as `value_json` under
`ce_topic_controlled_substance_hours` with
`"periodicity": "per_csr_renewal_cycle"`.

**3. Maine's pharmacology CE is inverted relative to every other state here.**
PA (16 h), CT (5 h), NH (5 h) and DC (15 h) attach pharmacology hours to
prescribing APRNs or to all APRNs. Maine attaches its 15 hours to a nurse
practitioner or certified nurse midwife who **does not** prescribe. Pattern-
matching on the field_key across states assigns this to exactly the wrong Maine
licensees. Flagged as an open conflict so the inversion is not normalised away.

**4. `ce_hours_total` is `value_json` in Georgia and Maryland because the hours
are optional.** Both states let a nurse satisfy continuing competency by
maintaining national certification, by practice hours, or by an academic
programme — the CE hours are one option of several. Since every APRN in both
states must hold current national certification anyway, the certification option
will satisfy the requirement for essentially the whole APRN population and the
hour figure will rarely bind. A bare `30` would invoice a duty most of them do
not owe.

**5. Three states tier APRN practice authority, and each names a different
instrument.** Massachusetts: *supervision by a Qualified Healthcare Professional*
under *mutually agreed upon guidelines*, ending at 2 years, and **only for
prescriptive practice** → `supervision_required`, `value_json`. Vermont: a
*formal agreement with a collaborating provider*, ending at 24 months **and**
2,400 hours → `collaborative_agreement_required`, `value_json`. Maine: 24 months
of *supervision* by a physician **or** a supervising NP **or** employment by a
clinic with a medical director → `supervision_required`, `value_json`. Rhode
Island is the counter-example and is a bare `false`: its regulation says
collaboration "does not require such relationship to be evidenced by a written
collaboration agreement" — an affirmative negative, not silence.

### Where two official sources disagreed

Seven cases. In every one the seeded value is what the licensee actually faces,
and the disagreement is an open conflict.

| Field | Source A | Source B | Seeded |
|---|---|---|---|
| `PA/MD/ce_topic_opioid_hours` | Board CME requirements document: "at least **two** hours" | Board Physician & Surgeon Licensure Snapshot: "**4 hours** … 2 hours in pain management … and 2 hours in … prescribing or dispensing of opioids" | **2** (the document whose sole purpose is to state CME requirements). The snapshot reads a statutory *or* as an *and*. |
| `MD/MD/ce_hours_total` | COMAR 10.32.01.10C(1) and the Board renewal page: 50 credits Category I **or** II, ≥25 Category 1 | Board Physician Renewal FAQ: "at least 50 **Category 1** CME credits" | the regulation. The FAQ would double the Category 1 burden. |
| `DC/APRN/ce_topic_public_health_priority_hours` | Licensee notice OS-26-03-05 (current cycle): **2.5** hours | 2024 RN/APRN Renewal FAQ: **3** hours | **2.5** (current cycle). |
| `DC/APRN/renewal_fee_cents` | Licensee notice OS-26-03-05: **$263** | 2024 Renewal FAQ: **$118** + $50 CBC | **$263** — what is charged now. |
| `NH/MD/initial_license_fee_cents` and `renewal_fee_cents` | OPLC Board of Medicine fee page: **$378.00** (incl. $28 PHP) | N.H. Admin. R. Plc 1002.28: **$385** | **$378** — the board's published charge. |
| `CT/APRN` topic hours (6 rows) | DPH APRN CE page: per-24-month hours, no recurrence qualifier | DPH physician CME page: the same topics on "first renewal, then every six years" | the APRN page (per cycle). If the six-year clock in fact applies, the platform over-generates threefold. |
| `DC/MD/ce_hours_total` | Board of Medicine page: 50 hours, no category restriction, plus two mandated topics | 17 DCMR § 4614.2 (2012 compilation): 50 **AMA/PRA Category I** hours, no topics | the board page — the 2012 compilation predates the 3/13/2020 amendment. |

### Values that could not be verified — the headline items

Full detail, with what was searched and what remains open, is in
`requirement_conflicts_seed_group_a.sql`.

| What | Why it is not seeded |
|---|---|
| **All of NJ/MD; most of NJ/APRN** | `njconsumeraffairs.gov` is behind an Imperva/Incapsula bot wall that returned HTTP 403 with incident IDs to every path but two, from two clients and two user agents. New Jersey does not publish the N.J.A.C. on a state-hosted site (it is licensed to LexisNexis), so N.J.A.C. 13:35 and 13:37 could not be read. Third-party republishers (Cornell LII, Justia) are excluded by the standard. **Two rows only: the joint-protocol requirement and a `value_json` initial fee.** |
| **`csr_required` for PA, NJ, GA, MA, MD, DC, NH, VT, ME** | No affirmative statement either way was found. Massachusetts is the closest call — 244 CMR 4.00 tells an APRN with prescriptive authority to "register with the Department of Public Health's Drug Control Program", which is almost certainly a state CSR, but the Board does not name it as one and no DPH page was read. **Given that 4 of the 12 jurisdictions checked *do* have a live CSR, this is the single largest remaining gap in the group.** |
| **`fingerprint_required` for 9 of 12 jurisdictions** | Verified only for GA/MD and MD/MD. DC is a deliberate near miss: DC Health charges a $50 Criminal Background Check at every renewal but never says it is fingerprint-based. Maine is a partial: fingerprints are an Interstate Medical Licensure Compact condition, not a Maine condition. |
| **`renewal_window_days` for most pairs** | Seeded only where a board published a transactional open date (MA/APRN 90, VT/APRN 42) or an explicit date range (GA/APRN 92, MD/MD 78), or a notification date that is flagged as such (PA/MD 60, CT/MD 60, CT/APRN 60). GA/MD, RI and DE publish a *notice* cadence; MA/MD names no interval at all. A notice is not a window. |
| **MD (Maryland) implicit bias / structural racism CME** | Both board notices say explicitly that it is a **one-time** requirement, and **neither publishes an hour count**. A key that can only hold hours cannot carry it without inventing the magnitude. Existence and one-time periodicity are recorded in the conflicts file. |
| **DC/MD fees** | The DC Health "Medicine Fee Schedule" page publishes no amounts: "All fees are set by regulation, and can be found on the relevant application." |
| **DE renewal fees (both professions), DE CSR renewal fee** | Every Delaware fee schedule says "You are notified of the amount of the renewal fee at the time of renewal." Only application fees are published anywhere. `csr_fee_cents` is seeded from the **application** fee and says so in its citation. |
| **DE/APRN practice authority** | 24 Del. C. ch. 19 defines full-practice authority and contains no collaboration mandate — an absence, not an affirmative negative. `false` was not seeded from it. |
| **CT/APRN collaboration threshold** | Connecticut's three-year / 2,000-hour transition is widely described but was not found on any `portal.ct.gov` page read, and `cga.ct.gov/current/PUB/chap_370.htm` returned repeated server errors. A threshold written from recall is exactly what this standard excludes. |
| **PA/APRN opioid CE hours** | The Board of Nursing lists "Opioid education for CRNPs with prescriptive authority" as a renewal requirement and publishes **no hour count**. The requirement demonstrably exists; the number does not. |
| **DE "the Mandatory Training" for physicians** | The Board's renewal page makes physicians attest to "the Mandatory Training" alongside CME. No Delaware page read describes what it is. |
| **MA/APRN and MA/MD topic hours** | 244 CMR 5.00 mandates no topic at all; the Board's web page points nurses at Chapter 260 domestic and sexual violence training with no hour count. For physicians, domestic violence and child abuse training are *initial-licensure* conditions with no published credit amount. |
| **NH RN continuing education hours** | RSA 326-B:31, III makes the APRN's 30 hours "**in addition to** the continuing education requirements to renew … as an RN", and the RN hour count could not be read (`oplc.nh.gov` returned HTTP 403 Akamai "Access Denied" to every fetch). Reporting 30 as New Hampshire's total APRN CE burden **understates** it. |

### Schema gaps this pass surfaced

1. **No anchor dates.** The table holds interval lengths but no anchor. A
   Delaware physician renews the licence 31 March odd years and the CSR 30 June
   odd years; a Connecticut physician renews the licence in their birth month
   annually, attests CME over a rolling 24 months, and renews the CSR 28
   February odd years. Without `renewal_anchor_date` / `csr_anchor_date` the
   platform cannot date any of these duties.
2. **No slot for topic periodicity** — the same gap the first four states logged,
   worse here. 27 of the 182 rows are `value_json` for periodicity or population
   reasons, including six Connecticut topics on a "first renewal then every six
   years" clock, two Georgia once-in-a-career duties, three Massachusetts
   one-time duties, and two Delaware topics on the **CSR** clock. Any consumer
   that reads `value_num` and ignores `value_json` drops all of them.
3. **No slot for a requirement that is not hours.** Vermont requires an APRN to
   have practised 400 hours in two years (or 960 in five) and to hold current
   national certification; Georgia, Maryland and Massachusetts all condition
   APRN renewal on national certification; Georgia bars APRNs from prescribing
   Schedule I and II; Delaware imposes re-entry pharmacotherapeutics hours after
   an absence. All can block a renewal; none is expressible. Suggest
   `practice_hours_required`, `national_certification_required`,
   `prescribing_schedule_restriction`.
4. **`initial_license_fee_cents` is sometimes not a scalar.** New Jersey's
   initial APN certificate is $80 or $160 depending on the remaining term of the
   applicant's RN licence, so that row is `value_json`. DC publishes three
   different APRN initial paths ($145 dual, $230 single, $34 reactivation) and is
   therefore unseeded. The field should probably permit `value_json` by
   convention.
5. **No slot for a one-time requirement with no hour count.** Maryland's implicit
   bias / structural racism attestation and DC's "at least one course in
   pharmacology" are both real, both mandatory, and both unrepresentable.

### Explicitly not covered

- **`license_type = 'DO'` — no coverage.** In DE, RI, VT, ME, NH, MD, DC and MA
  one authority licenses MDs and DOs (Delaware's renewal page names "Physician
  M.D & D.O." on one line; Rhode Island's CME regulation covers physicians
  "licensed to practice allopathic or osteopathic medicine"), so the MD rows are
  *likely* to hold — "likely" is not verified. **Pennsylvania's State Board of
  Osteopathic Medicine is a separate board** with its own renewal guide, fee
  schedule and CME requirements, and the PA/MD rows must **not** be applied to a
  Pennsylvania DO. GA, NJ, CT and MD were not checked for board separation.
- **Only the licence and, where verified, the state CSR.** DEA registration,
  CMS/Medicare enrolment, hospital privileges, malpractice and board
  certification are out of scope.
- **Rhode Island topic CME is a gap, not a zero.** The Board states "There are no
  specific topics required … **for this license renewal cycle**", scoping the
  statement to one cycle. It is recorded as an open conflict so no consumer
  caches "Rhode Island has no topic CME" as a standing fact.

### Authorities read

| Jurisdiction | Authorities |
|---|---|
| PA | Dept of State, BPOA — State Board of Medicine renewal information, CME requirements for an unrestricted MD licence, Physician & Surgeon Licensure Snapshot, IMLC renewal guide; State Board of Nursing — CRNP and RN Licensure Snapshots, renewal information, Tips for Renewal, CRNP Prescriptive Authority Collaborative Agreement Application Guide (`pa.gov`) |
| NJ | Board of Nursing — Advanced Practice Nurse Certification page and APN certification application (`njconsumeraffairs.gov`) |
| GA | Georgia Composite Medical Board — physician, CE and other required training, fee schedule (`medicalboard.georgia.gov`); Georgia Board of Nursing — nursing CE, renewal information, fee schedule, How to Guide: APRN (`sos.ga.gov`); Ga. Comp. R. & Regs. chs. 410-11 and 410-13 (`rules.sos.ga.gov`) |
| MA | Board of Registration in Medicine — CME requirements, CME Pilot Program, Alzheimer's CME notice, renewal, schedule of fees; Board of Registration in Nursing — 244 CMR 4.00 and 5.00, mandatory CE, renew your nursing licence, apply for APRN authorization (`mass.gov`) |
| CT | DPH Practitioner Licensing & Investigations — physician CME, physician licensure, APRN CE, APRN licensure requirements, health care practitioner renewal information, licence types that expire biennially, general policies and procedures, nursing renewal knowledge-base article; Dept of Consumer Protection — Controlled Substance Practitioner Registration (`portal.ct.gov`) |
| MD | Board of Physicians — physician licence renewals, 2025 renewal information, physician licensure information, implicit bias notice, structural racism notice (`mbp.state.md.us`, `health.maryland.gov`); COMAR 10.32.01.10, 10.27.01.13, 10.27.07.04 (`regs.maryland.gov`); Board of Nursing schedule of fees (`health.maryland.gov/mbon`) |
| DC | DC Health — Board of Medicine, licensee notice OS-26-03-05, RN/APRN 2024 renewal FAQ, APRN page, medicine fee schedule (`dchealth.dc.gov`); 17 DCMR ch. 46 regulations compilation (`doh.dc.gov`) |
| DE | Division of Professional Regulation — Board of Medical Licensure & Discipline (renewal, CE and audit, fees); Board of Nursing (renewal, CE and audit, APRN licence, fees); Controlled Substances (practitioner CSR, APRN CSR, renewal, fees, mandatory course) (`dpr.delaware.gov`); 24 Del. C. ch. 19 (`delcode.delaware.gov`) |
| RI | Dept of Health — physician application requirements, physicians licensing, nurses licensing, Uniform Controlled Substances Act Registration application (`health.ri.gov`); 216-RICR-40-05-1, 216-RICR-40-05-3, 216-RICR-10-05-2 (`rules.sos.ri.gov`) |
| NH | OPLC — Board of Medicine physician licensure requirements and licence fees (`oplc.nh.gov`); RSA 329 and RSA 326-B; N.H. Admin. R. Plc 1000 (`gc.nh.gov`) |
| VT | Dept of Health, Board of Medical Practice — applications/licensing/fees, CME Hour Requirements FAQ (`healthvermont.gov`); Board of Nursing administrative rules (`outside.vermont.gov`), nursing apply/renew (`sos.vermont.gov`); 26 V.S.A. §§ 1577, 1614 (`legislature.vermont.gov`) |
| ME | Board of Licensure in Medicine — licence FAQ, MD licence (`maine.gov/md`); State Board of Nursing — APRN FAQs, 02-380 CMR ch. 8, fees (`maine.gov/boardofnursing`); 32 M.R.S. § 2206 (`legislature.maine.gov`) |

No CE aggregator, licence-service marketplace, "2026 renewal guide" content farm
or third-party code republisher was used as a citation anywhere in this group,
and nothing was carried across from a neighbouring state, from one profession to
another, or from one board to another board in the same state.

### Hosts that blocked verification on 2026-09-18

`njconsumeraffairs.gov` (Imperva/Incapsula bot wall, HTTP 403 on every path but
two); `www.oplc.nh.gov` (Akamai "Access Denied", HTTP 403 — Board of Nursing fee
page, nursing FAQ, APRN checklists, Board of Medicine laws and rules);
`pacodeandbulletin.gov` (disallowed by robots.txt — 49 Pa. Code chs. 16, 18, 21);
`www.cga.ct.gov/current/PUB/chap_370.htm` (repeated server errors — C.G.S.
Medicine and Surgery); `www.dcregs.dc.gov` (serves section metadata, not section
text — current 17 DCMR §§ 4601 and 4614); `goals.sos.ga.gov` fee portal
(JavaScript shell, CSS error); `www1.maine.gov/boardofnursing/licensing/renew-license.html`
(HTTP 502). Each is named in the relevant conflict row, and in every case an
alternative primary source was sought before the gap was recorded.

---

## Group E — AR, OK, KS, NJ, WV (the five states earlier passes could not reach)

Files: `requirements_seed_group_e.sql`, `requirement_conflicts_seed_group_e.sql`
`verified_by` / `observed_by`: `research-agent-group-e`
Verified: 2026-09-18. Applied against PostgreSQL 16.13 on a throwaway cluster:
all `db/migrations/*.sql` in order, then every seed file in `db/seeds/` in name
order, then in dependency order (requirements before conflicts) twice. No
constraint violation, no `ux_requirements_current` collision, every row
populates exactly one value column, every row carries a `citation_url`, and the
second pass is a no-op. Final database: **664 `requirements` rows, 301
`requirement_conflicts` rows** across 49 states + DC.

**69 new `requirements` rows, 40 open `requirement_conflicts` rows** (20
qualifiers, 20 gaps). 18 of the 69 rows are `value_json`.

### Coverage matrix — before and after this pass

| State | Before (MD/APRN) | Added here (MD/APRN) | **Now (MD/APRN/total)** |
|-------|-----------------:|---------------------:|------------------------:|
| AR | 0 / 0 | 6 / 8 | **6 / 8 / 14** |
| OK | 0 / 0 | 9 / 11 | **9 / 11 / 20** |
| KS | 0 / 1 | 6 / 7 | **6 / 8 / 14** |
| NJ | 0 / 2 | 3 / 2 | **3 / 4 / 7** |
| WV | 4 / 0 | 7 / 10 | **11 / 10 / 21** |
| **Total** | **4 / 3** | **31 / 38** | **35 / 41 / 76** |

New Jersey is still the thinnest jurisdiction in the asset and the section
"New Jersey — what moved and what did not" below says exactly why.

### Field keys seeded

`initial_license_fee_cents` (8), `renewal_fee_cents` (8), `ce_hours_total` (7),
`renewal_cycle_months` (7), `ce_cycle_months` (6), `csr_fee_cents` (5),
`csr_required` (5), `renewal_window_days` (4),
`ce_topic_pharmacotherapeutics_hours` (3), `collaborative_agreement_required` (3),
`csr_renewal_cycle_months` (3), `fingerprint_required` (3),
`ce_topic_opioid_hours` (2), `ce_topic_pain_management_hours` (2),
`ce_topic_controlled_substance_hours` (1), `ce_topic_nutrition_hours` (1),
`supervision_required` (1).

**ONE new `field_key`: `ce_topic_nutrition_hours` (WV/MD).** West Virginia's
Board of Medicine adopted an emergency legislative rule — 11 CSR 6, filed
30 June 2026, effective 11 August 2026, sunset 1 August 2032 — that inserts a
mandatory **2 hours of Nutrition CME** into all three of the physician CME
options (§§ 4.1.1.b, 4.1.2.a, 4.1.3.a) and defines "Nutrition CME" at § 2.12.
Nothing in the existing vocabulary covers it. **It is not on the Board's own
Continuing Education web page**, which is the source the Group B pass read, so a
West Virginia physician planning from that page will miss it.

### The five things a consumer must know about this group

1. **Three of the five states run the licence clock and the CE clock at
   different speeds, and Oklahoma runs four clocks at once.** An Oklahoma
   physician reregisters **annually** in the month of initial licensure with **no
   grace period** (OAC 435:10-7-10), certifies **60 Category I hours every three
   years** (435:10-15-1), owes **1 hour of pain-management or opioid CME every
   year** if DEA-registered (59 O.S. § 495a.1(C)), and renews the OBNDD
   controlled-dangerous-substances registration **every year on 31 October**.
   Arkansas physicians run a 12-month licence and a 12-month CE clock but a
   birth-month anchor. Kansas physicians renew **annually** while K.A.R. 100-15-5
   measures CE over **18, 30 or 42 months**. Read `renewal_cycle_months`,
   `ce_cycle_months` and `csr_renewal_cycle_months` independently.
2. **A state controlled substance registration exists in Oklahoma, New Jersey
   and (conditionally) West Virginia — and in two of them it gates the DEA
   registration.**

   | State | Instrument | Who issues it | Cycle | Fee | Note |
   |---|---|---|---|---|---|
   | OK | Controlled dangerous substances registration | **OBNDD**, not the medical or nursing board | **12 mo, expires 31 Oct** | $140 | renewals timely only if filed by 1 Sept |
   | NJ | CDS registration | Division of Consumer Affairs **Drug Control Unit** | **not published** | $40 | **"A New Jersey CDS registration is the prerequisite to the federal DEA registration."** Per practice location. |
   | WV (MD) | Controlled Substance Dispensing Practitioner Registration | Board of Medicine | 24 mo, with the licence | **$30 or $15 per location**, by alphabetical cohort | **only for office-based dispensing/administering — not for writing prescriptions** |
   | AR, KS | **unknown — not seeded** | — | — | — | no affirmative source either way; see conflicts |
   | WV (APRN) | **unknown — not seeded** | — | — | — | CSMP enrolment is a PDMP, not a CSR |

   A consumer that renews the CSR alongside the licence will let an Oklahoma
   registration lapse every other year, and a New Jersey licensee who lets the
   CDS lapse loses the DEA registration with it.
3. **West Virginia renews RNs in even years and APRNs in odd years, and the
   APRN licence dies with the RN licence.** The Board states: "If your underlying
   RN license lapses or becomes invalid, your APRN license and Prescriptive
   Authority will automatically lapse as well, **regardless of the APRN odd-year
   renewal schedule**." A platform tracking only the APRN's 24-month odd-year
   clock will show a West Virginia APRN as compliant right through the even year
   in which their RN licence quietly expires. This is the single most dangerous
   clock in the group.
4. **Topic hours in this group are usually carved OUT OF the total, not added to
   it.** Flagged as `"additive": false` with `subset_of_field_key` on
   `AR/MD/ce_topic_opioid_hours` (1 of the 20), `KS/MD/ce_topic_opioid_hours`
   (1 category III credit of the 50), `WV/APRN/ce_topic_pharmacotherapeutics_hours`
   (12 of the 24) and `WV/MD/ce_topic_nutrition_hours` (2 of the 50 under
   Option 1, but standalone under Options 2 and 3). **Summing topic hours onto
   `ce_hours_total` over-bills every one of those.**
5. **An APRN hour count in this group is frequently one option on a menu, or an
   RN duty wearing an APRN label.** `AR/APRN/ce_hours_total` and
   `OK/APRN/ce_hours_total` are both `value_json`: Arkansas offers 15 contact
   hours **or** current national certification **or** a college credit hour, and
   Oklahoma offers 520 work hours **or** 24 contact hours **or** specialty
   certification **or** a refresher course **or** 6 academic credit hours — and
   in both states the duty attaches to the **RN** licence, while the APRN
   licence itself (OAC 485:10-15-5, ASBN APRN renewal) requires only current
   national certification. Both states separately require national
   certification at APRN renewal, so the hour count will rarely bind. Kansas is
   the exception: K.S.A./KSBN states a flat **30 contact hours "related to the
   advanced practice registered nurse role"**, and that one is a real `value_num`.

### Where official sources disagreed

| Field | Source A | Source B | Seeded |
|---|---|---|---|
| `WV/MD/ce_topic_controlled_substance_hours` (**Group B's row**) | Board of Medicine **website**: 3 hours "during each reporting period. This is not a one-time only requirement." | Board of Medicine **legislative rule 11 CSR 6 § 3.1** (emergency, eff. 11 Aug 2026): 3 hours "Within one year of receiving an initial license", and § 11-6-4 (Periodic CE) names no controlled-substance topic at all | **unchanged** — over-scheduling a 3-hour course is a smaller harm than telling a prescriber they are finished. Logged as an open conflict with `requirement_id` NULL. Caveat recorded: the rule PDF is a redline and struck-through text does not survive extraction, so a deleted recurring clause would be invisible. |
| `WV/MD/ce_hours_total` (**Group B's row**) | Board CE sheet / website: 50 hours | 11 CSR 6 § 4.1: 50 hours is **Option 1 of three**; Options 2 (ABMS certification / MOC) and 3 (12 months ACGME training) require **2 hours and no more** | **unchanged** (only one current row per key is allowed). Logged: a board-certified physician in MOC owes 2 hours, not 50. |
| `AR/MD/renewal_fee_cents` and `initial_license_fee_cents` | Board fee schedule PDF, re-published **10 August 2026**: $11 renewal / $120 initial | **the same PDF**: the Act 114 of 2023 reduction "will be in effect beginning July 1, 2023 and **end June 30, 2026**" | the published $11 / $120 — it is the only amount the Board publishes — with a loud open conflict |
| `WV/APRN` vs `WV/MD` controlled-substance CME | Board of Registered Nurses: 3 hours **once**, within 1 year of initial licensure, waivable | Board of Medicine website: **every** reporting period | each board's own statement for its own licensees; asymmetry logged |

### Values that could not be sourced — the headline items

- **`csr_required` for Arkansas and Kansas, in either direction.** Arkansas is
  the frustrating one: the ADH Controlled Substances page lists only
  researchers, instructors, chemical analysts and animal handlers as needing a
  state certificate, and the ADH controlled-substances rule points practitioners
  at the **federal** DEA registration. That reads like a clean `false` — which
  would be worth as much as a `true` and would save every Arkansas client a
  filing — but a negative cannot be asserted from a list that merely omits a
  category. **Not seeded in either direction.**
- **`ce_cycle_months` for KS/MD.** K.A.R. 100-15-5 measures 50 credits over
  18 months, 100 over 30, or 150 over 42, all "immediately preceding the license
  expiration date", while the licence renews annually. The regulation does not
  say which option a continuously-renewing licensee uses. Seeding 12 (the
  renewal cycle) or 18 (the shortest lookback) would each be an invention.
- **`fingerprint_required` for AR (both types) and OK (both types).** Arkansas
  requires "a state and federal criminal history background check report" at
  licensure **and at renewal** and charges $36.25 for it — but never writes the
  word *fingerprint*, and OAC Title 435 contains no occurrence of "fingerprint",
  "criminal history" or "background check" anywhere.
- **`renewal_window_days` for AR/MD, OK (both), WV/MD.** All four publish a
  notification date or a calendar month, not a transactional open date. Where a
  window *was* seeded it is flagged: `KS/MD` (47) and `WV/APRN` (61) are
  **derived by date arithmetic** from the board's own published dates and each
  carries an open conflict saying so.
- **New Jersey fees and CME, both licence types.** See below.
- **`csr_renewal_cycle_months` for New Jersey.** Neither the Drug Control Unit's
  application nor its registration FAQ states the term. This matters more in
  New Jersey than anywhere else because the state registration gates the DEA one.

### New Jersey — what moved and what did not

The Group A pass recorded `njconsumeraffairs.gov` as an Imperva/Incapsula wall.
That is half right and the half that is wrong is the useful half:

- **`.aspx` pages are still walled.** `/bme/Pages/renewals.aspx`,
  `/bme/Pages/FAQ.aspx`, `/bme/Pages/regulations.aspx` and
  `/renewals/Pages/RenewalsTemplateDetails.aspx` return HTTP 403, or a 212-byte
  `_Incapsula_Resource` stub to a direct fetch.
- **PDF assets on the same host serve normally.** `/documents/licenseprocess/*.pdf`,
  `/dcu/Applications/*.pdf` and `/bme/Applications/*.pdf` all returned real PDFs
  to an ordinary browser user agent. That is how NJ's CDS rows were obtained, and
  it is the lead the next pass should follow: **enumerate the Division's PDF
  asset paths rather than its pages.**
- **The N.J.A.C. is still unavailable.** The Office of Administrative Law's own
  "Access to Rules" page directs the public to `lexisnexis.com/hottopics/njcode`
  (which redirects into an `advance.lexis.com` container) and states that "the
  online version of the *Code* is not the official *Code*." N.J.A.C. 13:35-6.13
  (BME fee schedule) and 13:35-6.15 (CME) were **not** read.
- **A 2005 scan exists and was rejected.** The New Jersey State Library's dspace
  repository holds an OCR'd chapter 35 supplement (Supp. 6-6-05). It was fetched
  and read; nothing was seeded from it, because it predates New Jersey's opioid
  and cultural-competency CME mandates entirely.
- **`NJ/MD/renewal_cycle_months` = 24 is seeded from a Board document dated
  August 2017** — the only retrievable New Jersey physician renewal statement.
  The biennial odd-year structure is structural, so it was seeded; the **fees in
  the same document ($580 renewal, $325 application, $225 endorsement, $290/yr
  registration) were deliberately NOT seeded**, because a nine-year-old fee is
  exactly the kind of confidently-wrong value this asset exists to avoid.

### Schema gaps this pass surfaced

1. **The prerequisite-credential problem, stated more sharply than before.** In
   **all four** of AR, KS, OK and WV an APRN licence is derivative of an RN
   licence, and in every one of them the two credentials carry their own fee,
   their own application, and — in West Virginia — their own **renewal year**.
   Kansas requires APRNs to file *two* renewal applications ("APRNs with Kansas
   RN licenses must fill out a renewal application for both licenses"). The
   underlying RN licence may instead be a **Nurse Licensure Compact** multistate
   licence from a different state, on that state's clock and fee. Every APRN fee
   in this file is the advanced credential's fee alone and therefore
   **understates what the licensee pays**: AR $65 of $165, KS $55 of $140,
   OK $40 of $155. West Virginia is the one state that waives the RN renewal fee
   for an active APRN. Suggest `prerequisite_credential`.
2. **Fees are not always scalars.** Three more proofs here: Kansas prices the
   same annual physician renewal at **$360 on-line / $430 paper**; West Virginia
   prices its dispensing registration at **$30 or $15 per dispensing location**
   depending on the physician's alphabetical cohort; and Group A already had
   New Jersey's $80/$160 APN certificate. Groups A and E have both had to bend
   the convention — `value_json` for fees should be explicit, not an exception.
3. **Still no anchor dates, and four of these five states publish anchors rather
   than offsets.** OK: licence in the month of initial licensure, OBNDD 31 Oct,
   CME every third year. KS: physicians 15 May–30 Jun; nurses on a birth-month,
   **birth-year-parity** clock. WV: physicians 30 Jun, **A–L even years / M–Z
   odd years**; RNs 1 May–30 Jun even years; APRNs 1 May–30 Jun odd years. NJ:
   30 Jun of odd years. AR: last day of the birth month. The alphabetical and
   birth-parity cohorts cannot be expressed at all.
4. **No slot for a mandated activity with no duration.** OAC 435:10-15-1(a)(5)
   requires an Oklahoma physician who is an administrator or CEO of an inpatient
   entity to "observe the online presentation related to medical treatment laws
   described in ... 63 O.S. § 3162 ... at least once during each consecutive
   two-calendar-year period." Mandatory, on a third clock, for an occupational
   subset, **with no hour count**. Subsection (a)(6) has the same shape for
   medical-marijuana recommending physicians. Neither was seeded and no key was
   invented for them, because a topic row with a null hour count asserts nothing.
5. **No slot for a variable first term.** Arkansas publishes what other states
   hide: "The first license that is issued may be valid from three (3) months to
   twenty-seven (27) months depending upon one's birth date." Dating a first
   renewal at issuance + `renewal_cycle_months` is wrong for the whole
   new-licensee cohort, in Arkansas by up to fifteen months.

### Explicitly not covered

- **`license_type = 'DO'` — no coverage, and Oklahoma is a trap.** **Oklahoma
  has a separate State Board of Osteopathic Examiners with its own title of the
  Administrative Code (OAC Title 510)**, its own fees, its own reregistration
  rule and its own CME requirements, none of which was read. The OK/MD rows come
  from OAC Title 435 and **must not** be applied to an Oklahoma DO — the same
  hazard Group A recorded for Pennsylvania and Group B for Michigan. In
  **Arkansas** the State Medical Board licenses both and its fee schedule names
  "M.D./D.O." on one line, so the AR/MD rows are *likely* to hold for an
  Arkansas DO — "likely" is not verified. KS, NJ and WV were not checked for
  board separation.
- **Only the licence and, where verified, the state CSR.** DEA registration,
  CMS/Medicare enrolment, hospital privileges, malpractice and board
  certification are out of scope.
- **Kansas Board of Nursing regulations (K.A.R. agency 60) were never read.**
  The seeded KS/APRN rows come from the Board's own statements of what those
  regulations require, not from the regulation text. See the access note below.

### Authorities read

| Jurisdiction | Authorities |
|---|---|
| AR | Arkansas State Medical Board — Licensing FAQ, Fee Schedule, Instructions for Physician Licensure Applications (`armedicalboard.org`, `armedicalboard.adh.arkansas.gov`); Arkansas State Board of Nursing — Licensing, Fees, Renewal of Arkansas License, APRN Renewal Application Information, Continuing Education, Prescriptive Authority/Collaborative Practice, ASBN Rules ch. 2 § VII; ADH Pharmacy Services & Drug Control — Controlled Substances page and Rules & Regulations Pertaining to Controlled Substances; ADH Full Independent Practice Credentialing Committee (`healthy.arkansas.gov`) |
| OK | Oklahoma State Board of Medical Licensure and Supervision — Licensing FAQ, CME Guidelines, Laws page, and **OAC Title 435 as the Board publishes it, effective 1 September 2026** (`okmedicalboard.org`), cross-read against the Secretary of State's Title 435 PDF (`oklahomarules.blob.core.windows.net`); Oklahoma Board of Nursing — **OAC Title 485 effective 11 July 2026**, Title 485 Rules page, continuing-qualifications handout (`oklahoma.gov/nursing`); Oklahoma Bureau of Narcotics and Dangerous Drugs Control — Registration, Registration & PMP, Rules & Regulations, and its published 2025 OAC Title 475 (`obndd.ok.gov`) |
| KS | Kansas State Board of Healing Arts — License Fees, Renewal Dates (`ksbha.ks.gov`) and K.A.R. 100-15-4 and 100-15-5 as the Board publishes them (`ksbha.org`); Kansas State Board of Nursing — Agency Fees, Renewal Application, Continuing Nursing Education, Fingerprints & Background Check, Information Center, License Renewal Application form (`ksbn.kansas.gov`); K.S.A. 65-2809 and 65-1130 (`ksrevisor.gov`) |
| NJ | Division of Consumer Affairs — State Board of Medical Examiners landing page and "LICENSING and the APPLICATION PROCESS" (Aug 2017); Board of Nursing APN Certification; **Drug Control Unit CDS Registration Initial Application (rev. 4/25)**, CDS Reinstatement Application and registration FAQ (`njconsumeraffairs.gov`); Office of Administrative Law "Access to Rules" (`nj.gov/oal`); New Jersey State Library dspace scan of N.J.A.C. 13:35 (Supp. 6-6-05), read and rejected as stale |
| WV | Board of Medicine — Instructions for Physician Licensure Applications (rev. July 2025), Controlled Substance Dispensing Practitioner Registration Application, Legislative & Procedural Rules index, **11 CSR 4 (Fees for Services Rendered)** and **11 CSR 6 (Continuing Education, emergency rule eff. 11 Aug 2026)** (`wvbom.wv.gov`); Board of Registered Nurses — Renewals, Fees and Waivers, Continuing Education, Prescriptive Authority, Licensure Requirements (`wvrnboard.wv.gov`) |

No CE aggregator, licence-service marketplace, "2026 renewal guide" content farm
or third-party code republisher (Cornell LII, Justia, `regulations.justia.com`,
Casetext) was used as a citation anywhere in this group — not even as an
orientation citation — and nothing was carried across from a neighbouring state,
from one profession to another, or from one board to another board in the same
state.

### Hosts that blocked verification on 2026-09-18, and how each was worked around

| Host | Failure | Outcome |
|---|---|---|
| `www.obndd.ok.gov` | Akamai "Access Denied", HTTP 403 to direct fetch (the Group B failure) | **read** through a fetcher with its own egress — this is how Oklahoma's `csr_required`, `csr_fee_cents` and `csr_renewal_cycle_months` were finally established |
| `www.ksbha.ks.gov` | Akamai "Access Denied", HTTP 403 with browser headers | **read** through a fetcher |
| `www.okmedicalboard.org` | HTTP 403 on HTML pages to direct fetch | PDF assets fetch normally with a browser UA; **the Board's full Title 435 rules PDF was downloaded and read** |
| `oklahomarules.blob.core.windows.net` | proxy 502 to direct fetch | **read** through a fetcher |
| `ksbha.org` (legacy host, still serves K.A.R. PDFs) | **expired TLS certificate**, and outside the direct-fetch allowlist | **read** through a fetcher that does not fail on the certificate |
| `rules.ks.gov` (Kansas SoS, official K.A.R.) | JavaScript SPA; only `/browse`, `/search`, `/smart-search` routes; API paths return S3 `AccessDenied` | **not read** — K.A.R. agency 60 is an open gap |
| `sos.ks.gov/publications/pubs_kar*.aspx` | CloudFront 403 | **not read** |
| `www.njconsumeraffairs.gov` | Imperva/Incapsula on `.aspx` only | **PDF assets read**; pages not |
| `www.oscn.net` (Oklahoma Statutes) | robots.txt fetch failure | **not read** — 63 O.S. § 2-302 and 59 O.S. § 495a.1 relied on only as quoted by the agencies' own rules |
| `www.nj.gov/.../BME_regulations.pdf` | 2.6 MB image-only scan, no text layer | **not usable** |
| `wvbom.wv.gov` fee handout | fee digits do not survive extraction (the Group B failure) | **irrelevant** — the fees are in the Board's legislative rule **11 CSR 4**, which extracts cleanly ($400 application, $400 active biennial renewal) |

Each is named in the relevant conflict row, and in every case an alternative
primary source was sought before a gap was recorded.
