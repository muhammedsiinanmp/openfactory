"""SQLite projector for the spec projections.

Implements "Projections" and "Projection rules" under "Domain model and storage" in
docs/spec/phase1-spec.md for the M1 tables. The projector has no port: it is internal
to the recorder adapter (ADR-009), so this module carries no conformance assertion.
"""

import json
import sqlite3
from collections.abc import Iterable
from typing import Any

from openfactory.domain.events import StoredEvent
from openfactory.domain.payloads import (
    PAYLOAD_MODELS,
    SpecApprovedPayload,
    SpecImportedPayload,
)
from openfactory.domain.spec_hash import content_hash

_TABLES = ("spec_versions", "requirements", "adrs")
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
        self._conn.executemany(
            "INSERT INTO requirements (id, spec_version, title, statement, priority, deprecated,"
            " components, constrained_by, acceptance_criteria, hash)"
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
            "INSERT INTO adrs (id, spec_version, status, body, hash) VALUES (?, ?, ?, ?, ?)",
            [(adr.id, version, adr.status.value, adr.body, content_hash(adr)) for adr in spec.adrs],
        )
