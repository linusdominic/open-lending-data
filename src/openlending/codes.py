"""Code lists (domains) and labels.

2018+ codes follow the FFIEC "Filing Instructions Guide for HMDA Data Collected in <year>" and
are cross-checked against the enumerations in the HMDA Platform source code
(github.com/cfpb/hmda-platform, ``common/src/main/scala/hmda/model/filing/lar/enums``, commit
eec90f87, read 2026-11-19). Obvious spelling errors in the platform labels are corrected.

Pre-2018 codes follow the CFPB "HMDA Loan/Application Register Code Sheet"
(https://files.consumerfinance.gov/hmda-historic-data-dictionaries/lar_record_codes.pdf, linked
from https://www.consumerfinance.gov/data-research/hmda/historic-data/). That sheet does not
list agency code 4 (Office of Thrift Supervision, abolished in 2011); it is included here
because 2007-2011 filings use it.

``EXEMPT`` (1111) is a valid value only in fields that institutions with a partial exemption
under the Economic Growth, Regulatory Relief, and Consumer Protection Act (EGRRCPA, 2018) may
leave unreported. It is listed in those domains and nowhere else, so the domain check flags a
1111 that appears in a field where it is not allowed.
"""

from __future__ import annotations

Domain = dict[int, str]

EXEMPT = 1111
EXEMPT_LABEL = "Exempt"

# ---------------------------------------------------------------------------------------------
# 2018 and later (FFIEC public LAR)
# ---------------------------------------------------------------------------------------------

ACTION_TAKEN: Domain = {
    1: "Loan originated",
    2: "Application approved but not accepted",
    3: "Application denied",
    4: "Application withdrawn by applicant",
    5: "File closed for incompleteness",
    6: "Purchased loan",
    7: "Preapproval request denied",
    8: "Preapproval request approved but not accepted",
}
PURCHASER_TYPE: Domain = {
    0: "Not applicable",
    1: "Fannie Mae",
    2: "Ginnie Mae",
    3: "Freddie Mac",
    4: "Farmer Mac",
    5: "Private securitizer",
    6: "Commercial bank, savings bank, or savings association",
    71: "Credit union, mortgage company, or finance company",
    72: "Life insurance company",
    8: "Affiliate institution",
    9: "Other type of purchaser",
}
PREAPPROVAL: Domain = {1: "Preapproval requested", 2: "Preapproval not requested"}
LOAN_TYPE: Domain = {
    1: "Conventional",
    2: "FHA insured",
    3: "VA guaranteed",
    4: "USDA RHS or FSA guaranteed",
}
LOAN_PURPOSE: Domain = {
    1: "Home purchase",
    2: "Home improvement",
    31: "Refinancing",
    32: "Cash-out refinancing",
    4: "Other purpose",
    5: "Not applicable",
}
LIEN_STATUS: Domain = {1: "Secured by a first lien", 2: "Secured by a subordinate lien"}
REVERSE_MORTGAGE: Domain = {1: "Reverse mortgage", 2: "Not a reverse mortgage", EXEMPT: "Exempt"}
OPEN_END_LOC: Domain = {
    1: "Open-end line of credit",
    2: "Not an open-end line of credit",
    EXEMPT: "Exempt",
}
BUSINESS_PURPOSE: Domain = {
    1: "Primarily for a business or commercial purpose",
    2: "Not primarily for a business or commercial purpose",
    EXEMPT: "Exempt",
}
HOEPA_STATUS: Domain = {
    1: "High-cost mortgage",
    2: "Not a high-cost mortgage",
    3: "Not applicable",
}
YES_NO_FEATURE: dict[str, Domain] = {
    "negative_amortization": {1: "Negative amortization", 2: "No negative amortization"},
    "interest_only_payment": {1: "Interest-only payments", 2: "No interest-only payments"},
    "balloon_payment": {1: "Balloon payment", 2: "No balloon payment"},
    "other_nonamortizing_features": {
        1: "Other non-fully amortizing features",
        2: "No other non-fully amortizing features",
    },
}
for _d in YES_NO_FEATURE.values():
    _d[EXEMPT] = EXEMPT_LABEL
CONSTRUCTION_METHOD: Domain = {1: "Site-built", 2: "Manufactured home"}
OCCUPANCY_TYPE: Domain = {
    1: "Principal residence",
    2: "Second residence",
    3: "Investment property",
}
MH_SECURED_PROPERTY: Domain = {
    1: "Manufactured home and land",
    2: "Manufactured home and not land",
    3: "Not applicable",
    EXEMPT: EXEMPT_LABEL,
}
MH_LAND_INTEREST: Domain = {
    1: "Direct ownership",
    2: "Indirect ownership",
    3: "Paid leasehold",
    4: "Unpaid leasehold",
    5: "Not applicable",
    EXEMPT: EXEMPT_LABEL,
}
CREDIT_SCORE_TYPE: Domain = {
    1: "Equifax Beacon 5.0",
    2: "Experian Fair Isaac",
    3: "FICO Risk Score Classic 04",
    4: "FICO Risk Score Classic 98",
    5: "VantageScore 2.0",
    6: "VantageScore 3.0",
    7: "More than one credit scoring model",
    8: "Other credit scoring model",
    9: "Not applicable",
    10: "No co-applicant",
    11: "FICO Score 9",
    12: "FICO Score 8",
    13: "FICO Score 10",
    14: "FICO Score 10 T",
    15: "VantageScore 4.0",
    EXEMPT: EXEMPT_LABEL,
}
ETHNICITY: Domain = {
    1: "Hispanic or Latino",
    11: "Mexican",
    12: "Puerto Rican",
    13: "Cuban",
    14: "Other Hispanic or Latino",
    2: "Not Hispanic or Latino",
    3: "Information not provided by applicant in mail, internet, or telephone application",
    4: "Not applicable",
    5: "No co-applicant",
}
RACE: Domain = {
    1: "American Indian or Alaska Native",
    2: "Asian",
    21: "Asian Indian",
    22: "Chinese",
    23: "Filipino",
    24: "Japanese",
    25: "Korean",
    26: "Vietnamese",
    27: "Other Asian",
    3: "Black or African American",
    4: "Native Hawaiian or Other Pacific Islander",
    41: "Native Hawaiian",
    42: "Guamanian or Chamorro",
    43: "Samoan",
    44: "Other Pacific Islander",
    5: "White",
    6: "Information not provided by applicant in mail, internet, or telephone application",
    7: "Not applicable",
    8: "No co-applicant",
}
SEX: Domain = {
    1: "Male",
    2: "Female",
    3: "Information not provided by applicant in mail, internet, or telephone application",
    4: "Not applicable",
    5: "No co-applicant",
    6: "Applicant selected both male and female",
}
OBSERVED: Domain = {
    1: "Collected on the basis of visual observation or surname",
    2: "Not collected on the basis of visual observation or surname",
    3: "Not applicable",
    4: "No co-applicant",
}
SUBMISSION_OF_APPLICATION: Domain = {
    1: "Submitted directly to the institution",
    2: "Not submitted directly to the institution",
    3: "Not applicable",
    EXEMPT: EXEMPT_LABEL,
}
INITIALLY_PAYABLE: Domain = {
    1: "Initially payable to the institution",
    2: "Not initially payable to the institution",
    3: "Not applicable",
    EXEMPT: EXEMPT_LABEL,
}
AUS: Domain = {
    1: "Desktop Underwriter (DU)",
    2: "Loan Prospector (LP) or Loan Product Advisor",
    3: "Technology Open to Approved Lenders (TOTAL) Scorecard",
    4: "Guaranteed Underwriting System (GUS)",
    5: "Other",
    6: "Not applicable",
    7: "Internal proprietary system",
    EXEMPT: EXEMPT_LABEL,
}
DENIAL_REASON: Domain = {
    1: "Debt-to-income ratio",
    2: "Employment history",
    3: "Credit history",
    4: "Collateral",
    5: "Insufficient cash (downpayment, closing costs)",
    6: "Unverifiable information",
    7: "Credit application incomplete",
    8: "Mortgage insurance denied",
    9: "Other",
    10: "Not applicable",
    EXEMPT: EXEMPT_LABEL,
}
AGENCY: Domain = {
    1: "Office of the Comptroller of the Currency (OCC)",
    2: "Federal Reserve System (FRS)",
    3: "Federal Deposit Insurance Corporation (FDIC)",
    4: "Office of Thrift Supervision (OTS)",
    5: "National Credit Union Administration (NCUA)",
    7: "Department of Housing and Urban Development (HUD)",
    9: "Consumer Financial Protection Bureau (CFPB)",
}
OTHER_LENDER_CODE: Domain = {
    0: "Depository institution",
    1: "Mortgage bank subsidiary of a bank holding company or savings and loan holding company",
    2: "Independent mortgage company",
    3: "Mortgage bank affiliate of a depository institution",
    5: "Affiliate of a depository institution",
}

# Text-valued categorical fields in the 2018+ public LAR: the allowed values.
CONFORMING_LOAN_LIMIT = ["C", "NC", "U", "NA"]
DERIVED_LOAN_PRODUCT_TYPE = [
    f"{t}:{lien}"
    for t in ("Conventional", "FHA", "VA", "FSA/RHS")
    for lien in ("First Lien", "Subordinate Lien")
]
DERIVED_DWELLING_CATEGORY = [
    "Single Family (1-4 Units):Site-Built",
    "Multifamily:Site-Built",
    "Single Family (1-4 Units):Manufactured",
    "Multifamily:Manufactured",
]
DERIVED_ETHNICITY = [
    "Hispanic or Latino",
    "Not Hispanic or Latino",
    "Joint",
    "Ethnicity Not Available",
    "Free Form Text Only",
]
DERIVED_RACE = [
    "American Indian or Alaska Native",
    "Asian",
    "Black or African American",
    "Native Hawaiian or Other Pacific Islander",
    "White",
    "2 or more minority races",
    "Joint",
    "Free Form Text Only",
    "Race Not Available",
]
DERIVED_SEX = ["Male", "Female", "Joint", "Sex Not Available"]
TOTAL_UNITS = ["1", "2", "3", "4", "5-24", "25-49", "50-99", "100-149", ">149"]
DEBT_TO_INCOME = (
    ["<20%", "20%-<30%", "30%-<36%"]
    + [str(i) for i in range(36, 50)]
    + ["50%-60%", ">60%", "NA", "Exempt"]
)
AGE = ["<25", "25-34", "35-44", "45-54", "55-64", "65-74", ">74", "8888", "9999"]
AGE_ABOVE_62 = ["Yes", "No", "NA"]

# ---------------------------------------------------------------------------------------------
# 2007-2017 (CFPB historic LAR, "codes" files)
# ---------------------------------------------------------------------------------------------

H_LOAN_TYPE: Domain = {
    1: "Conventional",
    2: "FHA-insured",
    3: "VA-guaranteed",
    4: "FSA/RHS",
}
H_PROPERTY_TYPE: Domain = {
    1: "One-to-four family dwelling (other than manufactured housing)",
    2: "Manufactured housing",
    3: "Multifamily dwelling",
}
H_LOAN_PURPOSE: Domain = {1: "Home purchase", 2: "Home improvement", 3: "Refinancing"}
H_OWNER_OCCUPANCY: Domain = {
    1: "Owner-occupied as a principal dwelling",
    2: "Not owner-occupied",
    3: "Not applicable",
}
H_PREAPPROVAL: Domain = {
    1: "Preapproval was requested",
    2: "Preapproval was not requested",
    3: "Not applicable",
}
H_ETHNICITY: Domain = {
    1: "Hispanic or Latino",
    2: "Not Hispanic or Latino",
    3: "Information not provided by applicant in mail, Internet, or telephone application",
    4: "Not applicable",
    5: "No co-applicant",
}
H_RACE: Domain = {
    1: "American Indian or Alaska Native",
    2: "Asian",
    3: "Black or African American",
    4: "Native Hawaiian or Other Pacific Islander",
    5: "White",
    6: "Information not provided by applicant in mail, Internet, or telephone application",
    7: "Not applicable",
    8: "No co-applicant",
}
H_SEX: Domain = {
    1: "Male",
    2: "Female",
    3: "Information not provided by applicant in mail, Internet, or telephone application",
    4: "Not applicable",
    5: "No co-applicant",
}
H_PURCHASER_TYPE: Domain = {
    0: "Loan was not originated or was not sold in calendar year covered by register",
    1: "Fannie Mae",
    2: "Ginnie Mae",
    3: "Freddie Mac",
    4: "Farmer Mac",
    5: "Private securitization",
    6: "Commercial bank, savings bank or savings association",
    7: "Life insurance company, credit union, mortgage bank, or finance company",
    8: "Affiliate institution",
    9: "Other type of purchaser",
}
H_DENIAL_REASON: Domain = {k: v for k, v in DENIAL_REASON.items() if k <= 9}
H_HOEPA: Domain = {1: "HOEPA loan", 2: "Not a HOEPA loan"}
H_LIEN_STATUS: Domain = {
    1: "Secured by a first lien",
    2: "Secured by a subordinate lien",
    3: "Not secured by a lien",
    4: "Not applicable (purchased loans)",
}

# ---------------------------------------------------------------------------------------------
# Harmonised "core" codes (hmda_lar_core), shared by every year 2007-2025
# ---------------------------------------------------------------------------------------------

CORE_LOAN_PURPOSE: Domain = {
    1: "Home purchase",
    2: "Home improvement",
    3: "Refinancing (including cash-out)",
    4: "Other purpose (2018+ only)",
    5: "Not applicable (2018+ only)",
}
CORE_PROPERTY_TYPE: Domain = {
    1: "One-to-four family, site-built",
    2: "One-to-four family, manufactured housing",
    3: "Multifamily (5+ units)",
}
CORE_OCCUPANCY: Domain = {
    1: "Principal residence",
    2: "Not a principal residence (second home or investment)",
    3: "Not applicable (pre-2018 only)",
}
CORE_PREAPPROVAL: Domain = {
    1: "Preapproval requested",
    2: "Preapproval not requested",
    3: "Not applicable (pre-2018 only)",
}
CORE_PURCHASER_TYPE: Domain = {**{k: v for k, v in H_PURCHASER_TYPE.items() if k != 0}}
CORE_PURCHASER_TYPE[0] = "Not sold (or not applicable)"
CORE_LIEN_STATUS: Domain = dict(H_LIEN_STATUS)
CORE_HOEPA: Domain = {1: "High-cost (HOEPA) loan", 2: "Not a high-cost loan", 3: "Not applicable"}
CORE_ETHNICITY: Domain = dict(H_ETHNICITY)
CORE_RACE: Domain = dict(H_RACE)
CORE_SEX: Domain = {**H_SEX, 6: "Applicant selected both male and female (2018+ only)"}
CORE_DENIAL_REASON: Domain = dict(H_DENIAL_REASON)
CORE_ERA: dict[str, str] = {
    "pre2018": "CFPB historic LAR, 2007-2017 format",
    "2018plus": "FFIEC Snapshot public LAR, 2018 format",
}
