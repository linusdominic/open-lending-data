"""Column specifications for every harmonised table.

The data dictionary (docs/data-dictionary.md and .json), the typed SELECT statements in
:mod:`openlending.transform` and the domain checks in :mod:`openlending.validate` are all
generated from these specs, so they cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from openlending import codes as C

Kind = Literal["year", "id", "text", "category", "code", "number", "integer", "date", "bool"]


@dataclass(frozen=True)
class Col:
    name: str
    kind: Kind
    description: str
    sql_type: str = "VARCHAR"
    domain: C.Domain | None = None  # for kind == "code"
    allowed: list[str] | None = None  # for kind == "category"
    na_reason: bool = False  # numeric field that can be "NA" or "Exempt"
    label: bool = False  # emit <name>_label
    source: str | None = None  # raw column name when it differs
    nullable: bool = True
    years: str = ""  # free text, e.g. "2018+" or "2007-2017"
    notes: str = ""
    extra: dict[str, str] = field(default_factory=dict)


def _code(name: str, domain: C.Domain, desc: str, **kw: object) -> Col:
    return Col(name, "code", desc, "SMALLINT", domain=domain, label=True, **kw)  # type: ignore[arg-type]


def _num(name: str, desc: str, sql_type: str = "DOUBLE", **kw: object) -> Col:
    return Col(name, "number", desc, sql_type, na_reason=True, **kw)  # type: ignore[arg-type]


def _cat(name: str, allowed: list[str], desc: str) -> Col:
    return Col(name, "category", desc, "VARCHAR", allowed=allowed)


def _int(name: str, desc: str, sql_type: str = "INTEGER") -> Col:
    return Col(name, "integer", desc, sql_type)


# ---------------------------------------------------------------------------------------------
# hmda_lar: FFIEC Snapshot public LAR, 2018 onward, every published field, typed.
# ---------------------------------------------------------------------------------------------

_ETH = "Ethnicity ({who}), field {i} of 5. Codes 11-14 are Hispanic or Latino subgroups."
_RACE = "Race ({who}), field {i} of 5. Codes 21-27 and 41-44 are Asian and NHOPI subgroups."

HMDA_LAR: list[Col] = [
    Col("activity_year", "year", "Calendar year of the final action.", "SMALLINT", nullable=False),
    Col(
        "record_id",
        "id",
        "Row number of the record in the published CSV (1 = first data line). Together with "
        "activity_year it identifies a record; the public LAR has no loan identifier.",
        "INTEGER",
        nullable=False,
    ),
    Col(
        "lei",
        "id",
        "Legal Entity Identifier of the reporting institution, upper-cased.",
        nullable=False,
    ),
    Col(
        "derived_msa_md",
        "text",
        "MSA/MD of the property, derived by the FFIEC; 99999 means not in an MSA/MD.",
    ),
    Col("state_code", "text", "Two-letter postal state code of the property; NULL when NA."),
    Col("county_code", "text", "Five-digit state+county FIPS code; NULL when NA."),
    Col("census_tract", "text", "Eleven-digit census tract (state+county+tract); NULL when NA."),
    _cat(
        "conforming_loan_limit",
        C.CONFORMING_LOAN_LIMIT,
        "Whether the loan amount is within the GSE conforming loan limit (C, NC, U = "
        "undetermined, NA). Derived by the FFIEC.",
    ),
    _cat(
        "derived_loan_product_type",
        C.DERIVED_LOAN_PRODUCT_TYPE,
        "Loan type and lien status, derived by the FFIEC.",
    ),
    _cat(
        "derived_dwelling_category",
        C.DERIVED_DWELLING_CATEGORY,
        "Construction method and total units, derived by the FFIEC.",
    ),
    _cat(
        "derived_ethnicity",
        C.DERIVED_ETHNICITY,
        "Applicant and co-applicant ethnicity combined, derived by the FFIEC.",
    ),
    _cat(
        "derived_race",
        C.DERIVED_RACE,
        "Applicant and co-applicant race combined, derived by the FFIEC.",
    ),
    _cat("derived_sex", C.DERIVED_SEX, "Applicant and co-applicant sex combined, by the FFIEC."),
    _code("action_taken", C.ACTION_TAKEN, "Action taken on the application or loan."),
    _code("purchaser_type", C.PURCHASER_TYPE, "Type of entity that purchased the loan."),
    _code("preapproval", C.PREAPPROVAL, "Whether a preapproval was requested."),
    _code("loan_type", C.LOAN_TYPE, "Loan type (insurance or guarantee)."),
    _code("loan_purpose", C.LOAN_PURPOSE, "Purpose of the loan."),
    _code("lien_status", C.LIEN_STATUS, "Lien status of the property securing the loan."),
    _code("reverse_mortgage", C.REVERSE_MORTGAGE, "Whether the loan is a reverse mortgage."),
    _code(
        "open_end_line_of_credit",
        C.OPEN_END_LOC,
        "Whether the loan is an open-end line of credit.",
    ),
    _code(
        "business_or_commercial_purpose",
        C.BUSINESS_PURPOSE,
        "Whether the loan is primarily for a business or commercial purpose.",
    ),
    _num(
        "loan_amount",
        "Loan amount in US dollars. The public file reports the midpoint of the $10,000 "
        "interval containing the amount (e.g. 205000 for 200,000-209,999).",
    ),
    _num(
        "combined_loan_to_value_ratio",
        "Combined loan-to-value ratio, percent. Published as loan_to_value_ratio in the 2018 "
        "file and as combined_loan_to_value_ratio from 2019; same field.",
    ),
    _num("interest_rate", "Interest rate, percent."),
    _num(
        "rate_spread",
        "Difference between the APR and the average prime offer rate (APOR) for a comparable "
        "transaction, percentage points. Reported for all covered originations; can be negative.",
    ),
    _code("hoepa_status", C.HOEPA_STATUS, "Whether the loan is a high-cost mortgage (HOEPA)."),
    _num("total_loan_costs", "Total loan costs (closed-end loans), US dollars."),
    _num("total_points_and_fees", "Total points and fees (open-end/QM), US dollars."),
    _num("origination_charges", "Total origination charges, US dollars."),
    _num("discount_points", "Discount points, US dollars."),
    _num("lender_credits", "Lender credits, US dollars."),
    _num("loan_term", "Loan term in months.", "INTEGER"),
    _num("prepayment_penalty_term", "Prepayment penalty term in months.", "INTEGER"),
    _num("intro_rate_period", "Introductory rate period in months.", "INTEGER"),
    _code("negative_amortization", C.YES_NO_FEATURE["negative_amortization"], "Negative amort."),
    _code(
        "interest_only_payment",
        C.YES_NO_FEATURE["interest_only_payment"],
        "Interest-only payments.",
    ),
    _code("balloon_payment", C.YES_NO_FEATURE["balloon_payment"], "Balloon payment."),
    _code(
        "other_nonamortizing_features",
        C.YES_NO_FEATURE["other_nonamortizing_features"],
        "Other non-fully amortizing features.",
    ),
    _num(
        "property_value",
        "Property value in US dollars; the public file reports the midpoint of the $10,000 "
        "interval.",
    ),
    _code("construction_method", C.CONSTRUCTION_METHOD, "Construction method of the dwelling."),
    _code("occupancy_type", C.OCCUPANCY_TYPE, "Occupancy type of the dwelling."),
    _code(
        "manufactured_home_secured_property_type",
        C.MH_SECURED_PROPERTY,
        "Manufactured home secured property type.",
    ),
    _code(
        "manufactured_home_land_property_interest",
        C.MH_LAND_INTEREST,
        "Manufactured home land property interest.",
    ),
    _cat("total_units", C.TOTAL_UNITS, "Number of individual dwelling units (banded above 4)."),
    _num(
        "multifamily_affordable_units",
        "Income-restricted units in a multifamily dwelling.",
        "INTEGER",
    ),
    _num("income", "Gross annual income relied on, in thousands of US dollars.", "INTEGER"),
    _cat(
        "debt_to_income_ratio",
        C.DEBT_TO_INCOME,
        "Debt-to-income ratio, banded by the FFIEC in the public file; 36-49 are exact.",
    ),
    _code(
        "applicant_credit_score_type",
        C.CREDIT_SCORE_TYPE,
        "Credit scoring model (applicant). The score itself is not public.",
    ),
    _code(
        "co_applicant_credit_score_type",
        C.CREDIT_SCORE_TYPE,
        "Credit scoring model (co-applicant).",
    ),
    *[
        _code(f"applicant_ethnicity_{i}", C.ETHNICITY, _ETH.format(who="applicant", i=i))
        for i in range(1, 6)
    ],
    *[
        _code(f"co_applicant_ethnicity_{i}", C.ETHNICITY, _ETH.format(who="co-applicant", i=i))
        for i in range(1, 6)
    ],
    _code("applicant_ethnicity_observed", C.OBSERVED, "Ethnicity collected by observation."),
    _code("co_applicant_ethnicity_observed", C.OBSERVED, "Co-applicant ethnicity observed."),
    *[
        _code(f"applicant_race_{i}", C.RACE, _RACE.format(who="applicant", i=i))
        for i in range(1, 6)
    ],
    *[
        _code(f"co_applicant_race_{i}", C.RACE, _RACE.format(who="co-applicant", i=i))
        for i in range(1, 6)
    ],
    _code("applicant_race_observed", C.OBSERVED, "Race collected by visual observation."),
    _code("co_applicant_race_observed", C.OBSERVED, "Co-applicant race observed."),
    _code("applicant_sex", C.SEX, "Sex of applicant."),
    _code("co_applicant_sex", C.SEX, "Sex of co-applicant."),
    _code("applicant_sex_observed", C.OBSERVED, "Sex collected by visual observation."),
    _code("co_applicant_sex_observed", C.OBSERVED, "Co-applicant sex observed."),
    _cat("applicant_age", C.AGE, "Age band of applicant; 8888 = not applicable."),
    _cat(
        "co_applicant_age",
        C.AGE,
        "Age band of co-applicant; 8888 = not applicable, 9999 = no co-applicant.",
    ),
    _cat("applicant_age_above_62", C.AGE_ABOVE_62, "Whether the applicant is 62 or older."),
    _cat("co_applicant_age_above_62", C.AGE_ABOVE_62, "Whether the co-applicant is 62 or older."),
    _code(
        "submission_of_application",
        C.SUBMISSION_OF_APPLICATION,
        "Whether the application was submitted directly to the institution.",
    ),
    _code(
        "initially_payable_to_institution",
        C.INITIALLY_PAYABLE,
        "Whether the obligation was initially payable to the institution.",
    ),
    *[
        _code(f"aus_{i}", C.AUS, f"Automated underwriting system, field {i} of 5.")
        for i in range(1, 6)
    ],
    *[
        _code(f"denial_reason_{i}", C.DENIAL_REASON, f"Reason for denial, field {i} of 4.")
        for i in range(1, 5)
    ],
    _int("tract_population", "Total population of the census tract."),
    Col(
        "tract_minority_population_percent",
        "integer",
        "Minority population as a percent of tract population.",
        "DOUBLE",
    ),
    _int("ffiec_msa_md_median_family_income", "FFIEC median family income of the MSA/MD, USD."),
    Col(
        "tract_to_msa_income_percentage",
        "integer",
        "Tract median family income as a percent of the MSA/MD median family income.",
        "DOUBLE",
    ),
    _int("tract_owner_occupied_units", "Owner-occupied dwellings in the tract."),
    _int("tract_one_to_four_family_homes", "One-to-four family dwellings in the tract."),
    _int("tract_median_age_of_housing_units", "Median age of housing units in the tract."),
]

# Columns that come from the raw file (everything except record_id).
HMDA_LAR_RAW_COLUMNS = [c.name for c in HMDA_LAR if c.name != "record_id"]

# ---------------------------------------------------------------------------------------------
# hmda_lar_core: one schema for every covered year, 2007 onward.
# ---------------------------------------------------------------------------------------------

HMDA_LAR_CORE: list[Col] = [
    Col("activity_year", "year", "Calendar year of the final action.", "SMALLINT", nullable=False),
    Col(
        "record_id",
        "id",
        "Row number in the source file, unique within a year.",
        "INTEGER",
        nullable=False,
    ),
    Col(
        "source_era",
        "category",
        "Which published format the row came from.",
        allowed=list(C.CORE_ERA),
        nullable=False,
    ),
    Col(
        "lender_key",
        "id",
        "Key into the lenders table: the LEI from 2018, 'agency_code-respondent_id' (the "
        "'ARID' used by the FFIEC) before 2018.",
        nullable=False,
    ),
    Col("lei", "id", "Legal Entity Identifier (2018+; NULL before 2018)."),
    Col(
        "respondent_id", "id", "Pre-2018 respondent identifier (10 characters).", years="2007-2017"
    ),
    Col(
        "agency_code",
        "code",
        "Supervisory agency of the reporter. Pre-2018 from the LAR; "
        "2018+ from the Transmittal Sheet.",
        "SMALLINT",
        domain=C.AGENCY,
        label=True,
    ),
    _code("loan_type", C.LOAN_TYPE, "Loan type. Same codes in both eras."),
    _code(
        "property_type",
        C.CORE_PROPERTY_TYPE,
        "Dwelling type. Pre-2018 property_type; 2018+ from construction_method and total_units.",
    ),
    _code(
        "loan_purpose",
        C.CORE_LOAN_PURPOSE,
        "Loan purpose. 2018+ codes 31 and 32 (refinance, cash-out refinance) map to 3.",
    ),
    _code(
        "occupancy",
        C.CORE_OCCUPANCY,
        "Occupancy. 2018+ second residence (2) and investment property (3) map to 2.",
    ),
    _code("preapproval", C.CORE_PREAPPROVAL, "Preapproval requested."),
    _code("action_taken", C.ACTION_TAKEN, "Action taken. Same codes 1-8 in both eras."),
    _num(
        "loan_amount",
        "Loan amount in US dollars. Pre-2018: reported thousands x 1000. 2018+: midpoint of the "
        "$10,000 interval. Not comparable at the $10,000 level.",
    ),
    _num("applicant_income_000s", "Gross annual income, thousands of US dollars.", "INTEGER"),
    Col("msa_md", "text", "MSA/MD code as published that year (delineations change)."),
    Col("state_fips", "text", "Two-digit state FIPS code."),
    Col("county_fips", "text", "Five-digit state+county FIPS code."),
    Col("census_tract", "text", "Eleven-digit census tract (state+county+6-digit tract)."),
    _code(
        "applicant_ethnicity",
        C.CORE_ETHNICITY,
        "Applicant ethnicity (first field; 2018+ subgroups 11-14 map to 1).",
    ),
    _code("co_applicant_ethnicity", C.CORE_ETHNICITY, "Co-applicant ethnicity (first field)."),
    *[
        _code(
            f"applicant_race_{i}",
            C.CORE_RACE,
            f"Applicant race field {i}; 2018+ subgroups map to major groups 2 and 4.",
        )
        for i in range(1, 6)
    ],
    *[
        _code(f"co_applicant_race_{i}", C.CORE_RACE, f"Co-applicant race field {i}.")
        for i in range(1, 6)
    ],
    _code("applicant_sex", C.CORE_SEX, "Applicant sex."),
    _code("co_applicant_sex", C.CORE_SEX, "Co-applicant sex."),
    _cat(
        "derived_race",
        C.DERIVED_RACE,
        "FFIEC 2018 derived-race rule applied to both eras by this project (see "
        "docs/changes-over-time.md). For 2018+ it reproduces the FFIEC's own derived_race.",
    ),
    _cat("derived_ethnicity", C.DERIVED_ETHNICITY, "FFIEC 2018 derived-ethnicity rule, both eras."),
    _cat("derived_sex", C.DERIVED_SEX, "FFIEC 2018 derived-sex rule, both eras."),
    _code("purchaser_type", C.CORE_PURCHASER_TYPE, "Purchaser type; 2018+ 71 and 72 map to 7."),
    *[
        _code(
            f"denial_reason_{i}",
            C.CORE_DENIAL_REASON,
            f"Denial reason {i} of 3 (2018+ field 4 is dropped; code 10 'not applicable' "
            "becomes NULL).",
        )
        for i in range(1, 4)
    ],
    _num("rate_spread", "Rate spread as published (definitions differ by era; see docs)."),
    Col(
        "higher_priced",
        "bool",
        "Originated loan with a rate spread at or above the pre-2018 HMDA reporting threshold "
        "(APOR + 1.5 pp first lien, + 3.5 pp subordinate lien). Comparable from 2010 (applications "
        "after 1 Oct 2009); NULL for non-originations and for 2007-2009.",
        "BOOLEAN",
    ),
    _code("hoepa_status", C.CORE_HOEPA, "High-cost (HOEPA) status."),
    Col(
        "application_date_before_2004",
        "bool",
        "Pre-2018 application date indicator: true when "
        "the application was taken before 1 Jan 2004 (some 2007 records); NULL from 2018.",
        "BOOLEAN",
    ),
    _code("lien_status", C.CORE_LIEN_STATUS, "Lien status; codes 3 and 4 only occur pre-2018."),
    _code("open_end_line_of_credit", C.OPEN_END_LOC, "2018+ only; NULL before 2018."),
    _code("reverse_mortgage", C.REVERSE_MORTGAGE, "2018+ only; NULL before 2018."),
    _code("business_or_commercial_purpose", C.BUSINESS_PURPOSE, "2018+ only; NULL before 2018."),
    _int("tract_population", "Tract population."),
    Col(
        "tract_minority_population_percent",
        "integer",
        "Tract minority population, percent.",
        "DOUBLE",
    ),
    _int("ffiec_msa_md_median_family_income", "FFIEC/HUD median family income of the MSA/MD."),
    Col("tract_to_msa_income_percentage", "integer", "Tract to MSA/MD income, percent.", "DOUBLE"),
    _int("tract_owner_occupied_units", "Owner-occupied units in the tract."),
    _int("tract_one_to_four_family_homes", "One-to-four family homes in the tract."),
]

# ---------------------------------------------------------------------------------------------
# Supporting tables (described for the data dictionary; built in openlending.transform).
# ---------------------------------------------------------------------------------------------

LENDERS: list[Col] = [
    Col("activity_year", "year", "HMDA activity year.", "SMALLINT", nullable=False),
    Col(
        "lender_key", "id", "LEI (2018+) or 'agency_code-respondent_id' (pre-2018).", nullable=False
    ),
    Col(
        "lei",
        "id",
        "Legal Entity Identifier. Pre-2018 rows are filled from the FFIEC "
        "ARID-to-LEI crosswalk where the institution later reported with an LEI.",
    ),
    Col("respondent_id", "id", "Pre-2018 respondent identifier."),
    Col("agency_code", "code", "Supervisory agency.", "SMALLINT", domain=C.AGENCY, label=True),
    Col("respondent_name", "text", "Institution name as reported on the Transmittal Sheet."),
    Col("respondent_city", "text", "City on the Transmittal Sheet."),
    Col("respondent_state", "text", "State on the Transmittal Sheet."),
    Col("tax_id", "text", "Federal tax id from the Transmittal Sheet."),
    Col(
        "ts_lar_count", "integer", "Number of LAR records the institution reported (TS).", "BIGINT"
    ),
    Col(
        "ts_present",
        "bool",
        "False when the lender has LAR records that year but no Transmittal Sheet row; its "
        "name and ids then come from the nearest year that has them.",
        "BOOLEAN",
    ),
    Col("lar_records", "integer", "Number of rows for this lender in hmda_lar_core.", "BIGINT"),
    Col("rssd_id", "integer", "Federal Reserve RSSD id of the respondent.", "BIGINT"),
    Col(
        "rssd_source",
        "category",
        "Where rssd_id came from.",
        allowed=["panel", "panel_other_year", "respondent_id_frs", "none"],
    ),
    Col("parent_rssd_id", "integer", "RSSD id of the parent (Reporter Panel).", "BIGINT"),
    Col("top_holder_rssd_id", "integer", "RSSD id of the top holder (Reporter Panel).", "BIGINT"),
    Col("top_holder_name", "text", "Top holder name (Reporter Panel)."),
    Col(
        "assets_000s",
        "integer",
        "Assets in thousands of dollars as given in the Reporter "
        "Panel (definitions vary by lender type; -1 / blank become NULL).",
        "BIGINT",
    ),
    Col(
        "other_lender_code",
        "code",
        "Reporter Panel lender type.",
        "SMALLINT",
        domain=C.OTHER_LENDER_CODE,
        label=True,
    ),
    Col(
        "fdic_cert",
        "integer",
        "FDIC certificate number, matched on rssd_id to FDIC BankFind institutions (FED_RSSD).",
        "INTEGER",
    ),
    Col("fdic_name", "text", "FDIC institution name for the matched certificate."),
    Col(
        "fdic_match_method",
        "category",
        "rssd = rssd_id equals FDIC FED_RSSD; "
        "respondent_id_cert = pre-2018 FDIC-supervised respondent whose respondent_id is an "
        "FDIC certificate number.",
        allowed=["rssd", "respondent_id_cert"],
    ),
]

BANK_FINANCIALS: list[Col] = [
    Col("cert", "integer", "FDIC certificate number.", "INTEGER", nullable=False),
    Col("rssd_id", "integer", "Federal Reserve RSSD id (RSSDID).", "BIGINT"),
    Col("report_date", "date", "Quarter-end report date (REPDTE).", "DATE", nullable=False),
    Col("year", "year", "Calendar year of report_date.", "SMALLINT", nullable=False),
    Col("quarter", "integer", "Calendar quarter of report_date.", "SMALLINT", nullable=False),
    Col("name", "text", "Institution name at that date."),
    Col("total_assets", "integer", "ASSET: total assets, $000.", "BIGINT"),
    Col("total_deposits", "integer", "DEP: total deposits, $000.", "BIGINT"),
    Col("equity_capital", "integer", "EQ: total equity capital, $000.", "BIGINT"),
    Col("loans_and_leases_gross", "integer", "LNLSGR: total loans and leases, $000.", "BIGINT"),
    Col("loans_and_leases_net", "integer", "LNLSNET: net loans and leases, $000.", "BIGINT"),
    Col("real_estate_loans", "integer", "LNRE: loans secured by real estate, $000.", "BIGINT"),
    Col(
        "re_1_4_family_loans",
        "integer",
        "LNRERES: loans secured by 1-4 family residential properties, $000.",
        "BIGINT",
    ),
    Col(
        "re_1_4_family_lines",
        "integer",
        "LNRELOC: 1-4 family revolving open-end lines, $000.",
        "BIGINT",
    ),
    Col(
        "re_multifamily_loans",
        "integer",
        "LNREMULT: multifamily real estate loans, $000.",
        "BIGINT",
    ),
    Col("net_income", "integer", "NETINC: net income year to date, $000.", "BIGINT"),
    Col("roa", "integer", "ROA: return on assets, annualised, percent.", "DOUBLE"),
    Col("roe", "integer", "ROE: return on equity, annualised, percent.", "DOUBLE"),
    Col("equity_to_assets", "integer", "EQV: equity capital to assets, percent.", "DOUBLE"),
    Col("leverage_ratio", "integer", "RBC1AAJ: leverage (core capital) ratio, percent.", "DOUBLE"),
    Col("noncurrent_loans", "integer", "NCLNLS: noncurrent loans and leases, $000.", "BIGINT"),
    Col(
        "re_1_4_family_past_due_30_89",
        "integer",
        "P3RERES: 1-4 family loans 30-89 days past due, $000.",
        "BIGINT",
    ),
    Col(
        "re_1_4_family_nonaccrual",
        "integer",
        "NARERES: 1-4 family loans in nonaccrual, $000.",
        "BIGINT",
    ),
    Col(
        "re_1_4_family_net_chargeoffs",
        "integer",
        "NTRERES: 1-4 family net charge-offs year to date, $000.",
        "BIGINT",
    ),
    Col("employees", "integer", "NUMEMP: full-time equivalent employees.", "INTEGER"),
]

FDIC_INSTITUTIONS: list[Col] = [
    Col("cert", "integer", "FDIC certificate number.", "INTEGER", nullable=False),
    Col("rssd_id", "integer", "FED_RSSD: Federal Reserve RSSD id.", "BIGINT"),
    Col("name", "text", "Institution name (current or last)."),
    Col("city", "text", "City."),
    Col("state", "text", "State (postal code)."),
    Col("active", "bool", "Open and insured today.", "BOOLEAN"),
    Col("bank_class", "text", "BKCLASS charter class."),
    Col("regulator", "text", "REGAGNT primary federal regulator."),
    Col("established_date", "date", "ESTYMD.", "DATE"),
    Col("insured_date", "date", "INSDATE.", "DATE"),
    Col("end_date", "date", "ENDEFYMD; 9999-12-31 for open institutions.", "DATE"),
    Col("holding_company_rssd_id", "integer", "RSSDHCR: regulatory top holder RSSD.", "BIGINT"),
    Col("holding_company_name", "text", "NAMEHCR."),
    Col("community_bank", "bool", "CB: FDIC community bank flag.", "BOOLEAN"),
    Col("specialization", "text", "SPECGRPN: asset concentration group."),
]

MORTGAGE_COMPLAINTS: list[Col] = [
    Col("complaint_id", "id", "CFPB complaint id.", "BIGINT", nullable=False),
    Col("date_received", "date", "Date the CFPB received the complaint.", "DATE", nullable=False),
    Col("year", "year", "Calendar year of date_received.", "SMALLINT", nullable=False),
    Col("product", "text", "Always 'Mortgage' in this table."),
    Col("sub_product", "text", "Mortgage sub-product as published."),
    Col("issue", "text", "Issue."),
    Col("sub_issue", "text", "Sub-issue."),
    Col("company", "text", "Company name as published by the CFPB."),
    Col("state", "text", "Consumer's state."),
    Col("zip_code", "text", "Consumer's ZIP code as published (may be truncated or XX)."),
    Col("tags", "text", "Tags (Older American, Servicemember)."),
    Col("submitted_via", "text", "Channel."),
    Col("date_sent_to_company", "date", "Date sent to company.", "DATE"),
    Col("company_response", "text", "Company response to consumer."),
    Col("company_public_response", "text", "Company public response."),
    Col("timely_response", "bool", "Timely response?", "BOOLEAN"),
    Col("company_normalized", "text", "Company name after this project's normalisation."),
    Col("matched_lei", "id", "LEI of the HMDA lender the company name was matched to."),
    Col("matched_lender_name", "text", "HMDA respondent name that was matched."),
    Col(
        "match_method",
        "category",
        "How the match was made.",
        allowed=["exact_name", "normalized_name", "core_name", "ambiguous", "none"],
    ),
    Col(
        "match_confidence",
        "category",
        "high = identical name or identical normalised name, "
        "single LEI; medium = identical core name (generic words removed), single LEI; none = "
        "no match or ambiguous.",
        allowed=["high", "medium", "none"],
    ),
]

TABLES: dict[str, list[Col]] = {
    "hmda_lar": HMDA_LAR,
    "hmda_lar_core": HMDA_LAR_CORE,
    "lenders": LENDERS,
    "bank_financials": BANK_FINANCIALS,
    "fdic_institutions": FDIC_INSTITUTIONS,
    "mortgage_complaints": MORTGAGE_COMPLAINTS,
}

TABLE_DESCRIPTIONS: dict[str, str] = {
    "hmda_lar": "Every published field of the FFIEC Snapshot public LAR, 2018 onward, typed, "
    "with a decoded label next to every coded field. One row per published record.",
    "hmda_lar_core": "A common schema for every covered year (pre-2018 CFPB historic LAR and "
    "2018+ snapshot LAR), with codes mapped to shared definitions.",
    "lenders": "One row per lender per year: Transmittal Sheet, Reporter Panel identifiers and "
    "the FDIC certificate where the RSSD id matches an FDIC-insured institution.",
    "bank_financials": "Selected FDIC quarterly Call Report aggregates for every FDIC-insured "
    "institution, 2007 onward.",
    "fdic_institutions": "FDIC BankFind institution directory (open and closed).",
    "mortgage_complaints": "CFPB Consumer Complaint Database, product = Mortgage, with a "
    "name-based match to HMDA lenders.",
}

TABLE_KEYS: dict[str, list[str]] = {
    "hmda_lar": ["activity_year", "record_id"],
    "hmda_lar_core": ["activity_year", "record_id"],
    "lenders": ["activity_year", "lender_key"],
    "bank_financials": ["cert", "report_date"],
    "fdic_institutions": ["cert"],
    "mortgage_complaints": ["complaint_id"],
}
