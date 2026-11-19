"""Validation and release logic run end to end on the committed sample (no downloads)."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace

import duckdb
import pytest

from openlending.config import Settings
from openlending.release import build_release, parts_needed
from openlending.transform import SINGLE_TABLES, YEAR_TABLES
from openlending.validate import run_validation


def test_sample_exists(settings: Settings) -> None:
    for t in YEAR_TABLES + SINGLE_TABLES:
        files = list((settings.sample_dir / t).glob("*.parquet"))
        assert files, t


def test_sample_validates(settings: Settings) -> None:
    assert run_validation(settings, sample=True, log=lambda _: None)
    report = json.loads((settings.data_dir / "reports-sample" / "validation.json").read_text())
    names = {c["name"] for c in report["checks"]}
    assert {
        "key_unique_not_null",
        "referential_integrity",
        "code_domain",
        "derived_field_port_matches_ffiec",
    } <= names
    assert all(c["status"] == "pass" for c in report["checks"])


def test_sample_covers_every_year(settings: Settings) -> None:
    con = duckdb.connect()
    years = con.execute(
        f"SELECT DISTINCT activity_year FROM read_parquet('{settings.sample_dir}/hmda_lar_core/*.parquet') ORDER BY 1"
    ).fetchall()
    assert [y for (y,) in years] == list(range(2007, 2026))


def test_parts_needed() -> None:
    assert parts_needed(100, 1000) == 1
    assert parts_needed(1000, 1000) == 2
    assert parts_needed(5_000, 1000) == 6


def test_release_splits_and_checksums(settings: Settings) -> None:
    s = replace(settings, data_dir=settings.data_dir)
    shutil.copytree(settings.sample_dir, s.out_dir)
    s.docs_dir.mkdir(parents=True)
    (s.docs_dir / "data-dictionary.json").write_text("{}\n")
    out = build_release(s, max_bytes=400_000, log=lambda _: None)
    manifest = json.loads((out / "release-manifest.json").read_text())
    parts = [a for a in manifest["assets"] if "_part" in a["file"]]
    assert parts, "the sample hmda_lar file should be split at a 400 kB limit"
    for a in manifest["assets"]:
        assert (out / a["file"]).stat().st_size == a["bytes"] < 400_000
    sums = (out / "SHA256SUMS").read_text().splitlines()
    assert len(sums) == len(manifest["assets"])
    con = duckdb.connect()
    lar_files = sorted(str(p) for p in out.glob("hmda_lar*.parquet") if "core" not in p.name)
    assert lar_files
    split_rows = con.execute(f"SELECT count(*) FROM read_parquet({lar_files})").fetchone()
    whole_rows = con.execute(
        f"SELECT count(*) FROM read_parquet('{s.out_dir}/hmda_lar/*.parquet')"
    ).fetchone()
    assert split_rows == whole_rows


@pytest.mark.parametrize("table", ["hmda_lar", "hmda_lar_core"])
def test_sample_record_ids_unique(settings: Settings, table: str) -> None:
    con = duckdb.connect()
    dupes = con.execute(
        f"SELECT count(*) - count(DISTINCT (activity_year, record_id)) FROM "
        f"read_parquet('{settings.sample_dir}/{table}/*.parquet')"
    ).fetchone()
    assert dupes == (0,)


@pytest.mark.parametrize("table", YEAR_TABLES + SINGLE_TABLES)
def test_dictionary_matches_built_columns(settings: Settings, table: str) -> None:
    from openlending.dictionary import dictionary

    con = duckdb.connect()
    built = [
        r[0]
        for r in con.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{settings.sample_dir}/{table}/*.parquet')"
        ).fetchall()
    ]
    documented = [c["name"] for c in dictionary()[table]["columns"]]
    assert sorted(built) == sorted(documented)
