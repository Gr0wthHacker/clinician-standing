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
cp .env.example .env         # then fill in DATABASE_URL and STORAGE_PATH
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
Run `make` with no argument for the full list.

---

## Data sources

### Tier 1 — free federal bulk (working today)

| Source | Key | Size | Rows | Cadence | Encoding |
|---|---|---|---|---|---|
| CMS Doctors and Clinicians National Downloadable File | `cms_dac` | 839 MB | 3.39 M | Monthly | UTF-8 |
| CMS Revalidation Clinic Group Practice Reassignment | `cms_revalidation` | 540 MB | 3.39 M | Monthly | **latin-1** |
| OIG LEIE (full file + monthly supplement) | `oig_leie` | 15.6 MB | 84,001 | Monthly | **latin-1** |

### Not yet built

| Source | Key | Size | Cadence | Notes |
|---|---|---|---|---|
| NPPES full replicate | `nppes` | ~9 GB | Monthly | Source of truth for taxonomy, practice address, authorized official |
| PECOS enrollment files | `pecos` | moderate | Monthly | — |
| SAM.gov exclusions | `sam` | small | Daily | Second exclusion source; disagreement with LEIE is an exception, not a merge |
| Nursys e-Notify | `nursys` | push | push + API | Free institution account; API password rotates every 90 days |
| FSMB Physician Data Center | `fsmb_pdc` | file + API | Monthly | Licensed, quote required |
| State bulk files (CA, TX, NC, VA) | `state_xx` | varies | Varies | Per-state field mapping |

Payer portals — PECOS web, Availity, CAQH — are never automated. They are
session-based with MFA and their terms prohibit it. Work there raises a
`PORTAL_REQUIRED` exception for a human.

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
│       └── connectors/      # one module per source: fetch, checksum, diff, load
├── tests/
│   ├── conftest.py          # fixtures; no network, no database
│   └── fixtures/            # small committed samples, including the latin-1 CSV
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

### 5. Use the direct Postgres connection for bulk loads

Supabase's transaction-mode pooler (port 6543) does not support the
session-level features that `COPY` and migrations need. Use the direct
connection (port 5432) for `make migrate` and for bulk loads; the pooler is fine
for short status queries.

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
| `DATABASE_URL` | `ingest-monthly.yml` | Supabase Postgres URI. Use the direct connection (port 5432) so `COPY` works. |

`ci.yml` uses no secrets and reaches no network or database, by design.
Future connectors will add `NURSYS_API_KEY` and `FSMB_API_KEY`; both are
commented out in `.env.example` until the connector ships.

---

See [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.
