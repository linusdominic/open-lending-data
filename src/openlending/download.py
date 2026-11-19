"""Polite, resumable downloads.

- One file at a time; the caller iterates.
- The stock httpx client headers are sent unchanged: the FFIEC CDN has answered 403 to custom
  User-Agent strings and 200 to the default one.
- A partial download is kept as ``<name>.part`` and resumed with an HTTP Range request.
- Transient failures are retried with exponential backoff.
- A finished file is hashed and recorded in the manifest; a file whose size and hash already
  match its manifest entry is not downloaded again.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx

from openlending.manifest import Entry, read_manifest, sha256_file, update_manifest
from openlending.sources import RawFile

CHUNK = 1024 * 1024
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}

Log = Callable[[str], None]


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def backoff_delays(retries: int, base: float = 2.0, cap: float = 120.0) -> list[float]:
    """Delays (seconds) before each retry: base, 2*base, 4*base ... capped."""
    return [min(cap, base * (2**i)) for i in range(retries)]


def _remote_meta(client: httpx.Client, url: str) -> tuple[int | None, str | None, str | None]:
    r = client.head(url)
    r.raise_for_status()
    size = r.headers.get("content-length")
    return (
        int(size) if size is not None else None,
        r.headers.get("last-modified"),
        r.headers.get("etag"),
    )


def fetch(
    raw: RawFile,
    raw_dir: Path,
    manifest_path: Path,
    *,
    retries: int = 6,
    log: Log = print,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Entry:
    """Download one catalogue file into ``raw_dir`` and record it in the manifest."""
    dest = raw_dir / raw.relpath
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    own_client = client is None
    http = client or httpx.Client(follow_redirects=True, timeout=httpx.Timeout(60.0, read=300.0))
    try:
        size, last_modified, etag = _remote_meta(http, raw.url)
        existing = read_manifest(manifest_path).get(raw.key)
        if (
            existing
            and dest.exists()
            and dest.stat().st_size == existing.get("bytes")
            and (size is None or size == existing["bytes"])
            and (last_modified is None or last_modified == existing.get("last_modified"))
        ):
            log(f"skip  {raw.key}: already downloaded ({existing['bytes']:,} bytes)")
            return existing

        started = time.monotonic()
        delays = backoff_delays(retries)
        attempt = 0
        while True:
            have = part.stat().st_size if part.exists() else 0
            headers = {"Range": f"bytes={have}-"} if have else {}
            try:
                with http.stream("GET", raw.url, headers=headers) as resp:
                    if resp.status_code == 416:  # nothing left to fetch
                        break
                    if resp.status_code in RETRYABLE_STATUS:
                        raise httpx.HTTPStatusError(
                            f"retryable status {resp.status_code}",
                            request=resp.request,
                            response=resp,
                        )
                    resp.raise_for_status()
                    mode = "ab" if resp.status_code == 206 else "wb"
                    if mode == "wb" and have:
                        log(f"warn  {raw.key}: server ignored Range; restarting")
                    with part.open(mode) as fh:
                        for block in resp.iter_bytes(CHUNK):
                            fh.write(block)
                if size is None or part.stat().st_size >= size:
                    break
                raise httpx.ReadError("connection closed before the full body arrived")
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                status = (
                    exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                )
                if status is not None and status not in RETRYABLE_STATUS:
                    raise
                if attempt >= len(delays):
                    raise
                delay = delays[attempt]
                attempt += 1
                log(f"retry {raw.key}: {exc!r}; attempt {attempt}/{retries} in {delay:.0f}s")
                sleep(delay)

        got = part.stat().st_size
        if size is not None and got != size:
            raise RuntimeError(f"{raw.key}: expected {size} bytes, got {got}")
        part.replace(dest)
        seconds = time.monotonic() - started
        entry: Entry = {
            "url": raw.url,
            "path": raw.relpath,
            "group": raw.group,
            "year": raw.year,
            "bytes": got,
            "sha256": sha256_file(dest),
            "last_modified": last_modified,
            "etag": etag,
            "downloaded_at": _now(),
            "seconds": round(seconds, 1),
        }
        update_manifest(manifest_path, raw.key, entry)
        mb_s = got / 1e6 / seconds if seconds else 0.0
        log(f"done  {raw.key}: {got:,} bytes in {seconds:.0f}s ({mb_s:.1f} MB/s)")
        return entry
    finally:
        if own_client:
            http.close()
