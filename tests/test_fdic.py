from __future__ import annotations

from datetime import date

from openlending.fdic import quarter_ends


def test_quarter_ends() -> None:
    q = quarter_ends(date(2007, 3, 31), date(2008, 3, 31))
    assert q == [
        date(2007, 3, 31),
        date(2007, 6, 30),
        date(2007, 9, 30),
        date(2007, 12, 31),
        date(2008, 3, 31),
    ]
    assert quarter_ends(date(2026, 3, 31), date(2026, 6, 29)) == [date(2026, 3, 31)]
