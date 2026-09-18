# `db/seeds` — the rules asset

Seed data for the `requirements` and `requirement_conflicts` tables
(PRD 5.3, migration `0004_rules.sql`).

This is the company's core asset. Its value is entirely in being **cited and
correct**. Read the verification standard below before you add a row.

---

## Loading

The seeds assume all migrations have already been applied, in order.

```bash
for f in db/migrations/*.sql; do psql -v ON_ERROR_STOP=1 -d "$DB" -f "$f"; done

# Order matters: conflicts reference requirements by FK.
psql -v ON_ERROR_STOP=1 -d "$DB" -f db/seeds/00_requirements_base.sql
psql -v ON_ERROR_STOP=1 -d "$DB" -f db/seeds/20_conflicts_base.sql
```

Both files are idempotent and transactional. Each deletes only the rows it owns
(`verified_by = 'research-agent'` / `observed_by = 'research-agent'`, scoped to
CA/FL/TX/NY and MD/APRN) and reinserts them. `00_requirements_base.sql` also clears
the dependent `requirement_conflicts` rows first, which is why it must run
first and `20_conflicts_base.sql` must run after it — re-running the
requirements file alone leaves the conflicts table empty until you re-run the
conflicts file.

Verified against PostgreSQL 16.13 on 2026-09-18: all migrations plus both seeds
apply with no constraint violation, and re-running both twice is a no-op.

---

## The verification standard held to

> **A missing value is correct. An invented value is a defect.**

A wrong `renewal_cycle_months` produces a confidently wrong obligation calendar
that a client acts on. That is worse than an empty cell, because an empty cell
is visibly empty.

Concretely, every row in `00_requirements_base.sql`:

1. **Carries a citation to a primary source** — a state board page, a state
   statute, or a board rule. Third-party CE aggregators and summary sites were
   not used and are not citations.
2. **Carries a `citation_url` that was actually fetched and read on
   2026-09-18.** Not a plausible URL; a retrieved one. `citation` quotes the
   source's own words wherever a number is asserted, so a reviewer can check the
   row without re-fetching.
3. **Was not inferred.** Nothing was carried across from a sibling state, from
   one profession to another, or from one board to another board in the same
   state. Where a board is silent, the row is absent — silence is not a zero
   and is not a "no".

Anything that failed any of those tests is in `20_conflicts_base.sql`
with `resolution = 'unresolved'`, which blocks auto-clear (PRD 8.1 condition 6)
and raises `RULE_UNCERTAIN` (PRD 8.3). That is the designed behaviour for a
value the system does not know, and it is why the conflicts file is a
deliverable rather than an apology.

**This table is honestly sparse. Do not fill it in to make it look complete.**

---

## Coverage

71 `requirements` rows, 33 open `requirement_conflicts` rows.

| State | License type | Verified field keys |
|-------|--------------|--------------------:|
| CA | MD   |  8 |
| CA | APRN |  9 |
| FL | MD   |  9 |
| FL | APRN | 14 |
| TX | MD   | 10 |
| TX | APRN |  9 |
| NY | MD   |  5 |
| NY | APRN |  7 |

Field keys seeded at least once: `renewal_cycle_months`, `renewal_window_days`,
`ce_hours_total`, `ce_cycle_months`, `ce_topic_controlled_substance_hours`,
`ce_topic_domestic_violence_hours`, `ce_topic_ethics_hours`,
`ce_topic_hiv_aids_hours`, `ce_topic_human_trafficking_hours`,
`ce_topic_impairment_hours`, `ce_topic_implicit_bias_hours`,
`ce_topic_jurisprudence_ethics_hours`, `ce_topic_laws_and_rules_hours`,
`ce_topic_medical_errors_hours`, `ce_topic_opioid_hours`,
`ce_topic_pain_management_hours`, `ce_topic_pharmacotherapeutics_hours`,
`csr_required`, `collaborative_agreement_required`, `fingerprint_required`,
`supervision_required`, `initial_license_fee_cents`, `renewal_fee_cents`.

### Sources used

| Jurisdiction | Authorities read |
|---|---|
| CA | Medical Board of California (`mbc.ca.gov`); Board of Registered Nursing (`rn.ca.gov`) |
| FL | Board of Medicine (`flboardofmedicine.gov`); Board of Nursing (`floridasnursing.gov`); Florida Statutes (`leg.state.fl.us`) |
| TX | Texas Medical Board (`tmb.texas.gov`); Texas Board of Nursing (`bon.texas.gov`); Texas Occupations Code (`statutes.capitol.texas.gov`) |
| NY | NYSED Office of the Professions (`op.nysed.gov`); NYS DOH Bureau of Narcotic Enforcement (`health.ny.gov`) |

---

## Explicitly NOT covered

Read this before querying the table for anything.

- **`license_type = 'DO'` — no coverage at all, in any state.** In TX and NY a
  single authority licenses MDs and DOs, so the MD rows are *likely* to hold;
  "likely" is not verified. In **CA and FL the osteopathic boards are separate
  bodies with their own rules and fee schedules**, and applying the MD rows to a
  DO there would be wrong. A consumer that resolves a DO to the MD rows is
  manufacturing an unverified obligation.
- **Only CA, FL, TX, NY.** The other 46 states and DC are absent.
- **Only the licence itself.** DEA registration, CMS/Medicare enrolment,
  hospital privileges, malpractice and board certification are out of scope for
  this file.
- **No `csr_renewal_cycle_months` / `csr_fee_cents` anywhere** — the two states
  where `csr_required` is verified (TX, NY) both verified **false**, and the two
  where it is unknown (CA, FL) have no verified registration to hang a cycle or
  fee on.
- **No `ce_hours_total` for New York, either profession.** NYSED publishes no
  general CE hour requirement for physicians or nurses, only mandated topic
  training. Widely-known ≠ verified; `0` is not seeded because no source asserts
  it.
- **No `renewal_window_days` for NY (either profession), FL/APRN, or TX/MD.**
  NY states the window in months and gives two different figures; TX/MD
  publishes a 60–90 day *range*. A range is not a value.
- **No `fingerprint_required` for NY (either profession) or TX/APRN.**
- **No TX/APRN fees.** `bon.texas.gov`'s fee schedule, licensure-eligibility page
  and the full text of 22 TAC 216.3 were all unreachable on 2026-09-18 (robots
  disallow on `/rr_current/`, repeated robots.txt fetch failures and an
  incomplete TLS chain on the fee pages, and the Texas SoS TAC viewer has moved
  to a JS portal that serves no static text). Retrieve these by hand.
- **No `csr_required` for CA or FL.** Neither state's boards publish an
  affirmative statement either way, and a negative cannot be asserted from
  silence.

---

## Two conventions a consumer must honour

### 1. `value_json` carries the requirements that are not simply per-cycle

The `requirements` CHECK permits exactly one populated value column. This seed
uses:

- `value_num` — a plain per-cycle quantity (months, days, hours, cents).
- `value_bool` — a plain yes/no.
- **`value_json`** — a quantity that is **not** "this much, every cycle":
  one-time requirements, requirements on a clock other than the renewal cycle,
  and requirements that apply only to a subset of licensees. Shape is
  `{"hours": n, "periodicity": "...", ...}`.

> **Any consumer that reads `value_num` and ignores `value_json` will silently
> drop these rows.**

It matters. California's 12-hour pain management CME is **one-time**; recorded
as a per-cycle `12` it would bill every California physician a fabricated
12-hour duty every two years. Texas's opioid CME is **every 8 years**, human
trafficking **every 6**, ethics **every third cycle**; Florida's domestic
violence is **every third biennium** and is **in addition to** the CE total.
15 of the 71 rows are `value_json` for exactly this reason.

The underlying problem is a schema gap — the `field_key` set has no slot for
topic periodicity — and it is logged as an open conflict. Fixing it is a schema
change, not a data change.

### 2. Conditional authority is flagged, not flattened

Three of the four states have a tiered or conditional NP practice regime that a
single boolean misrepresents:

- **CA** — traditional NPs practise under standardized procedures, but 103 NP
  (B&P 2837.103) and 104 NP (B&P 2837.104) certificate holders do not.
- **FL** — an established protocol is required by s. 464.012, unless the APRN
  holds autonomous practice registration under s. 464.0123.
- **NY** — a written practice agreement is required only until 3,600 hours of
  experience; `collaborative_agreement_required` is therefore `value_json`
  carrying the threshold, not a bare boolean.

Where a boolean is seeded it is the **conservative default** (the answer that
applies to the untiered majority and that fails safe), and it is paired with an
open conflict naming the exception. Resolving these needs a per-clinician
attribute the platform does not yet hold.

---

## Where two official sources disagreed

Both cases are Florida, both are recorded as open conflicts, and in both the
seeded value is the board's published figure because that is what the licensee
actually pays:

| Field | Board publishes | Statute says |
|---|---|---|
| `FL/APRN/renewal_fee_cents` | $60.00 active-to-active | s. 464.012, F.S.: "a biennial renewal fee not to exceed $50" |
| `FL/APRN/initial_license_fee_cents` | $110.00 | s. 464.012, F.S.: "an application fee not to exceed $100" |

The likely reconciliation is statutory add-ons bundled outside the board fee cap
(e.g. the s. 456.065(3) unlicensed activity fee), but neither source publishes
the breakdown, so neither figure is treated as settled.

A third, milder disagreement is a citation discrepancy rather than a value one:
the Texas Board of Nursing attributes the 20-contact-hour CNE requirement to
Rule **216.3(a)** on its continuing education page and to Rule **216.5** in its
own FAQ. The value agrees; only the rule number differs. Also logged.

---

## Adding a row

1. Fetch and read a board page, statute or board rule. Not a summary site.
2. Quote the source's own words in `citation`. Put the URL you actually fetched
   in `citation_url`.
3. If it is not simply "this much, every cycle", use `value_json` with an
   explicit `periodicity`.
4. Set `verified_at` to the date you read the source and `verified_by` to who
   you are. Do not inherit someone else's `verified_at`.
5. If you could not verify it, **do not write the row** — write a
   `requirement_conflicts` row saying what you looked at and what is still open.
6. Superseding a rule means inserting `version + 1` and clearing `is_current` on
   the prior row (see `0004_rules.sql`); `ux_requirements_current` enforces one
   current row per `(state, license_type, field_key)`.
