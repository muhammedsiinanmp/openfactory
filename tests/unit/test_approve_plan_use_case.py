"""TASK-035: approve plan use case.

Each test names the acceptance criterion it covers (AC1..AC5 in
docs/tasks/TASK-035-approve-plan-use-case.md). The use case is driven through in-memory
fakes of SpecVersions, Plans and EventRecorder; no filesystem or database is used.
"""

import ast
import inspect
from pathlib import Path

from openfactory.app.approve_plan import ApprovePlanOutcome, approve_plan
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType, StoredEvent
from openfactory.domain.payloads import PlanApprovedPayload, TaskStateChangedPayload
from openfactory.domain.plans import PlanRef, Task
from openfactory.domain.spec_versions import SpecVersionRef
from openfactory.domain.states import TaskState

APP_DIR = Path(__file__).resolve().parents[2] / "src" / "openfactory" / "app"


def _task(task_id: str, depends_on: list[str]) -> Task:
    return Task(
        id=task_id,
        plan_id="plan_03",
        state=TaskState.pending,
        attempt=0,
        contract=TaskContract(
            task_id=task_id,
            objective=f"Do {task_id}.",
            requirements=["REQ-AUTH-001"],
            acceptance_criteria=["AC-AUTH-001-1"],
            depends_on=depends_on,
            components=["auth"],
            role="implementer",
            allowed_paths=["src/"],
            forbidden_paths=[],
            required_gates=["path_check", "ruff", "pytest", "gitleaks", "review"],
            limits=Limits(max_runtime_s=600, max_attempts=3, max_cost_usd=1.0),
        ),
        depends_on=depends_on,
    )


# Deliberately not in ascending order: the use case must sort the tasks it makes ready.
SAMPLE_TASKS = [
    _task("DB-001", []),
    _task("AUTH-002", ["AUTH-001"]),
    _task("AUTH-010", []),
    _task("AUTH-001", []),
]


class FakeVersions:
    def __init__(self, approved: SpecVersionRef | None) -> None:
        self.approved = approved

    def latest_approved(self) -> SpecVersionRef | None:
        return self.approved

    def current_draft(self) -> SpecVersionRef | None:
        raise AssertionError("approve_plan must not read the spec draft")

    def next_id(self) -> str:
        raise AssertionError("approve_plan must not ask for a new spec version id")

    def spec_set(self, version_id: str):  # noqa: ANN201
        raise AssertionError("approve_plan must not read a spec set")


class FakePlans:
    def __init__(self, draft: PlanRef | None, tasks: list[Task]) -> None:
        self.draft = draft
        self._tasks = tasks
        self.tasks_asked: list[str] = []

    def current_draft(self) -> PlanRef | None:
        return self.draft

    def approved(self) -> PlanRef | None:
        return None

    def next_id(self) -> str:
        return "plan_04"

    def tasks(self, plan_id: str) -> list[Task]:
        self.tasks_asked.append(plan_id)
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


def _sv(version_id: str) -> SpecVersionRef:
    return SpecVersionRef(id=version_id, hash="a" * 64)


def _run(draft: PlanRef | None, approved: SpecVersionRef | None, tasks: list[Task] = SAMPLE_TASKS):
    versions, plans, recorder = FakeVersions(approved), FakePlans(draft, tasks), FakeRecorder()
    result = approve_plan(versions, plans, recorder)
    return result, plans, recorder


def _approve_sample():
    return _run(PlanRef(id="plan_03", spec_version="sv_02"), _sv("sv_02"))


def test_ac1_no_draft_is_refused_and_records_nothing() -> None:
    result, _, recorder = _run(None, _sv("sv_01"))

    assert result.outcome is ApprovePlanOutcome.no_draft
    assert result.plan_id is None
    assert result.spec_version is None
    assert result.ready == []
    assert recorder.events == []


def test_ac2_draft_for_an_older_spec_version_is_stale_and_records_nothing() -> None:
    result, _, recorder = _run(
        PlanRef(id="plan_02", spec_version="sv_01"),
        _sv("sv_02"),
        [_task("AUTH-001", [])],
    )

    assert result.outcome is ApprovePlanOutcome.stale_draft
    assert result.plan_id == "plan_02"
    assert result.spec_version == "sv_01"
    assert result.ready == []
    assert recorder.events == []


def test_ac3_plan_approved_is_recorded_first_by_a_human() -> None:
    result, _, recorder = _approve_sample()

    first = recorder.events[0]
    assert first.type is EventType.PlanApproved
    assert first.stream == "plan:plan_03"
    assert first.actor == "human"
    assert first.causation_id is None
    assert first.payload == {"plan_id": "plan_03"}
    assert PlanApprovedPayload.model_validate(first.payload).plan_id == "plan_03"
    assert result.outcome is ApprovePlanOutcome.approved
    assert result.plan_id == "plan_03"
    assert result.spec_version == "sv_02"


def test_ac4_tasks_without_dependencies_become_ready_in_ascending_order() -> None:
    result, _, recorder = _approve_sample()

    events = recorder.events
    assert [e.type for e in events] == [
        EventType.PlanApproved,
        EventType.TaskStateChanged,
        EventType.TaskStateChanged,
        EventType.TaskStateChanged,
    ]
    assert [e.stream for e in events[1:]] == ["task:AUTH-001", "task:AUTH-010", "task:DB-001"]
    assert result.ready == ["AUTH-001", "AUTH-010", "DB-001"]


def test_ac4_each_task_state_changed_points_at_plan_approved() -> None:
    _, _, recorder = _approve_sample()

    approved, *changes = recorder.events
    for event in changes:
        assert event.actor == "orchestrator"
        assert event.causation_id == approved.event_id


def test_ac4_task_state_changed_payload_is_pending_to_ready_with_key_from() -> None:
    _, _, recorder = _approve_sample()

    for event in recorder.events[1:]:
        task_id = event.stream.removeprefix("task:")
        assert event.payload == {
            "task_id": task_id,
            "from": "pending",
            "to": "ready",
            "reason": None,
        }
        assert "from_" not in event.payload
        TaskStateChangedPayload.model_validate(event.payload)


def test_ac5_takes_exactly_the_three_ports() -> None:
    params = inspect.signature(approve_plan).parameters
    assert list(params) == ["versions", "plans", "recorder"]


def test_ac5_module_imports_no_adapter_and_no_cli() -> None:
    tree = ast.parse((APP_DIR / "approve_plan.py").read_text())
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not [m for m in imported if m.startswith(("openfactory.adapters", "openfactory.cli"))]


def test_ac5_tasks_are_read_for_the_draft_plan_only() -> None:
    _, plans, _ = _approve_sample()

    assert plans.tasks_asked == ["plan_03"]
