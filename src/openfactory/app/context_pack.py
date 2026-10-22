"""Context pack: the one text an implementer run receives.

See docs/spec/phase1-spec.md ("Execution": "The context pack") and ADR-014. The pack holds
the instructions, the task contract, the requirements and acceptance criteria the contract
names, the bodies of the ADRs those requirements are constrained by, and the names of the
tracked files that match `allowed_paths`; it holds no file contents. The spec items come
from the stored spec set of the plan's spec version, in that set's order. A retry's pack
ends with the failure report of the previous attempt ("Gates and remediation":
"Remediation"): its `failed` reason and each failed gate's output text, in recorded order.

The text is fixed by the arguments alone, so equal inputs give one `context_hash`, which the
caller takes with `context_hash` of `app/planner_prompt.py`.
"""

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from openfactory.domain.agent_run import ContextPack
from openfactory.domain.contracts import TaskContract
from openfactory.domain.models import Requirement, SpecSet
from openfactory.domain.path_patterns import matches_any

# The "Path patterns:" block repeats the spec word for word; a conformance test holds it.
_INSTRUCTIONS = """\
You are the implementer. Carry out the task contract below in this working directory.

Rules:
- Change, create or delete only files that match `allowed_paths`, and none that matches \
`forbidden_paths`. Leave no file outside `allowed_paths`, by-products of the tools you run \
included (for example `__pycache__/`): remove them before you finish.
- Every new test is under `tests/` and carries a `req` marker naming the requirement it \
covers, for example `@pytest.mark.req("REQ-AUTH-001")`.
- Do not run `git commit`; the orchestrator commits your changes.
- You are given file names only, not file contents; read the files you need.
- End with a short summary of what you changed.

Path patterns: an entry of `allowed_paths` or `forbidden_paths` is a pattern, matched \
against a path relative to the repo root, with `/` separators, case-sensitively.
- `*` matches any run of characters except `/`, the empty run included.
- `**` as a whole segment matches zero or more segments.
- `?` matches one character except `/`.
- A pattern that ends with `/` is the same as that pattern followed by `**`.
- A pattern with no `/` matches a file of that name in any directory, so `.env` and `.env.*` cover \
every directory, and `*.py` in `allowed_paths` allows a Python file in every directory.
- There are no negations and no character classes: `!` and `[` are literal characters."""

_NONE = "(none)"


class FailedGate(BaseModel):
    """A gate that failed in the previous attempt and the text of its output file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    gate: str
    text: str


class FailureReport(BaseModel):
    """The failure report of the previous attempt: its `failed` reason and failed gates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: str
    gates: list[FailedGate]


def _failure_text(failure: FailureReport) -> str:
    # A gate file's trailing newlines are dropped so each block ends `<text>\n</gate>`.
    blocks = [f'<gate name="{g.gate}">\n{g.text.rstrip("\n")}\n</gate>' for g in failure.gates]
    return "\n\n".join(
        [
            "## Failure report of the previous attempt",
            f"reason: {failure.reason}",
            *(blocks or [f"failed gates: {_NONE}"]),
        ]
    )


def _requirement_text(requirement: Requirement, criteria: set[str]) -> str:
    lines = [
        f"### {requirement.id}: {requirement.title}",
        f"statement: {requirement.statement}",
        f"constrained_by: {', '.join(requirement.constrained_by) or _NONE}",
        "acceptance criteria:",
    ]
    lines.extend(
        f"- {ac.id}: {ac.text}" for ac in requirement.acceptance_criteria if ac.id in criteria
    )
    return "\n".join(lines)


def build_context_pack(
    contract: TaskContract,
    spec: SpecSet,
    tracked_files: Sequence[str],
    failure: FailureReport | None = None,
) -> ContextPack:
    """The prompt text of an implementer run for `contract`.

    `failure` is the failure report of the previous attempt on a retry, else `None`.
    """
    criteria = set(contract.acceptance_criteria)
    requirements = [r for r in spec.requirements if r.id in contract.requirements]
    constraining = {adr_id for r in requirements for adr_id in r.constrained_by}
    adrs = [adr for adr in spec.adrs if adr.id in constraining]
    files = [name for name in tracked_files if matches_any(contract.allowed_paths, name)]

    sections = [
        _INSTRUCTIONS,
        "\n".join(["## Task contract", contract.model_dump_json(indent=2)]),
        "\n\n".join(
            [
                "## Requirements",
                *([_requirement_text(r, criteria) for r in requirements] or [_NONE]),
            ]
        ),
        "\n\n".join(
            [
                "## ADRs",
                *([f'<adr id="{adr.id}">\n{adr.body}\n</adr>' for adr in adrs] or [_NONE]),
            ]
        ),
        "\n".join(["## Tracked files that match allowed_paths", *(files or [_NONE])]),
    ]
    if failure is not None:
        sections.append(_failure_text(failure))
    return "\n\n".join(sections) + "\n"
