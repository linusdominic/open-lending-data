"""Validation: ``openlending validate`` (``make validate``).

Checks fall into two classes:

- integrity checks (row counts against the raw files, key uniqueness, referential integrity,
  code domains, parse losses, the reconkit reconciliation): these are about this pipeline,
  and any failure makes the command exit 1;
- external checks (published FFIEC / CFPB / Federal Reserve figures): these compare against
  documents that sometimes describe a different release of the data. Failures are reported
  with the difference and the source but do not change the exit code unless ``--strict``.

Results are written to ``data/reports/validation.json`` and ``docs/validation-report.md``.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import duckdb

from openlending.config import Settings
from openlending.db import connect, ident, lit
from openlending.expected import EXPECTED, METRICS
from openlending.schema import TABLE_KEYS, TABLES, Col
from openlending.stage import read_staging_manifest
from openlending.transform import SINGLE_TABLES, YEAR_TABLES, create_views

Log = Callable[[str], None]


@dataclass
class Check:
    name: str
    kind: str  # integrity | external | info
    status: str  # pass | fail | info
    subject: str
    expected: Any = None
    actual: Any = None
    source: str = ""
    detail: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


# Defects in the published source files that this project documents rather than "fixes".
# An integrity check whose failure count equals the documented count passes, with the
# explanation attached; any other count (a new anomaly, or one that disappeared) fails.
KNOWN_EXCEPTIONS: dict[tuple[str, str], tuple[int, str]] = {
    ("code_domain", "hmda_lar.total_units"): (
        1,
        "2019 snapshot: one record has total_units '0', which is not a valid value.",
    ),
    ("code_domain", "hmda_lar.applicant_ethnicity_1"): (
        1,
        "2020 snapshot: one record has ethnicity code 24 (a race subgroup code).",
    ),
    ("code_domain", "hmda_lar.co_applicant_ethnicity_1"): (
        8,
        "2023 snapshot: eight records have co-applicant ethnicity code 8 (not an ethnicity code).",
    ),
    ("code_domain", "hmda_lar.applicant_race_1"): (
        1,
        "2018 snapshot: one record has applicant race -1.",
    ),
    (
        "referential_integrity",
        "bank_financials -> fdic_institutions: cert in fdic_institutions",
    ): (
        4946,
        "Call Report filers that are not in the BankFind institutions endpoint (non-insured "
        "trust companies, uninsured branches; 116 certificates).",
    ),
}


def apply_known_exceptions(checks: list[Check]) -> None:
    for c in checks:
        known = KNOWN_EXCEPTIONS.get((c.name, c.subject))
        if known is None:
            continue
        count, why = known
        c.expected = count
        if c.actual == count:
            c.status = "pass"
            c.detail = f"documented source defect: {why} {c.detail}".strip()
        else:
            c.status = "fail"
            c.detail = f"documented count {count} no longer matches: {why} {c.detail}".strip()


def _scalar(con: duckdb.DuckDBPyConnection, sql: str) -> Any:
    row = con.execute(sql).fetchone()
    assert row is not None
    return row[0]


def _years(con: duckdb.DuckDBPyConnection, table: str) -> list[int]:
    return [
        int(r[0])
        for r in con.execute(f"SELECT DISTINCT activity_year FROM {table} ORDER BY 1").fetchall()
    ]


# ---------------------------------------------------------------------------------------------
# individual checks
# ---------------------------------------------------------------------------------------------


def check_row_counts(con: duckdb.DuckDBPyConnection, s: Settings, sample: bool) -> list[Check]:
    """Raw CSV data lines == staged rows == rows in the harmonised table, per year."""
    out: list[Check] = []
    if sample:
        return out
    staged = read_staging_manifest(s)
    core = dict(
        con.execute("SELECT activity_year, count(*) FROM hmda_lar_core GROUP BY 1").fetchall()
    )
    lar = dict(con.execute("SELECT activity_year, count(*) FROM hmda_lar GROUP BY 1").fetchall())
    for key, m in sorted(staged.items()):
        raw, rows = m["raw_data_lines"], m["staged_rows"]
        out.append(
            Check(
                "raw_lines_equal_staged_rows",
                "integrity",
                "pass" if raw == rows else "fail",
                key,
                raw,
                rows,
                "line count of the extracted CSV",
                f"repaired rows: {m.get('repaired_rows', 0)}",
            )
        )
        if key.startswith(("lar_", "historic_lar_")):
            year = int(key.rsplit("_", 1)[1])
            got_core = int(core.get(year, 0))
            out.append(
                Check(
                    "raw_lines_equal_core_rows",
                    "integrity",
                    "pass" if raw == got_core else "fail",
                    f"hmda_lar_core {year}",
                    raw,
                    got_core,
                    f"raw file {m['member']}",
                )
            )
            if key.startswith("lar_"):
                got = int(lar.get(year, 0))
                out.append(
                    Check(
                        "raw_lines_equal_lar_rows",
                        "integrity",
                        "pass" if raw == got else "fail",
                        f"hmda_lar {year}",
                        raw,
                        got,
                        f"raw file {m['member']}",
                    )
                )
    return out


def check_ts_counts(con: duckdb.DuckDBPyConnection) -> list[Check]:
    """Sum of Transmittal Sheet LAR counts vs rows in the LAR, per year (and lenders off)."""
    rows = con.execute(
        """
        SELECT l.activity_year, sum(l.ts_lar_count) AS ts_total,
               sum(coalesce(l.lar_records, 0)) AS lar_total,
               count(*) FILTER (WHERE l.ts_lar_count <> coalesce(l.lar_records, 0)) AS lenders_off
        FROM lenders l GROUP BY 1 ORDER BY 1
        """
    ).fetchall()
    core = dict(
        con.execute("SELECT activity_year, count(*) FROM hmda_lar_core GROUP BY 1").fetchall()
    )
    out = []
    for year, ts_total, _lar_total, off in rows:
        actual = int(core.get(year, 0))
        exp = int(ts_total or 0)
        out.append(
            Check(
                "ts_lar_count_equals_lar_rows",
                "external",
                "pass" if exp == actual else "fail",
                f"{year}",
                exp,
                actual,
                "Transmittal Sheet lar_count (same release as the LAR)",
                f"{off} lender(s) whose TS count differs from their LAR rows",
            )
        )
    return out


def check_published(con: duckdb.DuckDBPyConnection) -> list[Check]:
    years = set(_years(con, "hmda_lar_core"))
    out = []
    cache: dict[tuple[int, str], int] = {}
    for e in EXPECTED:
        if e.year not in years:
            continue
        if e.metric == "institutions":
            actual = int(
                _scalar(
                    con,
                    f"SELECT count(*) FROM lenders WHERE activity_year = {e.year} AND ts_present",
                )
            )
        else:
            if (e.year, e.metric) not in cache:
                pred = METRICS[e.metric]
                cache[(e.year, e.metric)] = int(
                    _scalar(
                        con,
                        f"SELECT count(*) FROM hmda_lar_core WHERE activity_year = "
                        f"{e.year} AND {pred}",
                    )
                )
            actual = cache[(e.year, e.metric)]
        ok = abs(actual - e.value) <= (0 if e.exact else e.unit / 2)
        diff = actual - e.value
        tol = "exact" if e.exact else f"rounded to {e.unit:,.0f}"
        out.append(
            Check(
                "published_figure",
                "external",
                "pass" if ok else "fail",
                f"{e.year} {e.metric}",
                e.value,
                actual,
                e.source,
                f"{tol}; difference {diff:+,.0f} ({diff / e.value:+.3%})"
                + (f"; {e.note}" if e.note else ""),
            )
        )
    return out


DATA_BROWSER = Path(__file__).resolve().parents[2] / "validation" / "data_browser_aggregations.json"


def check_data_browser(con: duckdb.DuckDBPyConnection) -> list[Check]:
    """Counts by action taken and loan purpose vs the HMDA Data Browser API (fetched once by
    scripts/fetch_data_browser.py and committed). The Data Browser serves the latest dataset
    for each year, which for most years is a later release than the Snapshot used here."""
    if not DATA_BROWSER.exists():
        return []
    data = json.loads(DATA_BROWSER.read_text())
    years = set(_years(con, "hmda_lar"))
    out = []
    for year_s, entry in sorted(data["years"].items()):
        year = int(year_s)
        if year not in years:
            continue
        for dim, col in (("actions_taken", "action_taken"), ("loan_purposes", "loan_purpose")):
            actual = {
                str(k): int(v)
                for k, v in con.execute(
                    f"SELECT {col}, count(*) FROM hmda_lar WHERE activity_year = {year} GROUP BY 1"
                ).fetchall()
            }
            for code, exp in sorted(entry[dim].items()):
                got = actual.get(code, 0)
                diff = got - int(exp)
                out.append(
                    Check(
                        "data_browser_count",
                        "external",
                        "pass" if diff == 0 else "fail",
                        f"{year} {col}={code}",
                        int(exp),
                        got,
                        f"HMDA Data Browser API, fetched {data['fetched_at']}: "
                        f"{entry[dim + '_url']}",
                        f"difference {diff:+,} ({diff / int(exp):+.3%})",
                    )
                )
    return out


def lender_match_rates(con: duckdb.DuckDBPyConnection) -> list[Check]:
    """Info: share of bank-supervised lenders (agency 1-4) matched to an FDIC certificate."""
    rows = con.execute(
        """SELECT activity_year,
                  count(*) FILTER (WHERE agency_code IN (1, 2, 3, 4)) AS banks,
                  count(fdic_cert) FILTER (WHERE agency_code IN (1, 2, 3, 4)) AS matched,
                  sum(lar_records) AS recs,
                  sum(lar_records) FILTER (WHERE fdic_cert IS NOT NULL) AS recs_matched
           FROM lenders GROUP BY 1 ORDER BY 1"""
    ).fetchall()
    return [
        Check("lender_fdic_match_rate", "info", "info", str(y), None,
              round(m / b, 4) if b else None, "lenders.fdic_cert",
              f"{m:,} of {b:,} lenders supervised by OCC/FRS/FDIC/OTS matched; "
              f"{(rm or 0) / r:.1%} of the year's LAR records are from a matched lender")
        for y, b, m, r, rm in rows
    ]  # fmt: skip


def check_keys(con: duckdb.DuckDBPyConnection, tables: list[str]) -> list[Check]:
    out = []
    for t in tables:
        key = TABLE_KEYS[t]
        cols = ", ".join(ident(k) for k in key)
        dupes = int(
            _scalar(
                con,
                f"SELECT count(*) FROM (SELECT {cols} FROM {t} GROUP BY ALL HAVING count(*) > 1)",
            )
        )
        nulls = int(
            _scalar(
                con,
                f"SELECT count(*) FROM {t} WHERE "
                + " OR ".join(f"{ident(k)} IS NULL" for k in key),
            )
        )
        out.append(
            Check(
                "key_unique_not_null",
                "integrity",
                "pass" if dupes == 0 and nulls == 0 else "fail",
                f"{t} ({', '.join(key)})",
                0,
                dupes + nulls,
                "",
                f"{dupes} duplicate keys, {nulls} null keys",
            )
        )
    return out


def check_referential(con: duckdb.DuckDBPyConnection, tables: list[str]) -> list[Check]:
    out = []
    pairs = [
        ("hmda_lar_core", "lenders", "activity_year, lender_key", "lender key in lenders"),
        ("hmda_lar", "lenders", "activity_year, lei", "LEI in lenders (same year)"),
        ("mortgage_complaints", "lenders", "matched_lei", "matched_lei in lenders"),
        ("bank_financials", "fdic_institutions", "cert", "cert in fdic_institutions"),
        ("lenders", "fdic_institutions", "fdic_cert", "fdic_cert in fdic_institutions"),
    ]
    for child, parent, cols, what in pairs:
        if child not in tables or parent not in tables:
            continue
        if child == "hmda_lar":
            cond = "p.activity_year = c.activity_year AND p.lender_key = c.lei"
            notnull = "c.lei IS NOT NULL"
        elif child == "hmda_lar_core":
            cond = "p.activity_year = c.activity_year AND p.lender_key = c.lender_key"
            notnull = "true"
        elif child == "mortgage_complaints":
            cond = "p.lei = c.matched_lei"
            notnull = "c.matched_lei IS NOT NULL"
        else:
            col = cols
            cond = f"p.cert = c.{col}"
            notnull = f"c.{col} IS NOT NULL"
        orphans = con.execute(
            f"""SELECT {"c.activity_year" if child.startswith("hmda") else "NULL"} AS y,
                       count(*) FROM {child} c
                WHERE {notnull} AND NOT EXISTS (SELECT 1 FROM {parent} p WHERE {cond})
                GROUP BY 1 ORDER BY 1"""
        ).fetchall()
        total = sum(int(n) for _, n in orphans)
        detail = ", ".join(f"{y}: {n:,}" for y, n in orphans if y is not None)
        out.append(
            Check(
                "referential_integrity",
                "integrity",
                "pass" if total == 0 else "fail",
                f"{child} -> {parent}: {what}",
                0,
                total,
                "",
                detail,
            )
        )
    return out


def _domain_sql(table: str, c: Col, by_year: bool) -> str | None:
    if c.kind == "code" and c.domain:
        allowed = ", ".join(str(k) for k in sorted(c.domain))
        cond = f"{ident(c.name)} IS NOT NULL AND {ident(c.name)} NOT IN ({allowed})"
    elif c.kind == "category" and c.allowed:
        allowed = ", ".join(lit(v) for v in c.allowed)
        cond = f"{ident(c.name)} IS NOT NULL AND {ident(c.name)} NOT IN ({allowed})"
    else:
        return None
    return f"count(*) FILTER (WHERE {cond})"


def check_domains(con: duckdb.DuckDBPyConnection, tables: list[str]) -> list[Check]:
    out = []
    for t in tables:
        cols = [c for c in TABLES[t] if _domain_sql(t, c, False)]
        if not cols:
            continue
        has_year = t in YEAR_TABLES
        exprs = ", ".join(f"{_domain_sql(t, c, has_year)} AS {ident(c.name)}" for c in cols)
        group = "activity_year" if has_year else "'all'"
        rows = con.execute(
            f"SELECT {group} AS y, {exprs} FROM {t} GROUP BY 1 ORDER BY 1"
        ).fetchall()
        for i, c in enumerate(cols, start=1):
            bad = {str(r[0]): int(r[i]) for r in rows if r[i]}
            total = sum(bad.values())
            example = ""
            if total:
                vals = con.execute(
                    f"SELECT {ident(c.name)}, count(*) FROM {t} WHERE {_domain_cond(c)} "
                    "GROUP BY 1 ORDER BY 2 DESC LIMIT 5"
                ).fetchall()
                example = "; values " + ", ".join(f"{v!r}: {n:,}" for v, n in vals)
            out.append(
                Check(
                    "code_domain",
                    "integrity",
                    "pass" if total == 0 else "fail",
                    f"{t}.{c.name}",
                    0,
                    total,
                    "codes.py / schema.py",
                    (", ".join(f"{y}: {n:,}" for y, n in bad.items()) + example),
                )
            )
    return out


def _domain_cond(c: Col) -> str:
    if c.kind == "code" and c.domain:
        return f"{ident(c.name)} NOT IN ({', '.join(str(k) for k in sorted(c.domain))})"
    assert c.allowed is not None
    return f"{ident(c.name)} NOT IN ({', '.join(lit(v) for v in c.allowed)})"


def check_parse_losses(s: Settings, sample: bool) -> list[Check]:
    path = s.reports_dir / "parse_loss.json"
    if sample or not path.exists():
        return []
    data = json.loads(path.read_text())
    out = []
    for key, losses in sorted(data.items()):
        total = sum(losses.values())
        out.append(
            Check(
                "no_parse_loss",
                "integrity",
                "pass" if total == 0 else "fail",
                key,
                0,
                total,
                "non-empty raw values that did not parse as the declared type",
                json.dumps(losses),
            )
        )
    return out


def check_derived_port(con: duckdb.DuckDBPyConnection) -> list[Check]:
    """This project's port of the FFIEC derived race/ethnicity/sex rules vs the FFIEC's own."""
    out = []
    for f in ("derived_race", "derived_ethnicity", "derived_sex"):
        rows = con.execute(
            f"""SELECT l.activity_year, count(*) AS n,
                       count(*) FILTER (WHERE l.{f} IS DISTINCT FROM c.{f}) AS differ
                FROM hmda_lar l JOIN hmda_lar_core c USING (activity_year, record_id)
                GROUP BY 1 ORDER BY 1"""
        ).fetchall()
        n = sum(int(r[1]) for r in rows)
        differ = sum(int(r[2]) for r in rows)
        detail = ", ".join(f"{y}: {d:,} of {m:,}" for y, m, d in rows)
        out.append(
            Check(
                "derived_field_port_matches_ffiec",
                "integrity",
                "pass" if differ == 0 else "fail",
                f.replace("derived_", ""),
                0,
                differ,
                "FFIEC-published derived_* columns in hmda_lar",
                f"{n:,} rows compared; differing by year: {detail}",
            )
        )
    return out


def null_rates(con: duckdb.DuckDBPyConnection, tables: list[str]) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for t in tables:
        cols = [r[0] for r in con.execute(f"DESCRIBE {t}").fetchall()]
        group = "activity_year" if t in YEAR_TABLES else "'all'"
        exprs = ", ".join(f"avg(CASE WHEN {ident(c)} IS NULL THEN 1.0 ELSE 0.0 END)" for c in cols)
        rows = con.execute(
            f"SELECT {group}, count(*), {exprs} FROM {t} GROUP BY 1 ORDER BY 1"
        ).fetchall()
        report[t] = {
            str(r[0]): {
                "rows": int(r[1]),
                **{c: round(float(v), 4) for c, v in zip(cols, r[2:], strict=True)},
            }
            for r in rows
        }
    return report


def check_reconkit(s: Settings, year: int, log: Log) -> list[Check]:
    from openlending.reconcile import reconcile_raw_vs_lar

    return reconcile_raw_vs_lar(s, year, log)


# ---------------------------------------------------------------------------------------------
# runner and report
# ---------------------------------------------------------------------------------------------


def run_validation(
    s: Settings,
    *,
    sample: bool = False,
    log: Log = print,
    strict: bool = False,
    reconkit_year: int | None = 2023,
) -> bool:
    t0 = time.monotonic()
    root = s.sample_dir if sample else s.out_dir
    con = connect(s)
    try:
        tables = create_views(con, root)
        log(f"validating {root}: tables {tables}")
        checks: list[Check] = []
        checks += check_row_counts(con, s, sample)
        if "lenders" in tables and not sample:
            checks += check_ts_counts(con)
            checks += check_published(con)
            checks += check_data_browser(con)
            checks += lender_match_rates(con)
        checks += check_keys(con, tables)
        checks += check_referential(con, tables)
        checks += check_domains(con, tables)
        checks += check_parse_losses(s, sample)
        if "hmda_lar" in tables:
            checks += check_derived_port(con)
        nulls = null_rates(con, tables)
        if not sample:
            apply_known_exceptions(checks)
    finally:
        con.close()
    if not sample and reconkit_year is not None:
        checks += check_reconkit(s, reconkit_year, log)
    seconds = time.monotonic() - t0

    failed_integrity = [c for c in checks if c.kind == "integrity" and c.status == "fail"]
    failed_external = [c for c in checks if c.kind == "external" and c.status == "fail"]
    ok = not failed_integrity and (not strict or not failed_external)
    out_dir = s.reports_dir if not sample else s.data_dir / "reports-sample"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "validation.json").write_text(
        json.dumps(
            {
                "seconds": round(seconds, 1),
                "checks": [asdict(c) for c in checks],
                "null_rates": nulls,
            },
            indent=1,
            default=str,
        )
        + "\n"
    )
    if not sample:
        write_markdown(s, checks, nulls, seconds)
    passed = sum(c.status == "pass" for c in checks)
    log(
        f"{len(checks)} checks: {passed} pass, {len(failed_integrity)} integrity failures, "
        f"{len(failed_external)} external mismatches, in {seconds:.0f}s"
    )
    for c in failed_integrity + failed_external:
        log(
            f"FAIL [{c.kind}] {c.name} {c.subject}: expected {c.expected} actual {c.actual} "
            f"{c.detail[:200]}"
        )
    return ok


def _fmt(v: Any) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, int):
        return f"{v:,}"
    return "" if v is None else str(v)


def write_markdown(s: Settings, checks: list[Check], nulls: dict[str, Any], seconds: float) -> Path:
    lines = [
        "# Validation report",
        "",
        "Generated by `openlending validate` (`make validate`) from the full build under "
        f"`data/`. Run time {seconds:.0f} s. Integrity checks concern this pipeline; external "
        "checks compare with published figures, which can describe a different release of the "
        "data (see each note).",
        "",
    ]
    by_name: dict[str, list[Check]] = {}
    for c in checks:
        by_name.setdefault(c.name, []).append(c)
    for name, group in by_name.items():
        n_pass = sum(c.status == "pass" for c in group)
        lines += [f"## {name} ({group[0].kind}): {n_pass} of {len(group)} pass", ""]
        lines += [
            "| Status | Subject | Expected | Actual | Source / detail |",
            "|---|---|---|---|---|",
        ]
        for c in group:
            detail = "; ".join(x for x in (c.source, c.detail) if x).replace("|", "/")
            lines.append(
                f"| {c.status} | {c.subject} | {_fmt(c.expected)} | {_fmt(c.actual)} | {detail} |"
            )
        lines.append("")
    lines += [
        "## Null rates",
        "",
        "Share of NULL values per column and year is in "
        "`data/reports/validation.json` (`null_rates`); the summary below lists hmda_lar_core.",
        "",
    ]
    core = nulls.get("hmda_lar_core", {})
    if core:
        years = sorted(core)
        cols = [c for c in core[years[0]] if c != "rows"]
        lines.append("| column | " + " | ".join(years) + " |")
        lines.append("|---|" + "---|" * len(years))
        for c in cols:
            lines.append(f"| {c} | " + " | ".join(f"{core[y].get(c, 0):.3f}" for y in years) + " |")
    s.docs_dir.mkdir(parents=True, exist_ok=True)
    path = s.docs_dir / "validation-report.md"
    path.write_text("\n".join(lines) + "\n")
    return path


__all__ = ["SINGLE_TABLES", "Check", "run_validation"]
