"""Nursys e-Notify (NCSBN) -- RN/APRN licensure, the primary source for roughly
half the clinician base.

Nursys e-Notify is a subscription that reports license and discipline changes for
the nurses an institution enrolls. It is seeded as a primary source in the
registry (0009: key ``nursys``, attests ``license_renewal``, ``csr_renewal``,
``ce_cycle``), so a license row derived here can clear those obligations, which is
what makes it the highest value per hour of build effort in the backlog.

WHAT THIS CONNECTOR DOES, AND DELIBERATELY DOES NOT, DO
-----------------------------------------------------------------------------
It CONSUMES. It calls Notification Lookup for the changes to enrolled nurses and
derives ``licenses`` rows from them, evidence first. It never ENROLLS: enrollment
(Manage Nurse List) requires last-4 SSN, birth year and home address
(spec 3.2.1), which is PII this system must never handle (PRD 2). Under the
client-owned-account model the client uploads that enrollment file into the
Nursys web UI directly; this connector only holds API credentials to read back
NCSBN-ID-keyed license status, which carries no SSN and no DOB.

THE API SHAPE THAT DRIVES THE CODE
-----------------------------------------------------------------------------
* Auth is two request headers, ``username`` and ``password`` (spec 3.1.3), over
  TLS. The password rotates every 90 days; :func:`rotate_account_passwords`
  changes it proactively before Nursys expires it.
* Every method is asynchronous: a POST returns a ``TransactionId`` and a later
  GET with that id returns the result (spec 3.2, 3.4, 3.5). The recommended wait
  is five minutes.
* Rate limit is an average of 25 requests per minute; exceeding it returns HTTP
  403 and blocks the account for 30 minutes (spec 3.1.6). POST and GET each
  count, so the client throttles both.
* The API host is part of the credential Nursys hands out and is redacted in the
  spec (3.1.4), so it is validated at run time rather than hardcoded.

NPI does not appear anywhere in Nursys. The roster is joined to the feed on
NCSBN ID through ``nursys_enrollment`` (0013).
"""

from __future__ import annotations

import json
import logging
import secrets
import string
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar
from uuid import UUID

from ..config import Settings
from ..db import fetch_all, transaction
from ..evidence import insert_credential, json_payload, store_evidence
from ..secrets import NursysCredential, SecretStore
from .base import Connector, ConnectorError

__all__ = [
    "DISCIPLINE_TO_SANCTION_ENABLED",
    "NursysAccount",
    "NursysApiError",
    "NursysClient",
    "NursysConnector",
    "NursysRateLimited",
    "RateLimiter",
    "generate_password",
    "iter_nurse_licenses",
    "map_license_status",
    "rotate_account_passwords",
]

LOGGER = logging.getLogger(__name__)

#: Auth header keys (spec 3.1.3).
HEADER_USERNAME = "username"
HEADER_PASSWORD = "password"

#: Method paths, appended to the account's (secret) API base URL (spec 3.1.5).
PATH_NOTIFICATION = "notificationlookup"
PATH_NURSE = "nurselookup"
PATH_CHANGE_PASSWORD = "changepassword"

#: Rate limit (spec 3.1.6): 25 req/min average; over it, 403 + 30-minute block.
DEFAULT_MAX_RPM = 25
BLOCK_SECONDS = 30 * 60

#: Async submit/poll (spec 3.2): five-minute recommended wait, then GET the result.
POLL_INITIAL_SECONDS = 300
POLL_INTERVAL_SECONDS = 60
POLL_MAX_ATTEMPTS = 10

#: Maximum nurses per Nurse Lookup / Manage Nurse List batch (spec 3.2, 3.4).
NURSE_LOOKUP_BATCH = 2000

#: Nursys expires the API password every 90 days; rotate before then.
PASSWORD_MAX_AGE_DAYS = 90
ROTATE_BEFORE_DAYS = 80

#: A board discipline is adverse-action-adjacent. Writing it to ``sanctions`` is
#: HIGH_CONSEQUENCE (PRD 8.3) and, like LEIE name+DOB matching, is gated behind a
#: reviewed threshold rather than shipped on day one. License STATUS
#: (suspended/revoked/expired) still flows through as a licenses row and drives
#: lapse severity; only the separate disciplinary record is withheld here.
DISCIPLINE_TO_SANCTION_ENABLED = False

#: Nursys ``LicenseStatus`` keyword -> our ``licenses.status`` enum (0003). The
#: status text is free-form (up to 500 chars, appendix A.8) and often carries a
#: "(see history)" suffix, so it is matched by keyword, most-severe first.
_STATUS_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("REVOK", "revoked"),
    ("SUSPEN", "suspended"),
    ("PROBATION", "probation"),
    ("EXPIRED", "expired"),
    ("UNENCUMBERED", "active"),
)

#: ``Active`` field values that mean the license currently permits practice.
_ACTIVE_TRUTHY: frozenset[str] = frozenset({"active", "y", "yes", "true", "1"})


class NursysApiError(ConnectorError):
    """A Nursys API call failed in a way that should fail the run."""


class NursysRateLimited(NursysApiError):
    """The account is rate-limited (HTTP 403); backing off is required."""


# ===========================================================================
# Pure helpers -- no network, no database, unit-tested directly.
# ===========================================================================
def map_license_status(active: str | None, license_status: str | None) -> str:
    """Map a Nursys license to our ``licenses.status`` enum (0003).

    The disciplinary keyword in ``license_status`` wins when present, because a
    revoked or suspended license is the finding regardless of the ``Active``
    flag. Otherwise the ``Active`` flag decides active vs lapsed. An unknown,
    non-active status maps to ``lapsed`` rather than ``active`` so the engine
    never treats an ambiguous license as clean.

    Args:
        active: The ``Active`` field, e.g. ``"Active"`` / ``"Inactive"``.
        license_status: The ``LicenseStatus`` field, free text.

    Returns:
        One of active | expired | lapsed | suspended | revoked | probation.
    """
    text = (license_status or "").upper()
    for keyword, mapped in _STATUS_KEYWORDS:
        if keyword in text:
            return mapped
    return "active" if (active or "").strip().lower() in _ACTIVE_TRUTHY else "lapsed"


def _parse_date(value: Any) -> date | None:
    """Parse a Nursys date (ISO ``YYYY-MM-DD`` or full timestamp), else None."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _clean(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def iter_nurse_licenses(payload: Any) -> Iterator[dict[str, Any]]:
    """Yield one normalized license per license in a Nurse/Notification payload.

    Tolerant by design: Notification Lookup and Nurse Lookup wrap the same
    nurse/license objects in slightly different envelopes, and the exact nesting
    is versioned. This walks the payload for any object carrying an ``NcsbnId``
    and a ``NurseLookupLicenses`` collection and flattens each license, so a new
    wrapper level does not silently drop rows.

    Yields:
        Dicts with ncsbn_id, jurisdiction, license_type, license_number, status,
        issue_date, expiry_date, compact_status, has_discipline and the raw
        status text, ready for change detection and derivation.
    """
    for nurse in _find_nurses(payload):
        ncsbn_raw = _clean(nurse.get("NcsbnId"))
        if not ncsbn_raw.isdigit():
            continue
        ncsbn_id = int(ncsbn_raw)
        for lic in nurse.get("NurseLookupLicenses") or []:
            if not isinstance(lic, dict):
                continue
            disciplines = lic.get("NurseLookupDisciplines") or []
            yield {
                "ncsbn_id": ncsbn_id,
                "jurisdiction": _clean(lic.get("JurisdictionAbbreviation"))[:2].upper() or None,
                "license_type": _clean(lic.get("LicenseType")) or None,
                "license_number": _clean(lic.get("LicenseNumber")) or None,
                "active": _clean(lic.get("Active")) or None,
                "status_raw": _clean(lic.get("LicenseStatus")) or None,
                "status": map_license_status(lic.get("Active"), lic.get("LicenseStatus")),
                "issue_date": _parse_date(lic.get("LicenseOriginalDate")),
                "expiry_date": _parse_date(lic.get("LicenseExpirationDate")),
                "compact_status": _clean(lic.get("CompactStatus")) or None,
                "has_discipline": bool(disciplines),
            }


def _find_nurses(payload: Any) -> Iterator[dict[str, Any]]:
    """Walk a decoded JSON payload for nurse objects (dicts with an NcsbnId)."""
    if isinstance(payload, dict):
        if "NcsbnId" in payload and "NurseLookupLicenses" in payload:
            yield payload
        for value in payload.values():
            yield from _find_nurses(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _find_nurses(item)


def generate_password(length: int = 28) -> str:
    """Generate a strong API password within Nursys's 50-char limit.

    Guarantees at least one lower, upper, digit and symbol from a set the API
    accepts (its own sample password mixes all four), then fills the rest from
    the full alphabet using :mod:`secrets`.
    """
    length = max(16, min(length, 50))
    symbols = "!@#$%*+-_"
    pools = (string.ascii_lowercase, string.ascii_uppercase, string.digits, symbols)
    chars = [secrets.choice(pool) for pool in pools]
    alphabet = "".join(pools)
    chars += [secrets.choice(alphabet) for _ in range(length - len(chars))]
    # Shuffle so the guaranteed characters are not always in the first positions.
    for i in range(len(chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]
    return "".join(chars)


# ===========================================================================
# Rate limiting -- per account, injectable clock for tests.
# ===========================================================================
class RateLimiter:
    """A sliding-window limiter for the 25-req/min Nursys ceiling.

    Args:
        max_per_minute: Requests allowed per rolling 60 seconds.
        time_fn: Monotonic clock; injectable so tests need no real time.
        sleep_fn: Sleep function; injectable so tests do not block.
    """

    def __init__(
        self,
        max_per_minute: int = DEFAULT_MAX_RPM,
        *,
        time_fn: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.max_per_minute = max_per_minute
        self._time = time_fn
        self._sleep = sleep_fn
        self._calls: list[float] = []

    def acquire(self) -> None:
        """Block until a request may be sent without breaching the average."""
        now = self._time()
        window_start = now - 60.0
        self._calls = [t for t in self._calls if t > window_start]
        if len(self._calls) >= self.max_per_minute:
            wait = 60.0 - (now - self._calls[0])
            if wait > 0:
                self._sleep(wait)
            now = self._time()
            self._calls = [t for t in self._calls if t > now - 60.0]
        self._calls.append(now)


# ===========================================================================
# The HTTP client -- auth, async submit/poll, rotation.
# ===========================================================================
class NursysClient:
    """A thin client for one Nursys e-Notify account.

    Args:
        credential: The account's API URL, username and password.
        limiter: Rate limiter; a default 25-rpm one is created when omitted.
        opener: ``urlopen``-compatible callable; injectable for tests.
        sleep_fn: Sleep function used between async polls; injectable for tests.
        timeout: Per-request timeout in seconds.
    """

    def __init__(
        self,
        credential: NursysCredential,
        *,
        limiter: RateLimiter | None = None,
        opener: Callable[..., Any] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        timeout: int = 120,
    ) -> None:
        self.credential = credential
        self.base_url = self._validate_url(credential.api_url)
        self.limiter = limiter or RateLimiter()
        self._open = opener or urllib.request.urlopen
        self._sleep = sleep_fn
        self.timeout = timeout

    @staticmethod
    def _validate_url(url: str) -> str:
        """Require an ``https`` URL with a host and no embedded credentials.

        The URL comes from our own secret store, not a third-party catalog, so
        the SSRF surface is smaller than the CMS connectors' -- but ``https`` and
        a bare host are still enforced so a misconfigured account cannot send the
        username/password headers to ``http://`` or to ``user@host``.
        """
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https":
            raise NursysApiError(f"Nursys API URL must be https, got {parsed.scheme!r}")
        if not parsed.hostname or parsed.username or parsed.password:
            raise NursysApiError(f"Nursys API URL {url!r} must be a bare https host")
        return url.rstrip("/")

    def _request(self, method: str, path: str, body: dict[str, Any] | None) -> Any:
        """Send one request, returning the decoded JSON (or None on 204).

        Raises:
            NursysRateLimited: On HTTP 403.
            NursysApiError: On any other transport or decode failure.
        """
        self.limiter.acquire()
        url = f"{self.base_url}/{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {
            HEADER_USERNAME: self.credential.username,
            HEADER_PASSWORD: self.credential.password,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self._open(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                raise NursysRateLimited(
                    "Nursys returned HTTP 403 (rate limit); the account is blocked for "
                    f"{BLOCK_SECONDS // 60} minutes. Reduce request rate and retry later."
                ) from exc
            raise NursysApiError(f"Nursys {method} {path} failed: HTTP {exc.code}") from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise NursysApiError(f"Nursys {method} {path} failed: {exc}") from exc
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise NursysApiError(f"Nursys {method} {path} returned invalid JSON: {exc}") from exc

    def _submit_and_poll(self, path: str, body: dict[str, Any]) -> Any:
        """POST to get a ``TransactionId``, then GET the result once ready.

        Mirrors the spec's async pattern: submit, wait the recommended interval,
        then retrieve. Returns the GET payload.

        Raises:
            NursysApiError: When no transaction id comes back, or the result is
                not ready within the poll budget.
        """
        submitted = self._request("POST", path, body) or {}
        transaction_id = submitted.get("TransactionId")
        if not transaction_id:
            raise NursysApiError(f"Nursys {path} POST returned no TransactionId")
        self._sleep(POLL_INITIAL_SECONDS)
        query = urllib.parse.urlencode({"transactionId": transaction_id})
        for attempt in range(1, POLL_MAX_ATTEMPTS + 1):
            result = self._request("GET", f"{path}?{query}", None)
            if _result_ready(result):
                return result
            LOGGER.info("Nursys %s not ready (attempt %s); waiting", path, attempt)
            self._sleep(POLL_INTERVAL_SECONDS)
        raise NursysApiError(
            f"Nursys {path} result for {transaction_id} not ready after {POLL_MAX_ATTEMPTS} polls"
        )

    def notification_lookup(self, start: date, end: date) -> Any:
        """Return license/discipline changes in ``[start, end]`` for enrolled nurses.

        Both dates are required and must be on or before today, with start on or
        before end (spec 3.5.1). The connector passes the last watermark as start
        and the run date as end.
        """
        return self._submit_and_poll(
            PATH_NOTIFICATION,
            {"StartDate": start.isoformat(), "EndDate": end.isoformat()},
        )

    def nurse_lookup(self, requests: list[dict[str, Any]]) -> Any:
        """Return full current licence data for a batch of enrolled nurses.

        Used to establish a baseline on an account's first run, because
        Notification Lookup only returns changes within a date range and would
        miss the current status of a nurse who has not changed recently. Each
        request is a matching combination (spec 3.4.2); enrolment by NCSBN ID is
        the one this connector uses. Up to 2,000 per batch (spec 3.4).
        """
        return self._submit_and_poll(PATH_NURSE, {"NurseLookupRequests": requests})

    def change_password(self, new_password: str) -> None:
        """Change this account's API password (spec 3.3).

        The caller persists the new password to the secret store only after this
        returns, so a failed change never orphans the working password.
        """
        self._request("POST", PATH_CHANGE_PASSWORD, {"NewPassword": new_password})


def _result_ready(result: Any) -> bool:
    """True when an async GET carries data rather than a not-ready flag.

    The spec returns a processing flag plus collections; a payload with any
    nurse object, or an explicit ready/complete flag, counts as ready. A bare
    ``None`` or an empty dict is treated as not-ready so the poll continues.
    """
    if not result:
        return False
    if isinstance(result, dict):
        flag = str(result.get("RequestStatus") or result.get("Status") or "").lower()
        if flag in {"pending", "processing", "inprogress", "in_progress"}:
            return False
    return any(True for _ in _find_nurses(result)) or _has_explicit_ready(result)


def _has_explicit_ready(result: Any) -> bool:
    """True when a payload flags completion even though it lists no nurses."""
    if isinstance(result, dict):
        flag = str(result.get("RequestStatus") or result.get("Status") or "").lower()
        return flag in {"complete", "completed", "success", "ready", "ok"}
    return False


# ===========================================================================
# Accounts
# ===========================================================================
class NursysAccount:
    """One row of ``nursys_account`` plus its resolved credential.

    Attributes:
        id: ``nursys_account.id``.
        label: Human label.
        auth_ref: Secret manager key.
        password_set_at: Rotation clock.
        last_notification_at: Watermark for Notification Lookup.
    """

    __slots__ = ("auth_ref", "id", "label", "last_notification_at", "password_set_at")

    def __init__(
        self,
        id: UUID,
        label: str,
        auth_ref: str,
        password_set_at: datetime | None,
        last_notification_at: datetime | None,
    ) -> None:
        self.id = id
        self.label = label
        self.auth_ref = auth_ref
        self.password_set_at = password_set_at
        self.last_notification_at = last_notification_at


_QUERY_ENABLED_ACCOUNTS = """
select id, label, auth_ref, password_set_at, last_notification_at
from nursys_account
where enabled and deleted_at is null
order by created_at
"""

_QUERY_ENROLLED = """
select account_id, ncsbn_id
from nursys_enrollment
where deleted_at is null and account_id is not null
order by account_id
"""


def _load_accounts(settings: Settings) -> list[NursysAccount]:
    """Read every enabled Nursys account."""
    with transaction(None, settings) as conn:
        return [
            NursysAccount(r[0], r[1], r[2], r[3], r[4])
            for r in fetch_all(conn, _QUERY_ENABLED_ACCOUNTS)
        ]


def _enrolled_by_account(settings: Settings) -> dict[str, list[int]]:
    """Map each account id to the NCSBN ids enrolled under it."""
    out: dict[str, list[int]] = {}
    with transaction(None, settings) as conn:
        for account_id, ncsbn_id in fetch_all(conn, _QUERY_ENROLLED):
            out.setdefault(str(account_id), []).append(int(ncsbn_id))
    return out


# ===========================================================================
# The connector
# ===========================================================================
class NursysConnector(Connector):
    """Consume Nursys e-Notify notifications and derive ``licenses`` rows."""

    key: ClassVar[str] = "nursys"
    display_name: ClassVar[str] = "Nursys e-Notify (NCSBN)"
    kind: ClassVar[str] = "push"
    cadence: ClassVar[str] = "push"
    # Adopted from the registry at run time (0009 seeds 90 and is_primary_source
    # true); these are only the values used against an unseeded database.
    freshness_sla_days: int = 90
    is_primary_source: bool = True
    terms_url: ClassVar[str | None] = "https://www.nursys.com/"
    # A notification feed legitimately reports zero changes; the shrink guard
    # that protects bulk files would misfire on it.
    min_rows_fraction: ClassVar[float] = 0.0

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__(settings)
        self._store = SecretStore()
        self._sleep = time.sleep
        self._opener: Callable[..., Any] | None = None
        # account id -> newest notification timestamp seen this run, for the
        # watermark write in load().
        self._new_watermarks: dict[str, datetime] = {}

    # ----------------------------------------------------------------- fetch
    def fetch(self) -> Path:
        """Pull notifications for every enabled account into one NDJSON file.

        Each line is ``{"account_id", "license": {...}}`` so load() can resolve
        the clinician per account without a second pass.
        """
        accounts = _load_accounts(self.settings)
        enrolled = _enrolled_by_account(self.settings)
        self.request_ref = f"nursys://notificationlookup ({len(accounts)} accounts)"
        out_path = self.work_file("notifications.ndjson")
        total = 0
        with out_path.open("w", encoding="utf-8") as handle:
            for account in accounts:
                total += self._fetch_account(account, enrolled.get(str(account.id), []), handle)
        self.log.info("nursys: %s license notifications across %s accounts", total, len(accounts))
        return out_path

    def _fetch_account(self, account: NursysAccount, ncsbn_ids: list[int], handle: Any) -> int:
        """Fetch one account's licences, writing NDJSON rows. Returns the count.

        First run for an account (no watermark): a Nurse Lookup baseline over
        every enrolled nurse, because Notification Lookup returns only changes
        within a date range and would miss the current status of a nurse who has
        not changed recently. Thereafter: Notification Lookup for the window
        between the last watermark and the run date.
        """
        credential = self._store.get_nursys(account.auth_ref)
        client = NursysClient(credential, opener=self._opener, sleep_fn=self._sleep)
        if account.last_notification_at is None:
            payloads = self._baseline_payloads(client, ncsbn_ids)
        else:
            payloads = [
                client.notification_lookup(
                    account.last_notification_at.date(), self.fetched_at.date()
                )
            ]
        count = 0
        for payload in payloads:
            for lic in iter_nurse_licenses(payload):
                handle.write(
                    json.dumps({"account_id": str(account.id), "license": lic}, default=str) + "\n"
                )
                count += 1
        # Watermark advances to the run date: the next run's Notification Lookup
        # starts where this one's window ended.
        self._new_watermarks[str(account.id)] = self.fetched_at
        return count

    def _baseline_payloads(self, client: NursysClient, ncsbn_ids: list[int]) -> list[Any]:
        """Nurse Lookup every enrolled nurse, batched to the API's 2,000 limit."""
        payloads: list[Any] = []
        for start in range(0, len(ncsbn_ids), NURSE_LOOKUP_BATCH):
            batch = [{"NcsbnId": n} for n in ncsbn_ids[start : start + NURSE_LOOKUP_BATCH]]
            if batch:
                payloads.append(client.nurse_lookup(batch))
        return payloads

    # ----------------------------------------------------------------- parse
    def parse(self, path: Path) -> Iterator[dict[str, Any]]:
        """Stream the NDJSON rows written by :meth:`fetch`."""
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    record = json.loads(line)
                    lic = record["license"]
                    lic["account_id"] = record["account_id"]
                    yield lic

    def identity_key(self, row: dict[str, Any]) -> str:
        """Stable identity of a license across runs: account, NCSBN id, license."""
        return "|".join(
            (
                row.get("account_id") or "",
                str(row.get("ncsbn_id") or ""),
                row.get("jurisdiction") or "",
                row.get("license_type") or "",
                row.get("license_number") or "",
            )
        )

    def content_tuple(self, row: dict[str, Any]) -> Sequence[Any]:
        """Fields whose change makes a license row 'changed'."""
        return (
            row.get("status"),
            str(row.get("expiry_date") or ""),
            str(row.get("issue_date") or ""),
            row.get("compact_status"),
            row.get("has_discipline"),
        )

    # ------------------------------------------------------------------ load
    def load(self, diff: Any) -> None:
        """Derive ``licenses`` rows for changed notifications, evidence first."""
        derived = 0
        skipped = 0
        with transaction(None, self.settings) as conn:
            self.ensure_registered(conn)
            enrollment_map = self._enrollment_map(conn)
            for row in diff.iter_rows():
                clinician_id = enrollment_map.get((row["account_id"], row["ncsbn_id"]))
                if clinician_id is None:
                    skipped += 1
                    continue
                self._derive_license(conn, clinician_id, row)
                derived += 1
            self._write_watermarks(conn)
        self.log.info("nursys: derived %s licenses, skipped %s unenrolled", derived, skipped)
        if skipped and not DISCIPLINE_TO_SANCTION_ENABLED:
            self.log.info(
                "nursys: board disciplines are recorded on the license evidence but not "
                "written to sanctions (DISCIPLINE_TO_SANCTION_ENABLED is off; HIGH_CONSEQUENCE, "
                "needs a reviewed threshold before it ships)"
            )

    def _enrollment_map(self, conn: Any) -> dict[tuple[str, int], UUID]:
        """Map ``(account_id, ncsbn_id)`` to a clinician id."""
        rows = fetch_all(
            conn,
            "select account_id, ncsbn_id, clinician_id from nursys_enrollment "
            "where deleted_at is null and clinician_id is not null",
        )
        return {(str(r[0]), int(r[1])): r[2] for r in rows}

    def _derive_license(self, conn: Any, clinician_id: UUID, row: dict[str, Any]) -> None:
        """Write evidence, then upsert the licenses row it supports.

        The evidence is per license notification, so the audit trail shows the
        exact Nursys payload behind each license assertion (PRD 5.2).
        """
        if row.get("jurisdiction") is None or row.get("license_type") is None:
            return
        evidence_id = store_evidence(
            self.key,
            self.request_ref,
            json_payload(row),
            parsed=row,
            match_keys={
                "ncsbn_id": row["ncsbn_id"],
                "method": "nursys_ncsbn",
                "has_discipline": row.get("has_discipline", False),
            },
            freshness_days=self.freshness_sla_days,
            conn=conn,
            fetched_at=self.fetched_at,
            settings=self.settings,
            suffix=".json",
        )
        self._upsert_license(conn, clinician_id, row, evidence_id)

    def _upsert_license(
        self, conn: Any, clinician_id: UUID, row: dict[str, Any], evidence_id: UUID
    ) -> None:
        """Insert a licenses row, or refresh status/dates on the existing one."""
        with conn.cursor() as cur:
            cur.execute(
                """
                select id from licenses
                where clinician_id = %(clinician_id)s and state = %(state)s
                  and license_type = %(license_type)s
                  and license_number is not distinct from %(license_number)s
                  and deleted_at is null
                limit 1
                """,
                {
                    "clinician_id": clinician_id,
                    "state": row["jurisdiction"],
                    "license_type": row["license_type"],
                    "license_number": row.get("license_number"),
                },
            )
            existing = cur.fetchone()
            if existing is None:
                insert_credential(
                    conn,
                    "licenses",
                    {
                        "clinician_id": clinician_id,
                        "state": row["jurisdiction"],
                        "license_type": row["license_type"],
                        "license_number": row.get("license_number"),
                        "status": row["status"],
                        "issue_date": row.get("issue_date"),
                        "expiry_date": row.get("expiry_date"),
                    },
                    evidence_id,
                )
                return
            cur.execute(
                """
                update licenses set status = %(status)s, issue_date = %(issue_date)s,
                    expiry_date = %(expiry_date)s, evidence_id = %(evidence_id)s,
                    verified_at = %(verified_at)s
                where id = %(id)s
                """,
                {
                    "id": existing[0],
                    "status": row["status"],
                    "issue_date": row.get("issue_date"),
                    "expiry_date": row.get("expiry_date"),
                    "evidence_id": evidence_id,
                    "verified_at": self.fetched_at,
                },
            )

    def _write_watermarks(self, conn: Any) -> None:
        """Advance each account's Notification Lookup watermark."""
        with conn.cursor() as cur:
            for account_id, watermark in self._new_watermarks.items():
                cur.execute(
                    "update nursys_account set last_notification_at = %(w)s where id = %(id)s",
                    {"w": watermark, "id": account_id},
                )


# ===========================================================================
# Password rotation -- a separate job, run weekly, never inside ingest.
# ===========================================================================
def rotate_account_passwords(
    settings: Settings,
    *,
    as_of: datetime | None = None,
    rotate_before_days: int = ROTATE_BEFORE_DAYS,
    store: SecretStore | None = None,
    opener: Callable[..., Any] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    """Proactively change the API password of every account nearing expiry.

    Nursys expires the password at 90 days; this rotates at ``rotate_before_days``
    (80 by default) so a run never races the expiry. Rotation is proactive only:
    a 401 mid-ingest is NOT auto-rotated, because a single institution credential
    that rotates and then fails to persist locks the account out into a 30-day
    temporary-password recovery. The new password is persisted only after Nursys
    accepts it, and ``password_set_at`` is advanced in the same transaction.

    Returns:
        One record per account acted on: its id, label and outcome.
    """
    as_of = as_of or datetime.now(UTC)
    store = store or SecretStore()
    threshold = as_of - timedelta(days=rotate_before_days)
    results: list[dict[str, Any]] = []

    for account in _load_accounts(settings):
        set_at = account.password_set_at
        if set_at is not None and set_at > threshold:
            continue
        outcome = _rotate_one(settings, account, store, opener, sleep_fn, as_of)
        results.append({"account_id": str(account.id), "label": account.label, **outcome})
    return results


def _rotate_one(
    settings: Settings,
    account: NursysAccount,
    store: SecretStore,
    opener: Callable[..., Any] | None,
    sleep_fn: Callable[[float], None],
    as_of: datetime,
) -> dict[str, Any]:
    """Rotate one account's password; never raises, so one failure is not fatal."""
    try:
        credential = store.get_nursys(account.auth_ref)
        client = NursysClient(credential, opener=opener, sleep_fn=sleep_fn)
        new_password = generate_password()
        client.change_password(new_password)
        store.put_nursys(account.auth_ref, credential.rotated(new_password, at=as_of))
        with transaction(None, settings) as conn, conn.cursor() as cur:
            cur.execute(
                "update nursys_account set password_set_at = %(w)s where id = %(id)s",
                {"w": as_of, "id": account.id},
            )
        LOGGER.info("nursys: rotated password for account %s", account.label)
        return {"status": "rotated"}
    except Exception as exc:  # deliberately broad: one account must not stop the rest
        LOGGER.error("nursys: could not rotate account %s: %s", account.label, exc)
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
