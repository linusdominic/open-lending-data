from __future__ import annotations

from openlending.matching import LenderIndex, core, exact_key, normalize

LENDERS = [
    ("LEI_WF", "Wells Fargo Bank, National Association"),
    ("LEI_BOA", "BANK OF AMERICA, N.A."),
    ("LEI_ROCKET", "Rocket Mortgage, LLC"),
    ("LEI_FNB1", "First National Bank"),
    ("LEI_FNB2", "FIRST NATIONAL BANK"),
    ("LEI_QCU", "Quantum Credit Union"),
    ("LEI_AMERIS", "AMERIS BANK"),
    ("LEI_LCU", "Lighthouse Federal Credit Union"),
]


def test_normalize_and_core() -> None:
    assert exact_key("  Rocket   Mortgage, LLC ") == "ROCKET MORTGAGE, LLC"
    assert normalize("Wells Fargo Bank, N.A.") == "WELLS FARGO BANK"
    assert normalize("WELLS FARGO & COMPANY") == "WELLS FARGO"
    assert normalize("HUNTINGTON NATIONAL BANK, THE") == "HUNTINGTON NATIONAL BANK"
    assert normalize("Foo Mortgage dba Bar Loans") == "FOO MORTGAGE"
    assert core("Wells Fargo Bank, National Association") == "WELLS FARGO"
    assert core("Bank of America") == ""  # nothing distinctive is left


def test_tiers() -> None:
    idx = LenderIndex(LENDERS)
    m = idx.match("ROCKET MORTGAGE, LLC")
    assert (m.lei, m.method, m.confidence) == ("LEI_ROCKET", "exact_name", "high")
    m = idx.match("BANK OF AMERICA, NATIONAL ASSOCIATION")
    assert (m.lei, m.method) == ("LEI_BOA", "normalized_name")
    m = idx.match("WELLS FARGO & COMPANY")
    assert (m.lei, m.method, m.confidence) == ("LEI_WF", "core_name", "medium")
    m = idx.match("AMERIS BANCORP")
    assert (m.lei, m.method) == ("LEI_AMERIS", "core_name")


def test_ambiguous_and_guards() -> None:
    idx = LenderIndex(LENDERS)
    assert idx.match("First National Bank").method == "ambiguous"
    # Not holding-company-like: the core tier is not tried.
    assert idx.match("Quantum Servicing Corporation").method == "none"
    # Holding-company-like, but a credit union is never matched to a non-credit-union.
    assert idx.match("Lighthouse Financial Group").method == "none"
    # A one-word core that is a common word is not accepted either.
    assert idx.match("Quantum Financial Group").method == "none"
    assert idx.match("Unknown Lender LLC").lei is None
