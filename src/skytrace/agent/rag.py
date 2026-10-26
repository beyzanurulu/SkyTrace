"""Documentation search (RAG) for the agent's ``search_docs`` tool.

Pipeline (``skytrace docs build``):

1. **fetch**: shallow, sparse git checkout of the PX4 user guide (Markdown,
   CC BY 4.0) and the ArduPilot wiki (reStructuredText, CC BY-SA 3.0); text
   files only, into ``rag.docs_dir``.
2. **select**: files whose path or title matches ``rag.keywords`` (log
   analysis, vibration, tuning, GPS, battery, failsafe, ...).
3. **chunk**: split at headings (Markdown ``#``, reST underlines); every chunk
   keeps its heading path and the public URL of its page (+ ``#anchor``).
4. **embed + index**: local embedding model through LiteLLM (Ollama, bge-m3 by
   default), stored in Qdrant local mode in ``rag.index_dir``.

``DocSearch.search(query)`` embeds the question with the same model and returns
the ``rag.top_k`` best chunks with title, URL and an excerpt. Nothing leaves the
machine when a local embedding model is used.
"""

from __future__ import annotations

import atexit
import json
import re
import subprocess
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

from skytrace.config import DocSourceConfig, RagConfig

Embed = Callable[[list[str]], list[list[float]]]

COLLECTION: Final = "skytrace_docs"
MANIFEST: Final = "manifest.json"
SOURCES: Final = ("px4", "ardupilot")


class DocsError(RuntimeError):
    """Fetching, building or opening the documentation index failed."""


@dataclass(frozen=True)
class Chunk:
    source: str  # "px4" | "ardupilot"
    path: str  # file path inside the repository
    title: str  # "Page title > Section > Subsection"
    url: str
    text: str


# --- fetch -------------------------------------------------------------------------


def _git(*args: str, cwd: Path | None = None) -> str:
    try:
        done = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as err:
        raise DocsError("git is needed to fetch the documentation") from err
    except subprocess.CalledProcessError as err:
        raise DocsError(f"git {' '.join(args[:2])} failed: {err.stderr.strip()[:300]}") from err
    return done.stdout.strip()


def fetch_source(name: str, src: DocSourceConfig, docs_dir: Path) -> tuple[Path, str]:
    """Shallow sparse checkout (text files only) of one source; returns (dir, commit)."""
    target = docs_dir / name
    if not (target / ".git").exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        _git(
            "clone",
            "--depth",
            "1",
            "--filter=blob:none",
            "--sparse",
            "--branch",
            src.ref,
            src.repo,
            str(target),
        )
    else:
        _git("fetch", "--depth", "1", "origin", src.ref, cwd=target)
        _git("reset", "--hard", "FETCH_HEAD", cwd=target)
    _git("sparse-checkout", "set", "--no-cone", *src.include, cwd=target)
    return target, _git("rev-parse", "HEAD", cwd=target)


# --- select + chunk -------------------------------------------------------------------

_MD_HEADING: Final = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_MD_LINK: Final = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_MD_CONTAINER: Final = re.compile(r"^:::\s*\w*.*$")
_RST_UNDERLINE: Final = re.compile(r"^([=\-~^\"'`#*+.:_])\1{2,}\s*$")
_RST_ROLE: Final = re.compile(r":\w+:`([^`<]*?)(?:\s*<[^>]*>)?`")
_RST_LINK: Final = re.compile(r"`([^`<]+?)\s*<[^>]+>`_+")
_RST_DIRECTIVE: Final = re.compile(
    r"^\s*\.\.\s+[\w-]+::.*$|^\s*\.\.\s+_[\w-]+:\s*$|^\s*:\w[\w-]*:.*$"
)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def page_url(source: str, rel_path: str, url_base: str) -> str:
    """Public URL of a documentation file."""
    if source == "px4":
        page = rel_path.removeprefix("docs/en/")
        return url_base + re.sub(r"\.md$", ".html", page)
    return url_base + re.sub(r"\.rst$", ".html", Path(rel_path).name)


def _sections_md(text: str) -> Iterator[tuple[list[str], list[str]]]:
    """(heading path, lines) per Markdown section; code fences are not parsed."""
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":  # front matter
        end = next((i for i, ln in enumerate(lines[1:], 1) if ln.strip() == "---"), 0)
        lines = lines[end + 1 :]
    path: list[str] = []
    body: list[str] = []
    fence = False
    for line in lines:
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
        m = None if fence else _MD_HEADING.match(line)
        if m:
            if body:
                yield list(path), body
            level = len(m.group(1))
            path = [*path[: level - 1], _MD_LINK.sub(r"\1", m.group(2))]
            body = []
        elif not _MD_CONTAINER.match(line.strip()):
            body.append(_MD_LINK.sub(r"\1", line))
    if body:
        yield list(path), body


def _sections_rst(text: str) -> Iterator[tuple[list[str], list[str]]]:
    """(heading path, lines) per reST section; heading levels follow underline order."""
    lines = text.splitlines()
    levels: list[str] = []
    path: list[str] = []
    body: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        overline = (
            _RST_UNDERLINE.match(line) and i + 2 < len(lines) and _RST_UNDERLINE.match(lines[i + 2])
        )
        if overline and lines[i + 1].strip():
            title, char, step = lines[i + 1].strip(), "o" + line.strip()[0], 3
        elif (
            line.strip()
            and not line.startswith(" ")
            and _RST_UNDERLINE.match(nxt)
            and (len(nxt.strip()) >= len(line.strip()))
        ):
            title, char, step = line.strip(), nxt.strip()[0], 2
        else:
            if not _RST_DIRECTIVE.match(line):
                body.append(_RST_LINK.sub(r"\1", _RST_ROLE.sub(r"\1", line)))
            i += 1
            continue
        if body:
            yield list(path), body
        if char not in levels:
            levels.append(char)
        level = levels.index(char)
        path = [*path[:level], _RST_ROLE.sub(r"\1", title)]
        body = []
        i += step
    if body:
        yield list(path), body


def _split(text: str, limit: int) -> list[str]:
    """Paragraph-wise pieces of at most ``limit`` characters (a long paragraph is cut)."""
    pieces: list[str] = []
    current = ""
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        while len(para) > limit:
            pieces.append(para[:limit])
            para = para[limit:]
        if current and len(current) + len(para) + 2 > limit:
            pieces.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        pieces.append(current)
    return pieces


def chunk_file(source: str, rel_path: str, text: str, url_base: str, limit: int) -> list[Chunk]:
    sections = _sections_md(text) if rel_path.endswith(".md") else _sections_rst(text)
    url = page_url(source, rel_path, url_base)
    chunks: list[Chunk] = []
    page_title = ""
    for path, body in sections:
        if path and not page_title:
            page_title = path[0]
        heading = path or [page_title or Path(rel_path).stem]
        anchor = f"#{_slug(heading[-1])}" if len(heading) > 1 else ""
        for piece in _split("\n".join(body), limit):
            if len(piece) < 40:  # navigation stubs, lone directives
                continue
            chunks.append(Chunk(source, rel_path, " > ".join(heading), url + anchor, piece))
    return chunks


def _title(text: str) -> str:
    for line in text.splitlines()[:30]:
        s = line.strip()
        if (
            s
            and not s.startswith(("---", "..", ":", "[", "!", "<"))
            and not _RST_UNDERLINE.match(s)
        ):
            return s.lstrip("# ")
    return ""


def select_files(root: Path, patterns: Sequence[str], keywords: Sequence[str]) -> list[Path]:
    """Text files under ``root`` whose relative path or title matches a keyword."""
    kw = re.compile("|".join(re.escape(k) for k in keywords), re.IGNORECASE)
    out = []
    for f in sorted(p for pattern in patterns for p in root.glob(pattern)):
        rel = f.relative_to(root).as_posix()
        if kw.search(rel) or kw.search(_title(f.read_text(encoding="utf-8", errors="replace"))):
            out.append(f)
    return out


_GLOBS: Final = {"px4": ("docs/en/**/*.md",), "ardupilot": ("*/source/docs/*.rst",)}


def collect_chunks(cfg: RagConfig, roots: dict[str, Path]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for name, root in roots.items():
        src: DocSourceConfig = getattr(cfg, name)
        for f in select_files(root, _GLOBS[name], cfg.keywords):
            rel = f.relative_to(root).as_posix()
            text = f.read_text(encoding="utf-8", errors="replace")
            chunks += chunk_file(name, rel, text, src.url_base, cfg.chunk_chars)
    return chunks


# --- embed + index ------------------------------------------------------------------


def litellm_embed(cfg: RagConfig) -> Embed:
    def embed(texts: list[str]) -> list[list[float]]:
        import litellm

        kwargs: dict[str, Any] = {"model": cfg.embedding_model, "input": texts}
        if cfg.api_base:
            kwargs["api_base"] = cfg.api_base
        response = litellm.embedding(**kwargs)
        return [list(map(float, item["embedding"])) for item in response.data]

    return embed


def _batches(items: Sequence[Chunk], size: int) -> Iterable[Sequence[Chunk]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def build_index(
    chunks: Sequence[Chunk],
    cfg: RagConfig,
    embed: Embed,
    *,
    location: str | Path,
    sources: dict[str, str] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> int:
    """(Re)create the collection at ``location`` (a directory, or ":memory:")."""
    from qdrant_client.models import Distance, PointStruct, VectorParams

    if not chunks:
        raise DocsError("no documentation chunks to index (check rag.keywords / sources)")
    client = _client(location)
    first = embed([chunks[0].text])[0]
    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
    client.create_collection(COLLECTION, VectorParams(size=len(first), distance=Distance.COSINE))
    done = 0
    for batch in _batches(chunks, cfg.batch_size):
        vectors = embed([c.text for c in batch])
        client.upsert(
            COLLECTION,
            [
                PointStruct(id=done + k, vector=v, payload=asdict(c))
                for k, (c, v) in enumerate(zip(batch, vectors, strict=True))
            ],
        )
        done += len(batch)
        if progress:
            progress(done, len(chunks))
    if location != ":memory:":
        manifest = {
            "embedding_model": cfg.embedding_model,
            "chunks": done,
            "dimensions": len(first),
            "sources": sources or {},
        }
        (Path(location) / MANIFEST).write_text(json.dumps(manifest, indent=2), "utf-8")
    _keep_alive[str(location)] = client
    return done


_keep_alive: dict[str, Any] = {}  # ":memory:" collections live as long as their client


def _client(location: str | Path) -> Any:  # noqa: ANN401 (qdrant_client has partial types)
    from qdrant_client import QdrantClient

    key = str(location)
    if key in _keep_alive:
        return _keep_alive[key]
    client = QdrantClient(location=":memory:") if key == ":memory:" else QdrantClient(path=key)
    _keep_alive[key] = client
    # Close before interpreter teardown; QdrantClient.__del__ fails at shutdown.
    atexit.register(client.close)
    return client


class DocSearch:
    """Query side: embed the question, return the closest chunks."""

    def __init__(
        self, cfg: RagConfig, embed: Embed | None = None, location: str | Path | None = None
    ) -> None:
        self.cfg = cfg
        self.location = location if location is not None else cfg.index_dir
        self.embed = embed or litellm_embed(cfg)
        if self.location != ":memory:":
            manifest = Path(self.location) / MANIFEST
            if not manifest.exists():
                raise DocsError(
                    f"no documentation index in {self.location}; run `skytrace docs build`"
                )
            built = json.loads(manifest.read_text("utf-8"))["embedding_model"]
            if built != cfg.embedding_model:
                raise DocsError(
                    f"index was built with {built}, config uses {cfg.embedding_model}; "
                    "rebuild with `skytrace docs build`"
                )
        self.client = _client(self.location)

    def search(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        vector = self.embed([query])[0]
        hits = self.client.query_points(COLLECTION, query=vector, limit=top_k or self.cfg.top_k)
        return [
            {
                "title": p.payload["title"],
                "url": p.payload["url"],
                "source": p.payload["source"],
                "score": round(float(p.score), 3),
                "text": p.payload["text"][: self.cfg.excerpt_chars],
            }
            for p in hits.points
        ]


def build(cfg: RagConfig, log: Callable[[str], None] = print) -> int:
    """fetch -> select -> chunk -> embed -> index, with the configured sources."""
    docs_dir = Path(cfg.docs_dir)
    roots: dict[str, Path] = {}
    commits: dict[str, str] = {}
    for name in SOURCES:
        src: DocSourceConfig = getattr(cfg, name)
        log(f"fetching {name} ({src.repo}, {src.ref}) ...")
        roots[name], commits[name] = fetch_source(name, src, docs_dir)
    chunks = collect_chunks(cfg, roots)
    log(
        f"{len(chunks)} chunks from "
        + ", ".join(f"{n} {sum(c.source == n for c in chunks)}" for n in SOURCES)
        + f"; embedding with {cfg.embedding_model} ..."
    )
    index_dir = Path(cfg.index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)
    step = max(1, len(chunks) // 10)

    def progress(done: int, total: int) -> None:
        if done % step < cfg.batch_size or done == total:
            log(f"  {done}/{total}")

    return build_index(
        chunks,
        cfg,
        litellm_embed(cfg),
        location=index_dir,
        sources={n: f"{getattr(cfg, n).repo}@{commits[n]}" for n in SOURCES},
        progress=progress,
    )
