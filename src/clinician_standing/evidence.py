"""Evidence-first writes.

PRD section 5.2: every credential row is an *assertion* and must carry an
``evidence_id``. PRD section 14 Phase 1 acceptance: a credential row cannot be
inserted without a valid one. This module is the only sanctioned way to create
that row, and :func:`insert_credential` is the only sanctioned way to write a
credential table.

The order is fixed and not negotiable:

1. persist the raw payload to ``STORAGE_PATH`` (content-addressed by sha256),
2. insert the ``evidence`` row with the digest, the request reference, the
   normalized extraction and the identity keys that matched,
3. only then derive credential rows that reference it.

Raw payloads are content-addressed, so re-fetching an unchanged monthly file
does not re-upload 839 MB; it still gets its own ``evidence`` row, because the
fetch itself is the fact being recorded.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from .config import Settings, get_settings
from .db import transaction

__all__ = [
    "CREDENTIAL_TABLES",
    "EvidenceError",
    "EvidenceRequired",
    "insert_credential",
    "json_payload",
    "read_blob",
    "require_evidence",
    "sha256_bytes",
    "sha256_file",
    "store_blob",
    "store_evidence",
    "store_evidence_for_file",
]

LOGGER = logging.getLogger(__name__)

#: Tables whose rows are assertions and therefore require an ``evidence_id``.
CREDENTIAL_TABLES: frozenset[str] = frozenset(
    {"licenses", "registrations", "enrollments", "privileges", "ce_records", "sanctions"}
)

_CHUNK = 1 << 20


class EvidenceError(RuntimeError):
    """Raised when evidence cannot be stored."""


class EvidenceRequired(RuntimeError):
    """Raised when a credential write is attempted without valid evidence."""


# --------------------------------------------------------------------- hashing


def sha256_bytes(payload: bytes) -> str:
    """Return the hex sha256 digest of ``payload``."""
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    """Return the hex sha256 digest of a file, streaming it in 1 MiB chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------- storage


def _storage_key(source_key: str, digest: str, fetched_at: datetime, suffix: str) -> str:
    """Build the content-addressed object key for a payload."""
    return f"evidence/{source_key}/{fetched_at:%Y/%m/%d}/{digest}{suffix}"


def _put_bytes(key: str, payload: bytes, settings: Settings) -> tuple[str, bool]:
    """Write bytes to storage, returning (reference, deduplicated)."""
    if settings.storage_is_s3:
        return _s3_put(key, payload=payload, path=None, settings=settings)
    target = settings.local_storage_root / key
    if target.exists() and target.stat().st_size == len(payload):
        return str(target), True
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".partial")
    tmp.write_bytes(payload)
    os.replace(tmp, target)
    return str(target), False


def _put_file(key: str, path: Path, settings: Settings) -> tuple[str, bool]:
    """Copy a file to storage, returning (reference, deduplicated)."""
    if settings.storage_is_s3:
        return _s3_put(key, payload=None, path=path, settings=settings)
    target = settings.local_storage_root / key
    size = path.stat().st_size
    if target.exists() and target.stat().st_size == size:
        return str(target), True
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".partial")
    shutil.copyfile(path, tmp)
    os.replace(tmp, target)
    return str(target), False


def _s3_put(
    key: str, *, payload: bytes | None, path: Path | None, settings: Settings
) -> tuple[str, bool]:
    """Upload to S3. boto3 is imported lazily so local runs need no AWS SDK."""
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError as exc:  # pragma: no cover - depends on deployment extras
        raise EvidenceError("STORAGE_PATH is an s3:// URI but boto3 is not installed") from exc

    prefix = f"{settings.s3_prefix}/" if settings.s3_prefix else ""
    object_key = f"{prefix}{key}"
    ref = f"s3://{settings.s3_bucket}/{object_key}"
    client = boto3.client("s3")
    try:
        client.head_object(Bucket=settings.s3_bucket, Key=object_key)
        return ref, True
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code not in {"404", "NoSuchKey", "NotFound"}:
            raise EvidenceError(f"S3 head_object failed for {ref}: {exc}") from exc

    if payload is not None:
        client.put_object(Bucket=settings.s3_bucket, Key=object_key, Body=payload)
    elif path is not None:
        client.upload_file(str(path), settings.s3_bucket, object_key)
    else:  # pragma: no cover - guarded by callers
        raise EvidenceError("_s3_put needs either payload or path")
    return ref, False


def store_blob(relative_key: str, payload: bytes, settings: Settings | None = None) -> str:
    """Persist a non-evidence artifact (a diff summary, a connector state file).

    Args:
        relative_key: Key under ``STORAGE_PATH``, e.g. ``diffs/oig_leie/<run>.json``.
        payload: Bytes to write.
        settings: Resolved settings; read from the environment when omitted.

    Returns:
        The storage reference, suitable for ``source_runs.diff_ref``.
    """
    settings = settings or get_settings()
    ref, _ = _put_bytes(relative_key, payload, settings)
    return ref


def read_blob(relative_key: str, settings: Settings | None = None) -> bytes | None:
    """Read back an artifact written by :func:`store_blob`, or None if absent."""
    settings = settings or get_settings()
    if settings.storage_is_s3:
        try:
            import boto3
            from botocore.exceptions import ClientError
        except ImportError as exc:  # pragma: no cover
            raise EvidenceError("STORAGE_PATH is an s3:// URI but boto3 is not installed") from exc
        prefix = f"{settings.s3_prefix}/" if settings.s3_prefix else ""
        object_key = f"{prefix}{relative_key}"
        client = boto3.client("s3")
        try:
            response = client.get_object(Bucket=settings.s3_bucket, Key=object_key)
        except ClientError as exc:
            # Only a genuine miss may read as "no previous state". An
            # AccessDenied or a SlowDown swallowed here would present as a first
            # run: the diff would reclassify the entire file as new and the run
            # would finish green. Same code list as _s3_put.
            code = exc.response.get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise EvidenceError(
                f"S3 get_object failed for s3://{settings.s3_bucket}/{object_key}: {exc}"
            ) from exc
        # boto3 is untyped, so the read() is Any. Bind it to the declared
        # return type here rather than letting Any escape the function.
        body: bytes = response["Body"].read()
        return body

    target = settings.local_storage_root / relative_key
    if not target.is_file():
        return None
    return target.read_bytes()


# -------------------------------------------------------------------- evidence


_INSERT_EVIDENCE = """
insert into evidence (
    id, source_key, fetched_at, request_ref, payload_ref, payload_sha256,
    parsed, match_keys, freshness_expires_at
) values (
    %(id)s, %(source_key)s, %(fetched_at)s, %(request_ref)s, %(payload_ref)s,
    %(payload_sha256)s, %(parsed)s, %(match_keys)s, %(freshness_expires_at)s
)
"""


def _insert_evidence_row(
    conn: psycopg.Connection,
    *,
    evidence_id: UUID,
    source_key: str,
    fetched_at: datetime,
    request_ref: str | None,
    payload_ref: str,
    payload_sha256: str,
    parsed: Mapping[str, Any] | Sequence[Any] | None,
    match_keys: Mapping[str, Any] | None,
    freshness_days: int,
) -> None:
    """Insert one ``evidence`` row. Caller owns the transaction."""
    with conn.cursor() as cur:
        cur.execute(
            _INSERT_EVIDENCE,
            {
                "id": evidence_id,
                "source_key": source_key,
                "fetched_at": fetched_at,
                "request_ref": request_ref,
                "payload_ref": payload_ref,
                "payload_sha256": payload_sha256,
                "parsed": Jsonb(parsed) if parsed is not None else None,
                "match_keys": Jsonb(match_keys) if match_keys is not None else None,
                "freshness_expires_at": fetched_at + timedelta(days=freshness_days),
            },
        )


def store_evidence(
    source_key: str,
    request_ref: str | None,
    payload_bytes: bytes,
    parsed: Mapping[str, Any] | Sequence[Any] | None,
    match_keys: Mapping[str, Any] | None,
    freshness_days: int,
    *,
    conn: psycopg.Connection | None = None,
    fetched_at: datetime | None = None,
    settings: Settings | None = None,
    suffix: str = ".bin",
) -> UUID:
    """Store a raw payload and record the ``evidence`` row for it.

    This is the single entry point for evidence creation. Nothing in this
    codebase may insert a credential row without calling it first.

    Args:
        source_key: Registry key from ``sources.key`` (``cms_dac``, ``oig_leie``,
            ``cms_revalidation``, ...).
        request_ref: The URL fetched or API call made.
        payload_bytes: The raw response, exactly as received.
        parsed: Normalized extraction, stored as ``evidence.parsed`` jsonb.
        match_keys: Which identity keys matched and how, e.g.
            ``{"npi": "1234567893", "method": "npi_exact"}``. Section 8.1
            auto-clear requires a strong single match, so this is not optional
            bookkeeping.
        freshness_days: The source's ``freshness_sla_days``; drives
            ``freshness_expires_at``.
        conn: Join an existing transaction. When omitted one is opened and
            committed here.
        fetched_at: Override the fetch timestamp (defaults to now, UTC).
        settings: Resolved settings.
        suffix: Extension for the stored object.

    Returns:
        The new ``evidence.id``.

    Raises:
        EvidenceError: If the payload cannot be persisted.
    """
    settings = settings or get_settings()
    fetched_at = fetched_at or datetime.now(UTC)
    digest = sha256_bytes(payload_bytes)
    key = _storage_key(source_key, digest, fetched_at, suffix)

    if settings.store_raw_payloads:
        payload_ref, dedup = _put_bytes(key, payload_bytes, settings)
    else:
        payload_ref, dedup = f"not-stored://{key}", False
    if dedup:
        LOGGER.debug("payload %s already present at %s", digest[:12], payload_ref)

    evidence_id = uuid4()
    with transaction(conn, settings) as active:
        _insert_evidence_row(
            active,
            evidence_id=evidence_id,
            source_key=source_key,
            fetched_at=fetched_at,
            request_ref=request_ref,
            payload_ref=payload_ref,
            payload_sha256=digest,
            parsed=parsed,
            match_keys=match_keys,
            freshness_days=freshness_days,
        )
    return evidence_id


def store_evidence_for_file(
    source_key: str,
    request_ref: str | None,
    path: Path,
    parsed: Mapping[str, Any] | Sequence[Any] | None,
    match_keys: Mapping[str, Any] | None,
    freshness_days: int,
    *,
    conn: psycopg.Connection | None = None,
    fetched_at: datetime | None = None,
    settings: Settings | None = None,
    sha256: str | None = None,
) -> UUID:
    """Streaming variant of :func:`store_evidence` for bulk files.

    Same contract and same ordering, but the payload is never held in memory.
    The DAC file is 839 MB and the revalidation file 540 MB; reading either into
    a ``bytes`` would be a needless 800 MB allocation.

    Args:
        source_key: Registry key from ``sources.key``.
        request_ref: The URL fetched.
        path: Local file holding the raw payload.
        parsed: Normalized summary of the file (counts, discovered URL, header).
        match_keys: Identity keys this evidence can be joined on.
        freshness_days: The source's ``freshness_sla_days``.
        conn: Join an existing transaction.
        fetched_at: Override the fetch timestamp.
        settings: Resolved settings.
        sha256: Precomputed digest, to avoid a second pass over the file.

    Returns:
        The new ``evidence.id``.
    """
    settings = settings or get_settings()
    fetched_at = fetched_at or datetime.now(UTC)
    digest = sha256 or sha256_file(path)
    key = _storage_key(source_key, digest, fetched_at, path.suffix or ".bin")

    if settings.store_raw_payloads:
        payload_ref, dedup = _put_file(key, path, settings)
    else:
        payload_ref, dedup = f"not-stored://{key}", False
    if dedup:
        LOGGER.info("payload %s already retained at %s; no re-upload", digest[:12], payload_ref)

    evidence_id = uuid4()
    with transaction(conn, settings) as active:
        _insert_evidence_row(
            active,
            evidence_id=evidence_id,
            source_key=source_key,
            fetched_at=fetched_at,
            request_ref=request_ref,
            payload_ref=payload_ref,
            payload_sha256=digest,
            parsed=parsed,
            match_keys=match_keys,
            freshness_days=freshness_days,
        )
    return evidence_id


# ------------------------------------------------------- guarded credential IO


def evidence_exists(conn: psycopg.Connection, evidence_id: UUID) -> bool:
    """Return True when ``evidence_id`` names a real evidence row."""
    with conn.cursor() as cur:
        cur.execute("select 1 from evidence where id = %s", (evidence_id,))
        return cur.fetchone() is not None


def require_evidence(conn: psycopg.Connection, evidence_id: UUID | None) -> UUID:
    """Assert that ``evidence_id`` exists before a credential row is written.

    Args:
        conn: Connection used for the credential write.
        evidence_id: Candidate evidence id.

    Returns:
        The validated id.

    Raises:
        EvidenceRequired: If the id is missing or unknown. The database has its
            own not-null foreign key; this raises earlier and with a message
            that says which invariant was broken.
    """
    if evidence_id is None:
        raise EvidenceRequired(
            "Refusing to write a credential row without evidence. Call "
            "evidence.store_evidence() first (PRD 5.2, Phase 1 acceptance)."
        )
    if not evidence_exists(conn, evidence_id):
        raise EvidenceRequired(f"evidence_id {evidence_id} does not exist")
    return evidence_id


def insert_credential(
    conn: psycopg.Connection,
    table: str,
    values: Mapping[str, Any],
    evidence_id: UUID,
    *,
    verified_at: datetime | None = None,
) -> UUID:
    """Insert one credential row, refusing to proceed without valid evidence.

    Args:
        conn: Open connection inside a transaction.
        table: One of :data:`CREDENTIAL_TABLES`.
        values: Column/value mapping, excluding ``id``, ``evidence_id`` and
            ``verified_at``.
        evidence_id: Evidence backing the assertion.
        verified_at: Assertion timestamp; defaults to now (UTC). Ignored for
            tables that have no ``verified_at`` column.

    Returns:
        The new row id.

    Raises:
        EvidenceRequired: If ``evidence_id`` is missing or unknown.
        ValueError: If ``table`` is not a credential table.
    """
    if table not in CREDENTIAL_TABLES:
        raise ValueError(f"{table!r} is not a credential table; use plain SQL")
    require_evidence(conn, evidence_id)

    payload: dict[str, Any] = dict(values)
    payload["evidence_id"] = evidence_id
    if table in {"licenses", "registrations", "enrollments"}:
        payload["verified_at"] = verified_at or datetime.now(UTC)
    row_id = uuid4()
    payload["id"] = row_id

    columns = ", ".join(f'"{c}"' for c in payload)
    placeholders = ", ".join(f"%({c})s" for c in payload)
    with conn.cursor() as cur:
        cur.execute(f"insert into {table} ({columns}) values ({placeholders})", payload)
    return row_id


def json_payload(record: Mapping[str, Any] | Iterable[Any]) -> bytes:
    """Serialize a record for storage as an evidence payload."""
    return json.dumps(record, default=str, sort_keys=True).encode("utf-8")
