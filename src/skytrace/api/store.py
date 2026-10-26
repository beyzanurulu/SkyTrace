"""Uploaded logs on disk: one folder per analysis, deleted after the retention time.

    <storage_dir>/<id>/meta.json   filename, upload time, options
    <storage_dir>/<id>/<log file>  the upload itself
    <storage_dir>/<id>/plots/      plots written by the agent's make_plot

Ids are random (uuid4 hex) and validated before they touch the file system.
"""

from __future__ import annotations

import gc
import json
import re
import shutil
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

_ID: Final = re.compile(r"[0-9a-f]{32}")
_UNSAFE: Final = re.compile(r"[^\w.-]+")
META: Final = "meta.json"


class UnknownAnalysisError(KeyError):
    """No analysis with this id (never existed, expired or deleted)."""


def safe_filename(name: str, limit: int = 100) -> str:
    """Base name of an uploaded file with anything but letters, digits, ``._-`` replaced."""
    base = _UNSAFE.sub("_", Path(name.replace("\\", "/")).name).strip("._") or "log"
    stem, dot, suffix = base.rpartition(".")
    if not dot:
        return base[:limit]
    return f"{stem[: limit - len(suffix) - 1]}.{suffix}"


class Store:
    def __init__(
        self, root: str | Path, retention_s: float, clock: Callable[[], float] = time.time
    ) -> None:
        self.root = Path(root)
        self.retention_s = retention_s
        self.clock = clock

    def create(self, filename: str, **options: Any) -> tuple[str, Path]:  # noqa: ANN401
        """A new, empty analysis folder; returns (id, path of the log file to write)."""
        analysis_id = uuid.uuid4().hex
        folder = self.root / analysis_id
        folder.mkdir(parents=True)
        name = safe_filename(filename)
        meta = {"id": analysis_id, "filename": name, "created_at": self.clock(), **options}
        (folder / META).write_text(json.dumps(meta), "utf-8")
        return analysis_id, folder / name

    def folder(self, analysis_id: str) -> Path:
        if not _ID.fullmatch(analysis_id):
            raise UnknownAnalysisError(analysis_id)
        folder = self.root / analysis_id
        if not (folder / META).is_file():
            raise UnknownAnalysisError(analysis_id)
        return folder

    def meta(self, analysis_id: str) -> dict[str, Any]:
        meta: dict[str, Any] = json.loads((self.folder(analysis_id) / META).read_text("utf-8"))
        if self.clock() - float(meta["created_at"]) > self.retention_s:
            raise UnknownAnalysisError(analysis_id)  # expired, not cleaned up yet
        meta["expires_at"] = float(meta["created_at"]) + self.retention_s
        return meta

    def update(self, analysis_id: str, **fields: Any) -> None:  # noqa: ANN401
        path = self.folder(analysis_id) / META
        meta = json.loads(path.read_text("utf-8"))
        meta.update(fields)
        path.write_text(json.dumps(meta), "utf-8")

    def log_path(self, analysis_id: str) -> Path:
        return self.folder(analysis_id) / str(self.meta(analysis_id)["filename"])

    def delete(self, analysis_id: str) -> None:
        shutil.rmtree(self.folder(analysis_id), ignore_errors=True)

    def discard(self, folder: Path) -> None:
        """Remove a folder of this store whatever state it is in (failed upload)."""
        if folder.parent == self.root:
            # A parser that failed half-way may still hold the file open (Windows
            # cannot delete it then) until its reader object is collected.
            gc.collect()
            shutil.rmtree(folder, ignore_errors=True)

    def cleanup(self) -> list[str]:
        """Delete expired analyses (and folders without readable metadata); their ids."""
        if not self.root.is_dir():
            return []
        removed = []
        now = self.clock()
        for folder in self.root.iterdir():
            if not folder.is_dir():
                continue
            try:
                created = float(json.loads((folder / META).read_text("utf-8"))["created_at"])
            except (OSError, ValueError, KeyError, TypeError):
                # A folder whose upload never finished: judge it by its own age.
                created = folder.stat().st_mtime
            if now - created > self.retention_s:
                shutil.rmtree(folder, ignore_errors=True)
                removed.append(folder.name)
        return removed
