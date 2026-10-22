"""Planner prompt: the one text a planner call receives, and its hash.

See docs/spec/phase1-spec.md ("Task contract": "Planning", "Plan checks"). The prompt holds
the requirements that are not deprecated with their acceptance criteria, the bodies of the
ADRs they are constrained by, the declared components, the forbidden paths, the gate names
and the tracked file names; it holds no file contents. It states that every task adds
tests under `tests/` with a `req` marker for each of its requirements. With rejections it is
the retry prompt: the same text with the rejection lines added.

The text is fixed by the arguments alone, so equal inputs give one `context_hash`.
"""

import hashlib
from collections.abc import Sequence

from openfactory.domain.contracts import REQUIRED_GATES
from openfactory.domain.models import Requirement, SpecSet
from openfactory.domain.plan_checks import PlanRejection, rejection_lines
from openfactory.domain.policy import BASELINE_FORBIDDEN_PATHS, Policy

_INSTRUCTIONS = """\
You are the planner. Break the requirements below into implementation tasks.

Reply with one structured result of the form {"tasks": [...]}. Each task has:
- task_id: capitals, a hyphen and three digits, for example AUTH-001; unique in the plan
- objective: what the task achieves
- requirements: the ids of the requirements it implements, at least one
- acceptance_criteria: the ids of the criteria it covers, at least one, each from its requirements
- depends_on: the task_ids of tasks in this plan that must be done first; no cycles
- components: declared components only
- role: "implementer"
- allowed_paths: the path patterns the task may change, at least one
- forbidden_paths: further path patterns the task must not change; may be empty

Path patterns: an entry of `allowed_paths` or `forbidden_paths` is a pattern, matched \
against a path relative to the repo root, with `/` separators, case-sensitively.
- `*` matches any run of characters except `/`, the empty run included.
- `**` as a whole segment matches zero or more segments.
- `?` matches one character except `/`.
- A pattern that ends with `/` is the same as that pattern followed by `**`.
- A pattern with no `/` matches a file of that name in any directory, so `.env` and `.env.*` cover \
every directory, and `*.py` in `allowed_paths` allows a Python file in every directory.
- There are no negations and no character classes: `!` and `[` are literal characters.

Rules:
- Every requirement below and every one of its acceptance criteria is covered by at least one task.
- Use only the requirement ids, acceptance criterion ids and components given below.
- Do not set required_gates or limits; the orchestrator sets them.
- Every task passes the gates named below, and no task may change a forbidden path.
- Every task adds tests under `tests/` that carry a `req` marker for each of its requirements, \
for example `@pytest.mark.req("REQ-AUTH-001")`, so its allowed_paths \
covers the test files it writes.
- You are given file names only, not file contents."""


_NONE = "(none)"


def _requirement_text(requirement: Requirement) -> str:
    lines = [
        f"### {requirement.id}: {requirement.title}",
        f"statement: {requirement.statement}",
        f"priority: {requirement.priority.value}",
        f"components: {', '.join(requirement.components)}",
        f"constrained_by: {', '.join(requirement.constrained_by) or _NONE}",
        "acceptance criteria:",
    ]
    lines.extend(f"- {ac.id}: {ac.text}" for ac in requirement.acceptance_criteria)
    return "\n".join(lines)


def _section(heading: str, lines: Sequence[str]) -> str:
    return "\n".join([f"## {heading}", *(lines or [_NONE])])


def build_planner_prompt(
    spec: SpecSet,
    policy: Policy,
    tracked_files: Sequence[str],
    rejections: Sequence[PlanRejection] = (),
) -> str:
    """The first prompt, or with `rejections` the retry prompt."""
    requirements = [r for r in spec.requirements if not r.deprecated]
    constraining = {adr_id for r in requirements for adr_id in r.constrained_by}
    adrs = [adr for adr in spec.adrs if adr.id in constraining]

    sections = [
        _INSTRUCTIONS,
        _section("Components", [f"- {component}" for component in spec.components]),
        "\n\n".join(["## Requirements", *(_requirement_text(r) for r in requirements)]),
        "\n\n".join(
            [
                "## ADRs",
                *([f'<adr id="{adr.id}">\n{adr.body}\n</adr>' for adr in adrs] or [_NONE]),
            ]
        ),
        _section(
            "Forbidden paths",
            [f"- {path}" for path in (*BASELINE_FORBIDDEN_PATHS, *policy.forbidden_paths)],
        ),
        _section("Gates", [f"- {gate}" for gate in REQUIRED_GATES]),
        _section("Tracked files", list(tracked_files)),
    ]
    if rejections:
        sections.append(
            _section(
                "Rejections of your earlier reply (rule  subject  message); "
                "reply again with a plan that has none of them",
                rejection_lines(rejections),
            )
        )
    return "\n\n".join(sections) + "\n"


def context_hash(prompt: str) -> str:
    """The SHA-256 of the prompt text encoded as UTF-8, as 64 lowercase hex characters."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()
