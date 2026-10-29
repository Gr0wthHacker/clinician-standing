# Changelog

## Unreleased

Integration of the first branch backlog onto `main` (BUILD_PLAN WP0.2), plus the
CI foundation that made it verifiable (WP0.1) and a bug that surfaced with it.

### Infrastructure
- **WP0.1 — Postgres in CI.** A `database` CI job stands up `postgres:15`, applies
  every migration and seed, and runs the `database`-marked tests on each PR.
  `db/ci/bootstrap.sql` recreates the Supabase roles; `db/ci/check_migrations.py`
  lints migration names and forbids editing an applied migration.
- Hashed lockfiles (`requirements.txt`, `requirements-dev.txt`) via `make lock`;
  CI installs `--require-hashes`.

### Features
- **LEIE name + state candidates** (T836, `0017_leie_npi_candidates.sql`,
  `leie_match.py`). LEIE rows with no NPI are matched against NPPES individuals
  on surname key, first name (exact, 3+ letter prefix, or initial), middle
  initial when both sides have one, and practice or self-reported license state.
  Confidence is below 1.0 by CHECK and split across same-name candidates; rows
  with more than 10 candidates are counted as too ambiguous. Candidates are
  review-only: never `sanctions`, surfaced by the API under
  `exclusions.possible_matches` as `possible_match_needs_review`. A review
  decision survives reruns; candidates the latest LEIE run did not produce are
  superseded, not deleted. `nppes` now runs before `oig_leie`.
- The API `sources` block reports NPPES (`nppes`, `nppes_weekly`) as checked
  with `as_of` once ingested, and reads a source's file-level evidence row when
  per-match evidence shares its timestamp.
- **Standing API v0.1** (`src/clinician_standing/api`): read-only FastAPI app:
  lookup by NPI or exact name plus state, exclusion screen and license records
  from ingested data, a `sources` block with as-of dates on every lookup,
  env-driven API keys and a per-key rate limit. OpenAPI in `docs/openapi.json`.
  Optional extra `.[api]`.
- **Directory layer** (`0016_directory_reference.sql`). Three new connectors
  for the public data commercial provider directories are built on, landing in
  reference tables that never drive obligations:
  - `nppes` -- the NPPES full replicate (V.2), discovered from the NPPES
    downloads page and read straight out of the zip. Taxonomy slots with
    self-reported license numbers and states, practice address, authorized
    official, deactivation status. Deactivation stubs keep the stored name and
    taxonomy. EIN and parent-organization TIN are not loaded.
  - `nppes_weekly` -- the NPPES weekly incremental, applied on top of the
    replicate. Every row in the file is upserted unless the stored row is newer;
    nothing is marked absent. Scheduled by `ingest-weekly.yml`. Live download
    untested (CMS page was in maintenance); fixtures follow the CMS layout.
  - `cms_hospitals` -- Hospital General Information, naming CCNs.
  - `cms_facility_affiliation` -- CMS Facility Affiliation Data: clinician to
    hospital, nursing home, home health, hospice, IRF, LTCH and dialysis
    facility, with DAC-style open/close semantics.
  - `clinician_directory` view joins all of it to the roster.
- **DAC enrichment** -- `cms_dac` now keeps `Med_sch`, `Grd_yr` and
  `sec_spec_all` as `clinicians.medical_school`, `graduation_year` and
  `secondary_specialties`. Optional columns: CMS dropping one costs that column,
  not the run. The content hash now includes them, so **the first DAC run after
  this ships reports every row as changed** and reloads once; that is expected.
- `parse.decode_lines` (UTF-8 with per-line latin-1 fallback) and
  `Connector.fetch_text` (allowlisted fetch of an HTML index page).
- **Nursys e-Notify connector** — consumption-only (no PII), `SecretStore`,
  90-day password rotation, `nursys rotate`, migration `0013_nursys.sql`.
- **Clock anchors** — `renewal_anchor` / `csr_anchor` / `ce_anchor` in the rules
  plane, fixing split-clock states (CT/DE/RI); inert until rows are authored.
- **Classifier** (PRD 8) — routes pending obligations to auto-cleared / action
  queue / exception with the eight reason codes, and reports the auto-clear rate.
  `classify run`.
- **Stale-source refresh** — `refresh` re-ingests sources past their freshness
  SLA (SOURCE_STALE automatic re-fetch).

### Fixes
- **DAC first load** -- the affiliation insert was quadratic on an empty
  `affiliations` table (nested-loop anti join scanning the heap it was writing).
  The first load of the September 2026 file stalled past ten minutes on that
  statement; with the anti join split into its own temp table the whole DAC
  load takes about six minutes.
- **DAC discovery** — handle the CMS metastore's flat distribution shape; the
  monthly DAC ingest would otherwise fail at discovery on the live API.
- **Audit fetch dates** — render evidence fetch dates in UTC (were local tz, off
  by a day on compliance documents).
- **Engine** — close obligations the roster no longer implies (pending/queued
  only; audit-preserving soft delete).
- **Security** — revoke Supabase `anon`/`authenticated` from app data
  (`0014`); salt the date-of-birth hash (`DOB_HASH_SALT`); harden
  `insert_credential` with `psycopg.sql` composition; scope the monthly ingest
  workflow to federal sources and redact artifacts.

Verified against Postgres 16: 14 migrations apply, seeds load (requirements 664,
conflicts 301, jurisdictions 51), full suite 193 passed.
