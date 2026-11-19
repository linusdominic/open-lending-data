# HMDA definitions over time, and how this project maps them

HMDA data for 2007-2017 and for 2018 onward come from two different reporting regimes. The
2015 HMDA Rule (CFPB, "Home Mortgage Disclosure (Regulation C)", 80 Fed. Reg. 66128, 28 Oct
2015, effective for data collected from 1 Jan 2018) changed which transactions are reported,
how institutions are identified, and the definition or code list of most fields. Years
therefore cannot simply be stacked. `hmda_lar` keeps the 2018+ fields exactly as published;
`hmda_lar_core` is the common schema, and this document is the record of every mapping it
makes. Code lists are in [data-dictionary.md](data-dictionary.md) and come from
`src/openlending/codes.py`.

Sources used throughout:

- **[CS]** CFPB, "HMDA Loan/Application Register Code Sheet" (pre-2018 codes),
  https://files.consumerfinance.gov/hmda-historic-data-dictionaries/lar_record_codes.pdf
- **[FIG]** FFIEC, "Filing Instructions Guide for HMDA Data Collected in 2018" and later years,
  and the code enumerations in the HMDA Platform source (github.com/cfpb/hmda-platform,
  `common/src/main/scala/hmda/model/filing/lar/enums`, commit eec90f87).
- **[2015R]** 80 Fed. Reg. 66128 (2015 HMDA Rule) and 82 Fed. Reg. 43088 (2017 amendments).
- **[EGR]** Economic Growth, Regulatory Relief, and Consumer Protection Act, Pub. L. 115-174,
  section 104 (24 May 2018), and CFPB interpretive and procedural rule, 83 Fed. Reg. 45325
  (7 Sep 2018).
- **[DISC]** CFPB, "Disclosure of Loan-Level HMDA Data", final policy guidance, 84 Fed. Reg.
  649 (31 Jan 2019): which fields are removed or modified in the public file.
- **[RS2008]** Federal Reserve Board, Regulation C amendments, 73 Fed. Reg. 63329 (24 Oct 2008),
  effective 1 Oct 2009: rate-spread reporting threshold.
- **[DER]** HMDA Platform source, `common/src/main/scala/hmda/parser/derivedFields/`
  (`RaceCategorization.scala`, `EthnicityCategorization.scala`, `SexCategorization.scala`),
  commit eec90f87.

## 1. Which transactions are in the data

| | 2007-2017 | 2018+ | Effect on comparisons |
|---|---|---|---|
| Coverage test | Purpose-based: home purchase, home improvement, refinancing of a dwelling | Transaction-based: closed-end loans and open-end lines secured by a dwelling [2015R] | Some pre-2018 records (unsecured home improvement loans) are no longer reported; some new ones are (dwelling-secured business-purpose loans, reverse mortgages). |
| Home-equity lines (HELOCs) | Optional | Required above the open-end threshold [2015R] | Open-end lines appear in volume from 2018. `open_end_line_of_credit` = 1 identifies them; filter them out for a closer comparison with earlier years. |
| Reverse mortgages | Reported when they met the purpose test | Reported, flagged | `reverse_mortgage` = 1 from 2018. |
| Institution thresholds | Asset and location tests | Loan-volume thresholds (closed-end 25 loans in each of the two preceding years; open-end 500, then 200 from 2022, set by later rules) [2015R] | The reporter population changes in 2018 (see `institutions` in the validation report). A 2020 rule raised the closed-end threshold to 100 loans from 1 Jul 2020; a federal court vacated that increase in 2022 (not re-checked for this build). |
| Partial exemptions | None | From 2018, institutions under the [EGR] thresholds may leave 26 data points unreported ("Exempt", code 1111) | See section 4. |

`hmda_lar_core` keeps every published record. It does not try to re-create the pre-2018
universe from 2018+ data; it provides `open_end_line_of_credit`, `reverse_mortgage` and
`business_or_commercial_purpose` (NULL before 2018) so that analyses can choose their filter.

## 2. Identifiers

| Field | 2007-2017 | 2018+ | Mapping |
|---|---|---|---|
| Institution | `respondent_id` (10 characters) + `agency_code`; the pair is the FFIEC's "ARID" | Legal Entity Identifier (LEI) | `lender_key` = LEI from 2018, `agency_code-respondent_id` before. `lenders.lei` is filled for pre-2018 lender-years from the FFIEC ARID-to-LEI crosswalk (`arid2017_to_lei_xref_csv.zip`), which maps 2017 ARIDs; it is applied to earlier years on the assumption that a respondent id kept its meaning. |
| LEI letter case | n/a | The 2018 and 2020 Transmittal Sheets contain LEIs with lower-case letters, while the LAR has them in upper case | All LEIs are upper-cased (ISO 17442 LEIs are upper case). Without this, 132,289 LAR records in 2018 and 2020 do not join to their lender. |
| Loan | No loan identifier in the public file | Universal Loan Identifier collected but removed from the public file [DISC] | `record_id` = row number in the published file. It identifies a row of this release, not a loan. |
| RSSD id | Reporter Panel 2010-2017; none in the 2007-2009 panel | Reporter Panel 2018-2023; the FFIEC published no panel with the 2024 and 2025 snapshots | `lenders.rssd_id` with `rssd_source`: `panel` (same year), `panel_other_year` (same LEI or ARID in another year's panel), `respondent_id_frs` (Federal Reserve-supervised respondents before 2010, whose respondent id is the RSSD id), `none`. |

## 3. Field-by-field mappings in `hmda_lar_core`

| Core field | 2007-2017 source | 2018+ source | Mapping and caveats |
|---|---|---|---|
| `loan_purpose` | 1 purchase, 2 improvement, 3 refinancing [CS] | 1, 2, 31 refinancing, 32 cash-out refinancing, 4 other purpose, 5 not applicable [FIG] | 31 and 32 become 3. 4 and 5 exist only from 2018. Pre-2018 home improvement included unsecured loans; 2018+ does not. |
| `property_type` | 1 one-to-four family (not manufactured), 2 manufactured housing, 3 multifamily [CS] | `construction_method` (1 site-built, 2 manufactured) and `total_units` (1-4, then bands) | 1-4 units site-built = 1; 1-4 units manufactured = 2; 5+ units = 3 (including manufactured multifamily, which the pre-2018 code list classed as manufactured housing). |
| `occupancy` | 1 owner-occupied principal dwelling, 2 not owner-occupied, 3 not applicable [CS] | 1 principal residence, 2 second residence, 3 investment property [FIG] | 2 and 3 become 2. Code 3 (not applicable) exists only before 2018 (mostly purchased loans and multifamily). |
| `preapproval` | 1 requested, 2 not requested, 3 not applicable | 1, 2 | Code 3 only before 2018. |
| `action_taken` | 1-8 | 1-8 | Same codes and meanings. |
| `loan_type` | 1-4 | 1-4 | Same codes and meanings. |
| `loan_amount` | Thousands of dollars, rounded | Dollars; the public file gives the midpoint of the $10,000 interval [DISC] | Pre-2018 value x 1000. In this build every 2018+ amount ends in 5,000, as the policy describes. Differences under $10,000 between eras are not meaningful. |
| `applicant_income_000s` | Thousands of dollars | Thousands of dollars | Same unit; `NA` becomes NULL with `_na_reason`. |
| Geography | `state_code` 2-digit FIPS, `county_code` 3-digit, `census_tract_number` "dddd.dd" | `state_code` postal abbreviation, `county_code` 5-digit FIPS, `census_tract` 11-digit | Core uses `state_fips` (2), `county_fips` (5), `census_tract` (11) in both eras. The 2014 historic file stores county codes without leading zeros; they are padded. |
| Census tracts | 2000-census tracts through 2011, 2010-census tracts from 2012 | 2010-census tracts through 2021, 2020-census tracts from 2022 | Measured in this build: 21,042 tract codes in 2012 and 22,705 in 2022 did not exist the year before (typically 94-295 in other years). 2024 adds 1,121 new codes, 873 of them in Connecticut (FIPS 09), consistent with the switch from counties to planning regions. Tract codes are not comparable across these breaks without a crosswalk, which this project does not provide. |
| `msa_md` | `msamd` | `derived_msa_md` | As published. MSA/MD delineations are revised by OMB from time to time; codes are not stable across years. |
| `applicant_ethnicity`, `co_applicant_ethnicity` | One field, codes 1-5 [CS] | Up to five fields, with subgroup codes 11-14 and free text [FIG] | First field only; 11-14 become 1 (Hispanic or Latino). Values outside the code list become NULL. |
| `applicant_race_1..5` | Five fields, codes 1-8 | Five fields with subgroup codes 21-27 (Asian) and 41-44 (Native Hawaiian or Other Pacific Islander) | 21-27 become 2, 41-44 become 4. |
| `applicant_sex` | 1-5 | 1-6 (6 = selected both male and female) | Same codes; 6 only from 2018. |
| `derived_race`, `derived_ethnicity`, `derived_sex` | Not published in the loan-level files | Published by the FFIEC in the public LAR | This project ports the FFIEC's own derivation code [DER] to SQL and applies it to both eras, so the derived fields have one definition across 2007-2025. On 2018+ data the port reproduces the published `derived_*` columns for every record (validation check `derived_field_port_matches_ffiec`). Before 2018 the inputs are coarser (one ethnicity field, no subgroups), so the same rule sees less detail. Two quirks of the FFIEC code are kept on purpose (see `src/openlending/derived.py`). |
| `purchaser_type` | 0-9; 7 = life insurance company, credit union, mortgage bank or finance company [CS] | 0-9 with 71 (credit union, mortgage company or finance company) and 72 (life insurance company) [FIG] | 71 and 72 become 7. |
| `denial_reason_1..3` | Up to three reasons, codes 1-9 | Up to four reasons, codes 1-9, 10 not applicable, 1111 exempt | The fourth reason is dropped; 10 and 1111 become NULL. `hmda_lar` keeps all four and the codes as published. |
| `rate_spread` | Reported only for originations above a threshold: before 1 Oct 2009 APR minus the Treasury yield, threshold 3 pp (first lien) / 5 pp (subordinate); from applications taken on or after 1 Oct 2009, APR minus the average prime offer rate (APOR), threshold 1.5 / 3.5 pp [RS2008] | APR minus APOR for every covered origination except reverse mortgages and purchased loans; can be negative [2015R] | Kept as published. **Not comparable as a level across eras**: before 2018 a NULL means "below the threshold", from 2018 it means not applicable or exempt (see `rate_spread_na_reason`). |
| `higher_priced` | Origination with a reported rate spread | Origination whose rate spread is at or above 1.5 pp (first lien) or 3.5 pp (subordinate lien) | A comparable indicator from 2010 (2009 mixes both thresholds; 2007-2008 used the Treasury benchmark), so it is NULL for 2007-2009. From 2018 it is NULL when the rate spread is NA or Exempt. |
| `hoepa_status` | 1 HOEPA loan, 2 not | 1 high-cost, 2 not, 3 not applicable | Code 3 only from 2018. |
| `lien_status` | 1 first, 2 subordinate, 3 not secured, 4 not applicable (purchased loans) | 1 first, 2 subordinate | 3 and 4 only before 2018 (unsecured loans are no longer reported; purchased loans now report lien status). |
| `application_date_before_2004` | `application_date_indicator` 1 | n/a | Kept because the Federal Reserve's 2007 tables exclude these records; NULL from 2018. |
| Tract demographics | `population`, `minority_population`, `hud_median_family_income`, `tract_to_msamd_income`, `number_of_owner_occupied_units`, `number_of_1_to_4_family_units` | `tract_population`, `tract_minority_population_percent`, `ffiec_msa_md_median_family_income`, `tract_to_msa_income_percentage`, `tract_owner_occupied_units`, `tract_one_to_four_family_homes` | Renamed to the 2018 names. The census or ACS vintage behind them changes over time. |

Fields that exist only from 2018 (combined LTV, interest rate, loan costs, points and fees,
origination charges, discount points, lender credits, loan term, prepayment penalty term,
introductory rate period, non-amortizing features, property value, manufactured-home fields,
total units, multifamily affordable units, debt-to-income ratio, credit score model, the
"observed" flags, age, application channel, automated underwriting systems) are in
`hmda_lar` only.

## 4. NA, Exempt and 1111

From 2018 a field can be empty for two different reasons, and the public file distinguishes
them: `NA` (not applicable to this record) and `Exempt` (the institution used a partial
exemption under [EGR]). For coded fields the exemption is the code 1111 [FIG].

- Numeric fields in `hmda_lar` are typed (DOUBLE or INTEGER) with NULL for both cases, and
  have a companion `<field>_na_reason` holding `NA` or `Exempt`. No information is lost.
- Coded fields keep 1111 as a code, with label "Exempt". 1111 is in the code list only for
  the fields that can be exempt; anywhere else it fails the domain check.
- Text-banded fields (`debt_to_income_ratio`, `total_units`, ages, `conforming_loan_limit`)
  are kept as published, including the literal `NA` / `Exempt` / `8888` / `9999` values.

## 5. Other changes in the published files

- **Column name**: the 2018 snapshot calls the combined loan-to-value ratio
  `loan_to_value_ratio`; 2019-2025 call it `combined_loan_to_value_ratio`. Both load into
  `combined_loan_to_value_ratio`.
- **Fields removed from the public file** [DISC]: Universal Loan Identifier, application and
  action dates, property address, credit score, NMLS identifier, free-form race and ethnicity
  text, exact age (banded), exact loan amount and property value (midpoints), exact DTI above
  60 and below 36 (banded). None of these can be recovered.
- **Releases**: the FFIEC publishes each year's data as a Snapshot (spring of the following
  year), and later as One Year and Three Year datasets that include resubmissions. This
  project uses the Snapshot for 2018-2025. The CFPB historic files for 2007-2017 are a later
  vintage than the data first released each September: for example the 2014 file contains
  173,877 records from one filer (respondent 41-1795868, Ditech Financial) that are in
  neither the 2014 Transmittal Sheet nor the Federal Reserve's 2014 figures, and the 2012
  file has one more record than the Federal Reserve's 2012 table.

## 6. Source file defects handled by the pipeline

These are recorded here because the pipeline changes or flags data because of them.

| File | Defect | Handling |
|---|---|---|
| CFPB `hmda_2007_panel.csv` | One row (respondent 9900000375) has parent id, name and city fused into the agency code field, giving 13 fields instead of 16 | Split back: agency code is the first character, the three parent fields are empty (`stage.repair_short_panel_rows`). |
| CFPB `hmda_2016_transmittal_sheet.csv` | One row (respondent 0000021122) has an extra empty field after the mailing address | The empty field is dropped (`stage.repair_extra_address_field`). |
| CFPB `hmda_2012_panel.csv` | "Respondent RSSD ID" has 11 characters in every row: the 10-digit id plus the first character of the next field, so Wells Fargo Bank's 451965 reads 4519650 | The eleventh character is dropped. Without this, the FDIC match rate for bank-supervised 2012 lenders falls from 97.6% to 60.2%. |
| FFIEC 2018 and 2020 Transmittal Sheets | Lower-case letters in some LEIs | LEIs upper-cased everywhere. |
| CFPB 2014 historic LAR | 173,877 records whose respondent has no 2014 Transmittal Sheet row | A `lenders` row is added with `ts_present = false`, name and ids from the nearest year. |
| FFIEC 2018-2023 snapshots | Out-of-domain values in four fields of 11 records (see validation report, "documented source defect") | Kept as published in `hmda_lar`; become NULL in `hmda_lar_core`. |
| Reporter Panel | `-1` used for "none" in ids, assets and lender type | Converted to NULL. |
