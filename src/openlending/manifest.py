"""The download manifest: one JSON object per raw file, keyed by catalogue key.

Each entry records the URL, local path, byte size, SHA-256, server Last-Modified / ETag and
how long the download took. The file is rewritten atomically under an exclusive lock so that
two download processes (for example the file queue and the FDIC API pull) can share it.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

Entry = dict[str, Any]


def sha256_file(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(path.suffix + ".lock")
    with lock.open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def read_manifest(path: Path) -> dict[str, Entry]:
    if not path.exists():
        return {}
    data: dict[str, Entry] = json.loads(path.read_text())
    return data


def update_manifest(path: Path, key: str, entry: Entry) -> None:
    with _locked(path):
        data = read_manifest(path)
        data[key] = entry
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(dict(sorted(data.items())), indent=2) + "\n")
        os.replace(tmp, path)
