"""The SQL port of the FFIEC derived race / ethnicity / sex rules equals the Python reference."""

from __future__ import annotations

import random

import duckdb
import pytest

from openlending import derived

RACE_CODES: list[int | None] = [1, 2, 21, 22, 27, 3, 4, 41, 44, 5, 6, 7, 8, None]
ETH_CODES: list[int | None] = [1, 11, 12, 14, 2, 3, 4, 5, None]


def _random_fields(rng: random.Random, codes: list[int | None]) -> list[int | None]:
    first = rng.choice(codes)
    n_more = rng.choice([0, 0, 0, 1, 2, 4])
    rest: list[int | None] = [
        rng.choice([c for c in codes if c is not None]) for _ in range(n_more)
    ]
    return [first, *rest, *([None] * (4 - n_more))]


def _run_sql(sql: str, rows: list[tuple[int | None, ...]], n: int) -> list[str]:
    con = duckdb.connect()
    cols = ", ".join(f"c{i} SMALLINT" for i in range(n))
    con.execute(f"CREATE TABLE t (id INTEGER, {cols})")
    con.executemany(
        f"INSERT INTO t VALUES (?, {', '.join('?' for _ in range(n))})",
        [(i, *r) for i, r in enumerate(rows)],
    )
    return [str(r[0]) for r in con.execute(f"SELECT {sql} FROM t ORDER BY id").fetchall()]


def test_race_sql_matches_python_reference() -> None:
    rng = random.Random(7)
    rows = []
    for _ in range(4000):
        rows.append((*_random_fields(rng, RACE_CODES), *_random_fields(rng, RACE_CODES)))
    sql = derived.race_sql([f"c{i}" for i in range(5)], [f"c{i}" for i in range(5, 10)])
    got = _run_sql(sql, rows, 10)
    want = [derived.derive_race(r[:5], r[5:]) for r in rows]
    assert got == want


def test_ethnicity_sql_matches_python_reference() -> None:
    rng = random.Random(11)
    rows = []
    for _ in range(4000):
        rows.append((*_random_fields(rng, ETH_CODES), *_random_fields(rng, ETH_CODES)))
    sql = derived.ethnicity_sql([f"c{i}" for i in range(5)], [f"c{i}" for i in range(5, 10)])
    got = _run_sql(sql, rows, 10)
    want = [derived.derive_ethnicity(r[:5], r[5:]) for r in rows]
    assert got == want


def test_sex_sql_matches_python_reference() -> None:
    rows: list[tuple[int | None, ...]] = [
        (a, b) for a in (1, 2, 3, 4, 6, None) for b in (1, 2, 3, 4, 5, 6, None)
    ]
    got = _run_sql(derived.sex_sql("c0", "c1"), rows, 2)
    assert got == [derived.derive_sex(r[0], r[1]) for r in rows]


N5: list[int | None] = [None, None, None, None]


@pytest.mark.parametrize(
    ("app", "co", "expected"),
    [
        ([5, *N5], [8, *N5], "White"),
        ([5, *N5], [5, *N5], "White"),
        ([3, *N5], [8, *N5], "Black or African American"),
        ([22, *N5], [8, *N5], "Asian"),
        ([2, 22, None, None, None], [8, *N5], "Asian"),
        ([3, *N5], [5, *N5], "Joint"),
        ([5, *N5], [3, *N5], "Joint"),
        ([2, 3, None, None, None], [8, *N5], "2 or more minority races"),
        ([6, *N5], [8, *N5], "Race Not Available"),
        ([None, *N5], [8, *N5], "Free Form Text Only"),
        ([1, 5, None, None, None], [8, *N5], "American Indian or Alaska Native"),
    ],
)
def test_race_examples(app: list[int | None], co: list[int | None], expected: str) -> None:
    assert derived.derive_race(app, co) == expected


def test_ethnicity_examples() -> None:
    assert derived.derive_ethnicity([1, *N5], [5, *N5]) == "Hispanic or Latino"
    assert derived.derive_ethnicity([2, *N5], [5, *N5]) == "Not Hispanic or Latino"
    assert derived.derive_ethnicity([1, *N5], [2, *N5]) == "Joint"
    assert derived.derive_ethnicity([3, *N5], [5, *N5]) == "Ethnicity Not Available"
    assert derived.derive_sex(1, 2) == "Joint"
    assert derived.derive_sex(2, 5) == "Female"
