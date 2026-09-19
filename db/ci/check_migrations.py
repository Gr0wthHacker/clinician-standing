"""Migration lint: names strictly increasing, and applied migrations unedited.

Two rules the CI enforces on every pull request, because both have bitten before
and neither shows up until a fresh environment is built:

1. **Naming and ordering.** Every file under ``db/migrations`` is
   ``NNNN_snake_case.sql`` with a four-digit prefix, the prefixes are strictly
   increasing with no duplicates, so ``psql`` applying them in glob order applies
   them in intended order.
2. **Applied migrations are immutable.** A migration that already exists on the
   base branch must be byte-identical here. Editing an applied migration changes
   the schema in new environments and in no other, which is the one thing
   ``CONTRIBUTING.md`` calls the rule that matters most. New migrations (absent
   from the base) are fine; that is how the schema moves forward.

Usage::

    python db/ci/check_migrations.py [base-ref]     # base-ref defaults to origin/main

Exits non-zero with a list of problems, or prints a one-line pass.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

MIGRATIONS = Path("db/migrations")
NAME_RE = re.compile(r"^(\d{4})_[a-z0-9]+(?:_[a-z0-9]+)*\.sql$")


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def _ref_exists(ref: str) -> bool:
    return _git("rev-parse", "--verify", "--quiet", ref).returncode == 0


def check(base: str) -> list[str]:
    """Return a list of problems; empty means the migrations are well-formed."""
    errors: list[str] = []
    files = sorted(MIGRATIONS.glob("*.sql"))
    if not files:
        return ["no migrations found under db/migrations"]

    numbers: list[int] = []
    for path in files:
        match = NAME_RE.match(path.name)
        if match is None:
            errors.append(f"bad migration name (want NNNN_snake_case.sql): {path.name}")
            continue
        numbers.append(int(match.group(1)))

    if numbers != sorted(numbers):
        errors.append(f"migration numbers are not strictly increasing: {numbers}")
    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    if duplicates:
        errors.append(f"duplicate migration numbers: {duplicates}")

    # Applied migrations are immutable: anything this branch changed that also
    # exists on the base branch was edited, not added.
    if not _ref_exists(base):
        print(f"note: base ref {base!r} not found; skipping the immutability check")
        return errors
    changed = _git("diff", "--name-only", f"{base}...HEAD", "--", str(MIGRATIONS))
    for rel in changed.stdout.split():
        if _git("cat-file", "-e", f"{base}:{rel}").returncode == 0:
            errors.append(f"already-applied migration edited (add a new one instead): {rel}")
    return errors


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    errors = check(base)
    if errors:
        print("MIGRATION LINT FAILED:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"migration lint ok: {len(sorted(MIGRATIONS.glob('*.sql')))} migrations, base {base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
