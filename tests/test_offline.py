import re
import socket
import threading
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from skytrace import offline
from skytrace.cli import app
from skytrace.config import ConfigError, load_config, with_model

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_log_small.ulg"


@pytest.fixture(autouse=True)
def _no_guard_left():
    offline.BLOCKED.clear()
    yield
    offline.remove_network_guard()
    offline.BLOCKED.clear()


def test_mode_from_environment(monkeypatch):
    monkeypatch.delenv(offline.MODE_ENV, raising=False)
    assert offline.mode() == "online"
    monkeypatch.setenv(offline.MODE_ENV, " Offline ")
    assert offline.is_offline()
    monkeypatch.setenv(offline.MODE_ENV, "airplane")
    with pytest.raises(ConfigError, match="SKYTRACE_MODE"):
        offline.mode()


def test_defaults_are_offline_ready():
    offline.check_config(load_config())


@pytest.mark.parametrize(
    "agent,rag,message",
    [
        ({"model": "gemini/gemini-2.5-flash"}, {}, "agent.model"),
        ({}, {"embedding_model": "text-embedding-3-small"}, "rag.embedding_model"),
        ({"api_base": "https://my-gpu-box.example.com"}, {}, "not in offline.allowed_hosts"),
        ({}, {"api_base": None}, "rag.api_base must point"),
    ],
)
def test_cloud_settings_are_refused(agent, rag, message):
    cfg = load_config()
    cfg = replace(cfg, agent=replace(cfg.agent, **agent), rag=replace(cfg.rag, **rag))
    with pytest.raises(offline.OfflineError, match=message):
        offline.check_config(cfg)


def test_cloud_model_override_drops_the_ollama_address():
    cfg = load_config()
    assert with_model(cfg, "gemini/gemini-2.5-flash").agent.api_base is None
    assert with_model(cfg, "ollama_chat/llama3.1:8b").agent.api_base == cfg.agent.api_base


def _local_server():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    threading.Thread(target=lambda: srv.accept()[0].close(), daemon=True).start()
    return srv


def test_guard_allows_loopback_and_refuses_the_rest():
    srv = _local_server()
    with offline.network_guard(["localhost"]):
        with socket.create_connection(srv.getsockname(), timeout=2):
            pass  # loopback is fine
        assert socket.getaddrinfo("localhost", 80)
        with pytest.raises(offline.OfflineNetworkError, match=r"example\.com:443"):
            socket.getaddrinfo("example.com", 443)  # not even a DNS lookup
        s = socket.socket()
        with pytest.raises(offline.OfflineNetworkError):
            s.connect(("203.0.113.5", 80))  # TEST-NET-3, refused before any packet
        s.close()
    srv.close()
    assert offline.BLOCKED == ["example.com:443", "203.0.113.5:80"]
    assert socket.getaddrinfo is offline._real_getaddrinfo  # restored


def test_http_clients_fail_loudly():
    with offline.network_guard(["localhost"]), pytest.raises(httpx.ConnectError):
        httpx.get("https://api.example.com/v1/chat", timeout=2)
    assert offline.BLOCKED == ["api.example.com:443"]


def test_activate_sets_offline_environment(monkeypatch):
    monkeypatch.delenv("LITELLM_LOCAL_MODEL_COST_MAP", raising=False)
    offline.activate(load_config())
    import os

    assert os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] == "True"
    with pytest.raises(offline.OfflineNetworkError):
        socket.getaddrinfo("raw.githubusercontent.com", 443)


def test_cli_docs_build_is_refused_offline(monkeypatch):
    monkeypatch.setenv(offline.MODE_ENV, "offline")
    res = CliRunner().invoke(app, ["docs", "build"])
    assert res.exit_code == 2 and "offline mode" in res.output


def test_cli_cloud_model_is_refused_offline(monkeypatch):
    monkeypatch.setenv(offline.MODE_ENV, "offline")
    res = CliRunner().invoke(app, ["chat", str(FIXTURE), "--model", "gemini/x", "--ask", "?"])
    assert res.exit_code == 2 and "not a local (Ollama) model" in " ".join(res.output.split())


def test_cli_analyze_works_offline(monkeypatch, tmp_path):
    monkeypatch.setenv(offline.MODE_ENV, "offline")
    out = tmp_path / "r.html"
    res = CliRunner().invoke(app, ["analyze", str(FIXTURE), "-o", str(out), "-q"])
    assert res.exit_code == 0, res.output
    html = out.read_text("utf-8")
    # Plotly is embedded: no external script / stylesheet. (The bundle mentions
    # cdn.plot.ly as the topojson default, fetched only by geo maps, not used here.)
    assert not re.search(r"<(script|link)[^>]+(src|href)=[\"']https?:", html)
    assert offline.BLOCKED == []
