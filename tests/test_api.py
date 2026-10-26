import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from skytrace.api import create_app
from skytrace.api.store import Store, safe_filename
from skytrace.config import load_config
from tests.fake_docs import fake_docs
from tests.test_agent import ScriptedModel

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_log_small.ulg"


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def make_client(tmp_path, complete=None, clock=None, agent=None, **api):
    cfg = load_config()
    cfg = replace(
        cfg,
        api=replace(cfg.api, storage_dir=str(tmp_path / "uploads"), **api),
        agent=replace(cfg.agent, **(agent or {})),
    )
    app = create_app(cfg, complete=complete, docs=fake_docs(cfg.rag), clock=clock or Clock())
    return TestClient(app), app


def upload(client, path=FIXTURE, name=None, ml=False):
    with open(path, "rb") as f:
        return client.post(f"/analyze?ml={str(ml).lower()}", files={"file": (name or path.name, f)})


def events(response):
    out = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_analyze_then_report_figures_and_reload(tmp_path):
    client, _ = make_client(tmp_path)
    res = upload(client)
    assert res.status_code == 200, res.text
    a = res.json()
    assert len(a["id"]) == 32 and a["filename"] == "sample_log_small.ulg"
    assert [f["id"] for f in a["findings"]] == ["F001", "F002"]
    assert a["summary"]["findings"]["warn"] == 2
    assert a["expires_at"] - a["created_at"] == 24 * 3600

    assert client.get(f"/analysis/{a['id']}").json()["findings"] == a["findings"]
    report = client.get(f"/report/{a['id']}")
    assert report.status_code == 200 and "<!doctype html>" in report.text.lower()
    figs = client.get(f"/figures/{a['id']}").json()
    assert figs["timeline"]["data"] and set(figs["evidence"]) == {"F001", "F002"}
    assert figs["evidence"]["F002"]["figure"]["data"][0]["meta"]["role"] == "series"


def test_chat_streams_tool_steps_then_the_verified_answer(tmp_path):
    model = ScriptedModel(
        [
            {"tool": "list_findings", "args": {"detector": "gps"}},
            {"answer": "Evet: F001 (0.2-1.7 s), EPH 3.26 m (eşik 3.0 m)."},
            {"answer": "Bir önceki cevaptaki F001."},
        ]
    )
    client, _ = make_client(tmp_path, complete=model)
    analysis_id = upload(client).json()["id"]
    res = client.post(f"/chat/{analysis_id}", json={"question": "GPS'te sorun var mı?"})
    assert res.headers["content-type"].startswith("text/event-stream")
    (kind, step), (kind2, answer) = events(res)
    assert (kind, step) == ("step", {"tool": "list_findings", "arguments": {"detector": "gps"}})
    assert kind2 == "answer" and answer["verified"] is True
    assert answer["finding_ids"] == ["F001"] and answer["tool_calls"] == ["list_findings"]

    # same session: the second question sees the first one
    res = client.post(f"/chat/{analysis_id}", json={"question": "Hangisiydi?"})
    assert events(res)[-1][1]["answer"] == "Bir önceki cevaptaki F001."
    sent = model.calls[-1][0]
    assert any(m.get("content") == "GPS'te sorun var mı?" for m in sent)


def test_chat_doc_question_returns_sources(tmp_path):
    model = ScriptedModel([{"answer": "Pervaneleri balanslayın."}])
    # the fake embedding's scores are not calibrated: let every prefetch through
    client, _ = make_client(tmp_path, complete=model, agent={"docs_prefetch_min_score": 0.0})
    analysis_id = upload(client).json()["id"]
    res = client.post(f"/chat/{analysis_id}", json={"question": "Titreşimi nasıl azaltırım?"})
    (_kind, step), (_, answer) = events(res)
    assert step["tool"] == "search_docs"
    assert answer["sources"] and all(s["url"].startswith("https://") for s in answer["sources"])
    assert "Documentation searched" in answer["answer"]


def test_model_errors_are_reported_in_the_stream(tmp_path):
    def broken(messages, tools):
        raise ConnectionError("ollama not running")

    client, _ = make_client(tmp_path, complete=broken)
    analysis_id = upload(client).json()["id"]
    res = client.post(f"/chat/{analysis_id}", json={"question": "Uçuş ne kadar sürdü?"})
    assert events(res) == [("error", {"message": "ConnectionError: ollama not running"})]


def test_empty_question_is_rejected(tmp_path):
    client, _ = make_client(tmp_path)
    analysis_id = upload(client).json()["id"]
    assert client.post(f"/chat/{analysis_id}", json={"question": ""}).status_code == 422


@pytest.mark.parametrize(
    "name,content,status",
    [
        ("notes.txt", b"hello", 415),
        ("empty.ulg", b"", 422),
        ("broken.ulg", b"not a ulog file" * 100, 422),
        ("broken.bin", b"\x00\x01" * 500, 422),
    ],
)
def test_bad_uploads_leave_nothing_behind(tmp_path, name, content, status):
    client, _ = make_client(tmp_path)
    res = client.post("/analyze", files={"file": (name, content)})
    assert res.status_code == status, res.text
    uploads = tmp_path / "uploads"
    assert not uploads.exists() or not any(uploads.iterdir())


def test_upload_size_limit(tmp_path):
    client, _ = make_client(tmp_path, max_upload_mb=0.01)  # ~10 kB; the fixture is larger
    res = upload(client)
    assert res.status_code == 413 and "upload limit" in res.json()["detail"]
    # refused from the Content-Length header alone, before the body is read
    res = client.post("/analyze", files={"file": ("big.ulg", b"x" * (1 << 21))})
    assert res.status_code == 413
    assert not any((tmp_path / "uploads").iterdir())


def test_uploads_expire_after_the_retention_time(tmp_path):
    clock = Clock()
    client, app = make_client(tmp_path, clock=clock)
    analysis_id = upload(client).json()["id"]
    clock.now += 23 * 3600
    assert client.get(f"/analysis/{analysis_id}").status_code == 200
    clock.now += 2 * 3600
    assert client.get(f"/analysis/{analysis_id}").status_code == 404  # expired, still on disk
    app.state.sweep()
    assert not (tmp_path / "uploads" / analysis_id).exists()


def test_delete_and_unknown_ids(tmp_path):
    client, _ = make_client(tmp_path)
    analysis_id = upload(client).json()["id"]
    assert client.delete(f"/analysis/{analysis_id}").status_code == 204
    assert client.get(f"/analysis/{analysis_id}").status_code == 404
    for bad in ("0" * 32, "not-an-id", "..%2F..%2Fsecrets"):
        assert client.get(f"/report/{bad}").status_code == 404


def test_plots_are_served_from_the_analysis_folder_only(tmp_path):
    client, _ = make_client(tmp_path)
    analysis_id = upload(client).json()["id"]
    plots = tmp_path / "uploads" / analysis_id / "plots"
    plots.mkdir()
    (plots / "battery_voltage.html").write_text("<html>plot</html>", "utf-8")
    assert client.get(f"/plots/{analysis_id}/battery_voltage.html").text == "<html>plot</html>"
    assert client.get(f"/plots/{analysis_id}/meta.json").status_code == 404
    assert client.get(f"/plots/{analysis_id}/..%2Fmeta.json").status_code == 404


def test_ui_and_local_assets_are_served(tmp_path):
    client, _ = make_client(tmp_path)
    page = client.get("/")
    assert page.status_code == 200 and "SKYTRACE" in page.text
    assert "http" not in page.text.split("<body>")[1].replace("http://www.w3.org", "")
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/app.css").status_code == 200
    assert len(client.get("/vendor/plotly.min.js").content) > 1_000_000  # local, no CDN
    status = client.get("/api/status").json()
    assert status["docs"] is True and status["retention_hours"] == 24


def test_safe_filenames():
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("C:\\logs\\my flight (2).ulg") == "my_flight_2_.ulg"
    assert safe_filename("....") == "log"
    assert len(safe_filename("a" * 300 + ".bin")) == 100


def test_cleanup_removes_unfinished_folders(tmp_path):
    store = Store(tmp_path, retention_s=10, clock=lambda: 1e12)
    (tmp_path / "half-written").mkdir()
    assert store.cleanup() == ["half-written"]
