"""SQLite implementation of the Traces port.

Reads the `requirements` and `trace_links` projections described under "Projections"
in docs/spec/phase1-spec.md. It only runs SELECT statements and creates no table; the
event recorder creates and writes the projections. Its own connection follows ADR-010.
"""

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from openfactory.ports.traces import Traces

_BUSY_TIMEOUT_MS = 5000


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

    def close(self) -> None:
        self._conn.close()


if TYPE_CHECKING:
    _: type[Traces] = SqliteTraces
