"""mortgage_complaints: CFPB complaints with product = 'Mortgage', matched to HMDA lenders."""

from __future__ import annotations

import time
from collections.abc import Callable

from openlending.config import Settings
from openlending.db import connect, lit
from openlending.matching import LenderIndex, normalize
from openlending.transform import _save_report, _write, single_file, staged

Log = Callable[[str], None]


def build_complaints(s: Settings, *, log: Log = print) -> None:
    t0 = time.monotonic()
    con = connect(s)
    try:
        src = staged(s, "complaints", "complaints")
        con.execute(
            f"""CREATE TEMP TABLE c AS
                SELECT * FROM read_parquet({lit(str(src))}) WHERE product = 'Mortgage'"""
        )
        lenders = single_file(s, "lenders")
        pairs = con.execute(
            f"""SELECT DISTINCT lei, respondent_name FROM read_parquet({lit(str(lenders))})
                WHERE lei IS NOT NULL AND respondent_name IS NOT NULL
                ORDER BY lei, respondent_name"""
        ).fetchall()
        index = LenderIndex((str(a), str(b)) for a, b in pairs)
        companies = [
            str(r[0])
            for r in con.execute(
                "SELECT DISTINCT company FROM c WHERE company IS NOT NULL ORDER BY 1"
            ).fetchall()
        ]
        rows = []
        for company in companies:
            m = index.match(company)
            rows.append((company, normalize(company), m.lei, m.lender_name, m.method, m.confidence))
        con.execute(
            "CREATE TEMP TABLE m (company VARCHAR, company_normalized VARCHAR, matched_lei "
            "VARCHAR, matched_lender_name VARCHAR, match_method VARCHAR, match_confidence VARCHAR)"
        )
        con.executemany("INSERT INTO m VALUES (?, ?, ?, ?, ?, ?)", rows)
        sql = """
            SELECT CAST(c.complaint_id AS BIGINT) AS complaint_id,
                   CAST(c.date_received AS DATE) AS date_received,
                   CAST(year(CAST(c.date_received AS DATE)) AS SMALLINT) AS year,
                   c.product, nullif(c.sub_product, '') AS sub_product,
                   nullif(c.issue, '') AS issue, nullif(c.sub_issue, '') AS sub_issue,
                   c.company, nullif(c.state, '') AS state, nullif(c.zip_code, '') AS zip_code,
                   nullif(c.tags, '') AS tags, nullif(c.submitted_via, '') AS submitted_via,
                   TRY_CAST(c.date_sent_to_company AS DATE) AS date_sent_to_company,
                   nullif(c.company_response_to_consumer, '') AS company_response,
                   nullif(c.company_public_response, '') AS company_public_response,
                   CASE c.timely_response WHEN 'Yes' THEN true WHEN 'No' THEN false END
                       AS timely_response,
                   m.company_normalized, m.matched_lei, m.matched_lender_name,
                   coalesce(m.match_method, 'none') AS match_method,
                   coalesce(m.match_confidence, 'none') AS match_confidence
            FROM c LEFT JOIN m USING (company)
            ORDER BY complaint_id
        """
        n = _write(con, sql, single_file(s, "mortgage_complaints"))
        stats = con.execute(
            f"""SELECT match_method, count(*) AS complaints, count(DISTINCT company) AS companies
                FROM read_parquet({lit(str(single_file(s, "mortgage_complaints")))})
                GROUP BY ALL ORDER BY complaints DESC"""
        ).fetchall()
        _save_report(
            s,
            "complaint_matching",
            "by_method",
            [{"method": a, "complaints": int(b), "companies": int(c)} for a, b, c in stats],
        )
        log(f"mortgage_complaints: {n:,} rows in {time.monotonic() - t0:.0f}s; {stats}")
    finally:
        con.close()
