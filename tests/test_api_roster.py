"""POST /v1/roster over HTTP, against the in-memory roster store.

Synthetic data only: SAMPLE / TESTCASE names and generated NPIs. The Postgres
store runs the same idempotency rules in test_api_roster_db.py.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clinician_standing.api.app import create_app
from clinician_standing.api.auth import ApiSettings
from clinician_standing.api.models import RosterSubmission
from clinician_standing.api.roster_store import MemoryRosterStore
from clinician_standing.api.store import MemoryStore

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
KEY = "test-key-synthetic-0123456789abcdef"
AUTH = {"Authorization": f"Bearer {KEY}"}
NPI = "1990001012"


def _client(
    roster: MemoryRosterStore | None = None, *, configured: bool = True
) -> tuple[TestClient, MemoryRosterStore]:
    roster = roster or MemoryRosterStore()
    app = create_app(
        store=MemoryStore([], []),
        settings=ApiSettings(database_url=None, api_keys=(KEY,), rate_limit_per_minute=1000),
        clock=lambda: NOW,
        roster_store=roster if configured else None,
    )
    return TestClient(app), roster


def _body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "source_system": "placerail",
        "external_id": "placement-0001",
        "clinician": {"first_name": "Alpha", "last_name": "Sample", "npi": NPI, "credential": "rn"},
        "licenses": [
            {"state": "mn", "license_type": "rn", "license_number": "TEST-1", "expires_on": None}
        ],
        "states": ["WI"],
        "employer": {"name": "Sample Test Clinic"},
        "placed_on": "2026-11-02",
    }
    body.update(overrides)
    return body


def test_requires_a_key() -> None:
    client, _ = _client()
    assert client.post("/v1/roster", json=_body()).status_code == 401


def test_bad_body_without_key_is_still_401() -> None:
    client, _ = _client()
    assert client.post("/v1/roster", json={"nope": 1}).status_code == 401


def test_not_configured_is_503_after_auth() -> None:
    client, _ = _client(configured=False)
    resp = client.post("/v1/roster", json=_body(), headers=AUTH)
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "roster_not_configured"


def test_create_then_resend_is_idempotent() -> None:
    client, roster = _client()
    first = client.post("/v1/roster", json=_body(), headers=AUTH)
    assert first.status_code == 201
    receipt = first.json()
    assert receipt["outcome"] == "created"
    assert receipt["review_status"] == "pending"
    assert "not verified" in receipt["note"]

    again = client.post("/v1/roster", json=_body(), headers=AUTH)
    assert again.status_code == 200
    assert again.json()["outcome"] == "unchanged"
    assert again.json()["id"] == receipt["id"]

    changed = client.post("/v1/roster", json=_body(employment_status="ended"), headers=AUTH)
    assert changed.status_code == 200
    assert changed.json()["outcome"] == "updated"
    assert changed.json()["id"] == receipt["id"]
    stored = roster.get("placerail", "placement-0001")
    assert stored is not None and stored["employment_status"] == "ended"


def test_normalizes_names_states_and_license_states() -> None:
    client, roster = _client()
    client.post("/v1/roster", json=_body(), headers=AUTH)
    stored = roster.get("placerail", "placement-0001")
    assert stored is not None
    assert (stored["first_name"], stored["last_name"], stored["credential"]) == (
        "ALPHA",
        "SAMPLE",
        "RN",
    )
    assert stored["states"] == ["MN", "WI"]
    assert '"license_type": "RN"' in stored["licenses"]
    assert stored["api_key_id"] and KEY not in stored["api_key_id"]


def test_npi_is_optional() -> None:
    client, _ = _client()
    body = _body(clinician={"last_name": "Testcase"})
    assert client.post("/v1/roster", json=body, headers=AUTH).status_code == 201


@pytest.mark.parametrize(
    "patch",
    [
        {"clinician": {"last_name": "Sample", "npi": "1990001013"}},  # bad check digit
        {"clinician": {"last_name": "  "}},
        {"clinician": {"last_name": "Sample", "date_of_birth": "1980-01-01"}},  # PHI
        {"clinician": {"last_name": "Sample", "email": "x@example.com"}},
        {"ssn": "000-00-0000"},
        {"source_system": "Place Rail!"},
        {"external_id": ""},
        {"states": ["Minnesota"]},
        {"licenses": [{"state": "MN"}]},
        {"employer": {"name": ""}},
        {"employer": {"name": "X", "org_pac_id": "123"}},
        {"employment_status": "fired"},
    ],
)
def test_invalid_or_extra_fields_are_400(patch: dict[str, Any]) -> None:
    client, roster = _client()
    resp = client.post("/v1/roster", json=_body(**patch), headers=AUTH)
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "invalid_request"
    assert roster.get("placerail", "placement-0001") is None


def test_closed_entry_is_409() -> None:
    client, roster = _client()
    client.post("/v1/roster", json=_body(), headers=AUTH)
    roster.close("placerail", "placement-0001")
    resp = client.post("/v1/roster", json=_body(), headers=AUTH)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "roster_entry_closed"


def test_payload_is_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    client, _ = _client()
    with caplog.at_level(logging.DEBUG):
        client.post("/v1/roster", json=_body(), headers=AUTH)
        client.post("/v1/roster", json=_body(clinician={"last_name": "x" * 200}), headers=AUTH)
    text = caplog.text.upper()
    assert NPI not in text
    assert "SAMPLE" not in text
    assert "TEST-1" not in text


def test_digest_ignores_input_spelling() -> None:
    a = RosterSubmission.model_validate(_body())
    b = RosterSubmission.model_validate(
        _body(
            clinician={
                "first_name": " alpha ",
                "last_name": "SAMPLE",
                "npi": NPI,
                "credential": "RN",
            },
            states=["wi", "MN"],
        )
    )
    assert a.digest() == b.digest()


def test_settings_read_roster_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_ROSTER_DATABASE_URL", " postgresql://roster ")
    assert ApiSettings.from_env().roster_database_url == "postgresql://roster"
    monkeypatch.delenv("API_ROSTER_DATABASE_URL")
    assert ApiSettings.from_env().roster_database_url is None
