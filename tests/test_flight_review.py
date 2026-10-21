import gzip
import io
import json
import os
import time
from datetime import date

import pytest

from skytrace.data import flight_review as fr
from skytrace.data.flight_review import (
    BlockedError,
    HttpResponse,
    LogEntry,
    download,
    fetch_index,
    filter_entries,
)


def _item(log_id, log_date="2026-09-01", mav="Quadrotor", labels=(), rating="Good", **kw):
    return {
        "log_id": log_id,
        "log_date": log_date,
        "mav_type": mav,
        "rating": rating,
        "error_labels": list(labels),
        "vehicle_uuid": "v1",
        **kw,
    }


class FakeClient:
    """Returns scripted responses per URL (a list is consumed in order)."""

    def __init__(self, routes):
        self.routes = {k: list(v) if isinstance(v, list) else [v] for k, v in routes.items()}
        self.calls = []

    def get(self, url, timeout):
        self.calls.append(url)
        queue = self.routes[url]
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item


def ok(body=b"ULog\x01data"):
    return HttpResponse(200, {}, [body[:4], body[4:]])


def status(code, headers=None):
    return HttpResponse(code, headers or {}, [])


def _url(log_id):
    return f"{fr.DOWNLOAD_URL}?log={log_id}"


def _entries(*ids):
    return [LogEntry.from_json(_item(i)) for i in ids]


class Recorder:
    def __init__(self):
        self.sleeps = []
        self.lines = []

    def sleep(self, s):
        self.sleeps.append(s)

    def log(self, line):
        self.lines.append(line)


# --- index / filtering -------------------------------------------------------


def test_fetch_index_maps_labels_and_skips_malformed():
    payload = [_item("a", labels=[2, 5]), {"no_log_id": True}, _item("b", log_date="bad")]
    client = FakeClient({fr.DBINFO_URL: HttpResponse(200, {}, [json.dumps(payload).encode()])})
    (entry,) = fetch_index(client)
    assert entry.log_id == "a"
    assert entry.error_labels == ("Vibration", "Component-failure")
    assert entry.log_date == date(2026, 9, 1)


def test_fetch_index_blocked():
    with pytest.raises(BlockedError):
        fetch_index(FakeClient({fr.DBINFO_URL: status(403)}))


def test_filter_entries():
    entries = [
        LogEntry.from_json(_item("old", "2025-01-01", labels=[2])),
        LogEntry.from_json(_item("new", "2026-09-10", labels=[2, 4])),
        LogEntry.from_json(_item("fw", "2026-09-11", mav="Fixed Wing", labels=[2])),
        LogEntry.from_json(_item("bad", "2026-09-12", rating="Crash")),
    ]
    got = filter_entries(entries, mav_types=["quadrotor"], error_labels=["vibration"], max_num=None)
    assert [e.log_id for e in got] == ["new", "old"]  # newest first
    got = filter_entries(entries, error_labels=["Vibration", "Sensor-error"], max_num=None)
    assert [e.log_id for e in got] == ["new"]  # must contain all labels
    assert [e.log_id for e in filter_entries(entries, since=date(2026, 9, 11))] == ["bad", "fw"]
    assert [e.log_id for e in filter_entries(entries, ratings=["crash"])] == ["bad"]
    assert len(filter_entries(entries, max_num=2)) == 2


def test_filter_negatives_hardware_duration_and_vehicle_cap():
    entries = [
        LogEntry.from_json(
            _item("v1a", "2026-09-05", vehicle_uuid="v1", sys_hw="FMU_V6X", duration_s=300)
        ),
        LogEntry.from_json(
            _item("v1b", "2026-09-04", vehicle_uuid="v1", sys_hw="FMU_V6X", duration_s=300)
        ),
        LogEntry.from_json(
            _item("v2", "2026-09-03", vehicle_uuid="v2", sys_hw="FMU_V6X", duration_s=20)
        ),
        LogEntry.from_json(
            _item("sitl", "2026-09-02", vehicle_uuid="v3", sys_hw="PX4_SITL", duration_s=300)
        ),
        LogEntry.from_json(
            _item("lab", "2026-09-01", labels=[2], vehicle_uuid="v4", duration_s=300)
        ),
        LogEntry.from_json(_item("nouuid", "2026-08-01", vehicle_uuid="", duration_s=300)),
    ]
    got = filter_entries(
        entries,
        no_error_labels=True,
        exclude_hw=["px4_sitl"],
        min_duration_s=60,
        max_per_vehicle=1,
        max_num=None,
    )
    assert [e.log_id for e in got] == ["v1a", "nouuid"]
    assert entries[0].sys_hw == "FMU_V6X" and entries[0].duration_s == 300.0


# --- download ----------------------------------------------------------------


def test_download_writes_files_index_and_rate_limits(tmp_path):
    rec = Recorder()
    client = FakeClient({_url("a"): ok(), _url("b"): ok()})
    report = download(_entries("a", "b"), tmp_path, client, sleep=rec.sleep, log=rec.log)
    assert report.downloaded == ["a", "b"]
    assert (tmp_path / "a.ulg").read_bytes() == b"ULog\x01data"
    assert not list(tmp_path.glob("*.part"))
    assert rec.sleeps == [fr.DEFAULT_DELAY_S]  # between requests, not after the last one
    index = [
        json.loads(line)
        for line in (tmp_path / "index.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [r["log_id"] for r in index] == ["a", "b"]
    assert index[0]["log_date"] == "2026-09-01"


def test_download_skips_existing_without_request(tmp_path):
    (tmp_path / "a.ulg").write_bytes(b"old")
    rec = Recorder()
    client = FakeClient({_url("b"): ok()})
    report = download(_entries("a", "b"), tmp_path, client, sleep=rec.sleep, log=rec.log)
    assert (report.skipped, report.downloaded) == (["a"], ["b"])
    assert client.calls == [_url("b")]
    assert rec.sleeps == []  # skipped files cost no delay
    assert (tmp_path / "a.ulg").read_bytes() == b"old"


def test_download_503_honours_retry_after_then_succeeds(tmp_path):
    rec = Recorder()
    client = FakeClient({_url("a"): [status(503, {"Retry-After": "42"}), status(503), ok()]})
    report = download(_entries("a"), tmp_path, client, sleep=rec.sleep, log=rec.log)
    assert report.downloaded == ["a"]
    assert rec.sleeps == [42.0, fr.BACKOFF_BASE_S * 2]  # Retry-After, then backoff attempt 1


def test_download_404_is_skipped_as_failed(tmp_path):
    rec = Recorder()
    client = FakeClient({_url("a"): status(404), _url("b"): ok()})
    report = download(_entries("a", "b"), tmp_path, client, sleep=rec.sleep, log=rec.log)
    assert (report.failed, report.downloaded) == (["a"], ["b"])
    assert not (tmp_path / "a.ulg").exists()


@pytest.mark.parametrize("code", [403, 444])
def test_download_stops_when_blocked(tmp_path, code):
    rec = Recorder()
    client = FakeClient({_url("a"): status(code), _url("b"): ok()})
    with pytest.raises(BlockedError):
        download(_entries("a", "b"), tmp_path, client, sleep=rec.sleep, log=rec.log)
    assert client.calls == [_url("a")]


def test_download_gives_up_after_max_retries(tmp_path):
    rec = Recorder()
    client = FakeClient({_url("a"): ConnectionResetError("reset")})
    report = download(_entries("a"), tmp_path, client, sleep=rec.sleep, log=rec.log)
    assert report.failed == ["a"]
    assert len(client.calls) == fr.MAX_RETRIES


def test_interrupted_body_leaves_no_partial_file(tmp_path):
    def broken():
        yield b"ULog"
        raise ConnectionResetError("mid-stream")

    rec = Recorder()
    client = FakeClient({_url("a"): HttpResponse(200, {}, broken())})
    report = download(_entries("a"), tmp_path, client, sleep=rec.sleep, log=rec.log)
    assert report.failed == ["a"]
    assert list(tmp_path.iterdir()) == []


# --- CLI ---------------------------------------------------------------------


def _index_client(n, **extra_routes):
    payload = [_item(f"id{i}") for i in range(n)]
    return FakeClient(
        {fr.DBINFO_URL: HttpResponse(200, {}, [json.dumps(payload).encode()]), **extra_routes}
    )


def test_cli_list_does_not_download(tmp_path, capsys):
    client = _index_client(3)
    assert fr.main(["--list", "--out", str(tmp_path)], client) == 0
    assert client.calls == [fr.DBINFO_URL]
    assert "id0" in capsys.readouterr().out


def test_cli_refuses_large_download_without_yes(tmp_path):
    client = _index_client(fr.CONFIRM_ABOVE + 1)
    assert fr.main(["-n", str(fr.CONFIRM_ABOVE + 1), "--out", str(tmp_path)], client) == 2
    assert client.calls == [fr.DBINFO_URL]


def test_cli_rejects_delay_below_server_limit():
    with pytest.raises(SystemExit):
        fr.main(["--delay", "1"], FakeClient({}))


def test_cli_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    client = _index_client(2, **{_url("id0"): ok(), _url("id1"): ok()})
    assert fr.main(["-n", "2", "--out", str(tmp_path)], client) == 0
    assert sorted(p.name for p in tmp_path.glob("*.ulg")) == ["id0.ulg", "id1.ulg"]


# --- transport / cache -------------------------------------------------------


def test_iter_body_decodes_gzip_in_chunks():
    payload = json.dumps([_item("a")]).encode() * 50
    body = io.BytesIO(gzip.compress(payload))
    assert b"".join(fr._iter_body(body, gunzip=True, size=7)) == payload
    assert body.closed
    assert b"".join(fr._iter_body(io.BytesIO(b"plain"), gunzip=False)) == b"plain"


def test_index_cache_is_reused_until_stale(tmp_path):
    cache = tmp_path / fr.INDEX_CACHE_NAME
    body = json.dumps([_item("a")]).encode()
    client = FakeClient({fr.DBINFO_URL: HttpResponse(200, {}, [body])})
    clock = [1_000_000.0]

    def now():
        return clock[0]

    assert [e.log_id for e in fetch_index(client, cache=cache, now=now)] == ["a"]
    assert gzip.decompress(cache.read_bytes()) == body
    os.utime(cache, (clock[0], clock[0]))

    clock[0] += 3600  # fresh: no request
    fetch_index(client, cache=cache, now=now)
    assert len(client.calls) == 1

    clock[0] += fr.INDEX_CACHE_MAX_AGE_S  # stale: fetched again
    fetch_index(client, cache=cache, now=now)
    assert len(client.calls) == 2
