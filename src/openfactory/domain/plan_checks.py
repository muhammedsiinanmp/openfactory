"""Deterministic checks of a planner reply against the spec set it was planned from.

Implements "Plan checks" under "Task contract" in docs/spec/phase1-spec.md. `parse_reply`
is the `schema` rule: it loads a structured result into the models or returns one rejection
per Pydantic error. `check_plan` runs the eight content rules on tasks that already loaded
and never returns `schema`; there is one rejection per subject and offending id.

The rule names are the plan's own set, separate from `spec_validation.Rule`.
"""

from collections import Counter
from collections.abc import Sequence
from enum import StrEnum
from typing import cast

from pydantic import BaseModel, ConfigDict, ValidationError

from openfactory.domain.contracts import PlannedTask, PlannerReply
from openfactory.domain.models import SpecSet


class PlanRule(StrEnum):
    schema = "schema"
    duplicate_task_id = "duplicate-task-id"
    unknown_dependency = "unknown-dependency"
    cycle = "cycle"
    unknown_requirement = "unknown-requirement"
    deprecated_requirement = "deprecated-requirement"
    unknown_criterion = "unknown-criterion"
    undeclared_component = "undeclared-component"
    uncovered = "uncovered"
    task_id_in_use = "task-id-in-use"


class PlanRejection(BaseModel):
    """One broken rule; `subject` is the ID it concerns."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule: PlanRule
    subject: str
    message: str


class ParsedReply(BaseModel):
    """A planner reply after the `schema` rule: the tasks, or the rejections and no tasks."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tasks: list[PlannedTask] | None
    rejections: list[PlanRejection]


def rejection_lines(rejections: Sequence[PlanRejection]) -> list[str]:
    """One `rule  subject  message` line per rejection, sorted by rule, subject, then message.

    The form `plan` prints and `AgentRunFinished.error` stores: two spaces between the
    fields, sorted as strings.
    """
    return [
        "  ".join(key) for key in sorted((r.rule.value, r.subject, r.message) for r in rejections)
    ]


def _schema_subject(structured: object, loc: tuple[int | str, ...]) -> str:
    """The `task_id` of the task the error lies in when that value is a string, else `reply`."""
    if isinstance(structured, dict) and len(loc) >= 2 and loc[0] == "tasks":
        tasks = cast("dict[object, object]", structured).get("tasks")
        index = loc[1]
        if isinstance(tasks, list) and isinstance(index, int):
            items = cast("list[object]", tasks)
            if index < len(items) and isinstance(task := items[index], dict):
                task_id = cast("dict[object, object]", task).get("task_id")
                if isinstance(task_id, str):
                    return task_id
    return "reply"


def parse_reply(structured: object | None) -> ParsedReply:
    """Load a planner's structured result, or return its `schema` rejections.

    `None` is a missing structured result. There is one rejection per Pydantic error, with
    the field path in its message.
    """
    if structured is None:
        return ParsedReply(
            tasks=None,
            rejections=[
                PlanRejection(rule=PlanRule.schema, subject="reply", message="no structured result")
            ],
        )
    try:
        reply = PlannerReply.model_validate(structured)
    except ValidationError as error:
        rejections: list[PlanRejection] = []
        for detail in error.errors():
            loc = detail["loc"]
            field_path = ".".join(str(part) for part in loc)
            rejections.append(
                PlanRejection(
                    rule=PlanRule.schema,
                    subject=_schema_subject(structured, loc),
                    message=f"{field_path}: {detail['msg']}" if field_path else detail["msg"],
                )
            )
        return ParsedReply(tasks=None, rejections=rejections)
    return ParsedReply(tasks=list(reply.tasks), rejections=[])


def _once(ids: Sequence[str]) -> list[str]:
    """Each id once, in order of first appearance."""
    return list(dict.fromkeys(ids))


def _duplicate_task_id(tasks: Sequence[PlannedTask]) -> list[PlanRejection]:
    counts = Counter(t.task_id for t in tasks)
    return [
        PlanRejection(
            rule=PlanRule.duplicate_task_id,
            subject=task_id,
            message=f"task id {task_id!r} is used by {count} tasks",
        )
        for task_id, count in counts.items()
        if count > 1
    ]


def _unknown_dependency(tasks: Sequence[PlannedTask]) -> list[PlanRejection]:
    in_plan = {t.task_id for t in tasks}
    return [
        PlanRejection(
            rule=PlanRule.unknown_dependency,
            subject=t.task_id,
            message=f"task {t.task_id!r} depends on {dep!r}, which is not in the plan",
        )
        for t in tasks
        for dep in _once(t.depends_on)
        if dep not in in_plan
    ]


def _cycle(tasks: Sequence[PlannedTask]) -> list[PlanRejection]:
    # Dependencies on tasks outside the plan are left out: nothing is reached through them.
    in_plan = {t.task_id for t in tasks}
    deps: dict[str, list[str]] = {}
    for t in tasks:
        deps.setdefault(t.task_id, []).extend(d for d in t.depends_on if d in in_plan)

    def reaches_itself(task_id: str) -> bool:
        seen: set[str] = set()
        stack = list(deps[task_id])
        while stack:
            current = stack.pop()
            if current == task_id:
                return True
            if current not in seen:
                seen.add(current)
                stack.extend(deps[current])
        return False

    return [
        PlanRejection(
            rule=PlanRule.cycle,
            subject=task_id,
            message=f"task {task_id!r} lies on a dependency cycle",
        )
        for task_id in deps
        if reaches_itself(task_id)
    ]


def _unknown_requirement(tasks: Sequence[PlannedTask], spec: SpecSet) -> list[PlanRejection]:
    known = {r.id for r in spec.requirements}
    return [
        PlanRejection(
            rule=PlanRule.unknown_requirement,
            subject=t.task_id,
            message=f"task {t.task_id!r} names requirement {req_id!r}, which is not in the spec",
        )
        for t in tasks
        for req_id in _once(t.requirements)
        if req_id not in known
    ]


def _deprecated_requirement(tasks: Sequence[PlannedTask], spec: SpecSet) -> list[PlanRejection]:
    deprecated = {r.id for r in spec.requirements if r.deprecated}
    return [
        PlanRejection(
            rule=PlanRule.deprecated_requirement,
            subject=t.task_id,
            message=f"task {t.task_id!r} names deprecated requirement {req_id!r}",
        )
        for t in tasks
        for req_id in _once(t.requirements)
        if req_id in deprecated
    ]


def _unknown_criterion(tasks: Sequence[PlannedTask], spec: SpecSet) -> list[PlanRejection]:
    criteria = {r.id: {ac.id for ac in r.acceptance_criteria} for r in spec.requirements}
    rejections: list[PlanRejection] = []
    for t in tasks:
        own = {ac_id for req_id in t.requirements for ac_id in criteria.get(req_id, set())}
        rejections.extend(
            PlanRejection(
                rule=PlanRule.unknown_criterion,
                subject=t.task_id,
                message=(
                    f"task {t.task_id!r} lists acceptance criterion {ac_id!r}, "
                    "which belongs to none of its requirements"
                ),
            )
            for ac_id in _once(t.acceptance_criteria)
            if ac_id not in own
        )
    return rejections


def _undeclared_component(tasks: Sequence[PlannedTask], spec: SpecSet) -> list[PlanRejection]:
    declared = set(spec.components)
    return [
        PlanRejection(
            rule=PlanRule.undeclared_component,
            subject=t.task_id,
            message=f"task {t.task_id!r} names undeclared component {component!r}",
        )
        for t in tasks
        for component in _once(t.components)
        if component not in declared
    ]


def _uncovered(tasks: Sequence[PlannedTask], spec: SpecSet) -> list[PlanRejection]:
    named = {req_id for t in tasks for req_id in t.requirements}
    listed = {ac_id for t in tasks for ac_id in t.acceptance_criteria}
    rejections: list[PlanRejection] = []
    for r in spec.requirements:
        if r.deprecated:
            continue
        if r.id not in named:
            rejections.append(
                PlanRejection(
                    rule=PlanRule.uncovered,
                    subject=r.id,
                    message=f"requirement {r.id!r} appears in no task",
                )
            )
        rejections.extend(
            PlanRejection(
                rule=PlanRule.uncovered,
                subject=ac.id,
                message=f"acceptance criterion {ac.id!r} appears in no task",
            )
            for ac in r.acceptance_criteria
            if ac.id not in listed
        )
    return rejections


def check_plan(tasks: Sequence[PlannedTask], spec: SpecSet) -> list[PlanRejection]:
    """Return every rejection of the plan, in a fixed rule order.

    Within a rule the rejections follow the order of the reply, except `uncovered`, whose
    subjects come in the spec set's order.
    """
    return [
        *_duplicate_task_id(tasks),
        *_unknown_dependency(tasks),
        *_cycle(tasks),
        *_unknown_requirement(tasks, spec),
        *_deprecated_requirement(tasks, spec),
        *_unknown_criterion(tasks, spec),
        *_undeclared_component(tasks, spec),
        *_uncovered(tasks, spec),
    ]
