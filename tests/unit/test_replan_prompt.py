"""TASK-101: the replan prompt (AC1 to AC6).

Each test names the acceptance criterion it covers in docs/tasks/TASK-101-replan-prompt.md.
Tests check what the prompt holds and the order of its parts, never its exact wording.
"""

import ast
import importlib
from pathlib import Path

import pytest

from openfactory.app.planner_prompt import build_planner_prompt, context_hash
from openfactory.app.replan_prompt import build_replan_prompt, untouched_tasks
from openfactory.domain.contracts import PlannedTask, complete_contract
from openfactory.domain.models import AcceptanceCriterion, Requirement, SpecSet
from openfactory.domain.payloads import ImpactComputedPayload, RequirementImpact
from openfactory.domain.plan_checks import PlanRejection, PlanRule, rejection_lines
from openfactory.domain.plans import Task
from openfactory.domain.policy import Policy
from openfactory.domain.states import TaskState

POLICY = Policy()
TRACKED = ["src/app/login.py", "tests/test_login.py"]
REJECTIONS = [
    PlanRejection(rule=PlanRule.uncovered, subject="AC-AUTH-006-1", message="no task covers it"),
    PlanRejection(rule=PlanRule.cycle, subject="AUTH-006", message="depends on itself"),
]


def make_req(n: int) -> Requirement:
    return Requirement(
        id=f"REQ-AUTH-00{n}",
        title=f"Title {n}",
        statement=f"Statement {n}.",
        priority="must",
        components=["auth"],
        acceptance_criteria=[AcceptanceCriterion(id=f"AC-AUTH-00{n}-1", text=f"Criterion {n}.")],
    )


SPEC = SpecSet(components=["auth"], requirements=[make_req(n) for n in range(1, 8)], adrs=[])


def make_task(n: int, state: TaskState, depends_on: list[str] | None = None) -> Task:
    planned = PlannedTask(
        task_id=f"AUTH-00{n}",
        objective=f"Objective-of-task-{n}",
        requirements=[f"REQ-AUTH-00{n}"],
        acceptance_criteria=[f"AC-AUTH-00{n}-1"],
        depends_on=depends_on or [],
        components=["auth"],
        role="implementer",
        allowed_paths=[f"src/zone{n}/**"],
        forbidden_paths=[],
    )
    return Task(
        id=planned.task_id,
        plan_id="plan_01",
        state=state,
        attempt=1,
        contract=complete_contract(planned, POLICY),
        depends_on=list(planned.depends_on),
    )


def plan_tasks(untouched_001_state: TaskState = TaskState.passed) -> list[Task]:
    return [
        make_task(5, TaskState.invalidated),
        make_task(3, TaskState.pending, ["AUTH-002"]),
        make_task(1, untouched_001_state),
        make_task(4, TaskState.abandoned),
        make_task(2, TaskState.passed),
    ]


def req_impact(
    req_id: str,
    change: str,
    obsolete: list[str] | None = None,
    new_work: list[str] | None = None,
) -> RequirementImpact:
    return RequirementImpact(
        id=req_id,
        change=change,  # pyright: ignore[reportArgumentType]
        kind="behavioral" if change == "modified" else None,
        rationale="why" if change == "modified" else None,
        obsolete_criteria=obsolete or [],
        new_work=new_work or [],
    )


def make_impact(**changes: object) -> ImpactComputedPayload:
    fields: dict[str, object] = {
        "from_version": "sv_01",
        "to_version": "sv_02",
        "run_id": None,
        "requirements": [
            req_impact(
                "REQ-AUTH-002",
                "modified",
                obsolete=["AC-AUTH-002-9", "AC-AUTH-002-3"],
                new_work=["Add session expiry"],
            ),
            req_impact("REQ-AUTH-007", "added"),
            req_impact("REQ-AUTH-006", "added"),
        ],
        "adrs": [],
        "tasks": ["AUTH-002"],
        "downstream": ["AUTH-003"],
        "files": ["src/zone2/b.py", "src/zone2/a.py"],
        "tests": ["tests/test_zone2_z.py", "tests/test_zone2_y.py"],
    }
    fields.update(changes)
    return ImpactComputedPayload(**fields)  # type: ignore[arg-type]


def replan(
    impact: ImpactComputedPayload | None = None,
    tasks: list[Task] | None = None,
    rejections: list[PlanRejection] | None = None,
) -> str:
    return build_replan_prompt(
        SPEC,
        POLICY,
        TRACKED,
        impact or make_impact(),
        tasks if tasks is not None else plan_tasks(),
        rejections or (),
    )


def replan_part(text: str) -> str:
    """The text after the planner prompt's own sections."""
    base = build_planner_prompt(SPEC, POLICY, TRACKED).rstrip("\n")
    assert text.startswith(base)
    return text[len(base) :]


def contract_json(n: int) -> str:
    task = next(t for t in plan_tasks() if t.id == f"AUTH-00{n}")
    return task.contract.model_dump_json(indent=2)


def test_task101_ac1_planner_prompt_comes_first_and_extra_sits_before_rejections() -> None:
    assert build_planner_prompt(SPEC, POLICY, TRACKED, extra=()) == build_planner_prompt(
        SPEC, POLICY, TRACKED
    )
    extra = build_planner_prompt(SPEC, POLICY, TRACKED, REJECTIONS, extra=["## Extra\nmarker-xyz"])
    assert "marker-xyz" in extra
    lines = rejection_lines(REJECTIONS)
    assert extra.index("Tracked files") < extra.index("marker-xyz") < extra.index(lines[0])


def test_task101_ac1_replan_is_planner_prompt_plus_sections_with_rejections_last() -> None:
    first = replan()
    assert replan_part(first).strip()
    retry = replan(rejections=REJECTIONS)
    assert retry.startswith(build_planner_prompt(SPEC, POLICY, TRACKED).rstrip("\n"))
    lines = rejection_lines(REJECTIONS)
    assert retry.index("Objective-of-task-1") < retry.index(lines[0])
    assert retry.rstrip("\n").splitlines()[-len(lines) :] == lines
    assert lines[0] not in first


def test_task101_ac2_contracts_of_impacted_and_downstream_in_ascending_id() -> None:
    part = replan_part(replan())
    assert contract_json(2) in part
    assert contract_json(3) in part
    assert part.index(contract_json(2)) < part.index(contract_json(3))
    # impacted and downstream are under separate headings
    between = part[
        part.index(contract_json(2)) + len(contract_json(2)) : part.index(contract_json(3))
    ]
    assert "##" in between


def test_task101_ac2_ids_sorted_as_strings_and_other_tasks_have_no_contract() -> None:
    impact = make_impact(tasks=["AUTH-002", "AUTH-001"], downstream=["AUTH-004", "AUTH-003"])
    part = replan_part(replan(impact))
    positions = [part.index(contract_json(n)) for n in (1, 2)]
    assert positions == sorted(positions)
    positions = [part.index(contract_json(n)) for n in (3, 4)]
    assert positions == sorted(positions)
    part = replan_part(replan())
    for n in (1, 4, 5):
        assert contract_json(n) not in part


def test_task101_ac3_files_tests_and_obsolete_criteria_sorted_and_listed_once() -> None:
    impact = make_impact(
        requirements=[
            req_impact("REQ-AUTH-002", "modified", obsolete=["AC-AUTH-002-9", "AC-AUTH-002-3"]),
            req_impact("REQ-AUTH-001", "modified", obsolete=["AC-AUTH-002-3"]),
        ]
    )
    part = replan_part(replan(impact))
    for ordered in (
        ["src/zone2/a.py", "src/zone2/b.py"],
        ["tests/test_zone2_y.py", "tests/test_zone2_z.py"],
        ["AC-AUTH-002-3", "AC-AUTH-002-9"],
    ):
        positions = [part.index(item) for item in ordered]
        assert positions == sorted(positions), ordered
    assert part.count("AC-AUTH-002-3") == 1


def test_task101_ac3_new_work_is_requirement_id_colon_text_in_requirement_order() -> None:
    impact = make_impact(
        requirements=[
            req_impact("REQ-AUTH-002", "modified", new_work=["Add session expiry"]),
            req_impact("REQ-AUTH-001", "modified", new_work=["Rework login form"]),
        ]
    )
    part = replan_part(replan(impact))
    first, second = "REQ-AUTH-002: Add session expiry", "REQ-AUTH-001: Rework login form"
    assert part.index(first) < part.index(second)


def test_task101_ac3_an_empty_group_shows_none() -> None:
    full = replan_part(replan())
    empty_tests = replan_part(replan(make_impact(tests=[])))
    assert empty_tests.count("(none)") == full.count("(none)") + 1


def test_task101_ac4_untouched_tasks_keeps_every_state_in_id_order() -> None:
    found = untouched_tasks(plan_tasks(), make_impact())
    assert [t.id for t in found] == ["AUTH-001", "AUTH-004", "AUTH-005"]
    assert [t.state for t in found] == [
        TaskState.passed,
        TaskState.abandoned,
        TaskState.invalidated,
    ]


def test_task101_ac4_prompt_lists_untouched_not_invalidated_without_full_contract() -> None:
    part = replan_part(replan())
    window = part[part.index("Objective-of-task-1") :]
    block1 = window[:400]
    for item in ("AUTH-001", "passed", "REQ-AUTH-001", "AC-AUTH-001-1"):
        assert item in block1, item
    block4 = part[part.index("Objective-of-task-4") :]
    assert "AUTH-004" in block4[:400]
    assert "abandoned" in block4[:400]
    assert "AUTH-005" not in part
    assert "Objective-of-task-5" not in part
    assert "src/zone1/**" not in part  # a block, not the contract
    assert "src/zone4/**" not in part


def test_task101_ac5_instructions_cover_the_stated_points() -> None:
    part = replan_part(replan()).lower()
    for term in ("allowed_paths", "delete", "abandoned", "invalidated", "precedence"):
        assert term in part, term
    assert '{"tasks": []}' in replan_part(replan())


def test_task101_ac5_instructions_name_added_requirements_sorted_or_none() -> None:
    part = replan_part(replan())  # REQ-AUTH-007 listed before REQ-AUTH-006 in the impact
    assert part.index("REQ-AUTH-006") < part.index("REQ-AUTH-007")
    no_added = make_impact(requirements=[req_impact("REQ-AUTH-002", "modified")])
    assert "REQ-AUTH-006" not in replan_part(replan(no_added))
    assert "REQ-AUTH-007" not in replan_part(replan(no_added))
    assert "(none)" in replan_part(replan(no_added))


@pytest.mark.parametrize("term", ["precedence", "allowed_paths"])
def test_task101_ac5_instruction_points_do_not_depend_on_the_arguments(term: str) -> None:
    empty = make_impact(requirements=[], tasks=[], downstream=[], files=[], tests=[])
    assert term in replan_part(replan(empty, tasks=[])).lower()


def test_task101_ac6_equal_arguments_equal_text_and_inputs_not_mutated() -> None:
    impact, tasks = make_impact(), plan_tasks()
    before = (impact.model_dump(), [t.model_dump() for t in tasks])
    first = build_replan_prompt(SPEC, POLICY, TRACKED, impact, tasks)
    assert first == build_replan_prompt(SPEC, POLICY, TRACKED, impact, tasks)
    assert (impact.model_dump(), [t.model_dump() for t in tasks]) == before


def test_task101_ac6_untouched_state_or_impact_file_changes_the_hash() -> None:
    base = context_hash(replan())
    assert context_hash(replan(tasks=plan_tasks(TaskState.failed))) != base
    other = make_impact(files=["src/zone2/b.py", "src/zone2/c.py"])
    assert context_hash(replan(other)) != base


def test_task101_ac6_module_imports_only_domain_and_planner_prompt() -> None:
    source = Path(importlib.import_module("openfactory.app.replan_prompt").__file__ or "")
    imported: list[str] = []
    for node in ast.walk(ast.parse(source.read_text())):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    own = [m for m in imported if m == "openfactory" or m.startswith("openfactory.")]
    allowed = ("openfactory.domain", "openfactory.app.planner_prompt")
    assert all(m.startswith(allowed) for m in own), own
