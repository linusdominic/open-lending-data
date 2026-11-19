"""The committed sample under ``sample/``: small, deterministic, referentially consistent.

How it is drawn (``openlending sample``, from a full build):

- hmda_lar: 500 records per year 2018+, the 500 with the smallest ``hash(activity_year,
  record_id)`` (DuckDB's hash function, so the draw is deterministic and spread over the file);
- hmda_lar_core: the same records for 2018+, plus 500 per pre-2018 year drawn the same way;
- mortgage_complaints: 2,000 complaints with the smallest ``hash(complaint_id)``;
- lenders: every lender-year referenced by the sampled core rows, plus one row (the latest
  year) for every LEI matched by a sampled complaint;
- bank_financials: year-end (Q4) rows for the FDIC certificates of the sampled lenders;
- fdic_institutions: every certificate referenced by the two tables above.

The sample is for tests and CI. It is not a statistical sample of anything: per-year sizes
are equal, so it over-represents small years.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable

from openlending.config import Settings
from openlending.db import connect, lit
from openlending.transform import PARQUET_OPTS, SINGLE_TABLES, YEAR_TABLES

Log = Callable[[str], None]
PER_YEAR = 500
COMPLAINTS = 2000


def write_sample(s: Settings, *, log: Log = print) -> None:
    src = s.out_dir
    dst = s.sample_dir
    if dst.exists():
        shutil.rmtree(dst)
    for t in YEAR_TABLES + SINGLE_TABLES:
        (dst / t).mkdir(parents=True, exist_ok=True)
    con = connect(s)

    def rp(t: str) -> str:
        return f"read_parquet({lit(str(src / t / '*.parquet'))}, union_by_name = true)"

    def out(t: str, sql: str) -> None:
        path = dst / t / f"{t}.parquet"
        con.execute(f"COPY ({sql}) TO {lit(str(path))} ({PARQUET_OPTS})")
        row = con.execute(f"SELECT count(*) FROM read_parquet({lit(str(path))})").fetchone()
        assert row is not None
        log(f"sample {t}: {int(row[0]):,} rows, {path.stat().st_size / 1e3:,.0f} kB")

    try:
        con.execute(
            f"""CREATE TEMP TABLE keys AS
                SELECT activity_year, record_id FROM (
                    SELECT activity_year, record_id,
                           row_number() OVER (PARTITION BY activity_year
                                              ORDER BY hash(activity_year, record_id),
                                                       record_id) AS rn
                    FROM {rp("hmda_lar_core")})
                WHERE rn <= {PER_YEAR}"""
        )
        out(
            "hmda_lar",
            f"SELECT l.* FROM {rp('hmda_lar')} l JOIN keys USING (activity_year, record_id) "
            "ORDER BY activity_year, record_id",
        )
        out(
            "hmda_lar_core",
            f"SELECT c.* FROM {rp('hmda_lar_core')} c JOIN keys USING (activity_year, record_id) "
            "ORDER BY activity_year, record_id",
        )
        con.execute(
            f"""CREATE TEMP TABLE complaints AS
                SELECT * FROM {rp("mortgage_complaints")}
                ORDER BY hash(complaint_id), complaint_id LIMIT {COMPLAINTS}"""
        )
        out("mortgage_complaints", "SELECT * FROM complaints ORDER BY complaint_id")
        con.execute(
            f"""CREATE TEMP TABLE lenders AS
                SELECT l.* FROM {rp("lenders")} l
                WHERE (activity_year, lender_key) IN (
                    SELECT DISTINCT activity_year, lender_key
                    FROM read_parquet({lit(str(dst / "hmda_lar_core" / "*.parquet"))}))
                UNION
                SELECT * FROM (
                    SELECT l.* FROM {rp("lenders")} l
                    WHERE l.lei IN (SELECT matched_lei FROM complaints)
                    QUALIFY row_number() OVER (PARTITION BY l.lei
                                               ORDER BY l.activity_year DESC) = 1)"""
        )
        out("lenders", "SELECT * FROM lenders ORDER BY activity_year, lender_key")
        con.execute(
            f"""CREATE TEMP TABLE fin AS
                SELECT * FROM {rp("bank_financials")}
                WHERE quarter = 4 AND cert IN (SELECT fdic_cert FROM lenders)"""
        )
        out("bank_financials", "SELECT * FROM fin ORDER BY cert, report_date")
        out(
            "fdic_institutions",
            f"""SELECT * FROM {rp("fdic_institutions")}
                WHERE cert IN (SELECT fdic_cert FROM lenders UNION SELECT cert FROM fin)
                ORDER BY cert""",
        )
    finally:
        con.close()
