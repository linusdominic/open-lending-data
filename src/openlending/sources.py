"""Catalogue of every raw file the pipeline downloads.

URLs were checked on 2026-11-19. The FFIEC serves snapshot files from
``files.ffiec.cfpb.gov/static-data/snapshot/<year>/`` (the links on
https://ffiec.cfpb.gov/data-publication/snapshot-national-loan-level-dataset/<year>), and the
CFPB serves pre-2018 data from ``files.consumerfinance.gov`` (linked from
https://www.consumerfinance.gov/data-research/hmda/historic-data/).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from openlending.config import HISTORIC_YEARS, LAR_YEARS, PANEL_YEARS

FFIEC_SNAPSHOT = "https://files.ffiec.cfpb.gov/static-data/snapshot"
CFPB_HISTORIC_LAR = "https://files.consumerfinance.gov/hmda-historic-loan-data"
CFPB_HISTORIC_INST = "https://files.consumerfinance.gov/hmda-historic-institution-data"
CFPB_COMPLAINTS = "https://files.consumerfinance.gov/ccdb/complaints.csv.zip"
FDIC_API = "https://api.fdic.gov/banks"


@dataclass(frozen=True)
class RawFile:
    """One downloadable file. ``key`` is unique and is the manifest key."""

    key: str
    url: str
    group: str  # lar, ts, panel, historic_lar, historic_panel, historic_ts, xref, complaints
    year: int | None

    @property
    def filename(self) -> str:
        return PurePosixPath(self.url).name

    @property
    def relpath(self) -> str:
        """Path under data/raw/."""
        sub = self.group if self.year is None else f"{self.group}/{self.year}"
        return f"{sub}/{self.filename}"


def catalogue() -> list[RawFile]:
    files: list[RawFile] = []
    for y in LAR_YEARS:
        files.append(RawFile(f"lar_{y}", f"{FFIEC_SNAPSHOT}/{y}/{y}_public_lar_csv.zip", "lar", y))
        files.append(RawFile(f"ts_{y}", f"{FFIEC_SNAPSHOT}/{y}/{y}_public_ts_csv.zip", "ts", y))
    for y in PANEL_YEARS:
        files.append(
            RawFile(f"panel_{y}", f"{FFIEC_SNAPSHOT}/{y}/{y}_public_panel_csv.zip", "panel", y)
        )
    files.append(
        RawFile(
            "arid2017_to_lei",
            f"{FFIEC_SNAPSHOT}/2017/arid2017tolei/arid2017_to_lei_xref_csv.zip",
            "xref",
            None,
        )
    )
    files.append(RawFile("complaints", CFPB_COMPLAINTS, "complaints", None))
    # Historic years last: they are the most expensive and the least essential.
    for y in sorted(HISTORIC_YEARS, reverse=True):
        files.append(
            RawFile(
                f"historic_panel_{y}",
                f"{CFPB_HISTORIC_INST}/hmda_{y}_panel.zip",
                "historic_panel",
                y,
            )
        )
        files.append(
            RawFile(
                f"historic_ts_{y}",
                f"{CFPB_HISTORIC_INST}/hmda_{y}_transmittal_sheet.zip",
                "historic_ts",
                y,
            )
        )
    for y in sorted(HISTORIC_YEARS, reverse=True):
        files.append(
            RawFile(
                f"historic_lar_{y}",
                f"{CFPB_HISTORIC_LAR}/hmda_{y}_nationwide_all-records_codes.zip",
                "historic_lar",
                y,
            )
        )
    return files


def select(groups: list[str] | None = None, years: list[int] | None = None) -> list[RawFile]:
    out = []
    for f in catalogue():
        if groups and f.group not in groups:
            continue
        if years and f.year is not None and f.year not in years:
            continue
        out.append(f)
    return out
