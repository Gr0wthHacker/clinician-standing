"""The connector contract.

PRD section 6: every connector is a scheduled job with the same shape — fetch,
checksum, diff against the last run, write evidence, emit change events. A
connector never writes a credential row directly from a parsed field; it writes
evidence first and derives credential rows from it.

Two behaviours the rest of the system depends on:

* ``run()`` always writes a ``source_runs`` row, including on failure. A failed
  connector that leaves no trace becomes a silent lapse, and section 11 targets
  zero of those.
* A second run over unchanged data produces zero changed rows. The diff is a
  content hash per identity key, carried between runs in ``STORAGE_PATH``, so a
  reload is never mistaken for a change (PRD Phase 2 acceptance).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import time
import traceback
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar
from uuid import UUID, uuid4

import psycopg

from ..config import Settings, get_settings
from ..db import connect, transaction
from ..evidence import read_blob, sha256_file, store_blob

__all__ = ["Connector", "ConnectorError", "DiffResult", "RunResult"]

LOGGER = logging.getLogger(__name__)

_CHUNK = 1 << 20


class ConnectorError(RuntimeError):
    """Raised for a connector-level failure that should fail the run."""


# ----------------------------------------------------------------- diff result


@dataclass
class DiffResult:
    """The change set between the previous run and this one.

    New and changed rows are spilled to an NDJSON file rather than held in
    memory: the first run of the DAC connector classifies all 3.39M deduplicated
    rows as new, and a steady-state run classifies almost none.

    Attributes:
        source_key: Owning connector key.
        rows_in: Rows read from the source after per-connector deduplication.
        rows_new: Identity keys not seen in the previous run.
        rows_changed: Identity keys whose content hash moved.
        rows_unchanged: Identity keys whose content hash is identical.
        rows_removed: Identity keys present last run and absent now.
        changes_path: NDJSON file, one ``{"change", "key", "row"}`` per line.
        state_path: Local file holding this run's state, promoted to storage
            only after ``load()`` succeeds.
        removed_keys: Identity key hashes that disappeared, for reporting.
    """

    source_key: str
    rows_in: int = 0
    rows_new: int = 0
    rows_changed: int = 0
    rows_unchanged: int = 0
    rows_removed: int = 0
    changes_path: Path | None = None
    state_path: Path | None = None
    removed_keys: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """True when this run produced any new or changed row."""
        return bool(self.rows_new or self.rows_changed)

    def iter_changes(self) -> Iterator[dict[str, Any]]:
        """Yield each spilled change record in file order."""
        if self.changes_path is None or not self.changes_path.exists():
            return
        with self.changes_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def iter_rows(self) -> Iterator[dict[str, Any]]:
        """Yield just the row payloads of new and changed records."""
        for record in self.iter_changes():
            yield record["row"]

    def summary(self) -> dict[str, Any]:
        """A JSON-serializable summary, stored and referenced by ``diff_ref``."""
        return {
            "source_key": self.source_key,
            "rows_in": self.rows_in,
            "rows_new": self.rows_new,
            "rows_changed": self.rows_changed,
            "rows_unchanged": self.rows_unchanged,
            "rows_removed": self.rows_removed,
            "removed_keys_sample": self.removed_keys[:1000],
        }


@dataclass
class RunResult:
    """Outcome of one connector run; mirrors the ``source_runs`` row."""

    source_key: str
    run_id: UUID
    started_at: datetime
    finished_at: datetime | None = None
    status: str = "failed"
    rows_in: int = 0
    rows_changed: int = 0
    rows_new: int = 0
    error: str | None = None
    diff_ref: str | None = None

    @property
    def ok(self) -> bool:
        """True when the run completed without error."""
        return self.status == "ok"


# -------------------------------------------------------------------- hashing


def _hash64(value: str) -> int:
    """Stable 64-bit digest of a string.

    blake2b at 8 bytes. At 3.39M keys the collision probability is around
    3e-7, which is acceptable for change detection and costs a third of the
    memory a hex digest would.
    """
    return int.from_bytes(hashlib.blake2b(value.encode("utf-8"), digest_size=8).digest(), "big")


# ------------------------------------------------------------------- connector


class Connector(ABC):
    """Base class for every source connector.

    Subclasses declare the registry metadata as class attributes and implement
    :meth:`fetch`, :meth:`parse`, :meth:`identity_key`, :meth:`content_tuple`
    and :meth:`load`. :meth:`checksum`, :meth:`diff` and :meth:`run` are
    provided and rarely need overriding.

    Class attributes:
        key: Matches ``sources.key``.
        display_name: Human label for the source registry.
        kind: ``bulk_file`` | ``api`` | ``push`` | ``scrape`` | ``manual``.
        cadence: ``daily`` | ``weekly`` | ``monthly`` | ``on_demand`` | ``push``.
        freshness_sla_days: How old an assertion from this source may be.
        is_primary_source: False means it cannot alone clear an obligation.
        terms_url: Terms of use reviewed for this source.
    """

    key: ClassVar[str] = ""
    display_name: ClassVar[str] = ""
    kind: ClassVar[str] = "bulk_file"
    cadence: ClassVar[str] = "monthly"
    freshness_sla_days: ClassVar[int] = 45
    is_primary_source: ClassVar[bool] = True
    terms_url: ClassVar[str | None] = None

    def __init__(self, settings: Settings | None = None) -> None:
        """Prepare a single run.

        Args:
            settings: Resolved settings; read from the environment when omitted.
        """
        if not self.key:
            raise ConnectorError(f"{type(self).__name__} must declare a key")
        self.settings = settings or get_settings()
        self.run_id: UUID = uuid4()
        self.request_ref: str | None = None
        self.fetched_path: Path | None = None
        self.fetched_checksum: str | None = None
        self.fetched_at: datetime = datetime.now(UTC)
        self.evidence_id: UUID | None = None
        self.log = logging.getLogger(f"{__name__}.{self.key}")

    # ------------------------------------------------------------- the contract

    @abstractmethod
    def fetch(self) -> Path:
        """Download the source to a local temp file and return its path."""

    def checksum(self, path: Path) -> str:
        """Return the sha256 hex digest of a fetched file."""
        return sha256_file(path)

    @abstractmethod
    def parse(self, path: Path) -> Iterator[dict[str, Any]]:
        """Yield normalized rows from the fetched file.

        Implementations stream. Any per-source deduplication (the DAC file's one
        row per clinician per location, for instance) happens here so that every
        downstream count sees deduplicated rows.
        """

    @abstractmethod
    def identity_key(self, row: dict[str, Any]) -> str:
        """Return the stable identity of a row across runs."""

    @abstractmethod
    def content_tuple(self, row: dict[str, Any]) -> Sequence[Any]:
        """Return the fields whose change makes a row 'changed'."""

    @abstractmethod
    def load(self, diff: DiffResult) -> None:
        """Write evidence and derive rows for the change set.

        Called with the connection-free diff; implementations open their own
        transaction. ``self.fetched_path``, ``self.fetched_checksum`` and
        ``self.request_ref`` are populated by :meth:`run` before this is called.
        """

    # ------------------------------------------------------------------- diff

    def diff(self, rows: Iterable[dict[str, Any]]) -> DiffResult:
        """Compare ``rows`` against the previous run's state.

        The previous run's state is a gzipped ``key_hash<TAB>content_hash``
        table in ``STORAGE_PATH``. Rerunning an unchanged file yields
        ``rows_new == rows_changed == 0``, which is the Phase 2 acceptance
        criterion.

        Args:
            rows: Normalized rows from :meth:`parse`.

        Returns:
            A :class:`DiffResult` whose new and changed rows are spilled to disk.
        """
        previous = self._load_state()
        work_dir = self.settings.ensure_work_dir()
        changes_path = work_dir / f"{self.key}-{self.run_id}.changes.ndjson"
        state_path = work_dir / f"{self.key}-{self.run_id}.state.tsv.gz"

        result = DiffResult(source_key=self.key, changes_path=changes_path, state_path=state_path)
        seen: set[int] = set()
        # A source may legitimately repeat an identity key -- the LEIE file lists
        # one business at several addresses under the same name and exclusion
        # date. Without disambiguation the last occurrence would overwrite the
        # others in the state table and every rerun would report phantom
        # changes, which breaks the Phase 2 acceptance criterion.
        duplicates: dict[int, int] = {}
        seen_extra: set[int] = set()

        with (
            changes_path.open("w", encoding="utf-8") as changes,
            gzip.open(state_path, "wt", encoding="utf-8") as state,
        ):
            for row in rows:
                key = self.identity_key(row)
                base_hash = _hash64(key)
                if base_hash in seen:
                    occurrence = duplicates.get(base_hash, 0) + 1
                    duplicates[base_hash] = occurrence
                    key = f"{key}\x00#{occurrence}"
                    key_hash = _hash64(key)
                    seen_extra.add(key_hash)
                else:
                    key_hash = base_hash
                    seen.add(base_hash)
                content_hash = _hash64(
                    "\x1f".join("" if v is None else str(v) for v in self.content_tuple(row))
                )
                result.rows_in += 1
                state.write(f"{key_hash:016x}\t{content_hash:016x}\n")

                prior = previous.get(key_hash)
                if prior is None:
                    change = "new"
                    result.rows_new += 1
                elif prior != content_hash:
                    change = "changed"
                    result.rows_changed += 1
                else:
                    result.rows_unchanged += 1
                    continue
                changes.write(
                    json.dumps({"change": change, "key": key, "row": row}, default=str) + "\n"
                )

        removed = [k for k in previous if k not in seen and k not in seen_extra]
        result.rows_removed = len(removed)
        result.removed_keys = [f"{k:016x}" for k in removed[:1000]]
        self.log.info(
            "diff: in=%s new=%s changed=%s unchanged=%s removed=%s",
            f"{result.rows_in:,}",
            f"{result.rows_new:,}",
            f"{result.rows_changed:,}",
            f"{result.rows_unchanged:,}",
            f"{result.rows_removed:,}",
        )
        return result

    def _state_key(self) -> str:
        """Storage key holding the previous run's row-hash table."""
        return f"state/{self.key}/rowhash.tsv.gz"

    def _load_state(self) -> dict[int, int]:
        """Load the previous run's row-hash table.

        At 3.39M rows this dictionary costs a few hundred megabytes. That is the
        deliberate trade for a self-contained diff that needs no extra table in
        the schema. If it ever becomes a problem, the upgrade is a sorted
        merge-join over the two state files rather than a bigger box.
        """
        raw = read_blob(self._state_key(), self.settings)
        if raw is None:
            self.log.info("no previous state for %s; treating every row as new", self.key)
            return {}
        table: dict[int, int] = {}
        for line in gzip.decompress(raw).decode("utf-8").splitlines():
            if not line:
                continue
            key_hex, _, content_hex = line.partition("\t")
            table[int(key_hex, 16)] = int(content_hex, 16)
        self.log.info("loaded %s prior row hashes", f"{len(table):,}")
        return table

    def _promote_state(self, diff: DiffResult) -> None:
        """Publish this run's state so the next run diffs against it."""
        if diff.state_path is None or not diff.state_path.exists():
            return
        store_blob(self._state_key(), diff.state_path.read_bytes(), self.settings)

    # -------------------------------------------------------------------- http

    def download(self, url: str, destination: Path) -> Path:
        """Stream a URL to ``destination`` with bounded retries.

        Args:
            url: Absolute URL to fetch.
            destination: Local path to write.

        Returns:
            ``destination``.

        Raises:
            ConnectorError: If every attempt fails.
        """
        destination.parent.mkdir(parents=True, exist_ok=True)
        if self.settings.use_cache and destination.is_file() and destination.stat().st_size:
            self.log.warning(
                "INGEST_USE_CACHE is set; reusing %s (%s bytes) instead of downloading %s",
                destination,
                f"{destination.stat().st_size:,}",
                url,
            )
            return destination
        last_error: Exception | None = None
        for attempt in range(1, self.settings.http_retries + 1):
            tmp = destination.with_suffix(destination.suffix + ".partial")
            try:
                request = urllib.request.Request(
                    url, headers={"User-Agent": self.settings.user_agent}
                )
                with (
                    urllib.request.urlopen(
                        request, timeout=self.settings.http_timeout_seconds
                    ) as response,
                    tmp.open("wb") as handle,
                ):
                    while chunk := response.read(_CHUNK):
                        handle.write(chunk)
                os.replace(tmp, destination)
                self.log.info("downloaded %s (%s bytes)", url, f"{destination.stat().st_size:,}")
                return destination
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                last_error = exc
                tmp.unlink(missing_ok=True)
                self.log.warning(
                    "download attempt %s/%s failed: %s", attempt, self.settings.http_retries, exc
                )
                if attempt < self.settings.http_retries:
                    time.sleep(min(30, 2**attempt))
        raise ConnectorError(f"could not download {url}: {last_error}")

    def fetch_json(self, url: str) -> Any:
        """GET a URL and parse the response as JSON.

        Args:
            url: Absolute URL.

        Returns:
            The decoded JSON document.

        Raises:
            ConnectorError: On a transport failure or unparsable body.
        """
        request = urllib.request.Request(url, headers={"User-Agent": self.settings.user_agent})
        try:
            with urllib.request.urlopen(
                request, timeout=self.settings.http_timeout_seconds
            ) as response:
                body = response.read()
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise ConnectorError(f"could not fetch {url}: {exc}") from exc
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ConnectorError(f"{url} did not return valid JSON: {exc}") from exc

    def work_file(self, name: str) -> Path:
        """Return a path inside the scratch directory for this connector."""
        return self.settings.ensure_work_dir() / f"{self.key}-{name}"

    # --------------------------------------------------------------- registry

    def ensure_registered(self, conn: psycopg.Connection) -> None:
        """Insert this connector's ``sources`` row if the registry lacks it.

        ``source_runs.source_key`` is a foreign key, so a run of a connector the
        registry has never seen would otherwise fail on the audit write rather
        than on the work.

        The registry wins where it already has a row: the seeded
        ``freshness_sla_days`` is adopted for this run so that
        ``evidence.freshness_expires_at`` and ``sources.freshness_sla_days`` can
        never disagree. Section 8.1 reads the SLA through the registry, so a
        connector quietly using a different number would make assertions look
        fresh that the registry considers stale.
        """
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into sources (
                    key, display_name, kind, cadence, freshness_sla_days,
                    is_primary_source, terms_url, enabled
                ) values (%s, %s, %s, %s, %s, %s, %s, true)
                on conflict (key) do nothing
                """,
                (
                    self.key,
                    self.display_name or self.key,
                    self.kind,
                    self.cadence,
                    self.freshness_sla_days,
                    self.is_primary_source,
                    self.terms_url,
                ),
            )
            cur.execute(
                "select freshness_sla_days, enabled from sources where key = %s", (self.key,)
            )
            row = cur.fetchone()
        if row and row[0] and row[0] != self.freshness_sla_days:
            self.log.info(
                "adopting registry freshness_sla_days=%s for %s (class default %s)",
                row[0],
                self.key,
                type(self).freshness_sla_days,
            )
            self.freshness_sla_days = row[0]
        if row and row[1] is False:
            self.log.warning("sources.enabled is false for %s; running anyway", self.key)

    def _write_source_run(self, result: RunResult) -> None:
        """Persist the ``source_runs`` row. Never raises into the caller."""
        try:
            with transaction(None, self.settings) as conn:
                self.ensure_registered(conn)
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        insert into source_runs (
                            id, source_key, started_at, finished_at, status,
                            rows_in, rows_changed, rows_new, error, diff_ref
                        ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            result.run_id,
                            result.source_key,
                            result.started_at,
                            result.finished_at,
                            result.status,
                            result.rows_in,
                            result.rows_changed,
                            result.rows_new,
                            result.error,
                            result.diff_ref,
                        ),
                    )
        except psycopg.Error as exc:
            # The run log is the audit trail; losing it is serious, but it must
            # not mask the original failure that is already on the RunResult.
            self.log.error("could not write source_runs row for %s: %s", self.key, exc)

    # ------------------------------------------------------------------- run

    def run(self) -> RunResult:
        """Orchestrate fetch, checksum, diff and load, and log the run.

        Returns:
            A :class:`RunResult`. The method does not raise on connector
            failure; it records ``status='failed'`` with the error text and
            returns, so a batch run can continue to the next source.
        """
        result = RunResult(source_key=self.key, run_id=self.run_id, started_at=datetime.now(UTC))
        diff: DiffResult | None = None
        loaded = False
        try:
            self.settings.validate()
            path = self.fetch()
            self.fetched_path = path
            self.fetched_checksum = self.checksum(path)
            self.log.info("fetched %s sha256=%s", path.name, self.fetched_checksum)

            diff = self.diff(self.parse(path))
            result.rows_in = diff.rows_in
            result.rows_new = diff.rows_new
            result.rows_changed = diff.rows_changed

            summary = diff.summary()
            summary.update(
                {
                    "run_id": str(self.run_id),
                    "request_ref": self.request_ref,
                    "payload_sha256": self.fetched_checksum,
                    "fetched_at": self.fetched_at.isoformat(),
                }
            )
            result.diff_ref = store_blob(
                f"diffs/{self.key}/{self.run_id}.json",
                json.dumps(summary, indent=2, default=str).encode("utf-8"),
                self.settings,
            )

            self.load(diff)
            loaded = True
            self._promote_state(diff)
            result.status = "ok"
        except Exception as exc:
            result.status = "partial" if loaded else "failed"
            result.error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"[:8000]
            self.log.exception("connector %s failed", self.key)
        finally:
            result.finished_at = datetime.now(UTC)
            self._write_source_run(result)
            self._cleanup(diff)
        return result

    def _cleanup(self, diff: DiffResult | None) -> None:
        """Remove scratch files unless KEEP_DOWNLOADS asks to keep them."""
        if self.settings.keep_downloads:
            return
        for candidate in (
            diff.changes_path if diff else None,
            diff.state_path if diff else None,
            self.fetched_path,
        ):
            if candidate is None:
                continue
            try:
                Path(candidate).unlink(missing_ok=True)
            except OSError as exc:
                self.log.warning("could not remove %s: %s", candidate, exc)

    # -------------------------------------------------------------- utilities

    def open_connection(self) -> psycopg.Connection:
        """Open a connection using this connector's settings."""
        return connect(self.settings)
