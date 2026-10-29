# Clinician Standing Monitor (T619)

One-page spec. Status: draft for Jack. Builds on the Standing API v0.1 in `src/clinician_standing/api`.

## Problem and buyer

A practice that bills federal health care programs cannot be paid for items or services furnished by an excluded person (42 CFR 1001.1901), and it needs to know when a clinician's license lapses or picks up a board action. A check run at hiring goes stale the month after. The buyer is the practice administrator or credentialing lead at a group practice or facility who holds the roster and answers for it.

## What it does

The client keeps a roster of clinicians by NPI. Each time a source finishes an ingest run, the monitor re-reads standing for every NPI on every active roster, compares it to the last stored snapshot and writes an alert for each change.

| Change | Source today | Alert |
|---|---|---|
| New exclusion match, or a reinstatement | `oig_leie` (monthly) | Immediate email |
| License status change (active to expired, suspended, revoked, probation) or discipline reported | `nursys` (push, nurses enrolled through the client's account) | Immediate email |
| License `expires_on` inside a set window (default 60 days) | `licenses` table | Monthly digest |
| NPI no longer in the CMS Doctors and Clinicians file | `cms_dac` (monthly) | Monthly digest |
| Revalidation due date present or changed | `cms_revalidation` (monthly) | Monthly digest |
| A source the roster relies on is past its freshness SLA | `sources`, `source_runs` | Monthly digest |

"Continuous" means each source is checked at the cadence its publisher sets. Nothing is checked more often than it is published.

## Inputs and data sources

- Roster: NPI (required), name, state and credential, entered by the client in the Lovable screens. No date of birth and no other PII.
- Ingested now: CMS Doctors and Clinicians file, CMS Revalidation file, OIG LEIE, Nursys e-Notify.
- Registered with no data yet, to add in order: SAM.gov exclusions (`sam`, free API key from SAM.gov), NPPES (`nppes`), then the state board bulk files the README lists (CA, TX, NC, VA).
- Never automated: PECOS web, Availity, CAQH. Work there stays a `PORTAL_REQUIRED` exception.

## Outputs and alerts

- `monitor_alerts` rows, each tied to the `evidence` row that caused it, with source and as-of date.
- Immediate email for exclusion and adverse license changes. Everything else goes in a monthly digest per roster.
- The digest repeats the API's `sources.checked` and `sources.not_checked` block, so a clean month states what was and was not looked at. It carries the same NPI-only matching note the API puts on every clean result.

## What exists to build on

- `api/service.py` and `api/store.py`: standing by NPI with exclusion screen, license records and the sources block. The monitor calls the same service, so a monitor result and an API lookup cannot disagree.
- Connectors with checksum diffing, `evidence` writes, `sanctions`, `licenses`, `exceptions` and the classifier's reason codes.
- `refresh.py` for stale sources, `audit.py` for the roster audit document layout, `ingest-monthly.yml` for the schedule.
- Two months of synthetic fixtures (`tests/fixtures/sample/v1`, `v2`) that already produce changes between runs.

## Build plan

| Step | Days |
|---|---|
| Migration 0016: `monitor_rosters`, `monitor_roster_members`, `monitor_snapshots`, `monitor_alerts`, RLS in the 0008/0014 pattern (UI writes roster membership, ingest role writes snapshots and alerts) | 1 |
| Snapshot and diff: standing per NPI from `api/service.py`, stored hash, alert per change, tests on the v1 to v2 fixtures | 2 |
| `clinician-standing monitor run` CLI, called at the end of the monthly ingest and after each Nursys run | 0.5 |
| Notifier behind an interface, vendor set by env var (none chosen yet) | 1 |
| Monthly digest (HTML and PDF), reusing the audit layout | 1.5 |
| Read endpoints: `GET /v1/rosters/{id}/alerts`, `GET /v1/rosters/{id}/standing` | 1.5 |
| Lovable screens: roster upload, alert queue, acknowledge | 2 |
| SAM.gov connector | 2 |

Core: about 9.5 days. With SAM.gov: about 11.5 days.

## Pricing

$15-25 per clinician per month (from the T619 brief). Stripe prices come later under T621 and are referenced by env var.

## Risks and open questions for Jack

1. Price floor. `pricing.py` and `quote_lines_pppm_floor_chk` hold every Clinician Standing PPPM line at $200 or more, and your pricing note says prices are not to be lowered from $200-400. A $15-25 monitor line must be a separate product with `is_pppm_floored = false`. Is it sold on its own, as an add-on, or as the entry point to the $200 tiers?
2. Exclusion matching is NPI only. The README notes most LEIE rows carry no NPI. Name plus date-of-birth matching needs DOB on the roster, which runs into your no-PII rule. Ship NPI-only with the coverage note, or collect a salted DOB hash?
3. License coverage is nurses enrolled through the client's own Nursys account. Physicians have no license source until a state board connector or FSMB (licensed, quote required) is added. Is the price the same for clinician types the monitor cannot cover yet?
4. Diff state. The monthly workflow keeps connector state in an Actions cache, which is evicted after 7 days without a hit. The monitor diffs against its own snapshot table to avoid that, but raw payload retention still needs the `s3://` storage fix.
5. This repo is public, and Group 1 is meant to stay blinded in public. This spec names the product and its price. Keep it here or move specs to a private repo?
6. Counsel: does selling ongoing exclusion screening for staffing decisions raise FCRA questions? This is the same question your Whitecoat notes raised for credentialing use.
7. Who receives alerts per roster, and is there a response-time promise? None is assumed here.
