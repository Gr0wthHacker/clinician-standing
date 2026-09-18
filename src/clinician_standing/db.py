"""Postgres access helpers built on psycopg 3.

Three things live here and nothing else: how to open a connection, how to run a
unit of work atomically, and how to get a lot of rows into a table quickly.
Bulk loads always go through ``COPY``; the ingest files carry 3.39M rows and
row-at-a-time ``INSERT`` is not an option.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql

from .config import REQUIRED_TABLES, ConfigError, Settings, get_settings

__all__ = [
    "connect",
    "copy_file_into",
    "copy_from_csv",
    "execute",
    "fetch_all",
    "fetch_one",
    "fetch_scalar",
    "missing_tables",
    "table_exists",
    "transaction",
]

LOGGER = logging.getLogger(__name__)


def connect(settings: Settings | None = None, *, autocommit: bool = False) -> psycopg.Connection:
    """Open a Postgres connection.

    Args:
        settings: Resolved settings; read from the environment when omitted.
        autocommit: Open in autocommit mode. Use for DDL-ish maintenance only;
            ingest work runs inside :func:`transaction`.

    Returns:
        An open connection. The caller owns closing it.

    Raises:
        ConfigError: If ``DATABASE_URL`` is not set.
    """
    settings = settings or get_settings()
    if not settings.database_url:
        raise ConfigError("DATABASE_URL is not set; cannot open a connection")
    conn = psycopg.connect(settings.database_url, autocommit=autocommit)
    return conn


@contextmanager
def transaction(
    conn: psycopg.Connection | None = None,
    settings: Settings | None = None,
) -> Iterator[psycopg.Connection]:
    """Run a unit of work atomically.

    When ``conn`` is omitted a connection is opened, committed on success,
    rolled back on any exception, and closed either way. When ``conn`` is
    supplied the caller keeps ownership and a savepoint-backed nested
    transaction is used instead, so this composes.

    Args:
        conn: An existing connection to join, or None to open a new one.
        settings: Settings used when opening a new connection.

    Yields:
        The connection to use for the unit of work.
    """
    if conn is not None:
        with conn.transaction():
            yield conn
        return

    owned = connect(settings)
    try:
        with owned.transaction():
            yield owned
    finally:
        owned.close()


def copy_from_csv(
    conn: psycopg.Connection,
    table: str,
    columns: Sequence[str],
    rows: Iterable[Sequence[Any]],
    *,
    batch_size: int | None = None,
) -> int:
    """Bulk-load ``rows`` into ``table`` with ``COPY ... FROM STDIN``.

    The name keeps the "csv" wording the repo conventions use, but rows are
    streamed as adapted tuples rather than serialized to CSV text, which avoids
    quoting bugs on free-text fields such as practice legal names.

    Args:
        conn: Open connection. The caller controls the transaction.
        table: Destination table, optionally schema-qualified.
        columns: Column names in the same order as each row tuple.
        rows: Iterable of row tuples. Consumed lazily, so a 3.39M-row generator
            never has to be materialized.
        batch_size: Rows between progress log lines.

    Returns:
        Number of rows written.
    """
    if not columns:
        raise ValueError("copy_from_csv requires at least one column")
    batch_size = batch_size or get_settings().copy_batch_size

    parts = table.split(".")
    target = sql.Identifier(*parts)
    statement = sql.SQL("COPY {} ({}) FROM STDIN").format(
        target,
        sql.SQL(", ").join(sql.Identifier(c) for c in columns),
    )

    written = 0
    with conn.cursor() as cur, cur.copy(statement) as copy:
        for row in rows:
            copy.write_row(row)
            written += 1
            if written % batch_size == 0:
                LOGGER.info("COPY %s: %s rows", table, f"{written:,}")
    LOGGER.info("COPY %s: %s rows total", table, f"{written:,}")
    return written


def copy_file_into(
    conn: psycopg.Connection,
    table: str,
    columns: Sequence[str],
    path: Path,
    *,
    encoding: str = "utf-8",
    header: bool = True,
    delimiter: str = ",",
) -> int:
    """``COPY`` a delimited file straight into a table.

    Only safe when the file's column order already matches ``columns`` and its
    encoding is known. The latin-1 federal files must be transcoded first, so
    they go through :func:`copy_from_csv` instead.

    Args:
        conn: Open connection.
        table: Destination table.
        columns: Column names in file order.
        path: File to load.
        encoding: File encoding, declared to Postgres.
        header: Whether the file's first line is a header row.
        delimiter: Field delimiter.

    Returns:
        Number of rows written.
    """
    parts = table.split(".")
    statement = sql.SQL(
        "COPY {} ({}) FROM STDIN WITH (FORMAT csv, HEADER {}, DELIMITER {}, ENCODING {})"
    ).format(
        sql.Identifier(*parts),
        sql.SQL(", ").join(sql.Identifier(c) for c in columns),
        sql.Literal(header),
        sql.Literal(delimiter),
        sql.Literal(encoding),
    )
    with conn.cursor() as cur:
        with cur.copy(statement) as copy, path.open("rb") as handle:
            while chunk := handle.read(1 << 20):
                copy.write(chunk)
        return cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0


def table_exists(conn: psycopg.Connection, table: str) -> bool:
    """Return True when ``table`` is visible on the current search_path."""
    with conn.cursor() as cur:
        cur.execute("select to_regclass(%s) is not null", (table,))
        row = cur.fetchone()
    return bool(row and row[0])


def missing_tables(conn: psycopg.Connection, tables: Sequence[str] = REQUIRED_TABLES) -> list[str]:
    """Return the subset of ``tables`` that does not exist yet."""
    return [name for name in tables if not table_exists(conn, name)]


def fetch_all(
    conn: psycopg.Connection, statement: str, params: Sequence[Any] | dict[str, Any] | None = None
) -> list[tuple[Any, ...]]:
    """Run a query and return every row."""
    with conn.cursor() as cur:
        cur.execute(statement, params)
        return cur.fetchall()


def fetch_one(
    conn: psycopg.Connection, statement: str, params: Sequence[Any] | dict[str, Any] | None = None
) -> tuple[Any, ...] | None:
    """Run a query and return the first row, or None."""
    with conn.cursor() as cur:
        cur.execute(statement, params)
        return cur.fetchone()


def fetch_scalar(
    conn: psycopg.Connection, statement: str, params: Sequence[Any] | dict[str, Any] | None = None
) -> Any:
    """Run a query and return the first column of the first row, or None."""
    row = fetch_one(conn, statement, params)
    return row[0] if row else None


def execute(
    conn: psycopg.Connection, statement: str, params: Sequence[Any] | dict[str, Any] | None = None
) -> int:
    """Run a statement and return the affected row count."""
    with conn.cursor() as cur:
        cur.execute(statement, params)
        return cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0
