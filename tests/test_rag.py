import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from skytrace.agent import AgentContext, FlightAgent, call_tool
from skytrace.agent.graph import SOURCES_HEADER, wants_docs
from skytrace.agent.rag import (
    Chunk,
    DocSearch,
    DocsError,
    build_index,
    chunk_file,
    collect_chunks,
    fetch_source,
    page_url,
    select_files,
)
from skytrace.config import DocSourceConfig, load_config
from skytrace.evaluation.agent_questions import check_reply
from tests.fake_docs import fake_docs, fake_embed
from tests.test_agent import ScriptedModel

RAG = load_config().rag

MD = """---
title: ignored front matter
---
# Vibration Isolation

Intro paragraph with a [link](../x.md) and an ![image](img.png) here.

::: tip
Keep accel vibration low, below 30 m/s/s on each axis.
:::

## Measuring vibration

```sh
# not a heading inside a code fence
listener sensor_combined
```

Use the [Flight Review](https://review.px4.io) vibration plots.
"""

RST = """.. _common-measuring-vibration:

=====================
Measuring Vibration
=====================

Vibration levels below :ref:`30m/s/s <vibe>` are normally acceptable.

.. image:: ../images/vibe.png
    :target: ../_images/vibe.png

Clipping
========

Any clip count above zero is worth a look, see `the forum <https://x.org>`__ for help.

Clip0
-----

Primary IMU clipping counter, it should stay at zero for a healthy flight.
"""


def test_markdown_chunks_paths_urls_and_cleanup():
    chunks = chunk_file(
        "px4", "docs/en/assembly/vibration_isolation.md", MD, RAG.px4.url_base, 1500
    )
    titles = [c.title for c in chunks]
    assert titles == ["Vibration Isolation", "Vibration Isolation > Measuring vibration"]
    first, second = chunks
    assert first.url == "https://docs.px4.io/main/en/assembly/vibration_isolation.html"
    assert second.url.endswith("vibration_isolation.html#measuring-vibration")
    assert "front matter" not in first.text and ":::" not in first.text
    assert "a link and an image here" in first.text
    assert "# not a heading" in second.text  # code fence kept as content


def test_rst_chunks_levels_roles_and_directives():
    chunks = chunk_file(
        "ardupilot",
        "common/source/docs/common-measuring-vibration.rst",
        RST,
        RAG.ardupilot.url_base,
        1500,
    )
    assert [c.title for c in chunks] == [
        "Measuring Vibration",
        "Measuring Vibration > Clipping",
        "Measuring Vibration > Clipping > Clip0",
    ]
    assert chunks[0].url == "https://ardupilot.org/copter/docs/common-measuring-vibration.html"
    assert chunks[2].url.endswith("#clip0")
    assert "below 30m/s/s are normally" in chunks[0].text
    assert ".. image" not in chunks[0].text and ":target:" not in chunks[0].text
    assert "see the forum for help" in chunks[1].text


def test_long_sections_are_split_under_the_limit():
    body = "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(20))
    chunks = chunk_file("px4", "docs/en/a.md", f"# A\n\n{body}", RAG.px4.url_base, 500)
    assert len(chunks) > 5 and all(len(c.text) <= 500 for c in chunks)


def test_page_urls():
    assert page_url("px4", "docs/en/log/flight_log_analysis.md", "https://d/") == (
        "https://d/log/flight_log_analysis.html"
    )
    assert page_url("ardupilot", "copter/source/docs/tuning.rst", "https://a/") == (
        "https://a/tuning.html"
    )


def test_select_files_by_path_or_title(tmp_path):
    (tmp_path / "docs/en/x").mkdir(parents=True)
    (tmp_path / "docs/en/x/battery_setup.md").write_text("# Power\n\ntext", "utf-8")
    (tmp_path / "docs/en/x/misc.md").write_text("# GPS and Compass\n\ntext", "utf-8")
    (tmp_path / "docs/en/x/camera.md").write_text("# Camera\n\ntext", "utf-8")
    picked = select_files(tmp_path, ["docs/en/**/*.md"], ["battery", "gps"])
    assert [p.name for p in picked] == ["battery_setup.md", "misc.md"]


# --- index + search -------------------------------------------------------------------


CHUNKS = [
    Chunk(
        "px4",
        "a.md",
        "Vibration Isolation",
        "https://d/vib.html",
        "Vibration damping mounts reduce accelerometer vibration and clipping.",
    ),
    Chunk(
        "px4",
        "b.md",
        "Battery",
        "https://d/bat.html",
        "Battery voltage sag under load and cell count configuration.",
    ),
    Chunk(
        "ardupilot",
        "c.rst",
        "GPS",
        "https://a/gps.html",
        "GPS satellites, HDOP and position accuracy before arming.",
    ),
]


def test_build_and_search_in_memory():
    assert build_index(CHUNKS, RAG, fake_embed, location=":memory:") == 3
    hits = DocSearch(RAG, fake_embed, location=":memory:").search("vibration clipping", top_k=2)
    assert hits[0]["url"] == "https://d/vib.html" and len(hits) == 2
    assert set(hits[0]) == {"title", "url", "source", "score", "text"}


def test_index_on_disk_records_the_model(tmp_path):
    build_index(CHUNKS, RAG, fake_embed, location=tmp_path / "idx", sources={"px4": "x@1"})
    manifest = json.loads((tmp_path / "idx" / "manifest.json").read_text("utf-8"))
    assert manifest["embedding_model"] == RAG.embedding_model and manifest["chunks"] == 3
    other = replace(RAG, embedding_model="ollama/other")
    with pytest.raises(DocsError, match="rebuild"):
        DocSearch(other, fake_embed, location=tmp_path / "idx")
    with pytest.raises(DocsError, match="docs build"):
        DocSearch(RAG, fake_embed, location=tmp_path / "missing")


def test_empty_selection_is_an_error():
    with pytest.raises(DocsError):
        build_index([], RAG, fake_embed, location=":memory:")


def test_fetch_sparse_checkout_of_text_files(tmp_path):
    repo = tmp_path / "origin"
    (repo / "docs/en/sub").mkdir(parents=True)
    (repo / "docs/en/sub/gps.md").write_text(
        "# GPS\n\nGPS setup text, long enough to pass the stub filter.", "utf-8"
    )
    (repo / "docs/en/sub/pic.png").write_bytes(b"\x89PNG")
    (repo / "code.c").write_text("int main;", "utf-8")
    for args in (
        ["init", "-q", "-b", "main"],
        ["add", "."],
        ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
    ):
        subprocess.run(["git", *args], cwd=repo, check=True)
    src = DocSourceConfig(
        repo=repo.as_uri(), ref="main", include=["/docs/en/**/*.md"], url_base="https://d/"
    )
    root, commit = fetch_source("px4", src, tmp_path / "docs")
    files = sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and ".git" not in p.parts
    )
    assert files == ["docs/en/sub/gps.md"] and len(commit) == 40
    cfg = replace(RAG, keywords=["gps"])
    chunks = collect_chunks(cfg, {"px4": root})
    assert [c.url for c in chunks] == ["https://docs.px4.io/main/en/sub/gps.html"]


# --- agent integration ----------------------------------------------------------------


@pytest.fixture(scope="module")
def ctx_docs(tmp_path_factory):
    from skytrace import FlightLog
    from skytrace.detectors import run_detectors

    cfg = load_config()
    root = Path(__file__).resolve().parent
    log = FlightLog.from_file(root / "fixtures" / "sample_log_small.ulg", cfg)
    docs = fake_docs(cfg.rag)
    return AgentContext(log, run_detectors(log, cfg), cfg, tmp_path_factory.mktemp("p"), docs)


def test_search_docs_tool_with_and_without_index(ctx_docs):
    out = json.loads(call_tool(ctx_docs, "search_docs", {"query": "vibration levels"}))
    assert out["available"] is True and out["results"][0]["url"].startswith("https://")
    off = replace(ctx_docs, docs=None)
    assert json.loads(call_tool(off, "search_docs", {"query": "x"}))["available"] is False


def test_doc_answer_with_url_and_doc_number_is_verified(ctx_docs):
    case = {
        "expect": {
            "tools": ["search_docs"],
            "verified": True,
            "key_terms_any": ["common-measuring-vibration.html"],
        },
    }
    model = ScriptedModel(
        [
            {"tool": "search_docs", "args": {"query": "acceptable vibration levels"}},
            {
                "answer": "ArduPilot dokümanına göre 30 m/s/s altı kabul edilebilir "
                "(https://ardupilot.org/copter/docs/common-measuring-vibration.html)."
            },
        ]
    )
    reply = FlightAgent(ctx_docs, model).ask("Kabul edilebilir titreşim seviyesi nedir?")
    assert check_reply(case, reply) == [], reply.answer


def test_made_up_urls_are_flagged(ctx_docs):
    model = ScriptedModel(
        [
            {"tool": "search_docs", "args": {"query": "reduce vibration"}},
            {
                "answer": "Pervaneleri balanslayın "
                "(https://docs.px4.io/main/en/assembly/vibration_isolation.html#fixing-vibration), "
                "bkz. https://docs.px4.io/main/en/troubleshooting/motor_balance.html."
            },
        ]
    )
    reply = FlightAgent(ctx_docs, model).ask("Titreşimi nasıl azaltırım?")
    # another anchor of a returned page is fine; a page no tool returned is not
    assert reply.verification.unknown_urls == [
        "https://docs.px4.io/main/en/troubleshooting/motor_balance.html"
    ]
    assert reply.verification.unverified == []  # digits inside urls are not numbers
    assert "urls https://docs.px4.io/main/en/troubleshooting" in reply.answer


def with_min_score(ctx, score):
    agent = replace(ctx.config.agent, docs_prefetch_min_score=score)
    return replace(ctx, config=replace(ctx.config, agent=agent))


VIB_URL = "https://docs.px4.io/main/en/assembly/vibration_isolation.html"


def test_how_to_question_searches_docs_up_front(ctx_docs):
    model = ScriptedModel([{"answer": f"Pervaneleri balanslayın ({VIB_URL})."}])  # no tool call
    reply = FlightAgent(with_min_score(ctx_docs, 0.0), model).ask("Titreşimi nasıl azaltırım?")
    messages, _ = model.calls[0]
    assert messages[-1]["role"] == "tool" and VIB_URL in messages[-1]["content"]
    assert reply.tool_calls == [] and "search_docs" in reply.prefetched
    case = {"expect": {"tools": ["search_docs"], "verified": True, "key_terms_any": [VIB_URL]}}
    assert check_reply(case, reply) == [], reply.answer
    assert SOURCES_HEADER not in reply.answer  # cited by the model already


def test_sources_are_appended_when_the_model_drops_them(ctx_docs):
    model = ScriptedModel([{"answer": "Pervaneleri balanslayın, kontrolcüyü köpüğe monte edin."}])
    reply = FlightAgent(with_min_score(ctx_docs, 0.0), model).ask("Titreşimi nasıl azaltırım?")
    assert SOURCES_HEADER in reply.answer and SOURCES_HEADER not in reply.raw_answer
    assert "https://" in reply.answer.split(SOURCES_HEADER)[1]


def test_low_scoring_prefetch_is_dropped(ctx_docs):
    model = ScriptedModel([{"answer": "Sadece bu log hakkında cevap verebilirim."}])
    reply = FlightAgent(with_min_score(ctx_docs, 1.01), model).ask("Yarın hava nasıl olacak?")
    assert "search_docs" not in reply.prefetched and reply.answer == reply.raw_answer


def test_terms_match_at_word_starts():
    terms = load_config().agent.docs_prefetch_terms
    assert wants_docs("Titreşimi nasıl azaltırım?", terms)
    assert wants_docs("How do I fix the GPS?", terms)
    assert not wants_docs("3 ile 5. saniyeler arasında hata ne kadardı?", terms)  # "niye"


@pytest.mark.parametrize("question", ["Uçuş ne kadar sürdü?", "Is the GPS fine?"])
def test_log_questions_do_not_search_docs(ctx_docs, question):
    model = ScriptedModel([{"answer": "Bilmiyorum."}])
    reply = FlightAgent(ctx_docs, model).ask(question)
    assert "search_docs" not in reply.prefetched
    assert model.calls[0][0][-1]["role"] == "user"


def test_no_docs_prefetch_without_index(ctx_docs):
    model = ScriptedModel([{"answer": "Bilmiyorum."}])
    reply = FlightAgent(replace(ctx_docs, docs=None), model).ask("Titreşimi nasıl azaltırım?")
    assert "search_docs" not in reply.prefetched


def test_cli_docs_search_without_index(tmp_path):
    from typer.testing import CliRunner

    from skytrace.cli import app

    cfg = tmp_path / "c.yaml"
    cfg.write_text(f"rag:\n  index_dir: {(tmp_path / 'none').as_posix()}\n", "utf-8")
    res = CliRunner().invoke(app, ["docs", "search", "vibration", "-c", str(cfg)])
    assert res.exit_code == 2 and "docs build" in res.output
