from __future__ import annotations

import json
from pathlib import Path

from openlending.config import Settings
from openlending.dictionary import dictionary, write_dictionary
from openlending.expected import EXPECTED, METRICS
from openlending.schema import HMDA_LAR_RAW_COLUMNS, TABLE_KEYS, TABLES

# Header of the FFIEC snapshot public LAR CSV for 2025, after openlending.db.normalize_name
# (2018 differs only in naming
# combined_loan_to_value_ratio "loan_to_value_ratio").
PUBLIC_LAR_HEADER = Path(__file__).with_name("public_lar_header.txt").read_text().split(",")


def test_lar_schema_covers_every_published_column() -> None:
    assert sorted(HMDA_LAR_RAW_COLUMNS) == sorted(h.strip() for h in PUBLIC_LAR_HEADER)


def test_dictionary_columns_are_unique_and_keys_exist() -> None:
    d = dictionary()
    assert set(d) == set(TABLES)
    for name, t in d.items():
        cols = [c["name"] for c in t["columns"]]
        assert len(cols) == len(set(cols)), name
        assert set(TABLE_KEYS[name]) <= set(cols)
        for c in t["columns"]:
            assert c["description"], (name, c["name"])
            if c["kind"] == "code":
                assert c.get("codes"), (name, c["name"])


def test_write_dictionary(settings: Settings) -> None:
    md, js = write_dictionary(settings)
    assert "## hmda_lar_core" in md.read_text()
    assert json.loads(js.read_text())["lenders"]["primary_key"] == ["activity_year", "lender_key"]


def test_every_expected_figure_has_a_metric() -> None:
    for e in EXPECTED:
        assert e.metric == "institutions" or e.metric in METRICS, e
        assert e.source
        assert e.value > 0
