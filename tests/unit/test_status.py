"""TASK-077: status use case (docs/tasks/TASK-077-status.md), driven through a fake Plans."""

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from openfactory.app.status import StatusRefusal, plan_status
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.plans import GateResultRef, PlanRef, Task
from openfactory.domain.states import TaskState

APP_DIR = Path(__file__).resolve().parents[2] / "src" / "openfactory" / "app"


def _task(task_id: str, state: TaskState, attempt: int, max_attempts: int = 3) -> Task:
    return Task(
        id=task_id,
        plan_id="plan_01",
        state=state,
        attempt=attempt,
        contract=TaskContract(
            task_id=task_id,
            objective=f"Do {task_id}.",
            requirements=["REQ-AUTH-001"],
            acceptance_criteria=["AC-AUTH-001-1"],
            depends_on=[],
            components=["auth"],
            role="implementer",
            allowed_paths=["src/"],
            forbidden_paths=[],
            required_gates=["path_check", "ruff", "pytest", "gitleaks", "review"],
            limits=Limits(max_runtime_s=600, max_attempts=max_attempts, max_cost_usd=1.0),
        ),
        depends_on=[],
    )


class FakePlans:
    """Records every call so a test can assert only reads happen."""

    def __init__(
        self,
        approved: PlanRef | None,
        tasks: list[Task],
        gates: dict[str, GateResultRef] | None = None,
    ) -> None:
        self._approved = approved
        self._tasks = tasks
        self._gates = gates or {}
        self.calls: list[str] = []

    def current_draft(self) -> PlanRef | None:
        self.calls.append("current_draft")
        return None

    def approved(self) -> PlanRef | None:
        self.calls.append("approved")
        return self._approved

    def next_id(self) -> str:
        raise AssertionError("plan_status must not ask for a plan id")

    def tasks(self, plan_id: str) -> list[Task]:
        self.calls.append("tasks")
        return list(self._tasks)

    def live_tasks_referencing(self, requirement_id: str) -> list[str]:
        raise AssertionError("not a status read")

    def latest_commit(self, plan_id: str):
        raise AssertionError("not a status read")

    def last_gate_result(self, task_id: str) -> GateResultRef | None:
        self.calls.append(f"last_gate_result:{task_id}")
        return self._gates.get(task_id)


APPROVED = PlanRef(id="plan_01", spec_version="sv_01")


def test_no_approved_plan_is_refused_without_reading_tasks() -> None:
    plans = FakePlans(None, [_task("AUTH-001", TaskState.ready, 0)])

    report = plan_status(plans=plans)

    assert report.refusal is StatusRefusal.no_approved_plan
    assert report.tasks == []
    assert "tasks" not in plans.calls


def test_tasks_are_sorted_by_id_as_strings_with_projected_fields_and_gate() -> None:
    gate = GateResultRef(gate="ruff", passed=False)
    plans = FakePlans(
        APPROVED,
        [
            _task("AUTH-010", TaskState.pending, 0, 4),
            _task("AUTH-002", TaskState.failed, 2, 2),
            _task("AUTH-001", TaskState.ready, 1, 3),
        ],
        gates={"AUTH-002": gate},
    )

    report = plan_status(plans=plans)

    assert report.refusal is None
    assert [t.task_id for t in report.tasks] == ["AUTH-001", "AUTH-002", "AUTH-010"]
    by_id = {t.task_id: t for t in report.tasks}
    assert (by_id["AUTH-001"].state, by_id["AUTH-001"].attempt, by_id["AUTH-001"].max_attempts) == (
        TaskState.ready,
        1,
        3,
    )
    assert by_id["AUTH-002"].gate == gate
    assert by_id["AUTH-002"].max_attempts == 2
    assert by_id["AUTH-001"].gate is None
    assert by_id["AUTH-010"].max_attempts == 4


def test_report_is_frozen() -> None:
    report = plan_status(plans=FakePlans(APPROVED, [_task("AUTH-001", TaskState.ready, 0)]))

    with pytest.raises(ValidationError):
        report.refusal = StatusRefusal.no_approved_plan  # type: ignore[misc]
    with pytest.raises(ValidationError):
        report.tasks[0].attempt = 5  # type: ignore[misc]


def test_status_module_takes_no_recorder_and_imports_only_domain_and_ports() -> None:
    import inspect

    assert set(inspect.signature(plan_status).parameters) == {"plans"}
    tree = ast.parse((APP_DIR / "status.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("openfactory")
        ):
            assert node.module.split(".")[1] in {"domain", "ports"}, node.module
