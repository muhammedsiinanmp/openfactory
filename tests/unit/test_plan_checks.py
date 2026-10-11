"""TASK-027: the plan checks for a planner reply.

Each test names the acceptance criterion it covers (AC1..AC6 in
docs/tasks/TASK-027-plan-content-checks.md).
"""

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from openfactory.domain import plan_checks
from openfactory.domain.contracts import PlannedTask
from openfactory.domain.models import AcceptanceCriterion, Requirement, SpecSet
from openfactory.domain.plan_checks import PlanRejection, PlanRule, check_plan
from openfactory.domain.spec_validation import Rule

PLAN_CHECKS_FILE = Path(plan_checks.__file__)


def req(req_id: str, criteria: list[str], deprecated: bool = False) -> Requirement:
    return Requirement(
        id=req_id,
        title=req_id,
        statement=req_id,
        priority="must",
        components=["auth"],
        acceptance_criteria=[AcceptanceCriterion(id=c, text=c) for c in criteria],
        deprecated=deprecated,
    )


SPEC = SpecSet(
    components=["auth"],
    requirements=[
        req("REQ-AUTH-001", ["AC-AUTH-001-1", "AC-AUTH-001-2"]),
        req("REQ-AUTH-002", ["AC-AUTH-002-1"]),
        req("REQ-AUTH-003", ["AC-AUTH-003-1"], deprecated=True),
    ],
)


def task(
    task_id: str = "AUTH-001",
    requirements: list[str] | None = None,
    criteria: list[str] | None = None,
    depends_on: list[str] | None = None,
    components: list[str] | None = None,
) -> PlannedTask:
    return PlannedTask(
        task_id=task_id,
        objective="Do it",
        requirements=requirements or ["REQ-AUTH-001"],
        acceptance_criteria=criteria or ["AC-AUTH-001-1", "AC-AUTH-001-2"],
        depends_on=depends_on or [],
        components=["auth"] if components is None else components,
        role="implementer",
        allowed_paths=["src/"],
    )


def auth_001(**changes: object) -> PlannedTask:
    return task(**changes)  # type: ignore[arg-type]


def auth_002(**changes: object) -> PlannedTask:
    base: dict[str, object] = {
        "task_id": "AUTH-002",
        "requirements": ["REQ-AUTH-002"],
        "criteria": ["AC-AUTH-002-1"],
        "depends_on": ["AUTH-001"],
    }
    return task(**(base | changes))  # type: ignore[arg-type]


def valid_plan() -> list[PlannedTask]:
    return [auth_001(), auth_002()]


def under(rule: PlanRule, tasks: list[PlannedTask]) -> list[PlanRejection]:
    return [r for r in check_plan(tasks, SPEC) if r.rule == rule]


def subjects(rejections: list[PlanRejection]) -> list[str]:
    return sorted(r.subject for r in rejections)


def imported_modules() -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(PLAN_CHECKS_FILE.read_text())):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


# AC1


def test_ac1_plan_rule_values_are_the_nine_spec_names() -> None:
    assert {r.value for r in PlanRule} == {
        "schema",
        "duplicate-task-id",
        "unknown-dependency",
        "cycle",
        "unknown-requirement",
        "deprecated-requirement",
        "unknown-criterion",
        "undeclared-component",
        "uncovered",
    }


def test_ac1_plan_rule_is_not_the_validation_rule() -> None:
    assert PlanRule is not Rule


def test_ac1_plan_rejection_has_three_fields_and_is_frozen() -> None:
    assert list(PlanRejection.model_fields) == ["rule", "subject", "message"]
    rejection = PlanRejection(rule=PlanRule("cycle"), subject="AUTH-001", message="m")
    with pytest.raises(ValidationError):
        rejection.subject = "AUTH-002"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        PlanRejection(rule=PlanRule("cycle"), subject="a", message="m", extra="x")  # type: ignore[call-arg]


def test_ac1_valid_plan_has_no_rejections() -> None:
    assert check_plan(valid_plan(), SPEC) == []


def test_ac1_check_plan_never_returns_schema() -> None:
    plan = [auth_001(requirements=["REQ-AUTH-009"], depends_on=["AUTH-009"])]
    assert PlanRule("schema") not in {r.rule for r in check_plan(plan, SPEC)}


def test_ac1_module_imports_no_outer_layer() -> None:
    forbidden = ("openfactory.adapters", "openfactory.app", "openfactory.ports")
    bad = [m for m in imported_modules() if m.startswith(forbidden)]
    assert bad == []


# AC2


@pytest.mark.parametrize("copies", [2, 3])
def test_ac2_duplicate_task_id_is_one_rejection_per_id(copies: int) -> None:
    plan = [*valid_plan(), *[auth_001() for _ in range(copies - 1)]]
    found = under(PlanRule("duplicate-task-id"), plan)
    assert subjects(found) == ["AUTH-001"]


def test_ac2_two_duplicated_ids_give_two_rejections() -> None:
    plan = [*valid_plan(), auth_001(), auth_002()]
    found = under(PlanRule("duplicate-task-id"), plan)
    assert subjects(found) == ["AUTH-001", "AUTH-002"]


def test_ac2_unknown_dependency_names_the_missing_task() -> None:
    plan = [auth_001(), auth_002(depends_on=["AUTH-001", "AUTH-009"])]
    found = under(PlanRule("unknown-dependency"), plan)
    assert subjects(found) == ["AUTH-002"]
    assert "AUTH-009" in found[0].message


@pytest.mark.parametrize(
    "deps, count",
    [(["AUTH-009", "AUTH-009"], 1), (["AUTH-008", "AUTH-009"], 2)],
)
def test_ac2_unknown_dependency_is_one_per_offending_id(deps: list[str], count: int) -> None:
    plan = [auth_001(), auth_002(depends_on=deps)]
    found = under(PlanRule("unknown-dependency"), plan)
    assert subjects(found) == ["AUTH-002"] * count


# AC3


def test_ac3_two_task_cycle_gives_one_rejection_per_task() -> None:
    plan = [auth_001(depends_on=["AUTH-002"]), auth_002()]
    found = under(PlanRule("cycle"), plan)
    assert subjects(found) == ["AUTH-001", "AUTH-002"]
    assert all(r.subject in r.message for r in found)


def test_ac3_three_task_ring_gives_three_rejections() -> None:
    plan = [
        auth_001(depends_on=["AUTH-003"]),
        auth_002(),
        auth_002(task_id="AUTH-003", depends_on=["AUTH-002"]),
    ]
    assert subjects(under(PlanRule("cycle"), plan)) == ["AUTH-001", "AUTH-002", "AUTH-003"]


def test_ac3_self_dependency_is_a_cycle_not_an_unknown_dependency() -> None:
    plan = [auth_001(depends_on=["AUTH-001"]), auth_002()]
    assert subjects(under(PlanRule("cycle"), plan)) == ["AUTH-001"]
    assert under(PlanRule("unknown-dependency"), plan) == []


def test_ac3_a_task_that_only_depends_on_a_cycle_is_not_on_it() -> None:
    plan = [
        auth_001(depends_on=["AUTH-002"]),
        auth_002(),
        auth_002(task_id="AUTH-003", depends_on=["AUTH-001"]),
    ]
    assert subjects(under(PlanRule("cycle"), plan)) == ["AUTH-001", "AUTH-002"]


def test_ac3_diamond_has_no_cycle() -> None:
    plan = [
        auth_001(task_id="AUTH-001"),
        auth_002(task_id="AUTH-002", depends_on=["AUTH-001"]),
        auth_002(task_id="AUTH-003", depends_on=["AUTH-001"]),
        auth_002(task_id="AUTH-004", depends_on=["AUTH-002", "AUTH-003"]),
    ]
    assert under(PlanRule("cycle"), plan) == []


def test_ac3_module_imports_no_graph_library() -> None:
    bad = [m for m in imported_modules() if m.split(".")[0] in {"networkx", "graphlib"}]
    assert bad == []


# AC4


def test_ac4_unknown_requirement_names_the_id_once_per_task() -> None:
    plan = [auth_001(requirements=["REQ-AUTH-001", "REQ-AUTH-009", "REQ-AUTH-009"]), auth_002()]
    found = under(PlanRule("unknown-requirement"), plan)
    assert subjects(found) == ["AUTH-001"]
    assert "REQ-AUTH-009" in found[0].message


def test_ac4_unknown_requirement_is_one_per_task() -> None:
    plan = [
        auth_001(requirements=["REQ-AUTH-009"]),
        auth_002(requirements=["REQ-AUTH-009"]),
    ]
    assert subjects(under(PlanRule("unknown-requirement"), plan)) == ["AUTH-001", "AUTH-002"]


def test_ac4_deprecated_requirement_is_not_an_unknown_one() -> None:
    plan = [auth_001(), auth_002(requirements=["REQ-AUTH-002", "REQ-AUTH-003"])]
    found = under(PlanRule("deprecated-requirement"), plan)
    assert subjects(found) == ["AUTH-002"]
    assert "REQ-AUTH-003" in found[0].message
    assert under(PlanRule("unknown-requirement"), plan) == []


def test_ac4_undeclared_component_names_the_component() -> None:
    plan = [auth_001(components=["auth", "billing"]), auth_002()]
    found = under(PlanRule("undeclared-component"), plan)
    assert subjects(found) == ["AUTH-001"]
    assert "billing" in found[0].message


# AC5


def test_ac5_criterion_not_in_the_spec_is_rejected() -> None:
    criteria = ["AC-AUTH-001-1", "AC-AUTH-001-2", "AC-AUTH-009-1"]
    plan = [auth_001(criteria=criteria), auth_002()]
    found = under(PlanRule("unknown-criterion"), plan)
    assert subjects(found) == ["AUTH-001"]
    assert "AC-AUTH-009-1" in found[0].message


def test_ac5_criterion_of_another_requirement_is_rejected() -> None:
    criteria = ["AC-AUTH-001-1", "AC-AUTH-001-2", "AC-AUTH-002-1"]
    plan = [auth_001(criteria=criteria), auth_002()]
    found = under(PlanRule("unknown-criterion"), plan)
    assert subjects(found) == ["AUTH-001"]
    assert "AC-AUTH-002-1" in found[0].message


def test_ac5_criteria_of_every_named_requirement_are_accepted() -> None:
    plan = [
        auth_001(
            requirements=["REQ-AUTH-001", "REQ-AUTH-002"],
            criteria=["AC-AUTH-001-1", "AC-AUTH-001-2", "AC-AUTH-002-1"],
        )
    ]
    assert under(PlanRule("unknown-criterion"), plan) == []


# AC6


def test_ac6_a_requirement_no_task_names_is_uncovered_with_its_criteria() -> None:
    found = under(PlanRule("uncovered"), [auth_001()])
    assert subjects(found) == ["AC-AUTH-002-1", "REQ-AUTH-002"]
    assert all(r.subject in r.message for r in found)


def test_ac6_an_unlisted_criterion_is_uncovered_but_its_requirement_is_not() -> None:
    plan = [auth_001(criteria=["AC-AUTH-001-1"]), auth_002()]
    assert subjects(under(PlanRule("uncovered"), plan)) == ["AC-AUTH-001-2"]


def test_ac6_a_deprecated_requirement_is_never_uncovered() -> None:
    found = {r.subject for r in check_plan([auth_001()], SPEC) if r.rule == PlanRule("uncovered")}
    assert not found & {"REQ-AUTH-003", "AC-AUTH-003-1"}


def test_ac6_two_broken_rules_are_both_reported_in_one_call() -> None:
    result = check_plan([auth_001(requirements=["REQ-AUTH-009"])], SPEC)
    rules = {r.rule for r in result}
    assert {PlanRule("unknown-requirement"), PlanRule("uncovered")} <= rules
