"""SQL generation in openlending.transform, run on tiny hand-made inputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from openlending.db import lit
from openlending.schema import HMDA_LAR, HMDA_LAR_RAW_COLUMNS
from openlending.transform import (
    core_2018_select,
    historic_core_select,
    int_expr,
    label_case,
    typed_select,
)

DEFAULTS: dict[str, str] = {
    "activity_year": "2023",
    "lei": "549300abcdefghijkl12",
    "derived_msa_md": "40140",
    "state_code": "CA",
    "county_code": "06071",
    "census_tract": "06071009709",
    "conforming_loan_limit": "C",
    "action_taken": "1",
    "purchaser_type": "71",
    "preapproval": "2",
    "loan_type": "1",
    "loan_purpose": "32",
    "lien_status": "1",
    "loan_amount": "205000",
    "combined_loan_to_value_ratio": "Exempt",
    "rate_spread": "1.6",
    "loan_term": "360.0",
    "income": "NA",
    "total_units": "1",
    "construction_method": "2",
    "occupancy_type": "3",
    "applicant_race_1": "22",
    "co_applicant_race_1": "8",
    "applicant_ethnicity_1": "12",
    "co_applicant_ethnicity_1": "5",
    "applicant_sex": "2",
    "co_applicant_sex": "5",
    "tract_minority_population_percent": "36.28000000001",
    "denial_reason_1": "10",
}


def _staged(con: duckdb.DuckDBPyConnection, rows: list[dict[str, str]]) -> str:
    cols = HMDA_LAR_RAW_COLUMNS
    con.execute("CREATE TABLE raw (" + ", ".join(f'"{c}" VARCHAR' for c in cols) + ")")
    for r in rows:
        # read_csv turns empty fields into NULL, so missing values are NULL here too.
        values = [r.get(c, DEFAULTS.get(c)) for c in cols]
        con.execute(f"INSERT INTO raw VALUES ({', '.join('?' for _ in cols)})", values)
    return "(SELECT *, row_number() OVER () - 1 AS file_row_number FROM raw)"


def _one(con: duckdb.DuckDBPyConnection, sql: str) -> dict[str, Any]:
    cur = con.execute(sql)
    names = [d[0] for d in cur.description or []]
    row = cur.fetchone()
    assert row is not None
    return dict(zip(names, row, strict=True))


def test_typed_select_handles_sentinels_and_labels() -> None:
    con = duckdb.connect()
    rel = _staged(con, [{}])
    exprs = typed_select(HMDA_LAR, record_id_expr="file_row_number + 1")
    r = _one(con, f"SELECT {', '.join(exprs)} FROM {rel}")
    assert r["record_id"] == 1
    assert r["lei"] == "549300ABCDEFGHIJKL12"  # upper-cased
    assert r["loan_amount"] == 205000.0
    assert r["combined_loan_to_value_ratio"] is None
    assert r["combined_loan_to_value_ratio_na_reason"] == "Exempt"
    assert r["income"] is None and r["income_na_reason"] == "NA"
    assert r["loan_term"] == 360 and r["loan_term_na_reason"] is None
    assert r["action_taken_label"] == "Loan originated"
    assert r["loan_purpose"] == 32 and r["loan_purpose_label"] == "Cash-out refinancing"
    assert r["aus_1"] is None and r["aus_1_label"] is None
    assert r["tract_minority_population_percent"] == 36.28000000001


def test_int_expr() -> None:
    con = duckdb.connect()
    got = con.execute(
        "SELECT " + ", ".join(int_expr(lit(v)) for v in ("360", "360.0", "360.5", "x"))
    ).fetchone()
    assert got == (360, 360, None, None)  # 360.5 is not rounded
    assert con.execute(f"SELECT {label_case('2', {1: 'a', 2: 'b'})}").fetchone() == ("b",)


def test_core_mapping_2018(tmp_path: Path) -> None:
    con = duckdb.connect()
    rel = _staged(
        con,
        [
            {},
            {
                "state_code": "TX",
                "county_code": "NA",
                "census_tract": "NA",
                "action_taken": "3",
                "lien_status": "2",
                "rate_spread": "NA",
            },
        ],
    )
    exprs = typed_select(HMDA_LAR, record_id_expr="file_row_number + 1")
    con.execute(f"CREATE TABLE lar AS SELECT {', '.join(exprs)} FROM {rel}")
    con.execute(
        "CREATE TABLE ts AS SELECT '549300ABCDEFGHIJKL12' AS lei, 9::SMALLINT AS agency_code"
    )
    rows = con.execute(f"SELECT * FROM ({core_2018_select('lar', 'ts')}) ORDER BY record_id")
    names = [d[0] for d in rows.description or []]
    a, b = (dict(zip(names, r, strict=True)) for r in rows.fetchall())
    assert a["loan_purpose"] == 3  # cash-out refinance -> refinance
    assert a["loan_purpose_label"] == "Refinancing (including cash-out)"
    assert a["purchaser_type"] == 7  # 71 -> 7
    assert a["applicant_race_1"] == 2  # Chinese -> Asian
    assert a["applicant_ethnicity"] == 1  # Puerto Rican -> Hispanic or Latino
    assert a["occupancy"] == 2  # investment -> not principal residence
    assert a["property_type"] == 2  # 1 unit, manufactured
    assert a["denial_reason_1"] is None  # 10 (not applicable) -> NULL
    assert a["derived_race"] == "Asian"
    assert a["derived_sex"] == "Female"
    assert a["higher_priced"] is True  # 1.6 >= 1.5 on a first lien
    assert a["agency_code"] == 9 and a["state_fips"] == "06"
    assert b["state_fips"] == "48" and b["county_fips"] is None
    assert b["higher_priced"] is None  # not originated


def test_historic_core_select() -> None:
    con = duckdb.connect()
    cols = {
        "as_of_year": "2010", "respondent_id": "0000451965", "agency_code": "1", "loan_type": "1",
        "property_type": "1", "loan_purpose": "3", "owner_occupancy": "1",
        "loan_amount_000s": "205", "preapproval": "3", "action_taken": "1", "msamd": "40140",
        "state_code": "6", "county_code": "71", "census_tract_number": "97.09",
        "applicant_ethnicity": "2", "co_applicant_ethnicity": "5", "applicant_race_1": "5",
        "applicant_race_2": "", "applicant_race_3": "", "applicant_race_4": "",
        "applicant_race_5": "", "co_applicant_race_1": "8", "co_applicant_race_2": "",
        "co_applicant_race_3": "", "co_applicant_race_4": "", "co_applicant_race_5": "",
        "applicant_sex": "1", "co_applicant_sex": "5", "applicant_income_000s": "NA",
        "purchaser_type": "0", "denial_reason_1": "", "denial_reason_2": "",
        "denial_reason_3": "", "rate_spread": "02.10", "hoepa_status": "2", "lien_status": "1",
        "population": "6022", "minority_population": "36.28",
        "hud_median_family_income": "65800", "tract_to_msamd_income": "68.0",
        "number_of_owner_occupied_units": "1214", "number_of_1_to_4_family_units": "2110",
        "application_date_indicator": "0",
    }  # fmt: skip
    con.execute(
        "CREATE TABLE raw AS SELECT "
        + ", ".join(f"{lit(v)} AS {k}" for k, v in cols.items())
        + ", 0 AS file_row_number"
    )
    r = _one(con, historic_core_select("raw"))
    assert r["lender_key"] == "1-0000451965"
    assert r["census_tract"] == "06071009709"
    assert r["county_fips"] == "06071" and r["state_fips"] == "06"
    assert r["loan_amount"] == 205000.0
    assert r["applicant_income_000s"] is None and r["applicant_income_000s_na_reason"] == "NA"
    assert r["derived_race"] == "White" and r["derived_ethnicity"] == "Not Hispanic or Latino"
    assert r["higher_priced"] is True and r["rate_spread"] == 2.1
    assert r["application_date_before_2004"] is False
    assert r["loan_purpose_label"] == "Refinancing (including cash-out)"
