"""The standing API, end to end over HTTP, against synthetic in-memory data.

No network and no database: the app is built on a MemoryStore loaded from
tests/fixtures/api/standing_synthetic.json, whose clinicians are invented
(SAMPLE, TESTCASE) and whose NPIs are generated. The Postgres store runs the
same lookups against a seeded database in test_api_db.py.

The wording assertions matter as much as the status codes. A lookup that found
no exclusion must always say how much of the OIG file it could not see and must
always refuse the stronger claim; that is checked here so it cannot drift.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from clinician_standing.api import service
from clinician_standing.api.app import create_app
from clinician_standing.api.auth import ApiSettings, KeyRing, RateLimiter
from clinician_standing.api.models import CheckRequest, is_valid_npi
from clinician_standing.api.store import MemoryStore

FIXTURE = Path(__file__).parent / "fixtures" / "api" / "standing_synthetic.json"
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
KEY = "test-key-synthetic-0123456789abcdef"
AUTH = {"Authorization": f"Bearer {KEY}"}

ALPHA = "1990001012"  # clean, MN
BRAVO = "1990001020"  # open LEIE exclusion, MN + WI
CHARLIE = "1990001038"  # reinstated exclusion, Nursys license in WI, no practice
DELTA = "1990001046"  # no NPI match, one LEIE name+state candidate for review, MN
ABSENT = "1990001053"  # valid check digit, not in the data


def _store() -> MemoryStore:
    return MemoryStore.from_dict(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _client(
    store: MemoryStore | None = None,
    keys: tuple[str, ...] = (KEY,),
    limit: int = 1000,
) -> TestClient:
    app = create_app(
        store=store or _store(),
        settings=ApiSettings(database_url=None, api_keys=keys, rate_limit_per_minute=limit),
        clock=lambda: NOW,
    )
    return TestClient(app)


@pytest.fixture
def client() -> TestClient:
    return _client()


# ---------------------------------------------------------------------------
# Auth, rate limit, errors
# ---------------------------------------------------------------------------


def test_health_needs_no_key(client: TestClient) -> None:
    assert client.get("/v1/health").json() == {"status": "ok"}


@pytest.mark.parametrize(
    "path",
    ["/v1/sources", f"/v1/clinicians/{ALPHA}", "/v1/clinicians?last_name=SAMPLE&state=MN"],
)
def test_missing_key_is_401(client: TestClient, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"
    assert resp.headers["WWW-Authenticate"] == "Bearer"


def test_wrong_key_is_401(client: TestClient) -> None:
    resp = client.get(f"/v1/clinicians/{ALPHA}", headers={"Authorization": "Bearer nope" * 5})
    assert resp.status_code == 401


def test_post_without_key_is_401_even_with_bad_body(client: TestClient) -> None:
    resp = client.post("/v1/standing/check", json={"npi": "123"})
    assert resp.status_code == 401


def test_no_keys_configured_fails_closed() -> None:
    resp = _client(keys=()).get(f"/v1/clinicians/{ALPHA}", headers=AUTH)
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "auth_not_configured"


def test_short_keys_are_ignored() -> None:
    ring = KeyRing(["short", KEY])
    assert ring.ignored_short == 1
    assert ring.identify("short") is None
    assert ring.identify(KEY) is not None


def test_rate_limit_returns_429_with_retry_after() -> None:
    client = _client(limit=2)
    assert client.get("/v1/sources", headers=AUTH).status_code == 200
    assert client.get("/v1/sources", headers=AUTH).status_code == 200
    resp = client.get("/v1/sources", headers=AUTH)
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "rate_limited"
    assert int(resp.headers["Retry-After"]) >= 1


def test_rate_limiter_window_resets() -> None:
    t = [0.0]
    limiter = RateLimiter(limit=1, window=60, clock=lambda: t[0])
    assert limiter.hit("k") is None
    assert limiter.hit("k") == pytest.approx(60)
    t[0] = 61
    assert limiter.hit("k") is None


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_KEYS", f" {KEY} , other-key-0123456789abcdefgh ,")
    monkeypatch.setenv("API_RATE_LIMIT_PER_MINUTE", "5")
    monkeypatch.delenv("API_DATABASE_URL", raising=False)
    settings = ApiSettings.from_env()
    assert len(settings.api_keys) == 2
    assert settings.rate_limit_per_minute == 5
    assert settings.database_url is None


def test_create_app_without_database_url_refuses() -> None:
    with pytest.raises(RuntimeError, match="API_DATABASE_URL"):
        create_app(settings=ApiSettings(database_url=None, api_keys=(KEY,)))


@pytest.mark.parametrize("npi", ["123", "1990001013", "abcdefghij"])
def test_bad_npi_is_400(client: TestClient, npi: str) -> None:
    resp = client.get(f"/v1/clinicians/{npi}", headers=AUTH)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_request"
    assert "check digit" in resp.json()["error"]["message"]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"last_name": "SAMPLE"},
        {"npi": ALPHA, "last_name": "SAMPLE", "state": "MN"},
        {"npi": ALPHA, "state": "MN"},
        {"last_name": "SAMPLE", "state": "Minnesota"},
    ],
)
def test_bad_check_body_is_400(client: TestClient, body: dict) -> None:
    resp = client.post("/v1/standing/check", json=body, headers=AUTH)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_request"


def test_name_search_requires_state(client: TestClient) -> None:
    resp = client.get("/v1/clinicians?last_name=SAMPLE", headers=AUTH)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_request"


def test_npi_check_digit() -> None:
    assert is_valid_npi(ALPHA)
    assert not is_valid_npi("1990001013")


# ---------------------------------------------------------------------------
# Sources block
# ---------------------------------------------------------------------------


def _by_key(block: dict) -> dict[str, dict]:
    return {s["key"]: s for s in block["checked"] + block["not_checked"]}


def test_sources_endpoint_splits_checked_and_not_checked(client: TestClient) -> None:
    body = client.get("/v1/sources", headers=AUTH).json()
    checked = {s["key"] for s in body["sources"]["checked"]}
    not_checked = {s["key"] for s in body["sources"]["not_checked"]}
    assert checked == {"cms_dac", "oig_leie", "nursys", "nppes", "nppes_weekly"}
    assert not_checked == {"sam_gov", "state_ca"}
    # Enrollment sources feed nothing in this API and are left out entirely.
    assert "cms_revalidation" not in checked | not_checked
    assert body["checked_at"].startswith("2026-10-28T12:00")


def test_sources_carry_as_of_and_staleness(client: TestClient) -> None:
    block = client.get("/v1/sources", headers=AUTH).json()["sources"]
    by_key = _by_key(block)
    assert by_key["oig_leie"]["as_of"].startswith("2026-08-01T02:05")
    assert by_key["oig_leie"]["stale"] is True
    assert by_key["cms_dac"]["stale"] is False
    assert by_key["sam_gov"]["as_of"] is None
    assert by_key["sam_gov"]["reason_not_checked"] == "No data from this source has been ingested."
    assert by_key["nppes"]["checked"] is True
    assert by_key["nppes"]["as_of"].startswith("2026-10-05T03:00")
    assert by_key["nppes"]["reason_not_checked"] is None
    assert by_key["nppes"]["role"] == "identity"
    assert by_key["nppes_weekly"]["as_of"].startswith("2026-10-27T03:00")
    assert by_key["nppes_weekly"]["freshness_sla_days"] == 14


def test_every_lookup_response_has_sources_and_scope(client: TestClient) -> None:
    for resp in (
        client.get(f"/v1/clinicians/{ALPHA}", headers=AUTH),
        client.get(f"/v1/clinicians/{ABSENT}", headers=AUTH),
        client.get("/v1/clinicians?last_name=SAMPLE&state=MN", headers=AUTH),
        client.post("/v1/standing/check", json={"npi": BRAVO}, headers=AUTH),
        client.get(f"/v1/clinicians/{CHARLIE}", headers=AUTH),
    ):
        body = resp.json()
        assert resp.status_code == 200
        assert body["sources"]["checked"]
        assert all(s["as_of"] for s in body["sources"]["checked"])
        assert body["scope"] == service.SCOPE
        assert "verif" not in json.dumps(body).lower()


# ---------------------------------------------------------------------------
# NPI lookups
# ---------------------------------------------------------------------------


def test_clean_npi_reports_no_npi_match_with_denominator(client: TestClient) -> None:
    body = client.get(f"/v1/clinicians/{ALPHA}", headers=AUTH).json()
    assert body["result"] == "found"
    c = body["clinicians"][0]
    assert c["match_basis"] == "npi"
    assert c["name_match"] is None
    assert c["identity"]["last_name"] == "SAMPLE"
    assert c["identity"]["practice_states"] == ["MN"]
    assert c["identity"]["source"] == "cms_dac"
    ex = c["exclusions"]
    assert ex["status"] == "no_npi_match"
    assert ex["matches"] == []
    assert ex["sources_screened"] == ["oig_leie"]
    note = ex["note"]
    assert "fetched 2026-08-01" in note
    assert "90 of the 100 records" in note
    assert "name and date-of-birth matching is not enabled" in note
    assert "7 were linked by name and state to at least one NPPES NPI" in note
    assert ex["possible_matches"] == []
    assert "past its 45-day freshness limit" in note
    assert "Not screened: SAM.gov Exclusions." in note
    assert note.endswith("does not establish that the clinician is not excluded.")


def test_open_exclusion_is_reported_with_source_and_date(client: TestClient) -> None:
    body = client.get(f"/v1/clinicians/{BRAVO}", headers=AUTH).json()
    ex = body["clinicians"][0]["exclusions"]
    assert ex["status"] == "open_exclusion_found"
    [match] = ex["matches"]
    assert match["source"] == "leie"
    assert match["source_key"] == "oig_leie"
    assert match["source_as_of"].startswith("2026-08-01")
    assert match["action_date"] == "2025-03-15"
    assert match["open"] is True
    assert match["match_basis"] == "npi"
    assert "does not establish" not in ex["note"]


def test_name_state_candidate_is_a_possible_match_never_an_exclusion(client: TestClient) -> None:
    body = client.get(f"/v1/clinicians/{DELTA}", headers=AUTH).json()
    ex = body["clinicians"][0]["exclusions"]
    assert ex["status"] == "possible_match_needs_review"
    assert ex["matches"] == []
    # The rejected and the superseded candidate in the fixture are not shown.
    [possible] = ex["possible_matches"]
    assert possible["status"] == "possible_match_needs_review"
    assert possible["match_basis"] == "name_state"
    assert 0 < possible["match_confidence"] < 1
    assert possible["match_detail"]["first_name"] == "exact"
    assert possible["leie_state"] == "MN"
    assert possible["source_key"] == "oig_leie"
    assert possible["open"] is True
    note = ex["note"]
    assert "No exclusion record matched this NPI" in note
    assert "1 OIG LEIE record with no NPI names someone with this clinician's name" in note
    assert "needs human review, and none is asserted as an exclusion" in note
    assert note.endswith("does not establish that the clinician is not excluded.")


def test_possible_match_beside_an_npi_exclusion_keeps_the_npi_status() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["clinicians"][1]["possible_exclusions"] = data["clinicians"][3]["possible_exclusions"][:1]
    resp = service.check(MemoryStore.from_dict(data), CheckRequest(npi=BRAVO), now=NOW)
    ex = resp.clinicians[0].exclusions
    assert ex.status == "open_exclusion_found"
    assert [m.match_basis for m in ex.matches] == ["npi"]
    assert [p.match_basis for p in ex.possible_matches] == ["name_state"]


def test_confirmed_candidate_is_still_not_an_exclusion() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["clinicians"][3]["possible_exclusions"][0]["review_status"] = "confirmed"
    resp = service.check(MemoryStore.from_dict(data), CheckRequest(npi=DELTA), now=NOW)
    ex = resp.clinicians[0].exclusions
    assert ex.status == "possible_match_needs_review"
    assert ex.matches == []
    assert ex.possible_matches[0].status == "confirmed_by_review"


def test_possible_match_model_refuses_confidence_of_one() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["clinicians"][3]["possible_exclusions"][0]["match_confidence"] = 1.0
    with pytest.raises(ValueError, match="less than 1"):
        service.check(MemoryStore.from_dict(data), CheckRequest(npi=DELTA), now=NOW)


def test_leie_note_says_when_name_state_matching_did_not_run() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    leie = next(s for s in data["sources"] if s["key"] == "oig_leie")
    leie["parsed"].pop("name_state_matching_ran")
    resp = service.check(MemoryStore.from_dict(data), CheckRequest(npi=ALPHA), now=NOW)
    assert "Name and state matching against NPPES did not run" in resp.clinicians[0].exclusions.note


def test_reinstated_exclusion_and_license_record(client: TestClient) -> None:
    c = client.get(f"/v1/clinicians/{CHARLIE}", headers=AUTH).json()["clinicians"][0]
    assert c["exclusions"]["status"] == "reinstated_exclusion_found"
    assert c["exclusions"]["matches"][0]["reinstated_date"] == "2022-06-01"
    lic = c["licenses"]
    assert lic["coverage"] == "records_found"
    [record] = lic["records"]
    assert record["state"] == "WI"
    assert record["status"] == "active"
    assert record["issued_on"] == "2018-01-15"
    assert record["expires_on"] == "2027-02-28"
    assert record["source_key"] == "nursys"
    assert record["discipline_reported"] is False
    assert record["last_confirmed_at"].startswith("2026-10-10")
    assert "No state board source was checked." in lic["note"]
    assert "Nursys data covers only nurses enrolled" in lic["note"]


def test_no_license_records_is_not_called_unlicensed(client: TestClient) -> None:
    lic = client.get(f"/v1/clinicians/{ALPHA}", headers=AUTH).json()["clinicians"][0]["licenses"]
    assert lic["coverage"] == "no_records_found"
    assert lic["records"] == []
    assert "does not mean the clinician is unlicensed" in lic["note"]


def test_unknown_npi_is_not_found_with_note(client: TestClient) -> None:
    body = client.get(f"/v1/clinicians/{ABSENT}", headers=AUTH).json()
    assert body["result"] == "not_found"
    assert body["clinicians"] == []
    assert "no screen was run" in body["note"]
    assert body["query"] == {"npi": ABSENT}


def test_post_check_matches_get(client: TestClient) -> None:
    got = client.get(f"/v1/clinicians/{BRAVO}", headers=AUTH).json()
    posted = client.post("/v1/standing/check", json={"npi": BRAVO}, headers=AUTH).json()
    assert got == posted


# ---------------------------------------------------------------------------
# Name + state lookups
# ---------------------------------------------------------------------------


def test_name_and_state_returns_candidates(client: TestClient) -> None:
    body = client.get("/v1/clinicians?last_name=sample&state=mn", headers=AUTH).json()
    assert body["result"] == "multiple_candidates"
    assert body["query"] == {"last_name": "SAMPLE", "state": "MN"}
    assert [c["identity"]["npi"] for c in body["clinicians"]] == [ALPHA, BRAVO]
    assert all(c["match_basis"] == "name_state" for c in body["clinicians"])
    assert all(c["name_match"] == "exact" for c in body["clinicians"])


def test_license_state_ties_a_clinician_to_a_state(client: TestClient) -> None:
    body = client.get("/v1/clinicians?last_name=SAMPLE&state=WI", headers=AUTH).json()
    assert {c["identity"]["npi"] for c in body["clinicians"]} == {BRAVO, CHARLIE}


def test_first_name_narrows_to_one(client: TestClient) -> None:
    body = client.post(
        "/v1/standing/check",
        json={"last_name": "  Sample ", "first_name": "alpha", "state": "MN"},
        headers=AUTH,
    ).json()
    assert body["result"] == "found"
    assert body["clinicians"][0]["identity"]["npi"] == ALPHA
    assert body["query"]["first_name"] == "ALPHA"


def test_name_in_other_state_is_not_found(client: TestClient) -> None:
    body = client.get("/v1/clinicians?last_name=TESTCASE&state=WI", headers=AUTH).json()
    assert body["result"] == "not_found"
    assert "this name with a practice or license in this state" in body["note"]


def test_name_results_are_capped(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    monkeypatch.setattr(service, "MAX_CANDIDATES", 1)
    body = client.get("/v1/clinicians?last_name=SAMPLE&state=MN", headers=AUTH).json()
    assert len(body["clinicians"]) == 1
    assert body["truncated"] is True


# ---------------------------------------------------------------------------
# Coverage edges, at the service layer
# ---------------------------------------------------------------------------


def _without(*keys: str) -> MemoryStore:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for source in data["sources"]:
        if source["key"] in keys:
            source.pop("fetched_at", None)
            source.pop("freshness_expires_at", None)
    return MemoryStore.from_dict(data)


def test_no_exclusion_source_means_not_screened() -> None:
    resp = service.check(_without("oig_leie"), CheckRequest(npi=ALPHA), now=NOW)
    ex = resp.clinicians[0].exclusions
    assert ex.status == "not_screened"
    assert ex.sources_screened == []
    assert "absence of a screen" in ex.note
    assert "oig_leie" in {s.key for s in resp.sources.not_checked}


def test_no_license_source_means_unknown() -> None:
    resp = service.check(_without("nursys"), CheckRequest(npi=ALPHA), now=NOW)
    lic = resp.clinicians[0].licenses
    assert lic.coverage == "no_license_source_ingested"
    assert "license status is unknown" in lic.note


def test_name_dob_match_is_labelled() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["clinicians"][1]["sanctions"][0]["match_confidence"] = 0.8
    resp = service.check(MemoryStore.from_dict(data), CheckRequest(npi=BRAVO), now=NOW)
    assert resp.clinicians[0].exclusions.matches[0].match_basis == "name_dob"


# ---------------------------------------------------------------------------
# OpenAPI document
# ---------------------------------------------------------------------------


def test_committed_openapi_matches_app() -> None:
    """docs/openapi.json is generated; regenerate with `make openapi`."""
    committed = json.loads(
        (Path(__file__).parent.parent / "docs" / "openapi.json").read_text(encoding="utf-8")
    )
    assert committed == _client().app.openapi()
