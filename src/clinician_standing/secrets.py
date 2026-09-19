"""Secret resolution for source credentials.

``sources.auth_ref`` and ``nursys_account.auth_ref`` are KEYS into a secret
manager, never credentials in the clear (0006, 0013). This module turns such a
key into the credential the connector needs, and -- for Nursys, whose API
password rotates every 90 days -- persists a rotated one back.

The store is deliberately a seam, not a dependency on any one secret manager.
Two backends resolve a key today:

* a local directory named by ``NURSYS_SECRETS_PATH`` (default ``./secrets``),
  which is where a rotated password is written so the next run reads it;
* an environment variable, read-only, for the initial bootstrap credential
  before the first rotation has written a file.

The read order is file first, environment second, so a rotated file always wins
over the bootstrap value the environment still carries. Plaintext credentials in
a local directory is a development posture; in production ``NURSYS_SECRETS_PATH``
points at a mounted secret volume or is replaced by a real secret manager behind
the same :class:`SecretStore` interface. Credentials never go into the evidence
store (seven-year retention) and never into a migration or a Lovable file
(PRD 12).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

__all__ = [
    "NursysCredential",
    "SecretError",
    "SecretStore",
    "env_var_for",
]

LOGGER = logging.getLogger(__name__)

#: Environment-variable prefix for a bootstrap credential (before first rotation).
_ENV_PREFIX = "NURSYS_SECRET_"

_UNSAFE = re.compile(r"[^a-z0-9]+")


class SecretError(RuntimeError):
    """Raised when a secret cannot be resolved or persisted."""


def _slug(auth_ref: str) -> str:
    """Normalize an auth_ref to a filesystem- and env-safe token."""
    return _UNSAFE.sub("_", auth_ref.strip().lower()).strip("_")


def env_var_for(auth_ref: str) -> str:
    """Return the environment-variable name that bootstraps ``auth_ref``.

    ``nursys/enotify_api_credentials`` -> ``NURSYS_SECRET_NURSYS_ENOTIFY_API_CREDENTIALS``.
    The variable holds the same JSON a stored credential file holds.
    """
    return f"{_ENV_PREFIX}{_slug(auth_ref).upper()}"


@dataclass(frozen=True)
class NursysCredential:
    """A Nursys e-Notify Institution account's API credential.

    Attributes:
        api_url: The account's API base URL. Nursys redacts part of it and hands
            it out with the credentials (spec 3.1.4), so it is a secret, kept
            here rather than hardcoded. Must be an ``https`` URL.
        username: The ``username`` request header value (spec 3.1.3).
        password: The ``password`` request header value. Rotates every 90 days.
        password_set_at: When ``password`` was last set, for the rotation clock.
    """

    api_url: str
    username: str
    password: str
    password_set_at: datetime | None = None

    def to_json(self) -> str:
        """Serialize for storage. The password is written; guard the store."""
        return json.dumps(
            {
                "api_url": self.api_url,
                "username": self.username,
                "password": self.password,
                "password_set_at": (
                    self.password_set_at.isoformat() if self.password_set_at else None
                ),
            },
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, raw: str) -> NursysCredential:
        """Parse a stored credential, raising :class:`SecretError` on bad shape."""
        try:
            data = json.loads(raw)
            set_at = data.get("password_set_at")
            return cls(
                api_url=str(data["api_url"]),
                username=str(data["username"]),
                password=str(data["password"]),
                password_set_at=datetime.fromisoformat(set_at) if set_at else None,
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise SecretError(f"credential is not valid: {exc}") from exc

    def rotated(self, new_password: str, *, at: datetime | None = None) -> NursysCredential:
        """Return a copy carrying a new password and a fresh ``password_set_at``."""
        return replace(self, password=new_password, password_set_at=at or datetime.now(UTC))


class SecretStore:
    """Resolve and persist credentials named by an ``auth_ref``.

    Args:
        root: Directory rotated credentials are written to and read from. Read
            from ``NURSYS_SECRETS_PATH`` when omitted, defaulting to ``./secrets``.
    """

    def __init__(self, root: str | Path | None = None) -> None:
        if root is not None:
            raw = str(root)
        else:
            raw = os.environ.get("NURSYS_SECRETS_PATH") or "./secrets"
        self.root = Path(raw).expanduser()

    def _file(self, auth_ref: str) -> Path:
        return self.root / f"{_slug(auth_ref)}.json"

    def get_nursys(self, auth_ref: str) -> NursysCredential:
        """Return the credential for ``auth_ref``.

        File first, environment second, so a rotated file wins over the
        bootstrap value.

        Raises:
            SecretError: When neither a file nor an environment variable holds it.
        """
        path = self._file(auth_ref)
        if path.is_file():
            return NursysCredential.from_json(path.read_text(encoding="utf-8"))
        env = os.environ.get(env_var_for(auth_ref))
        if env:
            return NursysCredential.from_json(env)
        raise SecretError(
            f"no credential for auth_ref {auth_ref!r}: expected {path} or "
            f"${env_var_for(auth_ref)}. Set the bootstrap credential out of band; "
            "the rotation job writes the file thereafter."
        )

    def put_nursys(self, auth_ref: str, credential: NursysCredential) -> None:
        """Persist ``credential`` for ``auth_ref`` atomically.

        Called by the rotation job after Nursys accepts a new password. Writes to
        the file backend so the next run reads the rotated value; the bootstrap
        environment variable, if any, is left untouched and simply loses to the
        file from now on.

        Raises:
            SecretError: When the directory cannot be created or written.
        """
        path = self._file(auth_ref)
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".json.partial")
            tmp.write_text(credential.to_json(), encoding="utf-8")
            os.replace(tmp, path)
            # 0600 where the platform honours it; a best effort, not a guarantee.
            with contextlib.suppress(OSError):  # pragma: no cover - platform dependent
                os.chmod(path, 0o600)
        except OSError as exc:
            raise SecretError(
                f"could not persist credential for {auth_ref!r} at {path}: {exc}"
            ) from exc
