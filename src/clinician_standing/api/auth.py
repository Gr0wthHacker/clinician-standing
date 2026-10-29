"""API-key authentication and a per-key rate limit, both driven by env vars.

``API_KEYS`` holds a comma-separated list of keys. Only their sha256 digests are
kept in memory after startup, and an incoming key is compared against every
digest in constant time. With no keys configured every authenticated endpoint
answers 503 rather than opening up.

The rate limit is a fixed one-minute window per key, held in process memory.
It protects the database from a runaway client; it is not metering. Behind more
than one worker or instance each process counts separately.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

__all__ = [
    "MIN_KEY_LENGTH",
    "ApiSettings",
    "KeyRing",
    "RateLimiter",
]

#: Shorter keys are ignored at startup. 32 random URL-safe characters is the
#: suggested form: ``python -c "import secrets; print(secrets.token_urlsafe(32))"``.
MIN_KEY_LENGTH = 24


def _digest(key: str) -> bytes:
    return hashlib.sha256(key.encode("utf-8")).digest()


class KeyRing:
    """The set of accepted API keys, held as digests."""

    def __init__(self, keys: Iterable[str]) -> None:
        cleaned = [k.strip() for k in keys]
        self.ignored_short = sum(1 for k in cleaned if 0 < len(k) < MIN_KEY_LENGTH)
        self._digests = tuple(_digest(k) for k in cleaned if len(k) >= MIN_KEY_LENGTH)

    @property
    def configured(self) -> bool:
        return bool(self._digests)

    def identify(self, presented: str) -> str | None:
        """Return a short stable id for an accepted key, or None.

        Every digest is compared, match or not, so timing does not reveal which
        position in the list matched.
        """
        candidate = _digest(presented)
        found: bytes | None = None
        for digest in self._digests:
            if hmac.compare_digest(candidate, digest):
                found = digest
        return found.hex()[:12] if found is not None else None


@dataclass
class RateLimiter:
    """Fixed-window counter: ``limit`` requests per key per ``window`` seconds."""

    limit: int
    window: float = 60.0
    clock: Callable[[], float] = time.monotonic
    _counts: dict[str, tuple[float, int]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def hit(self, key_id: str) -> float | None:
        """Count one request. Returns seconds to wait when over the limit, else None."""
        if self.limit <= 0:
            return None
        now = self.clock()
        with self._lock:
            start, count = self._counts.get(key_id, (now, 0))
            if now - start >= self.window:
                start, count = now, 0
            if count >= self.limit:
                return max(self.window - (now - start), 0.0)
            self._counts[key_id] = (start, count + 1)
            return None


@dataclass(frozen=True)
class ApiSettings:
    """Environment for the API process.

    Attributes:
        database_url: ``API_DATABASE_URL``. Kept separate from the ingest's
            ``DATABASE_URL`` so the API can run as a role with read access only.
        api_keys: ``API_KEYS``, comma-separated.
        rate_limit_per_minute: ``API_RATE_LIMIT_PER_MINUTE``. 0 disables it.
        roster_database_url: ``API_ROSTER_DATABASE_URL``, the ``app_roster_api``
            role (``0019_roster_intake.sql``). The only write credential the API
            holds. Unset, ``POST /v1/roster`` answers 503.
    """

    database_url: str | None
    api_keys: tuple[str, ...]
    rate_limit_per_minute: int = 60
    roster_database_url: str | None = None

    @classmethod
    def from_env(cls) -> ApiSettings:
        raw_keys = os.environ.get("API_KEYS", "")
        raw_limit = os.environ.get("API_RATE_LIMIT_PER_MINUTE", "").strip()
        try:
            limit = int(raw_limit) if raw_limit else 60
        except ValueError as exc:
            raise ValueError(
                f"API_RATE_LIMIT_PER_MINUTE must be an integer, got {raw_limit!r}"
            ) from exc
        url = os.environ.get("API_DATABASE_URL", "").strip() or None
        roster_url = os.environ.get("API_ROSTER_DATABASE_URL", "").strip() or None
        return cls(
            database_url=url,
            api_keys=tuple(k for k in raw_keys.split(",") if k.strip()),
            rate_limit_per_minute=limit,
            roster_database_url=roster_url,
        )
