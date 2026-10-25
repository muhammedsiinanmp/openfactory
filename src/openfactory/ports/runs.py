"""Runs port: read-only view of the agent run projection.

See docs/spec/phase1-spec.md ("Domain model and storage", "Ids"; "Task contract",
"Planning"; "Execution", "Restart"), ADR-012, ADR-014 and ADR-020.
"""

from typing import Protocol

from openfactory.domain.agent_run import RunRecord


class Runs(Protocol):
    def next_id(self) -> str:
        """The id after the highest one in use, finished or not; `run_0001` when there is none."""
        ...

    def unfinished_run(self, task_id: str) -> str | None:
        """The id of the task's run that has no `AgentRunFinished`, or None. If there are
        several, the one with the highest number."""
        ...

    def all_runs(self) -> list[RunRecord]:
        """Every run, finished or not, in ascending run number."""
        ...
