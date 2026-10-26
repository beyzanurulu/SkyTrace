"""Scoring of the agent's example questions (eval/agent_questions.yaml).

A reply passes when all of these hold:

- ``expect.tools``: every item was called (or its output was prefetched into the
  context); an item may be a list of alternatives ("get_flight_summary or get_events").
- ``expect.verified``: the verification node found nothing unbacked (true), or
  flagged exactly ``unverified`` / ``unknown_ids`` (false).
- ``expect.key_numbers``: each number appears in the answer, at whatever
  precision the answer uses (19.9343 is found as 19.9 or 19.93).
- ``expect.key_ids``: each finding id appears in the answer.
- ``expect.key_terms_any``: at least one of these appears (case-insensitive) in
  the answer as shown, i.e. including doc sources the agent appended.
- ``expect.no_tools`` / ``expect.no_numbers``: for questions outside the log, no
  tool call and no number at all.

Without the key facts an empty "no data found" answer would pass, since it
contains no number that could fail verification.
"""

from __future__ import annotations

from typing import Any

from skytrace.agent.graph import AgentReply
from skytrace.agent.verify import answer_numbers


def _contains_number(answer: str, expected: float) -> bool:
    for token in answer_numbers(answer):
        if token.decimals >= 1 and abs(round(abs(expected), token.decimals) - abs(token.value)) < (
            10 ** -(token.decimals + 6)
        ):
            return True
    return False


def check_reply(case: dict[str, Any], reply: AgentReply) -> list[str]:
    """Problems with ``reply`` for question ``case``; empty = pass."""
    expect = case["expect"]
    problems: list[str] = []
    # Prefetched outputs are real tool outputs already in the context: using them
    # counts as having called the tool.
    called = set(reply.tool_calls) | set(reply.prefetched)
    for item in expect.get("tools", []):
        options = [item] if isinstance(item, str) else list(item)
        if not called & set(options):
            problems.append(f"tool not called: {' or '.join(options)}")

    v = reply.verification
    if expect.get("verified", True):
        if not v.ok:
            problems.append(f"unbacked: {', '.join(v.unverified + v.unknown_ids + v.unknown_urls)}")
    else:
        if v.unverified != expect.get("unverified", []):
            problems.append(f"flagged numbers {v.unverified} != {expect.get('unverified')}")
        if v.unknown_ids != expect.get("unknown_ids", []):
            problems.append(f"flagged ids {v.unknown_ids} != {expect.get('unknown_ids')}")

    answer = reply.raw_answer
    for number in expect.get("key_numbers", []):
        if not _contains_number(answer, float(number)):
            problems.append(f"missing key number {number}")
    for fid in expect.get("key_ids", []):
        if fid not in answer:
            problems.append(f"missing finding id {fid}")
    # Terms are checked in what the user sees, incl. the appended doc sources.
    terms = expect.get("key_terms_any", [])
    if terms and not any(t.lower() in reply.answer.lower() for t in terms):
        problems.append(f"none of the key terms {terms}")
    if expect.get("no_tools") and reply.tool_calls:
        problems.append(f"no tool expected, called {reply.tool_calls}")
    if expect.get("no_numbers") and answer_numbers(answer):
        problems.append("no number expected in the answer")
    return problems
