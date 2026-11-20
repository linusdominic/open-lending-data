# Requires uv (https://docs.astral.sh/uv/). Large data goes to data/ (gitignored).
UV ?= uv
RUN = $(UV) run

.PHONY: install download build validate docs release-assets sample all test lint format typecheck check clean-build

install:
	$(UV) sync --python 3.12

download:            ## raw files (12.15 GB) and FDIC API pulls into data/raw
	$(RUN) openlending download

build:               ## stage raw files, then build every table and data/openlending.duckdb
	$(RUN) openlending build

validate:            ## every check; writes docs/validation-report.md
	$(RUN) openlending validate

docs:                ## data dictionary from the schema
	$(RUN) openlending docs

release-assets:      ## data/release: Parquet files under 1.9 GB, SHA256SUMS, notes
	$(RUN) openlending release-assets

sample:              ## redraw the committed sample/ from a full build
	$(RUN) openlending sample

all: download build validate docs release-assets

test:
	$(RUN) pytest

lint:
	$(RUN) ruff format --check .
	$(RUN) ruff check .

format:
	$(RUN) ruff format .
	$(RUN) ruff check --fix .

typecheck:
	$(RUN) mypy

check: lint typecheck test

clean-build:         ## remove built tables but keep raw downloads and staging
	rm -rf data/parquet data/release data/openlending.duckdb data/tmp
