#!/usr/bin/env python3
"""Appends one metadata-only line per hook event to .workflow/events.jsonl.

Never logs prompt text, file contents or command strings. Always exits 0.
Hooks run under whatever `python3` is on PATH, so this file stays 3.9-compatible.
"""

from __future__ import annotations

import contextlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / ".workflow" / "events.jsonl"
SUBAGENT_TOOLS = {"Task", "Agent"}


def utc_now() -> str:
    now = datetime.now(timezone.utc)  # noqa: UP017
    return now.isoformat(timespec="milliseconds")


def current_branch() -> str | None:
    # Read HEAD directly: this runs on every tool call, so no git subprocess.
    head = (ROOT / ".git" / "HEAD").read_text().strip()
    prefix = "ref: refs/heads/"
    return head[len(prefix) :] if head.startswith(prefix) else None


def current_task_id() -> str | None:
    branch = current_branch()
    if branch and (m := re.match(r"task/(TASK-\d+)-", branch)):
        return m.group(1)
    if branch != "main":
        return None
    planned = []
    for record in (ROOT / "docs" / "tasks").glob("TASK-*.md"):
        m = re.match(r"TASK-(\d+)", record.name)
        if m and "Status: planned" in record.read_text():
            planned.append((int(m.group(1)), m.group(0)))
    return max(planned)[1] if planned else None


def append_event(record: dict) -> None:
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps(record) + "\n")


def main() -> None:
    data = json.load(sys.stdin)
    tool_name = data.get("tool_name")
    subagent_type = None
    if tool_name in SUBAGENT_TOOLS:
        subagent_type = (data.get("tool_input") or {}).get("subagent_type")
    append_event(
        {
            "ts": utc_now(),
            "event": data.get("hook_event_name"),
            "session_id": data.get("session_id"),
            "transcript_path": data.get("transcript_path"),
            "task_id": current_task_id(),
            "tool_name": tool_name,
            "subagent_type": subagent_type if isinstance(subagent_type, str) else None,
        }
    )


if __name__ == "__main__":
    with contextlib.suppress(BaseException):
        main()
    sys.exit(0)
