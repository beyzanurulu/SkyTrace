"""Download public PX4 logs from Flight Review (review.px4.io) for evaluation.

Follows the server rules of the official ``flight_review/app/download_logs.py``:
at most 10 requests per minute (6 s between downloads), exponential back-off on
HTTP 503 (honouring ``Retry-After``), and stop immediately on 403 / 444 (IP
blocked). Downloads larger than ``CONFIRM_ABOVE`` files need ``--yes``.

Logs go to ``data/raw/`` (git-ignored) and are for local evaluation only:
Flight Review states no redistribution license for uploaded logs, so they are
never committed. ``index.jsonl`` next to the logs keeps each entry's metadata
(including the uploader's error labels) for building the labeled set.

Usage::

    uv run python -m skytrace.data.flight_review --max-num 10 --mav-type Quadrotor \\
        --error-label Vibration
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
import urllib.error
import urllib.request
import zlib
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import closing
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Final, Protocol

DBINFO_URL: Final = "https://review.px4.io/dbinfo"
DOWNLOAD_URL: Final = "https://review.px4.io/download"
USER_AGENT: Final = "SkyTrace-eval/0.1 (flight log analysis research)"

# Server-politeness values from the official download script (not analysis thresholds).
DEFAULT_DELAY_S: Final = 6.0
DEFAULT_MAX_NUM: Final = 10
CONFIRM_ABOVE: Final = 100
MAX_RETRIES: Final = 5
BACKOFF_BASE_S: Final = 30.0
BACKOFF_MAX_S: Final = 300.0
RETRY_OTHER_S: Final = 10.0
INDEX_TIMEOUT_S: Final = 5 * 60.0
DOWNLOAD_TIMEOUT_S: Final = 10 * 60.0
# The index (~30 MB gzipped) is regenerated once a day; reuse a local copy meanwhile.
INDEX_CACHE_MAX_AGE_S: Final = 24 * 3600.0
INDEX_CACHE_NAME: Final = "dbinfo.json.gz"  # stored compressed (~30 MB vs ~380 MB)

# flight_review/app/plot_app/config_tables.py: error_labels_table
ERROR_LABELS: Final[dict[int, str]] = {
    1: "Other",
    2: "Vibration",
    3: "Airframe-design",
    4: "Sensor-error",
    5: "Component-failure",
    6: "Software",
    7: "Human-error",
    8: "External-conditions",
}


class BlockedError(RuntimeError):
    """The server answered 403 / 444: our IP is blocked. Stop all requests."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    chunks: Iterable[bytes]


class HttpClient(Protocol):
    def get(self, url: str, timeout: float) -> HttpResponse: ...


class UrllibClient:
    """Minimal stdlib HTTP client; non-2xx statuses are returned, not raised."""

    def get(self, url: str, timeout: float) -> HttpResponse:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as err:
            return HttpResponse(err.code, dict(err.headers.items()), [])
        headers = dict(resp.headers.items())
        gzipped = headers.get("Content-Encoding", "").lower() == "gzip"
        return HttpResponse(resp.status, headers, _iter_body(resp, gunzip=gzipped))


class _Body(Protocol):
    def read(self, size: int, /) -> bytes: ...
    def close(self) -> None: ...


def _iter_body(resp: _Body, *, gunzip: bool, size: int = 1 << 16) -> Iterator[bytes]:
    """Stream the body, decoding ``Content-Encoding: gzip`` (urllib does not)."""
    decoder = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS) if gunzip else None
    with closing(resp):
        while chunk := resp.read(size):
            yield decoder.decompress(chunk) if decoder else chunk
        if decoder:
            yield decoder.flush()


@dataclass(frozen=True)
class LogEntry:
    log_id: str
    log_date: date
    mav_type: str
    rating: str
    error_labels: tuple[str, ...]
    vehicle_uuid: str | None
    airframe_name: str | None
    ver_sw: str | None
    sys_hw: str | None
    duration_s: float | None
    raw: dict[str, Any] = field(compare=False, repr=False)

    @classmethod
    def from_json(cls, item: dict[str, Any]) -> LogEntry:
        labels = tuple(
            ERROR_LABELS.get(int(i), f"label_{i}") for i in item.get("error_labels") or []
        )
        return cls(
            log_id=str(item["log_id"]),
            log_date=date.fromisoformat(str(item["log_date"])),
            mav_type=str(item.get("mav_type") or ""),
            rating=str(item.get("rating") or ""),
            error_labels=labels,
            vehicle_uuid=item.get("vehicle_uuid"),
            airframe_name=item.get("airframe_name"),
            ver_sw=item.get("ver_sw"),
            sys_hw=item.get("sys_hw") or None,
            duration_s=None if item.get("duration_s") is None else float(item["duration_s"]),
            raw=item,
        )


def fetch_index(
    client: HttpClient,
    url: str = DBINFO_URL,
    *,
    cache: Path | None = None,
    max_age_s: float = INDEX_CACHE_MAX_AGE_S,
    now: Callable[[], float] = time.time,
) -> list[LogEntry]:
    """Public log index; served from ``cache`` if it is younger than ``max_age_s``."""
    if cache is not None and cache.exists() and now() - cache.stat().st_mtime < max_age_s:
        body = gzip.decompress(cache.read_bytes())
    else:
        resp = client.get(url, INDEX_TIMEOUT_S)
        if resp.status in (403, 444):
            raise BlockedError(f"index request blocked (HTTP {resp.status})")
        if resp.status != 200:
            raise RuntimeError(f"index request failed (HTTP {resp.status})")
        body = b"".join(resp.chunks)
        if cache is not None:
            cache.parent.mkdir(parents=True, exist_ok=True)
            part = cache.with_suffix(".part")
            part.write_bytes(gzip.compress(body, compresslevel=6))
            part.replace(cache)
    items = json.loads(body)
    if not isinstance(items, list):
        raise RuntimeError("unexpected dbinfo payload (expected a JSON list)")
    entries = []
    for item in items:
        try:
            entries.append(LogEntry.from_json(item))
        except (KeyError, ValueError, TypeError):
            continue  # malformed entry: skip rather than abort the whole index
    return entries


def filter_entries(
    entries: Iterable[LogEntry],
    *,
    mav_types: Sequence[str] | None = None,
    error_labels: Sequence[str] | None = None,
    ratings: Sequence[str] | None = None,
    since: date | None = None,
    no_error_labels: bool = False,
    exclude_hw: Sequence[str] | None = None,
    min_duration_s: float | None = None,
    max_duration_s: float | None = None,
    max_per_vehicle: int | None = None,
    max_num: int | None = DEFAULT_MAX_NUM,
) -> list[LogEntry]:
    """Filter like the official script (labels: entry must have all), newest first.

    ``no_error_labels`` keeps only entries without any label (negatives for eval);
    ``max_per_vehicle`` caps logs per ``vehicle_uuid`` so one airframe cannot
    dominate a dataset (entries without uuid count as their own vehicle).
    """
    out = list(entries)
    if mav_types:
        wanted = {m.lower() for m in mav_types}
        out = [e for e in out if e.mav_type.lower() in wanted]
    if error_labels:
        need = {label.lower() for label in error_labels}
        out = [e for e in out if need <= {label.lower() for label in e.error_labels}]
    if ratings:
        wanted_r = {r.lower() for r in ratings}
        out = [e for e in out if e.rating.lower() in wanted_r]
    if since is not None:
        out = [e for e in out if e.log_date >= since]
    if no_error_labels:
        out = [e for e in out if not e.error_labels]
    if exclude_hw:
        excluded = {h.upper() for h in exclude_hw}
        out = [e for e in out if (e.sys_hw or "").upper() not in excluded]
    if min_duration_s is not None:
        out = [e for e in out if e.duration_s is not None and e.duration_s >= min_duration_s]
    if max_duration_s is not None:
        out = [e for e in out if e.duration_s is not None and e.duration_s <= max_duration_s]
    out.sort(key=lambda e: (e.log_date, e.log_id), reverse=True)
    if max_per_vehicle is not None:
        seen: dict[str, int] = {}
        capped = []
        for e in out:
            key = e.vehicle_uuid or f"log:{e.log_id}"
            if seen.get(key, 0) < max_per_vehicle:
                seen[key] = seen.get(key, 0) + 1
                capped.append(e)
        out = capped
    return out if max_num is None else out[:max_num]


@dataclass
class DownloadReport:
    downloaded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


def _fetch_with_retry(
    client: HttpClient, url: str, sleep: Callable[[float], None], log: Callable[[str], None]
) -> HttpResponse | None:
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.get(url, DOWNLOAD_TIMEOUT_S)
        except OSError as err:  # connection refused / reset / timeout
            log(f"  request failed ({err}); retry {attempt + 1}/{MAX_RETRIES}")
            sleep(RETRY_OTHER_S * (attempt + 1))
            continue
        if resp.status == 200:
            return resp
        if resp.status in (403, 444):
            raise BlockedError(
                f"HTTP {resp.status}: IP blocked by Flight Review; stopping. "
                "See https://github.com/PX4/flight_review/issues"
            )
        if resp.status == 404:
            log("  not found (404), skipping")
            return None
        if resp.status == 503:
            retry_after = resp.headers.get("Retry-After")
            wait = (
                float(retry_after)
                if retry_after and retry_after.isdigit()
                else min(BACKOFF_BASE_S * 2**attempt, BACKOFF_MAX_S)
            )
            log(f"  rate limited (503), waiting {wait:.0f} s")
            sleep(wait)
            continue
        log(f"  unexpected HTTP {resp.status}, retrying")
        sleep(RETRY_OTHER_S)
    log(f"  failed after {MAX_RETRIES} attempts")
    return None


def download(
    entries: Sequence[LogEntry],
    dest: Path,
    client: HttpClient,
    *,
    delay_s: float = DEFAULT_DELAY_S,
    overwrite: bool = False,
    sleep: Callable[[float], None] | None = None,
    log: Callable[[str], None] = print,
    download_url: str = DOWNLOAD_URL,
) -> DownloadReport:
    """Download ``entries`` into ``dest`` as ``<log_id>.ulg`` and append to ``index.jsonl``."""
    sleep = sleep if sleep is not None else time.sleep  # looked up at call time (testable)
    dest.mkdir(parents=True, exist_ok=True)
    report = DownloadReport()
    requested = False
    for n, entry in enumerate(entries, start=1):
        target = dest / f"{entry.log_id}.ulg"
        if target.exists() and not overwrite:
            report.skipped.append(entry.log_id)
            continue
        if requested:
            sleep(delay_s)  # rate limit between actual requests only
        requested = True
        log(f"Downloading {n}/{len(entries)} ({entry.log_id})")
        resp = _fetch_with_retry(client, f"{download_url}?log={entry.log_id}", sleep, log)
        if resp is None:
            report.failed.append(entry.log_id)
            continue
        part = target.with_suffix(".ulg.part")
        try:
            with part.open("wb") as fh:
                for chunk in resp.chunks:
                    fh.write(chunk)
            part.replace(target)  # no half-written .ulg on interruption
        except OSError as err:
            part.unlink(missing_ok=True)
            log(f"  write failed: {err}")
            report.failed.append(entry.log_id)
            continue
        with (dest / "index.jsonl").open("a", encoding="utf-8") as idx:
            record = {k: v for k, v in asdict(entry).items() if k != "raw"}
            record["log_date"] = entry.log_date.isoformat()
            idx.write(json.dumps(record) + "\n")
        report.downloaded.append(entry.log_id)
    return report


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--out", type=Path, default=Path("data/raw"), help="download folder")
    p.add_argument("--max-num", "-n", type=int, default=DEFAULT_MAX_NUM)
    p.add_argument("--mav-type", nargs="+", help="e.g. Quadrotor Hexarotor")
    p.add_argument("--error-label", nargs="+", choices=sorted(ERROR_LABELS.values()))
    p.add_argument("--rating", nargs="+", help="e.g. Good")
    p.add_argument("--since", type=date.fromisoformat, help="YYYY-MM-DD")
    p.add_argument("--no-error-labels", action="store_true", help="only logs without labels")
    p.add_argument("--exclude-hw", nargs="+", help="e.g. PX4_SITL")
    p.add_argument("--min-duration", type=float, help="seconds")
    p.add_argument("--max-duration", type=float, help="seconds")
    p.add_argument("--max-per-vehicle", type=int, help="cap logs per vehicle_uuid")
    p.add_argument("--delay", type=float, default=DEFAULT_DELAY_S)
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--refresh-index", action="store_true", help="ignore the cached index")
    p.add_argument("--list", action="store_true", help="only print matching entries")
    p.add_argument("--yes", "-y", action="store_true", help=f"allow > {CONFIRM_ABOVE} files")
    args = p.parse_args(argv)
    if args.delay < DEFAULT_DELAY_S:
        p.error(f"--delay below {DEFAULT_DELAY_S:.0f} s violates the server rate limit")
    if args.max_num <= 0:
        p.error("--max-num must be positive")
    return args


def main(argv: Sequence[str] | None = None, client: HttpClient | None = None) -> int:
    args = _parse_args(argv)
    http = client if client is not None else UrllibClient()
    print("Fetching Flight Review index...")
    cache = args.out / INDEX_CACHE_NAME
    entries = fetch_index(
        http, cache=cache, max_age_s=0.0 if args.refresh_index else INDEX_CACHE_MAX_AGE_S
    )
    selected = filter_entries(
        entries,
        mav_types=args.mav_type,
        error_labels=args.error_label,
        ratings=args.rating,
        since=args.since,
        no_error_labels=args.no_error_labels,
        exclude_hw=args.exclude_hw,
        min_duration_s=args.min_duration,
        max_duration_s=args.max_duration,
        max_per_vehicle=args.max_per_vehicle,
        max_num=args.max_num,
    )
    print(f"{len(entries)} public logs, {len(selected)} selected")
    if args.list:
        for e in selected:
            print(f"{e.log_id}  {e.log_date}  {e.mav_type:<12} {','.join(e.error_labels)}")
        return 0
    if len(selected) > CONFIRM_ABOVE and not args.yes:
        print(
            f"Refusing to download {len(selected)} files without --yes "
            "(Flight Review is funded by the Dronecode Foundation; please be gentle)."
        )
        return 2
    try:
        report = download(selected, args.out, http, delay_s=args.delay, overwrite=args.overwrite)
    except BlockedError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1
    print(
        f"done: {len(report.downloaded)} downloaded, {len(report.skipped)} skipped, "
        f"{len(report.failed)} failed -> {args.out}"
    )
    return 0 if not report.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
