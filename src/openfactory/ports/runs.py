"""Runs port: read-only view of the agent run projection.

See docs/spec/phase1-spec.md ("Domain model and storage", "Ids"; "Task contract",
"Planning") and ADR-012.
"""

from typing import Protocol


class Runs(Protocol):
    def next_id(self) -> str:
        """The id after the highest one in use, finished or not; `run_0001` when there is none."""
        ...
