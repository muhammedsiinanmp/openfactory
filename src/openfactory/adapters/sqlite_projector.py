"""SQLite projector for the spec, plan and task projections.

Implements "Projections" and "Projection rules" under "Domain model and storage" in
docs/spec/phase1-spec.md for the M1 tables and for `plans`, `tasks` and `task_deps`. The
projector has no port: it is internal to the recorder adapter (ADR-009), so this module
carries no conformance assertion.
"""

import json
import sqlite3
from collections.abc import Iterable
from typing import Any

from openfactory.domain.events import StoredEvent
from openfactory.domain.payloads import (
    PAYLOAD_MODELS,
    PlanApprovedPayload,
    PlanCreatedPayload,
    SpecApprovedPayload,
    SpecImportedPayload,
    TaskStateChangedPayload,
)
from openfactory.domain.spec_hash import content_hash

_TABLES = ("spec_versions", "requirements", "adrs", "plans", "tasks", "task_deps")
_CREATE_TABLES = (
    """
CREATE TABLE IF NOT EXISTS spec_versions (
  id          TEXT PRIMARY KEY,
  hash        TEXT NOT NULL,
  status      TEXT NOT NULL,
  components  TEXT NOT NULL,
  approved_at TEXT
)
""",
    """
CREATE TABLE IF NOT EXISTS requirements (
  id                  TEXT NOT NULL,
  spec_version        TEXT NOT NULL,
  title               TEXT NOT NULL,
  statement           TEXT NOT NULL,
  priority            TEXT NOT NULL,
  deprecated          INTEGER NOT NULL,
  components          TEXT NOT NULL,
  constrained_by      TEXT NOT NULL,
  acceptance_criteria TEXT NOT NULL,
  hash                TEXT NOT NULL,
  PRIMARY KEY (spec_version, id)
)
""",
    """
CREATE TABLE IF NOT EXISTS adrs (
  id           TEXT NOT NULL,
  spec_version TEXT NOT NULL,
  status       TEXT NOT NULL,
  body         TEXT NOT NULL,
  hash         TEXT NOT NULL,
  PRIMARY KEY (spec_version, id)
)
""",
    """
CREATE TABLE IF NOT EXISTS plans (
  id           TEXT PRIMARY KEY,
  spec_version TEXT NOT NULL,
  status       TEXT NOT NULL
)
""",
    """
CREATE TABLE IF NOT EXISTS tasks (
  id        TEXT PRIMARY KEY,
  plan_id   TEXT NOT NULL,
  state     TEXT NOT NULL,
  objective TEXT NOT NULL,
  contract  TEXT NOT NULL,
  attempt   INTEGER NOT NULL DEFAULT 0
)
""",
    """
CREATE TABLE IF NOT EXISTS task_deps (
  task_id    TEXT NOT NULL,
  depends_on TEXT NOT NULL,
  PRIMARY KEY (task_id, depends_on)
)
""",
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


class SqliteProjector:
    """Applies stored events to the projection tables.

    Never commits or rolls back: the caller owns the connection and the transaction.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create_tables(self) -> None:
        for statement in _CREATE_TABLES:
            self._conn.execute(statement)

    def apply(self, event: StoredEvent) -> None:
        """Validate the payload against its model, then project it.

        A type with no payload model has no projection yet and is ignored.
        """
        model = PAYLOAD_MODELS.get(event.type)
        if model is None:
            return
        payload = model.model_validate(event.payload)
        if isinstance(payload, SpecImportedPayload):
            self._apply_imported(payload)
        elif isinstance(payload, SpecApprovedPayload):
            self._conn.execute(
                "UPDATE spec_versions SET status = 'approved', approved_at = ? WHERE id = ?",
                (event.created_at.isoformat(), payload.spec_version),
            )
        elif isinstance(payload, PlanCreatedPayload):
            self._apply_plan_created(payload)
        elif isinstance(payload, PlanApprovedPayload):
            self._conn.execute(
                "UPDATE plans SET status = 'approved' WHERE id = ?", (payload.plan_id,)
            )
        elif isinstance(payload, TaskStateChangedPayload):
            self._conn.execute(
                "UPDATE tasks SET state = ? WHERE id = ?", (payload.to.value, payload.task_id)
            )

    def rebuild(self, events: Iterable[StoredEvent]) -> None:
        for table in _TABLES:
            self._conn.execute(f"DROP TABLE IF EXISTS {table}")
        self.create_tables()
        for event in sorted(events, key=lambda e: e.seq):
            self.apply(event)

    def _apply_imported(self, payload: SpecImportedPayload) -> None:
        version, spec = payload.spec_version, payload.spec
        # An existing draft keeps its id and its content is replaced.
        self._conn.execute(
            "INSERT OR REPLACE INTO spec_versions (id, hash, status, components, approved_at)"
            " VALUES (?, ?, 'draft', ?, NULL)",
            (version, payload.hash, _json(spec.components)),
        )
        self._conn.execute("DELETE FROM requirements WHERE spec_version = ?", (version,))
        self._conn.execute("DELETE FROM adrs WHERE spec_version = ?", (version,))
        # Spec, "Projection rules": of two requirements, or two ADRs, with one id the first in
        # the payload's order is kept and the others are skipped.
        self._conn.executemany(
            "INSERT OR IGNORE INTO requirements (id, spec_version, title, statement, priority,"
            " deprecated, components, constrained_by, acceptance_criteria, hash)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    req.id,
                    version,
                    req.title,
                    req.statement,
                    req.priority.value,
                    int(req.deprecated),
                    _json(req.components),
                    _json(req.constrained_by),
                    _json([c.model_dump(mode="json") for c in req.acceptance_criteria]),
                    content_hash(req),
                )
                for req in spec.requirements
            ],
        )
        self._conn.executemany(
            "INSERT OR IGNORE INTO adrs (id, spec_version, status, body, hash)"
            " VALUES (?, ?, ?, ?, ?)",
            [(adr.id, version, adr.status.value, adr.body, content_hash(adr)) for adr in spec.adrs],
        )

    def _apply_plan_created(self, payload: PlanCreatedPayload) -> None:
        # Spec, "Planning": the earlier draft is marked superseded and its tasks are removed.
        drafts = "SELECT id FROM plans WHERE status = 'draft'"
        self._conn.execute(
            f"DELETE FROM task_deps WHERE task_id IN"
            f" (SELECT id FROM tasks WHERE plan_id IN ({drafts}))"
        )
        self._conn.execute(f"DELETE FROM tasks WHERE plan_id IN ({drafts})")
        self._conn.execute("UPDATE plans SET status = 'superseded' WHERE status = 'draft'")
        self._conn.execute(
            "INSERT INTO plans (id, spec_version, status) VALUES (?, ?, 'draft')",
            (payload.plan_id, payload.spec_version),
        )
        self._conn.executemany(
            "INSERT INTO tasks (id, plan_id, state, objective, contract, attempt)"
            " VALUES (?, ?, 'pending', ?, ?, 0)",
            [
                (task.task_id, payload.plan_id, task.objective, _json(task.model_dump(mode="json")))
                for task in payload.tasks
            ],
        )
        self._conn.executemany(
            "INSERT INTO task_deps (task_id, depends_on) VALUES (?, ?)",
            [(task.task_id, dep) for task in payload.tasks for dep in task.depends_on],
        )
