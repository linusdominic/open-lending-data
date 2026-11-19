# Contributing

Issues and pull requests are welcome. Some ground rules:

## Development setup

You need [uv](https://docs.astral.sh/uv/). Python 3.12 is installed by uv if missing.

```bash
make install        # uv sync --python 3.12
make check          # ruff format --check, ruff check, mypy --strict, pytest
```

`make check` runs entirely on the committed sample in `sample/`; it needs no downloads. CI
runs the same commands.

## Changing the schema

Column definitions live in `src/openlending/schema.py` and code lists in
`src/openlending/codes.py`. The build SQL, the domain checks and the data dictionary are all
generated from them. After a change:

```bash
uv run openlending docs     # regenerate docs/data-dictionary.{md,json}
```

CI fails if the committed dictionary is out of date. If the change alters how a field is
mapped across years, update `docs/changes-over-time.md` in the same pull request, with the
source document for the definition.

## Changing the data

A full rebuild needs about 12.4 GB of downloads and 33 GB of disk (raw, staging and output),
plus about 10 GB of temporary space; see the README for timings. If you change the harmonisation, run `make build validate` and
include the validation summary in the pull request. If the sample needs to change, run
`openlending sample` after a full build and commit `sample/` together with the code change.

## Published figures

`src/openlending/expected.py` holds the published aggregates that validation compares
against. Add a figure only with a citation (document, URL, table or page) and never an
estimate. If a figure differs because the source describes a different release of the data,
say so in its note rather than widening the tolerance.

## Style

- `ruff format` and `ruff check` clean; `mypy --strict` clean.
- Plain, specific prose in documentation. Every number in the README must come from a run,
  with the command that produced it.
