"""The pytest tag rule: each requirement of the contract has a tagged test in a changed file.

See docs/spec/phase1-spec.md ("Gates and remediation": "The pytest gate and `req` markers";
"Traceability") and ADR-015. A marker line's `file` and the changed paths are both relative
to the worktree root in POSIX form, so they are compared as plain strings.
"""

from collections.abc import Sequence

from openfactory.domain.contracts import TaskContract
from openfactory.domain.gates import MarkerLine


def uncovered_requirements(
    marker_lines: Sequence[MarkerLine],
    changed_paths: Sequence[str],
    contract: TaskContract,
) -> list[str]:
    """The requirements with no tagged test in a changed file, in contract order, each once."""
    changed = set(changed_paths)
    covered = {req_id for line in marker_lines if line.file in changed for req_id in line.req}
    return [req_id for req_id in dict.fromkeys(contract.requirements) if req_id not in covered]


def tag_rule_lines(uncovered: Sequence[str]) -> list[str]:
    """One line per uncovered requirement, in the order given, with no line break."""
    return [f"no tagged test in a changed file: {req_id}" for req_id in uncovered]
