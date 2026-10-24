"""TASK-104: approve plan after a replan (AC1..AC6 in docs/tasks/TASK-104-approve-plan-replan.md).

Driven through in-memory fakes of SpecVersions, Plans, EventRecorder and EventStore.
"""

import pytest

from openfactory.app.approve_plan import ApprovePlanOutcome, approve_plan
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType, StoredEvent
from openfactory.domain.plans import PlanRef, Task
from openfactory.domain.spec_versions import SpecVersionRef
from openfactory.domain.states import TRANSITIONS, TaskState

S = TaskState
APPROVED = PlanRef(id="plan_01", spec_version="sv_01")
DRAFT = PlanRef(id="plan_02", spec_version="sv_02")


def _task(task_id: str, plan_id: str, state: TaskState, depends_on: list[str]) -> Task:
    return Task(
        id=task_id,
        plan_id=plan_id,
        state=state,
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


def _approved_tasks(**states: TaskState) -> list[Task]:
    """The fixture of the task record's Plan step 3; `states` overrides by id (AUTH_002=...)."""
    spec = {
        "AUTH-001": (S.passed, []),
        "AUTH-002": (S.passed, []),
        "AUTH-003": (S.pending, ["AUTH-002"]),
        "AUTH-004": (S.abandoned, []),
        "AUTH-005": (S.pending, ["AUTH-006"]),
        "AUTH-006": (S.escalated, []),
        "AUTH-010": (S.passed, []),
    }
    out = []
    for task_id, (state, deps) in spec.items():
        state = states.get(task_id.replace("-", "_"), state)
        out.append(_task(task_id, "plan_01", state, deps))
    return out


def _draft_tasks() -> list[Task]:
    return [
        _task("AUTH-009", "plan_02", S.pending, []),
        _task("AUTH-008", "plan_02", S.pending, ["AUTH-007"]),
        _task("AUTH-007", "plan_02", S.pending, ["AUTH-001"]),
    ]


def _impact(seq: int, from_version: str, tasks: list[str], downstream: list[str]) -> StoredEvent:
    event = Event.new(
        stream="spec:sv_02",
        type=EventType.ImpactComputed,
        payload={
            "from_version": from_version,
            "to_version": "sv_02",
            "run_id": None,
            "requirements": [],
            "adrs": [],
            "tasks": tasks,
            "downstream": downstream,
            "files": [],
            "tests": [],
        },
        actor="orchestrator",
    )
    return StoredEvent(**event.model_dump(), seq=seq)


def _plan_created(seq: int) -> StoredEvent:
    event = Event.new(
        stream="plan:plan_02",
        type=EventType.PlanCreated,
        payload={"plan_id": "plan_02", "spec_version": "sv_02", "tasks": []},
        actor="orchestrator",
    )
    return StoredEvent(**event.model_dump(), seq=seq)


def _impact_events(extra_downstream: list[str] | None = None) -> list[StoredEvent]:
    return [
        _impact(2, "sv_01", ["AUTH-001"], []),  # older matching impact: not the latest
        _impact(4, "sv_01", ["AUTH-002", "AUTH-004"], ["AUTH-003", *(extra_downstream or [])]),
        _impact(5, "sv_00", ["AUTH-001"], []),  # higher seq but another from_version
        _plan_created(6),
        _impact(8, "sv_01", ["AUTH-001"], []),  # recorded after the PlanCreated
    ]


class FakeVersions:
    def __init__(self, latest: str) -> None:
        self.latest = latest

    def latest_approved(self) -> SpecVersionRef:
        return SpecVersionRef(id=self.latest, hash="a" * 64)

    def current_draft(self) -> SpecVersionRef | None:
        raise AssertionError("approve_plan must not read the spec draft")

    def next_id(self) -> str:
        raise AssertionError("not used")

    def spec_set(self, version_id: str):  # noqa: ANN201
        raise AssertionError("not used")


class FakePlans:
    def __init__(
        self, draft: PlanRef | None, approved: PlanRef | None, tasks: dict[str, list[Task]]
    ) -> None:
        self.draft = draft
        self.approved_plan = approved
        self._tasks = tasks

    def current_draft(self) -> PlanRef | None:
        return self.draft

    def approved(self) -> PlanRef | None:
        return self.approved_plan

    def next_id(self) -> str:
        raise AssertionError("not used")

    def tasks(self, plan_id: str) -> list[Task]:
        return list(self._tasks.get(plan_id, []))

    def live_tasks_referencing(self, requirement_id: str) -> list[str]:
        return []


class FakeRecorder:
    def __init__(self) -> None:
        self.events: list[StoredEvent] = []

    def record(self, event: Event) -> StoredEvent:
        stored = StoredEvent(**event.model_dump(), seq=len(self.events) + 1)
        self.events.append(stored)
        return stored


class FakeEvents:
    def __init__(self, events: list[StoredEvent]) -> None:
        self.events = events
        self.reads: list[str | None] = []
        self.appended = 0

    def append(self, event: Event) -> StoredEvent:
        self.appended += 1
        raise AssertionError("approve_plan must not append through the EventStore")

    def read(self, stream: str | None = None) -> list[StoredEvent]:
        self.reads.append(stream)
        return [e for e in self.events if stream is None or e.stream == stream]


def _run(
    *,
    draft: PlanRef | None = DRAFT,
    approved: PlanRef | None = APPROVED,
    latest: str = "sv_02",
    approved_tasks: list[Task] | None = None,
    events: list[StoredEvent] | None = None,
    recorder: FakeRecorder | None = None,
):
    plans = FakePlans(
        draft,
        approved,
        {
            "plan_01": _approved_tasks() if approved_tasks is None else approved_tasks,
            "plan_02": _draft_tasks(),
        },
    )
    store = FakeEvents(_impact_events() if events is None else events)
    recorder = recorder or FakeRecorder()
    result = approve_plan(FakeVersions(latest), plans, recorder, events=store)
    return result, recorder, store


def _changes(recorder: FakeRecorder) -> list[tuple[str, str, str]]:
    return [
        (e.stream.removeprefix("task:"), e.payload["from"], e.payload["to"])
        for e in recorder.events
        if e.type is EventType.TaskStateChanged
    ]


# AC1


def test_task104_ac1_no_draft_is_refused_and_records_nothing() -> None:
    result, recorder, _ = _run(draft=None)

    assert result.outcome is ApprovePlanOutcome.no_draft
    assert recorder.events == []


@pytest.mark.parametrize("approved_plan_exists", [True, False])
def test_task104_ac1_stale_draft_flags_whether_an_approved_plan_exists(
    approved_plan_exists: bool,
) -> None:
    result, recorder, _ = _run(
        draft=PlanRef(id="plan_02", spec_version="sv_01"),
        approved=APPROVED if approved_plan_exists else None,
        latest="sv_03",
    )

    assert result.outcome is ApprovePlanOutcome.stale_draft
    assert result.plan_id == "plan_02"
    assert result.spec_version == "sv_01"
    assert result.approved_plan_exists is approved_plan_exists
    assert recorder.events == []


def test_task104_ac1_stale_check_comes_before_the_busy_check() -> None:
    result, recorder, _ = _run(
        draft=PlanRef(id="plan_02", spec_version="sv_01"),
        latest="sv_03",
        approved_tasks=_approved_tasks(AUTH_002=S.running),
    )

    assert result.outcome is ApprovePlanOutcome.stale_draft
    assert recorder.events == []


# AC2


def test_task104_ac2_busy_task_names_the_lowest_id_as_strings() -> None:
    tasks = _approved_tasks(AUTH_002=S.running, AUTH_010=S.gating)
    result, recorder, _ = _run(
        approved_tasks=tasks, events=_impact_events(extra_downstream=["AUTH-010"])
    )

    assert result.outcome is ApprovePlanOutcome.task_busy
    assert result.task_id == "AUTH-002"
    assert result.state is S.running
    assert recorder.events == []


def test_task104_ac2_busy_downstream_task_is_refused() -> None:
    result, recorder, _ = _run(approved_tasks=_approved_tasks(AUTH_003=S.gating))

    assert result.outcome is ApprovePlanOutcome.task_busy
    assert result.task_id == "AUTH-003"
    assert result.state is S.gating
    assert recorder.events == []


def test_task104_ac2_running_untouched_task_does_not_refuse() -> None:
    result, _, _ = _run(approved_tasks=_approved_tasks(AUTH_001=S.running))

    assert result.outcome is ApprovePlanOutcome.approved


# AC3


def test_task104_ac3_uses_the_latest_matching_impact_before_the_plan_created() -> None:
    result, recorder, store = _run()

    assert result.invalidated == ["AUTH-002", "AUTH-003"]
    assert store.appended == 0
    assert set(store.reads) <= {"plan:plan_02", "spec:sv_02"}
    assert "AUTH-001" not in [c[0] for c in _changes(recorder)]


def test_task104_ac3_first_plan_never_reads_the_event_store() -> None:
    _, recorder, store = _run(approved=None, approved_tasks=[])

    assert store.reads == []
    assert _changes(recorder) == [
        ("AUTH-009", "pending", "ready"),
    ]


# AC4


def test_task104_ac4_plan_approved_then_invalidations_in_ascending_order() -> None:
    result, recorder, _ = _run()

    approved, *rest = recorder.events
    assert approved.type is EventType.PlanApproved
    assert approved.stream == "plan:plan_02"
    assert approved.actor == "human"
    assert approved.causation_id is None
    assert result.outcome is ApprovePlanOutcome.approved
    invalidations = rest[:2]
    assert [e.stream for e in invalidations] == ["task:AUTH-002", "task:AUTH-003"]
    for e in invalidations:
        assert e.type is EventType.TaskStateChanged
        assert e.actor == "orchestrator"
        assert e.causation_id == approved.event_id
        assert e.payload["to"] == "invalidated"
        assert e.payload["reason"] == "spec change sv_02"
    assert [e.payload["from"] for e in invalidations] == ["passed", "pending"]
    assert result.invalidated == ["AUTH-002", "AUTH-003"]


def test_task104_ac4_abandoned_and_untouched_tasks_get_no_event() -> None:
    _, recorder, _ = _run()

    touched = {c[0] for c in _changes(recorder)}
    assert "AUTH-004" not in touched  # abandoned and impacted
    assert not touched & {"AUTH-001", "AUTH-005", "AUTH-006", "AUTH-010"}


# AC5


def test_task104_ac5_pending_tasks_with_passed_dependencies_become_ready_after_invalidations() -> (
    None
):
    result, recorder, _ = _run()

    assert _changes(recorder) == [
        ("AUTH-002", "passed", "invalidated"),
        ("AUTH-003", "pending", "invalidated"),
        ("AUTH-007", "pending", "ready"),
        ("AUTH-009", "pending", "ready"),
    ]
    readies = recorder.events[-2:]
    approved = recorder.events[0]
    for e in readies:
        assert e.payload["reason"] is None
        assert e.causation_id == approved.event_id
    assert result.ready == ["AUTH-007", "AUTH-009"]


def test_task104_ac5_blocked_and_invalidated_tasks_stay_pending() -> None:
    result, _, _ = _run()

    # AUTH-008 waits on the new AUTH-007, AUTH-005 on an escalated task, AUTH-003 is invalidated.
    assert not set(result.ready) & {"AUTH-008", "AUTH-005", "AUTH-003"}


# AC6


@pytest.mark.parametrize(("source", "target"), [(S.passed, S.invalidated), (S.pending, S.ready)])
def test_task104_ac6_a_transition_missing_from_transitions_raises_before_any_record(
    monkeypatch: pytest.MonkeyPatch, source: TaskState, target: TaskState
) -> None:
    trimmed = dict(TRANSITIONS)
    trimmed[source] = TRANSITIONS[source] - {target}
    monkeypatch.setattr("openfactory.app.approve_plan.TRANSITIONS", trimmed)

    recorder = FakeRecorder()
    with pytest.raises(ValueError):
        _run(recorder=recorder)

    assert recorder.events == []
