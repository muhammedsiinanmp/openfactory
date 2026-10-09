"""SQLite implementation of the EventStore port.

The `events` table SQL lives in `sqlite_events`, shared with the recorder adapter.
"""

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from openfactory.adapters.sqlite_events import (
    create_events_table,
    insert_event,
    select_events,
    stored_event,
)
from openfactory.domain.events import Event, StoredEvent
from openfactory.ports.event_store import EventStore


class SqliteEventStore:
    """Opens the database file, creating the `events` table if it is missing."""

    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        create_events_table(self._conn)
        self._conn.commit()

    def append(self, event: Event) -> StoredEvent:
        with self._conn:
            insert_event(self._conn, event)
        return stored_event(self._conn, event)

    def read(self, stream: str | None = None) -> list[StoredEvent]:
        return select_events(self._conn, stream=stream)

    def close(self) -> None:
        self._conn.close()


if TYPE_CHECKING:
    _: type[EventStore] = SqliteEventStore
