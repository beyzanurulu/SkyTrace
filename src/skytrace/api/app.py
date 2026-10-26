"""FastAPI backend of the web UI (``skytrace serve``).

    POST   /analyze            upload a log -> id, summary, findings
    GET    /analysis/{id}      the same again (page reload)
    DELETE /analysis/{id}      delete the upload now
    GET    /report/{id}        the single-file HTML report
    GET    /figures/{id}       timeline + evidence figures (Plotly JSON)
    GET    /plots/{id}/{name}  plots the agent drew with make_plot
    POST   /chat/{id}          question -> server-sent events: step*, answer | error
    GET    /api/status         model, documentation index, limits
    GET    /                   the web UI (static files, Plotly served locally)

The chat stream sends each tool call as it happens and then the verified answer
in one piece: streaming the model's tokens would show numbers before the
verification node has checked them. One question runs at a time (a local model
serves one request at a time anyway); parsed logs and chat sessions are kept in
memory for the ``api.max_loaded`` most recently used analyses and rebuilt from
the stored upload when needed (the chat history then starts over).
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Final

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from plotly.offline import get_plotlyjs
from plotly.utils import PlotlyJSONEncoder
from pydantic import BaseModel, Field

from skytrace import __version__
from skytrace.agent.graph import AgentReply, Complete, FlightAgent, ToolStep
from skytrace.agent.rag import DocSearch, DocsError
from skytrace.agent.tools import AgentContext, call_tool
from skytrace.api.store import Store, UnknownAnalysisError
from skytrace.config import SkyTraceConfig, load_config
from skytrace.detectors import DetectionResult, run_detectors
from skytrace.parsers.schema import FlightLog
from skytrace.report.evidence import evidence_for
from skytrace.report.html import evidence_figure, render_html, timeline_figure

LOG_SUFFIXES: Final = (".ulg", ".bin")
CHUNK: Final = 1 << 20
MULTIPART_SLACK: Final = 1 << 20  # form overhead allowed on top of the file itself
WEB_DIR: Final = Path(__file__).resolve().parent.parent / "web"
_FINDING_ID: Final = re.compile(r"\bF\d{3}\b")


@dataclass
class Session:
    log: FlightLog
    result: DetectionResult
    ctx: AgentContext
    agent: FlightAgent | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


class Sessions:
    """The most recently used parsed logs (parsing a long log takes seconds)."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._items: OrderedDict[str, Session] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str, build: Callable[[], Session]) -> Session:
        with self._lock:
            if key in self._items:
                self._items.move_to_end(key)
                return self._items[key]
        session = build()  # outside the lock: slow
        with self._lock:
            session = self._items.setdefault(key, session)
            self._items.move_to_end(key)
            while len(self._items) > self.limit:
                self._items.popitem(last=False)
        return session

    def drop(self, key: str) -> None:
        with self._lock:
            self._items.pop(key, None)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _tool_json(ctx: AgentContext, name: str) -> Any:  # noqa: ANN401 (JSON value)
    return json.loads(call_tool(ctx, name, {}))


def reply_payload(reply: AgentReply, known_ids: set[str]) -> dict[str, Any]:
    v = reply.verification
    plots: list[str] = []
    sources: list[dict[str, str]] = []
    for m in reply.messages:
        if m.get("role") != "tool":
            continue
        try:
            out = json.loads(str(m["content"]))
        except json.JSONDecodeError:
            continue
        if not isinstance(out, dict):
            continue
        if isinstance(out.get("path"), str):
            plots.append(Path(out["path"]).name)
        for r in out.get("results") or []:
            if isinstance(r, dict) and "url" in r:
                sources.append({"title": str(r.get("title", "")), "url": str(r["url"])})
    return {
        "answer": reply.answer,
        "verified": v.ok,
        "unverified": v.unverified,
        "unknown_ids": v.unknown_ids,
        "unknown_urls": v.unknown_urls,
        "tool_calls": reply.tool_calls,
        "prefetched": reply.prefetched,
        "finding_ids": sorted(set(_FINDING_ID.findall(reply.answer)) & known_ids),
        "plots": list(dict.fromkeys(plots)),
        "sources": list({s["url"]: s for s in sources}.values()),
    }


def create_app(
    config: SkyTraceConfig | None = None,
    *,
    complete: Complete | None = None,
    docs: DocSearch | str | None = "auto",
    clock: Callable[[], float] = time.time,
) -> FastAPI:
    """The app. ``complete`` replaces the model (tests); ``docs="auto"`` opens the index."""
    cfg = config if config is not None else load_config()
    api = cfg.api
    limit_bytes = int(api.max_upload_mb * 1024 * 1024)
    store = Store(api.storage_dir, api.retention_hours * 3600, clock)
    sessions = Sessions(api.max_loaded)
    model_lock = threading.Lock()
    docs_index: DocSearch | None
    if docs == "auto":
        try:
            docs_index = DocSearch(cfg.rag)
        except DocsError:
            docs_index = None
    else:
        docs_index = docs if isinstance(docs, DocSearch) else None

    def session(analysis_id: str) -> Session:
        meta = store.meta(analysis_id)  # raises for unknown / expired ids

        def build() -> Session:
            log = FlightLog.from_file(store.log_path(analysis_id), cfg)
            result = run_detectors(log, cfg, ml=bool(meta.get("ml")))
            plots = store.folder(analysis_id) / "plots"
            return Session(log, result, AgentContext(log, result, cfg, plots, docs_index))

        return sessions.get(analysis_id, build)

    def payload(analysis_id: str, s: Session) -> dict[str, Any]:
        meta = store.meta(analysis_id)
        return {
            "id": analysis_id,
            "filename": meta["filename"],
            "created_at": meta["created_at"],
            "expires_at": meta["expires_at"],
            "ml": bool(meta.get("ml")),
            "summary": _tool_json(s.ctx, "get_flight_summary"),
            "findings": _tool_json(s.ctx, "list_findings")["findings"],
        }

    def sweep() -> None:
        for analysis_id in store.cleanup():
            sessions.drop(analysis_id)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async def loop() -> None:
            while True:
                await asyncio.to_thread(sweep)
                await asyncio.sleep(api.cleanup_interval_s)

        task = asyncio.create_task(loop())
        try:
            yield
        finally:
            task.cancel()

    app = FastAPI(title="SkyTrace", version=__version__, lifespan=lifespan)
    app.state.store = store
    app.state.sweep = sweep

    @app.exception_handler(UnknownAnalysisError)
    async def unknown(_: Request, exc: UnknownAnalysisError) -> JSONResponse:
        return JSONResponse({"detail": "unknown or expired analysis"}, status_code=404)

    @app.middleware("http")
    async def upload_limit(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Refuse an oversized upload before it is read; the copy loop below
        # also counts, for uploads without a Content-Length.
        length = request.headers.get("content-length", "")
        too_large = length.isdigit() and int(length) > limit_bytes + MULTIPART_SLACK
        if request.url.path == "/analyze" and too_large:
            return JSONResponse({"detail": _too_large(api.max_upload_mb)}, status_code=413)
        return await call_next(request)

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        return {
            "version": __version__,
            "model": cfg.agent.model,
            "docs": docs_index is not None,
            "max_upload_mb": api.max_upload_mb,
            "retention_hours": api.retention_hours,
        }

    @app.post("/analyze")
    def analyze(
        file: Annotated[UploadFile, File()], ml: Annotated[bool, Query()] = False
    ) -> dict[str, Any]:
        name = file.filename or ""
        if Path(name).suffix.lower() not in LOG_SUFFIXES:
            raise HTTPException(415, f"expected a .ulg (PX4) or .bin (ArduPilot) log: {name!r}")
        analysis_id, path = store.create(name, ml=ml)
        error: HTTPException | None = None
        try:
            size = 0
            with path.open("wb") as out:
                while chunk := file.file.read(CHUNK):
                    size += len(chunk)
                    if size > limit_bytes:
                        raise HTTPException(413, _too_large(api.max_upload_mb))
                    out.write(chunk)
            if size == 0:
                raise HTTPException(422, "the file is empty")
            store.update(analysis_id, size_bytes=size)
            s = session(analysis_id)
            if not s.log.metadata.duration_s:
                # pymavlink skips bytes it cannot decode: any file "parses" to an empty log
                sessions.drop(analysis_id)
                raise HTTPException(422, "no flight data found in the file (not a flight log?)")
        except HTTPException as exc:
            error = exc
        except Exception as exc:  # parser: corrupt, truncated or unsupported log
            error = HTTPException(422, f"could not read the log: {exc}")
        if error is not None:
            # Outside the except blocks: the parser's traceback (and the file it
            # still holds open) is released, so the folder can be deleted.
            store.discard(path.parent)
            raise error
        return payload(analysis_id, s)

    @app.get("/analysis/{analysis_id}")
    def analysis(analysis_id: str) -> dict[str, Any]:
        return payload(analysis_id, session(analysis_id))

    @app.delete("/analysis/{analysis_id}", status_code=204)
    def delete(analysis_id: str) -> Response:
        store.folder(analysis_id)
        sessions.drop(analysis_id)
        store.delete(analysis_id)
        return Response(status_code=204)

    @app.get("/report/{analysis_id}", response_class=HTMLResponse)
    def report(analysis_id: str) -> HTMLResponse:
        s = session(analysis_id)
        return HTMLResponse(render_html(s.log, s.result, cfg))

    @app.get("/figures/{analysis_id}")
    def figures(analysis_id: str) -> Response:
        s = session(analysis_id)
        evidence: dict[str, Any] = {}
        for f in s.result.findings:
            ev = evidence_for(s.log, f, cfg)
            evidence[f.id] = (
                None
                if ev is None
                else {"title": ev.title, "figure": evidence_figure(ev, f).to_plotly_json()}
            )
        body = {
            "timeline": timeline_figure(s.log, s.result.findings).to_plotly_json(),
            "evidence": evidence,
        }
        return Response(json.dumps(body, cls=PlotlyJSONEncoder), media_type="application/json")

    @app.get("/plots/{analysis_id}/{name}")
    def plot(analysis_id: str, name: str) -> FileResponse:
        store.meta(analysis_id)
        path = store.folder(analysis_id) / "plots" / name
        if Path(name).name != name or path.suffix != ".html" or not path.is_file():
            raise HTTPException(404, "no such plot")
        return FileResponse(path, media_type="text/html")

    @app.post("/chat/{analysis_id}")
    def chat(analysis_id: str, body: ChatRequest) -> StreamingResponse:
        s = session(analysis_id)
        known_ids = {f.id for f in s.result.findings}

        def events() -> Iterator[str]:
            if not model_lock.acquire(blocking=False):
                yield sse("status", {"message": "waiting for the model (another question runs)"})
                model_lock.acquire()
            try:
                with s.lock:
                    if s.agent is None:
                        s.agent = FlightAgent(s.ctx, complete)
                    for item in s.agent.ask_stream(body.question):
                        if isinstance(item, ToolStep):
                            yield sse("step", {"tool": item.name, "arguments": item.arguments})
                        else:
                            yield sse("answer", reply_payload(item, known_ids))
            except Exception as exc:  # the model backend: connection, timeout, ...
                yield sse("error", {"message": f"{type(exc).__name__}: {exc}"})
            finally:
                model_lock.release()

        return StreamingResponse(
            events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    @app.get("/vendor/plotly.min.js")
    def plotly_js() -> Response:
        return Response(
            get_plotlyjs(),
            media_type="application/javascript",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @app.get("/", response_class=HTMLResponse)
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html", media_type="text/html")

    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
    return app


def _too_large(max_mb: float) -> str:
    return f"the log is larger than the {max_mb:g} MB upload limit (api.max_upload_mb)"
