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
from openfactory.domain.traces import (
    FileTrace,
    RequirementTrace,
    TracedCommit,
    TracedTask,
    TracedTest,
)
from openfactory.ports.traces import Traces

_BUSY_TIMEOUT_MS = 5000

# Each commit with its task: run -> commit `trailer` links joined to task -> run ones.
_COMMIT_TASKS = (
    "SELECT c.to_id AS sha, r.from_id AS task_id FROM trace_links r JOIN trace_links c"
    " ON c.from_kind = 'run' AND c.from_id = r.to_id AND c.to_kind = 'commit'"
    " AND c.source = 'trailer' WHERE r.from_kind = 'task' AND r.to_kind = 'run'"
    " AND r.source = 'trailer'"
)
# The commit -> file `diff` links.
_DIFF = "from_kind = 'commit' AND to_kind = 'file' AND source = 'diff'"
# The tasks a requirement -> task `contract` link reaches from the requirement bound to `?`.
_REQUIREMENT_TASKS = (
    "SELECT to_id FROM trace_links WHERE from_kind = 'requirement' AND from_id = ?"
    " AND to_kind = 'task' AND source = 'contract'"
)
# The shas of those tasks' commits.
_COMMITS = f"SELECT sha FROM ({_COMMIT_TASKS}) WHERE task_id IN ({_REQUIREMENT_TASKS})"
# The commits, with their tasks, that changed the file bound to `?`.
_FILE_COMMITS = (
    f"SELECT DISTINCT sha, task_id FROM ({_COMMIT_TASKS})"
    f" WHERE sha IN (SELECT from_id FROM trace_links WHERE {_DIFF} AND to_id = ?)"
)
# The requirements a `contract` link links to those commits' tasks.
_FILE_REQUIREMENTS = (
    "SELECT from_id FROM trace_links WHERE from_kind = 'requirement' AND to_kind = 'task'"
    f" AND source = 'contract' AND to_id IN (SELECT task_id FROM ({_FILE_COMMITS}))"
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
            f"SELECT DISTINCT sha, task_id FROM ({_COMMIT_TASKS})"
            f" WHERE task_id IN ({_REQUIREMENT_TASKS}) ORDER BY task_id, sha",
            (requirement_id,),
        ).fetchall()
        files = self._conn.execute(
            f"SELECT DISTINCT to_id FROM trace_links WHERE {_DIFF}"
            f" AND from_id IN ({_COMMITS})"
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
            f" SELECT to_id FROM trace_links WHERE {_DIFF} AND from_id IN ({_COMMITS}))"
            ") GROUP BY from_id ORDER BY from_id",
            (requirement_id, requirement_id),
        ).fetchall()
        return RequirementTrace(
            tasks=[TracedTask(task_id=row[0], state=TaskState(row[1])) for row in tasks],
            commits=[TracedCommit(sha=row[0], task_id=row[1]) for row in commits],
            files=[row[0] for row in files],
            tests=[TracedTest(node_id=row[0], tagged=bool(row[1])) for row in tests],
        )

    def file_trace(self, path: str) -> FileTrace | None:
        commits = self._conn.execute(f"{_FILE_COMMITS} ORDER BY task_id, sha", (path,)).fetchall()
        if not commits:
            return None
        tasks = self._conn.execute(
            f"SELECT id, state FROM tasks WHERE id IN (SELECT task_id FROM ({_FILE_COMMITS}))"
            " ORDER BY id",
            (path,),
        ).fetchall()
        requirements = self._conn.execute(
            f"SELECT DISTINCT from_id FROM ({_FILE_REQUIREMENTS}) ORDER BY from_id", (path,)
        ).fetchall()
        adrs = self._conn.execute(
            "SELECT DISTINCT to_id FROM trace_links WHERE from_kind = 'requirement'"
            " AND to_kind = 'adr' AND source = 'spec'"
            f" AND from_id IN ({_FILE_REQUIREMENTS}) ORDER BY to_id",
            (path,),
        ).fetchall()
        return FileTrace(
            commits=[TracedCommit(sha=row[0], task_id=row[1]) for row in commits],
            tasks=[TracedTask(task_id=row[0], state=TaskState(row[1])) for row in tasks],
            requirements=[row[0] for row in requirements],
            adrs=[row[0] for row in adrs],
        )

    def close(self) -> None:
        self._conn.close()


if TYPE_CHECKING:
    _: type[Traces] = SqliteTraces
