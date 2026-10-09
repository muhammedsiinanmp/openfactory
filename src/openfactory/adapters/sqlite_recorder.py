"""SQLite implementation of the EventRecorder port.

Implements "Projection rules" under "Domain model and storage" in
docs/spec/phase1-spec.md: append, apply and `projection_state.last_seq` in one
transaction, catch-up on open, and rebuild. Design choices are in ADR-010.
"""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, cast

from pydantic import ValidationError

from openfactory.adapters.sqlite_events import (
    create_events_table,
    insert_event,
    select_events,
    stored_event,
)
from openfactory.adapters.sqlite_projector import SqliteProjector
from openfactory.domain.events import Event, StoredEvent
from openfactory.domain.payloads import PAYLOAD_MODELS
from openfactory.ports.event_recorder import EventRecorder

if TYPE_CHECKING:
    from pydantic_core import InitErrorDetails

_BUSY_TIMEOUT_MS = 5000
_CREATE_STATE = """
CREATE TABLE IF NOT EXISTS projection_state (
    id       INTEGER PRIMARY KEY,
    last_seq INTEGER NOT NULL
)
"""


class SqliteEventRecorder:
    """Opens the database file, creates what is missing and applies unapplied events."""

    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._projector = SqliteProjector(self._conn)
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
            with self._transaction():
                create_events_table(self._conn)
                self._projector.create_tables()
                self._conn.execute(_CREATE_STATE)
                self._conn.execute(
                    "INSERT OR IGNORE INTO projection_state (id, last_seq) VALUES (1, 0)"
                )
                self._catch_up()
        except BaseException:
            self._conn.close()
            raise

    def record(self, event: Event) -> StoredEvent:
        with self._transaction():
            inserted = insert_event(self._conn, event)
            stored = stored_event(self._conn, event)
            if inserted:
                self._projector.apply(stored)
                self._set_last_seq(stored.seq)
        return stored

    def rebuild(self) -> None:
        """Clear the projections and replay every stored event, or change nothing."""
        with self._transaction():
            events = select_events(self._conn)
            self._projector.rebuild(events)
            self._set_last_seq(events[-1].seq if events else 0)

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def _transaction(self) -> Generator[None]:
        # IMMEDIATE takes the write lock up front, so busy_timeout covers the wait and
        # DDL is rolled back with everything else.
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self._conn.rollback()
            raise
        self._conn.commit()

    def _catch_up(self) -> None:
        last_seq: int = self._conn.execute(
            "SELECT last_seq FROM projection_state WHERE id = 1"
        ).fetchone()[0]
        for event in select_events(self._conn, after_seq=last_seq):
            try:
                self._projector.apply(event)
            except ValidationError as exc:
                raise ValidationError.from_exception_data(
                    f"stored event seq {event.seq} ({exc.title})",
                    cast("list[InitErrorDetails]", exc.errors()),
                ) from exc
            except sqlite3.IntegrityError as exc:
                model = PAYLOAD_MODELS[event.type].__name__
                raise sqlite3.IntegrityError(
                    f"stored event seq {event.seq} ({model}): {exc}"
                ) from exc
            last_seq = event.seq
        self._set_last_seq(last_seq)

    def _set_last_seq(self, seq: int) -> None:
        self._conn.execute("UPDATE projection_state SET last_seq = ? WHERE id = 1", (seq,))


if TYPE_CHECKING:
    _: type[EventRecorder] = SqliteEventRecorder
