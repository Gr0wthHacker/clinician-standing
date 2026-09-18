"""The free roster audit (PRD section 9).

Most of what matters here is wording, not arithmetic. The audit is a sales
artifact that a prospect may act on, and the single worst thing it can do is
report a roster as clean when it has been screened against roughly a tenth of
the OIG exclusion file. The exclusion-caveat tests below exist to make that
failure impossible to introduce quietly: they assert that the sentence always
carries the unscreened count and always refuses the stronger claim.

Everything else -- roster counts, revalidation arithmetic, the two-federal-file
disagreement -- is checked against a seeded practice. Those tests are marked
``database`` and are deselected in CI, like the rest of the suite.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime

import pytest

from clinician_standing import audit
from conftest import database_url

# ---------------------------------------------------------------------------
# Seed: one practice, as the three working connectors would leave it
# ---------------------------------------------------------------------------

#: The audit is computed against this date so every day count in the
#: assertions below is a constant, not a function of when the suite runs.
AS_OF = date(2026, 9, 18)

ORG_PAC_ID = "4183920157"
OTHER_ORG_PAC_ID = "7720041183"

PRACTICE_ID = "aaaaaaaa-0000-4000-8000-0000000000a1"
OTHER_PRACTICE_ID = "aaaaaaaa-0000-4000-8000-0000000000a2"
DAC_EVIDENCE_ID = "11111111-1111-4111-8111-1111111111a1"
REVAL_EVIDENCE_ID = "22222222-2222-4222-8222-2222222222a1"
LEIE_EVIDENCE_ID = "33333333-3333-4333-8333-3333333333a1"

#: Twelve on the roster plus one who left. (npi, first, last, credential, type, specialty)
ROSTER: tuple[tuple[str, str, str, str, str, str], ...] = (
    ("1003819472", "MARGARET", "OKONKWO", "MD", "physician", "FAMILY PRACTICE"),
    ("1114920583", "DAVID", "HALVORSEN", "MD", "physician", "INTERNAL MEDICINE"),
    ("1225031694", "PRIYA", "RAMASWAMY", "DO", "physician", "FAMILY PRACTICE"),
    ("1336142705", "THOMAS", "BERGSTROM", "MD", "physician", "GERIATRIC MEDICINE"),
    ("1447253816", "ANNE", "LINDQUIST", "MD", "physician", "FAMILY PRACTICE"),
    ("1558364927", "JAMAL", "WHITFIELD", "DO", "physician", "SPORTS MEDICINE"),
    ("1669476038", "SOFIA", "CASTELLANOS", "MD", "physician", "INTERNAL MEDICINE"),
    ("1770587149", "ERIN", "DAHLBERG", "NP", "np", "NURSE PRACTITIONER"),
    ("1881698250", "KEVIN", "MATSUDA", "NP", "np", "NURSE PRACTITIONER"),
    ("1992709361", "RACHEL", "OYELARAN", "PA", "pa", "PHYSICIAN ASSISTANT"),
    ("1203810472", "BRIAN", "NDIAYE", "CRNA", "crna", "CRNA"),
    ("1314921583", "HELENA", "SVOBODA", "CSW", "other", "CLINICAL SOCIAL WORKER"),
)

#: Affiliation closed in February, but the revalidation file still reassigns
#: her billing rights to the group. That mismatch is a finding in its own right.
DEPARTED = ("1425032694", "LOUISE", "ABARA", "MD", "physician", "INTERNAL MEDICINE")

#: (npi, status, revalidation_due). Three roster lapses plus the departed one.
ENROLLMENTS: tuple[tuple[str, str, date | None], ...] = (
    ("1003819472", "revalidation_due", date(2025, 7, 31)),  # 414 days over
    ("1114920583", "revalidation_due", date(2026, 5, 31)),  # 110 days over
    ("1225031694", "revalidation_due", date(2026, 8, 31)),  # 18 days over, inside 30
    ("1336142705", "approved", date(2026, 10, 31)),  # due in 43
    ("1447253816", "approved", date(2027, 1, 31)),  # due in 135
    ("1558364927", "approved", date(2027, 6, 30)),
    ("1669476038", "approved", date(2027, 8, 31)),
    ("1770587149", "approved", date(2028, 3, 31)),
    ("1881698250", "approved", None),  # CMS wrote TBD
    ("1992709361", "approved", date(2027, 11, 30)),
    ("1203810472", "approved", date(2028, 1, 31)),
    ("1425032694", "revalidation_due", date(2026, 4, 30)),  # departed, still reassigning
)
#: Deliberately absent from ENROLLMENTS: 1314921583. CMS lists her at the group
#: in the directory file and nowhere in the reassignment file.
DIRECTORY_ONLY_NPI = "1314921583"

#: The real LEIE numbers: 84,001 rows, 8,701 of them carrying an NPI.
LEIE_ROWS_TOTAL = 84_001
LEIE_ROWS_WITH_NPI = 8_701
LEIE_ROWS_UNSCREENED = LEIE_ROWS_TOTAL - LEIE_ROWS_WITH_NPI


def _seed_statements() -> list[tuple[str, dict]]:
    """Every statement that builds the seeded practice, in dependency order."""
    out: list[tuple[str, dict]] = []
    evidence = """
        insert into evidence (id, source_key, fetched_at, request_ref, payload_ref,
                              payload_sha256, parsed, match_keys, freshness_expires_at)
        values (%(id)s, %(source_key)s, %(fetched_at)s, %(request_ref)s, %(payload_ref)s,
                %(sha)s, %(parsed)s, %(match_keys)s, %(expires)s)
    """
    out.append(
        (
            evidence,
            {
                "id": DAC_EVIDENCE_ID,
                "source_key": "cms_dac",
                # 61 days before AS_OF: past the 45-day freshness limit, so the
                # directory record in this audit is stale and has to say so.
                "fetched_at": datetime(2026, 7, 19, 4, 12, tzinfo=UTC),
                "request_ref": "https://data.cms.gov/.../DAC_NationalDownloadableFile.csv",
                "payload_ref": "cms_dac/2026-07-19/dac.csv",
                "sha": "a1" * 32,
                "parsed": '{"dataset": "mj5m-pzi6", "rows_after_dedupe": 2884120}',
                "match_keys": '{"npi": "exact", "org_pac_id": "exact"}',
                "expires": datetime(2026, 9, 2, 4, 12, tzinfo=UTC),
            },
        )
    )
    out.append(
        (
            evidence,
            {
                "id": REVAL_EVIDENCE_ID,
                "source_key": "cms_revalidation",
                "fetched_at": datetime(2026, 9, 8, 3, 40, tzinfo=UTC),
                "request_ref": "https://data.cms.gov/.../Revalidation_Group_Reassignment.csv",
                "payload_ref": "cms_revalidation/2026-09-08/reval.csv",
                "sha": "b2" * 32,
                "parsed": '{"rows_read": 3392044, "encoding": "latin-1"}',
                "match_keys": '{"individual_npi": "exact", "group_pac_id": "exact"}',
                "expires": datetime(2026, 10, 23, 3, 40, tzinfo=UTC),
            },
        )
    )
    out.append(
        (
            evidence,
            {
                "id": LEIE_EVIDENCE_ID,
                "source_key": "oig_leie",
                "fetched_at": datetime(2026, 9, 6, 2, 5, tzinfo=UTC),
                "request_ref": "https://oig.hhs.gov/exclusions/downloadables/UPDATED.csv",
                "payload_ref": "oig_leie/2026-09-06/UPDATED.csv",
                "sha": "c3" * 32,
                "parsed": (
                    f'{{"rows_total": {LEIE_ROWS_TOTAL}, '
                    f'"rows_with_npi": {LEIE_ROWS_WITH_NPI}, '
                    f'"npi_coverage": 0.1036, "name_dob_matching_enabled": false}}'
                ),
                "match_keys": '{"npi": "exact"}',
                "expires": datetime(2026, 10, 21, 2, 5, tzinfo=UTC),
            },
        )
    )

    practice = """
        insert into practices (id, org_pac_id, legal_name, address_line1, address_line2,
                               city, state, zip, phone, client_status)
        values (%(id)s, %(pac)s, %(name)s, %(a1)s, %(a2)s, %(city)s, %(state)s,
                %(zip)s, %(phone)s, %(status)s)
    """
    out.append(
        (
            practice,
            {
                "id": PRACTICE_ID,
                "pac": ORG_PAC_ID,
                "name": "Northshore Family Medicine LLC",
                "a1": "2250 COUNTY ROAD B",
                "a2": "SUITE 140",
                "city": "ROSEVILLE",
                "state": "MN",
                "zip": "551131820",
                "phone": "6516338800",
                "status": "prospect",
            },
        )
    )
    out.append(
        (
            practice,
            {
                "id": OTHER_PRACTICE_ID,
                "pac": OTHER_ORG_PAC_ID,
                "name": "Lakeshore Urgent Care PC",
                "a1": "18 HARBOR VIEW DR",
                "a2": None,
                "city": "SUPERIOR",
                "state": "WI",
                "zip": "548802214",
                "phone": "7153940120",
                "status": None,
            },
        )
    )

    clinician = """
        insert into clinicians (npi, first_name, last_name, credential, clinician_type,
                                primary_specialty)
        values (%(npi)s, %(first)s, %(last)s, %(cred)s, %(type)s, %(spec)s)
    """
    for npi, first, last, cred, kind, spec in (*ROSTER, DEPARTED):
        out.append(
            (
                clinician,
                {
                    "npi": npi,
                    "first": first,
                    "last": last,
                    "cred": cred,
                    "type": kind,
                    "spec": spec,
                },
            )
        )

    affiliation = """
        insert into affiliations (clinician_id, practice_id, start_date, end_date, is_billing)
        select id, %(practice_id)s, %(start)s, %(end)s, true from clinicians where npi = %(npi)s
    """
    for npi, *_ in ROSTER:
        out.append(
            (
                affiliation,
                {"practice_id": PRACTICE_ID, "start": None, "end": None, "npi": npi},
            )
        )
    out.append(
        (
            affiliation,
            {
                "practice_id": PRACTICE_ID,
                "start": date(2016, 6, 1),
                "end": date(2026, 2, 28),
                "npi": DEPARTED[0],
            },
        )
    )
    # CMS also lists one of the roster at a second practice, in another state.
    out.append(
        (
            affiliation,
            {
                "practice_id": OTHER_PRACTICE_ID,
                "start": None,
                "end": None,
                "npi": "1558364927",
            },
        )
    )

    # The group's own revalidation, overdue. The cms_revalidation connector does
    # not derive this row today; the audit reads it where it exists and says so
    # where it does not, and this seed exercises the first branch.
    out.append(
        (
            """
            insert into enrollments (clinician_id, practice_id, payer, status,
                                     revalidation_due, evidence_id, verified_at)
            values (null, %(practice_id)s, 'medicare', 'revalidation_due', %(due)s,
                    %(evidence_id)s, %(verified_at)s)
            """,
            {
                "practice_id": PRACTICE_ID,
                "due": date(2025, 11, 30),
                "evidence_id": REVAL_EVIDENCE_ID,
                "verified_at": datetime(2026, 9, 8, 3, 58, tzinfo=UTC),
            },
        )
    )
    for npi, status, due in ENROLLMENTS:
        out.append(
            (
                """
                insert into enrollments (clinician_id, practice_id, payer, status,
                                         revalidation_due, evidence_id, verified_at)
                select id, %(practice_id)s, 'medicare', %(status)s, %(due)s,
                       %(evidence_id)s, %(verified_at)s
                from clinicians where npi = %(npi)s
                """,
                {
                    "practice_id": PRACTICE_ID,
                    "status": status,
                    "due": due,
                    "evidence_id": REVAL_EVIDENCE_ID,
                    "verified_at": datetime(2026, 9, 8, 3, 58, tzinfo=UTC),
                    "npi": npi,
                },
            )
        )
    return out


EXCLUSION_STATEMENT = """
    insert into sanctions (clinician_id, source, action_type, action_date, description,
                           match_confidence, evidence_id)
    select id, 'leie', '1128b4', date '2024-03-15', 'LICENSE REVOCATION', 1.0, %(evidence_id)s
    from clinicians where npi = %(npi)s
"""


@pytest.fixture
def seeded():
    """A connection holding the seeded practice, rolled back afterwards.

    The seed lives inside one explicit transaction that is always rolled back,
    so the suite leaves no rows behind and can be run repeatedly against the
    same database. ``autocommit=True`` plus an explicit BEGIN is deliberate: it
    puts the transaction boundary in this fixture rather than in the driver's
    implicit one, so the rollback is unambiguous.

    Skips only when TEST_DATABASE_URL is unset, which is an environment fact.
    A driver that will not import or a schema that is not there is an error.
    """
    import psycopg

    url = database_url()
    if url is None:
        pytest.skip("TEST_DATABASE_URL is not set")
    conn = psycopg.connect(url, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("begin")
            for statement, params in _seed_statements():
                cur.execute(statement, params)
        yield conn
    finally:
        try:
            with conn.cursor() as cur:
                cur.execute("rollback")
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# The exclusion caveat. No database; this is the part that must never regress.
# ---------------------------------------------------------------------------


def _screen(**overrides):
    """An :class:`ExclusionScreen` with the real LEIE proportions by default."""
    defaults = {
        "roster_size": 12,
        "leie_screened": True,
        "leie_records_total": LEIE_ROWS_TOTAL,
        "leie_records_with_npi": LEIE_ROWS_WITH_NPI,
        "leie_records_unscreened": LEIE_ROWS_UNSCREENED,
        "leie_name_dob_enabled": False,
        "leie_source": _source_state("oig_leie"),
        "sam_screened": False,
        "sam_source": _source_state("sam_gov", fetched=None, enabled=False),
        "hits": (),
    }
    defaults.update(overrides)
    return audit.ExclusionScreen(**defaults)


def _source_state(key, fetched=datetime(2026, 9, 6, 2, 5, tzinfo=UTC), enabled=True, stale=False):
    return audit.SourceState(
        key=key,
        display_name=key.upper(),
        cadence="monthly",
        freshness_sla_days=45,
        enabled=enabled,
        is_primary_source=True,
        fetched_at=fetched,
        expires_at=None,
        stale=stale,
        age_days=12 if fetched else None,
        last_run_at=fetched,
        last_run_status="ok" if fetched else None,
        parsed={},
    )


def test_clean_screen_states_the_unscreened_denominator():
    """A clean screen names how much of the file it could not match."""
    text = audit.exclusion_caveat(_screen())
    assert "75,300" in text
    assert "84,001" in text
    assert "carry no NPI and were not screened" in text


def test_clean_screen_refuses_the_stronger_claim():
    """It must never read as 'no exclusions'. This is the whole point."""
    text = audit.exclusion_caveat(_screen())
    assert "It does not mean that no clinician on this roster is excluded." in text
    assert "NPI matching is the only matching performed." in text
    # The bare claim, in any of the forms a careless edit would produce.
    lowered = text.lower()
    for forbidden in ("no exclusions found.", "roster is clear", "no exclusions.", "all clear"):
        assert forbidden not in lowered


def test_clean_screen_names_the_disabled_matching_mode():
    """Name+DOB matching being off is the reason for the gap, so it is stated."""
    assert "name-and-date-of-birth matching is not enabled" in audit.exclusion_caveat(_screen())


def test_caveat_survives_missing_file_statistics():
    """With no row counts recorded, the caveat says so rather than going quiet."""
    text = audit.exclusion_caveat(
        _screen(leie_records_total=None, leie_records_with_npi=None, leie_records_unscreened=None)
    )
    assert "could not be quantified" in text
    assert "It does not mean that no clinician on this roster is excluded." in text


def test_caveat_when_the_screen_never_ran():
    """No evidence row means no screen, and the wording must not imply one."""
    text = audit.exclusion_caveat(_screen(leie_screened=False, leie_source=None))
    assert "was not run" in text
    assert "not the absence of an exclusion" in text


def test_caveat_with_a_hit_still_refuses_to_clear_the_rest():
    """A hit does not turn the other eleven into a cleared roster."""
    hit = audit.ExclusionRow(
        clinician=audit.ClinicianRef("1003819472", "Margaret Okonkwo, MD", "MD", "physician", None),
        source="leie",
        action_type="1128b4",
        action_date=date(2024, 3, 15),
        description="LICENSE REVOCATION",
        reinstated_date=None,
        match_confidence=1.0,
        evidence_source_key="oig_leie",
        evidence_fetched_at=datetime(2026, 9, 6, tzinfo=UTC),
    )
    text = audit.exclusion_caveat(_screen(hits=(hit,)))
    assert "matched an open OIG exclusion by NPI" in text
    assert "an NPI match is the only kind this screen can make" in text
    # Capitalisation of the source names must survive the sentence assembly.
    assert "OIG LEIE" in text
    assert "oig leie" not in text


def test_stale_leie_snapshot_is_disclosed_in_the_caveat():
    """Screening a stale file is not the same as screening the current one."""
    text = audit.exclusion_caveat(_screen(leie_source=_source_state("oig_leie", stale=True)))
    assert "past this system's 45-day freshness limit" in text
    assert "exclusions published since then are not represented" in text


def test_sam_caveat_names_the_unscreened_roster():
    """SAM.gov has no connector, so every clinician is unscreened against it."""
    text = audit.sam_caveat(_screen())
    assert "was not performed" in text
    assert "12 clinicians" in text
    assert "debarred government-wide without appearing on the OIG list" in text


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("551131820", "55113-1820"), ("55113", "55113"), (None, ""), ("", "")],
)
def test_zip_formatting(raw, expected):
    assert audit.format_zip(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("6516338800", "(651) 633-8800"), ("651633", "651633"), (None, "")],
)
def test_phone_formatting(raw, expected):
    assert audit.format_phone(raw) == expected


def test_findings_sort_worst_first():
    """Severity leads; inside a severity, emission order decides.

    Not the size of the number: the quantities are in different units, and a
    292-day overdue revalidation must not outrank one clinician matched to an
    exclusion just because 292 is larger than 1.
    """

    def finding(key, severity, quantity, rank):
        return audit.Finding(
            key=key,
            severity=severity,
            title=key,
            detail="",
            source_keys=(),
            citations=(),
            quantity=quantity,
            rank=rank,
        )

    unordered = [
        finding("low", audit.Severity.LOW, 9, 4),
        finding("critical_small_number", audit.Severity.CRITICAL, 1, 0),
        finding("critical_big_number", audit.Severity.CRITICAL, 292, 1),
        finding("not_assessed", audit.Severity.NOT_ASSESSED, 100, 5),
        finding("medium", audit.Severity.MEDIUM, 2, 2),
    ]
    ordered = [f.key for f in sorted(unordered, key=lambda f: f.sort_key)]
    assert ordered == [
        "critical_small_number",
        "critical_big_number",
        "medium",
        "low",
        "not_assessed",
    ]


# ---------------------------------------------------------------------------
# End to end, against a seeded practice
# ---------------------------------------------------------------------------


@pytest.mark.database
def test_unknown_practice_raises_rather_than_returning_an_empty_audit(seeded):
    """An audit of a practice nobody ingested is a failure, not a clean sheet."""
    with pytest.raises(audit.PracticeNotFound):
        audit.audit_practice("0000000000", conn=seeded, as_of=AS_OF)


@pytest.mark.database
def test_roster_counts_exclude_closed_affiliations(seeded):
    result = audit.audit_practice(ORG_PAC_ID, conn=seeded, as_of=AS_OF)
    assert result.roster.total == len(ROSTER)
    assert result.roster.physicians == 7
    assert result.roster.non_physicians == 5
    assert result.roster.by_type["np"] == 2
    assert result.roster.distinct_specialties == 8
    assert {state for state, _ in result.roster.states} == {"MN", "WI"}
    assert DEPARTED[0] not in {row.clinician.npi for row in result.enrollment.rows if row.on_roster}


@pytest.mark.database
def test_telehealth_is_reported_as_not_assessed_not_as_zero(seeded):
    """The ingest reads the flag and drops it; a zero here would be a lie."""
    result = audit.audit_practice(ORG_PAC_ID, conn=seeded, as_of=AS_OF)
    assert result.roster.telehealth_assessed is False
    assert result.roster.telehealth_count is None
    assert "does not retain it" in result.roster.telehealth_note


@pytest.mark.database
def test_group_revalidation_overdue_is_the_worst_finding(seeded):
    result = audit.audit_practice(ORG_PAC_ID, conn=seeded, as_of=AS_OF)
    assert result.enrollment.group_due_date == date(2025, 11, 30)
    assert result.enrollment.group_days_overdue == (AS_OF - date(2025, 11, 30)).days
    assert result.worst_severity is audit.Severity.CRITICAL
    assert result.findings[0].key == "group_revalidation_overdue"


@pytest.mark.database
def test_retrospective_billing_window_is_applied_per_clinician(seeded):
    """42 CFR 424.521 caps recovery at 30 days; the rest is quantified exposure."""
    result = audit.audit_practice(ORG_PAC_ID, conn=seeded, as_of=AS_OF)
    by_npi = {row.clinician.npi: row for row in result.enrollment.overdue}
    assert set(by_npi) == {"1003819472", "1114920583", "1225031694", DEPARTED[0]}

    longest = by_npi["1003819472"]
    assert longest.days_overdue == (AS_OF - date(2025, 7, 31)).days
    assert longest.unbillable_days == longest.days_overdue - audit.RETROSPECTIVE_BILLING_DAYS

    # 18 days past due sits entirely inside the 30-day window: nothing is lost.
    inside = by_npi["1225031694"]
    assert inside.days_overdue == 18
    assert inside.unbillable_days == 0

    assert result.enrollment.total_unbillable_days == sum(
        row.unbillable_days for row in result.enrollment.overdue
    )


@pytest.mark.database
def test_due_soon_and_no_due_date_are_separated(seeded):
    result = audit.audit_practice(ORG_PAC_ID, conn=seeded, as_of=AS_OF)
    assert {row.clinician.npi for row in result.enrollment.due_soon} == {"1336142705", "1447253816"}
    assert {row.clinician.npi for row in result.enrollment.no_due_date} == {"1881698250"}


@pytest.mark.database
def test_disagreement_between_two_federal_files_is_reported_both_ways(seeded):
    """Neither file is treated as right; the disagreement is the finding."""
    result = audit.audit_practice(ORG_PAC_ID, conn=seeded, as_of=AS_OF)
    assert [c.npi for c in result.enrollment.unenrolled] == [DIRECTORY_ONLY_NPI]
    assert [c.npi for c in result.enrollment.unaffiliated] == [DEPARTED[0]]
    keys = {f.key for f in result.findings}
    assert "roster_source_disagreement_missing_enrollment" in keys
    assert "roster_source_disagreement_missing_directory" in keys


@pytest.mark.database
def test_stale_directory_snapshot_is_flagged(seeded):
    """The DAC evidence is 61 days old against a 45-day limit."""
    result = audit.audit_practice(ORG_PAC_ID, conn=seeded, as_of=AS_OF)
    assert result.directory.stale is True
    assert "freshness limit" in (result.directory.stale_note or "")
    assert "directory_stale" in {f.key for f in result.findings}


@pytest.mark.database
def test_second_cms_listing_is_reported(seeded):
    result = audit.audit_practice(ORG_PAC_ID, conn=seeded, as_of=AS_OF)
    listings = result.directory.other_listings
    assert [listing.clinician.npi for listing in listings] == ["1558364927"]
    assert listings[0].state == "WI"


@pytest.mark.database
def test_every_finding_carries_a_source_or_says_it_has_none(seeded):
    """A compliance artifact with an uncited assertion is worse than useless."""
    result = audit.audit_practice(ORG_PAC_ID, conn=seeded, as_of=AS_OF)
    assert result.findings
    for finding in result.findings:
        assert len(finding.source_keys) == len(finding.citations)
        for citation in finding.citations:
            # Either a fetch date or an explicit statement that there is none.
            assert "fetched 20" in citation or "never ingested" in citation
        if not finding.citations:
            assert finding.severity is audit.Severity.NOT_ASSESSED


@pytest.mark.database
def test_clean_roster_produces_no_exclusion_hits_but_a_not_assessed_finding(seeded):
    result = audit.audit_practice(ORG_PAC_ID, conn=seeded, as_of=AS_OF)
    assert result.exclusions.hits == ()
    coverage = next(f for f in result.findings if f.key == "exclusion_coverage")
    assert coverage.severity is audit.Severity.NOT_ASSESSED
    assert coverage.quantity == LEIE_ROWS_UNSCREENED


@pytest.mark.database
def test_an_exclusion_hit_becomes_the_first_finding(seeded):
    """A matched exclusion outranks an overdue group revalidation."""
    with seeded.cursor() as cur:
        cur.execute(EXCLUSION_STATEMENT, {"evidence_id": LEIE_EVIDENCE_ID, "npi": "1003819472"})
    result = audit.audit_practice(ORG_PAC_ID, conn=seeded, as_of=AS_OF)
    assert len(result.exclusions.open_hits) == 1
    assert result.findings[0].key == "exclusion_hit"
    assert result.findings[0].severity is audit.Severity.CRITICAL
    assert "1003819472" in result.findings[0].detail


@pytest.mark.database
@pytest.mark.parametrize("renderer", ["render_markdown", "render_html", "render_json"])
def test_every_format_carries_the_caveat_and_the_fetch_dates(seeded, renderer):
    result = audit.audit_practice(ORG_PAC_ID, conn=seeded, as_of=AS_OF)
    document = getattr(audit, renderer)(result)
    assert "75,300" in document or "75300" in document
    assert "2026-09-06" in document  # the LEIE snapshot date
    assert "2026-07-19" in document  # the directory snapshot date
    assert "42 CFR 424.521(a)" in document


@pytest.mark.database
def test_html_is_self_contained_and_has_no_script(seeded):
    result = audit.audit_practice(ORG_PAC_ID, conn=seeded, as_of=AS_OF)
    document = audit.render_html(result)
    assert document.startswith("<!doctype html>")
    assert "<style>" in document
    assert "<script" not in document.lower()
    # Only the web-font stylesheet may be external; nothing else is fetched, so
    # the page renders offline and prints the same either way.
    hosts = set(re.findall(r"https?://([^/\"']+)", document))
    assert hosts <= {"fonts.googleapis.com", "fonts.gstatic.com"}, hosts


@pytest.mark.database
def test_json_round_trips(seeded):
    result = audit.audit_practice(ORG_PAC_ID, conn=seeded, as_of=AS_OF)
    payload = json.loads(audit.render_json(result))
    assert payload["org_pac_id"] == ORG_PAC_ID
    assert payload["summary"]["roster_size"] == len(ROSTER)
    assert payload["summary"]["retrospective_billing_citation"] == "42 CFR 424.521(a)"
    assert payload["exclusions"]["leie_records_unscreened"] == LEIE_ROWS_UNSCREENED
    assert "It does not mean" in payload["exclusions"]["caveat"]
