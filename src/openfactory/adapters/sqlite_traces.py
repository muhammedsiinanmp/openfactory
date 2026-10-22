"""SQLite implementation of the Traces port.

Reads the `requirements`, `spec_versions`, `tasks` and `trace_links` projections
described under "Projections" in docs/spec/phase1-spec.md; `spec_versions` only to tell
approved requirements from draft ones. It only runs SELECT statements and creates no
table; the event recorder creates and writes the projections. Its own connection follows ADR-010.
"""

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from openfactory.domain.states import TaskState
from openfactory.domain.traces import RequirementTrace, TracedCommit, TracedTask, TracedTest
from openfactory.ports.traces import Traces

_BUSY_TIMEOUT_MS = 5000

# The task -> run `trailer` links of the tasks a requirement -> task `contract` link
# reaches from the requirement bound to `?`.
_TASK_RUNS = (
    "(SELECT from_id, to_id FROM trace_links WHERE from_kind = 'task' AND to_kind = 'run'"
    " AND source = 'trailer' AND from_id IN (SELECT to_id FROM trace_links"
    " WHERE from_kind = 'requirement' AND from_id = ? AND to_kind = 'task'"
    " AND source = 'contract'))"
)
# The shas those runs' run -> commit `trailer` links reach.
_COMMITS = (
    f"SELECT c.to_id FROM {_TASK_RUNS} r JOIN trace_links c ON c.from_kind = 'run'"
    " AND c.from_id = r.to_id AND c.to_kind = 'commit' AND c.source = 'trailer'"
)


class SqliteTraces:
    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(path)
        self._conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")

    def untested_requirements(self, spec_version: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT id FROM requirements WHERE spec_version = ? AND deprecated = 0"
            " AND id NOT IN (SELECT to_id FROM trace_links WHERE from_kind = 'test'"
            " AND to_kind = 'requirement' AND source = 'test_tag') ORDER BY id",
            (spec_version,),
        ).fetchall()
        return [row[0] for row in rows]

    def requirement_trace(self, requirement_id: str) -> RequirementTrace | None:
        known = self._conn.execute(
            "SELECT 1 FROM requirements r JOIN spec_versions v ON v.id = r.spec_version"
            " WHERE r.id = ? AND v.status = 'approved' LIMIT 1",
            (requirement_id,),
        ).fetchone()
        if known is None:
            return None
        tasks = self._conn.execute(
            "SELECT t.id, t.state FROM trace_links l JOIN tasks t ON t.id = l.to_id"
            " WHERE l.from_kind = 'requirement' AND l.from_id = ? AND l.to_kind = 'task'"
            " AND l.source = 'contract' ORDER BY t.id",
            (requirement_id,),
        ).fetchall()
        commits = self._conn.execute(
            f"SELECT DISTINCT c.to_id, r.from_id FROM {_TASK_RUNS} r"
            " JOIN trace_links c ON c.from_kind = 'run' AND c.from_id = r.to_id"
            " AND c.to_kind = 'commit' AND c.source = 'trailer'"
            " ORDER BY r.from_id, c.to_id",
            (requirement_id,),
        ).fetchall()
        files = self._conn.execute(
            f"SELECT DISTINCT to_id FROM trace_links WHERE from_kind = 'commit'"
            f" AND to_kind = 'file' AND source = 'diff' AND from_id IN ({_COMMITS})"
            " ORDER BY to_id",
            (requirement_id,),
        ).fetchall()
        tests = self._conn.execute(
            "SELECT from_id, MAX(tagged) FROM ("
            " SELECT from_id, 1 AS tagged FROM trace_links WHERE from_kind = 'test'"
            " AND to_kind = 'requirement' AND to_id = ? AND source = 'test_tag'"
            " UNION ALL"
            " SELECT from_id, 0 FROM trace_links WHERE from_kind = 'test'"
            " AND to_kind = 'file' AND source = 'test_tag' AND to_id IN ("
            " SELECT to_id FROM trace_links WHERE from_kind = 'commit' AND to_kind = 'file'"
            f" AND source = 'diff' AND from_id IN ({_COMMITS}))"
            ") GROUP BY from_id ORDER BY from_id",
            (requirement_id, requirement_id),
        ).fetchall()
        return RequirementTrace(
            tasks=[TracedTask(task_id=row[0], state=TaskState(row[1])) for row in tasks],
            commits=[TracedCommit(sha=row[0], task_id=row[1]) for row in commits],
            files=[row[0] for row in files],
            tests=[TracedTest(node_id=row[0], tagged=bool(row[1])) for row in tests],
        )

    def close(self) -> None:
        self._conn.close()


if TYPE_CHECKING:
    _: type[Traces] = SqliteTraces
