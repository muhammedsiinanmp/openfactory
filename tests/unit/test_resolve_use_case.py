"""TASK-075: resolve use case (AC1..AC3, AC5, AC6 in docs/tasks/TASK-075-resolve-use-case.md).

Driven through in-memory fakes of Plans and EventRecorder; no filesystem or database.
"""

import ast
import inspect
from pathlib import Path

import pytest

from openfactory.app.resolve import ResolveRefusal, resolve_task
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType, StoredEvent
from openfactory.domain.payloads import TaskResolvedPayload, TaskStateChangedPayload
from openfactory.domain.plans import PlanRef, Task
from openfactory.domain.states import TRANSITIONS, TaskState

APP_DIR = Path(__file__).resolve().parents[2] / "src" / "openfactory" / "app"


def _task(task_id: str, state: TaskState) -> Task:
    return Task(
        id=task_id,
        plan_id="plan_01",
        state=state,
        attempt=2,
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
            limits=Limits(max_runtime_s=600, max_attempts=3, max_cost_usd=1.0),
        ),
        depends_on=[],
    )


class FakePlans:
    def __init__(self, approved: PlanRef | None, tasks: list[Task]) -> None:
        self._approved = approved
        self._tasks = tasks

    def current_draft(self) -> PlanRef | None:
        return PlanRef(id="plan_02", spec_version="sv_01")

    def approved(self) -> PlanRef | None:
        return self._approved

    def next_id(self) -> str:
        raise AssertionError("resolve_task must not ask for a plan id")

    def tasks(self, plan_id: str) -> list[Task]:
        return list(self._tasks)

    def live_tasks_referencing(self, requirement_id: str) -> list[str]:
        return []


class FakeRecorder:
    def __init__(self) -> None:
        self.events: list[StoredEvent] = []

    def record(self, event: Event) -> StoredEvent:
        stored = StoredEvent(**event.model_dump(), seq=len(self.events) + 1)
        self.events.append(stored)
        return stored


APPROVED = PlanRef(id="plan_01", spec_version="sv_01")


def _resolve(task_id, decision, *, approved=APPROVED, state=TaskState.escalated):
    plans = FakePlans(approved, [_task("AUTH-001", state)])
    recorder = FakeRecorder()
    result = resolve_task(task_id, decision, plans=plans, recorder=recorder)
    return result, recorder


def test_ac1_no_approved_plan_is_refused_even_for_a_task_in_a_draft() -> None:
    result, recorder = _resolve("AUTH-001", "retry", approved=None)

    assert result.refusal is ResolveRefusal.no_approved_plan
    assert result.state is None
    assert recorder.events == []


def test_ac1_unknown_task_is_refused() -> None:
    result, recorder = _resolve("NOPE-001", "abandon")

    assert result.refusal is ResolveRefusal.unknown_task
    assert result.state is None
    assert recorder.events == []


@pytest.mark.parametrize(
    "state", [TaskState.failed, TaskState.ready, TaskState.passed, TaskState.abandoned]
)
def test_ac1_a_task_not_escalated_is_refused_with_its_state(state: TaskState) -> None:
    result, recorder = _resolve("AUTH-001", "retry", state=state)

    assert result.refusal is ResolveRefusal.not_escalated
    assert result.detail == state.value
    assert result.state is None
    assert recorder.events == []


def test_ac2_retry_records_task_resolved_then_ready() -> None:
    result, recorder = _resolve("AUTH-001", "retry")

    resolved, changed = recorder.events
    assert resolved.type is EventType.TaskResolved
    assert resolved.stream == "task:AUTH-001"
    assert resolved.actor == "human"
    assert resolved.causation_id is None
    assert resolved.payload == {"task_id": "AUTH-001", "decision": "retry"}
    TaskResolvedPayload.model_validate(resolved.payload)

    assert changed.type is EventType.TaskStateChanged
    assert changed.stream == "task:AUTH-001"
    assert changed.actor == "orchestrator"
    assert changed.causation_id == resolved.event_id
    assert changed.payload == {
        "task_id": "AUTH-001",
        "from": "escalated",
        "to": "ready",
        "reason": None,
    }
    TaskStateChangedPayload.model_validate(changed.payload)
    assert result.refusal is None
    assert result.state is TaskState.ready


def test_ac3_abandon_records_task_resolved_then_abandoned() -> None:
    result, recorder = _resolve("AUTH-001", "abandon")

    resolved, changed = recorder.events
    assert resolved.type is EventType.TaskResolved
    assert resolved.actor == "human"
    assert resolved.causation_id is None
    assert resolved.payload == {"task_id": "AUTH-001", "decision": "abandon"}
    assert changed.type is EventType.TaskStateChanged
    assert changed.actor == "orchestrator"
    assert changed.causation_id == resolved.event_id
    assert changed.payload == {
        "task_id": "AUTH-001",
        "from": "escalated",
        "to": "abandoned",
        "reason": None,
    }
    assert result.state is TaskState.abandoned


def test_ac5_a_transition_missing_from_transitions_raises_before_any_record(monkeypatch) -> None:
    trimmed = dict(TRANSITIONS)
    trimmed[TaskState.escalated] = TRANSITIONS[TaskState.escalated] - {TaskState.ready}
    monkeypatch.setattr("openfactory.app.resolve.TRANSITIONS", trimmed)
    recorder = FakeRecorder()
    plans = FakePlans(APPROVED, [_task("AUTH-001", TaskState.escalated)])

    with pytest.raises(ValueError):
        resolve_task("AUTH-001", "retry", plans=plans, recorder=recorder)

    assert recorder.events == []


def test_ac6_takes_only_plans_and_recorder() -> None:
    params = inspect.signature(resolve_task).parameters
    assert list(params) == ["task_id", "decision", "plans", "recorder"]


def test_ac6_module_imports_only_domain_ports_pydantic_and_stdlib() -> None:
    tree = ast.parse((APP_DIR / "resolve.py").read_text())
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not [
        m
        for m in imported
        if m.startswith(("openfactory.adapters", "openfactory.cli", "openfactory.app"))
    ]
