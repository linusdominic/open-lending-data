"""Stage raw zip files as text-only Parquet.

For every raw file: extract the CSV member, count its data lines while extracting (the
independent row count used by validation), load it with DuckDB with every column as text and
normalised column names, and write ``data/staging/<group>/<key>.parquet`` in file order. The
row number in that Parquet file (``file_row_number``) is the ``record_id`` used downstream.
"""

from __future__ import annotations

import csv
import json
import os
import time
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from openlending.config import Settings
from openlending.db import connect, lit, normalize_name
from openlending.manifest import read_manifest

Log = Callable[[str], None]
CHUNK = 16 * 1024 * 1024
STAGED_GROUPS = {
    "lar",
    "ts",
    "panel",
    "xref",
    "complaints",
    "historic_lar",
    "historic_panel",
    "historic_ts",
}


def staging_manifest_path(s: Settings) -> Path:
    return s.staging_dir / "staging_manifest.json"


def read_staging_manifest(s: Settings) -> dict[str, dict[str, Any]]:
    p = staging_manifest_path(s)
    return json.loads(p.read_text()) if p.exists() else {}


def _write_staging_manifest(s: Settings, data: dict[str, dict[str, Any]]) -> None:
    p = staging_manifest_path(s)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(dict(sorted(data.items())), indent=2) + "\n")
    os.replace(tmp, p)


def csv_member(zf: zipfile.ZipFile) -> zipfile.ZipInfo:
    """The data file inside a zip: the largest member that is not macOS metadata."""
    members = [
        m
        for m in zf.infolist()
        if not m.is_dir() and not m.filename.startswith("__MACOSX") and "/._" not in m.filename
    ]
    if not members:
        raise ValueError(f"no data member in {zf.filename}")
    return max(members, key=lambda m: m.file_size)


def extract_and_count(zip_path: Path, dest: Path) -> tuple[str, int, int]:
    """Extract the CSV member to ``dest``; return (member name, bytes, data lines).

    Data lines are newline-terminated lines after the header, plus a final line without a
    newline if there is one, minus empty lines at the end of the file.
    """
    with zipfile.ZipFile(zip_path) as zf:
        member = csv_member(zf)
        newlines = 0
        size = 0
        last = b""
        trailing_empty = 0
        with zf.open(member) as src, dest.open("wb") as out:
            while block := src.read(CHUNK):
                out.write(block)
                newlines += block.count(b"\n")
                size += len(block)
                last = (last + block)[-4:]
        lines = newlines + (0 if last.endswith(b"\n") or size == 0 else 1)
        # Count blank lines at the very end (e.g. "\n\n" or "\r\n\r\n").
        tail = last.replace(b"\r", b"")
        while tail.endswith(b"\n\n"):
            trailing_empty += 1
            tail = tail[:-1]
        return member.filename, size, lines - 1 - trailing_empty


def repair_short_panel_rows(path: Path) -> int:
    """2007 Reporter Panel: one row has the parent id, name and city fused into the agency code
    field (a fixed-width remnant), so it has 13 fields instead of 16. Split it back: the agency
    code is the first character, and the three parent fields are empty. Returns rows repaired.
    """
    with path.open(newline="", encoding="latin-1") as fh:
        rows = list(csv.reader(fh))
    width = len(rows[0])
    fixed = 0
    for i, row in enumerate(rows):
        if len(row) == width - 3:
            rows[i] = [*row[:2], row[2].strip(), "", "", "", *row[3:]]
            fixed += 1
    with path.open("w", newline="", encoding="latin-1") as fh:
        csv.writer(fh, lineterminator="\r\n").writerows(rows)
    return fixed


def repair_extra_address_field(path: Path) -> int:
    """2016 Transmittal Sheet: one row has an extra empty field after the mailing address
    (23 fields instead of 22). Drop that empty field. Returns rows repaired."""
    with path.open(newline="", encoding="latin-1") as fh:
        rows = list(csv.reader(fh))
    width = len(rows[0])
    fixed = 0
    for i, row in enumerate(rows):
        if len(row) == width + 1 and row[6] == "":
            rows[i] = row[:6] + row[7:]
            fixed += 1
    with path.open("w", newline="", encoding="latin-1") as fh:
        csv.writer(fh, lineterminator="\r\n").writerows(rows)
    return fixed


# Source-specific repairs applied to the extracted CSV before loading. Each is documented in
# docs/changes-over-time.md ("Source file defects").
REPAIRS: dict[str, Callable[[Path], int]] = {
    "historic_panel_2007": repair_short_panel_rows,
    "historic_ts_2016": repair_extra_address_field,
}


def _header(path: Path) -> list[str]:
    with path.open("rb") as fh:
        line = fh.readline().decode("utf-8-sig", errors="replace").rstrip("\r\n")
    return next(csv.reader([line]))


def stage_file(s: Settings, key: str, entry: dict[str, Any], log: Log) -> dict[str, Any]:
    zip_path = s.raw_dir / entry["path"]
    out = s.staging_dir / entry["group"] / f"{key}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = s.data_dir / "tmp" / "extract"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    csv_path = tmp_dir / f"{key}.csv"
    t0 = time.monotonic()
    try:
        member, size, lines = extract_and_count(zip_path, csv_path)
        t_extract = time.monotonic() - t0
        repaired = REPAIRS[key](csv_path) if key in REPAIRS else 0
        header = _header(csv_path)
        names = [normalize_name(h) for h in header]
        if len(set(names)) != len(names):
            raise ValueError(f"{key}: duplicate column names after normalisation: {names}")
        names_sql = "[" + ", ".join(lit(n) for n in names) + "]"
        con = connect(s, preserve_order=True)
        try:
            con.execute(
                f"""
                COPY (
                    SELECT *
                    FROM read_csv({lit(str(csv_path))}, header = true, all_varchar = true,
                                  names = {names_sql},
                                  delim = ',', quote = '"', escape = '"',
                                  null_padding = false, sample_size = -1)
                ) TO {lit(str(out))} (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 500000)
                """
            )
            rows_row = con.execute(f"SELECT count(*) FROM read_parquet({lit(str(out))})").fetchone()
            assert rows_row is not None
            rows = int(rows_row[0])
        finally:
            con.close()
    finally:
        csv_path.unlink(missing_ok=True)
    seconds = time.monotonic() - t0
    log(
        f"staged {key}: {lines:,} data lines, {rows:,} rows, "
        f"{size / 1e9:.2f} GB csv, extract {t_extract:.0f}s, total {seconds:.0f}s"
    )
    return {
        "raw_key": key,
        "raw_sha256": entry["sha256"],
        "member": member,
        "csv_bytes": size,
        "raw_data_lines": lines,
        "staged_rows": rows,
        "repaired_rows": repaired,
        "columns": names,
        "staging_path": str(out.relative_to(s.data_dir)),
        "parquet_bytes": out.stat().st_size,
        "seconds": round(seconds, 1),
    }


def stage_all(
    s: Settings,
    *,
    groups: set[str] | None = None,
    years: list[int] | None = None,
    log: Log = print,
    force: bool = False,
) -> None:
    manifest = read_manifest(s.manifest_path)
    staged = read_staging_manifest(s)
    for key, entry in sorted(manifest.items()):
        if entry["group"] not in STAGED_GROUPS:
            continue
        if groups and entry["group"] not in groups:
            continue
        if years and entry.get("year") is not None and entry["year"] not in years:
            continue
        prev = staged.get(key)
        out = s.data_dir / prev["staging_path"] if prev else None
        if (
            not force
            and prev
            and prev.get("raw_sha256") == entry["sha256"]
            and out is not None
            and out.exists()
        ):
            continue
        staged[key] = stage_file(s, key, entry, log)
        _write_staging_manifest(s, staged)
