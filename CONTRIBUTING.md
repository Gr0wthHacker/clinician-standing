# Contributing

## Branches

Branch off `main`. Name it `<type>/<short-description>`, lowercase, hyphenated:

```
feat/nursys-connector
fix/leie-latin1-decode
chore/bump-psycopg
docs/source-registry-notes
db/0007-privileges-table
```

Types: `feat`, `fix`, `chore`, `docs`, `test`, `db`.

## Commits

Imperative mood, lowercase, no trailing period. Say what the commit does, not
what you did.

```
add nursys e-notify connector
fix latin-1 decode in the leie parser
dedupe dac rows on npi and org_pac_id
```

Not `Added...`, not `Fixes bug.`, not `WIP`. Keep a commit to one change;
a body paragraph is welcome when the reason is not obvious from the diff.

## Schema changes go through `db/migrations/`

This is the rule that matters most.

- Every table, column, type, constraint, index and RLS policy is defined by a
  numbered SQL migration in `db/migrations/`. That directory is the only
  definition of the schema that exists.
- Never create or alter a table from Lovable, from the Supabase dashboard SQL
  editor, or from a psql session against production. A change made that way
  exists in the running database and in no file, will not appear in a fresh
  environment, and will be lost the next time the schema is rebuilt.
- Migrations are forward-only and append-only. Do not edit a migration that has
  been applied anywhere; add the next number.
- If a Lovable screen needs a field that does not exist, the migration lands
  first and the UI is pointed at the new column afterwards.
- Ingest and the UI must not both write the same column. Ingest owns anything
  derived from a source; the UI owns workflow state.

## Before you open a pull request

```bash
make lint       # ruff check and format
make typecheck  # mypy
make test       # pytest — no network, no database
```

CI runs the same three. Tests must not require network access or a live
database; mark anything that does with `@pytest.mark.network` or
`@pytest.mark.database` and it will be deselected.

## Things that will not be merged

- A secret, a connection string or an API key in a tracked file.
- A data file. `data/`, `storage/`, `*.csv` and `*.pkl` are gitignored for a
  reason — the CMS DAC file is 839 MB.
- A column that identifies a patient. Provider and practice data only.
- A scraper for a source whose terms prohibit automated access.
