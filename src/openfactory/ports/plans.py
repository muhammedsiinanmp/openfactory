"""Plans port: read-only view of the plan and task projections.

See docs/spec/phase1-spec.md ("Domain model and storage", "Ids"; "Task contract",
"Planning"; "Spec input format", "Validation rules"; "Execution", "Base and branches"),
ADR-012 and ADR-014.
"""

from typing import Protocol

from openfactory.domain.plans import CommitRef, GateResultRef, PlanRef, Task


class Plans(Protocol):
    def current_draft(self) -> PlanRef | None:
        """The draft plan, or None. At most one draft exists at a time."""
        ...

    def approved(self) -> PlanRef | None:
        """The approved plan with the highest number in its id, or None."""
        ...

    def next_id(self) -> str:
        """The id after the highest one in use, superseded plans included; `plan_01` when
        there is none."""
        ...

    def tasks(self, plan_id: str) -> list[Task]:
        """The tasks of a plan in ascending id order, each with its dependencies.

        Empty for a superseded plan and for a plan that does not exist.
        """
        ...

    def live_tasks_referencing(self, requirement_id: str) -> list[str]:
        """The ids, in ascending order, of the tasks that list the requirement in their
        contract and are in neither state `abandoned` nor `invalidated`."""
        ...

    def task_ids_in_use(self) -> list[str]:
        """The ids, in ascending order, of the tasks in the `tasks` projection outside the
        draft being replaced: the tasks of every plan that is not `draft`."""
        ...

    def latest_commit(self, plan_id: str) -> CommitRef | None:
        """The commit with the highest run id, compared by number, among the tasks of the
        plan, with its task id; None when the plan has no commit."""
        ...

    def last_gate_result(self, task_id: str) -> GateResultRef | None:
        """The last gate, in the task's `required_gates` order, evaluated for the task's
        latest implementer run that has a gate result; None when there is none."""
        ...
