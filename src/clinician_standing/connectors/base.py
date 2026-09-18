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
import urllib.parse
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

__all__ = [
    "ALLOWED_DOWNLOAD_HOSTS",
    "Connector",
    "ConnectorError",
    "DiffResult",
    "RunResult",
]

LOGGER = logging.getLogger(__name__)

_CHUNK = 1 << 20

#: Hosts this ingest is allowed to fetch from, and the only ones.
#:
#: Two of the three connectors discover their download URL from a remote JSON
#: document -- the CMS metastore item for the DAC file, data.cms.gov/data.json
#: for the revalidation file -- and hand whatever ``downloadURL`` they find
#: straight to :meth:`Connector.download`, which passes it to
#: ``urllib.request.urlopen``. urllib honours ``file://`` and ``ftp://`` and any
#: host at all, so a hijacked, mistyped or substituted entry in that document
#: would be downloaded, checksummed, stored as evidence under a seven-year
#: retention policy and parsed into the roster, with nothing in the audit trail
#: marking it as anything other than a normal CMS release. Every URL is checked
#: against this list, and the scheme against ``https``, before a byte is read.
#:
#: Adding a host here is a deliberate act: it widens what this system will
#: accept as federal evidence. A connector may narrow the list further by
#: overriding :attr:`Connector.allowed_hosts`.
ALLOWED_DOWNLOAD_HOSTS: frozenset[str] = frozenset(
    {
        "data.cms.gov",  # CMS provider-data metastore, data.json and its payloads
        "download.cms.gov",  # CMS bulk download host (NPPES, some CMS extracts)
        "oig.hhs.gov",  # OIG LEIE exclusions file
    }
)


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


# --------------------------------------------------------------- re-iteration


class _ReparsedRows:
    """Re-runs ``connector.parse(path)`` on every iteration.

    :meth:`Connector.diff` needs two passes over the rows and the files are too
    large to materialize, so the second pass re-parses the local file rather
    than keeping 3.39M dicts alive.
    """

    __slots__ = ("_connector", "_path")

    def __init__(self, connector: Connector, path: Path) -> None:
        self._connector = connector
        self._path = path

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self._connector.parse(self._path))


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
            Declared per connector, but the registry wins: see
            :meth:`ensure_registered`, which rebinds it per run.
        is_primary_source: False means it cannot alone clear an obligation.
            Same rule as ``freshness_sla_days`` -- the registry wins.
        terms_url: Terms of use reviewed for this source.
        allowed_hosts: Hosts this connector may fetch from. Defaults to
            :data:`ALLOWED_DOWNLOAD_HOSTS`; narrow it, do not widen it.
        min_rows_fraction: Plausibility floor, see
            :meth:`_check_row_plausibility`.
    """

    key: ClassVar[str] = ""
    display_name: ClassVar[str] = ""
    kind: ClassVar[str] = "bulk_file"
    cadence: ClassVar[str] = "monthly"
    # freshness_sla_days and is_primary_source are deliberately NOT ClassVar:
    # the class declaration is only the value used against a database whose
    # registry has no row for this source. ensure_registered() rebinds both on
    # the instance from sources, which is authoritative.
    freshness_sla_days: int = 45
    is_primary_source: bool = True
    terms_url: ClassVar[str | None] = None
    allowed_hosts: ClassVar[frozenset[str]] = ALLOWED_DOWNLOAD_HOSTS
    min_rows_fraction: ClassVar[float] = 0.5

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
        # True when fetch() returned a caller-owned file (a LOCAL_SOURCE_*
        # override) rather than something this run downloaded. _cleanup() must
        # never unlink such a file: it belongs to the operator, not to the run.
        self.fetched_is_external: bool = False
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
        criterion -- and that has to hold when the publisher reorders rows
        inside the file, which it does.

        DUPLICATE IDENTITY KEYS. A source may legitimately repeat an identity
        key: the LEIE file lists one business at several addresses under the
        same name and exclusion date, and the revalidation file has 38,417
        groups of repeated ``(NPI, group PAC ID, enrolment id)``, 38,286 of
        which differ in content. Something has to tell those rows apart or the
        last one in the file overwrites the others in the state table.

        The disambiguator is derived from the row's own content, never from its
        position in the file. Within a repeated group the member with the
        smallest content hash keeps the bare identity key and the rest are
        suffixed with their content hash, so the set of keys a group produces
        depends only on the set of rows in it. The previous implementation
        numbered them ``#1``, ``#2`` in file order, which meant that reordering
        two rows inside a group moved both their keys: on the measured
        revalidation file that is up to ~46,000 rows reported as changed by a
        run in which nothing changed. A changed row is a row the loader
        rewrites, so phantom changes are not merely a noisy count.

        Args:
            rows: Normalized rows from :meth:`parse`. Iterated **twice** -- once
                to find the repeated identity keys, once to classify -- so a
                one-shot iterator is materialized into a list first. :meth:`run`
                passes a re-iterable that re-runs :meth:`parse`, so the 3.39M-row
                files are never held in memory.

        Returns:
            A :class:`DiffResult` whose new and changed rows are spilled to disk.
        """
        if iter(rows) is rows:
            # A generator: consuming it for the duplicate scan would leave
            # nothing to classify. Small inputs only -- run() never lands here.
            rows = list(rows)

        duplicated = self._duplicate_identity_hashes(rows)
        if duplicated:
            self.log.info(
                "%s identity keys repeat in this file; disambiguating by content hash",
                f"{len(duplicated):,}",
            )

        # Loaded after the duplicate scan so the scan's own key set is already
        # freed: at 3.39M rows both structures at once are a few hundred MB.
        previous = self._load_state()
        work_dir = self.settings.ensure_work_dir()
        changes_path = work_dir / f"{self.key}-{self.run_id}.changes.ndjson"
        state_path = work_dir / f"{self.key}-{self.run_id}.state.tsv.gz"

        result = DiffResult(source_key=self.key, changes_path=changes_path, state_path=state_path)
        # Only the members of repeated groups are buffered, and only until the
        # end of the pass: 38k groups on the largest real file, not 3.39M rows.
        groups: dict[int, list[tuple[int, dict[str, Any]]]] = {}

        with (
            changes_path.open("w", encoding="utf-8") as changes,
            gzip.open(state_path, "wt", encoding="utf-8") as state,
        ):

            def classify(key: str, content_hash: int, row: dict[str, Any]) -> None:
                """Write one row's state line and, if it moved, its change line."""
                key_hash = _hash64(key)
                state.write(f"{key_hash:016x}\t{content_hash:016x}\n")
                # pop, not get: whatever is left in `previous` at the end is
                # exactly the set of keys that disappeared, which saves carrying
                # a second 3.39M-entry "seen" set just to compute it.
                prior = previous.pop(key_hash, None)
                if prior is None:
                    change = "new"
                    result.rows_new += 1
                elif prior != content_hash:
                    change = "changed"
                    result.rows_changed += 1
                else:
                    result.rows_unchanged += 1
                    return
                changes.write(
                    json.dumps({"change": change, "key": key, "row": row}, default=str) + "\n"
                )

            for row in rows:
                key = self.identity_key(row)
                base_hash = _hash64(key)
                content_hash = _hash64(
                    "\x1f".join("" if v is None else str(v) for v in self.content_tuple(row))
                )
                result.rows_in += 1
                if base_hash in duplicated:
                    groups.setdefault(base_hash, []).append((content_hash, row))
                else:
                    classify(key, content_hash, row)

            for members in groups.values():
                # Sorting by content hash is what makes the assignment below
                # independent of the order the rows arrived in.
                members.sort(key=lambda item: item[0])
                identity = self.identity_key(members[0][1])
                ties: dict[int, int] = {}
                for index, (content_hash, row) in enumerate(members):
                    if index == 0:
                        key = identity
                    else:
                        # Content hash, not position. An extra member inserted
                        # into the group only adds its own key; it does not
                        # renumber the others.
                        seen_before = ties.get(content_hash, 0)
                        ties[content_hash] = seen_before + 1
                        key = f"{identity}\x00#{content_hash:016x}"
                        if seen_before:
                            # Byte-identical rows repeated in the same group.
                            # They carry no content to tell them apart, so an
                            # ordinal is the only option -- and it is stable,
                            # because identical rows are interchangeable.
                            key = f"{key}:{seen_before}"
                    classify(key, content_hash, row)

        result.rows_removed = len(previous)
        result.removed_keys = [f"{k:016x}" for k in list(previous)[:1000]]
        self.log.info(
            "diff: in=%s new=%s changed=%s unchanged=%s removed=%s",
            f"{result.rows_in:,}",
            f"{result.rows_new:,}",
            f"{result.rows_changed:,}",
            f"{result.rows_unchanged:,}",
            f"{result.rows_removed:,}",
        )
        return result

    def _duplicate_identity_hashes(self, rows: Iterable[dict[str, Any]]) -> set[int]:
        """Identity-key hashes that appear more than once in ``rows``.

        A cheap first pass: it calls :meth:`identity_key` but not
        :meth:`content_tuple`, and keeps no rows. Knowing the repeated keys
        up front is what lets :meth:`diff` assign every member of a group a
        content-derived key, including the first one -- which is the member the
        old positional scheme got wrong.
        """
        seen: set[int] = set()
        duplicated: set[int] = set()
        for row in rows:
            base_hash = _hash64(self.identity_key(row))
            if base_hash in seen:
                duplicated.add(base_hash)
            else:
                seen.add(base_hash)
        return duplicated

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

    def require_allowed_url(self, url: str) -> str:
        """Return ``url`` if this connector may fetch it, else raise.

        ``cms_dac`` and ``cms_revalidation`` read their download URL out of a
        remote JSON document and pass it here; the URL is therefore attacker- or
        error-controlled input, not a constant. Two things are checked:

        * the scheme is ``https``. ``urlopen`` will happily serve ``file:///``
          and ``ftp://``, which would let a substituted catalog entry turn a
          local file into a checksummed, seven-year-retained evidence payload;
        * the host is in :attr:`allowed_hosts`. ``hostname`` is used rather than
          ``netloc`` so ``https://data.cms.gov@example.com/x`` resolves to
          ``example.com`` and is refused.

        A rejected URL fails the run. That is the intended outcome: a roster
        built from an unverified file is worse than a roster that is a month
        stale, and the failure is recorded in ``source_runs``.

        Args:
            url: Candidate URL.

        Returns:
            ``url`` unchanged.

        Raises:
            ConnectorError: On any scheme or host that is not allowed.
        """
        try:
            parsed = urllib.parse.urlsplit(url)
        except ValueError as exc:
            raise ConnectorError(f"{self.key}: unparsable URL {url!r}: {exc}") from exc
        if parsed.scheme != "https":
            raise ConnectorError(
                f"{self.key}: refusing to fetch {url!r}: scheme {parsed.scheme!r} is not https. "
                "Source URLs are read out of a remote catalog and must be transport-authenticated."
            )
        host = (parsed.hostname or "").lower()
        if host not in self.allowed_hosts:
            raise ConnectorError(
                f"{self.key}: refusing to fetch {url!r}: host {host!r} is not in the download "
                f"allowlist {sorted(self.allowed_hosts)}. If this is a legitimate new CMS or OIG "
                "host, add it to ALLOWED_DOWNLOAD_HOSTS in a reviewed change."
            )
        return url

    def download(self, url: str, destination: Path) -> Path:
        """Stream a URL to ``destination`` with bounded retries.

        Args:
            url: Absolute URL to fetch. Checked against
                :meth:`require_allowed_url` before anything is opened.
            destination: Local path to write.

        Returns:
            ``destination``.

        Raises:
            ConnectorError: If the URL is not allowed, or every attempt fails.
        """
        self.require_allowed_url(url)
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
            url: Absolute URL. Checked against :meth:`require_allowed_url` --
                the catalog documents are as much a trust boundary as the
                payloads they point at.

        Returns:
            The decoded JSON document.

        Raises:
            ConnectorError: If the URL is not allowed, or on a transport failure
                or unparsable body.
        """
        self.require_allowed_url(url)
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

        The registry wins where it already has a row. Both
        ``freshness_sla_days`` and ``is_primary_source`` are adopted for this
        run:

        * ``freshness_sla_days`` so that ``evidence.freshness_expires_at`` and
          ``sources.freshness_sla_days`` can never disagree. Section 8.1 reads
          the SLA through the registry, so a connector quietly using a different
          number would make assertions look fresh that the registry considers
          stale.
        * ``is_primary_source`` for the same reason, and it is the sharper of
          the two. It is the first gate in PRD 8.1 condition 1, the registry is
          where the decision is recorded (0009 seeds it, 0010 pairs it with
          ``attests_obligation_types``), and a class attribute left behind by a
          revision would have a connector reasoning about its own authority
          from a value the database disagrees with. Only the registry's answer
          is used at run time.

        A CONNECTOR NEVER ASSERTS ITS OWN AUTHORITY. The row this method may
        insert always carries ``is_primary_source = false``, whatever the class
        declares. Two reasons, and the second is not optional:

        * whether a source can clear an obligation is a decision recorded in a
          migration, reviewed, and paired with ``attests_obligation_types``. A
          connector declaring itself primary would be marking its own homework.
        * 0010 adds ``sources_primary_attests_chk``
          (``not is_primary_source or cardinality(attests_obligation_types) > 0``),
          and Postgres evaluates CHECK constraints against the tuple an
          ``insert ... on conflict`` proposes -- before it discovers the
          conflict, and with the column's ``'{}'`` default in place. An insert
          proposing ``is_primary_source = true`` therefore fails even when the
          stored row is perfectly fine, taking the whole run with it.

        The insert is only reached by a connector the registry has never seen.
        For a seeded source it is a no-op and the adoption below does the work.
        """
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into sources (
                    key, display_name, kind, cadence, freshness_sla_days,
                    is_primary_source, terms_url, enabled
                ) values (%s, %s, %s, %s, %s, false, %s, true)
                on conflict (key) do nothing
                returning key
                """,
                (
                    self.key,
                    self.display_name or self.key,
                    self.kind,
                    self.cadence,
                    self.freshness_sla_days,
                    self.terms_url,
                ),
            )
            # RETURNING rather than rowcount: `on conflict do nothing` reports
            # no rows when the row was already there, and a returned key is the
            # unambiguous signal that this connector is new to the registry.
            created = cur.fetchone() is not None
            cur.execute(
                "select freshness_sla_days, enabled, is_primary_source from sources where key = %s",
                (self.key,),
            )
            row = cur.fetchone()
        if row is None:  # pragma: no cover - the insert above guarantees a row
            return
        if created:
            self.log.warning(
                "sources had no row for %s, so one was inserted with "
                "is_primary_source=false and no attested obligation types. It can "
                "record runs and evidence but can never clear an obligation. Seed it "
                "properly in a migration alongside attests_obligation_types (see "
                "db/migrations/0009 and 0010) before relying on it.",
                self.key,
            )
        if row[0] and row[0] != self.freshness_sla_days:
            self.log.info(
                "adopting registry freshness_sla_days=%s for %s (class default %s)",
                row[0],
                self.key,
                type(self).freshness_sla_days,
            )
            self.freshness_sla_days = row[0]
        if row[2] is not None and row[2] != self.is_primary_source:
            self.log.info(
                "adopting registry is_primary_source=%s for %s (class default %s)",
                row[2],
                self.key,
                type(self).is_primary_source,
            )
            self.is_primary_source = bool(row[2])
        if row[1] is False:
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
        except Exception as exc:
            # Deliberately broad. The run log is the audit trail; losing it is
            # serious, but it must not mask the original failure that is already
            # on the RunResult, and it must never escape run()'s `finally` and
            # abort the whole batch. psycopg.Error is not enough: a missing
            # DATABASE_URL makes db.connect() raise ConfigError, a plain
            # RuntimeError, which used to take the entire ingest down and leave
            # every source without a source_runs row.
            self.log.error("could not write source_runs row for %s: %s", self.key, exc)

    # -------------------------------------------------------- storage guard

    #: Path fragments that mark a directory as living only for the duration of a
    #: CI job. GITHUB_WORKSPACE is checked separately, at run time.
    EPHEMERAL_STORAGE_MARKERS: ClassVar[tuple[str, ...]] = ("/home/runner/work",)

    def _check_storage_durability(self) -> None:
        """Refuse to write raw payloads into storage that dies with the job.

        ``evidence.payload_ref`` is a seven-year retention pointer and the diff
        state lives beside it. Under a CI runner's workspace both are destroyed
        minutes after the run: every payload_ref cites a path that no longer
        exists, and every run re-classifies the whole file as new because the
        previous state is gone. ``config.py`` and ``evidence.py`` already
        support an ``s3://`` STORAGE_PATH; that is the fix.

        Raises:
            ConnectorError: When raw payload storage is on and ``storage_path``
                is under a known-ephemeral root.
        """
        if not self.settings.store_raw_payloads or self.settings.storage_is_s3:
            return
        root = str(self.settings.local_storage_root)
        reason = next((m for m in self.EPHEMERAL_STORAGE_MARKERS if m in root), None)
        workspace = (os.environ.get("GITHUB_WORKSPACE") or "").strip()
        if reason is None and workspace:
            try:
                resolved = str(Path(workspace).expanduser().resolve())
            except OSError:  # pragma: no cover - unreadable workspace path
                resolved = workspace
            if root == resolved or root.startswith(resolved.rstrip("/") + "/"):
                reason = "$GITHUB_WORKSPACE"
        if reason is None:
            return
        raise ConnectorError(
            f"STORAGE_PATH {root} is inside an ephemeral CI workspace ({reason}). "
            "Raw evidence payloads are retained seven years and evidence.payload_ref "
            "would cite a path destroyed with the runner, while the diff state beside "
            "it would be lost and every run would report the whole file as new. Set "
            "STORAGE_PATH to an s3:// URI, or set STORE_RAW_PAYLOADS=false for a "
            "throwaway run."
        )

    # ------------------------------------------------------ plausibility floor

    def _previous_ok_rows_in(self) -> int | None:
        """``rows_in`` of the most recent successful run of this source.

        Returns:
            The row count, or None when this source has never completed a run
            (the first run of a new source, or a fresh database).

        Raises:
            ConnectorError: If the run log cannot be read. The check is not
                optional: skipping it because the database is unreachable is
                how a guard becomes decorative.
        """
        try:
            with transaction(None, self.settings) as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    select rows_in from source_runs
                    where source_key = %s and status = 'ok' and rows_in > 0
                    order by started_at desc
                    limit 1
                    """,
                    (self.key,),
                )
                row = cur.fetchone()
        except Exception as exc:
            raise ConnectorError(
                f"could not read the previous successful run for {self.key} to check the row "
                f"count against it: {exc}"
            ) from exc
        return int(row[0]) if row and row[0] is not None else None

    def _check_row_plausibility(self, rows_in: int) -> None:
        """Refuse a run whose input shrank implausibly since the last good one.

        A truncated download, a substituted file or a publisher error that ships
        a partial extract all present the same way: the parse succeeds, the diff
        succeeds, and the load quietly rewrites the roster from a fraction of
        the data. Nothing else in the pipeline notices -- the checksum matches
        the bytes that arrived, and ``status`` is ``ok``.

        So a run is refused when it reads less than
        :attr:`min_rows_fraction` of the rows the last successful run read. The
        first run of a source has nothing to compare against and is allowed.
        Growth is never refused: these files grow.

        Args:
            rows_in: Rows this run read, after per-connector deduplication.

        Raises:
            ConnectorError: When the count is below the floor.
        """
        previous = self._previous_ok_rows_in()
        if previous is None:
            self.log.info(
                "no previous successful run for %s; skipping the row-count floor", self.key
            )
            return
        floor = int(previous * self.min_rows_fraction)
        if rows_in >= floor:
            self.log.info(
                "row count %s is within the plausibility floor %s (%.0f%% of the last good run's %s)",
                f"{rows_in:,}",
                f"{floor:,}",
                self.min_rows_fraction * 100,
                f"{previous:,}",
            )
            return
        raise ConnectorError(
            f"{self.key}: this run read {rows_in:,} rows, below the floor of {floor:,} "
            f"({self.min_rows_fraction:.0%} of the {previous:,} rows the last successful run "
            "read). A truncated or substituted source file looks exactly like this, and loading "
            "it would rewrite the roster from a fraction of the data. Refusing the run; check "
            "the publisher, then re-run. Raise the connector's min_rows_fraction only if the "
            "source genuinely shrank."
        )

    # ------------------------------------------------------------------- run

    def _reiterable_rows(self, path: Path) -> Iterable[dict[str, Any]]:
        """A re-iterable view over ``parse(path)``.

        :meth:`diff` walks its input twice -- once for repeated identity keys,
        once to classify -- and neither the 839 MB DAC file nor the 540 MB
        revalidation file may be held in memory. Re-parsing the local file is
        the cheap half of the run; holding 3.39M dicts is not an option.
        """
        return _ReparsedRows(self, path)

    def run(self, dry_run: bool = False) -> RunResult:
        """Orchestrate fetch, checksum, diff and load, and log the run.

        Args:
            dry_run: Fetch, parse and diff, but do not call :meth:`load`, do not
                promote the diff state, and do not write a ``source_runs`` row.
                The diff summary is still written to storage so the run can be
                inspected. The result carries ``status='dry-run'``.

        Returns:
            A :class:`RunResult`. The method does not raise on connector
            failure: it records ``status='failed'`` with the error text and
            returns, so a batch run can continue to the next source. That
            includes a failure to write the ``source_runs`` row itself, which
            :meth:`_write_source_run` swallows rather than raising out of the
            ``finally`` below.
        """
        result = RunResult(source_key=self.key, run_id=self.run_id, started_at=datetime.now(UTC))
        diff: DiffResult | None = None
        loaded = False
        try:
            self.settings.validate()
            if not dry_run:
                # A dry run writes no evidence, so an ephemeral store cannot
                # produce a payload_ref that outlives the runner.
                self._check_storage_durability()
            path = self.fetch()
            self.fetched_path = path
            self.fetched_checksum = self.checksum(path)
            self.log.info("fetched %s sha256=%s", path.name, self.fetched_checksum)

            diff = self.diff(self._reiterable_rows(path))
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

            # After the diff summary is stored, so a refused run still leaves a
            # readable diff_ref saying what arrived, and before load(), so
            # nothing derived from a short file reaches the roster.
            self._check_row_plausibility(diff.rows_in)

            if dry_run:
                self.log.warning(
                    "dry run: skipping load() and the source_runs row for %s", self.key
                )
                result.status = "dry-run"
            else:
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
            if not dry_run:
                self._write_source_run(result)
            self._cleanup(diff)
        return result

    def _is_run_scratch(self, candidate: Path) -> bool:
        """True when ``candidate`` is a file this run created under ``work_dir``.

        Anything else -- above all a ``LOCAL_SOURCE_*`` override, which is a
        path the operator handed us and still owns -- is left alone.
        """
        if self.fetched_is_external and candidate == self.fetched_path:
            return False
        try:
            work_dir = self.settings.work_dir.expanduser().resolve()
            return candidate.expanduser().resolve().parent == work_dir
        except OSError:
            return False

    def _cleanup(self, diff: DiffResult | None) -> None:
        """Remove scratch files unless KEEP_DOWNLOADS asks to keep them.

        Only files this run created under ``work_dir`` are removed. A source
        file supplied through ``LOCAL_SOURCE_*`` is the operator's own copy and
        is never deleted.
        """
        if self.settings.keep_downloads:
            return
        for candidate in (
            diff.changes_path if diff else None,
            diff.state_path if diff else None,
            self.fetched_path,
        ):
            if candidate is None:
                continue
            path = Path(candidate)
            if not self._is_run_scratch(path):
                self.log.info("leaving %s in place; this run did not create it", path)
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                self.log.warning("could not remove %s: %s", candidate, exc)

    # -------------------------------------------------------------- utilities

    def open_connection(self) -> psycopg.Connection:
        """Open a connection using this connector's settings."""
        return connect(self.settings)
