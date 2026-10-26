"""Check that every number and finding id in an answer is backed by a tool output.

The rule of the agent is that the model never produces a number itself. This
check enforces it after the fact: numbers are pulled out of the answer and
looked up in the tool outputs of the same turn. A number counts as backed if a
tool number rounded to the answer's decimals equals it, if it is within
``rel_tol`` of one, or (when followed by ``%``) if it matches a tool fraction
times 100. Signs are ignored ("a drop of 0.3 m/s" for vz = -0.3). Numbers from
the user's own question, markdown list numbering and finding ids are handled
separately; every other number that does not match is reported.

Cited urls are checked the same way: a url (without its ``#anchor``) must occur
in a tool output (search_docs results), so a made-up documentation link is
reported like a made-up number.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Final

_FINDING_ID: Final = re.compile(r"\bF\d{3}\b")
_LIST_PREFIX: Final = re.compile(r"^[ \t]*\d+[.)][ \t]+", re.MULTILINE)
# 12, -3.5, 23,4 (decimal comma), 1e-3, also glued to a unit (23.3V, 5m);
# not when glued to a preceding word (m1, x2, F001)
_NUMBER: Final = re.compile(r"(?<![\w.,])[-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?(?![\d.,]*\d)")
# Inside tool-output strings only stand-alone numbers count ("EPH 3.26 m"), never
# digits glued to letters (firmware hashes like "8583f1da30b6" would back
# arbitrary integers).
_TOOL_NUMBER: Final = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?(?![\w.])")
_URL: Final = re.compile(r"https?://[^\s()<>\[\]\"'`]+")


def _urls(text: str) -> list[str]:
    return [m.group(0).rstrip(".,;:!?") for m in _URL.finditer(text)]


def _page(url: str) -> str:
    return url.split("#", 1)[0].rstrip("/")


def _walk(value: object, out: list[float]) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int | float):
        out.append(float(value))
    elif isinstance(value, str):
        out.extend(float(t) for t in _TOOL_NUMBER.findall(value))
    elif isinstance(value, dict):
        for v in value.values():
            _walk(v, out)
    elif isinstance(value, list | tuple):
        for v in value:
            _walk(v, out)


def tool_numbers(outputs: Iterable[str]) -> list[float]:
    """Numeric values of the tool outputs (JSON values; stand-alone numbers in text)."""
    pool: list[float] = []
    for text in outputs:
        try:
            _walk(json.loads(text), pool)
        except (json.JSONDecodeError, TypeError):
            pool.extend(float(t) for t in _TOOL_NUMBER.findall(text))
    return pool


@dataclass(frozen=True)
class Verification:
    checked: int
    unverified: list[str] = field(default_factory=list)
    unknown_ids: list[str] = field(default_factory=list)
    unknown_urls: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.unverified and not self.unknown_ids and not self.unknown_urls


@dataclass(frozen=True)
class _Token:
    text: str
    value: float
    decimals: int
    percent: bool


def _blank(match: re.Match[str]) -> str:
    return " " * len(match.group(0))  # keep positions: later lookups use offsets


def answer_numbers(text: str) -> list[_Token]:
    """Number tokens of a text, without finding ids, urls and list numbering."""
    cleaned = _LIST_PREFIX.sub(_blank, _FINDING_ID.sub(_blank, _URL.sub(_blank, text)))
    tokens = []
    for m in _NUMBER.finditer(cleaned):
        raw = m.group(0).replace(",", ".")
        mantissa = raw.lower().split("e")[0]
        decimals = len(mantissa.split(".", 1)[1]) if "." in mantissa else 0
        after = cleaned[m.end() : m.end() + 2].lstrip()
        before = cleaned[max(0, m.start() - 2) : m.start()].rstrip()
        percent = after.startswith("%") or before.endswith("%")  # "74%" and Turkish "%74"
        tokens.append(_Token(m.group(0), float(raw), decimals, percent))
    return tokens


def _same(a: float, b: float, decimals: int, rel_tol: float) -> bool:
    if abs(round(b, decimals) - a) < 10 ** -(decimals + 6):
        return True
    return b > 0 and abs(b - a) <= rel_tol * b


def _backed(token: _Token, pool: list[float], rel_tol: float) -> bool:
    a = abs(token.value)
    for v in pool:
        b = abs(v)
        if _same(a, b, token.decimals, rel_tol):
            return True
        if token.percent and _same(a, b * 100, token.decimals, rel_tol):
            return True
    return False


def verify_answer(
    answer: str, tool_outputs: Iterable[str], question: str = "", rel_tol: float = 0.005
) -> Verification:
    outputs = list(tool_outputs)
    tool_text = "\n".join(outputs)
    pool = tool_numbers(outputs)
    known_ids = set(_FINDING_ID.findall(tool_text))
    from_user = {round(t.value, 9) for t in answer_numbers(question)}

    unknown_ids = sorted({i for i in _FINDING_ID.findall(answer) if i not in known_ids})
    tokens = answer_numbers(answer)
    unverified = [
        t.text
        for t in tokens
        if round(t.value, 9) not in from_user and not _backed(t, pool, rel_tol)
    ]
    known_pages = {_page(u) for u in _urls(tool_text)}
    unknown_urls = list(dict.fromkeys(u for u in _urls(answer) if _page(u) not in known_pages))
    return Verification(
        checked=len(tokens),
        unverified=unverified,
        unknown_ids=unknown_ids,
        unknown_urls=unknown_urls,
    )


def annotate(answer: str, v: Verification) -> str:
    """Append a visible warning for anything not backed by a tool output."""
    if v.ok:
        return answer
    parts = []
    if v.unverified:
        parts.append("numbers " + ", ".join(dict.fromkeys(v.unverified)))
    if v.unknown_ids:
        parts.append("finding ids " + ", ".join(v.unknown_ids))
    if v.unknown_urls:
        parts.append("urls " + ", ".join(v.unknown_urls))
    return f"{answer}\n\n⚠ Not backed by any tool output (do not trust): {'; '.join(parts)}."
