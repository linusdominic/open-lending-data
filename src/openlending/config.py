"""Paths and run settings.

Everything large lives under ``data/`` (gitignored). The location can be moved with the
``OPENLENDING_DATA`` environment variable; the committed sample lives in ``sample/``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Years of the FFIEC Snapshot National Loan-Level Dataset in the 2018 format.
LAR_YEARS: tuple[int, ...] = (2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025)
# The FFIEC stopped publishing a Reporter Panel with the snapshot after 2023.
PANEL_YEARS: tuple[int, ...] = (2018, 2019, 2020, 2021, 2022, 2023)
# Pre-2018 years published by the CFPB as "historic" HMDA data.
HISTORIC_YEARS: tuple[int, ...] = tuple(range(2007, 2018))


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    sample_dir: Path
    docs_dir: Path
    duckdb_memory_limit: str
    duckdb_threads: int

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def staging_dir(self) -> Path:
        """Raw files converted to Parquet with every column as text (one per source file)."""
        return self.data_dir / "staging"

    @property
    def out_dir(self) -> Path:
        """Harmonised Parquet outputs, one directory per table, partitioned by year."""
        return self.data_dir / "parquet"

    @property
    def release_dir(self) -> Path:
        return self.data_dir / "release"

    @property
    def manifest_path(self) -> Path:
        return self.raw_dir / "manifest.json"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "openlending.duckdb"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"


def load_settings(data_dir: Path | None = None) -> Settings:
    root = data_dir or Path(os.environ.get("OPENLENDING_DATA", REPO_ROOT / "data"))
    return Settings(
        data_dir=Path(root),
        sample_dir=REPO_ROOT / "sample",
        docs_dir=REPO_ROOT / "docs",
        duckdb_memory_limit=os.environ.get("OPENLENDING_MEMORY_LIMIT", "6GB"),
        duckdb_threads=int(os.environ.get("OPENLENDING_THREADS", "6")),
    )
