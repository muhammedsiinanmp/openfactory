"""TASK-052: run use case, one task (AC1..AC6 in docs/tasks/TASK-052-run-one-task.md).

`run_task` is driven through in-memory fakes of the seven ports; no git, claude or
database is used.
"""

import ast
from pathlib import Path
from uuid import UUID

import pytest

from openfactory.app.context_pack import build_context_pack
from openfactory.app.planner_prompt import context_hash
from openfactory.app.run import run_task
from openfactory.domain.agent_run import RunResult
from openfactory.domain.commit_message import build_commit_message
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, StoredEvent
from openfactory.domain.models import SpecSet
from openfactory.domain.plans import CommitRef, PlanRef, Task
from openfactory.domain.policy import BASELINE_FORBIDDEN_PATHS
from openfactory.domain.states import TaskState

APP_DIR = Path(__file__).resolve().parents[2] / "src" / "openfactory" / "app"

BASE = "b" * 40
COMMIT = "c" * 40
LATEST = "a" * 40
WORKTREE = Path(".openfactory/worktrees/AUTH-002")
TRACKED = ["app/auth/login.py", "README.md", "specs/requirements.yaml"]
PLAN = PlanRef(id="plan_01", spec_version="sv_01")
SPEC = SpecSet()


def _task(state: TaskState = TaskState.ready) -> Task:
    return Task(
        id="AUTH-002",
        plan_id="plan_01",
        state=state,
        attempt=0,
        contract=TaskContract(
            task_id="AUTH-002",
            objective="Add the login endpoint.",
            requirements=["REQ-AUTH-001"],
            acceptance_criteria=["AC-AUTH-001-1"],
            depends_on=[],
            components=["auth"],
            role="implementer",
            allowed_paths=["app/auth/**", "tests/auth/**"],
            forbidden_paths=list(BASELINE_FORBIDDEN_PATHS),
            required_gates=["path_check", "ruff", "pytest", "gitleaks", "review"],
            limits=Limits(max_runtime_s=600, max_attempts=2, max_cost_usd=1.0),
        ),
        depends_on=[],
    )


def _result(exit_: str = "ok", error: str | None = None) -> RunResult:
    ok = exit_ == "ok"
    return RunResult(
        exit=exit_,  # type: ignore[arg-type]
        model="claude-x" if ok else None,
        tokens_in=100 if ok else None,
        tokens_out=50 if ok else None,
        cost_usd=0.25 if ok else None,
        duration_s=12.5,
        error=error,
        summary="Added the login endpoint." if ok else "",
    )


class FakeGit:
    def __init__(self, changed: list[str]) -> None:
        self.changed = changed
        self.head_calls = 0
        self.tracked_calls: list[Path | None] = []
        self.stage_calls: list[tuple[Path, str]] = []
        self.commit_calls: list[tuple[Path, str]] = []

    def tracked_files(self, worktree: Path | None = None) -> list[str]:
        self.tracked_calls.append(worktree)
        return list(TRACKED)

    def head_commit(self, worktree: Path | None = None) -> str | None:
        self.head_calls += 1
        return BASE

    def stage_changes(self, worktree: Path, base: str) -> list[str]:
        self.stage_calls.append((worktree, base))
        return list(self.changed)

    def reset_soft(self, worktree: Path, base: str) -> None:
        raise AssertionError("not in this task")

    def commit(self, worktree: Path, message: str) -> str:
        self.commit_calls.append((worktree, message))
        return COMMIT


class FakeWorkspace:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def create(self, task_id: str, base: str) -> Path:
        self.calls.append(("create", (task_id, base)))
        return WORKTREE

    def remove(self, task_id: str) -> None:
        self.calls.append(("remove", (task_id,)))

    def remove_worktree(self, task_id: str) -> None:
        self.calls.append(("remove_worktree", (task_id,)))


class FakeExecutor:
    def __init__(self, result: RunResult) -> None:
        self.result = result
        self.calls: list[tuple[TaskContract, str, Path, Path]] = []

    def run(
        self, contract: TaskContract, context: str, workdir: Path, output_dir: Path
    ) -> RunResult:
        self.calls.append((contract, context, workdir, output_dir))
        return self.result


class FakeRunFiles:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def write(self, run_id: str, name: str, text: str) -> Path:
        self.calls.append((run_id, name, text))
        return Path(".openfactory/runs") / run_id / name


class FakeRuns:
    def next_id(self) -> str:
        return "run_0002"

    def unfinished_run(self, task_id: str) -> str | None:
        raise AssertionError("not in this task")


class FakePlans:
    def __init__(self, latest: CommitRef | None) -> None:
        self.latest = latest

    def latest_commit(self, plan_id: str) -> CommitRef | None:
        return self.latest


class FakeRecorder:
    def __init__(self) -> None:
        self.events: list[StoredEvent] = []

    def record(self, event: Event) -> StoredEvent:
        stored = StoredEvent(**event.model_dump(), seq=len(self.events) + 1)
        self.events.append(stored)
        return stored


class Run:
    """One `run_task` call with its fakes."""

    def __init__(
        self,
        *,
        task: Task | None = None,
        changed: list[str] | None = None,
        result: RunResult | None = None,
        latest: CommitRef | None = None,
        causation_id: UUID | None = None,
        raises: type[Exception] | None = None,
        match: str | None = None,
    ) -> None:
        self.git = FakeGit(
            ["tests/auth/test_login.py", "app/auth/login.py"] if changed is None else changed
        )
        self.workspace = FakeWorkspace()
        self.executor = FakeExecutor(result or _result())
        self.run_files = FakeRunFiles()
        self.recorder = FakeRecorder()
        kwargs = dict(
            causation_id=causation_id,
            git=self.git,
            workspace=self.workspace,
            executor=self.executor,
            run_files=self.run_files,
            runs=FakeRuns(),
            plans=FakePlans(latest),
            recorder=self.recorder,
        )
        self.task = task or _task()
        if raises is not None:
            with pytest.raises(raises, match=match):
                run_task(self.task, PLAN, SPEC, **kwargs)  # type: ignore[arg-type]
            self.outcome = None
        else:
            self.outcome = run_task(self.task, PLAN, SPEC, **kwargs)  # type: ignore[arg-type]

    @property
    def events(self) -> list[StoredEvent]:
        return self.recorder.events

    def shape(self) -> list[tuple[str, str | None, str | None]]:
        """(type, from->to for state changes, reason)."""
        out = []
        for e in self.events:
            if e.type == "TaskStateChanged":
                out.append((e.type, f"{e.payload['from']}>{e.payload['to']}", e.payload["reason"]))
            else:
                out.append((e.type, None, None))
        return out


def test_ac1_passed_run_records_seven_events_in_order() -> None:
    r = Run()
    assert r.shape() == [
        ("TaskStateChanged", "ready>running", None),
        ("AgentRunStarted", None, None),
        ("AgentRunFinished", None, None),
        ("TaskStateChanged", "running>gating", None),
        ("GateEvaluated", None, None),
        ("CommitRecorded", None, None),
        ("TaskStateChanged", "gating>passed", None),
    ]
    assert {e.actor for e in r.events} == {"orchestrator"}
    assert [e.stream for e in r.events] == [
        "task:AUTH-002",
        "run:run_0002",
        "run:run_0002",
        "task:AUTH-002",
        "task:AUTH-002",
        "task:AUTH-002",
        "task:AUTH-002",
    ]


def test_ac1_payloads_and_result() -> None:
    r = Run()
    pack = r.executor.calls[0][1]
    started, finished, gate, commit = (r.events[i].payload for i in (1, 2, 4, 5))
    assert started == {
        "run_id": "run_0002",
        "task_id": "AUTH-002",
        "role": "implementer",
        "runtime": "claude-code",
        "context_hash": context_hash(pack),
    }
    expected = _result().model_dump(exclude={"summary"})
    assert finished == {"run_id": "run_0002", **expected}
    assert gate == {
        "run_id": "run_0002",
        "task_id": "AUTH-002",
        "gate": "path_check",
        "passed": True,
        "output_path": None,
    }
    assert r.run_files.calls == []
    assert commit == {
        "sha": COMMIT,
        "task_id": "AUTH-002",
        "run_id": "run_0002",
        "branch": "openfactory/AUTH-002",
        "spec_version": "sv_01",
        "files": ["app/auth/login.py", "tests/auth/test_login.py"],
    }
    assert r.outcome is not None
    assert r.outcome.task_id == "AUTH-002"
    assert r.outcome.state == "passed"
    assert r.outcome.last_event_id == r.events[-1].event_id


def test_ac2_events_chain_by_causation() -> None:
    r = Run()
    assert r.events[0].causation_id is None
    for before, after in zip(r.events, r.events[1:], strict=False):
        assert after.causation_id == before.event_id


def test_ac2_first_event_takes_the_given_causation_id() -> None:
    x = UUID("12345678-1234-5678-1234-567812345678")
    r = Run(causation_id=x)
    assert r.events[0].causation_id == x
    assert r.events[1].causation_id == r.events[0].event_id


def test_ac3_base_is_head_commit_and_calls_use_the_worktree() -> None:
    r = Run()
    contract = r.task.contract
    assert r.workspace.calls == [
        ("remove", ("AUTH-002",)),
        ("create", ("AUTH-002", BASE)),
        ("remove_worktree", ("AUTH-002",)),
    ]
    assert r.git.tracked_calls == [WORKTREE]
    assert r.git.stage_calls == [(WORKTREE, BASE)]
    pack = build_context_pack(contract, SPEC, TRACKED)
    assert r.executor.calls == [(contract, pack, WORKTREE, Path(".openfactory/runs/run_0002"))]
    message = build_commit_message(contract, _result().summary, "run_0002", "sv_01")
    assert r.git.commit_calls == [(WORKTREE, message)]


def test_ac3_base_is_the_plans_latest_commit_when_it_has_one() -> None:
    r = Run(latest=CommitRef(sha=LATEST, task_id="AUTH-001"))
    assert ("create", ("AUTH-002", LATEST)) in r.workspace.calls
    assert r.git.stage_calls == [(WORKTREE, LATEST)]
    assert r.git.head_calls == 0


@pytest.mark.parametrize(("exit_", "reason"), [("error", "run error"), ("timeout", "run timeout")])
def test_ac4_failed_process_fails_the_task_without_gates(exit_: str, reason: str) -> None:
    result = _result(exit_, error="boom")
    r = Run(result=result)
    assert r.shape() == [
        ("TaskStateChanged", "ready>running", None),
        ("AgentRunStarted", None, None),
        ("AgentRunFinished", None, None),
        ("TaskStateChanged", "running>failed", reason),
    ]
    assert r.events[2].payload["exit"] == exit_
    assert r.events[2].payload["error"] == "boom"
    assert r.git.stage_calls == []
    assert r.git.commit_calls == []
    assert r.run_files.calls == []
    assert ("remove_worktree", ("AUTH-002",)) not in r.workspace.calls
    assert r.outcome is not None
    assert r.outcome.state == "failed"
    assert r.outcome.last_event_id == r.events[-1].event_id


def test_ac5_no_changes_fails_the_attempt() -> None:
    r = Run(changed=[])
    assert r.shape()[-2:] == [
        ("TaskStateChanged", "running>gating", None),
        ("TaskStateChanged", "gating>failed", "no changes"),
    ]
    assert "GateEvaluated" not in [e.type for e in r.events]
    assert r.git.commit_calls == []
    assert r.outcome is not None
    assert r.outcome.state == "failed"
    assert r.outcome.last_event_id == r.events[-1].event_id


def test_ac5_path_violation_escalates() -> None:
    r = Run(changed=["app/auth/login.py", "README.md", "specs/requirements.yaml"])
    assert r.run_files.calls == [
        ("run_0002", "path_check.txt", "README.md\nspecs/requirements.yaml\n")
    ]
    gate = next(e for e in r.events if e.type == "GateEvaluated")
    assert gate.payload["passed"] is False
    assert gate.payload["output_path"] == ".openfactory/runs/run_0002/path_check.txt"
    assert r.shape()[-4:] == [
        ("TaskStateChanged", "running>gating", None),
        ("GateEvaluated", None, None),
        ("TaskStateChanged", "gating>failed", "path_check"),
        ("TaskStateChanged", "failed>escalated", "path violation"),
    ]
    assert "CommitRecorded" not in [e.type for e in r.events]
    assert r.git.commit_calls == []
    assert r.outcome is not None
    assert r.outcome.state == "escalated"
    assert r.outcome.last_event_id == r.events[-1].event_id


def test_ac6_a_transition_not_in_transitions_raises_before_recording() -> None:
    r = Run(task=_task(TaskState.pending), raises=ValueError, match=r"(?s)pending.*running")
    assert r.events == []


def test_ac6_run_module_imports_no_adapter_or_cli() -> None:
    tree = ast.parse((APP_DIR / "run.py").read_text())
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules.append(node.module or "")
    assert modules
    assert not [m for m in modules if m.startswith(("openfactory.adapters", "openfactory.cli"))]
