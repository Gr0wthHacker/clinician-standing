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
