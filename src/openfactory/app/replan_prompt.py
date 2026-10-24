"""Replan prompt: the one text a replan's planner call receives.

See docs/spec/phase1-spec.md ("Spec diff and impact analysis": "Step 5: replan"; "Task
contract": "Plan checks"). The prompt is the planner prompt plus, as its `extra` sections:
fixed replan instructions, the `added` requirement ids, the contracts of the impacted and
downstream tasks, the files, tests, obsolete criteria and new work of the `ImpactComputed`,
and the untouched tasks that are not `invalidated`, each with its id, objective, state,
requirements and acceptance criteria. With rejections it is the retry prompt, as for a
first plan. Its hash is `planner_prompt.context_hash`.
"""

from collections.abc import Sequence

from openfactory.app.planner_prompt import build_planner_prompt
from openfactory.domain.models import SpecSet
from openfactory.domain.payloads import ImpactComputedPayload
from openfactory.domain.plan_checks import PlanRejection
from openfactory.domain.plans import Task
from openfactory.domain.policy import Policy
from openfactory.domain.states import TaskState

_REPLAN_INSTRUCTIONS = """\
## Replan instructions
This is a replan: the spec changed after the plan was approved. These replan instructions \
take precedence over the rules above.
- Plan tasks only for the impacted work below and the added requirements listed below.
- A requirement or acceptance criterion already covered by an untouched task below that is \
not invalidated needs no new task.
- When no new task is needed, reply {"tasks": []}.
- A new task's task_id must not be the id of any task shown in this prompt.
- A new task may depend on an untouched task below that is neither abandoned nor \
invalidated, as well as on the new tasks in your reply.
- The new tasks rewrite or delete the obsolete code and tests listed below, and their \
allowed_paths cover those files."""


_NONE = "(none)"


def _section(heading: str, lines: Sequence[str], separator: str = "\n") -> str:
    return separator.join([f"## {heading}", *(lines or [_NONE])])


def _contracts(heading: str, ids: Sequence[str], by_id: dict[str, Task]) -> str:
    contracts = [by_id[i].contract.model_dump_json(indent=2) for i in sorted(ids) if i in by_id]
    return _section(heading, contracts, "\n\n")


def _untouched_text(task: Task) -> str:
    return "\n".join(
        [
            f"### {task.id}",
            f"objective: {task.contract.objective}",
            f"state: {task.state.value}",
            f"requirements: {', '.join(task.contract.requirements)}",
            f"acceptance criteria: {', '.join(task.contract.acceptance_criteria)}",
        ]
    )


def untouched_tasks(plan_tasks: Sequence[Task], impact: ImpactComputedPayload) -> list[Task]:
    """The plan's tasks that are neither impacted nor downstream, in every state, by id."""
    touched = {*impact.tasks, *impact.downstream}
    return sorted((t for t in plan_tasks if t.id not in touched), key=lambda t: t.id)


def build_replan_prompt(
    spec: SpecSet,
    policy: Policy,
    tracked_files: Sequence[str],
    impact: ImpactComputedPayload,
    plan_tasks: Sequence[Task],
    rejections: Sequence[PlanRejection] = (),
) -> str:
    """The first replan prompt, or with `rejections` the retry prompt."""
    by_id = {t.id: t for t in plan_tasks}
    added = sorted(r.id for r in impact.requirements if r.change == "added")
    obsolete = sorted({ac for r in impact.requirements for ac in r.obsolete_criteria})
    new_work = [f"{r.id}: {work}" for r in impact.requirements for work in r.new_work]
    untouched = [t for t in untouched_tasks(plan_tasks, impact) if t.state != TaskState.invalidated]
    extra = [
        _REPLAN_INSTRUCTIONS,
        _section("Added requirements", [f"- {i}" for i in added]),
        _contracts("Impacted tasks", impact.tasks, by_id),
        _contracts("Downstream tasks", impact.downstream, by_id),
        _section("Impacted files", [f"- {f}" for f in sorted(set(impact.files))]),
        _section("Impacted tests", [f"- {t}" for t in sorted(set(impact.tests))]),
        _section("Obsolete criteria", [f"- {ac}" for ac in obsolete]),
        _section("New work", [f"- {w}" for w in new_work]),
        _section("Untouched tasks", [_untouched_text(t) for t in untouched], "\n\n"),
    ]
    return build_planner_prompt(spec, policy, tracked_files, rejections, extra=extra)
