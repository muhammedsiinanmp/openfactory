"""Gate output: what the `GateRunner` port returns for a gate that starts a process.

See "Running a gate that starts a process" and "The pytest gate and `req` markers" under
"Gates and remediation" in docs/spec/phase1-spec.md, and ADR-015, ADR-016, ADR-017. No
link between `passed`, `finding` and the gate is checked here: the adapter keeps it.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

# The gates that start a process; `path_check` is built in and `review` is an LLM call.
ProcessGate = Literal["ruff", "pytest", "gitleaks"]


class MarkerLine(BaseModel):
    """One collected test, as the `openfactory_req` plugin writes it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # The pytest node id, for example `tests/auth/test_login.py::test_ok`.
    node_id: str
    # Relative to the repo.
    file: str
    # The ids of its `req` markers; empty for a test with none.
    req: list[str]


class GateOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # As the adapter returns it: true when every command of the gate exited 0. For
    # `pytest` the use case also applies the tag rule.
    passed: bool
    # As the adapter returns it: each command line, then its standard output, then its
    # standard error. For `pytest` the use case may add the tag rule's lines.
    text: str
    # True only when `gitleaks` exits 3.
    finding: bool
    # The collected tests for `pytest`; empty for `ruff` and `gitleaks`.
    marker_lines: list[MarkerLine]
