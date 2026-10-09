"""SQLite implementation of the SpecVersions port.

Reads the `spec_versions` projection described under "Projections" and "Spec versions"
in docs/spec/phase1-spec.md. It only runs SELECT statements and creates no table; the
event recorder creates and writes the projections. Its own connection follows ADR-010.
"""

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from openfactory.domain.spec_versions import SpecVersionRef
from openfactory.ports.spec_versions import SpecVersions

_BUSY_TIMEOUT_MS = 5000
# Ids are compared by their number, so `sv_100` comes after `sv_99`.
_NUMBER = "CAST(substr(id, 4) AS INTEGER)"


class SqliteSpecVersions:
    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(path)
        self._conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")

    def latest_approved(self) -> SpecVersionRef | None:
        return self._latest("approved")

    def current_draft(self) -> SpecVersionRef | None:
        return self._latest("draft")

    def next_id(self) -> str:
        rows = self._conn.execute(f"SELECT MAX({_NUMBER}) FROM spec_versions").fetchall()
        highest: int = rows[0][0] or 0
        return f"sv_{highest + 1:02d}"

    def close(self) -> None:
        self._conn.close()

    def _latest(self, status: str) -> SpecVersionRef | None:
        # fetchall finishes the statement, so no read transaction stays open between calls.
        rows = self._conn.execute(
            f"SELECT id, hash FROM spec_versions WHERE status = ? ORDER BY {_NUMBER} DESC LIMIT 1",
            (status,),
        ).fetchall()
        if not rows:
            return None
        return SpecVersionRef(id=rows[0][0], hash=rows[0][1])


if TYPE_CHECKING:
    _: type[SpecVersions] = SqliteSpecVersions
