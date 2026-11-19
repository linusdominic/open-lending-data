"""Company-name normalisation and matching of CFPB complaint companies to HMDA lenders.

The Consumer Complaint Database names companies; HMDA identifies lenders by LEI. There is no
shared identifier, so the match is by name, in three tiers, and only when the result is a
single LEI:

1. ``exact_name`` (high): the upper-cased, whitespace-collapsed names are identical.
2. ``normalized_name`` (high): identical after removing punctuation and legal-form words
   (INC, LLC, CORP, N.A., NATIONAL ASSOCIATION, FSB ...).
3. ``core_name`` (medium): identical after also removing generic industry words (BANK,
   BANCORP, FINANCIAL, HOLDINGS, GROUP, MORTGAGE ...). This is what links a holding company
   such as "WELLS FARGO & COMPANY" to "Wells Fargo Bank, National Association". Because it
   is the tier most likely to be wrong, it is only tried when the complaint company looks like
   a holding company (BANCORP, BANCSHARES, FINANCIAL, HOLDING(S), GROUP, "& CO"), never pairs
   a credit union with a non-credit-union, and never accepts a one-word core that is a common
   word (FIRST, AMERICAN, CITIZENS ...). It is labelled medium.

A name that maps to more than one LEI at its tier is ``ambiguous`` and gets no LEI.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

LEGAL_TOKENS = {
    "INC", "INCORPORATED", "LLC", "LLP", "LP", "LTD", "LIMITED", "CORP", "CORPORATION", "CO",
    "COMPANY", "NA", "FSB", "SSB", "PLC", "PC", "THE", "AND", "OF",
}  # fmt: skip
LEGAL_PHRASES = [
    "NATIONAL ASSOCIATION",
    "N A",
    "L L C",
    "F S B",
    "S S B",
    "A FEDERAL SAVINGS BANK",
    "FEDERAL SAVINGS BANK",
    "A DIVISION OF",
]
GENERIC_TOKENS = {
    "BANK", "BANCORP", "BANCSHARES", "BANKING", "FINANCIAL", "FINANCE", "SERVICES", "SERVICING",
    "GROUP", "HOLDINGS", "HOLDING", "MORTGAGE", "HOME", "LOANS", "LOAN", "LENDING", "TRUST",
    "SAVINGS", "FEDERAL", "CREDIT", "UNION", "FUNDING", "CAPITAL", "USA", "US", "AMERICA",
}  # fmt: skip


HOLDING_MARKERS = re.compile(
    r"\b(BANCORP|BANCSHARES|FINANCIAL|HOLDINGS?|GROUP)\b|&\s*CO(MPANY)?\b|\bAND COMPANY\b"
)
GENERIC_CORES = {
    "FIRST", "SECOND", "THIRD", "AMERICAN", "NATIONAL", "CITY", "COMMUNITY", "UNITED", "CITIZENS",
    "PEOPLES", "SECURITY", "GREAT", "STANDARD", "PACIFIC", "ATLANTIC", "SOUTHERN", "NORTHERN",
    "WESTERN", "EASTERN", "CENTRAL", "MIDWEST", "SOUTHWEST", "NORTHWEST", "HERITAGE", "LIBERTY",
    "PREMIER", "PIONEER", "GUARANTY", "FIDELITY", "COMMERCE", "STATE", "MUTUAL", "PRIME",
    "FREEDOM", "SUMMIT", "EMPIRE", "OMNI", "UNIFIED", "QUANTUM", "LINCOLN", "INSIGHT", "DIGITAL",
}  # fmt: skip


def is_credit_union(name: str) -> bool:
    return "CREDIT UNION" in _base(name) or _base(name).endswith(" FCU")


def holding_like(name: str) -> bool:
    return bool(HOLDING_MARKERS.search(name.upper()))


def _base(name: str) -> str:
    s = name.upper()
    s = re.split(r"\b(?:D/B/A|DBA|F/K/A|FKA|A/K/A|AKA)\b", s)[0]
    s = s.replace("&", " AND ")
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def exact_key(name: str) -> str:
    return re.sub(r"\s+", " ", name.upper()).strip()


def normalize(name: str) -> str:
    """Remove punctuation and legal-form words: 'Wells Fargo Bank, N.A.' -> 'WELLS FARGO BANK'."""
    s = f" {_base(name)} "
    for phrase in LEGAL_PHRASES:
        s = s.replace(f" {phrase} ", " ")
    tokens = [t for t in s.split() if t not in LEGAL_TOKENS]
    return " ".join(tokens)


def core(name: str) -> str:
    """Normalised name without generic industry words: 'WELLS FARGO BANK' -> 'WELLS FARGO'."""
    tokens = [t for t in normalize(name).split() if t not in GENERIC_TOKENS]
    out = " ".join(tokens)
    return out if len(out.replace(" ", "")) >= 4 else ""


@dataclass(frozen=True)
class Match:
    lei: str | None
    lender_name: str | None
    method: str  # exact_name | normalized_name | core_name | ambiguous | none
    confidence: str  # high | medium | none


class LenderIndex:
    """Name -> LEI lookups at three tiers built from (lei, name) pairs."""

    def __init__(self, lenders: Iterable[tuple[str, str]]) -> None:
        self.tiers: dict[str, dict[str, dict[str, str]]] = {
            "exact_name": defaultdict(dict),
            "normalized_name": defaultdict(dict),
            "core_name": defaultdict(dict),
        }
        for lei, name in lenders:
            if not lei or not name:
                continue
            for tier, fn in (
                ("exact_name", exact_key),
                ("normalized_name", normalize),
                ("core_name", core),
            ):
                key = fn(name)
                if key:
                    self.tiers[tier][key].setdefault(lei, name)

    def match(self, company: str) -> Match:
        ambiguous = False
        for tier, fn, conf in (
            ("exact_name", exact_key, "high"),
            ("normalized_name", normalize, "high"),
            ("core_name", core, "medium"),
        ):
            key = fn(company)
            if not key:
                continue
            hits = self.tiers[tier].get(key)
            if not hits:
                continue
            if tier == "core_name":
                if not holding_like(company) or key in GENERIC_CORES:
                    continue
                cu = is_credit_union(company)
                hits = {k: v for k, v in hits.items() if is_credit_union(v) == cu}
                if not hits:
                    continue
            if len(hits) == 1:
                ((lei, name),) = hits.items()
                return Match(lei, name, tier, conf)
            ambiguous = True
            break
        if ambiguous:
            return Match(None, None, "ambiguous", "none")
        return Match(None, None, "none", "none")
