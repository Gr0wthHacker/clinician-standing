"""Runtime configuration for the clinician-standing ingest layer.

Every setting comes from the process environment. There is no config file,
because several of these values are secrets (``DATABASE_URL`` carries a
password) and the deployment target is a scheduled job, not a workstation.

Read once via :func:`get_settings`; call :meth:`Settings.validate` before doing
any work so a misconfigured job fails at startup instead of halfway through a
839 MB download.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final
from urllib.parse import urlparse

__all__ = ["ConfigError", "Settings", "get_settings", "reset_settings_cache"]

#: Default freshness buffer applied when a connector does not declare one.
DEFAULT_FRESHNESS_SLA_DAYS: Final[int] = 45

#: Tables the ingest layer requires. ``init-check`` verifies all of them.
REQUIRED_TABLES: Final[tuple[str, ...]] = (
    "sources",
    "source_runs",
    "evidence",
    "practices",
    "clinicians",
    "affiliations",
    "enrollments",
    "sanctions",
)


class ConfigError(RuntimeError):
    """Raised when the environment cannot support a run."""


def _env_str(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def _env_int(name: str, default: int) -> int:
    raw = _env_str(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = _env_str(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Resolved environment settings.

    Attributes:
        database_url: libpq connection URI for the Supabase Postgres instance.
        storage_path: Local directory or ``s3://bucket/prefix`` for raw evidence
            payloads and diff summaries. Raw payloads are retained seven years,
            so in production this is object storage.
        work_dir: Scratch directory for downloads and spilled diff files.
        http_timeout_seconds: Per-request timeout for source downloads.
        http_retries: Retry attempts for a failed download.
        user_agent: Sent on every outbound request. Section 6.4 of the PRD
            requires identifying the client honestly.
        copy_batch_size: Rows buffered per ``COPY`` flush.
        store_raw_payloads: When false, evidence rows are written but the raw
            bytes are not persisted. Only for local development.
        keep_downloads: Leave downloaded source files on disk after a run.
        use_cache: Reuse an already-downloaded bulk file instead of fetching it
            again. Saves 1.4 GB of transfer when re-running a parse.
        default_sources: Connector keys ``ingest`` runs when given no argument.
        log_level: Root log level for the CLI.
    """

    database_url: str | None = None
    storage_path: str = "./storage"
    work_dir: Path = field(
        default_factory=lambda: Path(tempfile.gettempdir()) / "clinician-standing"
    )
    http_timeout_seconds: int = 600
    http_retries: int = 3
    user_agent: str = "clinician-standing-ingest/0.1 (+https://clinicianstanding.com)"
    copy_batch_size: int = 50_000
    store_raw_payloads: bool = True
    keep_downloads: bool = False
    use_cache: bool = False
    default_sources: tuple[str, ...] = ()
    log_level: str = "INFO"

    # ---------------------------------------------------------------- loading

    @classmethod
    def from_env(cls) -> Settings:
        """Build settings from environment variables."""
        storage_path = _env_str("STORAGE_PATH", "./storage") or "./storage"

        # Downloads land next to the evidence store when that is a local
        # directory, because .env.example sizes STORAGE_PATH for them (the DAC
        # and revalidation files are 1.4 GB together). With s3:// storage there
        # is no local directory to use, so fall back to the system temp dir.
        work_dir_raw = _env_str("WORK_DIR")
        if work_dir_raw:
            work_dir = Path(work_dir_raw).expanduser()
        elif storage_path.startswith("s3://"):
            work_dir = Path(tempfile.gettempdir()) / "clinician-standing"
        else:
            work_dir = Path(storage_path).expanduser().resolve() / "work"

        sources_raw = _env_str("INGEST_SOURCES", "") or ""
        default_sources = tuple(s.strip() for s in sources_raw.split(",") if s.strip())

        return cls(
            database_url=_env_str("DATABASE_URL"),
            storage_path=storage_path,
            work_dir=work_dir,
            http_timeout_seconds=_env_int("HTTP_TIMEOUT_SECONDS", 600),
            http_retries=_env_int("HTTP_RETRIES", 3),
            # HTTP_USER_AGENT is the documented name in .env.example;
            # INGEST_USER_AGENT is accepted as an alias.
            user_agent=(
                _env_str("HTTP_USER_AGENT") or _env_str("INGEST_USER_AGENT") or cls.user_agent
            ),
            copy_batch_size=_env_int("COPY_BATCH_SIZE", 50_000),
            store_raw_payloads=_env_bool("STORE_RAW_PAYLOADS", True),
            keep_downloads=_env_bool("KEEP_DOWNLOADS", False),
            use_cache=_env_bool("INGEST_USE_CACHE", False),
            default_sources=default_sources,
            log_level=_env_str("LOG_LEVEL", "INFO") or "INFO",
        )

    # ------------------------------------------------------------- validation

    def validate(self) -> None:
        """Fail loudly on an environment that cannot support a run.

        Raises:
            ConfigError: If ``DATABASE_URL`` is missing or unusable, or if the
                storage target is neither a writable local directory nor an
                ``s3://`` URI.
        """
        if not self.database_url:
            raise ConfigError(
                "DATABASE_URL is not set. Export a Postgres connection URI, e.g. "
                "postgresql://user:password@host:5432/postgres"
            )
        scheme = urlparse(self.database_url).scheme
        if scheme not in {"postgres", "postgresql"}:
            raise ConfigError(f"DATABASE_URL must be a postgresql:// URI, got scheme {scheme!r}")
        if not self.storage_path:
            raise ConfigError("STORAGE_PATH is empty; set a local directory or an s3:// URI")
        if self.storage_is_s3:
            if not self.s3_bucket:
                raise ConfigError(f"STORAGE_PATH {self.storage_path!r} has no bucket")
        else:
            root = self.local_storage_root
            try:
                root.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise ConfigError(f"STORAGE_PATH {root} is not creatable: {exc}") from exc
            if not os.access(root, os.W_OK):
                raise ConfigError(f"STORAGE_PATH {root} is not writable")
        if self.copy_batch_size < 1:
            raise ConfigError("COPY_BATCH_SIZE must be >= 1")

    # ---------------------------------------------------------------- storage

    @property
    def storage_is_s3(self) -> bool:
        """True when raw payloads go to S3 rather than a local directory."""
        return self.storage_path.startswith("s3://")

    @property
    def s3_bucket(self) -> str:
        """Bucket name parsed out of an ``s3://`` STORAGE_PATH."""
        if not self.storage_is_s3:
            return ""
        return urlparse(self.storage_path).netloc

    @property
    def s3_prefix(self) -> str:
        """Key prefix parsed out of an ``s3://`` STORAGE_PATH (no leading slash)."""
        if not self.storage_is_s3:
            return ""
        return urlparse(self.storage_path).path.lstrip("/").rstrip("/")

    @property
    def local_storage_root(self) -> Path:
        """Local storage directory. Meaningless when :attr:`storage_is_s3`."""
        return Path(self.storage_path).expanduser().resolve()

    def ensure_work_dir(self) -> Path:
        """Create and return the scratch directory used for downloads."""
        self.work_dir.mkdir(parents=True, exist_ok=True)
        return self.work_dir

    # ---------------------------------------------------------- dev overrides

    def local_source_override(self, source_key: str) -> Path | None:
        """Return a pre-downloaded file to use instead of fetching.

        Set ``LOCAL_SOURCE_CMS_DAC=/path/to/dac.csv`` to run the pipeline against
        an already-downloaded copy. Intended for development and CI fixtures; a
        scheduled run never sets it.
        """
        raw = _env_str(f"LOCAL_SOURCE_{source_key.upper()}")
        if not raw:
            return None
        path = Path(raw).expanduser()
        if not path.is_file():
            raise ConfigError(
                f"LOCAL_SOURCE_{source_key.upper()} points at {path}, which is not a file"
            )
        return path


_CACHED: Settings | None = None


def get_settings(refresh: bool = False) -> Settings:
    """Return process-wide settings, reading the environment on first call.

    Args:
        refresh: Re-read the environment instead of using the cached value.
    """
    global _CACHED
    if _CACHED is None or refresh:
        _CACHED = Settings.from_env()
    return _CACHED


def reset_settings_cache() -> None:
    """Drop the cached settings. Used by tests."""
    global _CACHED
    _CACHED = None
