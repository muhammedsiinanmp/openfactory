"""GateRunner port: runs a gate that starts a process in a task's worktree.

See docs/spec/phase1-spec.md ("Gates and remediation", "Running a gate that starts a
process") and ADR-015, ADR-016, ADR-017.
"""

from pathlib import Path
from typing import Protocol

from openfactory.domain.gates import GateOutput, ProcessGate


class GateRunner(Protocol):
    def run(self, gate: ProcessGate, worktree: Path, timeout_s: int) -> GateOutput:
        """Run the commands of `gate` in `worktree`, each with a `timeout_s` limit.

        A failure is returned, not raised: a command that cannot be started or runs past
        `timeout_s` fails its gate, and the text says why. `worktree` is passed relative
        to the repo; the adapter resolves it against its own repo. `finding` is true only
        when `gitleaks` exits 3; `marker_lines` is empty for `ruff` and `gitleaks`.
        """
        ...

    def missing_tool(self) -> str | None:
        """The first of `uv` and `gitleaks` that is not on `PATH`, or None."""
        ...
