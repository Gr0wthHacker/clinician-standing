"""FastAPI application for the standing API.

Endpoints (all under ``/v1``):

* ``GET  /health``                 liveness, no auth, no database
* ``GET  /sources``                sources this API reads and their as-of dates
* ``GET  /clinicians/{npi}``       standing by NPI
* ``GET  /clinicians``             standing by ``last_name`` + ``state`` (+ ``first_name``)
* ``POST /standing/check``         either lookup, JSON body
* ``POST /roster``                 hand a placed clinician to the roster (the one write)

Errors use one envelope, ``{"error": {"code", "message"}}``, with the codes
``invalid_request`` (400), ``unauthorized`` (401), ``roster_entry_closed`` (409),
``rate_limited`` (429), ``auth_not_configured`` (503), ``roster_not_configured``
(503) and ``store_unavailable`` (503).

Request bodies are never logged.
"""

# No `from __future__ import annotations` here: FastAPI resolves the
# dependency annotations at runtime, and the closures in create_app reference
# local names that a deferred annotation could not see.

import logging
import math
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError

from . import service
from .auth import ApiSettings, KeyRing, RateLimiter
from .models import (
    CheckRequest,
    ErrorResponse,
    HealthResponse,
    RosterReceipt,
    RosterSubmission,
    SourcesResponse,
    StandingResponse,
)
from .roster_store import PostgresRosterStore, RosterEntryClosed, RosterStore
from .store import PostgresStore, StandingStore, StoreUnavailable

__all__ = ["ApiError", "create_app"]

LOGGER = logging.getLogger(__name__)

API_VERSION = "0.1.0"

DESCRIPTION = """
Lookups over the federal data the Clinician Standing ingest has loaded, plus one
write: `POST /v1/roster`, which records a placed clinician for review.

Every lookup response carries a `sources` block. `sources.checked` lists each
source the answer read, with `as_of` (when that snapshot was fetched) and a
`stale` flag. `sources.not_checked` lists the sources this API knows about but
did not read, with the reason. An answer covers only the checked sources.

Roster intake is idempotent on `(source_system, external_id)`. Licenses sent
there are recorded as claims and are not verified until matched to source evidence.

Authenticate with `Authorization: Bearer <key>`.
"""

ROSTER_NOTE = (
    "Received for review. Reported licenses are recorded as claims and are not "
    "verified until they are matched to source evidence."
)

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse, "description": "invalid_request"},
    401: {"model": ErrorResponse, "description": "unauthorized"},
    429: {"model": ErrorResponse, "description": "rate_limited"},
    503: {"model": ErrorResponse, "description": "auth_not_configured or store_unavailable"},
}

_ROSTER_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_ERRORS,
    200: {"model": RosterReceipt, "description": "A resend: updated or unchanged"},
    409: {"model": ErrorResponse, "description": "roster_entry_closed"},
    503: {
        "model": ErrorResponse,
        "description": "auth_not_configured, roster_not_configured or store_unavailable",
    },
}


class ApiError(Exception):
    """An error with a documented code."""

    def __init__(
        self, status: int, code: str, message: str, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers or {}


def _error(
    status: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
        headers=headers,
    )


def _validation_message(exc: RequestValidationError | ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path"))
        msg = str(err.get("msg", "invalid")).removeprefix("Value error, ")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts) or "invalid request"


def create_app(
    store: StandingStore | None = None,
    settings: ApiSettings | None = None,
    limiter: RateLimiter | None = None,
    clock: Callable[[], datetime] | None = None,
    roster_store: RosterStore | None = None,
) -> FastAPI:
    """Build the application.

    With no arguments, settings come from the environment and the store is
    Postgres at ``API_DATABASE_URL``; this is what
    ``uvicorn --factory clinician_standing.api.app:create_app`` calls.
    ``clock`` fixes "now" for staleness and ``checked_at``; tests pass one.
    ``roster_store`` backs ``POST /v1/roster``; without one it is Postgres at
    ``API_ROSTER_DATABASE_URL`` when that is set, and the endpoint answers 503
    otherwise.
    """
    now = clock or (lambda: datetime.now(UTC))
    settings = settings or ApiSettings.from_env()
    if store is None:
        if not settings.database_url:
            raise RuntimeError("API_DATABASE_URL is not set; the API has nothing to read")
        store = PostgresStore(settings.database_url)
    if roster_store is None and settings.roster_database_url:
        roster_store = PostgresRosterStore(settings.roster_database_url)
    keyring = KeyRing(settings.api_keys)
    if keyring.ignored_short:
        LOGGER.warning(
            "ignored %s API key(s) shorter than the minimum length", keyring.ignored_short
        )
    if not keyring.configured:
        LOGGER.warning("API_KEYS has no usable key; authenticated endpoints will answer 503")
    limiter = limiter or RateLimiter(limit=settings.rate_limit_per_minute)
    bearer = HTTPBearer(auto_error=False)

    app = FastAPI(
        title="Clinician Standing API",
        version=API_VERSION,
        description=DESCRIPTION,
        docs_url="/docs",
        redoc_url=None,
    )

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _error(exc.status, exc.code, exc.message, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _error(400, "invalid_request", _validation_message(exc))

    @app.exception_handler(StoreUnavailable)
    async def _store_down(_: Request, exc: StoreUnavailable) -> JSONResponse:
        LOGGER.error("store unavailable: %s", exc)
        return _error(503, "store_unavailable", "The data store did not answer. Retry later.")

    def authenticate(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> str:
        if not keyring.configured:
            raise ApiError(503, "auth_not_configured", "No API keys are configured on this server.")
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise ApiError(
                401,
                "unauthorized",
                "Send an API key as 'Authorization: Bearer <key>'.",
                {"WWW-Authenticate": "Bearer"},
            )
        key_id = keyring.identify(credentials.credentials)
        if key_id is None:
            raise ApiError(
                401, "unauthorized", "API key not recognized.", {"WWW-Authenticate": "Bearer"}
            )
        wait = limiter.hit(key_id)
        if wait is not None:
            raise ApiError(
                429,
                "rate_limited",
                f"Rate limit of {limiter.limit} requests per minute reached.",
                {"Retry-After": str(max(1, math.ceil(wait)))},
            )
        return key_id

    auth = [Depends(authenticate)]

    def run_check(request: CheckRequest) -> StandingResponse:
        assert store is not None
        return service.check(store, request, now=now())

    def parse(**fields: str | None) -> CheckRequest:
        try:
            return CheckRequest(**fields)
        except ValidationError as exc:
            raise ApiError(400, "invalid_request", _validation_message(exc)) from exc

    @app.get("/v1/health", response_model=HealthResponse, tags=["meta"])
    def health() -> HealthResponse:
        """Liveness only. Does not touch the database."""
        return HealthResponse(status="ok")

    @app.get(
        "/v1/sources",
        response_model=SourcesResponse,
        responses=_ERRORS,
        dependencies=auth,
        tags=["meta"],
    )
    def sources() -> SourcesResponse:
        """Sources this API reads, whether each has been ingested, and as of when."""
        assert store is not None
        return service.sources_response(store, now=now())

    @app.get(
        "/v1/clinicians/{npi}",
        response_model=StandingResponse,
        responses=_ERRORS,
        dependencies=auth,
        tags=["standing"],
    )
    def by_npi(npi: str) -> StandingResponse:
        """Standing for one NPI: identity, exclusion screen, license records."""
        return run_check(parse(npi=npi))

    @app.get(
        "/v1/clinicians",
        response_model=StandingResponse,
        responses=_ERRORS,
        dependencies=auth,
        tags=["standing"],
    )
    def by_name(
        last_name: Annotated[str, Query(max_length=80)],
        state: Annotated[str, Query(description="Two-letter USPS code")],
        first_name: Annotated[str | None, Query(max_length=80)] = None,
    ) -> StandingResponse:
        """Candidates whose name matches exactly and who practice or hold a license in
        ``state``. Returns up to 25, each with its own exclusion and license screen."""
        return run_check(parse(last_name=last_name, first_name=first_name, state=state))

    @app.post(
        "/v1/standing/check",
        response_model=StandingResponse,
        responses=_ERRORS,
        dependencies=auth,
        tags=["standing"],
    )
    def standing_check(body: CheckRequest) -> StandingResponse:
        """Either lookup as a JSON body: ``{"npi"}`` or ``{"last_name", "state"}``
        with an optional ``first_name``."""
        return run_check(body)

    @app.post(
        "/v1/roster",
        status_code=201,
        response_model=RosterReceipt,
        responses=_ROSTER_RESPONSES,
        tags=["roster"],
    )
    def roster_intake(
        body: RosterSubmission,
        response: Response,
        key_id: Annotated[str, Depends(authenticate)],
    ) -> RosterReceipt:
        """Record a placed clinician for roster review.

        Idempotent on ``(source_system, external_id)``: the first call answers
        201 ``created``; a resend answers 200 ``updated`` when anything changed
        and 200 ``unchanged`` when nothing did. Send ``employment_status: ended``
        when the placement ends. Unknown fields are rejected, so nothing beyond
        name, NPI, licenses, states and employer can be stored."""
        if roster_store is None:
            raise ApiError(
                503, "roster_not_configured", "Roster intake is not configured on this server."
            )
        try:
            write = roster_store.upsert(body, key_id, now())
        except RosterEntryClosed as exc:
            raise ApiError(
                409,
                "roster_entry_closed",
                "This roster entry was closed and cannot be changed through the API.",
            ) from exc
        if write.outcome != "created":
            response.status_code = 200
        return RosterReceipt(
            id=write.id,
            source_system=body.source_system,
            external_id=body.external_id,
            outcome=write.outcome,
            review_status=write.review_status,
            received_at=write.received_at,
            updated_at=write.updated_at,
            note=ROSTER_NOTE,
        )

    return app
