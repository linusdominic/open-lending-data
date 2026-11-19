"""Fetch nationwide counts by action taken and by loan purpose from the HMDA Data Browser API.

Writes validation/data_browser_aggregations.json, which `openlending validate` compares
against. Run by hand (it is not part of the build) and commit the result:

    uv run python scripts/fetch_data_browser.py

The Data Browser serves the latest dataset published for each year (Three Year, One Year or
Snapshot; see https://ffiec.cfpb.gov/documentation/tools/data-browser/data-browser-faq), so
for most years it describes a later release than the Snapshot this project uses.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

API = "https://ffiec.cfpb.gov/v2/data-browser-api/view/nationwide/aggregations"
OUT = Path(__file__).resolve().parents[1] / "validation" / "data_browser_aggregations.json"


def main() -> None:
    result: dict[str, object] = {
        "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "api": API,
        "years": {},
    }
    years: dict[str, object] = {}
    with httpx.Client(timeout=120) as client:
        for year in range(2018, 2026):
            entry: dict[str, object] = {}
            for dim, values in (("actions_taken", "1,2,3,4,5,6,7,8"),
                                ("loan_purposes", "1,2,31,32,4,5")):  # fmt: skip
                params = {"years": str(year), dim: values}
                r = client.get(API, params=params)
                r.raise_for_status()
                aggs = r.json()["aggregations"]
                entry[dim] = {a[dim]: a["count"] for a in aggs}
                entry[f"{dim}_url"] = str(r.url)
                time.sleep(1)
            years[str(year)] = entry
            print(year, entry["actions_taken"])
    result["years"] = years
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
