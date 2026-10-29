# Clinician Standing — ingest layer

This repository holds the Python that keeps the Clinician Standing database
true. It downloads the federal bulk files that describe who may practice and
bill — the CMS Doctors and Clinicians file, the OIG exclusion list, the CMS
revalidation file — diffs each one against the previous run, and writes the
changes into a Supabase Postgres database as timestamped, cited evidence. Every
human-facing screen is built separately in Lovable and reads that same database.

---

## Architecture: two codebases, one contract

```
  ┌────────────────────────────┐        ┌────────────────────────────┐
  │  THIS REPO (Python)        │        │  LOVABLE (TypeScript/React)│
  │                            │        │                            │
  │  bulk file downloads       │        │  exception queue           │
  │  diffing and checksums     │        │  action queue              │
  │  parsers and scrapers      │        │  roster, clinician detail  │
  │  evidence writes           │        │  obligation calendar       │
  │  scheduled jobs            │        │  client portal             │
  └─────────────┬──────────────┘        └─────────────┬──────────────┘
                │                                     │
                │  writes                             │  reads
                ▼                                     ▼
        ┌───────────────────────────────────────────────────┐
        │        SUPABASE POSTGRES — the shared contract     │
        │        schema owned by db/migrations/ only         │
        └───────────────────────────────────────────────────┘
```

**Python owns bulk ingest and scrapers.** Anything that downloads a file,
parses hundreds of megabytes, talks to a source API, or computes a diff lives
here. It writes `evidence` rows and the credential rows the reconciler derives
from them.

**Lovable owns every human-facing screen.** Queues, rosters, detail views, the
rules admin, the client portal. It reads the database, and it writes only user
actions — resolving an exception, completing an obligation, uploading a
document.

**Supabase Postgres is the contract between them.** Tables, columns, types,
constraints and row-level security policies are defined in `db/migrations/` in
this repository. That directory is the only definition of the schema that
exists.

### ⚠️ Lovable must never create or alter a table

Lovable's SQL editor and its "let me add a column for that" behavior are the
single largest source of drift risk in this system, because a column added
there exists in the running database and in no file anywhere.

- Every schema change is a numbered migration in `db/migrations/`, reviewed and
  applied with `make migrate`.
- If a screen needs a field that does not exist, the migration lands **first**,
  and Lovable is pointed at the new column afterwards.
- A table created from the Lovable or Supabase UI has no migration, will not
  exist in a fresh environment, and will be silently dropped the next time the
  schema is rebuilt. Assume it will happen.
- Ingest writes and UI writes must never both own the same column. Ingest owns
  everything derived from a source; the UI owns workflow state.

---

## Quickstart

```bash
git clone <repo-url> clinician-standing
cd clinician-standing

make install                 # creates .venv and installs the package with dev tools
cp .env.example .env         # then fill in the two database URLs and STORAGE_PATH
make migrate                 # applies db/migrations via the supabase CLI
make ingest                  # downloads, diffs and loads every enabled connector
make status                  # last run, rows changed and freshness per source
```

Requires Python 3.11 and, for `make migrate`, the
[Supabase CLI](https://supabase.com/docs/guides/cli) linked to the project.

The first `make ingest` downloads roughly 1.4 GB and takes 10 to 25 minutes
depending on how CMS is feeling. Budget about 5 GB of free disk in
`STORAGE_PATH`: each file is kept alongside the previous run so the next run
can diff rather than reload.

Other targets: `make test`, `make lint`, `make typecheck`, `make clean`.

### Sample run without downloading anything

`tests/fixtures/sample/` holds two months of small synthetic CMS DAC, CMS
revalidation and OIG LEIE files for an invented five-clinician roster
(`roster.csv`). Names are placeholders and the NPIs are generated with valid
check digits. `make sample` creates a scratch database on `TEST_DATABASE_URL`,
applies every migration and seed, runs all three connectors as `app_ingest`
for month 1, month 1 again (expects zero changes) and month 2, checks the
affiliations, enrollments and sanctions it wrote, then drops the database.

To drive the CLI by hand against the same files, point each connector at a
local file:

```bash
F=tests/fixtures/sample/v1
LOCAL_SOURCE_CMS_DAC=$F/cms_dac.csv \
LOCAL_SOURCE_CMS_REVALIDATION=$F/cms_revalidation.csv \
LOCAL_SOURCE_OIG_LEIE=$F/oig_leie.csv \
  clinician-standing ingest --sources cms_dac,cms_revalidation,oig_leie
clinician-standing audit 9900000001
```
Run `make` with no argument for the full list.

---

## Data sources

### Tier 1 — free federal bulk (working today)

| Source | Key | Size | Rows | Cadence | Encoding |
|---|---|---|---|---|---|
| CMS Doctors and Clinicians National Downloadable File | `cms_dac` | 839 MB | 3.39 M | Monthly | UTF-8 |
| CMS Revalidation Clinic Group Practice Reassignment | `cms_revalidation` | 540 MB | 3.39 M | Monthly | **latin-1** |
| OIG LEIE (full file + monthly supplement) | `oig_leie` | 15.6 MB | 84,001 | Monthly | **latin-1** |
| NPPES full replicate (V.2) | `nppes` | 1.2 GB zip / 11.7 GB | ~9 M | Monthly | UTF-8, per-line latin-1 fallback |
| NPPES weekly incremental (V.2) | `nppes_weekly` | small | the week's changes | Weekly | same as `nppes` |
| CMS Hospital General Information | `cms_hospitals` | ~2 MB | ~5,400 | Monthly | UTF-8 |
| CMS Facility Affiliation Data | `cms_facility_affiliation` | ~60 MB | ~1.3 M | Monthly | UTF-8 |

`nppes_weekly` reads the newest weekly file off the same NPPES downloads page
and upserts every row into `nppes_providers`, skipping any row older than the
stored one and never marking NPIs absent (the monthly replicate owns that). Its
live download is untested: the CMS page was down for maintenance when it was
built, so the file-name pattern is verified against fixtures only.
`ingest-weekly.yml` runs it every Monday.

The NPPES rows and the last two are the **directory layer** (`0016_directory_reference.sql`).
They describe the whole national clinician population rather than client
rosters, land in reference tables keyed on NPI and CMS Certification Number
(`nppes_providers`, `facilities`, `clinician_facility_affiliations`), and never
write `affiliations` or generate obligations. `clinician_directory` joins them
to the roster at read time: NPPES status and self-reported license states,
medical school and graduation year from the DAC file, and every open facility
affiliation with the facility's name.

### Not yet built

| Source | Key | Size | Cadence | Notes |
|---|---|---|---|---|
| PECOS enrollment files | `pecos` | moderate | Monthly | — |
| SAM.gov exclusions | `sam` | small | Daily | Second exclusion source; disagreement with LEIE is an exception, not a merge |
| Nursys e-Notify | `nursys` | push | push + API | Free institution account; API password rotates every 90 days |
| FSMB Physician Data Center | `fsmb_pdc` | file + API | Monthly | Licensed, quote required |
| State bulk files (CA, TX, NC, VA) | `state_xx` | varies | Varies | Per-state field mapping |

Payer portals — PECOS web, Availity, CAQH — are never automated. They are
session-based with MFA and their terms prohibit it. Work there raises a
`PORTAL_REQUIRED` exception for a human.

---

## Standing API (v0.1)

A read-only HTTP API over the data this repo has already ingested. It makes no
outbound request and writes nothing. It reports what the ingested sources say
about a clinician and the date each source was fetched, and nothing beyond
that. The endpoint and field names follow the license-check-hub spec where the
concept is the same.

```bash
make install-api
export API_DATABASE_URL=postgresql://...   # read access is all it needs
export API_KEYS=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
make api                                   # uvicorn on 127.0.0.1:8000, docs at /docs
```

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/v1/health` | none | Liveness. No database call. |
| GET | `/v1/sources` | key | Sources the API reads, whether each is ingested, and its as-of date |
| GET | `/v1/clinicians/{npi}` | key | Standing by NPI |
| GET | `/v1/clinicians?last_name=&state=&first_name=` | key | Standing by exact name plus state, up to 25 candidates |
| POST | `/v1/standing/check` | key | Either lookup as JSON: `{"npi"}` or `{"last_name", "state", "first_name"?}` |

```bash
curl -s localhost:8000/v1/clinicians/1990001012 -H "Authorization: Bearer $API_KEYS"
```

**What a lookup returns.** For each matched clinician: identity from the CMS
DAC file (name, credential, specialty, practice states), an exclusion screen
(matches from the `sanctions` table with source, action date, reinstatement
date and match basis), and license records from the `licenses` table with the
source that asserted each one. Each screen carries a status that separates
"looked and found nothing" from "could not look" (`no_npi_match` vs
`not_screened`, `no_records_found` vs `no_license_source_ingested`), plus a
`note` stating what was not covered.

**The `sources` block.** Every lookup response has `sources.checked` (each
source read, with `as_of`, `freshness_expires_at` and `stale`) and
`sources.not_checked` (sources the API knows about but did not read, with the
reason). Read the answer as covering the checked sources only.

**Limits a caller should know.**

- Exclusion matching is by NPI only. About 90% of LEIE rows carry no NPI, and
  name plus date-of-birth matching is not enabled, so `no_npi_match` does not
  mean the clinician is not excluded. The note on every clean result says this
  with the counts from the last ingest.
- LEIE rows without an NPI are linked to NPPES NPIs by name and state
  (`leie_match.py`, table `leie_npi_candidates`). These come back under
  `exclusions.possible_matches` with `match_basis: name_state`, a confidence
  below 1.0 and `status: possible_match_needs_review`. They never appear under
  `exclusions.matches`, never set `open_exclusion_found`, and never write
  `sanctions`. The confidence orders candidates for review; nobody has measured
  it against a labeled sample yet.
- Only clinicians present in the CMS DAC file can be found. An NPI outside it
  returns `result: not_found` and no screen is run.
- Name lookup is exact on the upper-cased name. A clinician is tied to a state
  by an active affiliation with a practice there or by a license issued there.
- License records come only from sources that have been ingested. Today that
  can only be Nursys, which covers nurses enrolled through a client account. No
  state board source is ingested.

**Auth and limits.** `API_KEYS` is a comma-separated list; keys shorter than 24
characters are ignored. Send `Authorization: Bearer <key>`. With no usable key
the API answers 503 `auth_not_configured`. `API_RATE_LIMIT_PER_MINUTE` (default
60, 0 disables) is a per-key fixed window held in process memory, so each
worker counts separately.

**Errors** use `{"error": {"code", "message"}}`: `invalid_request` (400, which
includes an NPI with a bad check digit), `unauthorized` (401), `rate_limited`
(429 with `Retry-After`), `auth_not_configured` and `store_unavailable` (503).

**OpenAPI.** `docs/openapi.json` is generated from the code by `make openapi`,
and `tests/test_api.py` fails when the two disagree. A running server also
serves it at `/openapi.json` with an interactive view at `/docs`.

**Not built yet from the license-check-hub spec:** state board license
sources (no `state_*` connector ships), license number and profession inputs,
`GET /v1/lookups/{id}` and any lookup log, batch endpoints, caching with
`?fresh=true`, per-org keys stored hashed in the database with a dashboard,
monthly quotas, metering and billing, sandbox keys, webhook re-verification,
and board health checks. SAM.gov and NPDB are registered sources with no data
ingested, so they always appear under `not_checked`. NPPES appears under
`checked`, with its `as_of`, once the `nppes` or `nppes_weekly` connector has
run.

---

## Repository layout

```
.
├── db/
│   └── migrations/          # numbered SQL migrations — the ONLY schema definition
├── src/
│   └── clinician_standing/
│       ├── cli.py           # `clinician-standing` entry point: ingest, status
│       ├── config.py        # environment loading and validation
│       ├── db.py            # psycopg connection and COPY helpers
│       ├── api/             # read-only standing API (FastAPI): app, auth, store, service
│       └── connectors/      # one module per source: fetch, checksum, diff, load
├── tests/
│   ├── conftest.py          # fixtures; no network, no database
│   └── fixtures/            # small committed samples, including the latin-1 CSV
├── docs/
│   └── openapi.json         # generated by `make openapi`; a test checks it matches the code
├── .github/workflows/
│   ├── ci.yml               # ruff, mypy, pytest on every push and PR
│   └── ingest-monthly.yml   # scheduled ingest — see the cron caveat below
├── .env.example             # every variable the project reads
├── Makefile                 # install, test, lint, typecheck, migrate, ingest, status, clean
└── pyproject.toml           # dependencies, ruff and mypy configuration
```

`storage/` and `data/` are created at runtime and are gitignored. Nothing
downloaded ever belongs in a commit — the DAC file alone is 839 MB and GitHub
rejects blobs over 100 MB *after* they are already in local history.

---

## Known gotchas

These each cost real debugging time. They are listed so they cost it once.

### 1. LEIE and the revalidation file are latin-1, not UTF-8

Both files contain bytes — `0xa0` (non-breaking space) most commonly, plus
accented characters in names — that are not valid UTF-8. Reading either with
Python's default encoding raises `UnicodeDecodeError` partway through a
multi-hundred-megabyte parse, which is slow to reproduce and easy to
misdiagnose as a truncated download.

```python
# wrong — fails after several minutes, deep inside the file
open(path, encoding="utf-8")

# right
open(path, encoding="latin-1", newline="")
```

Do **not** "fix" it with `errors="ignore"`. That turns `PEÑA` into `PEA`
silently, and a mangled surname in an exclusion screen is a false negative on a
named clinician. latin-1 maps all 256 byte values, so it can never raise and
never drops a character. `tests/test_encoding.py` guards this.

### 2. Dedupe the CMS DAC file on `(NPI, org_pac_id)`

The Doctors and Clinicians file carries **one row per clinician per practice
location**. A clinician practicing at three sites of the same group appears
three times. Counting the file raw overstates the roster and double-loads
affiliations.

- The identity of a row is the pair `(NPI, org_pac_id)`.
- Address, city, ZIP, phone and the telehealth flag vary *within* a pair and
  must not be part of the key.
- Deduping on NPI alone is also wrong: it collapses a clinician's two different
  groups into one and loses a real affiliation.

`tests/test_dedupe.py` guards this.

### 3. Scheduled GitHub Actions do not run on a private repo on the free tier

`on: schedule` is **silently ignored** on private repositories owned by a free
personal GitHub account. No run, no error, no notification — the workflow
simply never fires. Two fixes:

1. GitHub Pro on the owning account ($4/month), or
2. make the repository public.

`workflow_dispatch` — the "Run workflow" button and `gh workflow run` — works on
the free tier regardless, private repos included. Until one of the two fixes is
in place, treat `ingest-monthly.yml` as manual-only and keep a calendar reminder
on the first of the month.

Related, and it bites on paid plans too: GitHub disables scheduled workflows in
any repository with 60 days of no commit activity, and emails the owner. A repo
that only runs ingest will hit this. Re-enable it from the Actions tab.

### 4. LEIE NPI coverage is about 10%

Only 8,701 of 84,001 exclusion rows carry an NPI. Matching on NPI alone finds
almost nothing, so name plus date-of-birth matching is mandatory — and a false
positive there is a serious accusation about a named clinician. Exclusion
matches below full confidence are written with a `match_confidence` under 1.0
and routed to the exception queue, never auto-cleared.
Name plus state candidates against NPPES (`0018`, `leie_match.py`) cover part
of the gap for human review only; they are never written as sanctions.

### 5. Use the direct Postgres connection for bulk loads

Supabase's transaction-mode pooler (port 6543) does not support the
session-level features that `COPY` and migrations need. Use the direct
connection (port 5432) for `make migrate` and for bulk loads; the pooler is fine
for short status queries.

### 6. The ingest does not connect as the superuser

`DATABASE_URL` names **`app_ingest`**, a login role created by
`db/migrations/0011_ingest_role.sql` whose entire reach is membership in
`app_internal`. It owns nothing, has no DDL rights and — the part that matters —
has no `BYPASSRLS`, so the row-level security in `0008_rls.sql` actually applies
to it. `0011` also sets `FORCE ROW LEVEL SECURITY` on all 16 tables, because
plain `ENABLE` exempts the table owner.

Before this split, `DATABASE_URL` was Supabase's `postgres` role: the owner of
every table, with `BYPASSRLS`. The careful three-role model applied to nobody,
and the one secret held by an unattended monthly job could read, rewrite or drop
the entire database. The superuser URI is now `MIGRATION_DATABASE_URL`, used by
a person running migrations and by nothing else.

A superuser and any role with `BYPASSRLS` still bypass RLS — that is how
Postgres works. Keeping that credential out of the ingest's environment is the
control, not the policies.

---

## Compliance boundaries

- **No PHI, ever.** Provider and practice data only. This is enforced by schema
  review, not by policy. A migration that introduces a patient-identifying
  column does not get merged.
- **Secrets never live in the repo or in a Lovable project file.** `.env` is
  gitignored; CI reads GitHub Actions repository secrets.
- **Site terms are a hard gate.** Any scrape adapter carries a
  `termsReviewedAt`, fails closed when that review is over 180 days old, honors
  `robots.txt`, identifies itself honestly, holds to one request per second, and
  raises an exception on a CAPTCHA rather than solving it.

---

## GitHub repository secrets

Configured under **Settings → Secrets and variables → Actions**:

| Secret | Required by | Notes |
|---|---|---|
| `DATABASE_URL` | `ingest-monthly.yml` | The **`app_ingest`** role's URI — not the superuser's. Direct connection (port 5432) so `COPY` works. Rotate with `alter role app_ingest password '<new>'`; it does not touch the superuser password. |

**`MIGRATION_DATABASE_URL` is deliberately not a repository secret.** It is the
superuser credential; no workflow needs it, and adding it would hand a scheduled
unattended job the ability to drop the schema. Migrations are applied by a person
with the Supabase CLI or `psql`. See `db/README.md`.

`ci.yml` uses no secrets and reaches no network or database, by design.
Future connectors will add `NURSYS_API_KEY` and `FSMB_API_KEY`; both are
commented out in `.env.example` until the connector ships.

---

See [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.
