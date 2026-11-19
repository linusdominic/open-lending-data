"""Build orchestration: ``openlending build`` runs these steps in order."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime

from openlending.config import Settings

Log = Callable[[str], None]

STEPS = ["stage", "lar", "core", "historic", "fdic", "lenders", "complaints", "db"]


def _record_timing(s: Settings, step: str, seconds: float, years: list[int] | None) -> None:
    path = s.reports_dir / "build_timings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(path.read_text()) if path.exists() else {}
    label = step if not years else f"{step}[{','.join(map(str, years))}]"
    data[label] = {
        "seconds": round(seconds, 1),
        "finished_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def run_build(
    s: Settings, *, steps: list[str] | None = None, years: list[int] | None = None, log: Log
) -> None:
    todo = steps or STEPS
    unknown = set(todo) - set(STEPS)
    if unknown:
        raise SystemExit(f"unknown step(s): {sorted(unknown)}; choose from {STEPS}")
    for step in STEPS:
        if step not in todo:
            continue
        log(f"== build step: {step}")
        t0 = time.monotonic()
        if step == "stage":
            from openlending.stage import stage_all

            stage_all(s, years=years, log=log)
        elif step == "lar":
            from openlending.transform import build_hmda_lar

            build_hmda_lar(s, years=years, log=log)
        elif step == "historic":
            from openlending.transform import build_historic_core

            build_historic_core(s, years=years, log=log)
        elif step == "lenders":
            from openlending.transform import build_lenders

            build_lenders(s, log=log)
        elif step == "fdic":
            from openlending.transform import build_fdic

            build_fdic(s, log=log)
        elif step == "complaints":
            from openlending.complaints import build_complaints

            build_complaints(s, log=log)
        elif step == "core":
            from openlending.transform import build_core_2018plus

            build_core_2018plus(s, years=years, log=log)
        elif step == "db":
            from openlending.transform import build_database

            build_database(s, log=log)
        seconds = time.monotonic() - t0
        _record_timing(s, step, seconds, years)
        log(f"== {step} done in {seconds:.0f}s")
