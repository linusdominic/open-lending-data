# Matching CFPB complaints to HMDA lenders

The CFPB Consumer Complaint Database names the company a complaint is about; HMDA
identifies lenders by LEI. There is no shared identifier, so `mortgage_complaints` links
them by name. This page describes the method, the match rates from the build on 19 November
2026, and a manual review of the riskiest tier. The code is `src/openlending/matching.py`.

## Method

Names of HMDA lenders come from `lenders.respondent_name` for every lender-year with an LEI
(2018-2025, plus pre-2018 lender-years whose ARID maps to an LEI). A complaint company is
matched at the first tier that gives exactly one LEI:

| Tier | Confidence | Rule |
|---|---|---|
| `exact_name` | high | Upper-cased, whitespace-collapsed names are identical. |
| `normalized_name` | high | Identical after removing punctuation, anything after "DBA"/"FKA"/"AKA", and legal-form words (INC, LLC, CORP, CO, COMPANY, N.A., NATIONAL ASSOCIATION, FSB, THE, AND, OF ...). |
| `core_name` | medium | Identical after also removing generic industry words (BANK, BANCORP, FINANCIAL, HOLDINGS, GROUP, MORTGAGE, HOME, LOANS, SERVICES, CREDIT UNION ...). Tried only when the complaint company looks like a holding company (BANCORP, BANCSHARES, FINANCIAL, HOLDING(S), GROUP, "& CO"); never pairs a credit union with a non-credit-union; never accepts a one-word core that is a common word (FIRST, AMERICAN, CITIZENS ...). |
| `ambiguous` | none | The first tier that found the name found several LEIs (for example "First National Bank"). No LEI is assigned. |
| `none` | none | No tier found the name. |

A match links a complaint to a lender in the same corporate family, not necessarily the same
legal entity: "WELLS FARGO & COMPANY" (the holding company named in complaints) is linked to
"Wells Fargo Bank, National Association" (the HMDA reporter).

## Results

467,257 mortgage complaints (product = "Mortgage", received 1 Dec 2011 to 17 Nov 2026) from
2,564 distinct company names. Command: the queries in
[Reproducing the numbers](../README.md#reproducing-the-numbers).

| Tier | Complaints | Share | Companies |
|---|---|---|---|
| exact_name | 69,938 | 15.0% | 393 |
| normalized_name | 133,786 | 28.6% | 259 |
| core_name | 128,700 | 27.5% | 62 |
| ambiguous | 5,322 | 1.1% | 62 |
| none | 129,511 | 27.7% | 1,788 |
| **matched (any tier)** | **332,424** | **71.1%** | **714 (27.8%)** |

43.6% of complaints are matched at high confidence. The match rate falls over time, from
85-88% in 2011-2013 to 53% in 2024-2025, as complaint volume shifts to servicers that do not
report HMDA under the name used in complaints. The largest unmatched companies are
Shellpoint Partners (17,724 complaints), Select Portfolio Servicing (15,283), Mr. Cooper Group
(13,321), U.S. Bancorp (9,166), LoanCare (7,390) and HSBC North America Holdings (4,842).
Several of these are servicers that do not originate loans, or report HMDA under a different
legal name (U.S. Bancorp's bank reports as "U.S. Bank National Association"; "US" and
"BANCORP" are both generic words, so nothing distinctive is left to match).

A matched LEI says the lender filed HMDA in some year, not in the complaint's year: of the
134,112 matched complaints received in 2018 or later, 103,047 (76.8%) are matched to an LEI
that filed HMDA in the same year.

## Manual review of the core-name tier

All 62 company names matched at the `core_name` tier were reviewed by hand, judging from the
names and from public knowledge of the companies. This is a judgement, not a check against an
authoritative ownership database.

| Judgement | Companies | Complaints |
|---|---|---|
| Same corporate family (e.g. Wells Fargo & Company -> Wells Fargo Bank NA; Ocwen Financial -> Ocwen Loan Servicing; Truist Financial -> Truist Bank; Ameris Bancorp -> Ameris Bank) | 39 | 128,294 |
| Could not tell from names (e.g. Beacon Financial Corporation -> Beacon Bank & Trust; Flagship Financial Group -> Flagship Bank; Rock Holdings -> Rock Mortgage Services) | 14 | 108 |
| Wrong (e.g. Fidelity National Financial, a title insurer -> Fidelity National Bank; Encore Capital Group, a debt buyer -> Encore Bank; Minnesota Home Financial -> Minnesota Bank & Trust; Nationwide Funding Group -> N A Nationwide Mortgage) | 9 | 298 |

So the tier is almost entirely right by complaint volume (at most 406 of 128,700 complaints,
0.3%, are wrong or uncertain) but not by company count (9 of 62 company names, 15%, are
wrong). Analyses at the level of individual small companies should filter to
`match_confidence = 'high'`.

The `normalized_name` tier was spot-checked: 25 randomly drawn company names (DuckDB
`reservoir(25 rows) repeatable (42)`) all matched the evidently same company. The
`exact_name` tier needs no review beyond the fact that it is unique.

## What this does not do

- No aliases or corporate-family tables are used: a company whose HMDA reporter has an
  unrelated name (Mr. Cooper Group / Nationstar Mortgage) is not matched.
- Name changes over time are only handled when an older name also appears in HMDA.
- A complaint about a servicer is linked to the servicer's HMDA filings, which describe
  loans it originated or purchased, not the loans it services.
