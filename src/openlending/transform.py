"""Harmonisation: staged text Parquet -> typed, documented Parquet tables.

Every table is written per year (or as one file for small tables) under ``data/parquet/``.
SQL is generated from the column specs in :mod:`openlending.schema`, so the data dictionary,
the build and the validation checks share one definition.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import duckdb

from openlending import codes as C
from openlending import derived
from openlending.config import HISTORIC_YEARS, LAR_YEARS, PANEL_YEARS, Settings
from openlending.db import connect, ident, lit
from openlending.schema import (
    BANK_FINANCIALS,
    HMDA_LAR,
    HMDA_LAR_CORE,
    LENDERS,
    Col,
)

Log = Callable[[str], None]

PARQUET_OPTS = "FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 200000"

STATE_FIPS: dict[str, str] = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08", "CT": "09",
    "DE": "10", "DC": "11", "FL": "12", "GA": "13", "HI": "15", "ID": "16", "IL": "17",
    "IN": "18", "IA": "19", "KS": "20", "KY": "21", "LA": "22", "ME": "23", "MD": "24",
    "MA": "25", "MI": "26", "MN": "27", "MS": "28", "MO": "29", "MT": "30", "NE": "31",
    "NV": "32", "NH": "33", "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38",
    "OH": "39", "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46",
    "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53", "WV": "54",
    "WI": "55", "WY": "56", "AS": "60", "GU": "66", "MP": "69", "PR": "72", "VI": "78",
}  # fmt: skip


# ---------------------------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------------------------


def table_dir(s: Settings, table: str) -> Path:
    return s.out_dir / table


def year_file(s: Settings, table: str, year: int) -> Path:
    return table_dir(s, table) / f"{table}_{year}.parquet"


def single_file(s: Settings, table: str) -> Path:
    return table_dir(s, table) / f"{table}.parquet"


def staged(s: Settings, group: str, key: str) -> Path:
    return s.staging_dir / group / f"{key}.parquet"


def _write(con: duckdb.DuckDBPyConnection, sql: str, out: Path) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.parquet")
    con.execute(f"COPY ({sql}) TO {lit(str(tmp))} ({PARQUET_OPTS})")
    tmp.replace(out)
    row = con.execute(f"SELECT count(*) FROM read_parquet({lit(str(out))})").fetchone()
    assert row is not None
    return int(row[0])


def _save_report(s: Settings, name: str, key: str, value: Any) -> None:
    path = s.reports_dir / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(path.read_text()) if path.exists() else {}
    data[key] = value
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------------------------
# SQL fragments
# ---------------------------------------------------------------------------------------------


def label_case(expr: str, domain: C.Domain) -> str:
    whens = " ".join(f"WHEN {k} THEN {lit(v)}" for k, v in sorted(domain.items()))
    return f"CASE {expr} {whens} END"


def _raw(name: str) -> str:
    return f"nullif(trim({ident(name)}), '')"


def int_expr(raw: str, sql_type: str = "INTEGER") -> str:
    """Text to integer; accepts '360' and '360.0' but not '360.5' (-> NULL, never rounded)."""
    d = f"TRY_CAST({raw} AS DOUBLE)"
    return f"CASE WHEN {d} = trunc({d}) THEN TRY_CAST({d} AS {sql_type}) END"


def typed_select(cols: list[Col], *, record_id_expr: str) -> list[str]:
    """SELECT expressions for the 2018+ LAR, from a staged all-text relation."""
    out: list[str] = []
    for c in cols:
        n = c.name
        raw = _raw(n)
        if n == "record_id":
            out.append(f"CAST({record_id_expr} AS INTEGER) AS record_id")
        elif c.kind == "year":
            out.append(f"CAST({raw} AS SMALLINT) AS {ident(n)}")
        elif c.kind == "id" and n == "lei":
            out.append(f"upper({raw}) AS {ident(n)}")
        elif c.kind == "id":
            out.append(f"{raw} AS {ident(n)}")
        elif c.kind == "text":
            out.append(f"CASE WHEN {raw} = 'NA' THEN NULL ELSE {raw} END AS {ident(n)}")
        elif c.kind == "category":
            out.append(f"{raw} AS {ident(n)}")
        elif c.kind == "code":
            typed = f"TRY_CAST({raw} AS SMALLINT)"
            out.append(f"{typed} AS {ident(n)}")
            if c.label and c.domain:
                # Label from the typed expression: a bare column name here would bind to the
                # raw text column of the same name, not to the alias above.
                out.append(f"{label_case(typed, c.domain)} AS {ident(n + '_label')}")
        elif c.kind == "number":
            val = (
                f"TRY_CAST({raw} AS DOUBLE)"
                if c.sql_type == "DOUBLE"
                else int_expr(raw, c.sql_type)
            )
            out.append(
                f"CASE WHEN {raw} IN ('NA', 'Exempt') THEN NULL ELSE {val} END AS {ident(n)}"
            )
            out.append(
                f"CASE WHEN {raw} IN ('NA', 'Exempt') THEN {raw} END AS {ident(n + '_na_reason')}"
            )
        elif c.kind == "integer":
            if c.sql_type == "DOUBLE":
                out.append(f"TRY_CAST({raw} AS DOUBLE) AS {ident(n)}")
            else:
                out.append(f"{int_expr(raw, c.sql_type)} AS {ident(n)}")
        else:  # pragma: no cover - guarded by schema tests
            raise ValueError(f"unhandled kind {c.kind} for {n}")
    return out


def parse_loss_sql(cols: list[Col], rel: str) -> str:
    """Count, per column, non-empty raw values that the typed expression turned into NULL."""
    parts = []
    for c in cols:
        n = c.name
        raw = _raw(n)
        if c.kind == "code":
            cond = f"{raw} IS NOT NULL AND TRY_CAST({raw} AS SMALLINT) IS NULL"
        elif c.kind == "number":
            val = (
                f"TRY_CAST({raw} AS DOUBLE)"
                if c.sql_type == "DOUBLE"
                else int_expr(raw, c.sql_type)
            )
            cond = f"{raw} IS NOT NULL AND {raw} NOT IN ('NA', 'Exempt') AND {val} IS NULL"
        elif c.kind == "integer":
            val = (
                f"TRY_CAST({raw} AS DOUBLE)"
                if c.sql_type == "DOUBLE"
                else int_expr(raw, c.sql_type)
            )
            cond = f"{raw} IS NOT NULL AND {raw} <> 'NA' AND {val} IS NULL"
        else:
            continue
        parts.append(f"count(*) FILTER (WHERE {cond}) AS {ident(n)}")
    return f"SELECT {', '.join(parts)} FROM {rel}"


# ---------------------------------------------------------------------------------------------
# hmda_lar (2018+)
# ---------------------------------------------------------------------------------------------


def lar_years_available(s: Settings) -> list[int]:
    return [y for y in LAR_YEARS if staged(s, "lar", f"lar_{y}").exists()]


# Raw column names that changed between snapshot years: {old name: name used here}.
LAR_RENAMES = {"loan_to_value_ratio": "combined_loan_to_value_ratio"}


def lar_relation(con: duckdb.DuckDBPyConnection, src: Path) -> str:
    """The staged LAR file with file_row_number and the current column names."""
    base = f"read_parquet({lit(str(src))}, file_row_number = true)"
    cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {base}").fetchall()}
    renames = [f"{ident(a)} AS {ident(b)}" for a, b in LAR_RENAMES.items() if a in cols]
    if not renames:
        return base
    return f"(SELECT * RENAME ({', '.join(renames)}) FROM {base})"


def build_hmda_lar(s: Settings, *, years: list[int] | None = None, log: Log = print) -> None:
    con = connect(s)
    try:
        for y in years or lar_years_available(s):
            if y not in LAR_YEARS:
                continue
            src = staged(s, "lar", f"lar_{y}")
            t0 = time.monotonic()
            rel = lar_relation(con, src)
            exprs = typed_select(HMDA_LAR, record_id_expr="file_row_number + 1")
            sql = f"SELECT {', '.join(exprs)} FROM {rel}"
            n = _write(con, sql, year_file(s, "hmda_lar", y))
            loss_row = con.execute(parse_loss_sql(HMDA_LAR, rel)).fetchone()
            assert loss_row is not None
            names = [d[0] for d in con.description or []]
            loss = {k: int(v) for k, v in zip(names, loss_row, strict=True) if v}
            _save_report(s, "parse_loss", f"hmda_lar_{y}", loss)
            log(f"hmda_lar {y}: {n:,} rows in {time.monotonic() - t0:.0f}s; parse losses {loss}")
    finally:
        con.close()


# ---------------------------------------------------------------------------------------------
# hmda_lar_core
# ---------------------------------------------------------------------------------------------

CORE_NAMES = [c.name for c in HMDA_LAR_CORE]


def core_2018_select(lar: str, ts: str) -> str:
    """hmda_lar_core rows from typed hmda_lar (alias l) joined to the TS (alias t)."""
    race = [f"l.applicant_race_{i}" for i in range(1, 6)]
    co_race = [f"l.co_applicant_race_{i}" for i in range(1, 6)]
    eth = [f"l.applicant_ethnicity_{i}" for i in range(1, 6)]
    co_eth = [f"l.co_applicant_ethnicity_{i}" for i in range(1, 6)]

    def race_major(x: str) -> str:
        return (
            f"CASE WHEN {x} BETWEEN 21 AND 27 THEN 2 WHEN {x} BETWEEN 41 AND 44 THEN 4 "
            f"WHEN {x} IN (1,2,3,4,5,6,7,8) THEN {x} END"
        )

    def eth_major(x: str) -> str:
        return f"CASE WHEN {x} BETWEEN 11 AND 14 THEN 1 WHEN {x} IN (1,2,3,4,5) THEN {x} END"

    def denial(x: str) -> str:
        return f"CASE WHEN {x} BETWEEN 1 AND 9 THEN {x} END"

    sel: dict[str, str] = {
        "activity_year": "l.activity_year",
        "record_id": "l.record_id",
        "source_era": "'2018plus'",
        "lender_key": "l.lei",
        "lei": "l.lei",
        "respondent_id": "CAST(NULL AS VARCHAR)",
        "agency_code": "t.agency_code",
        "loan_type": "l.loan_type",
        "property_type": (
            "CASE WHEN l.total_units IN ('1','2','3','4') AND l.construction_method = 1 THEN 1 "
            "WHEN l.total_units IN ('1','2','3','4') AND l.construction_method = 2 THEN 2 "
            "WHEN l.total_units IS NOT NULL AND l.total_units NOT IN ('1','2','3','4') THEN 3 END"
        ),
        "loan_purpose": (
            "CASE WHEN l.loan_purpose IN (31, 32) THEN 3 "
            "WHEN l.loan_purpose IN (1, 2, 4, 5) THEN l.loan_purpose END"
        ),
        "occupancy": "CASE WHEN l.occupancy_type = 1 THEN 1 WHEN l.occupancy_type IN (2, 3) "
        "THEN 2 END",
        "preapproval": "CASE WHEN l.preapproval IN (1, 2) THEN l.preapproval END",
        "action_taken": "l.action_taken",
        "loan_amount": "l.loan_amount",
        "loan_amount_na_reason": "l.loan_amount_na_reason",
        "applicant_income_000s": "l.income",
        "applicant_income_000s_na_reason": "l.income_na_reason",
        "msa_md": "l.derived_msa_md",
        "state_fips": "coalesce(substr(l.county_code, 1, 2), sf.fips)",
        "county_fips": "l.county_code",
        "census_tract": "l.census_tract",
        "applicant_ethnicity": eth_major("l.applicant_ethnicity_1"),
        "co_applicant_ethnicity": eth_major("l.co_applicant_ethnicity_1"),
        **{f"applicant_race_{i}": race_major(f"l.applicant_race_{i}") for i in range(1, 6)},
        **{f"co_applicant_race_{i}": race_major(f"l.co_applicant_race_{i}") for i in range(1, 6)},
        "applicant_sex": "l.applicant_sex",
        "co_applicant_sex": "l.co_applicant_sex",
        "derived_race": derived.race_sql(race, co_race),
        "derived_ethnicity": derived.ethnicity_sql(eth, co_eth),
        "derived_sex": derived.sex_sql("l.applicant_sex", "l.co_applicant_sex"),
        "purchaser_type": "CASE WHEN l.purchaser_type IN (71, 72) THEN 7 ELSE l.purchaser_type END",
        **{f"denial_reason_{i}": denial(f"l.denial_reason_{i}") for i in range(1, 4)},
        "rate_spread": "l.rate_spread",
        "rate_spread_na_reason": "l.rate_spread_na_reason",
        "higher_priced": (
            "CASE WHEN l.action_taken = 1 AND l.rate_spread IS NOT NULL THEN "
            "CASE WHEN l.lien_status = 1 THEN l.rate_spread >= 1.5 "
            "WHEN l.lien_status = 2 THEN l.rate_spread >= 3.5 END END"
        ),
        "hoepa_status": "l.hoepa_status",
        "application_date_before_2004": "CAST(NULL AS BOOLEAN)",
        "lien_status": "l.lien_status",
        "open_end_line_of_credit": "l.open_end_line_of_credit",
        "reverse_mortgage": "l.reverse_mortgage",
        "business_or_commercial_purpose": "l.business_or_commercial_purpose",
        "tract_population": "l.tract_population",
        "tract_minority_population_percent": "l.tract_minority_population_percent",
        "ffiec_msa_md_median_family_income": "l.ffiec_msa_md_median_family_income",
        "tract_to_msa_income_percentage": "l.tract_to_msa_income_percentage",
        "tract_owner_occupied_units": "l.tract_owner_occupied_units",
        "tract_one_to_four_family_homes": "l.tract_one_to_four_family_homes",
    }
    state_values = ", ".join(f"({lit(k)}, {lit(v)})" for k, v in STATE_FIPS.items())
    return (
        f"SELECT {', '.join(_core_with_na(sel))} FROM {lar} l "
        f"LEFT JOIN (SELECT DISTINCT ON (lei) lei, agency_code FROM {ts}) t ON t.lei = l.lei "
        f"LEFT JOIN (VALUES {state_values}) sf(abbr, fips) ON sf.abbr = l.state_code"
    )


def _core_with_na(sel: dict[str, str]) -> list[str]:
    """Core SELECT list: column, its label, and the _na_reason companions for numbers."""
    out = []
    for c in HMDA_LAR_CORE:
        out.append(f"{sel[c.name]} AS {ident(c.name)}")
        if c.label and c.domain:
            # From the mapped expression, not the bare name, which would bind to the source.
            out.append(f"{label_case(sel[c.name], c.domain)} AS {ident(c.name + '_label')}")
        if c.na_reason:
            out.append(f"{sel[c.name + '_na_reason']} AS {ident(c.name + '_na_reason')}")
    return out


def _ts_2018_rel(s: Settings, y: int) -> str:
    p = staged(s, "ts", f"ts_{y}")
    return (
        f"(SELECT upper(trim(lei)) AS lei, TRY_CAST(agency_code AS SMALLINT) AS agency_code "
        f"FROM read_parquet({lit(str(p))}))"
    )


def build_core_2018plus(s: Settings, *, years: list[int] | None = None, log: Log = print) -> None:
    con = connect(s)
    try:
        for y in years or lar_years_available(s):
            if y not in LAR_YEARS:
                continue
            t0 = time.monotonic()
            lar = f"read_parquet({lit(str(year_file(s, 'hmda_lar', y)))})"
            n = _write(
                con, core_2018_select(lar, _ts_2018_rel(s, y)), year_file(s, "hmda_lar_core", y)
            )
            log(f"hmda_lar_core {y}: {n:,} rows in {time.monotonic() - t0:.0f}s")
    finally:
        con.close()


def _tract_expr(state: str, county: str, tract: str) -> str:
    """Pre-2018 tract '0201.00' (or '201.00', '0201') -> 11-digit state+county+tract."""
    t = f"nullif(nullif({tract}, 'NA'), '')"
    six = (
        f"CASE WHEN {t} LIKE '%.%' THEN lpad(split_part({t}, '.', 1), 4, '0') || "
        f"rpad(split_part({t}, '.', 2), 2, '0') ELSE lpad({t}, 4, '0') || '00' END"
    )
    return (
        f"CASE WHEN {t} IS NULL OR {state} IS NULL OR {county} IS NULL THEN NULL "
        f"ELSE {state} || {county} || {six} END"
    )


def historic_core_select(rel: str) -> str:
    def code(n: str) -> str:
        return f"TRY_CAST(nullif(nullif(trim({n}), ''), 'NA') AS SMALLINT)"

    def num(n: str) -> str:
        return f"TRY_CAST(nullif(nullif(trim({n}), ''), 'NA') AS DOUBLE)"

    def integer(n: str) -> str:
        return f"CAST(round({num(n)}) AS INTEGER)"

    state = (
        "CASE WHEN trim(state_code) IN ('', 'NA') THEN NULL ELSE lpad(trim(state_code), 2, '0') END"
    )
    county3 = (
        "CASE WHEN trim(county_code) IN ('', 'NA') THEN NULL "
        "ELSE lpad(trim(county_code), 3, '0') END"
    )
    race = [f"r.applicant_race_{i}" for i in range(1, 6)]
    co_race = [f"r.co_applicant_race_{i}" for i in range(1, 6)]
    race_cols = ", ".join(
        f"{code(f'{who}_race_{i}')} AS {who}_race_{i}"
        for who in ("applicant", "co_applicant")
        for i in range(1, 6)
    )
    eth = ["r.applicant_ethnicity", "NULL", "NULL", "NULL", "NULL"]
    co_eth = ["r.co_applicant_ethnicity", "NULL", "NULL", "NULL", "NULL"]
    inner = f"""
        SELECT
            CAST(trim(as_of_year) AS SMALLINT) AS activity_year,
            CAST(file_row_number + 1 AS INTEGER) AS record_id,
            trim(respondent_id) AS respondent_id,
            {code("agency_code")} AS agency_code,
            {code("loan_type")} AS loan_type,
            {code("property_type")} AS property_type,
            {code("loan_purpose")} AS loan_purpose,
            {code("owner_occupancy")} AS occupancy,
            {code("preapproval")} AS preapproval,
            {code("action_taken")} AS action_taken,
            {num("loan_amount_000s")} * 1000 AS loan_amount,
            {integer("applicant_income_000s")} AS applicant_income_000s,
            CASE WHEN trim(applicant_income_000s) = 'NA' THEN 'NA' END
                AS applicant_income_000s_na_reason,
            nullif(nullif(trim(msamd), ''), 'NA') AS msa_md,
            {state} AS state_fips,
            {state} || {county3} AS county_fips,
            {_tract_expr(state, county3, "trim(census_tract_number)")} AS census_tract,
            {code("applicant_ethnicity")} AS applicant_ethnicity,
            {code("co_applicant_ethnicity")} AS co_applicant_ethnicity,
            {race_cols},
            {code("applicant_sex")} AS applicant_sex,
            {code("co_applicant_sex")} AS co_applicant_sex,
            {code("purchaser_type")} AS purchaser_type,
            {code("denial_reason_1")} AS denial_reason_1,
            {code("denial_reason_2")} AS denial_reason_2,
            {code("denial_reason_3")} AS denial_reason_3,
            {num("rate_spread")} AS rate_spread,
            CASE WHEN trim(rate_spread) = 'NA' THEN 'NA' END AS rate_spread_na_reason,
            {code("hoepa_status")} AS hoepa_status,
            CASE trim(application_date_indicator) WHEN '1' THEN true WHEN '0' THEN false END
                AS application_date_before_2004,
            {code("lien_status")} AS lien_status,
            {integer("population")} AS tract_population,
            {num("minority_population")} AS tract_minority_population_percent,
            {integer("hud_median_family_income")} AS ffiec_msa_md_median_family_income,
            {num("tract_to_msamd_income")} AS tract_to_msa_income_percentage,
            {integer("number_of_owner_occupied_units")} AS tract_owner_occupied_units,
            {integer("number_of_1_to_4_family_units")} AS tract_one_to_four_family_homes
        FROM {rel}
    """
    sel: dict[str, str] = {name: f"r.{name}" for name in CORE_NAMES}
    sel.update(
        {
            "source_era": "'pre2018'",
            "lender_key": "CAST(r.agency_code AS VARCHAR) || '-' || r.respondent_id",
            "lei": "CAST(NULL AS VARCHAR)",
            "loan_amount_na_reason": "CAST(NULL AS VARCHAR)",
            "applicant_income_000s_na_reason": "r.applicant_income_000s_na_reason",
            "rate_spread_na_reason": "r.rate_spread_na_reason",
            "derived_race": derived.race_sql(race, co_race),
            "derived_ethnicity": derived.ethnicity_sql(eth, co_eth),
            "derived_sex": derived.sex_sql("r.applicant_sex", "r.co_applicant_sex"),
            "higher_priced": (
                "CASE WHEN r.activity_year >= 2010 AND r.action_taken = 1 "
                "THEN r.rate_spread IS NOT NULL END"
            ),
            "open_end_line_of_credit": "CAST(NULL AS SMALLINT)",
            "reverse_mortgage": "CAST(NULL AS SMALLINT)",
            "business_or_commercial_purpose": "CAST(NULL AS SMALLINT)",
        }
    )
    return f"SELECT {', '.join(_core_with_na(sel))} FROM ({inner}) r"


def historic_years_available(s: Settings) -> list[int]:
    return [y for y in HISTORIC_YEARS if staged(s, "historic_lar", f"historic_lar_{y}").exists()]


def build_historic_core(s: Settings, *, years: list[int] | None = None, log: Log = print) -> None:
    con = connect(s)
    try:
        for y in years or historic_years_available(s):
            if y not in HISTORIC_YEARS:
                continue
            t0 = time.monotonic()
            src = staged(s, "historic_lar", f"historic_lar_{y}")
            rel = f"read_parquet({lit(str(src))}, file_row_number = true)"
            n = _write(con, historic_core_select(rel), year_file(s, "hmda_lar_core", y))
            log(f"hmda_lar_core {y} (historic): {n:,} rows in {time.monotonic() - t0:.0f}s")
    finally:
        con.close()


# ---------------------------------------------------------------------------------------------
# lenders
# ---------------------------------------------------------------------------------------------


def _nz_bigint(expr: str) -> str:
    """Panel ids use -1 / 0 / blank for 'none'."""
    return (
        f"CASE WHEN TRY_CAST(trim({expr}) AS BIGINT) > 0 THEN TRY_CAST(trim({expr}) AS BIGINT) END"
    )


def _nonneg_smallint(expr: str) -> str:
    return f"CASE WHEN TRY_CAST({expr} AS SMALLINT) >= 0 THEN TRY_CAST({expr} AS SMALLINT) END"


def _varchar_columns(names: list[str]) -> str:
    """read_json ``columns`` struct reading every field as text."""
    return "{" + ", ".join(f"{lit(k)}: 'VARCHAR'" for k in names) + "}"


# The 2012 CFPB Reporter Panel has an 11-character "Respondent RSSD ID" in every row: the
# 10-digit id followed by the first character of the next field (so 451965 reads 4519650).
# Every other year has 10 characters. Drop the eleventh character.
PANEL_RSSD_FIX = (
    "CASE WHEN length(trim(respondent_rssd_id)) = 11 THEN left(trim(respondent_rssd_id), 10) "
    "ELSE respondent_rssd_id END"
)


def lenders_sql(s: Settings) -> str:
    parts_2018 = []
    for y in LAR_YEARS:
        ts = staged(s, "ts", f"ts_{y}")
        if not ts.exists():
            continue
        parts_2018.append(
            f"""SELECT CAST(activity_year AS SMALLINT) AS activity_year, upper(trim(lei)) AS lei,
                TRY_CAST(agency_code AS SMALLINT) AS agency_code,
                trim(respondent_name) AS respondent_name, trim(respondent_city) AS respondent_city,
                trim(respondent_state) AS respondent_state, trim(tax_id) AS tax_id,
                TRY_CAST(lar_count AS BIGINT) AS ts_lar_count
            FROM read_parquet({lit(str(ts))})"""
        )
    panels = []
    for y in PANEL_YEARS:
        p = staged(s, "panel", f"panel_{y}")
        if not p.exists():
            continue
        panels.append(
            f"""SELECT CAST(activity_year AS SMALLINT) AS panel_year, upper(trim(lei)) AS lei,
                {_nz_bigint("respondent_rssd")} AS rssd_id,
                {_nz_bigint("parent_rssd")} AS parent_rssd_id,
                {_nz_bigint("topholder_rssd")} AS top_holder_rssd_id,
                CASE WHEN trim(topholder_name) IN ('', '-1') THEN NULL ELSE trim(topholder_name) END
                    AS top_holder_name,
                CASE WHEN TRY_CAST(assets AS BIGINT) >= 0 THEN TRY_CAST(assets AS BIGINT) END
                    AS assets_000s,
                {_nonneg_smallint("other_lender_code")} AS other_lender_code
            FROM read_parquet({lit(str(p))})"""
        )
    ts_all = " UNION ALL ".join(parts_2018)
    panel_all = " UNION ALL ".join(panels)
    modern = f"""
        WITH ts AS ({ts_all}),
        panel AS ({panel_all}),
        best AS (
            SELECT ts.*, p.panel_year, p.rssd_id, p.parent_rssd_id, p.top_holder_rssd_id,
                   p.top_holder_name, p.assets_000s, p.other_lender_code,
                   row_number() OVER (PARTITION BY ts.activity_year, ts.lei
                                      ORDER BY (p.panel_year = ts.activity_year) DESC,
                                               p.panel_year DESC) AS rn
            FROM ts LEFT JOIN panel p
              ON p.lei = ts.lei AND p.panel_year <= ts.activity_year
        )
        SELECT activity_year, lei AS lender_key, lei, CAST(NULL AS VARCHAR) AS respondent_id,
               agency_code, respondent_name, respondent_city, respondent_state, tax_id,
               ts_lar_count, rssd_id,
               CASE WHEN rssd_id IS NULL THEN 'none'
                    WHEN panel_year = activity_year THEN 'panel'
                    ELSE 'panel_other_year' END AS rssd_source,
               CASE WHEN panel_year = activity_year THEN parent_rssd_id END AS parent_rssd_id,
               CASE WHEN panel_year = activity_year THEN top_holder_rssd_id END
                   AS top_holder_rssd_id,
               CASE WHEN panel_year = activity_year THEN top_holder_name END AS top_holder_name,
               CASE WHEN panel_year = activity_year THEN assets_000s END AS assets_000s,
               CASE WHEN panel_year = activity_year THEN other_lender_code END
                   AS other_lender_code
        FROM best WHERE rn = 1
    """

    hist_ts, hist_panel = [], []
    for y in HISTORIC_YEARS:
        ts = staged(s, "historic_ts", f"historic_ts_{y}")
        if ts.exists():
            hist_ts.append(
                f"""SELECT CAST(activity_year AS SMALLINT) AS activity_year,
                    trim(respondent_id) AS respondent_id,
                    TRY_CAST(agency_code AS SMALLINT) AS agency_code,
                    trim(respondent_name) AS respondent_name,
                    trim(respondent_city) AS respondent_city,
                    trim(respondent_state) AS respondent_state,
                    trim(federal_tax_id) AS tax_id,
                    TRY_CAST(lar_count AS BIGINT) AS ts_lar_count
                FROM read_parquet({lit(str(ts))})"""
            )
        p = staged(s, "historic_panel", f"historic_panel_{y}")
        if p.exists() and y >= 2010:
            hist_panel.append(
                f"""SELECT CAST(activity_year AS SMALLINT) AS panel_year,
                    trim(respondent_id) AS respondent_id,
                    TRY_CAST(agency_code AS SMALLINT) AS agency_code,
                    {_nz_bigint(PANEL_RSSD_FIX)} AS rssd_id,
                    {_nz_bigint("parent_rssd_id")} AS parent_rssd_id,
                    {_nz_bigint("top_holder_rssd_id")} AS top_holder_rssd_id,
                    nullif(trim(top_holder_name), '') AS top_holder_name,
                    CASE WHEN TRY_CAST(assets AS BIGINT) >= 0 THEN TRY_CAST(assets AS BIGINT) END
                        AS assets_000s,
                    {_nonneg_smallint("other_lender_code")} AS other_lender_code
                FROM read_parquet({lit(str(p))})"""
            )
        elif p.exists():
            hist_panel.append(
                f"""SELECT CAST(activity_year AS SMALLINT) AS panel_year,
                    trim(respondent_identification_number) AS respondent_id,
                    TRY_CAST(agency_code AS SMALLINT) AS agency_code,
                    CAST(NULL AS BIGINT) AS rssd_id, CAST(NULL AS BIGINT) AS parent_rssd_id,
                    CAST(NULL AS BIGINT) AS top_holder_rssd_id,
                    CAST(NULL AS VARCHAR) AS top_holder_name,
                    CASE WHEN TRY_CAST(trim(assets) AS BIGINT) >= 0
                         THEN TRY_CAST(trim(assets) AS BIGINT) END AS assets_000s,
                    {_nonneg_smallint("trim(other_lender_code)")} AS other_lender_code
                FROM read_parquet({lit(str(p))})"""
            )
    xref = staged(s, "xref", "arid2017_to_lei")
    historic = f"""
        WITH ts AS ({" UNION ALL ".join(hist_ts)}),
        panel AS ({" UNION ALL ".join(hist_panel)}),
        same AS (
            SELECT ts.*, p.rssd_id AS p_rssd, p.parent_rssd_id, p.top_holder_rssd_id,
                   p.top_holder_name, p.assets_000s, p.other_lender_code
            FROM ts LEFT JOIN panel p
              ON p.respondent_id = ts.respondent_id AND p.agency_code = ts.agency_code
             AND p.panel_year = ts.activity_year
        ),
        other_year AS (
            SELECT respondent_id, agency_code, rssd_id,
                   row_number() OVER (PARTITION BY respondent_id, agency_code
                                      ORDER BY panel_year) AS rn
            FROM panel WHERE rssd_id IS NOT NULL
        ),
        xref AS (
            SELECT trim(arid_2017) AS arid,
                   coalesce(nullif(trim(lei_2018), ''), nullif(trim(lei_2019), ''),
                            nullif(trim(lei_2020), '')) AS lei
            FROM read_parquet({lit(str(xref))})
        )
        SELECT s.activity_year,
               CAST(s.agency_code AS VARCHAR) || '-' || s.respondent_id AS lender_key,
               x.lei, s.respondent_id, s.agency_code, s.respondent_name, s.respondent_city,
               s.respondent_state, s.tax_id, s.ts_lar_count,
               coalesce(s.p_rssd, o.rssd_id,
                        CASE WHEN s.agency_code = 2 THEN TRY_CAST(s.respondent_id AS BIGINT) END)
                   AS rssd_id,
               CASE WHEN s.p_rssd IS NOT NULL THEN 'panel'
                    WHEN o.rssd_id IS NOT NULL THEN 'panel_other_year'
                    WHEN s.agency_code = 2 AND TRY_CAST(s.respondent_id AS BIGINT) > 0
                        THEN 'respondent_id_frs'
                    ELSE 'none' END AS rssd_source,
               s.parent_rssd_id, s.top_holder_rssd_id, s.top_holder_name, s.assets_000s,
               s.other_lender_code
        FROM same s
        LEFT JOIN other_year o
          ON o.respondent_id = s.respondent_id AND o.agency_code = s.agency_code AND o.rn = 1
        LEFT JOIN xref x
          ON x.arid = CAST(s.agency_code AS VARCHAR) || ltrim(s.respondent_id, '0')
    """
    return f"({modern}) UNION ALL BY NAME ({historic})"


def build_lenders(s: Settings, *, log: Log = print) -> None:
    con = connect(s)
    try:
        t0 = time.monotonic()
        con.execute(f"CREATE TEMP TABLE l AS {lenders_sql(s)}")
        core = str(table_dir(s, "hmda_lar_core") / "*.parquet")
        con.execute(
            f"""CREATE TEMP TABLE counts AS
                SELECT activity_year, lender_key, count(*) AS lar_records
                FROM read_parquet({lit(core)}) GROUP BY ALL"""
        )
        fdic = single_file(s, "fdic_institutions")
        con.execute(
            f"""CREATE TEMP TABLE fdic AS
                SELECT * FROM read_parquet({lit(str(fdic))})"""
        )
        # Lender keys that appear in the LAR but have no Transmittal Sheet row that year
        # (e.g. one 2014 filer): add a row so every LAR record has a lender, flagged
        # ts_present = false, with name and identifiers from the nearest year that has them.
        con.execute(
            """INSERT INTO l BY NAME
               SELECT c.activity_year, c.lender_key, o.lei, o.respondent_id, o.agency_code,
                      o.respondent_name, o.respondent_city, o.respondent_state, o.tax_id,
                      CAST(NULL AS BIGINT) AS ts_lar_count, o.rssd_id,
                      CASE WHEN o.rssd_id IS NULL THEN 'none' ELSE 'panel_other_year' END
                          AS rssd_source
               FROM counts c
               JOIN (SELECT * FROM l QUALIFY row_number() OVER (PARTITION BY lender_key
                     ORDER BY activity_year DESC) = 1) o USING (lender_key)
               WHERE NOT EXISTS (SELECT 1 FROM l x WHERE x.activity_year = c.activity_year
                                 AND x.lender_key = c.lender_key)"""
        )
        con.execute(
            """INSERT INTO l BY NAME
               SELECT c.activity_year, c.lender_key,
                      CASE WHEN c.activity_year >= 2018 THEN c.lender_key END AS lei,
                      CASE WHEN c.activity_year < 2018 THEN split_part(c.lender_key, '-', 2)
                           || CASE WHEN length(c.lender_key) - length(replace(c.lender_key, '-',
                              '')) > 1 THEN '-' || split_part(c.lender_key, '-', 3) ELSE '' END
                      END AS respondent_id,
                      CASE WHEN c.activity_year < 2018
                           THEN TRY_CAST(split_part(c.lender_key, '-', 1) AS SMALLINT) END
                          AS agency_code,
                      'none' AS rssd_source
               FROM counts c
               WHERE NOT EXISTS (SELECT 1 FROM l x WHERE x.lender_key = c.lender_key)"""
        )
        cols = [c.name for c in LENDERS]
        sql = f"""
            WITH by_rssd AS (
                SELECT rssd_id, cert, name,
                       row_number() OVER (PARTITION BY rssd_id ORDER BY active DESC,
                                          end_date DESC, cert) AS rn
                FROM fdic WHERE rssd_id IS NOT NULL
            ),
            m AS (
                SELECT l.*, c.lar_records,
                       coalesce(r.cert, a.cert) AS fdic_cert,
                       coalesce(r.name, a.name) AS fdic_name,
                       CASE WHEN r.cert IS NOT NULL THEN 'rssd'
                            WHEN a.cert IS NOT NULL THEN 'respondent_id_cert' END
                           AS fdic_match_method
                FROM l
                LEFT JOIN counts c USING (activity_year, lender_key)
                LEFT JOIN by_rssd r ON r.rssd_id = l.rssd_id AND r.rn = 1
                LEFT JOIN fdic a
                  ON l.activity_year < 2018 AND l.agency_code = 3 AND r.cert IS NULL
                 AND a.cert = TRY_CAST(l.respondent_id AS INTEGER)
            )
            SELECT {", ".join(ident(c) for c in cols if c != "ts_present")},
                   ts_lar_count IS NOT NULL AS ts_present,
                   {label_case("agency_code", C.AGENCY)} AS agency_code_label,
                   {label_case("other_lender_code", C.OTHER_LENDER_CODE)}
                       AS other_lender_code_label
            FROM m ORDER BY activity_year, lender_key
        """
        n = _write(con, sql, single_file(s, "lenders"))
        log(f"lenders: {n:,} lender-years in {time.monotonic() - t0:.0f}s")
    finally:
        con.close()


# ---------------------------------------------------------------------------------------------
# FDIC
# ---------------------------------------------------------------------------------------------


def _ymd(expr: str) -> str:
    return f"TRY_CAST(strptime(CAST({expr} AS VARCHAR), ['%Y%m%d', '%m/%d/%Y']) AS DATE)"


def build_fdic(s: Settings, *, log: Log = print) -> None:
    con = connect(s)
    try:
        t0 = time.monotonic()
        inst = s.raw_dir / "fdic" / "institutions.jsonl"
        sql = f"""
            SELECT CAST(CERT AS INTEGER) AS cert,
                   CASE WHEN TRY_CAST(FED_RSSD AS BIGINT) > 0 THEN TRY_CAST(FED_RSSD AS BIGINT) END
                       AS rssd_id,
                   NAME AS name, CITY AS city, STALP AS state,
                   TRY_CAST(ACTIVE AS INTEGER) = 1 AS active,
                   BKCLASS AS bank_class, REGAGNT AS regulator,
                   {_ymd("ESTYMD")} AS established_date, {_ymd("INSDATE")} AS insured_date,
                   {_ymd("ENDEFYMD")} AS end_date,
                   CASE WHEN TRY_CAST(RSSDHCR AS BIGINT) > 0 THEN TRY_CAST(RSSDHCR AS BIGINT) END
                       AS holding_company_rssd_id,
                   nullif(NAMEHCR, '') AS holding_company_name,
                   TRY_CAST(CB AS INTEGER) = 1 AS community_bank, SPECGRPN AS specialization
            FROM read_json({lit(str(inst))}, format = 'newline_delimited',
                           columns = {_varchar_columns(_fdic_inst_fields())})
            ORDER BY cert
        """
        n = _write(con, sql, single_file(s, "fdic_institutions"))
        log(f"fdic_institutions: {n:,} rows")
        fin = str(s.raw_dir / "fdic" / "financials" / "*.jsonl")
        from openlending.fdic import FINANCIAL_FIELDS

        mapping = {
            "total_assets": "ASSET", "total_deposits": "DEP", "equity_capital": "EQ",
            "loans_and_leases_gross": "LNLSGR", "loans_and_leases_net": "LNLSNET",
            "real_estate_loans": "LNRE", "re_1_4_family_loans": "LNRERES",
            "re_1_4_family_lines": "LNRELOC", "re_multifamily_loans": "LNREMULT",
            "net_income": "NETINC", "roa": "ROA", "roe": "ROE", "equity_to_assets": "EQV",
            "leverage_ratio": "RBC1AAJ", "noncurrent_loans": "NCLNLS",
            "re_1_4_family_past_due_30_89": "P3RERES", "re_1_4_family_nonaccrual": "NARERES",
            "re_1_4_family_net_chargeoffs": "NTRERES", "employees": "NUMEMP",
        }  # fmt: skip
        types = {c.name: c.sql_type for c in BANK_FINANCIALS}
        measures = ", ".join(
            f"TRY_CAST(TRY_CAST({src} AS DOUBLE) AS {types[dst]}) AS {dst}"
            if types[dst] != "DOUBLE"
            else f"TRY_CAST({src} AS DOUBLE) AS {dst}"
            for dst, src in mapping.items()
        )
        sql = f"""
            SELECT CAST(CERT AS INTEGER) AS cert,
                   CASE WHEN TRY_CAST(RSSDID AS BIGINT) > 0 THEN TRY_CAST(RSSDID AS BIGINT) END
                       AS rssd_id,
                   {_ymd("REPDTE")} AS report_date,
                   CAST(year({_ymd("REPDTE")}) AS SMALLINT) AS year,
                   CAST(quarter({_ymd("REPDTE")}) AS SMALLINT) AS quarter,
                   NAME AS name, {measures}
            FROM read_json({lit(fin)}, format = 'newline_delimited',
                           columns = {_varchar_columns(FINANCIAL_FIELDS)})
            ORDER BY report_date, cert
        """
        n = _write(con, sql, single_file(s, "bank_financials"))
        log(f"bank_financials: {n:,} bank-quarters in {time.monotonic() - t0:.0f}s")
    finally:
        con.close()


def _fdic_inst_fields() -> list[str]:
    from openlending.fdic import INSTITUTION_FIELDS

    return INSTITUTION_FIELDS


# ---------------------------------------------------------------------------------------------
# DuckDB database with views
# ---------------------------------------------------------------------------------------------

YEAR_TABLES = ["hmda_lar", "hmda_lar_core"]
SINGLE_TABLES = ["lenders", "bank_financials", "fdic_institutions", "mortgage_complaints"]


def code_rows() -> list[tuple[str, str, int, str]]:
    """(table, column, code, label) for every coded column."""
    rows: list[tuple[str, str, int, str]] = []
    for table, cols in (("hmda_lar", HMDA_LAR), ("hmda_lar_core", HMDA_LAR_CORE),
                        ("lenders", LENDERS)):  # fmt: skip
        for c in cols:
            if c.domain:
                rows.extend((table, c.name, k, v) for k, v in sorted(c.domain.items()))
    return rows


def create_views(con: duckdb.DuckDBPyConnection, root: Path) -> list[str]:
    """Create one view per table over the Parquet files under ``root``; return their names."""
    made = []
    for t in YEAR_TABLES + SINGLE_TABLES:
        files = sorted((root / t).glob("*.parquet"))
        if not files:
            continue
        glob = str(root / t / "*.parquet")
        con.execute(
            f"CREATE OR REPLACE VIEW {t} AS SELECT * FROM read_parquet({lit(glob)}, "
            "union_by_name = true)"
        )
        made.append(t)
    con.execute("CREATE OR REPLACE TABLE hmda_codes (table_name VARCHAR, column_name VARCHAR, "
                "code SMALLINT, label VARCHAR)")  # fmt: skip
    con.executemany("INSERT INTO hmda_codes VALUES (?, ?, ?, ?)", code_rows())
    return made


def build_database(s: Settings, *, log: Log = print) -> None:
    path = s.database_path
    tmp = path.with_suffix(".tmp.duckdb")
    tmp.unlink(missing_ok=True)
    con = connect(s, tmp)
    try:
        made = create_views(con, s.out_dir)
    finally:
        con.close()
    tmp.replace(path)
    log(f"database {path}: views {made} and table hmda_codes")
