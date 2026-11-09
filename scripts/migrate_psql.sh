#!/usr/bin/env bash
# Apply db/migrations (and optionally db/seeds) to any Postgres with psql: Neon, a local server, or Supabase without its CLI.
#
#   MIGRATION_DATABASE_URL=postgresql://neondb_owner:...@ep-xxx.us-east-1.aws.neon.tech/neondb?sslmode=require \
#     scripts/migrate_psql.sh [--seeds]
#
# Use the owner (DDL) credential, never DATABASE_URL (app_ingest), and Neon's direct host, not the -pooler one.
# Applied files are recorded in supabase_migrations.schema_migrations, the table `supabase db push` keeps, so the two
# paths agree on what has run. Each file runs in its own transaction. Seeds are idempotent and run every time.
set -euo pipefail

: "${MIGRATION_DATABASE_URL:?Set MIGRATION_DATABASE_URL to the owner connection string}"
seeds=0
[ "${1:-}" = "--seeds" ] && seeds=1
cd "$(dirname "$0")/.."

run() { psql "$MIGRATION_DATABASE_URL" -X -v ON_ERROR_STOP=1 -q "$@"; }

# 0011 forces row level security on every table, and later migrations and the seeds insert rows, so the migrating role must
# bypass RLS (Supabase's postgres role does). Stop before anything is applied if it cannot.
if [ "$(run -tAc "select rolsuper or rolbypassrls from pg_roles where rolname = current_user")" != "t" ]; then
  echo "The role in MIGRATION_DATABASE_URL cannot bypass row level security, so migration 0015 and the seeds would be"
  echo "refused. Use a role with BYPASSRLS (on Neon, the owner role created with the project). Nothing was applied."
  exit 1
fi

run -c "create schema if not exists supabase_migrations;
  create table if not exists supabase_migrations.schema_migrations (version text primary key, statements text[], name text)"

for f in db/migrations/[0-9]*.sql; do
  base="$(basename "$f" .sql)"
  version="${base%%_*}"
  name="${base#*_}"
  if [ "$(run -tAc "select 1 from supabase_migrations.schema_migrations where version = '$version'")" = "1" ]; then
    echo "  skip  $base"
    continue
  fi
  echo "  apply $base"
  run -1 -f "$f" -c "insert into supabase_migrations.schema_migrations (version, name) values ('$version', '$name')"
done

if [ "$seeds" = 1 ]; then
  for f in db/seeds/[0-9]*.sql; do
    echo "  seed  $(basename "$f")"
    run -f "$f"
  done
fi
echo "Done. Set app_ingest's password once, then use it in DATABASE_URL:"
echo "  psql \"\$MIGRATION_DATABASE_URL\" -c \"alter role app_ingest password '<generated>'\""
