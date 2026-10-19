"""Process implementation of the GateRunner port: the `ruff` and `gitleaks` gates.

Runs each command of a gate in the task's worktree, as described under "Gates and
remediation" ("Running a gate that starts a process") in docs/spec/phase1-spec.md and in
ADR-015, ADR-016 and ADR-017: `ruff` through `uv run`, `gitleaks` from `PATH`. The
`pytest` gate is built by M4 outline item 2.

A failure is returned, not raised. The text layout and the texts of a timeout and of a
command that cannot be started are rows of 2026-10-16 in docs/decisions.md.
"""

import shlex
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from openfactory.domain.gates import GateOutput, ProcessGate
from openfactory.ports.gate_runner import GateRunner

_TOOLS = ("uv", "gitleaks")
_RUFF = (
    ["uv", "run", "ruff", "check"],
    ["uv", "run", "ruff", "format", "--check"],
)
_GITLEAKS = [
    "gitleaks",
    "git",
    "--pre-commit",
    "--staged",
    "--redact",
    "--no-banner",
    "--exit-code",
    "3",
    ".",
]
# Set by `--exit-code 3`: the only exit status that is a finding (ADR-016).
_FINDING = 3


class ProcessGates:
    def __init__(self, repo: Path) -> None:
        self.repo = repo

    def missing_tool(self) -> str | None:
        return next((tool for tool in _TOOLS if shutil.which(tool) is None), None)

    def run(self, gate: ProcessGate, worktree: Path, timeout_s: int) -> GateOutput:
        if gate == "pytest":
            raise NotImplementedError("pytest gate: outline item 2")
        commands = _RUFF if gate == "ruff" else (_GITLEAKS,)
        # Relative paths are resolved against the repo, not the caller's working directory.
        cwd = self.repo / worktree
        text = ""
        codes: list[int | None] = []
        # A gate's commands all run, whatever the earlier ones gave.
        for args in commands:
            part, code = _run_command(args, cwd, timeout_s)
            text += part
            codes.append(code)
        return GateOutput(
            passed=all(code == 0 for code in codes),
            text=text,
            finding=gate == "gitleaks" and codes == [_FINDING],
            marker_lines=[],
        )


def _run_command(args: list[str], cwd: Path, timeout_s: int) -> tuple[str, int | None]:
    """The command's text and its exit status, None when it timed out or did not start."""
    text = _line(f"$ {shlex.join(args)}")
    try:
        done = subprocess.run(args, capture_output=True, timeout=timeout_s, cwd=cwd, check=False)
    except subprocess.TimeoutExpired:
        return text + _line(f"timed out after {timeout_s} s"), None
    except OSError as error:
        return text + _line(f"{args[0]} could not be started: {error}"), None
    for printed in (done.stdout, done.stderr):
        text += _line(printed.decode("utf-8", errors="replace"))
    return text, done.returncode


def _line(part: str) -> str:
    """`part` ending in a line break, or nothing for an empty part."""
    if not part or part.endswith("\n"):
        return part
    return part + "\n"


if TYPE_CHECKING:
    _: type[GateRunner] = ProcessGates
