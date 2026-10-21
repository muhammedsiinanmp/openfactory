"""TASK-054: run use case, the Restart repair (AC1..AC6 in the task record).

`repair_plan` is driven through in-memory fakes of the Plans, Runs, WorkspaceManager and
EventRecorder ports.
"""

import ast
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from openfactory.app.run import RepairResult, repair_plan
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType, StoredEvent
from openfactory.domain.plans import CommitRef, PlanRef, Task
from openfactory.domain.policy import BASELINE_FORBIDDEN_PATHS
from openfactory.domain.states import TaskState
from openfactory.ports.git_provider import GitError

APP_DIR = Path(__file__).resolve().parents[2] / "src" / "openfactory" / "app"
BOOM = "fatal: boom\nhint: more"
PLAN = PlanRef(id="plan_01", spec_version="sv_01")
S = TaskState


def _task(task_id: str, state: TaskState, depends_on: list[str] | None = None) -> Task:
    deps = depends_on or []
    return Task(
        id=task_id,
        plan_id="plan_01",
        state=state,
        attempt=0,
        contract=TaskContract(
            task_id=task_id,
            objective="Add the login endpoint.",
            requirements=["REQ-AUTH-001"],
            acceptance_criteria=["AC-AUTH-001-1"],
            depends_on=deps,
            components=["auth"],
            role="implementer",
            allowed_paths=["app/auth/**"],
            forbidden_paths=list(BASELINE_FORBIDDEN_PATHS),
            required_gates=["path_check", "ruff", "pytest", "gitleaks", "review"],
            limits=Limits(max_runtime_s=600, max_attempts=2, max_cost_usd=1.0),
        ),
        depends_on=deps,
    )


class FakeRecorder:
    def __init__(self) -> None:
        self.events: list[StoredEvent] = []
        self.log: list[str] = []

    def record(self, event: Event) -> StoredEvent:
        self.log.append("record")
        stored = StoredEvent(**event.model_dump(), seq=len(self.events) + 1)
        self.events.append(stored)
        return stored


class FakeEvents:
    """Read-only EventStore: the seeded events of a stream, then the recorder's."""

    def __init__(self, recorder: FakeRecorder, seeded: tuple[StoredEvent, ...] = ()) -> None:
        self.recorder = recorder
        self.seeded = list(seeded)
        self.reads: list[str | None] = []

    def append(self, event: Event) -> StoredEvent:
        raise AssertionError("repair must not append to the EventStore")

    def read(self, stream: str | None = None) -> list[StoredEvent]:
        self.reads.append(stream)
        return [
            e for e in (*self.seeded, *self.recorder.events) if stream is None or e.stream == stream
        ]


def _seed(task_id: str, type: EventType, payload: dict[str, Any]) -> StoredEvent:
    event = Event.new(stream=f"task:{task_id}", type=type, payload=payload, actor="orchestrator")
    return StoredEvent(**event.model_dump(), seq=1000)


def _seed_move(task_id: str, frm: str, to: str, reason: str | None = None) -> StoredEvent:
    payload = {"task_id": task_id, "from": frm, "to": to, "reason": reason}
    return _seed(task_id, EventType.TaskStateChanged, payload)


def _seed_gate(task_id: str, gate: str, passed: bool) -> StoredEvent:
    payload = {
        "run_id": "run_0001",
        "task_id": task_id,
        "gate": gate,
        "passed": passed,
        "output_path": None,
    }
    return _seed(task_id, EventType.GateEvaluated, payload)


class FakeWorkspace:
    def __init__(self, recorder: FakeRecorder, fail: bool = False) -> None:
        self.recorder = recorder
        self.fail = fail
        self.calls: list[tuple[str, str]] = []
        self.events_at_call: list[int] = []

    def create(self, task_id: str, base: str) -> Any:
        raise AssertionError("repair must not create a worktree")

    def remove(self, task_id: str) -> None:
        self.calls.append(("remove", task_id))

    def remove_worktree(self, task_id: str) -> None:
        self.calls.append(("remove_worktree", task_id))
        self.events_at_call.append(len(self.recorder.events))
        if self.fail:
            raise GitError(BOOM)


class FakeRuns:
    def __init__(self, unfinished: dict[str, str]) -> None:
        self.unfinished = unfinished

    def next_id(self) -> str:
        raise AssertionError("not in this task")

    def unfinished_run(self, task_id: str) -> str | None:
        return self.unfinished.get(task_id)


class FakePlans:
    def __init__(self, tasks: list[Task], latest: CommitRef | None) -> None:
        self._tasks = tasks
        self.latest = latest

    def tasks(self, plan_id: str) -> list[Task]:
        return list(self._tasks)

    def latest_commit(self, plan_id: str) -> CommitRef | None:
        return self.latest


class Repair:
    """One `repair_plan` call with its fakes."""

    def __init__(
        self,
        tasks: list[Task],
        *,
        committed: str | None = None,
        unfinished: dict[str, str] | None = None,
        remove_fails: bool = False,
        seeded: tuple[StoredEvent, ...] = (),
    ) -> None:
        latest = CommitRef(sha="c" * 40, task_id=committed) if committed else None
        self.recorder = FakeRecorder()
        self.workspace = FakeWorkspace(self.recorder, remove_fails)
        self.store = FakeEvents(self.recorder, seeded)
        self.result: RepairResult = repair_plan(
            PLAN,
            workspace=self.workspace,
            runs=FakeRuns(unfinished or {}),
            plans=FakePlans(tasks, latest),
            recorder=self.recorder,
            events=self.store,
        )

    @property
    def events(self) -> list[StoredEvent]:
        return self.recorder.events

    def moves(self) -> list[tuple[Any, Any, Any, Any]]:
        """(task id, from, to, reason) of each TaskStateChanged, in recorded order."""
        return [
            (
                e.payload["task_id"],
                e.payload["from"],
                e.payload["to"],
                e.payload["reason"],
            )
            for e in self.events
            if e.type == "TaskStateChanged"
        ]


def test_ac1_gating_task_with_commit_passes_then_worktree_removed() -> None:
    r = Repair([_task("AUTH-002", S.gating)], committed="AUTH-002")
    assert r.moves() == [("AUTH-002", "gating", "passed", None)]
    assert len(r.events) == 1
    assert r.workspace.calls == [("remove_worktree", "AUTH-002")]
    assert r.workspace.events_at_call == [1]
    assert r.result.warnings == []


def test_ac1_removal_failure_warns_and_goes_on() -> None:
    tasks = [
        _task("AUTH-002", S.gating),
        _task("AUTH-003", S.running),
        _task("AUTH-004", S.pending, ["AUTH-002"]),
    ]
    r = Repair(tasks, committed="AUTH-002", remove_fails=True)
    assert r.result.warnings == ["worktree of AUTH-002 not removed: fatal: boom"]
    assert r.moves() == [
        ("AUTH-002", "gating", "passed", None),
        ("AUTH-003", "running", "failed", "interrupted"),
        ("AUTH-003", "failed", "ready", None),
        ("AUTH-004", "pending", "ready", None),
    ]


def test_ac2_running_task_with_unfinished_run() -> None:
    r = Repair([_task("AUTH-002", S.running)], unfinished={"AUTH-002": "run_0003"})
    first, second, third = r.events
    assert first.type == "AgentRunFinished"
    assert first.stream == "run:run_0003"
    assert first.payload == {
        "run_id": "run_0003",
        "exit": "error",
        "model": None,
        "tokens_in": None,
        "tokens_out": None,
        "cost_usd": None,
        "duration_s": 0,
        "error": "interrupted",
    }
    assert second.type == "TaskStateChanged"
    assert third.type == "TaskStateChanged"
    assert r.moves() == [
        ("AUTH-002", "running", "failed", "interrupted"),
        ("AUTH-002", "failed", "ready", None),
    ]


def test_ac2_running_task_without_run_gets_only_failed() -> None:
    r = Repair([_task("AUTH-002", S.running)])
    assert len(r.events) == 2
    assert r.moves() == [
        ("AUTH-002", "running", "failed", "interrupted"),
        ("AUTH-002", "failed", "ready", None),
    ]


def test_ac2_gating_task_without_its_commit_fails() -> None:
    tasks = [_task("AUTH-002", S.gating), _task("AUTH-003", S.gating)]
    for committed in (None, "AUTH-003"):
        r = Repair(tasks, committed=committed)
        assert ("AUTH-002", "gating", "failed", "interrupted") in r.moves()
    no_commit = Repair([_task("AUTH-002", S.gating)])
    assert no_commit.moves() == [
        ("AUTH-002", "gating", "failed", "interrupted"),
        ("AUTH-002", "failed", "ready", None),
    ]
    assert no_commit.workspace.calls == []


def test_ac3_promotes_pending_tasks_in_ascending_id() -> None:
    tasks = [
        _task("AUTH-001", S.passed),
        _task("AUTH-002", S.pending),
        _task("AUTH-003", S.pending, ["AUTH-001"]),
        _task("AUTH-004", S.pending, ["AUTH-001", "AUTH-002"]),
        _task("AUTH-005", S.escalated),
        _task("AUTH-006", S.pending, ["AUTH-005"]),
    ]
    r = Repair(tasks)
    assert r.moves() == [
        ("AUTH-002", "pending", "ready", None),
        ("AUTH-003", "pending", "ready", None),
    ]


def test_ac3_dependent_of_task_passed_in_step_1_is_promoted() -> None:
    tasks = [_task("AUTH-001", S.gating), _task("AUTH-002", S.pending, ["AUTH-001"])]
    r = Repair(tasks, committed="AUTH-001")
    assert r.moves() == [
        ("AUTH-001", "gating", "passed", None),
        ("AUTH-002", "pending", "ready", None),
    ]


def test_ac3_dependent_of_task_failed_in_step_2_is_not_promoted() -> None:
    tasks = [_task("AUTH-001", S.running), _task("AUTH-002", S.pending, ["AUTH-001"])]
    r = Repair(tasks)
    assert r.moves() == [
        ("AUTH-001", "running", "failed", "interrupted"),
        ("AUTH-001", "failed", "ready", None),
    ]


def test_ac4_steps_run_in_order() -> None:
    tasks = [
        _task("AUTH-001", S.pending),
        _task("AUTH-002", S.running),
        _task("AUTH-003", S.gating),
    ]
    r = Repair(tasks, committed="AUTH-003")
    assert [m[0] for m in r.moves()] == ["AUTH-003", "AUTH-002", "AUTH-002", "AUTH-001"]


def test_ac4_other_states_and_clean_plan_record_nothing() -> None:
    tasks = [
        _task("AUTH-001", S.ready),
        _task("AUTH-002", S.passed),
        _task("AUTH-004", S.escalated),
        _task("AUTH-005", S.abandoned),
        _task("AUTH-006", S.invalidated),
    ]
    r = Repair(tasks)
    assert r.events == []
    assert r.workspace.calls == []
    assert r.result.warnings == []
    assert r.result.last_event_ids == {}


def test_ac5_events_are_orchestrator_with_no_causation() -> None:
    tasks = [
        _task("AUTH-001", S.gating),
        _task("AUTH-002", S.running),
        _task("AUTH-003", S.pending, ["AUTH-001"]),
    ]
    r = Repair(tasks, committed="AUTH-001", unfinished={"AUTH-002": "run_0001"})
    assert len(r.events) == 5
    assert all(e.actor == "orchestrator" and e.causation_id is None for e in r.events)
    for e in r.events:
        if e.type == "TaskStateChanged":
            assert e.stream == f"task:{e.payload['task_id']}"


def test_ac6_last_event_ids_map_each_touched_task_to_its_last_event() -> None:
    tasks = [
        _task("AUTH-001", S.running),
        _task("AUTH-002", S.ready),
        _task("AUTH-003", S.pending, ["AUTH-002"]),
        _task("AUTH-004", S.pending),
    ]
    r = Repair(tasks, unfinished={"AUTH-001": "run_0001"})
    ids: dict[str, UUID] = r.result.last_event_ids
    assert set(ids) == {"AUTH-001", "AUTH-004"}
    assert ids["AUTH-001"] == r.events[2].event_id
    assert r.events[2].type == "TaskStateChanged"
    assert ids["AUTH-004"] == r.events[3].event_id


# ---- TASK-073: step 2 exceptions, step 3 settling ----


def _gating_after(task_id: str, *gates: tuple[str, bool]) -> tuple[StoredEvent, ...]:
    return (
        _seed_move(task_id, "ready", "running"),
        _seed_move(task_id, "running", "gating"),
        *(_seed_gate(task_id, gate, passed) for gate, passed in gates),
    )


def _step2_move(r: Repair, task_id: str) -> tuple[Any, ...]:
    return next(m for m in r.moves() if m[0] == task_id and m[1] in ("gating", "running"))


@pytest.mark.parametrize(
    ("gates", "reason"),
    [
        ([("path_check", False)], "path_check"),
        ([("path_check", True)], "interrupted"),
        ([("path_check", False), ("ruff", True)], "path_check"),
    ],
)
def test_task073_ac1_failed_path_check_in_current_gating_sets_reason(
    gates: list[tuple[str, bool]], reason: str
) -> None:
    r = Repair([_task("AUTH-001", S.gating)], seeded=_gating_after("AUTH-001", *gates))
    assert _step2_move(r, "AUTH-001") == ("AUTH-001", "gating", "failed", reason)


def test_task073_ac1_path_check_of_an_earlier_attempt_does_not_count() -> None:
    seeded = (
        *_gating_after("AUTH-001", ("path_check", False)),
        _seed_move("AUTH-001", "gating", "failed", "path_check"),
        _seed_move("AUTH-001", "failed", "ready"),
        _seed_move("AUTH-001", "ready", "running"),
        _seed_move("AUTH-001", "running", "gating"),
    )
    r = Repair([_task("AUTH-001", S.gating)], seeded=seeded)
    assert _step2_move(r, "AUTH-001") == ("AUTH-001", "gating", "failed", "interrupted")
    assert ("AUTH-001", "failed", "ready", None) in r.moves()


def test_task073_ac1_running_task_is_always_interrupted() -> None:
    seeded = (
        *_gating_after("AUTH-001", ("path_check", False), ("gitleaks", False)),
        _seed_move("AUTH-001", "gating", "failed", "path_check"),
        _seed_move("AUTH-001", "failed", "ready"),
        _seed_move("AUTH-001", "ready", "running"),
    )
    r = Repair([_task("AUTH-001", S.running)], seeded=seeded)
    assert _step2_move(r, "AUTH-001") == ("AUTH-001", "running", "failed", "interrupted")


@pytest.mark.parametrize(
    "gates",
    [
        [("gitleaks", False)],
        [("path_check", True), ("ruff", True), ("pytest", True), ("gitleaks", False)],
    ],
)
def test_task073_ac2_failed_gitleaks_in_current_gating_is_secret_found(
    gates: list[tuple[str, bool]],
) -> None:
    r = Repair([_task("AUTH-001", S.gating)], seeded=_gating_after("AUTH-001", *gates))
    assert _step2_move(r, "AUTH-001") == ("AUTH-001", "gating", "failed", "secret found")


def test_task073_ac2_no_failed_gitleaks_is_interrupted() -> None:
    r = Repair(
        [_task("AUTH-001", S.gating)],
        seeded=_gating_after("AUTH-001", ("gitleaks", True), ("ruff", False)),
    )
    assert _step2_move(r, "AUTH-001") == ("AUTH-001", "gating", "failed", "interrupted")


def test_task073_ac2_stream_is_read_through_the_event_store() -> None:
    r = Repair([_task("AUTH-001", S.gating)], seeded=_gating_after("AUTH-001", ("gitleaks", False)))
    assert "task:AUTH-001" in r.store.reads


@pytest.mark.parametrize(
    ("gate", "reason", "escalation"),
    [
        ("path_check", "path_check", "path violation"),
        ("gitleaks", "secret found", "secret found"),
    ],
)
def test_task073_ac3_task_failed_in_step_2_escalates_at_once(
    gate: str, reason: str, escalation: str
) -> None:
    r = Repair([_task("AUTH-001", S.gating)], seeded=_gating_after("AUTH-001", (gate, False)))
    assert r.moves() == [
        ("AUTH-001", "gating", "failed", reason),
        ("AUTH-001", "failed", "escalated", escalation),
    ]


@pytest.mark.parametrize(
    ("reason", "escalation"),
    [
        ("path_check", "path violation"),
        ("secret found", "secret found"),
        ("cost limit", "cost limit"),
    ],
)
def test_task073_ac3_task_already_failed_escalates_from_its_stream(
    reason: str, escalation: str
) -> None:
    seeded = (_seed_move("AUTH-001", "gating", "failed", reason),)
    r = Repair([_task("AUTH-001", S.failed)], seeded=seeded)
    assert r.moves() == [("AUTH-001", "failed", "escalated", escalation)]


def test_task073_ac3_only_the_last_failed_reason_counts() -> None:
    seeded = (
        _seed_move("AUTH-001", "gating", "failed", "path_check"),
        _seed_move("AUTH-001", "failed", "ready"),
        _seed_move("AUTH-001", "running", "failed", "interrupted"),
    )
    r = Repair([_task("AUTH-001", S.failed)], seeded=seeded)
    assert r.moves() == [("AUTH-001", "failed", "ready", None)]


@pytest.mark.parametrize(
    ("attempt", "to", "reason"),
    [(0, "ready", None), (1, "ready", None), (2, "escalated", "attempts exhausted")],
)
def test_task073_ac4_failed_task_follows_the_attempts_rule(
    attempt: int, to: str, reason: str | None
) -> None:
    task = _task("AUTH-001", S.failed).model_copy(update={"attempt": attempt})
    seeded = (_seed_move("AUTH-001", "running", "failed", "interrupted"),)
    r = Repair([task], seeded=seeded)
    assert r.moves() == [("AUTH-001", "failed", to, reason)]
    assert r.events[0].actor == "orchestrator"
    assert r.events[0].causation_id is None


def test_task073_ac4_settles_in_ascending_id_after_step_2_before_promotion() -> None:
    tasks = [
        _task("AUTH-005", S.failed),
        _task("AUTH-003", S.running),
        _task("AUTH-004", S.failed),
        _task("AUTH-006", S.pending),
        _task("AUTH-007", S.pending, ["AUTH-004"]),
    ]
    seeded = tuple(
        _seed_move(t, "running", "failed", "interrupted") for t in ("AUTH-004", "AUTH-005")
    )
    r = Repair(tasks, seeded=seeded)
    assert r.moves() == [
        ("AUTH-003", "running", "failed", "interrupted"),
        ("AUTH-003", "failed", "ready", None),
        ("AUTH-004", "failed", "ready", None),
        ("AUTH-005", "failed", "ready", None),
        ("AUTH-006", "pending", "ready", None),
    ]
    assert all(e.causation_id is None for e in r.events)
    assert set(r.result.last_event_ids) == {"AUTH-003", "AUTH-004", "AUTH-005", "AUTH-006"}
    assert r.result.last_event_ids["AUTH-004"] == r.events[2].event_id


def test_task073_ac6_run_module_reads_events_only_from_the_port() -> None:
    tree = ast.parse((APP_DIR / "run.py").read_text())
    modules = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not [m for m in modules if m.startswith(("openfactory.adapters", "openfactory.cli"))]
    assert "openfactory.ports.event_store" in modules
