"""Process implementation of the GateRunner port: the `ruff`, `pytest` and `gitleaks` gates.

Runs each command of a gate in the task's worktree, as described under "Gates and
remediation" ("Running a gate that starts a process", "The pytest gate and `req`
markers") in docs/spec/phase1-spec.md and in ADR-015, ADR-016 and ADR-017: `ruff` and
`pytest` through `uv run`, `gitleaks` from `PATH`. The `pytest` gate loads the
`openfactory_req` plugin from `pytest_plugin/` through `PYTHONPATH`.

A failure is returned, not raised. The text layout and the texts of a timeout and of a
command that cannot be started are rows of 2026-10-16 in docs/decisions.md; the handling
of the marker lines is a row of 2026-10-19.
"""

import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from openfactory.domain.gates import GateOutput, MarkerLine, ProcessGate
from openfactory.ports.gate_runner import GateRunner

_TOOLS = ("uv", "gitleaks")
_RUFF = (
    ["uv", "run", "ruff", "check"],
    ["uv", "run", "ruff", "format", "--check"],
)
_PYTEST_COLLECT = ["uv", "run", "pytest", "--collect-only", "-q", "-p", "openfactory_req", "tests/"]
_PYTEST_RUN = ["uv", "run", "pytest", "-p", "openfactory_req", "tests/"]
# Put on `PYTHONPATH` for both pytest commands; the plugin is never imported here.
_PLUGIN_DIR = Path(__file__).resolve().parent / "pytest_plugin"
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
        # Relative paths are resolved against the repo, not the caller's working directory.
        cwd = self.repo / worktree
        if gate == "pytest":
            return _run_pytest(cwd, timeout_s)
        commands = _RUFF if gate == "ruff" else (_GITLEAKS,)
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


def _run_pytest(cwd: Path, timeout_s: int) -> GateOutput:
    """Both pytest commands; the marker lines come from the `--collect-only` one."""
    env = dict(os.environ)
    # Set below for the `--collect-only` command only, whatever the caller's environment holds.
    env.pop("OPENFACTORY_REQ_OUT", None)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(_PLUGIN_DIR), env.get("PYTHONPATH")]))
    descriptor, name = tempfile.mkstemp()
    os.close(descriptor)
    req_out = Path(name)
    try:
        text, collect_code = _run_command(
            _PYTEST_COLLECT, cwd, timeout_s, env | {"OPENFACTORY_REQ_OUT": name}
        )
        written = req_out.read_text(encoding="utf-8", errors="replace")
    finally:
        req_out.unlink(missing_ok=True)
    part, run_code = _run_command(_PYTEST_RUN, cwd, timeout_s, env)
    text += part
    marker_lines: list[MarkerLine] = []
    invalid: str | None = None
    for line in filter(None, written.splitlines()):
        try:
            marker_lines.append(MarkerLine.model_validate_json(line))
        except ValidationError:
            invalid = line
            break
    if invalid is not None:
        # The `req` values come from the target repo's tests: returned, not raised.
        return GateOutput(
            passed=False,
            text=text + _line(f"invalid marker line: {invalid}"),
            finding=False,
            marker_lines=[],
        )
    return GateOutput(
        passed=collect_code == 0 and run_code == 0,
        text=text,
        finding=False,
        marker_lines=marker_lines,
    )


def _run_command(
    args: list[str], cwd: Path, timeout_s: int, env: dict[str, str] | None = None
) -> tuple[str, int | None]:
    """The command's text and its exit status, None when it timed out or did not start."""
    text = _line(f"$ {shlex.join(args)}")
    try:
        done = subprocess.run(
            args, capture_output=True, timeout=timeout_s, cwd=cwd, env=env, check=False
        )
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
