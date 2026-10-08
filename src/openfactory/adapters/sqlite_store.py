"""SQLite implementation of the EventStore port.

The `events` DDL is the one in docs/spec/phase1-spec.md ("Domain model and storage").
"""

import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from openfactory.domain.events import Event, StoredEvent
from openfactory.ports.event_store import EventConflictError, EventStore

_CREATE_EVENTS = """
CREATE TABLE IF NOT EXISTS events (
  seq          INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id     TEXT UNIQUE NOT NULL,
  stream       TEXT NOT NULL,
  type         TEXT NOT NULL,
  payload      TEXT NOT NULL,
  actor        TEXT NOT NULL,
  causation_id TEXT,
  created_at   TEXT NOT NULL
)
"""
_COLUMNS = "seq, event_id, stream, type, payload, actor, causation_id, created_at"


def _to_stored(row: sqlite3.Row) -> StoredEvent:
    return StoredEvent.model_validate({**dict(row), "payload": json.loads(row["payload"])})


def _canonical(event: Event) -> str:
    """Canonical JSON of the envelope fields, so that 1, 1.0 and true stay distinct."""
    return json.dumps(event.model_dump(mode="json", exclude={"seq"}), sort_keys=True)


class SqliteEventStore:
    """Opens the database file, creating the `events` table if it is missing."""

    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_CREATE_EVENTS)
        self._conn.commit()

    def append(self, event: Event) -> StoredEvent:
        with self._conn:
            self._conn.execute(
                "INSERT INTO events (event_id, stream, type, payload, actor, causation_id,"
                " created_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(event_id) DO NOTHING",
                (
                    str(event.event_id),
                    event.stream,
                    event.type.value,
                    json.dumps(event.payload),
                    event.actor,
                    str(event.causation_id) if event.causation_id else None,
                    event.created_at.isoformat(),
                ),
            )
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM events WHERE event_id = ?", (str(event.event_id),)
        ).fetchone()
        stored = _to_stored(row)
        if _canonical(stored) != _canonical(event):
            raise EventConflictError(
                f"event_id {event.event_id} is already stored with different content"
            )
        return stored

    def read(self, stream: str | None = None) -> list[StoredEvent]:
        if stream is None:
            rows = self._conn.execute(f"SELECT {_COLUMNS} FROM events ORDER BY seq")
        else:
            rows = self._conn.execute(
                f"SELECT {_COLUMNS} FROM events WHERE stream = ? ORDER BY seq", (stream,)
            )
        return [_to_stored(row) for row in rows]

    def close(self) -> None:
        self._conn.close()


if TYPE_CHECKING:
    _: type[EventStore] = SqliteEventStore
