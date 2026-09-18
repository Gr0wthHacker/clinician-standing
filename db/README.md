# `db/` — the Postgres schema

The verification platform's database: Postgres 15 on Supabase, built from the
data model in **PRD section 5** (`08-PRD-verification-platform.md`).

---

## ⚠️ This schema is the shared contract. Read this before touching anything.

Three independent things read and write this database:

| Component | What it does |
|---|---|
| **Python ingest** (`sources/`, scheduled jobs) | Writes `evidence`, `source_runs`, and derived credential rows |
| **Obligations engine** (nightly) | Reads `requirements` + roster, writes `obligations` and `exceptions` |
| **Lovable UI** | Renders the queues, the roster, the client portal |

They only interoperate because the table and column names, types and constraints
are fixed here and nowhere else.

> ### Lovable must never create or alter tables.
>
> **Lovable reads and writes existing rows. That is all.**
>
> Lovable's Supabase integration will happily offer to "add a column", "create a
> table for this feature", or "fix" a type. Refuse every time. A schema change
> made from inside the UI builder is invisible to this directory, silently
> breaks the ingest scripts and the nightly engine, and cannot be reviewed,
> reverted or replayed into another environment.
>
> **Every schema change is a new numbered migration in `db/migrations/`,
> committed to this repo, reviewed, and applied with the Supabase CLI.**
> There is no second path. If Lovable needs a column, write the migration here
> first, apply it, then point Lovable at the column that now exists.
>
> The same rule applies to RLS policies, roles and grants. `0008_rls.sql` is the
> whole access-control story; a policy added elsewhere is a security hole nobody
> can find later.

A second, related rule, from PRD section 2: **no PHI, ever.** Provider data is
not patient data. If a proposed column could hold anything about a patient, the
answer is no — "enforced by schema review, not by policy alone" (PRD 12). Note
`clinicians.dob_hash`: a sha256 digest for LEIE name+DOB matching, never a date
of birth, and constrained to 64 hex characters so a raw date cannot be stored.

---

## Migrations

Applied strictly in filename order. Each one is re-runnable (`IF NOT EXISTS`,
guarded `DO` blocks, `DROP POLICY IF EXISTS` before `CREATE POLICY`), and none
references an object a later file creates.

| File | Contents | PRD |
|---|---|---|
| `0001_extensions.sql` | `pgcrypto`, `pg_trgm`, the `app` helper schema, and the conventions header | — |
| `0002_core.sql` | `practices`, `clinicians`, `affiliations`, **`evidence`** | 5.1, 5.4 |
| `0003_credentials.sql` | `licenses`, `registrations`, `enrollments`, `privileges`, `ce_records`, `sanctions` | 5.2 |
| `0004_rules.sql` | `requirements`, `requirement_conflicts` | 5.3 |
| `0005_obligations.sql` | `obligations`, `exceptions` | 5.4 |
| `0006_sources.sql` | `sources`, `source_runs`, and the `evidence.source_key` FK | 5.5 |
| `0007_indexes.sql` | Performance indexes, each commented with the query it serves | 7, 8, 10, 11 |
| `0008_rls.sql` | Roles, grants, RLS policies | 12 |
| `0009_seed_sources.sql` | Source registry seed | 6 |

`evidence` is defined in `0002` rather than `0005` because the credential tables
in `0003` carry a `NOT NULL` foreign key to it, and migrations may not reference
forward. The table itself is exactly as PRD 5.4 specifies.

### Enum-like columns

Allowed-value sets (`status`, `severity`, `clinician_type`, `obligation_type`,
`reason_code`, `sources.kind`, `sources.cadence`, …) are **`text` columns with
named `CHECK` constraints**, not Postgres `ENUM` types. Used consistently
everywhere; the reasoning is in the header of `0001_extensions.sql`. Every
constraint is named `<table>_<column>_chk`, so widening a value set is:

```sql
alter table obligations drop constraint obligations_status_chk;
alter table obligations add  constraint obligations_status_chk
  check (status in (...new list...));
```

which runs, and rolls back, inside a transaction.

---

## Applying the migrations

### Prerequisites

```bash
# macOS
brew install supabase/tap/supabase
# or: npm i -g supabase
supabase --version        # 1.150+ recommended
```

The Supabase CLI looks for migrations in `supabase/migrations/`. Keep the single
copy here and point the CLI at it with a symlink (do this once, per clone):

```bash
mkdir -p supabase
ln -s ../db/migrations supabase/migrations
```

The CLI parses the leading digits of a filename as the version, so `0001…`
through `0009…` sort and apply in the right order.

### Local development

```bash
supabase start                 # local Postgres + Studio in Docker
supabase db reset              # drop, recreate, replay every migration in order
```

`supabase db reset` is the fastest way to confirm a migration applies from
scratch. Run it before every push.

### A hosted project

```bash
supabase login
supabase link --project-ref <your-project-ref>

supabase db push --dry-run     # ALWAYS look at this first
supabase db push
```

`db push` applies only migrations not yet recorded in
`supabase_migrations.schema_migrations`, so it is safe to re-run.

### Without the CLI

Every file is plain SQL and can be applied with `psql` in order:

```bash
export DATABASE_URL='postgresql://postgres:<pw>@db.<ref>.supabase.co:5432/postgres'
for f in db/migrations/0*.sql; do
  echo "== $f"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f" || exit 1
done
```

Use this for a one-off environment or for CI. The CLI remains the path of record
because it tracks which migrations have run.

### Adding a migration

1. New file, next number, descriptive name: `0010_add_<thing>.sql`.
2. Never edit an applied migration. Changing one that has already run on any
   environment guarantees drift.
3. Make it re-runnable and forward-reference-free, like the others.
4. `supabase db reset` locally, then `supabase db push --dry-run`, then push.

---

## Roles and access control (`0008_rls.sql`)

RLS is enabled on all 16 tables. Access is gated twice: **`GRANT`s decide which
tables a role may touch at all; policies decide which rows within them.** A role
with no grant on a table gets `permission denied`, not an empty result — the
failure is loud, which is the point.

| Role | Reach |
|---|---|
| `app_internal` | Everything. QA specialist, team lead, account lead, ingest jobs. |
| `app_delivery` | **Action queue only.** `obligations` with status `queued`/`in_progress`, plus the roster and credential rows for clinicians who have queued work. Column-level `UPDATE (status, completed_at)` — nothing else. **No grant at all** on `evidence`, `sanctions`, `requirements`, `requirement_conflicts`, `exceptions`, `sources`, `source_runs`. |
| `app_client_portal` | **Read-only, own practice only.** Scoped by JWT claim. No `evidence`, no `sanctions`, no rules, no exceptions. |

`app_delivery` implements PRD 12 directly: *"Offshore associates access the
action queue only, never the evidence store or the rules admin."*

Supabase's `service_role` has `BYPASSRLS` and is unaffected by any of this. Use
it only from trusted server-side jobs. **Never ship it to a browser.**

### JWT claims the policies read

PostgREST switches to the role in the JWT `role` claim; practice scope comes
from the claim set:

```json
{
  "role": "app_client_portal",
  "practice_id": "…uuid…"
}
```

`practice_ids` (an array of uuid) is accepted too, for a client administrator
over more than one practice. With neither claim present, every client-portal
policy returns zero rows — deny by default.

Mint these claims in your auth hook / custom access token hook. The helper
functions live in the `app` schema (`app.portal_practice_ids()`,
`app.is_internal()`, `app.is_delivery()`, `app.is_client_portal()`).

---

## The invariant this schema exists to enforce

> **PRD 14, Phase 1 acceptance: "a credential row cannot be inserted without a
> valid `evidence_id`."**

`licenses`, `registrations`, `enrollments` and `sanctions` have
`evidence_id uuid NOT NULL REFERENCES evidence`. No application code, no Lovable
form and no ingest script can get around it:

```sql
-- fails: null value in column "evidence_id" violates not-null constraint
insert into licenses (clinician_id, state, license_type, status, verified_at)
values (…);

-- fails: violates foreign key constraint "licenses_evidence_id_fkey"
insert into licenses (…, evidence_id, …) values (…, gen_random_uuid(), …);

-- fails: still referenced from table "licenses"
delete from evidence where id = '…';
```

Evidence is soft-deleted (`evidence.deleted_at`), never removed — raw payloads
are retained 7 years (PRD 12).

`privileges` and `ce_records` keep `evidence_id` **nullable**, exactly as PRD 5.2
declares them, because no connector in the PRD 6 registry publishes facility
privileging or per-clinician CE data. The reasoning and the resulting obligation
on the classifier are written out above those tables in `0003_credentials.sql`.
Short version: a row there with `evidence_id IS NULL` can never satisfy PRD 8.1
condition 1, so it must never auto-clear.

## The other flag that decides the business

`sources.is_primary_source` is the first gate on auto-clear (PRD 8.1), and the
auto-clear rate is *"the single metric that determines whether this business
works"* (PRD 1.1). Seed values and the reasoning behind each are in
`0009_seed_sources.sql`. Read the note there about `oig_leie` and `sam_gov`
before changing either.

## Verifying a deployment

```sql
-- 16 tables, all with RLS on
select count(*) filter (where rowsecurity) as rls_on, count(*) as tables
from pg_tables where schemaname = 'public';

-- the source registry
select key, kind, cadence, freshness_sla_days, is_primary_source, enabled
from sources order by is_primary_source desc, key;

-- evidence coverage must stay 100% (PRD 11)
select 'licenses' t, count(*) filter (where evidence_id is null) as missing from licenses
union all select 'registrations', count(*) filter (where evidence_id is null) from registrations
union all select 'enrollments',   count(*) filter (where evidence_id is null) from enrollments
union all select 'sanctions',     count(*) filter (where evidence_id is null) from sanctions;
```
