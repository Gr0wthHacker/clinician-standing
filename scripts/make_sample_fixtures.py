"""Write the synthetic sample roster and bulk-file fixtures under tests/fixtures/sample.

Everything here is invented. Names are placeholders ("SAMPLE", "TESTER"), PAC IDs
and enrollment IDs start with 99, and NPIs are generated with a valid check
digit (Luhn over the 80840 prefix) so they pass the same checks a real NPI
would, without belonging to anyone. Re-run after changing a row:

    python scripts/make_sample_fixtures.py

Two snapshots are written per source. ``v1`` is the first month. ``v2`` is the
next month: one clinician leaves one of two groups, another leaves the file, one revalidation due date moves, and
one new exclusion lands on a roster NPI. The end-to-end test runs v1, re-runs
v1 (which must report zero changes), then runs v2.
"""

from __future__ import annotations

import csv
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "sample"


def npi_with_check_digit(base9: str) -> str:
    """Append the NPI check digit (Luhn over ``80840`` + the first nine digits)."""
    digits = [int(d) for d in "80840" + base9]
    total = 0
    for index, digit in enumerate(reversed(digits)):
        if index % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return base9 + str((10 - total % 10) % 10)


# --------------------------------------------------------------------- roster
GROUP_A = "9900000001"  # SAMPLE FAMILY MEDICINE GROUP
GROUP_B = "9900000002"  # SAMPLE URGENT CARE LLC

ROSTER = [
    # key, base9, first, last, cred, specialty
    ("alpha", "199000001", "ALPHA", "SAMPLE", "MD", "FAMILY PRACTICE"),
    ("bravo", "199000002", "BRAVO", "SAMPLE", "DO", "INTERNAL MEDICINE"),
    ("charlie", "199000003", "CHARLIE", "TESTER", "NP", "NURSE PRACTITIONER"),
    ("delta", "199000004", "DELTA", "TESTER", "PA", "PHYSICIAN ASSISTANT"),
    ("echo", "199000005", "ECHO", "PLACEHOLDER", "", "NURSE PRACTITIONER"),
]
NPI = {key: npi_with_check_digit(base) for key, base, *_ in ROSTER}
IDX = {key: i for i, (key, *_) in enumerate(ROSTER)}
OUTSIDE_NPI = npi_with_check_digit("199000099")  # excluded, not on the roster

DAC_HEADER = [
    "NPI", "Ind_PAC_ID", "Ind_enrl_ID", "Provider Last Name", "Provider First Name",
    "Provider Middle Name", "suff", "gndr", "Cred", "Med_sch", "Grd_yr", "pri_spec",
    "sec_spec_1", "Telehlth", "Facility Name", "org_pac_id", "num_org_mem", "adr_ln_1",
    "adr_ln_2", "ln_2_sprs", "City/Town", "State", "ZIP Code", "Telephone Number",
    "ind_assgn", "grp_assgn", "adrs_id",
]  # fmt: skip

LOCATIONS = {
    GROUP_A: [
        ("100 SAMPLE ST", "SPRINGFIELD", "IL", "627010000", "2175550100"),
        ("200 EXAMPLE AVE", "SPRINGFIELD", "IL", "627020000", "2175550101"),
    ],
    GROUP_B: [("300 PLACEHOLDER RD", "SPRINGFIELD", "IL", "627030000", "2175550102")],
}
GROUP_NAME = {GROUP_A: "SAMPLE FAMILY MEDICINE GROUP", GROUP_B: "SAMPLE URGENT CARE LLC"}


def dac_rows(affiliations: list[tuple[str, str]]) -> list[dict[str, str]]:
    by_key = {r[0]: r for r in ROSTER}
    rows: list[dict[str, str]] = []
    for key, group in affiliations:
        _, _, first, last, cred, spec = by_key[key]
        members = sum(1 for _, g in affiliations if g == group)
        # One line per practice location, as CMS publishes it.
        for loc_index, (adr, city, state, zipc, phone) in enumerate(LOCATIONS[group]):
            rows.append(
                {
                    "NPI": NPI[key],
                    "Ind_PAC_ID": f"99100000{IDX[key]:02d}",
                    "Ind_enrl_ID": f"I9900000000{IDX[key]:04d}",
                    "Provider Last Name": last,
                    "Provider First Name": first,
                    "Provider Middle Name": "",
                    "suff": "",
                    "gndr": "",
                    "Cred": cred,
                    "Med_sch": "",
                    "Grd_yr": "",
                    "pri_spec": spec,
                    "sec_spec_1": "",
                    "Telehlth": "Y" if key == "alpha" else "",
                    "Facility Name": GROUP_NAME[group],
                    "org_pac_id": group,
                    "num_org_mem": str(members),
                    "adr_ln_1": adr,
                    "adr_ln_2": "",
                    "ln_2_sprs": "",
                    "City/Town": city,
                    "State": state,
                    "ZIP Code": zipc,
                    "Telephone Number": phone,
                    "ind_assgn": "Y",
                    "grp_assgn": "Y",
                    "adrs_id": f"IL{group[-3:]}{loc_index}",
                }
            )
    return rows


DAC_V1 = [
    ("alpha", GROUP_A),
    ("bravo", GROUP_A),
    ("charlie", GROUP_A),
    ("delta", GROUP_A),
    ("echo", GROUP_A),
    ("alpha", GROUP_B),
    ("charlie", GROUP_B),
]
# v2: charlie leaves GROUP_B but stays at GROUP_A, so that affiliation closes.
# delta leaves the file entirely, which by design does NOT close the affiliation
# (absence of a clinician is ambiguous; see CmsDacConnector.load).
DAC_V2 = [a for a in DAC_V1 if a not in {("charlie", GROUP_B), ("delta", GROUP_A)}]

# -------------------------------------------------------------------- LEIE
LEIE_HEADER = [
    "LASTNAME", "FIRSTNAME", "MIDNAME", "BUSNAME", "GENERAL", "SPECIALTY", "UPIN", "NPI",
    "DOB", "ADDRESS", "CITY", "STATE", "ZIP", "EXCLTYPE", "EXCLDATE", "REINDATE",
    "WAIVERDATE", "WVRSTATE",
]  # fmt: skip


def leie_row(**fields: str) -> dict[str, str]:
    row = dict.fromkeys(LEIE_HEADER, "")
    row.update({"NPI": "0000000000", "DOB": "", "REINDATE": "00000000",
                "WAIVERDATE": "00000000"})  # fmt: skip
    row.update(fields)
    return row


LEIE_V1 = [
    # Roster clinician charlie, excluded by NPI.
    leie_row(
        LASTNAME="TESTER",
        FIRSTNAME="CHARLIE",
        GENERAL="IND- LIC HC SERV PRO",
        SPECIALTY="NURSE/NURSE PRAC",
        NPI=NPI["charlie"],
        DOB="19700101",
        ADDRESS="1 FAKE LN",
        CITY="SPRINGFIELD",
        STATE="IL",
        ZIP="62701",
        EXCLTYPE="1128b4",
        EXCLDATE="20250115",
    ),
    # Excluded NPI that is not on the roster.
    leie_row(
        LASTNAME="OUTSIDER",
        FIRSTNAME="ZULU",
        GENERAL="IND- LIC HC SERV PRO",
        SPECIALTY="PHYSICIAN",
        NPI=OUTSIDE_NPI,
        DOB="19650202",
        ADDRESS="9 NOWHERE CT",
        CITY="SHELBYVILLE",
        STATE="IL",
        ZIP="62565",
        EXCLTYPE="1128a1",
        EXCLDATE="20240301",
    ),
    # No NPI, latin-1 name with a non-breaking space. Not screenable by NPI.
    leie_row(
        LASTNAME="PE\u00d1A\u00a0SAMPLE",
        FIRSTNAME="JOS\u00c9",
        GENERAL="OTHER BUSINESS",
        DOB="19800303",
        ADDRESS="5 EXAMPLE WAY",
        CITY="SPRINGFIELD",
        STATE="IL",
        ZIP="62704",
        EXCLTYPE="1128a2",
        EXCLDATE="20230610",
    ),
    # Business row, one name at two addresses.
    leie_row(
        BUSNAME="SAMPLE PHARMACY LLC",
        GENERAL="PHARMACY",
        ADDRESS="7 TEST BLVD",
        CITY="SPRINGFIELD",
        STATE="IL",
        ZIP="62701",
        EXCLTYPE="1128b8",
        EXCLDATE="20220901",
    ),
    leie_row(
        BUSNAME="SAMPLE PHARMACY LLC",
        GENERAL="PHARMACY",
        ADDRESS="8 TEST BLVD",
        CITY="SPRINGFIELD",
        STATE="IL",
        ZIP="62701",
        EXCLTYPE="1128b8",
        EXCLDATE="20220901",
    ),
]
# v2: a new exclusion for roster clinician echo.
LEIE_V2 = [
    *LEIE_V1,
    leie_row(
        LASTNAME="PLACEHOLDER",
        FIRSTNAME="ECHO",
        GENERAL="IND- LIC HC SERV PRO",
        SPECIALTY="NURSE/NURSE PRAC",
        NPI=NPI["echo"],
        DOB="19750505",
        ADDRESS="3 FAKE LN",
        CITY="SPRINGFIELD",
        STATE="IL",
        ZIP="62701",
        EXCLTYPE="1128b7",
        EXCLDATE="20260915",
    ),
]

# ------------------------------------------------------------ revalidation
REVAL_HEADER = [
    "Group PAC ID", "Group Enrollment ID", "Group Legal Business Name", "Group State Code",
    "Group Due Date", "Group Reassignments and Physician Assistants", "Record Type",
    "Individual Enrollment ID", "Individual NPI", "Individual First Name",
    "Individual Last Name", "Individual State Code", "Individual Specialty Description",
    "Individual Due Date", "Individual Total Employer Associations",
]  # fmt: skip


def reval_rows(
    due: dict[tuple[str, str], str], affiliations: list[tuple[str, str]]
) -> list[dict[str, str]]:
    by_key = {r[0]: r for r in ROSTER}
    rows = []
    for key, group in affiliations:
        _, _, first, last, _, spec = by_key[key]
        members = sum(1 for _, g in affiliations if g == group)
        employers = sum(1 for k, _ in affiliations if k == key)
        rows.append(
            {
                "Group PAC ID": group,
                "Group Enrollment ID": f"O99000000000{group[-1]}",
                "Group Legal Business Name": GROUP_NAME[group],
                "Group State Code": "IL",
                "Group Due Date": "12/31/2027",
                "Group Reassignments and Physician Assistants": str(members),
                "Record Type": "Reassignment",
                "Individual Enrollment ID": f"I9900000000{IDX[key]:04d}",
                "Individual NPI": NPI[key],
                "Individual First Name": first,
                "Individual Last Name": last,
                "Individual State Code": "IL",
                "Individual Specialty Description": spec.title(),
                "Individual Due Date": due.get((key, group), "TBD"),
                "Individual Total Employer Associations": str(employers),
            }
        )
    return rows


DUE_V1 = {
    ("alpha", GROUP_A): "03/31/2027",
    ("bravo", GROUP_A): "01/31/2025",  # past due
    ("charlie", GROUP_A): "06/30/2027",
    ("delta", GROUP_A): "09/30/2027",
    # echo/GROUP_A left as TBD
    ("alpha", GROUP_B): "03/31/2027",
    ("charlie", GROUP_B): "06/30/2027",
}
DUE_V2 = {**DUE_V1, ("bravo", GROUP_A): "01/31/2028"}  # bravo revalidated


def write(path: Path, header: list[str], rows: list[dict[str, str]], encoding: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    write(OUT / "v1" / "cms_dac.csv", DAC_HEADER, dac_rows(DAC_V1), "utf-8-sig")
    write(OUT / "v2" / "cms_dac.csv", DAC_HEADER, dac_rows(DAC_V2), "utf-8-sig")
    write(OUT / "v1" / "oig_leie.csv", LEIE_HEADER, LEIE_V1, "latin-1")
    write(OUT / "v2" / "oig_leie.csv", LEIE_HEADER, LEIE_V2, "latin-1")
    write(OUT / "v1" / "cms_revalidation.csv", REVAL_HEADER, reval_rows(DUE_V1, DAC_V1), "latin-1")
    write(OUT / "v2" / "cms_revalidation.csv", REVAL_HEADER, reval_rows(DUE_V2, DAC_V2), "latin-1")
    with (OUT / "roster.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["npi", "first_name", "last_name", "credential", "org_pac_id"])
        for key, group in DAC_V1:
            r = next(x for x in ROSTER if x[0] == key)
            writer.writerow([NPI[key], r[2], r[3], r[4], group])
    print(f"wrote fixtures to {OUT}")
    for key, npi in NPI.items():
        print(f"  {key:8s} {npi}")


if __name__ == "__main__":
    main()
