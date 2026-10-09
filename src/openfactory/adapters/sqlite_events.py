"""SQL and row helpers for the `events` table, shared by the SQLite adapters.

The `events` DDL is the one in docs/spec/phase1-spec.md ("Domain model and storage").
This module implements no port, so it carries no conformance assertion (ADR-010). None
of its functions commits: the caller owns the transaction.
"""

import json
import sqlite3

from openfactory.domain.events import Event, StoredEvent
from openfactory.ports.event_store import EventConflictError

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


def create_events_table(conn: sqlite3.Connection) -> None:
    conn.execute(_CREATE_EVENTS)


def insert_event(conn: sqlite3.Connection, event: Event) -> bool:
    """Insert the event unless its `event_id` is already stored; True if a row was written."""
    cursor = conn.execute(
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
    return cursor.rowcount == 1


def stored_event(conn: sqlite3.Connection, event: Event) -> StoredEvent:
    """Return the stored row for the event's `event_id`, which must exist.

    Raises `EventConflictError` if the stored content differs from the event's.
    """
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM events WHERE event_id = ?", (str(event.event_id),)
    ).fetchone()
    stored = _to_stored(row)
    if _canonical(stored) != _canonical(event):
        raise EventConflictError(
            f"event_id {event.event_id} is already stored with different content"
        )
    return stored


def select_events(
    conn: sqlite3.Connection, *, stream: str | None = None, after_seq: int = 0
) -> list[StoredEvent]:
    """Stored events with `seq` above `after_seq`, in ascending `seq`."""
    if stream is None:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM events WHERE seq > ? ORDER BY seq", (after_seq,)
        )
    else:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM events WHERE seq > ? AND stream = ? ORDER BY seq",
            (after_seq, stream),
        )
    return [_to_stored(row) for row in rows]
