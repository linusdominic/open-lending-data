"""Command line interface: ``openlending download|build|validate|docs|release-assets|sample``."""

from __future__ import annotations

import sys
import time

import click

from openlending.config import load_settings


def _log(msg: str) -> None:
    click.echo(f"{time.strftime('%H:%M:%S')} {msg}", err=False)
    sys.stdout.flush()


def _years(value: str | None) -> list[int] | None:
    if not value:
        return None
    out: list[int] = []
    for part in value.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


@click.group()
@click.version_option(package_name="openlending")
def main() -> None:
    """Harmonised US mortgage-lending public data."""


@main.command()
@click.option("--group", "groups", multiple=True, help="Only these source groups (repeatable).")
@click.option("--years", default=None, help="Year list or range, e.g. 2018-2025 or 2017,2016.")
@click.option("--fdic/--no-fdic", default=True, help="Also pull FDIC BankFind data.")
def download(groups: tuple[str, ...], years: str | None, fdic: bool) -> None:
    """Download raw files (one at a time, resumable) and record them in the manifest."""
    from openlending.download import fetch
    from openlending.sources import select

    s = load_settings()
    files = select(list(groups) or None, _years(years))
    for i, raw in enumerate(files, 1):
        _log(f"[{i}/{len(files)}] {raw.key} <- {raw.url}")
        fetch(raw, s.raw_dir, s.manifest_path, log=_log)
    if fdic and (not groups or "fdic" in groups):
        from openlending.fdic import pull_fdic

        pull_fdic(s, log=_log)


@main.command()
@click.option(
    "--step",
    "steps",
    multiple=True,
    help="Run only these steps (stage, lar, historic, lenders, fdic, complaints, core, db).",
)
@click.option("--years", default=None, help="Restrict LAR / historic steps to these years.")
def build(steps: tuple[str, ...], years: str | None) -> None:
    """Build harmonised Parquet tables and the DuckDB database from data/raw."""
    from openlending.pipeline import run_build

    run_build(load_settings(), steps=list(steps) or None, years=_years(years), log=_log)


@main.command()
@click.option("--sample", is_flag=True, help="Validate the committed sample instead of data/.")
@click.option("--strict", is_flag=True, help="Also fail on mismatches with published figures.")
@click.option(
    "--reconkit-year", default=2023, show_default=True, help="Year reconciled with reconkit."
)
def validate(sample: bool, strict: bool, reconkit_year: int) -> None:
    """Run every validation check and write a report.

    Exits 1 if an integrity check fails (or, with --strict, if any published figure differs).
    """
    from openlending.validate import run_validation

    ok = run_validation(
        load_settings(), sample=sample, log=_log, strict=strict, reconkit_year=reconkit_year
    )
    sys.exit(0 if ok else 1)


@main.command()
def docs() -> None:
    """Regenerate the data dictionary (markdown and JSON) from the schema."""
    from openlending.dictionary import write_dictionary

    for path in write_dictionary(load_settings()):
        _log(f"wrote {path}")


@main.command("release-assets")
@click.option("--max-bytes", default=1_900_000_000, show_default=True)
def release_assets(max_bytes: int) -> None:
    """Write per-year Parquet files under the GitHub Release size limit plus a manifest."""
    from openlending.release import build_release

    build_release(load_settings(), max_bytes=max_bytes, log=_log)


@main.command()
def sample() -> None:
    """Draw the small committed sample from the full build."""
    from openlending.sample import write_sample

    write_sample(load_settings(), log=_log)


if __name__ == "__main__":
    main()
