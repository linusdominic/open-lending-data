"""FDIC BankFind Suite API pulls (https://api.fdic.gov/banks, public, no key).

Two datasets are pulled:

- ``institutions``: every FDIC-insured institution, open or closed, with its FDIC
  certificate number (CERT) and Federal Reserve RSSD id (FED_RSSD). This is the bridge from
  HMDA lenders (which carry an RSSD id in the Reporter Panel) to FDIC data.
- ``financials``: selected quarterly Call Report aggregates, one request per quarter
  (each quarter has fewer than 10,000 institutions, the API's page limit).

Responses are stored as JSON Lines under ``data/raw/fdic/`` and recorded in the manifest
with their SHA-256, like file downloads.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

from openlending.config import Settings
from openlending.download import backoff_delays
from openlending.manifest import read_manifest, sha256_file, update_manifest
from openlending.sources import FDIC_API

INSTITUTION_FIELDS = [
    "CERT",
    "FED_RSSD",
    "NAME",
    "CITY",
    "STALP",
    "ZIP",
    "ACTIVE",
    "BKCLASS",
    "CHARTER",
    "CHRTAGNT",
    "REGAGNT",
    "ESTYMD",
    "INSDATE",
    "ENDEFYMD",
    "RSSDHCR",
    "NAMEHCR",
    "ASSET",
    "REPDTE",
    "CB",
    "SPECGRPN",
]

# Dollar amounts are in thousands of US dollars, as published by the FDIC.
FINANCIAL_FIELDS = [
    "CERT",
    "RSSDID",
    "REPDTE",
    "NAME",
    "ASSET",
    "DEP",
    "EQ",
    "LNLSGR",
    "LNLSNET",
    "LNRE",
    "LNRERES",
    "LNRELOC",
    "LNREMULT",
    "NETINC",
    "ROA",
    "ROE",
    "EQV",
    "RBC1AAJ",
    "NCLNLS",
    "P3RERES",
    "NARERES",
    "NTRERES",
    "NUMEMP",
]

FIRST_QUARTER = date(2007, 3, 31)
PAGE_LIMIT = 10_000

Log = Callable[[str], None]


def quarter_ends(first: date, last: date) -> list[date]:
    """Calendar quarter-end dates from ``first`` to ``last`` inclusive."""
    ends = []
    y, q = first.year, (first.month - 1) // 3 + 1
    while True:
        month = q * 3
        day = 31 if month in (3, 12) else 30
        d = date(y, month, day)
        if d > last:
            break
        if d >= first:
            ends.append(d)
        q += 1
        if q == 5:
            y, q = y + 1, 1
    return ends


def _get(client: httpx.Client, url: str, params: dict[str, Any], log: Log) -> dict[str, Any]:
    delays = backoff_delays(6)
    for attempt in range(len(delays) + 1):
        try:
            r = client.get(url, params=params)
            if r.status_code in (429, 500, 502, 503, 504):
                raise httpx.HTTPStatusError("retryable", request=r.request, response=r)
            r.raise_for_status()
            payload: dict[str, Any] = r.json()
            return payload
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            if attempt == len(delays):
                raise
            log(f"retry fdic {params.get('filters', '')}: {exc!r} in {delays[attempt]:.0f}s")
            time.sleep(delays[attempt])
    raise AssertionError("unreachable")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    tmp.replace(path)


def _record(s: Settings, key: str, path: Path, url: str, rows: int, seconds: float) -> None:
    update_manifest(
        s.manifest_path,
        key,
        {
            "url": url,
            "path": str(path.relative_to(s.raw_dir)),
            "group": "fdic",
            "year": None,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "rows": rows,
            "last_modified": None,
            "etag": None,
            "downloaded_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "seconds": round(seconds, 1),
        },
    )


def pull_fdic(s: Settings, log: Log = print, pause: float = 0.5) -> None:
    out = s.raw_dir / "fdic"
    done = read_manifest(s.manifest_path)
    with httpx.Client(timeout=httpx.Timeout(60.0, read=180.0)) as client:
        # Institutions: about 28,000 rows, three pages.
        key = "fdic_institutions"
        if key not in done:
            t0 = time.monotonic()
            rows: list[dict[str, Any]] = []
            offset = 0
            while True:
                params = {
                    "fields": ",".join(INSTITUTION_FIELDS),
                    "sort_by": "CERT",
                    "sort_order": "ASC",
                    "limit": PAGE_LIMIT,
                    "offset": offset,
                }
                page = _get(client, f"{FDIC_API}/institutions", params, log)
                batch = [d["data"] for d in page["data"]]
                rows.extend(batch)
                total = int(page["meta"]["total"])
                offset += len(batch)
                if not batch or offset >= total:
                    break
                time.sleep(pause)
            if len(rows) != total:
                raise RuntimeError(f"FDIC institutions: got {len(rows)} of {total}")
            path = out / "institutions.jsonl"
            _write_jsonl(path, rows)
            _record(s, key, path, f"{FDIC_API}/institutions", len(rows), time.monotonic() - t0)
            log(f"done  {key}: {len(rows):,} institutions")

        # Latest available quarter.
        latest = _get(
            client,
            f"{FDIC_API}/financials",
            {"fields": "REPDTE", "sort_by": "REPDTE", "sort_order": "DESC", "limit": 1},
            log,
        )
        last = datetime.strptime(latest["data"][0]["data"]["REPDTE"], "%Y%m%d").date()
        for q in quarter_ends(FIRST_QUARTER, last):
            ymd = q.strftime("%Y%m%d")
            key = f"fdic_financials_{ymd}"
            if key in done:
                continue
            t0 = time.monotonic()
            params = {
                "filters": f"REPDTE:{ymd}",
                "fields": ",".join(FINANCIAL_FIELDS),
                "sort_by": "CERT",
                "sort_order": "ASC",
                "limit": PAGE_LIMIT,
            }
            page = _get(client, f"{FDIC_API}/financials", params, log)
            rows = [d["data"] for d in page["data"]]
            total = int(page["meta"]["total"])
            if len(rows) != total:
                raise RuntimeError(f"FDIC financials {ymd}: got {len(rows)} of {total}")
            path = out / "financials" / f"{ymd}.jsonl"
            _write_jsonl(path, rows)
            url = f"{FDIC_API}/financials?filters=REPDTE:{ymd}"
            _record(s, key, path, url, len(rows), time.monotonic() - t0)
            log(f"done  {key}: {len(rows):,} institutions")
            time.sleep(pause)
