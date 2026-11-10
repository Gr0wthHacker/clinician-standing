# Running the database on Neon

The schema in `db/` is plain Postgres. The Python ingest, the engine and the API only need libpq URIs, so they run on Neon unchanged. What changes is how migrations are applied (`scripts/migrate_psql.sh` instead of the Supabase CLI) and which connection strings go where.

## Plan and size

The full CMS Doctors and Clinicians file is 3.39M rows and loads every clinician and practice in it, so the loaded database will outgrow Neon Free's per-project storage. Use Neon Launch: usage based with no monthly minimum, billed per GB-month of storage and per compute hour. The monthly ingest is a short burst of compute, and the database scales to zero between runs.

## 1. Create the project

Create a Neon project on Postgres 17, region `aws-us-east-1`. The dashboard gives the owner role (`neondb_owner`) and two hosts: the direct one and the `-pooler` one. Use the direct host everywhere here: the ingest stages files with `COPY` into temporary tables, which needs a session connection. Every URI needs `?sslmode=require`.

Check that the owner can bypass row level security, since `0011` forces RLS on every table and later migrations and the seeds insert rows:

```bash
psql "$MIGRATION_DATABASE_URL" -tAc "select rolbypassrls from pg_roles where rolname = current_user"
```

It should print `t`. `scripts/migrate_psql.sh` runs the same check and stops before applying anything if it prints `f`.

## 2. Apply the schema

```bash
export MIGRATION_DATABASE_URL='postgresql://neondb_owner:...@ep-xxx.us-east-1.aws.neon.tech/neondb?sslmode=require'
make migrate-psql          # migrations and seeds
```

It records each file in `supabase_migrations.schema_migrations`, the same table `supabase db push` uses, so reruns skip what has been applied. `0011` must run once per Neon branch: it creates `app_ingest`, and re-asserting that role's attributes later needs a superuser, which Neon does not provide.

Then give `app_ingest` its password, out of band as before:

```bash
psql "$MIGRATION_DATABASE_URL" -c "alter role app_ingest password '<generated>'"
```

## 3. Point the jobs at it

| Where | Variable | Value |
|---|---|---|
| GitHub Actions secret (`ingest-monthly.yml`) | `DATABASE_URL` | `postgresql://app_ingest:<password>@<direct host>/neondb?sslmode=require` |
| Local `.env` | `DATABASE_URL`, `MIGRATION_DATABASE_URL` | the same two URIs |
| API host | `API_DATABASE_URL`, `API_ROSTER_DATABASE_URL` | the read and roster roles on the same host |

`MIGRATION_DATABASE_URL` stays out of repository secrets, as it does on Supabase.

## 4. Data

Start empty and run the first ingest: it rebuilds practices, clinicians, affiliations, enrollments, sanctions and evidence from the federal files. Only rows entered by hand (rosters, quotes) need copying, table by table, with a pg_dump at least as new as the source server:

```bash
pg_dump "$SUPABASE_SUPERUSER_URI" --data-only --no-owner --no-privileges --table=public.<table> \
  | psql "$MIGRATION_DATABASE_URL" -v ON_ERROR_STOP=1
```

## The UI

Lovable's Supabase integration (Supabase Auth and its REST API) does not exist on Neon. The policies in `0008` read the practice scope from `request.jwt.claims`, which PostgREST sets, so Neon's Data API (PostgREST compatible, with JWT auth from any JWKS provider) is the matching path for the client portal. Wire that up when the UI is built.
