"""release-assets: Parquet files sized for GitHub Releases, a SHA-256 manifest, release notes.

GitHub rejects release assets of 2 GiB or more; files here are kept under ``max_bytes``
(default 1.9 GB). A year whose Parquet file is larger is split into parts by ``record_id``
range. Nothing is uploaded.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openlending import __version__
from openlending.config import Settings
from openlending.db import connect, lit
from openlending.manifest import sha256_file
from openlending.transform import PARQUET_OPTS, SINGLE_TABLES, YEAR_TABLES, table_dir

Log = Callable[[str], None]


def _link_or_copy(src: Path, dst: Path) -> None:
    dst.unlink(missing_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def parts_needed(size: int, max_bytes: int, headroom: float = 0.85) -> int:
    """How many parts a file of ``size`` bytes must be split into (1 if it fits)."""
    if size < max_bytes:
        return 1
    return math.ceil(size / (max_bytes * headroom))


def build_release(s: Settings, *, max_bytes: int = 1_900_000_000, log: Log = print) -> Path:
    out = s.release_dir
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*"):
        old.unlink()
    assets: list[dict[str, Any]] = []
    con = connect(s)
    t0 = time.monotonic()
    try:
        for table in YEAR_TABLES + SINGLE_TABLES:
            for src in sorted(table_dir(s, table).glob("*.parquet")):
                size = src.stat().st_size
                n_parts = parts_needed(size, max_bytes)
                rows_row = con.execute(f"SELECT count(*) FROM read_parquet({lit(str(src))})"
                                       ).fetchone()  # fmt: skip
                assert rows_row is not None
                total_rows = int(rows_row[0])
                if n_parts == 1:
                    dst = out / src.name
                    _link_or_copy(src, dst)
                    targets = [(dst, total_rows)]
                else:
                    targets = []
                    per = math.ceil(total_rows / n_parts)
                    for i in range(n_parts):
                        # Split by position in the file; every row lands in one part.
                        lo, hi = i * per, min((i + 1) * per, total_rows) - 1
                        dst = out / f"{src.stem}_part{i + 1}of{n_parts}.parquet"
                        con.execute(
                            "COPY (SELECT * EXCLUDE (file_row_number) FROM "
                            f"read_parquet({lit(str(src))}, file_row_number = true) "
                            f"WHERE file_row_number BETWEEN {lo} AND {hi} "
                            f"ORDER BY file_row_number) TO {lit(str(dst))} ({PARQUET_OPTS})"
                        )
                        targets.append((dst, hi - lo + 1))
                for dst, rows in targets:
                    b = dst.stat().st_size
                    if b >= max_bytes:
                        raise RuntimeError(f"{dst.name} is {b:,} bytes, over {max_bytes:,}")
                    suffix = src.stem.rsplit("_", 1)[-1]
                    year = suffix if table in YEAR_TABLES and suffix.isdigit() else None
                    assets.append(
                        {
                            "file": dst.name,
                            "table": table,
                            "year": int(year) if year else None,
                            "rows": rows,
                            "bytes": b,
                            "sha256": sha256_file(dst),
                        }
                    )
                    log(f"asset {dst.name}: {rows:,} rows, {b / 1e6:,.1f} MB")
    finally:
        con.close()
    for doc in (
        "data-dictionary.json",
        "data-dictionary.md",
        "changes-over-time.md",
        "complaint-matching.md",
        "validation-report.md",
    ):
        p = s.docs_dir / doc
        if p.exists():
            shutil.copy2(p, out / doc)
            assets.append(
                {"file": doc, "table": None, "year": None, "rows": None,
                 "bytes": p.stat().st_size, "sha256": sha256_file(out / doc)}
            )  # fmt: skip
    (out / "SHA256SUMS").write_text("".join(f"{a['sha256']}  {a['file']}\n" for a in assets))
    (out / "release-manifest.json").write_text(
        json.dumps(
            {
                "version": __version__,
                "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "max_bytes": max_bytes,
                "assets": assets,
            },
            indent=2,
        )
        + "\n"
    )
    notes = release_notes(assets, max_bytes)
    (out / "RELEASE_NOTES.md").write_text(notes)
    log(f"release: {len(assets)} assets in {out} ({time.monotonic() - t0:.0f}s)")
    return out


def release_notes(assets: list[dict[str, Any]], max_bytes: int) -> str:
    data = [a for a in assets if a["table"]]
    total = sum(a["bytes"] for a in data)
    lines = [
        f"# open-lending-data {__version__}",
        "",
        "Harmonised US mortgage-lending public data built by `openlending build` from the "
        "FFIEC HMDA Snapshot National Loan-Level Dataset (2018 onward), the CFPB historic HMDA "
        "data (2007-2017), the FDIC BankFind Suite API and the CFPB Consumer Complaint "
        "Database. See the repository README for coverage, validation results and limitations.",
        "",
        f"{len(data)} Parquet files (zstd), {total / 1e9:.2f} GB in total, each under "
        f"{max_bytes / 1e9:.1f} GB. Verify downloads with `sha256sum -c SHA256SUMS`.",
        "",
        "| File | Table | Year | Rows | MB |",
        "|---|---|---|---|---|",
    ]
    for a in data:
        lines.append(
            f"| {a['file']} | {a['table']} | {a['year'] or ''} | {a['rows']:,} | "
            f"{a['bytes'] / 1e6:,.1f} |"
        )
    lines += [
        "",
        "Also attached: data-dictionary.json, data-dictionary.md, changes-over-time.md, "
        "complaint-matching.md, validation-report.md, "
        "SHA256SUMS and release-manifest.json.",
        "",
    ]
    return "\n".join(lines)
