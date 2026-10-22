"""TASK-055: run use case, the loop (AC1..AC6 in docs/tasks/TASK-055-run-loop.md).

`run_plan` is driven through in-memory fakes of the eight ports. The fake `Plans` derives
task states from the `TaskStateChanged` events the fake recorder stored.
"""

import ast
from pathlib import Path
from typing import Any

import pytest

from openfactory.app.run import RunRefusal, RunReport, run_plan
from openfactory.domain.agent_run import RunResult
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType, StoredEvent
from openfactory.domain.gates import GateOutput, MarkerLine, ProcessGate
from openfactory.domain.llm import LLMReply
from openfactory.domain.models import SpecSet
from openfactory.domain.plans import CommitRef, PlanRef, Task
from openfactory.domain.policy import BASELINE_FORBIDDEN_PATHS
from openfactory.domain.spec_versions import SpecVersionRef
from openfactory.domain.states import TaskState
from openfactory.ports.git_provider import GitError

APP_DIR = Path(__file__).resolve().parents[2] / "src" / "openfactory" / "app"
BASE = "b" * 40
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


def _worktree(task_id: str) -> Path:
    return Path(f".openfactory/worktrees/{task_id}")


class FakeRecorder:
    def __init__(self) -> None:
        self.events: list[StoredEvent] = []

    def record(self, event: Event) -> StoredEvent:
        stored = StoredEvent(**event.model_dump(), seq=len(self.events) + 1)
        self.events.append(stored)
        return stored


class FakeEvents:
    """Read-only EventStore: the seeded events of a stream, then the recorder's."""

    def __init__(self, recorder: FakeRecorder, seeded: tuple[StoredEvent, ...] = ()) -> None:
        self.recorder = recorder
        self.seeded = list(seeded)

    def append(self, event: Event) -> StoredEvent:
        raise AssertionError("run must not append to the EventStore")

    def read(self, stream: str | None = None) -> list[StoredEvent]:
        return [
            e for e in (*self.seeded, *self.recorder.events) if stream is None or e.stream == stream
        ]


def _seed_failed(task_id: str, reason: str) -> StoredEvent:
    event = Event.new(
        stream=f"task:{task_id}",
        type=EventType.TaskStateChanged,
        payload={"task_id": task_id, "from": "gating", "to": "failed", "reason": reason},
        actor="orchestrator",
    )
    return StoredEvent(**event.model_dump(), seq=1000)


class FakePlans:
    """Task states are the initial ones with the stored `TaskStateChanged` events applied."""

    def __init__(
        self,
        tasks: list[Task],
        recorder: FakeRecorder,
        approved: PlanRef | None,
        committed: str | None,
    ) -> None:
        self._tasks = tasks
        self._recorder = recorder
        self._approved = approved
        self._committed = committed

    def approved(self) -> PlanRef | None:
        return self._approved

    def tasks(self, plan_id: str) -> list[Task]:
        states = {t.id: t.state for t in self._tasks}
        attempts = {t.id: t.attempt for t in self._tasks}
        for e in self._recorder.events:
            if e.type == "TaskStateChanged":
                states[e.payload["task_id"]] = TaskState(e.payload["to"])
                if e.payload["to"] == "running":
                    attempts[e.payload["task_id"]] += 1
        return [
            t.model_copy(update={"state": states[t.id], "attempt": attempts[t.id]})
            for t in self._tasks
        ]

    def latest_commit(self, plan_id: str) -> CommitRef | None:
        sha, task_id = None, self._committed
        for e in self._recorder.events:
            if e.type == "CommitRecorded":
                sha, task_id = e.payload["sha"], e.payload["task_id"]
        if task_id is None:
            return None
        return CommitRef(sha=sha or "c" * 40, task_id=task_id)


class FakeGit:
    def __init__(self, head: str | None, raises: bool, changed: dict[str, list[str]]) -> None:
        self.head = head
        self.raises = raises
        self.changed = changed
        self.calls: list[str] = []

    def head_commit(self, worktree: Path | None = None) -> str | None:
        self.calls.append("head_commit")
        if worktree is not None:
            return self._base
        if self.raises:
            raise GitError(BOOM)
        self._base = self.head or BASE
        return self.head

    _base: str = BASE

    def tracked_files(self, worktree: Path | None = None) -> list[str]:
        self.calls.append("tracked_files")
        return ["app/auth/login.py"]

    def stage_changes(self, worktree: Path, base: str) -> list[str]:
        self.calls.append("stage_changes")
        return self.changed.get(worktree.name, ["app/auth/login.py"])

    def staged_diff(self, worktree: Path, base: str) -> str:
        self.calls.append("staged_diff")
        return "diff --git a/app/auth/login.py b/app/auth/login.py\n"

    def reset_soft(self, worktree: Path, base: str) -> None:
        self.calls.append("reset_soft")

    def commit(self, worktree: Path, message: str) -> str:
        self.calls.append("commit")
        return ("e" + str(len(self.calls))).ljust(40, "e")


class FakeWorkspace:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def create(self, task_id: str, base: str) -> Path:
        self.calls.append(("create", task_id))
        return _worktree(task_id)

    def remove(self, task_id: str) -> None:
        self.calls.append(("remove", task_id))

    def remove_worktree(self, task_id: str) -> None:
        self.calls.append(("remove_worktree", task_id))


class FakeExecutor:
    def __init__(self, failing: set[str]) -> None:
        self.failing = failing
        self.calls: list[str] = []

    def run(
        self, contract: TaskContract, context: str, workdir: Path, output_dir: Path
    ) -> RunResult:
        self.calls.append(contract.task_id)
        if contract.task_id in self.failing:
            return RunResult(
                exit="error",
                model=None,
                tokens_in=None,
                tokens_out=None,
                cost_usd=None,
                duration_s=1.0,
                error="boom",
                summary="",
            )
        return RunResult(
            exit="ok",
            model="claude-x",
            tokens_in=1,
            tokens_out=1,
            cost_usd=0.1,
            duration_s=1.0,
            error=None,
            summary="Done.",
        )


class FakeLLM:
    """Approves every review."""

    def complete(self, prompt: str, schema: dict[str, object]) -> LLMReply:
        return LLMReply(
            structured={"verdict": "approve", "comments": "ok"},
            model="claude-r",
            tokens_in=1,
            tokens_out=1,
            cost_usd=0.01,
            duration_s=1.0,
        )


class FakeRunFiles:
    def write(self, run_id: str, name: str, text: str) -> Path:
        return Path(".openfactory/runs") / run_id / name


class FakeRuns:
    def __init__(self, unfinished: dict[str, str]) -> None:
        self.unfinished = unfinished
        self.n = 0

    def next_id(self) -> str:
        self.n += 1
        return f"run_{self.n:04d}"

    def unfinished_run(self, task_id: str) -> str | None:
        return self.unfinished.get(task_id)


class FakeVersions:
    def __init__(self) -> None:
        self.spec_calls: list[str] = []

    def latest_approved(self) -> SpecVersionRef:
        raise AssertionError("run must use the plan's spec version, not the latest")

    def spec_set(self, version_id: str) -> SpecSet | None:
        self.spec_calls.append(version_id)
        return SpecSet()


class FakeGates:
    def __init__(self, missing: str | None) -> None:
        self.missing = missing
        self.missing_calls = 0
        self.run_calls: list[tuple[str, Path, int]] = []

    def missing_tool(self) -> str | None:
        self.missing_calls += 1
        return self.missing

    def run(self, gate: ProcessGate, worktree: Path, timeout_s: int) -> GateOutput:
        self.run_calls.append((gate, worktree, timeout_s))
        markers = (
            [
                MarkerLine(
                    node_id="tests/test_a.py::test_x",
                    file="app/auth/login.py",
                    req=["REQ-AUTH-001"],
                )
            ]
            if gate == "pytest"
            else []
        )
        return GateOutput(passed=True, text="", finding=False, marker_lines=markers)


class Run:
    """One `run_plan` call with its fakes."""

    def __init__(
        self,
        tasks: list[Task],
        *,
        task_id: str | None = None,
        approved: PlanRef | None = PLAN,
        head: str | None = BASE,
        head_raises: bool = False,
        committed: str | None = None,
        failing: set[str] | None = None,
        escalating: set[str] | None = None,
        unfinished: dict[str, str] | None = None,
        missing: str | None = None,
        seeded: tuple[StoredEvent, ...] = (),
    ) -> None:
        self.gates = FakeGates(missing)
        self.recorder = FakeRecorder()
        changed = {t: ["README.md"] for t in (escalating or set())}
        self.git = FakeGit(head, head_raises, changed)
        self.workspace = FakeWorkspace()
        self.executor = FakeExecutor(failing or set())
        self.versions = FakeVersions()
        self.report: RunReport = run_plan(
            task_id=task_id,
            git=self.git,
            workspace=self.workspace,
            executor=self.executor,
            run_files=FakeRunFiles(),
            runs=FakeRuns(unfinished or {}),
            plans=FakePlans(tasks, self.recorder, approved, committed),
            versions=self.versions,
            recorder=self.recorder,
            gates=self.gates,
            llm=FakeLLM(),
            events=FakeEvents(self.recorder, seeded),
        )

    @property
    def events(self) -> list[StoredEvent]:
        return self.recorder.events

    def moves(self) -> list[tuple[str, str, str, Any]]:
        return [
            (e.payload["task_id"], e.payload["from"], e.payload["to"], e.payload["reason"])
            for e in self.events
            if e.type == "TaskStateChanged"
        ]

    def move_event(self, task_id: str, frm: str, to: str) -> StoredEvent:
        return next(
            e
            for e in self.events
            if e.type == "TaskStateChanged"
            and (e.payload["task_id"], e.payload["from"], e.payload["to"]) == (task_id, frm, to)
        )

    def taken(self) -> list[str]:
        return [r.task_id for r in self.report.tasks]


# ---- AC1: refusals before any event ----


@pytest.mark.parametrize(
    ("kwargs", "refusal", "detail", "git_calls"),
    [
        ({"approved": None}, RunRefusal.no_approved_plan, None, []),
        ({"head": None}, RunRefusal.no_commit, None, ["head_commit"]),
        ({"head_raises": True}, RunRefusal.git_failed, "fatal: boom", ["head_commit"]),
        (
            {"head": None, "committed": "AUTH-001"},
            RunRefusal.no_commit,
            None,
            ["head_commit"],
        ),
    ],
)
def test_ac1_refusals_record_nothing(
    kwargs: dict[str, Any], refusal: RunRefusal, detail: str | None, git_calls: list[str]
) -> None:
    r = Run([_task("AUTH-001", S.ready)], **kwargs)
    assert r.report.refusal == refusal
    assert r.report.detail == detail
    assert r.report.warnings == []
    assert r.report.tasks == []
    assert r.events == []
    assert r.workspace.calls == []
    assert r.executor.calls == []
    assert r.git.calls == git_calls


# ---- AC2: repair, then the loop ----


def test_ac2_repair_first_then_ascending_loop_including_repair_promoted() -> None:
    tasks = [
        _task("AUTH-004", S.ready),
        _task("AUTH-002", S.ready),
        _task("AUTH-005", S.running),
        _task("AUTH-003", S.pending),
    ]
    r = Run(tasks, unfinished={"AUTH-005": "run_0009"})
    assert r.report.refusal is None
    assert r.taken() == ["AUTH-002", "AUTH-003", "AUTH-004", "AUTH-005"]
    assert [t.state for t in r.report.tasks] == [S.passed] * 4
    # the repair's events come before any loop event
    assert r.moves()[:3] == [
        ("AUTH-005", "running", "failed", "interrupted"),
        ("AUTH-005", "failed", "ready", None),
        ("AUTH-003", "pending", "ready", None),
    ]
    assert r.events[0].type == "AgentRunFinished"
    assert r.executor.calls == ["AUTH-002", "AUTH-003", "AUTH-004", "AUTH-005"]


def test_ac2_repair_warnings_are_returned() -> None:
    class Failing(FakeWorkspace):
        def remove_worktree(self, task_id: str) -> None:
            self.calls.append(("remove_worktree", task_id))
            raise GitError(BOOM)

    tasks = [_task("AUTH-001", S.gating)]
    recorder = FakeRecorder()
    report = run_plan(
        git=FakeGit(BASE, False, {}),
        workspace=Failing(),
        executor=FakeExecutor(set()),
        run_files=FakeRunFiles(),
        runs=FakeRuns({}),
        plans=FakePlans(tasks, recorder, PLAN, "AUTH-001"),
        versions=FakeVersions(),
        recorder=recorder,
        gates=FakeGates(None),
        llm=FakeLLM(),
        events=FakeEvents(recorder),
    )
    assert report.warnings == ["worktree of AUTH-001 not removed: fatal: boom"]
    assert report.tasks == []


def test_ac2_failed_and_escalated_tasks_do_not_stop_the_loop() -> None:
    tasks = [_task(f"AUTH-00{i}", S.ready) for i in (3, 1, 2)]
    r = Run(tasks, failing={"AUTH-001"}, escalating={"AUTH-002"})
    assert r.taken() == ["AUTH-001", "AUTH-002", "AUTH-003"]
    assert [t.state for t in r.report.tasks] == [S.escalated, S.escalated, S.passed]


def test_ac2_spec_set_is_the_plans_version_read_once() -> None:
    r = Run([_task("AUTH-001", S.ready), _task("AUTH-002", S.ready)])
    assert r.versions.spec_calls == ["sv_01"]


def test_ac2_no_ready_task_records_nothing() -> None:
    r = Run([_task("AUTH-001", S.passed), _task("AUTH-002", S.escalated)])
    assert r.report.refusal is None
    assert r.report.tasks == []
    assert r.events == []


# ---- AC3: promotion after a pass ----


def test_ac3_dependents_promoted_in_ascending_id_and_taken() -> None:
    tasks = [
        _task("AUTH-004", S.pending, ["AUTH-001"]),
        _task("AUTH-001", S.ready),
        _task("AUTH-003", S.pending, ["AUTH-001"]),
        _task("AUTH-005", S.pending, ["AUTH-001", "AUTH-009"]),
        _task("AUTH-009", S.escalated),
    ]
    r = Run(tasks)
    assert r.taken() == ["AUTH-001", "AUTH-003", "AUTH-004"]
    promos = [m for m in r.moves() if m[1:3] == ("pending", "ready")]
    assert promos == [
        ("AUTH-003", "pending", "ready", None),
        ("AUTH-004", "pending", "ready", None),
    ]
    first = r.report.tasks[0]
    for task_id in ("AUTH-003", "AUTH-004"):
        assert r.move_event(task_id, "pending", "ready").causation_id == first.last_event_id


def test_ac3_no_promotion_after_a_task_that_did_not_pass() -> None:
    tasks = [_task("AUTH-001", S.ready), _task("AUTH-002", S.pending, ["AUTH-001"])]
    r = Run(tasks, failing={"AUTH-001"})
    assert r.taken() == ["AUTH-001"]
    assert not [m for m in r.moves() if m[1:3] == ("pending", "ready")]


# ---- AC4: causation of the first running event ----


def test_ac4_causation_of_ready_to_running() -> None:
    tasks = [
        _task("AUTH-001", S.ready),
        _task("AUTH-002", S.pending),
        _task("AUTH-003", S.pending, ["AUTH-001"]),
    ]
    r = Run(tasks)
    assert r.taken() == ["AUTH-001", "AUTH-002", "AUTH-003"]
    # already ready, no earlier event in the command
    assert r.move_event("AUTH-001", "ready", "running").causation_id is None
    # promoted by the repair
    repair_ready = r.move_event("AUTH-002", "pending", "ready")
    assert r.move_event("AUTH-002", "ready", "running").causation_id == repair_ready.event_id
    # promoted after a pass
    loop_ready = r.move_event("AUTH-003", "pending", "ready")
    assert r.move_event("AUTH-003", "ready", "running").causation_id == loop_ready.event_id


# ---- AC5: --task ----


def test_ac5_unknown_task_keeps_repair_events_and_warnings() -> None:
    tasks = [_task("AUTH-001", S.running), _task("AUTH-002", S.pending)]
    r = Run(tasks, task_id="AUTH-099")
    assert r.report.refusal == RunRefusal.unknown_task
    assert r.report.detail == "AUTH-099"
    assert r.report.tasks == []
    assert r.moves() == [
        ("AUTH-001", "running", "failed", "interrupted"),
        ("AUTH-001", "failed", "ready", None),
        ("AUTH-002", "pending", "ready", None),
    ]
    assert r.executor.calls == []


def test_ac5_not_ready_reports_state_after_repair() -> None:
    task = _task("AUTH-001", S.running).model_copy(update={"attempt": 2})
    r = Run([task], task_id="AUTH-001")
    assert r.report.refusal == RunRefusal.not_ready
    assert r.report.detail == "escalated"
    assert r.report.tasks == []
    assert r.executor.calls == []


def test_ac5_task_runs_alone_and_promotes_without_taking() -> None:
    tasks = [
        _task("AUTH-001", S.ready),
        _task("AUTH-002", S.ready),
        _task("AUTH-003", S.pending, ["AUTH-002"]),
    ]
    r = Run(tasks, task_id="AUTH-002")
    assert r.report.refusal is None
    assert r.taken() == ["AUTH-002"]
    assert r.executor.calls == ["AUTH-002"]
    promo = r.move_event("AUTH-003", "pending", "ready")
    assert promo.causation_id == r.report.tasks[0].last_event_id
    assert not [m for m in r.moves() if m[0] == "AUTH-003" and m[2] == "running"]


# ---- AC6: structure ----


def test_ac6_promotions_are_orchestrator_events_on_the_task_stream() -> None:
    tasks = [_task("AUTH-001", S.ready), _task("AUTH-002", S.pending, ["AUTH-001"])]
    r = Run(tasks)
    promo = r.move_event("AUTH-002", "pending", "ready")
    assert promo.stream == "task:AUTH-002"
    assert promo.actor == "orchestrator"


def test_ac6_run_module_imports_no_adapter_or_cli() -> None:
    tree = ast.parse((APP_DIR / "run.py").read_text())
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules.append(node.module or "")
    assert not [m for m in modules if m.startswith(("openfactory.adapters", "openfactory.cli"))]


# ---- TASK-056 AC3: the repair's warnings come back with a --task refusal ----


def _run_with_failing_removal(task_id: str) -> RunReport:
    class Failing(FakeWorkspace):
        def remove_worktree(self, task_id: str) -> None:
            self.calls.append(("remove_worktree", task_id))
            raise GitError(BOOM)

    tasks = [_task("AUTH-001", S.gating), _task("AUTH-002", S.ready)]
    recorder = FakeRecorder()
    return run_plan(
        task_id=task_id,
        git=FakeGit(BASE, False, {}),
        workspace=Failing(),
        executor=FakeExecutor(set()),
        run_files=FakeRunFiles(),
        runs=FakeRuns({}),
        plans=FakePlans(tasks, recorder, PLAN, "AUTH-001"),
        versions=FakeVersions(),
        recorder=recorder,
        gates=FakeGates(None),
        llm=FakeLLM(),
        events=FakeEvents(recorder),
    )


def test_task056_unknown_task_returns_the_repair_warnings() -> None:
    report = _run_with_failing_removal("AUTH-099")
    assert report.refusal == RunRefusal.unknown_task
    assert report.warnings == ["worktree of AUTH-001 not removed: fatal: boom"]


def test_task056_not_ready_returns_the_repair_warnings() -> None:
    report = _run_with_failing_removal("AUTH-001")
    assert report.refusal == RunRefusal.not_ready
    assert report.detail == "passed"
    assert report.warnings == ["worktree of AUTH-001 not removed: fatal: boom"]


# ---- TASK-067: the `<tool> not found` refusal ----


@pytest.mark.parametrize("tool", ["uv", "gitleaks"])
def test_task067_missing_tool_refuses_before_any_event(tool: str) -> None:
    r = Run([_task("AUTH-001", S.ready)], missing=tool)
    assert r.report.refusal == RunRefusal.tool_not_found
    assert r.report.detail == tool
    assert r.report.warnings == []
    assert r.report.tasks == []
    assert r.events == []
    assert r.workspace.calls == []
    assert r.executor.calls == []
    assert r.gates.missing_calls == 1
    assert r.gates.run_calls == []


@pytest.mark.parametrize(
    ("kwargs", "refusal"),
    [
        ({"approved": None}, RunRefusal.no_approved_plan),
        ({"head": None}, RunRefusal.no_commit),
        ({"head_raises": True}, RunRefusal.git_failed),
    ],
)
def test_task067_earlier_refusals_come_before_the_tool_check(
    kwargs: dict[str, Any], refusal: RunRefusal
) -> None:
    r = Run([_task("AUTH-001", S.ready)], missing="uv", **kwargs)
    assert r.report.refusal == refusal
    assert r.gates.missing_calls == 0
    assert r.gates.run_calls == []


def test_task067_no_missing_tool_goes_on_to_the_loop() -> None:
    r = Run([_task("AUTH-001", S.ready)])
    assert r.report.refusal is None
    assert r.taken() == ["AUTH-001"]
    assert r.gates.missing_calls == 1


@pytest.mark.parametrize("task_id", ["AUTH-099", "AUTH-001"])
def test_task067_missing_tool_beats_task_refusals_and_repair_records_nothing(
    task_id: str,
) -> None:
    r = Run([_task("AUTH-001", S.running)], task_id=task_id, missing="gitleaks")
    assert r.report.refusal == RunRefusal.tool_not_found
    assert r.report.detail == "gitleaks"
    assert r.events == []
    assert r.gates.run_calls == []


# ---- TASK-068: the gates are passed through to each task ----


def test_task068_gates_are_called_during_the_loop() -> None:
    r = Run([_task("AUTH-001", S.ready)])
    assert r.taken() == ["AUTH-001"]
    assert r.gates.run_calls == [
        (gate, _worktree("AUTH-001"), 600) for gate in ("ruff", "pytest", "gitleaks")
    ]


# ---- TASK-072: the retry loop ----


class FlakyExecutor(FakeExecutor):
    """Fails a task's first N runs (`fail_first`), then succeeds."""

    def __init__(self, fail_first: dict[str, int]) -> None:
        super().__init__(set())
        self.fail_first = fail_first

    def run(
        self, contract: TaskContract, context: str, workdir: Path, output_dir: Path
    ) -> RunResult:
        seen = self.calls.count(contract.task_id)
        self.failing = (
            {contract.task_id} if seen < self.fail_first.get(contract.task_id, 0) else set()
        )
        return super().run(contract, context, workdir, output_dir)


class Retry:
    """`run_plan` with a flaky executor."""

    def __init__(
        self, tasks: list[Task], fail_first: dict[str, int], task_id: str | None = None
    ) -> None:
        self.recorder = FakeRecorder()
        self.executor = FlakyExecutor(fail_first)
        self.report = run_plan(
            task_id=task_id,
            git=FakeGit(BASE, False, {}),
            workspace=FakeWorkspace(),
            executor=self.executor,
            run_files=FakeRunFiles(),
            runs=FakeRuns({}),
            plans=FakePlans(tasks, self.recorder, PLAN, None),
            versions=FakeVersions(),
            recorder=self.recorder,
            gates=FakeGates(None),
            llm=FakeLLM(),
            events=FakeEvents(self.recorder),
        )

    def moves(self, task_id: str) -> list[StoredEvent]:
        return [
            e
            for e in self.recorder.events
            if e.type == "TaskStateChanged" and e.payload["task_id"] == task_id
        ]

    def pairs(self, task_id: str) -> list[tuple[str, str]]:
        return [(e.payload["from"], e.payload["to"]) for e in self.moves(task_id)]


def test_task072_ac1_failed_moves_to_ready_pointing_at_the_failed_event() -> None:
    r = Retry([_task("AUTH-001", S.ready)], {"AUTH-001": 1})
    moves = r.moves("AUTH-001")
    i = next(i for i, e in enumerate(moves) if e.payload["to"] == "failed")
    failed, nxt = moves[i], moves[i + 1]
    assert (nxt.payload["from"], nxt.payload["to"], nxt.payload["reason"]) == (
        "failed",
        "ready",
        None,
    )
    assert nxt.actor == "orchestrator"
    assert nxt.causation_id == failed.event_id


def test_task072_ac2_attempts_exhausted_escalates_and_stops() -> None:
    r = Retry([_task("AUTH-001", S.ready)], {"AUTH-001": 5})
    assert r.executor.calls == ["AUTH-001", "AUTH-001"]
    moves = r.moves("AUTH-001")
    last, failed = moves[-1], moves[-2]
    assert (last.payload["from"], last.payload["to"], last.payload["reason"]) == (
        "failed",
        "escalated",
        "attempts exhausted",
    )
    assert last.causation_id == failed.event_id
    assert [t.state for t in r.report.tasks] == [S.escalated]


def test_task072_ac2_already_escalated_task_gets_no_further_move() -> None:
    tasks = [_task("AUTH-001", S.ready)]
    recorder = FakeRecorder()
    run_plan(
        git=FakeGit(BASE, False, {"AUTH-001": ["README.md"]}),
        workspace=FakeWorkspace(),
        executor=FakeExecutor(set()),
        run_files=FakeRunFiles(),
        runs=FakeRuns({}),
        plans=FakePlans(tasks, recorder, PLAN, None),
        versions=FakeVersions(),
        recorder=recorder,
        gates=FakeGates(None),
        llm=FakeLLM(),
        events=FakeEvents(recorder),
    )
    tos = [e.payload["to"] for e in recorder.events if e.type == "TaskStateChanged"]
    assert tos == ["running", "gating", "failed", "escalated"]


def test_task072_ac3_retry_running_event_points_at_the_failed_to_ready_move() -> None:
    tasks = [_task("AUTH-002", S.ready), _task("AUTH-003", S.ready)]
    r = Retry(tasks, {"AUTH-003": 1})
    assert r.executor.calls == ["AUTH-002", "AUTH-003", "AUTH-003"]
    moves = r.moves("AUTH-003")
    back = next(e for e in moves if (e.payload["from"], e.payload["to"]) == ("failed", "ready"))
    again = [e for e in moves if e.payload["to"] == "running"][1]
    assert again.causation_id == back.event_id


def test_task072_ac3_retry_is_taken_by_the_lowest_id_rule() -> None:
    tasks = [_task("AUTH-001", S.ready), _task("AUTH-002", S.ready)]
    r = Retry(tasks, {"AUTH-001": 1})
    assert r.executor.calls == ["AUTH-001", "AUTH-001", "AUTH-002"]


def test_task072_ac3_fail_once_then_pass_promotes_dependents() -> None:
    tasks = [_task("AUTH-001", S.ready), _task("AUTH-002", S.pending, ["AUTH-001"])]
    r = Retry(tasks, {"AUTH-001": 1})
    assert [t.state for t in r.report.tasks] == [S.passed, S.passed]
    assert ("pending", "ready") in r.pairs("AUTH-002")


def test_task072_ac4_task_option_retries_only_that_task() -> None:
    tasks = [_task("AUTH-001", S.ready), _task("AUTH-002", S.ready)]
    r = Retry(tasks, {"AUTH-002": 1}, task_id="AUTH-002")
    assert r.executor.calls == ["AUTH-002", "AUTH-002"]
    assert [(t.task_id, t.state) for t in r.report.tasks] == [("AUTH-002", S.passed)]


def test_task072_ac4_task_option_stops_when_attempts_run_out() -> None:
    tasks = [_task("AUTH-001", S.ready), _task("AUTH-002", S.ready)]
    r = Retry(tasks, {"AUTH-002": 5}, task_id="AUTH-002")
    assert r.executor.calls == ["AUTH-002", "AUTH-002"]
    assert [(t.task_id, t.state) for t in r.report.tasks] == [("AUTH-002", S.escalated)]


def test_task072_ac5_one_entry_per_task_at_first_position_with_last_attempt() -> None:
    tasks = [_task(f"AUTH-00{i}", S.ready) for i in (1, 2, 3)]
    r = Retry(tasks, {"AUTH-001": 1})
    assert [t.task_id for t in r.report.tasks] == ["AUTH-001", "AUTH-002", "AUTH-003"]
    assert [t.state for t in r.report.tasks] == [S.passed] * 3
    last_ids = [e.event_id for e in r.moves("AUTH-001") if e.payload["to"] == "passed"]
    assert r.report.tasks[0].last_event_id == last_ids[-1]


def test_task072_ac6_settling_moves_are_validated_through_the_chain() -> None:
    source = (APP_DIR / "run.py").read_text()
    assert "_settle_failed" in source
    assert "attempts exhausted" in source


# ---- TASK-073: settling failed tasks in the repair ----


def test_task073_ac5_settled_to_ready_is_taken_pointing_at_the_repair_event() -> None:
    r = Run([_task("AUTH-001", S.running)])
    assert r.taken() == ["AUTH-001"]
    back = r.move_event("AUTH-001", "failed", "ready")
    assert back.causation_id is None
    # the loop's `ready` to `running` is the second `running` move; find it by causation
    loop_start = next(
        e
        for e in r.events
        if e.type == "TaskStateChanged"
        and e.payload["from"] == "ready"
        and e.payload["to"] == "running"
    )
    assert loop_start.causation_id == back.event_id


@pytest.mark.parametrize(
    ("reason", "escalation"),
    [("path_check", "path violation"), ("secret found", "secret found")],
)
def test_task073_ac5_task_option_on_a_repair_escalated_task_is_refused(
    reason: str, escalation: str
) -> None:
    r = Run(
        [_task("AUTH-001", S.failed)],
        task_id="AUTH-001",
        seeded=(_seed_failed("AUTH-001", reason),),
    )
    assert r.report.refusal == RunRefusal.not_ready
    assert r.report.detail == "escalated"
    assert r.moves() == [("AUTH-001", "failed", "escalated", escalation)]
    assert r.executor.calls == []


def test_task073_ac5_cli_run_passes_an_event_store() -> None:
    cli = (APP_DIR.parent / "cli.py").read_text()
    assert "SqliteEventStore" in cli
    assert "events=" in cli


class RecordingExecutor(FlakyExecutor):
    def __init__(self, fail_first: dict[str, int]) -> None:
        super().__init__(fail_first)
        self.contexts: list[str] = []

    def run(
        self, contract: TaskContract, context: str, workdir: Path, output_dir: Path
    ) -> RunResult:
        self.contexts.append(context)
        return super().run(contract, context, workdir, output_dir)


def test_task074_ac5_second_attempt_pack_holds_the_first_attempts_reason() -> None:
    recorder = FakeRecorder()
    executor = RecordingExecutor({"AUTH-001": 1})
    run_plan(
        task_id=None,
        git=FakeGit(BASE, False, {}),
        workspace=FakeWorkspace(),
        executor=executor,
        run_files=FakeRunFiles(),
        runs=FakeRuns({}),
        plans=FakePlans([_task("AUTH-001", S.ready)], recorder, PLAN, None),
        versions=FakeVersions(),
        recorder=recorder,
        gates=FakeGates(None),
        llm=FakeLLM(),
        events=FakeEvents(recorder),
    )
    first, second = executor.contexts
    assert "Failure report" not in first
    assert "## Failure report of the previous attempt" in second
    assert "reason: run error" in second
