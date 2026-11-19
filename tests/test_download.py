from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest

from openlending.download import backoff_delays, fetch
from openlending.manifest import read_manifest
from openlending.sources import RawFile, catalogue, select

BODY = bytes(range(256)) * 400  # 102,400 bytes
RAW = RawFile("test_file", "https://example.test/data/test.zip", "lar", 2099)


def _handler(fail_first: int = 0, cut_at: int | None = None) -> httpx.MockTransport:
    state = {"gets": 0}

    def handle(request: httpx.Request) -> httpx.Response:
        headers = {
            "content-length": str(len(BODY)),
            "last-modified": "Wed, 01 Jan 2025 00:00:00 GMT",
        }
        if request.method == "HEAD":
            return httpx.Response(200, headers=headers)
        state["gets"] += 1
        if state["gets"] <= fail_first:
            return httpx.Response(503)
        rng = request.headers.get("range")
        start = int(rng.split("=")[1].rstrip("-")) if rng else 0
        body = BODY[start:]
        if cut_at is not None and state["gets"] == fail_first + 1:
            body = BODY[start:cut_at]
        status = 206 if rng else 200
        return httpx.Response(status, content=body)

    return httpx.MockTransport(handle)


def test_backoff_delays() -> None:
    assert backoff_delays(4, base=2, cap=10) == [2, 4, 8, 10]


def test_fetch_retries_and_records_manifest(tmp_path: Path) -> None:
    client = httpx.Client(transport=_handler(fail_first=2))
    sleeps: list[float] = []
    entry = fetch(
        RAW,
        tmp_path,
        tmp_path / "manifest.json",
        client=client,
        log=lambda _: None,
        sleep=sleeps.append,
    )
    assert sleeps == [2.0, 4.0]
    dest = tmp_path / RAW.relpath
    assert dest.read_bytes() == BODY
    assert entry["sha256"] == hashlib.sha256(BODY).hexdigest()
    assert read_manifest(tmp_path / "manifest.json")["test_file"]["bytes"] == len(BODY)
    # A second call finds the file in the manifest and does not download again.
    again = fetch(RAW, tmp_path, tmp_path / "manifest.json", client=client, log=lambda _: None)
    assert again["downloaded_at"] == entry["downloaded_at"]


def test_fetch_resumes_partial_download(tmp_path: Path) -> None:
    client = httpx.Client(transport=_handler(cut_at=50_000))
    entry = fetch(
        RAW,
        tmp_path,
        tmp_path / "manifest.json",
        client=client,
        log=lambda _: None,
        sleep=lambda _: None,
    )
    assert (tmp_path / RAW.relpath).read_bytes() == BODY
    assert entry["bytes"] == len(BODY)


def test_fetch_gives_up_on_client_error(tmp_path: Path) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    client = httpx.Client(transport=httpx.MockTransport(handle))
    with pytest.raises(httpx.HTTPStatusError):
        fetch(RAW, tmp_path, tmp_path / "manifest.json", client=client, log=lambda _: None)


def test_catalogue_is_unique_and_selectable() -> None:
    keys = [f.key for f in catalogue()]
    assert len(keys) == len(set(keys))
    lar = select(["lar"], [2018, 2025])
    assert [f.key for f in lar] == ["lar_2018", "lar_2025"]
    assert all(f.url.startswith("https://") for f in catalogue())
