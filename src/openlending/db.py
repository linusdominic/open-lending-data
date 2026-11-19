"""DuckDB connection helpers."""

from __future__ import annotations

import re
from pathlib import Path

import duckdb

from openlending.config import Settings


def connect(
    s: Settings,
    path: Path | str = ":memory:",
    *,
    preserve_order: bool = False,
    read_only: bool = False,
) -> duckdb.DuckDBPyConnection:
    """Open DuckDB with the project's memory and thread limits.

    ``memory_limit`` defaults to 6 GB (OPENLENDING_MEMORY_LIMIT) because the build shares the
    machine with other jobs; DuckDB spills to ``data/tmp/duckdb`` beyond that.
    """
    con = duckdb.connect(str(path), read_only=read_only)
    tmp = s.data_dir / "tmp" / "duckdb"
    tmp.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET memory_limit = '{s.duckdb_memory_limit}'")
    con.execute(f"SET threads = {int(s.duckdb_threads)}")
    con.execute(f"SET temp_directory = '{tmp}'")
    con.execute(f"SET preserve_insertion_order = {str(preserve_order).lower()}")
    return con


_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def ident(name: str) -> str:
    """Quote a column name; only plain snake_case identifiers are accepted."""
    if not _IDENT.match(name):
        raise ValueError(f"unexpected identifier {name!r}")
    return f'"{name}"'


def lit(value: str) -> str:
    """A SQL string literal."""
    return "'" + value.replace("'", "''") + "'"


def normalize_name(raw: str) -> str:
    """Raw header to snake_case: 'Respondent Name (Panel)' -> 'respondent_name_panel'."""
    s = re.sub(r"[^0-9a-zA-Z]+", "_", raw.strip()).strip("_").lower()
    return s or "unnamed"
