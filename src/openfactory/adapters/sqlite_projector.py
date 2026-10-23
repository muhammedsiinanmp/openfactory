"""SQLite projector for the spec, plan, task, agent run, gate result, commit and trace projections.

Implements "Projections" and "Projection rules" under "Domain model and storage" in
docs/spec/phase1-spec.md for the M1 tables, for `plans`, `tasks`, `task_deps` and
`agent_runs`, and for `gate_results` and `commits`, including the task's cost and the
`retry` reset, and for `trace_links` (ADR-018). The projector has no port: it is
internal to the recorder adapter (ADR-009), so this module carries no conformance assertion.
"""

import json
import sqlite3
from collections.abc import Iterable
from typing import Any

from openfactory.domain.events import StoredEvent
from openfactory.domain.payloads import (
    PAYLOAD_MODELS,
    AgentRunFinishedPayload,
    AgentRunStartedPayload,
    CommitRecordedPayload,
    GateEvaluatedPayload,
    PlanApprovedPayload,
    PlanCreatedPayload,
    SpecApprovedPayload,
    SpecImportedPayload,
    TaskResolvedPayload,
    TaskStateChangedPayload,
    TestsCollectedPayload,
)
from openfactory.domain.spec_hash import content_hash
from openfactory.domain.states import TaskState

_TABLES = (
    "spec_versions",
    "requirements",
    "adrs",
    "plans",
    "tasks",
    "task_deps",
    "agent_runs",
    "gate_results",
    "commits",
    "trace_links",
)
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
  attempt   INTEGER NOT NULL DEFAULT 0,
  cost_usd  REAL NOT NULL DEFAULT 0
)
""",
    """
CREATE TABLE IF NOT EXISTS task_deps (
  task_id    TEXT NOT NULL,
  depends_on TEXT NOT NULL,
  PRIMARY KEY (task_id, depends_on)
)
""",
    """
CREATE TABLE IF NOT EXISTS agent_runs (
  id           TEXT PRIMARY KEY,
  task_id      TEXT,
  role         TEXT NOT NULL,
  runtime      TEXT NOT NULL,
  model        TEXT,
  started_at   TEXT NOT NULL,
  ended_at     TEXT,
  exit         TEXT,
  tokens_in    INTEGER,
  tokens_out   INTEGER,
  cost_usd     REAL,
  duration_s   REAL,
  context_hash TEXT NOT NULL
)
""",
    """
CREATE TABLE IF NOT EXISTS gate_results (
  run_id      TEXT NOT NULL,
  gate        TEXT NOT NULL,
  passed      INTEGER NOT NULL,
  output_path TEXT,
  PRIMARY KEY (run_id, gate)
)
""",
    """
CREATE TABLE IF NOT EXISTS commits (
  sha     TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  run_id  TEXT NOT NULL,
  branch  TEXT NOT NULL
)
""",
    """
CREATE TABLE IF NOT EXISTS trace_links (
  from_kind TEXT NOT NULL,
  from_id   TEXT NOT NULL,
  to_kind   TEXT NOT NULL,
  to_id     TEXT NOT NULL,
  source    TEXT NOT NULL,
  PRIMARY KEY (from_kind, from_id, to_kind, to_id, source)
)
""",
)
# Spec, "Projection rules": each link is stored once; a link already stored is not inserted again.
_INSERT_LINK = (
    "INSERT OR IGNORE INTO trace_links (from_kind, from_id, to_kind, to_id, source)"
    " VALUES (?, ?, ?, ?, ?)"
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
        """Validate the payload against its model, then project it."""
        payload = PAYLOAD_MODELS[event.type].model_validate(event.payload)
        if isinstance(payload, SpecImportedPayload):
            self._apply_imported(payload)
        elif isinstance(payload, SpecApprovedPayload):
            self._conn.execute(
                "UPDATE spec_versions SET status = 'approved', approved_at = ? WHERE id = ?",
                (event.created_at.isoformat(), payload.spec_version),
            )
            self._link_spec(payload.spec_version)
        elif isinstance(payload, PlanCreatedPayload):
            self._apply_plan_created(payload)
        elif isinstance(payload, PlanApprovedPayload):
            self._conn.execute(
                "UPDATE plans SET status = 'approved' WHERE id = ?", (payload.plan_id,)
            )
            self._link_plan(payload.plan_id)
        elif isinstance(payload, TaskStateChangedPayload):
            # Spec, "Projection rules": each change to `running` counts as an attempt.
            self._conn.execute(
                "UPDATE tasks SET state = ?, attempt = attempt + ? WHERE id = ?",
                (payload.to.value, int(payload.to is TaskState.running), payload.task_id),
            )
        elif isinstance(payload, AgentRunStartedPayload):
            self._conn.execute(
                "INSERT INTO agent_runs (id, task_id, role, runtime, started_at, context_hash)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    payload.run_id,
                    payload.task_id,
                    payload.role,
                    payload.runtime,
                    event.created_at.isoformat(),
                    payload.context_hash,
                ),
            )
        elif isinstance(payload, AgentRunFinishedPayload):
            self._conn.execute(
                "UPDATE agent_runs SET model = ?, ended_at = ?, exit = ?, tokens_in = ?,"
                " tokens_out = ?, cost_usd = ?, duration_s = ? WHERE id = ?",
                (
                    payload.model,
                    event.created_at.isoformat(),
                    payload.exit,
                    payload.tokens_in,
                    payload.tokens_out,
                    payload.cost_usd,
                    payload.duration_s,
                    payload.run_id,
                ),
            )
            # Spec, "Projection rules": a null cost counts as 0; a run with no task adds nothing.
            self._conn.execute(
                "UPDATE tasks SET cost_usd = cost_usd + ?"
                " WHERE id = (SELECT task_id FROM agent_runs WHERE id = ?)",
                (payload.cost_usd or 0, payload.run_id),
            )
        elif isinstance(payload, TaskResolvedPayload):
            # Spec, "Projection rules": `retry` gives a fresh budget; `abandon` changes no row.
            if payload.decision == "retry":
                self._conn.execute(
                    "UPDATE tasks SET attempt = 0, cost_usd = 0 WHERE id = ?", (payload.task_id,)
                )
        elif isinstance(payload, GateEvaluatedPayload):
            self._conn.execute(
                "INSERT INTO gate_results (run_id, gate, passed, output_path) VALUES (?, ?, ?, ?)",
                (payload.run_id, payload.gate, int(payload.passed), payload.output_path),
            )
        elif isinstance(payload, CommitRecordedPayload):
            self._conn.execute(
                "INSERT INTO commits (sha, task_id, run_id, branch) VALUES (?, ?, ?, ?)",
                (payload.sha, payload.task_id, payload.run_id, payload.branch),
            )
            self._conn.executemany(
                _INSERT_LINK,
                [
                    ("task", payload.task_id, "run", payload.run_id, "trailer"),
                    ("run", payload.run_id, "commit", payload.sha, "trailer"),
                    *(("commit", payload.sha, "file", path, "diff") for path in payload.files),
                ],
            )
        elif isinstance(payload, TestsCollectedPayload):
            # Spec, "Projection rules": the latest collection replaces every `test_tag` link.
            self._conn.execute("DELETE FROM trace_links WHERE source = 'test_tag'")
            self._conn.executemany(
                _INSERT_LINK,
                [
                    link
                    for test in payload.tests
                    for link in (
                        ("test", test.node_id, "file", test.file, "test_tag"),
                        *(("test", test.node_id, "requirement", r, "test_tag") for r in test.req),
                    )
                ],
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

    def _link_spec(self, spec_version: str) -> None:
        # Spec, "Projection rules": the `spec` links are those of the latest approved version.
        self._conn.execute("DELETE FROM trace_links WHERE source = 'spec'")
        rows = self._conn.execute(
            "SELECT id, constrained_by FROM requirements WHERE spec_version = ?", (spec_version,)
        ).fetchall()
        self._conn.executemany(
            _INSERT_LINK,
            [
                ("requirement", req_id, "adr", adr_id, "spec")
                for req_id, constrained_by in rows
                for adr_id in json.loads(constrained_by)
            ],
        )

    def _link_plan(self, plan_id: str) -> None:
        tasks = self._conn.execute(
            "SELECT id, contract FROM tasks WHERE plan_id = ?", (plan_id,)
        ).fetchall()
        deps = self._conn.execute(
            "SELECT task_id, depends_on FROM task_deps WHERE task_id IN"
            " (SELECT id FROM tasks WHERE plan_id = ?)",
            (plan_id,),
        ).fetchall()
        self._conn.executemany(
            _INSERT_LINK,
            [
                ("requirement", req_id, "task", task_id, "contract")
                for task_id, contract in tasks
                for req_id in json.loads(contract)["requirements"]
            ]
            + [("task", task_id, "task", dep, "contract") for task_id, dep in deps],
        )
