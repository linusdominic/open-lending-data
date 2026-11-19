# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-19

### Added

- `openlending download`: resumable, one-at-a-time downloads of the FFIEC HMDA Snapshot
  National Loan-Level Dataset (LAR, Transmittal Sheet, Reporter Panel) for 2018-2025, the CFPB
  historic HMDA LAR, panel and transmittal sheets for 2007-2017, the FFIEC ARID-to-LEI
  crosswalk, the CFPB Consumer Complaint Database and FDIC BankFind institutions and quarterly
  financials, with a SHA-256 manifest.
- `openlending build`: staging to text Parquet, then the tables `hmda_lar`, `hmda_lar_core`,
  `lenders`, `bank_financials`, `fdic_institutions`, `mortgage_complaints` as zstd Parquet
  partitioned by year, and a DuckDB database with views over them.
- `openlending validate`: row counts against the raw files, published FFIEC / CFPB / Federal
  Reserve figures, key uniqueness, referential integrity, code domains, parse losses, the
  derived race/ethnicity/sex port against the FFIEC's values, null rates, and a reconkit
  reconciliation of the raw and harmonised 2023 LAR.
- `openlending docs`: data dictionary in Markdown and JSON, generated from the schema.
- `openlending release-assets`: per-year Parquet files under 1.9 GB, SHA256SUMS, manifest and
  release notes.
- Committed sample (`sample/`) and tests that run without downloads.
