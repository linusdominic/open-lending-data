# open-lending-data

A reproducible pipeline that turns US mortgage-lending public data into one documented,
validated, multi-year dataset: HMDA loan/application records for 2007-2025 on a common
schema, the HMDA lenders behind them, FDIC quarterly financials for the lenders that are
FDIC-insured banks, and CFPB mortgage complaints matched to lenders by name.

It is for fair-lending researchers, journalists, fintech and policy analysts who want to
compare years without re-deriving every definitional change, and for data engineers who
want to see how the harmonisation and its validation are done.

Status: version 0.1.0. Built and validated on one machine (Apple silicon, macOS, 16 GB
RAM, 10 cores, Python 3.12 via uv, DuckDB 2.0.0) on 19 November 2026. Every number below
comes from that run; the command that produced it is next to it or in
[Reproducing the numbers](#reproducing-the-numbers). The release files are published as
[release v0.1.0](https://github.com/linusdominic/open-lending-data/releases/tag/v0.1.0) (31 Parquet files, 13.22 GB).

## Why

HMDA data are published by the FFIEC and the CFPB in formats that do not line up across
years. The 2018 redesign changed how lenders are identified (LEI instead of respondent id),
which transactions are reported, and the codes of most fields: loan purpose gained cash-out
refinancing and "other", race and ethnicity gained subgroups, rate spread went from a
threshold-triggered field to one reported for every origination, and 26 fields can be
"Exempt" for smaller filers. Stacking years without handling this produces wrong numbers.

Existing options cover parts of this. Hugging Face hosts about 14 HMDA uploads, mostly
single years; the CFPB's HMDA_Data_Science_Kit downloads files but does not harmonise them;
nothing public joins HMDA lenders to bank financials or complaints. This project does all
three, documents every mapping in [docs/changes-over-time.md](docs/changes-over-time.md),
and checks the output against the source files and against published totals.

### Responsible use

HMDA collects race, ethnicity, sex and age so that lending can be monitored for
discrimination. The public file has no credit scores, no exact incomes and no other inputs
to an underwriting decision, so a difference between groups is a reason to look further,
not proof of discrimination. Complaints are not a statistical sample: the CFPB says the
database "is not a statistical sample of consumers' experiences in the marketplace". Do not
use any of this to make decisions about individuals.

## What you get

| Table | Rows | Parquet | Key | What it is |
|---|---|---|---|---|
| `hmda_lar` | 137,678,531 (2018-2025) | 6.04 GB, 8 files | `activity_year, record_id` | Every field of the FFIEC Snapshot public LAR, typed: 174 columns, i.e. the 99 published fields, `record_id`, a label for each coded field and an `_na_reason` for each numeric field that can be NA or Exempt. |
| `hmda_lar_core` | 325,140,977 (2007-2025) | 7.13 GB, 19 files | `activity_year, record_id` | One schema for every year: 87 columns with codes mapped to shared definitions, FIPS geography, derived race/ethnicity/sex on one definition, a comparable `higher_priced` flag. |
| `lenders` | 121,119 lender-years | 3.2 MB | `activity_year, lender_key` | Transmittal Sheet and Reporter Panel: LEI or respondent id, agency, name, RSSD id, parent and top holder, and the FDIC certificate where the RSSD id matches. |
| `bank_financials` | 487,729 bank-quarters (2007 Q1-2026 Q2) | 31.9 MB | `cert, report_date` | Selected FDIC Call Report aggregates (assets, deposits, equity, 1-4 family loans, past-due and net charge-offs, ROA, ROE, leverage ratio...), $000. |
| `fdic_institutions` | 27,835 | 0.8 MB | `cert` | FDIC BankFind directory, open and closed, with `FED_RSSD`. |
| `mortgage_complaints` | 467,257 (Dec 2011-Nov 2026) | 5.2 MB | `complaint_id` | CFPB complaints with product "Mortgage", with the matched lender LEI, match method and confidence. |

Row counts are from `openlending build` on 19 Nov 2026; the HMDA tables' counts equal the
line counts of the raw files (see [Validation](#validation)). Sizes are the zstd Parquet files in
`data/release/release-manifest.json`. `data/openlending.duckdb` (0.5 MB) has a view per table
and a `hmda_codes` table (every code and label). Column-level documentation:
[docs/data-dictionary.md](docs/data-dictionary.md) (also as JSON).

Example, against the DuckDB database or the release files:

```sql
-- Originations of first-lien, one-to-four family, principal-residence home-purchase and
-- refinance loans, excluding open-end lines and reverse mortgages, by year.
SELECT activity_year,
       count(*) FILTER (WHERE loan_purpose = 1) AS home_purchase,
       count(*) FILTER (WHERE loan_purpose = 3) AS refinance,
       round(median(loan_amount) FILTER (WHERE loan_purpose = 1)) AS median_purchase_amount
FROM hmda_lar_core
WHERE action_taken = 1 AND lien_status = 1 AND property_type IN (1, 2) AND occupancy = 1
  AND coalesce(open_end_line_of_credit, 2) <> 1 AND coalesce(reverse_mortgage, 2) <> 1
GROUP BY 1 ORDER BY 1;
```

Output (`uv run python` with DuckDB against `data/openlending.duckdb`, 2.2 s over 325
million rows):

```
year  home_purchase   refinance  median_purchase_amount
2007      3,447,916   3,649,381                 176,000
2008      2,607,722   2,896,644                 171,000
2009      2,447,890   5,288,161                 162,000
2010      2,213,631   4,509,310                 166,000
2011      2,060,808   3,840,044                 164,000
2012      2,331,989   5,900,788                 173,000
2013      2,680,340   4,384,836                 185,000
2014      2,804,466   1,994,390                 189,000
2015      3,199,645   2,841,018                 198,000
2016      3,544,594   3,370,884                 206,000
2017      3,686,516   2,200,838                 215,000
2018      3,704,922   1,634,466                 225,000
2019      3,850,717   3,086,675                 235,000
2020      4,223,686   7,900,696                 255,000
2021      4,506,800   7,672,155                 285,000
2022      3,662,542   1,940,149                 305,000
2023      2,925,689     571,373                 305,000
2024      2,950,239     847,886                 315,000
2025      2,988,787   1,172,623                 325,000
```

The medians show one of the definitional changes: from 2018 the public file reports loan
amounts as the midpoint of a $10,000 band, so every 2018+ median ends in 5,000.

## Coverage

| Source | Years | Files | Downloaded | Uncompressed |
|---|---|---|---|---|
| FFIEC HMDA Snapshot National Loan-Level Dataset: LAR | 2018-2025 | 8 zip | 7.69 GB | 53.0 GB CSV |
| FFIEC Snapshot Transmittal Sheet | 2018-2025 | 8 zip | 1.6 MB | |
| FFIEC Snapshot Reporter Panel | 2018-2023 (none published for 2024, 2025) | 6 zip | 1.6 MB | |
| FFIEC ARID-to-LEI crosswalk (2017 respondent ids) | 2017 | 1 zip | 0.1 MB | |
| CFPB historic HMDA LAR, "all records, codes" | 2007-2017 | 11 zip | 4.08 GB | 32.3 GB CSV |
| CFPB historic Reporter Panel and Transmittal Sheet | 2007-2017 | 22 zip | 7.8 MB | |
| CFPB Consumer Complaint Database (all products; mortgage subset kept) | Dec 2011-17 Nov 2026 | 1 zip | 0.37 GB | 5.84 GB CSV, 19,251,022 complaints |
| FDIC BankFind Suite API: institutions | current | 1 response set | | 27,835 institutions |
| FDIC BankFind Suite API: quarterly financials | 2007 Q1-2026 Q2 (78 quarters) | 78 responses | 0.23 GB JSONL (both FDIC pulls) | 487,729 rows |

Every HMDA year from 2007 to 2025 is covered; 2025 is the snapshot the FFIEC released in
June 2026 (file Last-Modified 23 Jun 2026). Nothing before 2007 is included: the CFPB
historic page starts at 2007. URLs are in `src/openlending/sources.py`; each downloaded
file's URL, size, SHA-256 and Last-Modified are in `data/raw/manifest.json`. The FFIEC CDR
bulk Call Report download was not used; the FDIC API carries the fields needed and the RSSD id.

## Rebuilding

Requirements: [uv](https://docs.astral.sh/uv/) (it installs Python 3.12), about 33 GB of
disk for `data/` (raw 12.4 GB, staging 7.6 GB, tables 13.2 GB; release files are hard links) plus up to 10.2 GB of
temporary space while the largest CSV is staged, and network access to the FFIEC, CFPB and
FDIC sites. DuckDB is limited to 6 GB of memory (`OPENLENDING_MEMORY_LIMIT`) and 6 threads
(`OPENLENDING_THREADS`).

```bash
make install         # uv sync --python 3.12
make download        # raw files and FDIC API pulls -> data/raw (resumable)
make build           # stage, then build every table and data/openlending.duckdb
make validate        # all checks -> docs/validation-report.md; exit 1 on an integrity failure
make docs            # data dictionary from the schema
make release-assets  # data/release: Parquet under 1.9 GB each, SHA256SUMS, notes
```

`openlending build --step lar --years 2024,2025` rebuilds part of it; steps are `stage, lar,
core, historic, fdic, lenders, complaints, db`.

Timings on this machine (shared with another job during the run), wall clock:

| Step | Time | Notes |
|---|---|---|
| `download`, files | 17 min 13 s | 57 files, 12.15 GB, one at a time; 6-21 MB/s |
| `download`, FDIC API | 4 min 21 s | 79 requests, 0.5 s apart |
| `build` | 12 min 40 s | peak resident memory 5.35 GB |
| of which `stage` | 6 min 42 s | unzip and convert 91 GB of CSV to text Parquet |
| of which `lar` | 3 min 3 s | 137.7 M rows, 174 columns |
| of which `core` (2018+) and `historic` (2007-2017) | 1 min 38 s and 1 min 15 s | |
| of which `fdic`, `lenders`, `complaints`, `db` | 3 s together | |
| `validate` | 4 min 22 s | peak resident memory 5.46 GB; includes 2 reconkit runs of 37 s each |
| `release-assets` | 5.8 s | hard links plus SHA-256 of 13.2 GB |

Timings come from `/usr/bin/time -l` around each command and from
`data/reports/build_timings.json`; download times from `data/raw/manifest.json`.

## Design choices

**Two LAR tables, not one.** `hmda_lar` keeps every field of the 2018+ public file, typed,
with a label next to every coded field and an `_na_reason` next to every numeric field that
can be `NA` or `Exempt`. Nothing is dropped or recoded there. `hmda_lar_core` is the narrower
schema that exists in every year from 2007, with codes mapped to shared definitions. The
mapping of each field, and the source document for each definition, is in
[docs/changes-over-time.md](docs/changes-over-time.md). Analyses that only need 2018+ should
use `hmda_lar`.

**One record id.** The public LAR has no loan identifier. `record_id` is the row's position
in the published CSV (1 = first data line), so `(activity_year, record_id)` identifies a
published record and can be traced back to the raw file.

**Derived race, ethnicity and sex on one definition.** From 2018 the FFIEC publishes
`derived_race`, `derived_ethnicity` and `derived_sex`; before 2018 there are none. This
project ports the FFIEC's own derivation code (from the HMDA Platform source) to SQL and
applies it to every year. On 2018-2025 it reproduces the published values for every record,
which is checked on each validation run.

**Plain DuckDB SQL, not dbt.** dbt (dbt-core 1.12 with dbt-duckdb 1.11) was considered and
not used, because the SQL is generated from one Python schema
(`src/openlending/schema.py`): the same column specs produce the typed SELECTs, the data
dictionary and the domain checks, so a 174-column table is described once. In dbt that
would be either hand-written 170-column models or a macro layer duplicating the schema. The
build also runs one year at a time to stay within a 6 GB DuckDB memory limit, and the checks
that matter most (line counts of the raw files, published totals with citations, a
reconciliation across two database connections) sit outside the warehouse, where dbt tests
do not reach without extra plumbing. What is lost: dbt's lineage graph and generated docs
site.

**Parquet first, DuckDB second.** Outputs are zstd Parquet files, one per table per year,
readable by anything. `data/openlending.duckdb` only holds views over them plus a
`hmda_codes` lookup table, so it is about 0.5 MB; it records absolute paths, so rebuild it
(`openlending build --step db`) after moving `data/`.

**Polite downloads.** One file at a time, the stock httpx client headers (a custom
User-Agent has been refused by the FFIEC CDN before; not re-tested here), HTTP Range resume of partial files, exponential
backoff on 429/5xx, and a manifest (`data/raw/manifest.json`) with URL, size, SHA-256, server
Last-Modified and download time for every file. A file whose size and Last-Modified match
its manifest entry is not downloaded again.

## Validation

`make validate` ran 630 checks in 4 min 22 s on 19 Nov 2026: 483 pass, 128 external
mismatches (explained below), 19 informational, **0 integrity failures**. The full table, with
expected value, actual value and source for every check, is
[docs/validation-report.md](docs/validation-report.md).

**Integrity checks** (about this pipeline; any failure exits 1):

| Check | Result |
|---|---|
| Data lines in each raw CSV = rows staged | 57 of 57 files |
| Raw lines = rows in `hmda_lar` per year | 8 of 8 years (2018-2025), exact |
| Raw lines = rows in `hmda_lar_core` per year | 19 of 19 years (2007-2025), exact |
| No non-empty raw value lost when typing | 8 of 8 years, 0 values lost |
| Key unique and not null | 6 of 6 tables |
| Referential integrity | 5 of 5: every LAR record has a lender row that year; every matched complaint LEI and every `fdic_cert` exists; `bank_financials` has 4,946 rows for 116 certificates absent from the BankFind institutions endpoint (non-insured trust companies and similar), recorded as a documented exception |
| Code values within documented domains | 111 of 111 columns; 11 records in four `hmda_lar` fields carry invalid codes in the published 2018-2023 files and are recorded as documented exceptions (count must match exactly) |
| Ported FFIEC derived race / ethnicity / sex vs the FFIEC's published values | 0 differences in 137,678,531 records, for each of the three fields |
| reconkit: staged raw 2023 file vs `hmda_lar` 2023 | 0 rows missing, 0 changed; 11,483,889 rows x 114 columns, two separate DuckDB connections, checksum bisection, 4 + 4 queries, 0 rows downloaded, 36.7 s |
| reconkit: same, with three planted changes | finds exactly record_ids 17, 4242 and 999999, 36.8 s |

reconkit (https://github.com/linusdominic/reconkit, installed from git) compares each column
of the raw file, cast with deliberately simple rules, with the harmonised table, keyed on
`record_id`. The planted run exists so that a clean result cannot come from a comparison that
cannot see differences.

**External checks** (against published figures; mismatches are reported, not fatal):

| Check | Result | Notes |
|---|---|---|
| Published totals (FFIEC releases, CFPB Data Point reports, Federal Reserve Bulletin tables) | 234 of 261 | Sources and every value in `src/openlending/expected.py`; 81 of the passes are exact-count matches |
| HMDA Data Browser API counts by action taken and loan purpose | 14 of 112 | All 14 for 2025 match exactly. For 2018-2024 the Data Browser serves later releases (One Year, Three Year) that include resubmissions; the Snapshot totals are 0.13%-0.69% lower |
| Sum of Transmittal Sheet `lar_count` = LAR rows | 16 of 19 years | 2014, 2017 and 2018 differ (below) |

What the mismatches are:

- **2014 (9 of 14 figures fail).** The CFPB's 2014 historic file (Last-Modified 17 Mar 2026)
  contains 173,877 records from one filer, respondent 41-1795868 (agency 7, named Ditech
  Financial in the 2015-2017 transmittal sheets), that are not in the 2014 Transmittal Sheet
  and not in the Federal Reserve's 2014 figures. Without them the counts match the Federal
  Reserve to the thousand: applications 9,933,258 (published 9,933 thousand), originations
  5,979,766 (5,980), purchased loans 1,752,016 (1,752), refinance applications 4,385,649
  (4,386). The records are kept; `lenders` has a row for this filer with `ts_present = false`.
- **2012 (8 of 15 fail by 1 or 2).** The CFPB file has 18,691,551 records against the
  Federal Reserve's 18,691,550; the 2012 figures are otherwise identical.
- **2021 (9 of 18 fail by 0.04%-0.12%).** The 2021 Snapshot downloaded now has 4,333
  transmittal sheets and 26,124,552 records; the FFIEC release reported 4,338 institutions and
  the CFPB's 2023 Data Point has slightly higher 2021 counts. All snapshot files for
  2018-2024 on the FFIEC CDN have Last-Modified 21 Nov 2025, so they may have been re-issued
  after those publications; this was not resolved.
- **2020 (1 of 19).** Home-purchase applications 7,076,486 against a published 7,077
  thousand: 14 records outside the rounding.
- **Transmittal Sheet counts.** 2017: transmittal sheets sum to 14,241,872, the LAR has
  14,285,496 (288 lenders differ). 2018: 15,120,213 against 15,119,651 (23 lenders differ).
  Both are as published.
- **2007** passes only because `application_date_before_2004` is kept: the Federal
  Reserve's 2007 Table 3 excludes the 2,115 applications taken before 2004, and with them
  excluded the counts match exactly (originations 10,441,353; denials 5,952,496; applications
  21,389,258).

No published record totals were found for 2024 or 2025; only institution counts (4,908 and
4,782, both matched). For 2025 the Data Browser comparison serves as the external check.

## Joins and match rates

**HMDA lenders to FDIC banks.** `lenders.rssd_id` (from the Reporter Panel) is matched to
`FED_RSSD` in the FDIC BankFind institution list; for pre-2018 FDIC-supervised respondents
whose respondent id is an FDIC certificate, that is used when the RSSD match fails.

| Years | Lenders supervised by OCC, FRS, FDIC or OTS matched to an FDIC certificate | Share of LAR records from a matched lender |
|---|---|---|
| 2007-2009 | 84.2%, 86.6%, 90.7% | 26.6%, 35.3%, 46.0% |
| 2010-2017 | 93.2%-97.7% | 36.1%-58.9% |
| 2018-2025 | 94.9%-97.4% | 27.5%-41.5% |

The 2007-2009 Reporter Panels carry no RSSD ids, so those years rely on ids from other
years' panels. The share of records is lower than the share of lenders because most HMDA
records come from independent mortgage companies, which are not FDIC-insured and are not
expected to match. Per-year values are in the validation report (`lender_fdic_match_rate`).
RSSD ids for 2024 and 2025 come from the 2023 or earlier panel of the same LEI
(`rssd_source = 'panel_other_year'`), because no panel was published for those years.

**Complaints to HMDA lenders.** By name, in tiers, never more than one LEI; details and a
manual review in [docs/complaint-matching.md](docs/complaint-matching.md).

| | Complaints | Companies |
|---|---|---|
| Mortgage complaints | 467,257 | 2,564 |
| Matched, high confidence (exact or normalised name) | 203,724 (43.6%) | 652 |
| Matched, medium confidence (holding-company core name) | 128,700 (27.5%) | 62 |
| Ambiguous (several LEIs) | 5,322 (1.1%) | 62 |
| Not matched | 129,511 (27.7%) | 1,788 |

So 71.1% of complaints but only 27.8% of company names are matched. Of the 62 medium-tier
company names, a manual review judged 39 to be in the right corporate family, 14
undeterminable from names, and 9 wrong; the 9 wrong ones account for 298 complaints. The
match rate falls from 85-88% of complaints in 2011-2013 to 53% in 2024-2025, as complaints
shift to servicers that do not file HMDA under the name used in complaints.

## Committed sample

`sample/` (1.9 MB) has every table in miniature so that tests and CI run without
downloads: 500 records per year of `hmda_lar` (4,000) and `hmda_lar_core` (9,500), the
2,000 complaints with the smallest `hash(complaint_id)`, every lender-year those rows
reference (4,583), year-end financials of the matched banks (12,429) and their FDIC
directory rows (744). Records are the 500 per year with the smallest DuckDB
`hash(activity_year, record_id)`, so the draw is deterministic; `openlending sample`
redraws it from a full build. Per-year sizes are equal, so it is not a representative sample
of anything. `openlending validate --sample` runs the integrity checks on it (125 checks, all
pass).

## Release assets

`make release-assets` wrote 31 Parquet files (13.22 GB, largest `hmda_lar_2021.parquet` at
1,160.6 MB, so no year needed splitting under the 1.9 GB limit), `SHA256SUMS`,
`release-manifest.json` (file, table, year, rows, bytes, SHA-256), `RELEASE_NOTES.md` and the
documentation files to `data/release/`. They are attached to [release v0.1.0](https://github.com/linusdominic/open-lending-data/releases/tag/v0.1.0);
after upload, the SHA-256 GitHub reports for each of the 38 attached files matched the local
file. To use them without building:

```bash
gh release download v0.1.0 -R linusdominic/open-lending-data -D data/release
cd data/release && sha256sum -c SHA256SUMS
```

Files over the limit would be
split into `_partNofM` files by row position; that path is exercised by the tests on the
sample with a 400 kB limit, not on real data.

## Sources, licences and terms

| Source | Publisher | What it says about use |
|---|---|---|
| HMDA Snapshot National Loan-Level Dataset, Transmittal Sheet, Reporter Panel, ARID-to-LEI crosswalk | FFIEC, published by the CFPB at ffiec.cfpb.gov | No licence statement found on the data publication pages. HMDA data are disclosed to the public under 12 U.S.C. 2803 and Regulation C. |
| Historic HMDA data 2007-2017 | CFPB, consumerfinance.gov/data-research/hmda/historic-data/ | The page states no licence or terms. |
| Consumer Complaint Database | CFPB | "All complaint data we publish is freely available for anyone to use, analyze, and build on." The CFPB also states the database is not a statistical sample of consumers' experiences. |
| BankFind Suite API | FDIC, api.fdic.gov | The API documentation states no licence or terms of use; no key is required. |

All four are works of US federal agencies, which are not subject to copyright in the United
States (17 U.S.C. 105). That is the basis for redistributing derived files here; it is not a
statement by any of the agencies, and use outside the US may be governed differently. The
derived data carries no additional restrictions from this project. The code is MIT-licensed
(see [LICENSE](LICENSE)).

## What is not verified / limitations

- **Published totals for 2024 and 2025** beyond institution counts were not found. 2025 is
  checked against the Data Browser (which serves the 2025 Snapshot); 2024 only against
  internal consistency and a Data Browser release that is a later vintage.
- **The 2021 mismatch** with the FFIEC release and the CFPB Data Point is explained only as a
  probable re-issue of the snapshot file; the FFIEC was not asked.
- **Federal Register citations** in [docs/changes-over-time.md](docs/changes-over-time.md):
  73 FR 63329 (2008 rate-spread rule) and 84 FR 649 (disclosure policy) were checked
  against search results during the build; the 2015 rule, the 2017 amendments, the 2018
  EGRRCPA rule and the 2020 threshold rule and its 2022 vacatur were cited from their standard
  references and not re-opened.
- **Tract vintages.** The switch to 2010 and 2020 census tracts is inferred from the data
  (tract codes new in 2012 and 2022), not from FFIEC census-file documentation.
- **Complaint matching** is by name and was reviewed by hand only for the medium tier and a
  25-company sample of one high tier; the judgements in that review were not checked against
  an ownership database. The lower tiers of matching are not suitable for analysis of single
  small companies.
- **RSSD ids for 2024-2025** come from earlier panels; a lender that changed charter or was
  acquired after 2023 may carry a stale RSSD and FDIC certificate.
- **`hmda_lar_core` does not re-create one reporting universe.** Coverage rules, reporter
  thresholds and partial exemptions differ by year. The core table makes the codes comparable;
  it does not make the populations comparable. Filters that help are in
  [docs/changes-over-time.md](docs/changes-over-time.md).
- **Pre-2018 data are a later vintage** than the figures first published each year (see 2012
  and 2014 above). Which corrections the CFPB applied is not documented on its page.
- **`record_id` is per release.** If the FFIEC re-issues a snapshot file, record ids may
  change. Use `(activity_year, record_id)` only together with the file's SHA-256 in
  `data/raw/manifest.json`.
- **Runs.** The full pipeline was run on one macOS machine. CI runs lint, type checks, tests
  and `validate --sample` on Ubuntu (first run on GitHub passed, 19 Nov 2026); the full
  build has not been run on Linux or Windows.
- **dbt** was not used (see Design choices), so the dbt-core / dbt-duckdb versions noted as
  working on this machine were not exercised.
- **The survey of existing datasets** in [Why](#why) (Hugging Face uploads, the CFPB's
  HMDA_Data_Science_Kit) was not repeated for this README.

## Development

```bash
make check     # ruff format --check . && ruff check . && mypy && pytest
```

On 19 Nov 2026: `uv run ruff format --check .` (40 files already formatted),
`uv run ruff check .` (all checks passed), `uv run mypy` (`--strict`, no issues in 32 source
files), `uv run pytest` (52 passed in 3.1 s), `uv run openlending validate --sample` (125
checks, all pass). CI (`.github/workflows/ci.yml`) runs the same commands plus a check that
the committed data dictionary matches the schema; it downloads nothing.

Layout:

```
src/openlending/
  sources.py      catalogue of raw files and URLs
  download.py     resumable downloads; manifest.py: SHA-256 manifest
  fdic.py         FDIC BankFind API pulls
  stage.py        zip -> text Parquet, raw line counts, documented repairs
  schema.py       column specs for every table (drives SQL, dictionary and checks)
  codes.py        code lists and labels, both eras and the core schema
  derived.py      FFIEC derived race/ethnicity/sex, SQL and Python
  transform.py    hmda_lar, hmda_lar_core, lenders, FDIC tables, DuckDB views
  matching.py     complaint company -> LEI; complaints.py builds the table
  expected.py     published figures with citations
  validate.py     all checks and the report; reconcile.py: the reconkit runs
  release.py      release assets; sample.py: the committed sample
  dictionary.py   data dictionary
docs/             changes-over-time, data dictionary, complaint matching, validation report
validation/       Data Browser aggregates used by validation (fetched by scripts/)
sample/           committed sample
tests/            pytest suite (runs on the sample)
```

## Reproducing the numbers

| Number | Where it comes from |
|---|---|
| Row counts, sizes | `data/release/release-manifest.json` after `make release-assets`; raw line counts in `data/staging/staging_manifest.json` |
| Download sizes and times | `data/raw/manifest.json` (`bytes`, `seconds`); wall time from the download log |
| Build and validate times, memory | `/usr/bin/time -l uv run openlending build` and `... validate`; per step `data/reports/build_timings.json` |
| Validation results | `data/reports/validation.json`, `docs/validation-report.md` |
| FDIC match rates | `lender_fdic_match_rate` rows in the validation report |
| Complaint match rates | `SELECT match_method, count(*), count(DISTINCT company) FROM mortgage_complaints GROUP BY 1` |
| Tract changes | count of `census_tract` values in a year that are absent the year before, from `hmda_lar_core` |

## License

Code: MIT, Copyright (c) 2026 Linus Dominic Nathaniel. Data: see
[Sources, licences and terms](#sources-licences-and-terms).
