"""SQLite implementation of the Runs port.

Reads the `agent_runs` projection described under "Projections" in
docs/spec/phase1-spec.md. It only runs SELECT statements and creates no table; the
event recorder creates and writes the projections. Its own connection follows ADR-010.
"""

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from openfactory.ports.runs import Runs

_BUSY_TIMEOUT_MS = 5000
# Ids are compared by their number, so `run_10000` comes after `run_9999`.
_NUMBER = "CAST(substr(id, 5) AS INTEGER)"


class SqliteRuns:
    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(path)
        self._conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")

    def next_id(self) -> str:
        # fetchall finishes the statement, so no read transaction stays open between calls.
        rows = self._conn.execute(f"SELECT MAX({_NUMBER}) FROM agent_runs").fetchall()
        highest: int = rows[0][0] or 0
        return f"run_{highest + 1:04d}"

    def close(self) -> None:
        self._conn.close()


if TYPE_CHECKING:
    _: type[Runs] = SqliteRuns
