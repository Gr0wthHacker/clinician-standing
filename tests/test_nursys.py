"""Nursys connector: pure logic, the HTTP client against a fake transport, and
the secret store. No network and no database (conftest guarantees both).

The connector's database path (load/derive) is exercised by the database-marked
integration tests; here we pin the parts that decide correctness on their own:
the license-status mapping, the tolerant payload walk, rate limiting, URL
validation, the async submit/poll, and credential rotation persistence.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from clinician_standing.connectors.nursys import (
    NursysApiError,
    NursysClient,
    NursysRateLimited,
    RateLimiter,
    generate_password,
    iter_nurse_licenses,
    map_license_status,
)
from clinician_standing.secrets import (
    NursysCredential,
    SecretError,
    SecretStore,
    env_var_for,
)

# --------------------------------------------------------------------------- #
# map_license_status
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("active", "status", "expected"),
    [
        ("Active", "UNENCUMBERED", "active"),
        ("Active", "UNENCUMBERED (see history)", "active"),
        ("Inactive", "EXPIRED", "expired"),
        ("Active", "SUSPENSION (see history)", "suspended"),
        ("Active", "REVOKED (see history)", "revoked"),
        ("Active", "PROBATION (see history)", "probation"),
        # A revoked license reads as revoked even if the Active flag lies.
        ("Active", "REVOKED", "revoked"),
        # Unknown, non-active status is lapsed, never silently active.
        ("Inactive", "CEASE & DESIST (see history)", "lapsed"),
        (None, None, "lapsed"),
        ("Y", "", "active"),
    ],
)
def test_map_license_status(active: str | None, status: str | None, expected: str) -> None:
    assert map_license_status(active, status) == expected


# --------------------------------------------------------------------------- #
# iter_nurse_licenses
# --------------------------------------------------------------------------- #

_SAMPLE_PAYLOAD = {
    "NurseLookupResponses": [
        {
            "Nurse": {
                "FirstName": "Anthonette",
                "LastName": "Sparman",
                "NcsbnId": "99912345",
                "NurseLookupLicenses": [
                    {
                        "JurisdictionAbbreviation": "NY",
                        "LicenseType": "RN",
                        "LicenseNumber": "284831",
                        "Active": "Active",
                        "LicenseStatus": "UNENCUMBERED",
                        "LicenseOriginalDate": "2005-06-01",
                        "LicenseExpirationDate": "2027-05-31",
                        "CompactStatus": "Not a compact license",
                        "NurseLookupDisciplines": [],
                    },
                    {
                        "JurisdictionAbbreviation": "nj",
                        "LicenseType": "APRN",
                        "LicenseNumber": "AP-9",
                        "Active": "Inactive",
                        "LicenseStatus": "SUSPENSION (see history)",
                        "LicenseExpirationDate": "2024-01-15T00:00:00-05:00",
                        "NurseLookupDisciplines": [{"DateActionWasTaken": "2023-01-01"}],
                    },
                ],
            }
        },
        # A nurse with a blank NCSBN ID must be skipped, not crash the walk.
        {"Nurse": {"NcsbnId": "", "NurseLookupLicenses": [{"LicenseType": "RN"}]}},
    ]
}


def test_iter_nurse_licenses_flattens_and_normalizes() -> None:
    rows = list(iter_nurse_licenses(_SAMPLE_PAYLOAD))
    assert len(rows) == 2

    first, second = rows
    assert first["ncsbn_id"] == 99912345
    assert first["jurisdiction"] == "NY"
    assert first["status"] == "active"
    assert first["issue_date"].isoformat() == "2005-06-01"
    assert first["expiry_date"].isoformat() == "2027-05-31"
    assert first["has_discipline"] is False

    # Jurisdiction is upper-cased; a full timestamp is reduced to its date.
    assert second["jurisdiction"] == "NJ"
    assert second["status"] == "suspended"
    assert second["expiry_date"].isoformat() == "2024-01-15"
    assert second["has_discipline"] is True


def test_iter_nurse_licenses_skips_blank_ncsbn() -> None:
    # The third nurse in the payload has a blank NcsbnId and no valid licenses.
    assert all(r["ncsbn_id"] == 99912345 for r in iter_nurse_licenses(_SAMPLE_PAYLOAD))


# --------------------------------------------------------------------------- #
# generate_password
# --------------------------------------------------------------------------- #


def test_generate_password_meets_complexity_and_length() -> None:
    for _ in range(50):
        pw = generate_password()
        assert 16 <= len(pw) <= 50
        assert any(c.islower() for c in pw)
        assert any(c.isupper() for c in pw)
        assert any(c.isdigit() for c in pw)
        assert any(not c.isalnum() for c in pw)


def test_generate_password_is_not_constant() -> None:
    assert generate_password() != generate_password()


# --------------------------------------------------------------------------- #
# RateLimiter
# --------------------------------------------------------------------------- #


class _Clock:
    """A controllable monotonic clock. sleep advances the clock, never blocks."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_rate_limiter_allows_burst_then_throttles() -> None:
    clock = _Clock()
    limiter = RateLimiter(max_per_minute=25, time_fn=clock.time, sleep_fn=clock.sleep)
    for _ in range(25):
        limiter.acquire()
    assert clock.slept == []  # 25 in the window, no wait yet
    limiter.acquire()  # the 26th must wait out the window
    assert clock.slept and clock.slept[0] > 0


def test_rate_limiter_window_slides() -> None:
    clock = _Clock()
    limiter = RateLimiter(max_per_minute=2, time_fn=clock.time, sleep_fn=clock.sleep)
    limiter.acquire()
    limiter.acquire()
    clock.now += 61  # both calls fall out of the 60s window
    limiter.acquire()
    assert clock.slept == []


# --------------------------------------------------------------------------- #
# NursysClient -- fake transport
# --------------------------------------------------------------------------- #


class _FakeResponse:
    def __init__(self, body: object) -> None:
        self._body = json.dumps(body).encode("utf-8") if body is not None else b""

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class _FakeTransport:
    """Routes requests by method+path to canned responses; records calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.change_password_body: dict | None = None
        self.last_post_body: dict | None = None

    def __call__(self, request, timeout=None):
        method = request.get_method()
        url = request.full_url
        self.calls.append((method, url))
        if method == "POST" and request.data is not None:
            self.last_post_body = json.loads(request.data.decode("utf-8"))
        if "notificationlookup" in url and method == "POST":
            return _FakeResponse({"TransactionId": "txn-1"})
        if "notificationlookup" in url and method == "GET":
            return _FakeResponse(_SAMPLE_PAYLOAD)
        if "nurselookup" in url and method == "POST":
            return _FakeResponse({"TransactionId": "nl-1"})
        if "nurselookup" in url and method == "GET":
            return _FakeResponse(_SAMPLE_PAYLOAD)
        if "changepassword" in url and method == "POST":
            self.change_password_body = json.loads(request.data.decode("utf-8"))
            return _FakeResponse({"TransactionId": "pw-1"})
        raise AssertionError(f"unexpected call {method} {url}")


def _credential() -> NursysCredential:
    return NursysCredential(
        api_url="https://api.example-nursys.com/v1",
        username="inst",
        password="oldpw",
    )


def test_client_rejects_non_https_url() -> None:
    with pytest.raises(NursysApiError):
        NursysClient(NursysCredential("http://x/y", "u", "p"))
    with pytest.raises(NursysApiError):
        NursysClient(NursysCredential("https://u:p@host/y", "u", "p"))


def test_client_notification_lookup_sends_both_dates_and_polls() -> None:
    from datetime import date

    transport = _FakeTransport()
    client = NursysClient(_credential(), opener=transport, sleep_fn=lambda _s: None)
    payload = client.notification_lookup(date(2026, 9, 1), date(2026, 9, 18))
    rows = list(iter_nurse_licenses(payload))
    assert len(rows) == 2
    methods = [m for m, _ in transport.calls]
    assert methods == ["POST", "GET"]  # exactly one submit and one poll
    # Both dates are required by the API (spec 3.5.1).
    assert transport.last_post_body == {"StartDate": "2026-09-01", "EndDate": "2026-09-18"}


def test_client_nurse_lookup_submits_batch_and_polls() -> None:
    transport = _FakeTransport()
    client = NursysClient(_credential(), opener=transport, sleep_fn=lambda _s: None)
    payload = client.nurse_lookup([{"NcsbnId": 99912345}])
    assert len(list(iter_nurse_licenses(payload))) == 2
    assert transport.last_post_body == {"NurseLookupRequests": [{"NcsbnId": 99912345}]}


def test_client_change_password_sends_new_password() -> None:
    transport = _FakeTransport()
    client = NursysClient(_credential(), opener=transport, sleep_fn=lambda _s: None)
    client.change_password("N3w-Str0ng!pw")
    assert transport.change_password_body == {"NewPassword": "N3w-Str0ng!pw"}


class _RateLimitTransport:
    def __call__(self, request, timeout=None):
        import urllib.error

        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)


def test_client_raises_rate_limited_on_403() -> None:
    client = NursysClient(_credential(), opener=_RateLimitTransport(), sleep_fn=lambda _s: None)
    with pytest.raises(NursysRateLimited):
        client.change_password("x")


# --------------------------------------------------------------------------- #
# Secret store
# --------------------------------------------------------------------------- #


def test_credential_json_round_trip() -> None:
    at = datetime(2026, 6, 1, tzinfo=UTC)
    cred = NursysCredential("https://h/x", "u", "p", password_set_at=at)
    parsed = NursysCredential.from_json(cred.to_json())
    assert parsed == cred


def test_credential_rotated_advances_timestamp() -> None:
    cred = NursysCredential("https://h/x", "u", "old")
    at = datetime(2026, 9, 1, tzinfo=UTC)
    rotated = cred.rotated("new", at=at)
    assert rotated.password == "new"
    assert rotated.password_set_at == at
    assert cred.password == "old"  # original is untouched (frozen)


def test_secret_store_put_then_get(tmp_path) -> None:
    store = SecretStore(root=tmp_path)
    cred = NursysCredential("https://h/x", "u", "p", password_set_at=datetime.now(UTC))
    store.put_nursys("nursys/acct_1", cred)
    assert store.get_nursys("nursys/acct_1") == cred


def test_secret_store_file_wins_over_env(tmp_path, monkeypatch) -> None:
    auth_ref = "nursys/acct_2"
    boot = NursysCredential("https://h/x", "u", "bootstrap")
    monkeypatch.setenv(env_var_for(auth_ref), boot.to_json())
    store = SecretStore(root=tmp_path)
    # Before any file exists, the env bootstrap resolves.
    assert store.get_nursys(auth_ref).password == "bootstrap"
    # After a rotation writes the file, the file wins.
    store.put_nursys(auth_ref, boot.rotated("rotated"))
    assert store.get_nursys(auth_ref).password == "rotated"


def test_secret_store_missing_raises(tmp_path) -> None:
    with pytest.raises(SecretError):
        SecretStore(root=tmp_path).get_nursys("nursys/absent")
