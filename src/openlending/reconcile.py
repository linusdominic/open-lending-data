"""Reconcile the raw-loaded LAR with the harmonised hmda_lar, row by row, using reconkit.

Left side: the staged raw file (every value as published, as text) in its own DuckDB
connection, with a deliberately simple cast of each column to the type ``hmda_lar`` declares
(NA / Exempt / empty -> NULL; nothing else). Right side: the harmonised Parquet file in a
second DuckDB connection. Because the two sides are separate connections, reconkit
reconciles them by checksum bisection, as it would two different databases, keyed on
``record_id`` (the row's position in the published file).

A second run plants three known differences in the right side and checks that reconkit
reports exactly those three rows, so a clean result cannot come from a comparison that is
unable to see differences.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from openlending.config import Settings
from openlending.db import connect, ident, lit
from openlending.schema import HMDA_LAR, Col
from openlending.transform import LAR_RENAMES, staged, year_file
from openlending.validate import Check

Log = Callable[[str], None]

PLANTED = (17, 4242, 999_999)


def _left_expr(c: Col) -> str:
    x = f"nullif(trim({ident(c.name)}), '')"
    if c.kind == "year":
        return f"CAST({x} AS SMALLINT) AS {ident(c.name)}"
    if c.kind == "code":
        return f"TRY_CAST({x} AS SMALLINT) AS {ident(c.name)}"
    if c.kind == "number":
        val = f"TRY_CAST(TRY_CAST({x} AS DOUBLE) AS {c.sql_type})"
        return (
            f"CASE WHEN {x} IN ('NA', 'Exempt') THEN NULL ELSE {val} END AS {ident(c.name)}, "
            f"CASE WHEN {x} IN ('NA', 'Exempt') THEN {x} END AS {ident(c.name + '_na_reason')}"
        )
    if c.kind == "integer":
        return f"TRY_CAST(TRY_CAST({x} AS DOUBLE) AS {c.sql_type}) AS {ident(c.name)}"
    if c.kind == "text":
        return f"CASE WHEN {x} = 'NA' THEN NULL ELSE {x} END AS {ident(c.name)}"
    return f"{x} AS {ident(c.name)}"


def compared_columns() -> list[str]:
    out = []
    for c in HMDA_LAR:
        if c.name == "record_id":
            continue
        out.append(c.name)
        if c.na_reason:
            out.append(c.name + "_na_reason")
    return out


def reconcile_raw_vs_lar(s: Settings, year: int, log: Log) -> list[Check]:
    from reconkit import DiffOptions, TableSpec, diff_tables
    from reconkit.adapters.duckdb import from_connection

    src = staged(s, "lar", f"lar_{year}")
    out_file = year_file(s, "hmda_lar", year)
    if not src.exists() or not out_file.exists():
        return [Check("reconkit_raw_vs_hmda_lar", "integrity", "fail", str(year), detail="missing")]

    left_con = connect(s)
    right_con = connect(s)
    base = f"read_parquet({lit(str(src))}, file_row_number = true)"
    cols = {r[0] for r in left_con.execute(f"DESCRIBE SELECT * FROM {base}").fetchall()}
    renames = [f"{ident(a)} AS {ident(b)}" for a, b in LAR_RENAMES.items() if a in cols]
    rel = f"(SELECT * RENAME ({', '.join(renames)}) FROM {base})" if renames else base
    exprs = ", ".join(_left_expr(c) for c in HMDA_LAR if c.name != "record_id")
    left_con.execute(
        f"CREATE VIEW raw_lar AS SELECT CAST(file_row_number + 1 AS INTEGER) AS record_id, "
        f"{exprs} FROM {rel}"
    )
    keep = ", ".join(ident(c) for c in ["record_id", *compared_columns()])
    right_con.execute(
        f"CREATE VIEW hmda_lar AS SELECT {keep} FROM read_parquet({lit(str(out_file))})"
    )
    planted = ", ".join(map(str, PLANTED))
    right_con.execute(
        f"""CREATE VIEW hmda_lar_planted AS
            SELECT * REPLACE (CASE WHEN record_id IN ({planted}) THEN coalesce(loan_amount, 0)
                                   + 10000 ELSE loan_amount END AS loan_amount)
            FROM hmda_lar"""
    )
    left = from_connection(left_con, name=f"raw_lar_{year}")
    right = from_connection(right_con, name=f"hmda_lar_{year}")
    options = DiffOptions(validate_unique_key=True)
    checks = []
    try:
        t0 = time.monotonic()
        res = diff_tables(TableSpec(left, "raw_lar"), TableSpec(right, "hmda_lar"),
                          key=["record_id"], options=options)  # fmt: skip
        seconds = time.monotonic() - t0
        n_diff = len(res.diffs)
        detail = (
            f"strategy {res.strategy}, {len(res.compared_columns)} columns compared, "
            f"{res.left.row_count} vs {res.right.row_count} rows, "
            f"{res.left.queries}+{res.right.queries} queries, "
            f"{res.left.rows_fetched}+{res.right.rows_fetched} rows downloaded, "
            f"{seconds:.1f}s; missing left {res.missing_in_left}, missing right "
            f"{res.missing_in_right}, changed {res.changed}"
        )
        if res.diffs:
            first = res.diffs[0]
            detail += f"; first: {first.kind} {first.key} " + str(
                [(c.column, c.left, c.right) for c in first.columns][:3]
            )
        log(f"reconkit raw vs hmda_lar {year}: {n_diff} differences; {detail}")
        checks.append(Check("reconkit_raw_vs_hmda_lar", "integrity",
                            "pass" if n_diff == 0 else "fail", f"hmda_lar {year}", 0, n_diff,
                            "reconkit diff_tables, staged raw file vs harmonised Parquet",
                            detail, {"seconds": round(seconds, 1)}))  # fmt: skip

        t0 = time.monotonic()
        res2 = diff_tables(TableSpec(left, "raw_lar"), TableSpec(right, "hmda_lar_planted"),
                           key=["record_id"], options=options)  # fmt: skip
        seconds2 = time.monotonic() - t0
        found = sorted(int(d.key[0]) for d in res2.diffs)
        ok = found == sorted(PLANTED) and all(
            [c.column for c in d.columns] == ["loan_amount"] for d in res2.diffs
        )
        log(f"reconkit planted check {year}: found {found} in {seconds2:.1f}s")
        checks.append(Check("reconkit_detects_planted_differences", "integrity",
                            "pass" if ok else "fail", f"hmda_lar {year}", list(PLANTED), found,
                            "loan_amount + 10000 on three record_ids in the right-hand view",
                            f"{res2.left.queries}+{res2.right.queries} queries, "
                            f"{res2.left.rows_fetched}+{res2.right.rows_fetched} rows downloaded, "
                            f"{seconds2:.1f}s"))  # fmt: skip
    finally:
        left_con.close()
        right_con.close()
    return checks
