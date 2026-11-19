from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from openlending.db import ident, normalize_name
from openlending.stage import (
    extract_and_count,
    repair_extra_address_field,
    repair_short_panel_rows,
)


def _zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


@pytest.mark.parametrize(
    ("body", "lines"),
    [
        (b"a,b\n1,2\n3,4\n", 2),
        (b"a,b\n1,2\n3,4", 2),
        (b"a,b\r\n1,2\r\n3,4\r\n", 2),
        (b"a,b\n1,2\n\n", 1),
        (b"a,b\n", 0),
    ],
)
def test_extract_and_count(tmp_path: Path, body: bytes, lines: int) -> None:
    z = _zip(tmp_path / "x.zip", {"__MACOSX/._data.csv": b"junk" * 100, "data.csv": body})
    member, size, n = extract_and_count(z, tmp_path / "out.csv")
    assert member == "data.csv"
    assert size == len(body)
    assert n == lines
    assert (tmp_path / "out.csv").read_bytes() == body


def test_repairs(tmp_path: Path) -> None:
    p = tmp_path / "panel.csv"
    p.write_text(
        "y,id,agency,pid,pname,pcity,pstate,region\r\n"
        "2007,1,7,2,P,C,MI,05\r\n"
        "2007,9900000375,7                     ,MI,05\r\n",
        encoding="latin-1",
    )
    assert repair_short_panel_rows(p) == 1
    assert p.read_text(encoding="latin-1").splitlines()[2] == "2007,9900000375,7,,,,MI,05"

    t = tmp_path / "ts.csv"
    header = ",".join(f"c{i}" for i in range(8))
    t.write_text(f"{header}\r\n0,1,2,3,4,ADDR,,CITY,8\r\n0,1,2,3,4,ADDR,CITY,8\r\n")
    assert repair_extra_address_field(t) == 1
    assert t.read_text().splitlines()[1] == "0,1,2,3,4,ADDR,CITY,8"


def test_names() -> None:
    assert normalize_name(" Respondent Name (Panel)") == "respondent_name_panel"
    assert normalize_name("co-applicant_race-1") == "co_applicant_race_1"
    assert ident("loan_amount") == '"loan_amount"'
    with pytest.raises(ValueError, match="identifier"):
        ident("x; DROP TABLE y")
