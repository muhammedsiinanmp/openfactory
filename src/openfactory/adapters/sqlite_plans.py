"""SQLite implementation of the Plans port.

Reads the `plans`, `tasks`, `task_deps` and `commits` projections described under "Projections"
in docs/spec/phase1-spec.md. It only runs SELECT statements and creates no table; the
event recorder creates and writes the projections. Its own connection follows ADR-010.
"""

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from openfactory.domain.contracts import TaskContract
from openfactory.domain.plans import CommitRef, PlanRef, Task
from openfactory.ports.plans import Plans

_BUSY_TIMEOUT_MS = 5000
# Ids are compared by their number, so `plan_100` comes after `plan_99`.
_NUMBER = "CAST(substr(id, 6) AS INTEGER)"


class SqlitePlans:
    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(path)
        self._conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")

    def current_draft(self) -> PlanRef | None:
        return self._latest("draft")

    def approved(self) -> PlanRef | None:
        return self._latest("approved")

    def next_id(self) -> str:
        rows = self._conn.execute(f"SELECT MAX({_NUMBER}) FROM plans").fetchall()
        highest: int = rows[0][0] or 0
        return f"plan_{highest + 1:02d}"

    def tasks(self, plan_id: str) -> list[Task]:
        rows = self._conn.execute(
            "SELECT id, state, attempt, contract FROM tasks WHERE plan_id = ? ORDER BY id",
            (plan_id,),
        ).fetchall()
        deps = self._conn.execute(
            "SELECT task_id, depends_on FROM task_deps"
            " WHERE task_id IN (SELECT id FROM tasks WHERE plan_id = ?) ORDER BY depends_on",
            (plan_id,),
        ).fetchall()
        depends_on: dict[str, list[str]] = {}
        for task_id, dependency in deps:
            depends_on.setdefault(task_id, []).append(dependency)
        return [
            Task(
                id=row[0],
                plan_id=plan_id,
                state=row[1],
                attempt=row[2],
                contract=TaskContract.model_validate_json(row[3]),
                depends_on=depends_on.get(row[0], []),
            )
            for row in rows
        ]

    def live_tasks_referencing(self, requirement_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT id, contract FROM tasks"
            " WHERE state NOT IN ('abandoned', 'invalidated') ORDER BY id"
        ).fetchall()
        return [
            row[0]
            for row in rows
            if requirement_id in TaskContract.model_validate_json(row[1]).requirements
        ]

    def latest_commit(self, plan_id: str) -> CommitRef | None:
        rows = self._conn.execute(
            "SELECT commits.sha, commits.task_id FROM commits"
            " JOIN tasks ON tasks.id = commits.task_id WHERE tasks.plan_id = ?"
            " ORDER BY CAST(substr(commits.run_id, 5) AS INTEGER) DESC LIMIT 1",
            (plan_id,),
        ).fetchall()
        if not rows:
            return None
        return CommitRef(sha=rows[0][0], task_id=rows[0][1])

    def close(self) -> None:
        self._conn.close()

    def _latest(self, status: str) -> PlanRef | None:
        # fetchall finishes the statement, so no read transaction stays open between calls.
        rows = self._conn.execute(
            f"SELECT id, spec_version FROM plans WHERE status = ? ORDER BY {_NUMBER} DESC LIMIT 1",
            (status,),
        ).fetchall()
        if not rows:
            return None
        return PlanRef(id=rows[0][0], spec_version=rows[0][1])


if TYPE_CHECKING:
    _: type[Plans] = SqlitePlans
