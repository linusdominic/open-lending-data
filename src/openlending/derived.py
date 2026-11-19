"""The FFIEC's derived race, ethnicity and sex rules, as SQL and as plain Python.

Ported from the HMDA Platform source code (github.com/cfpb/hmda-platform, commit eec90f87,
``common/src/main/scala/hmda/parser/derivedFields/{Race,Ethnicity,Sex}Categorization.scala``),
including two quirks of that code that are kept on purpose so the port reproduces the
published ``derived_*`` columns:

- "any applicant White" checks race fields 1, 2, 3 and 5 but not 4;
- the "contains Not Hispanic or Latino" test is also true when ethnicity field 3, 4 or 5 is
  empty, and the single-race Native Hawaiian / Pacific Islander rule tests the applicant's own
  race fields (not the co-applicant's) for White.

The SQL builders take column expressions so the same rules run on the 2018+ LAR (subgroup
codes) and the pre-2018 LAR (major groups only). The Python functions are the reference used
by the unit tests to check the SQL.
"""

from __future__ import annotations

from collections.abc import Sequence

ASIAN = (2, 21, 22, 23, 24, 25, 26, 27)
NHOPI = (4, 41, 42, 43, 44)
HISPANIC = (1, 11, 12, 13, 14)

Codes = Sequence[int | None]


# ------------------------------------------------------------------------------------------
# Python reference implementation
# ------------------------------------------------------------------------------------------


def _any_white(r: Codes) -> bool:
    return 5 in (r[0], r[1], r[2], r[4])


def _two_to_five_empty(r: Codes) -> bool:
    return all(x is None for x in r[1:5])


def _three_to_five_empty(r: Codes) -> bool:
    return all(x is None for x in r[2:5])


def _any_minority(r: Codes) -> bool:
    return any(x in ASIAN or x in NHOPI or x in (1, 3) for x in r)


def _n_minority_groups(r: Codes) -> int:
    return sum(
        [
            any(x in NHOPI for x in r),
            any(x in ASIAN for x in r),
            3 in r,
            1 in r,
        ]
    )


def _only_asian(r: Codes) -> bool:
    return (
        any(x in ASIAN for x in r) and not any(x in NHOPI for x in r) and 3 not in r and 1 not in r
    )


def _only_nhopi(r: Codes) -> bool:
    return (
        not any(x in ASIAN for x in r) and any(x in NHOPI for x in r) and 3 not in r and 1 not in r
    )


def derive_race(r: Codes, c: Codes) -> str:
    """Derived race from applicant race fields ``r`` and co-applicant fields ``c`` (5 each)."""
    r1 = r[0]
    if r1 is None:
        return "Free Form Text Only"
    if r1 in (6, 7):
        return "Race Not Available"
    if _n_minority_groups(r) > 1 and not _any_white(c):
        return "2 or more minority races"
    if _any_minority(r) and _any_white(c):
        return "Joint"
    if _any_minority(c) and r1 == 5 and _two_to_five_empty(r):
        return "Joint"
    if r1 == 5 and _two_to_five_empty(r) and _two_to_five_empty(c) and c[0] in (5, 6, 7, 8):
        return "White"

    def pair(group: tuple[int, ...], label: str) -> str | None:
        if (r1 in group and r[1] == 5) or (r[1] in group and r1 == 5):
            if _three_to_five_empty(r) and not _any_white(c):
                return label
            return "Joint"
        return None

    aian = "American Indian or Alaska Native"
    if r1 == 1 and _two_to_five_empty(r) and not _any_white(c):
        return aian
    if (p := pair((1,), aian)) is not None:
        return p
    if r1 in ASIAN and _two_to_five_empty(r) and not _any_white(c):
        return "Asian"
    if _only_asian(r) and not _any_white(c):
        return "Asian"
    if (p := pair(ASIAN, "Asian")) is not None:
        return p
    nh = "Native Hawaiian or Other Pacific Islander"
    if r1 in NHOPI and _two_to_five_empty(r) and not _any_white(r):
        return nh
    if _only_nhopi(r) and not _any_white(c):
        return nh
    if (p := pair(NHOPI, nh)) is not None:
        return p
    black = "Black or African American"
    if r1 == 3 and _two_to_five_empty(r) and not _any_white(c):
        return black
    if (p := pair((3,), black)) is not None:
        return p
    return "Joint"


def _contains_not_hispanic_flag(e: Codes) -> bool:
    return e[0] == 2 or e[1] == 2 or e[2] is None or e[3] is None or e[4] is None


def derive_ethnicity(e: Codes, c: Codes) -> str:
    e1 = e[0]
    any_h = any(x in HISPANIC for x in e)
    co_any_h = any(x in HISPANIC for x in c)
    if e1 is None:
        return "Free Form Text Only"
    if e1 in (3, 4):
        return "Ethnicity Not Available"
    if e1 in HISPANIC and _two_to_five_empty(e) and not _contains_not_hispanic_flag(c):
        return "Hispanic or Latino"
    if any_h and 2 not in e and 2 not in c:
        return "Hispanic or Latino"
    if e1 == 2 and _two_to_five_empty(e) and not co_any_h:
        return "Not Hispanic or Latino"
    if (
        (any_h and _contains_not_hispanic_flag(c))
        or (_contains_not_hispanic_flag(e) and co_any_h)
        or (_contains_not_hispanic_flag(e) and any_h)
        or (_contains_not_hispanic_flag(c) and co_any_h)
    ):
        return "Joint"
    return "Ethnicity Not Available"


def derive_sex(s: int | None, co: int | None) -> str:
    if s in (3, 4):
        return "Sex Not Available"
    if s == 1 and co not in (2, 6):
        return "Male"
    if s == 2 and co not in (1, 6):
        return "Female"
    if (s == 1 and co in (2, 6)) or (s == 2 and co in (1, 6)) or s == 6:
        return "Joint"
    return "Sex Not Available"


# ------------------------------------------------------------------------------------------
# SQL builders (NULL = empty field; every predicate is NULL-safe)
# ------------------------------------------------------------------------------------------


def _in(x: str, values: Sequence[int]) -> str:
    return f"coalesce({x} IN ({', '.join(map(str, values))}), false)"


def _eq(x: str, v: int) -> str:
    return f"coalesce({x} = {v}, false)"


def _any(cols: Sequence[str], values: Sequence[int]) -> str:
    return "(" + " OR ".join(_in(c, values) for c in cols) + ")"


def _empty(cols: Sequence[str]) -> str:
    return "(" + " AND ".join(f"{c} IS NULL" for c in cols) + ")"


def race_sql(r: Sequence[str], c: Sequence[str]) -> str:
    def white(x: Sequence[str]) -> str:
        return "(" + " OR ".join(_eq(x[i], 5) for i in (0, 1, 2, 4)) + ")"

    def minority(x: Sequence[str]) -> str:
        return (
            "(" + " OR ".join([_any(x, ASIAN), _any(x, NHOPI), _any(x, (3,)), _any(x, (1,))]) + ")"
        )

    def n_groups(x: Sequence[str]) -> str:
        parts = [_any(x, NHOPI), _any(x, ASIAN), _any(x, (3,)), _any(x, (1,))]
        return "(" + " + ".join(f"CAST({p} AS INTEGER)" for p in parts) + ")"

    def only(x: Sequence[str], yes: Sequence[int], no: Sequence[int]) -> str:
        return (
            f"({_any(x, yes)} AND NOT {_any(x, no)} AND NOT {_any(x, (3,))} "
            f"AND NOT {_any(x, (1,))})"
        )

    r1, r2 = r[0], r[1]
    e25, e35 = _empty(r[1:5]), _empty(r[2:5])
    cw = white(c)

    def pair_when(group: Sequence[int], label: str) -> str:
        cond = f"(({_in(r1, group)} AND {_eq(r2, 5)}) OR ({_in(r2, group)} AND {_eq(r1, 5)}))"
        return f"WHEN {cond} THEN CASE WHEN {e35} AND NOT {cw} THEN '{label}' ELSE 'Joint' END"

    aian, nh, black = (
        "American Indian or Alaska Native",
        "Native Hawaiian or Other Pacific Islander",
        "Black or African American",
    )
    return f"""CASE
        WHEN {r1} IS NULL THEN 'Free Form Text Only'
        WHEN {_in(r1, (6, 7))} THEN 'Race Not Available'
        WHEN {n_groups(r)} > 1 AND NOT {cw} THEN '2 or more minority races'
        WHEN {minority(r)} AND {cw} THEN 'Joint'
        WHEN {minority(c)} AND {_eq(r1, 5)} AND {e25} THEN 'Joint'
        WHEN {_eq(r1, 5)} AND {e25} AND {_empty(c[1:5])} AND {_in(c[0], (5, 6, 7, 8))}
            THEN 'White'
        WHEN {_eq(r1, 1)} AND {e25} AND NOT {cw} THEN '{aian}'
        {pair_when((1,), aian)}
        WHEN {_in(r1, ASIAN)} AND {e25} AND NOT {cw} THEN 'Asian'
        WHEN {only(r, ASIAN, NHOPI)} AND NOT {cw} THEN 'Asian'
        {pair_when(ASIAN, "Asian")}
        WHEN {_in(r1, NHOPI)} AND {e25} AND NOT {white(r)} THEN '{nh}'
        WHEN {only(r, NHOPI, ASIAN)} AND NOT {cw} THEN '{nh}'
        {pair_when(NHOPI, nh)}
        WHEN {_eq(r1, 3)} AND {e25} AND NOT {cw} THEN '{black}'
        {pair_when((3,), black)}
        ELSE 'Joint' END"""


def ethnicity_sql(e: Sequence[str], c: Sequence[str]) -> str:
    def cnh(x: Sequence[str]) -> str:
        return (
            f"({_eq(x[0], 2)} OR {_eq(x[1], 2)} OR {x[2]} IS NULL OR {x[3]} IS NULL "
            f"OR {x[4]} IS NULL)"
        )

    any_h, co_any_h = _any(e, HISPANIC), _any(c, HISPANIC)
    return f"""CASE
        WHEN {e[0]} IS NULL THEN 'Free Form Text Only'
        WHEN {_in(e[0], (3, 4))} THEN 'Ethnicity Not Available'
        WHEN {_in(e[0], HISPANIC)} AND {_empty(e[1:5])} AND NOT {cnh(c)}
            THEN 'Hispanic or Latino'
        WHEN {any_h} AND NOT {_any(e, (2,))} AND NOT {_any(c, (2,))} THEN 'Hispanic or Latino'
        WHEN {_eq(e[0], 2)} AND {_empty(e[1:5])} AND NOT {co_any_h} THEN 'Not Hispanic or Latino'
        WHEN ({any_h} AND {cnh(c)}) OR ({cnh(e)} AND {co_any_h}) OR ({cnh(e)} AND {any_h})
            OR ({cnh(c)} AND {co_any_h}) THEN 'Joint'
        ELSE 'Ethnicity Not Available' END"""


def sex_sql(s: str, co: str) -> str:
    return f"""CASE
        WHEN {_in(s, (3, 4))} THEN 'Sex Not Available'
        WHEN {_eq(s, 1)} AND NOT {_in(co, (2, 6))} THEN 'Male'
        WHEN {_eq(s, 2)} AND NOT {_in(co, (1, 6))} THEN 'Female'
        WHEN ({_eq(s, 1)} AND {_in(co, (2, 6))}) OR ({_eq(s, 2)} AND {_in(co, (1, 6))})
            OR {_eq(s, 6)} THEN 'Joint'
        ELSE 'Sex Not Available' END"""
