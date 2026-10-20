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
from openfactory.domain.gates import GateOutput, MarkerLine, ProcessGate
from openfactory.domain.models import SpecSet
from openfactory.domain.plans import CommitRef, PlanRef, Task
from openfactory.domain.policy import BASELINE_FORBIDDEN_PATHS
from openfactory.domain.states import TaskState
from openfactory.ports.git_provider import GitError

APP_DIR = Path(__file__).resolve().parents[2] / "src" / "openfactory" / "app"

BASE = "b" * 40
COMMIT = "c" * 40
LATEST = "a" * 40
WORKTREE = Path(".openfactory/worktrees/AUTH-002")
TRACKED = ["app/auth/login.py", "README.md", "specs/requirements.yaml"]
TIP = "d" * 40
BOOM = "fatal: boom\nhint: more"
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
    def __init__(self, changed: list[str], tip: str = BASE, fail_in: str | None = None) -> None:
        self.changed = changed
        self.tip = tip
        self.fail_in = fail_in
        self.recorder: FakeRecorder | None = None
        self.log: list[str] = []
        self.reset_calls: list[tuple[Path, str]] = []
        self.events_at_reset: int | None = None
        self.head_calls = 0
        self.tracked_calls: list[Path | None] = []
        self.stage_calls: list[tuple[Path, str]] = []
        self.commit_calls: list[tuple[Path, str]] = []

    def _maybe_fail(self, name: str) -> None:
        self.log.append(name)
        if self.fail_in == name:
            raise GitError(BOOM)

    def tracked_files(self, worktree: Path | None = None) -> list[str]:
        self.tracked_calls.append(worktree)
        self._maybe_fail("tracked_files")
        return list(TRACKED)

    def head_commit(self, worktree: Path | None = None) -> str | None:
        if worktree is None:
            self.head_calls += 1  # counts repo reads only, not tip reads of a worktree
            self._maybe_fail("head_commit")
            return BASE
        self._maybe_fail("head_commit_worktree")
        return self.tip

    def stage_changes(self, worktree: Path, base: str) -> list[str]:
        self.stage_calls.append((worktree, base))
        self._maybe_fail("stage_changes")
        return list(self.changed)

    def reset_soft(self, worktree: Path, base: str) -> None:
        self.reset_calls.append((worktree, base))
        if self.recorder is not None:
            self.events_at_reset = len(self.recorder.events)
        self._maybe_fail("reset_soft")

    def commit(self, worktree: Path, message: str) -> str:
        self.commit_calls.append((worktree, message))
        self._maybe_fail("commit")
        return COMMIT


class FakeWorkspace:
    def __init__(self, fail_in: str | None = None) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []
        self.fail_in = fail_in

    def create(self, task_id: str, base: str) -> Path:
        self.calls.append(("create", (task_id, base)))
        if self.fail_in == "create":
            raise GitError(BOOM)
        return WORKTREE

    def remove(self, task_id: str) -> None:
        self.calls.append(("remove", (task_id,)))
        if self.fail_in == "remove":
            raise GitError(BOOM)

    def remove_worktree(self, task_id: str) -> None:
        self.calls.append(("remove_worktree", (task_id,)))
        if self.fail_in == "remove_worktree":
            raise GitError(BOOM)


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


GATES: tuple[ProcessGate, ...] = ("ruff", "pytest", "gitleaks")


def _gate_output(
    gate: str,
    *,
    passed: bool = True,
    finding: bool = False,
    markers: list[MarkerLine] | None = None,
) -> GateOutput:
    if markers is None:
        # Covers REQ-AUTH-001 in a file `Run` reports as changed.
        markers = (
            [MarkerLine(file="tests/auth/test_login.py", req=["REQ-AUTH-001"])]
            if gate == "pytest"
            else []
        )
    return GateOutput(passed=passed, text=f"{gate} text\n", finding=finding, marker_lines=markers)


class FakeGates:
    """Returns the set output per gate (default: passes) and logs its calls."""

    def __init__(self, outputs: dict[str, GateOutput] | None = None) -> None:
        self.outputs = outputs or {}
        self.recorder: FakeRecorder | None = None
        self.calls: list[tuple[str, Path, int]] = []
        self.events_at_call: list[int] = []

    def run(self, gate: ProcessGate, worktree: Path, timeout_s: int) -> GateOutput:
        self.calls.append((gate, worktree, timeout_s))
        if self.recorder is not None:
            self.events_at_call.append(len(self.recorder.events))
        return self.outputs.get(gate) or _gate_output(gate)

    def missing_tool(self) -> str | None:
        return None


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
        tip: str | None = None,
        git_fails_in: str | None = None,
        workspace_fails_in: str | None = None,
        gates: dict[str, GateOutput] | None = None,
    ) -> None:
        base = LATEST if latest is not None else BASE
        self.git = FakeGit(
            ["tests/auth/test_login.py", "app/auth/login.py"] if changed is None else changed,
            tip=tip or base,
            fail_in=git_fails_in,
        )
        self.workspace = FakeWorkspace(workspace_fails_in)
        self.executor = FakeExecutor(result or _result())
        self.run_files = FakeRunFiles()
        self.recorder = FakeRecorder()
        self.git.recorder = self.recorder
        self.gates = FakeGates(gates)
        self.gates.recorder = self.recorder
        kwargs = dict(
            causation_id=causation_id,
            git=self.git,
            gates=self.gates,
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
        ("GateEvaluated", None, None),
        ("GateEvaluated", None, None),
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
        "task:AUTH-002",
        "task:AUTH-002",
        "task:AUTH-002",
    ]


def test_ac1_payloads_and_result() -> None:
    r = Run()
    pack = r.executor.calls[0][1]
    started, finished, gate, commit = (r.events[i].payload for i in (1, 2, 4, 8))
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
    assert r.run_files.calls == [
        ("run_0002", "ruff.txt", "ruff text\n"),
        ("run_0002", "pytest.txt", "pytest text\n"),
        ("run_0002", "gitleaks.txt", "gitleaks text\n"),
    ]
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


# ---- TASK-053: reset, git failures, failed removal after a pass ----

PASSED_SHAPE = [
    ("TaskStateChanged", "ready>running", None),
    ("AgentRunStarted", None, None),
    ("AgentRunFinished", None, None),
    ("TaskStateChanged", "running>gating", None),
    ("GateEvaluated", None, None),
    ("GateEvaluated", None, None),
    ("GateEvaluated", None, None),
    ("GateEvaluated", None, None),
    ("CommitRecorded", None, None),
    ("TaskStateChanged", "gating>passed", None),
]


def test_t053_ac1_tip_not_base_resets_soft_after_gating_before_stage_and_commit() -> None:
    r = Run(tip=TIP)
    assert r.git.reset_calls == [(WORKTREE, BASE)]
    assert r.git.events_at_reset == 4  # running, started, finished, running>gating
    assert r.git.log.index("reset_soft") < r.git.log.index("stage_changes")
    assert r.git.log.index("stage_changes") < r.git.log.index("commit")
    assert r.shape() == PASSED_SHAPE


def test_t053_ac1_tip_is_base_no_reset() -> None:
    r = Run()
    assert r.git.reset_calls == []
    assert r.shape() == PASSED_SHAPE


@pytest.mark.parametrize("fail_in", ["head_commit"])
def test_t053_ac2_repo_head_failure_fails_the_task(fail_in: str) -> None:
    r = Run(git_fails_in=fail_in)
    _assert_early_failure(r)


@pytest.mark.parametrize("fail_in", ["remove", "create"])
def test_t053_ac2_workspace_failure_fails_the_task(fail_in: str) -> None:
    r = Run(workspace_fails_in=fail_in)
    _assert_early_failure(r)


def test_t053_ac2_tracked_files_failure_fails_the_task() -> None:
    r = Run(git_fails_in="tracked_files")
    _assert_early_failure(r)


def _assert_early_failure(r: Run) -> None:
    assert r.shape() == [
        ("TaskStateChanged", "ready>running", None),
        ("TaskStateChanged", "running>failed", "git: fatal: boom"),
    ]
    assert r.executor.calls == []
    assert r.events[1].causation_id == r.events[0].event_id  # AC5
    assert r.outcome is not None
    assert r.outcome.state == "failed"
    assert r.outcome.last_event_id == r.events[-1].event_id
    assert r.outcome.warning is None


@pytest.mark.parametrize(
    "fail_in", ["head_commit_worktree", "reset_soft", "stage_changes", "commit"]
)
def test_t053_ac3_gating_git_failure_fails_the_task(fail_in: str) -> None:
    r = Run(tip=TIP, git_fails_in=fail_in)
    expected = [
        ("TaskStateChanged", "ready>running", None),
        ("AgentRunStarted", None, None),
        ("AgentRunFinished", None, None),
        ("TaskStateChanged", "running>gating", None),
    ]
    if fail_in == "commit":
        expected += [("GateEvaluated", None, None)] * 4
        assert r.events[4].payload["passed"] is True
    expected.append(("TaskStateChanged", "gating>failed", "git: fatal: boom"))
    assert r.shape() == expected
    assert "CommitRecorded" not in [e.type for e in r.events]
    assert ("remove_worktree", ("AUTH-002",)) not in r.workspace.calls
    assert r.events[-1].causation_id == r.events[-2].event_id  # AC5
    assert r.outcome is not None
    assert r.outcome.state == "failed"
    assert r.outcome.last_event_id == r.events[-1].event_id


def test_t053_ac4_failed_removal_after_a_pass_is_a_warning() -> None:
    r = Run(workspace_fails_in="remove_worktree")
    assert r.shape() == PASSED_SHAPE
    assert r.outcome is not None
    assert r.outcome.state == "passed"
    assert r.outcome.last_event_id == r.events[-1].event_id
    assert r.outcome.warning == "worktree of AUTH-002 not removed: fatal: boom"


def test_t053_ac4_no_warning_by_default() -> None:
    r = Run()
    assert r.outcome is not None
    assert r.outcome.warning is None


# ---- TASK-068: the ruff, pytest and gitleaks gates and the tag rule ----

FAIL = {g: _gate_output(g, passed=False) for g in GATES}
PASS_ALL: dict[str, GateOutput] = {}


def _gate_events(r: Run) -> list[StoredEvent]:
    return [e for e in r.events if e.type == "GateEvaluated"]


def test_task068_ac1_gates_run_in_order_with_worktree_and_timeout() -> None:
    r = Run()
    assert r.gates.calls == [(g, WORKTREE, 600) for g in GATES]
    events = _gate_events(r)
    assert [(e.payload["gate"], e.payload["passed"]) for e in events] == [
        ("path_check", True),
        ("ruff", True),
        ("pytest", True),
        ("gitleaks", True),
    ]
    assert {(e.payload["run_id"], e.payload["task_id"]) for e in events} == {
        ("run_0002", "AUTH-002")
    }
    assert r.events[4].stream == "task:AUTH-002"


def test_task068_ac1_each_gate_is_recorded_right_after_its_run() -> None:
    r = Run()
    # path_check is event 5 (index 4); the ruff call sees 5 events, pytest 6, gitleaks 7.
    assert r.gates.events_at_call == [5, 6, 7]


def test_task068_ac1_all_three_run_when_an_earlier_one_fails() -> None:
    r = Run(gates={"ruff": _gate_output("ruff", passed=False)})
    assert [c[0] for c in r.gates.calls] == list(GATES)
    assert [e.payload["gate"] for e in _gate_events(r)][1:] == list(GATES)


def test_task068_ac2_text_is_written_unchanged_and_path_is_recorded() -> None:
    outputs = {
        "ruff": GateOutput(passed=False, text="ruff bad", finding=False, marker_lines=[]),
        "pytest": _gate_output("pytest"),
        "gitleaks": GateOutput(passed=True, text="", finding=False, marker_lines=[]),
    }
    r = Run(gates=outputs)
    assert r.run_files.calls == [
        ("run_0002", "ruff.txt", "ruff bad"),
        ("run_0002", "pytest.txt", "pytest text\n"),
        ("run_0002", "gitleaks.txt", ""),
    ]
    paths = [e.payload["output_path"] for e in _gate_events(r)]
    assert paths == [
        None,
        ".openfactory/runs/run_0002/ruff.txt",
        ".openfactory/runs/run_0002/pytest.txt",
        ".openfactory/runs/run_0002/gitleaks.txt",
    ]


def test_task068_ac3_path_violation_runs_no_gate() -> None:
    r = Run(changed=["app/auth/login.py", "README.md"])
    assert r.gates.calls == []
    assert [e.payload["gate"] for e in _gate_events(r)] == ["path_check"]
    assert r.outcome is not None
    assert r.outcome.state == "escalated"


def test_task068_ac3_all_pass_commits_after_the_three_gates() -> None:
    r = Run()
    assert r.shape() == PASSED_SHAPE
    assert r.outcome is not None
    assert r.outcome.state == "passed"


@pytest.mark.parametrize(
    ("failing", "reason"),
    [
        (["pytest", "gitleaks"], "pytest"),
        (["ruff", "pytest", "gitleaks"], "ruff"),
        (["gitleaks"], "gitleaks"),
    ],
)
def test_task068_ac4_first_failed_gate_names_the_reason(failing: list[str], reason: str) -> None:
    r = Run(gates={g: _gate_output(g, passed=False) for g in failing})
    assert r.shape()[-2:] == [
        ("GateEvaluated", None, None),
        ("TaskStateChanged", "gating>failed", reason),
    ]
    assert [e.payload["passed"] for e in _gate_events(r)][1:] == [g not in failing for g in GATES]
    assert r.git.commit_calls == []
    assert "CommitRecorded" not in [e.type for e in r.events]
    assert ("remove_worktree", ("AUTH-002",)) not in r.workspace.calls
    assert r.outcome is not None
    assert r.outcome.state == "failed"
    assert r.outcome.last_event_id == r.events[-1].event_id


def test_task068_ac4_reason_follows_required_gates_order() -> None:
    task = _task()
    contract = task.contract.model_copy(
        update={"required_gates": ["path_check", "gitleaks", "pytest", "ruff", "review"]}
    )
    r = Run(
        task=task.model_copy(update={"contract": contract}),
        gates={g: _gate_output(g, passed=False) for g in ("ruff", "pytest")},
    )
    assert r.shape()[-1] == ("TaskStateChanged", "gating>failed", "pytest")


@pytest.mark.parametrize("ruff_fails", [False, True])
def test_task068_ac5_gitleaks_finding_escalates(ruff_fails: bool) -> None:
    gates = {"gitleaks": _gate_output("gitleaks", passed=False, finding=True)}
    if ruff_fails:
        gates["ruff"] = _gate_output("ruff", passed=False)
    r = Run(gates=gates)
    assert r.shape()[-2:] == [
        ("TaskStateChanged", "gating>failed", "secret found"),
        ("TaskStateChanged", "failed>escalated", "secret found"),
    ]
    assert r.git.commit_calls == []
    assert "CommitRecorded" not in [e.type for e in r.events]
    assert r.outcome is not None
    assert r.outcome.state == "escalated"
    assert r.outcome.last_event_id == r.events[-1].event_id


def _two_req_task() -> Task:
    task = _task()
    contract = task.contract.model_copy(update={"requirements": ["REQ-AUTH-001", "REQ-AUTH-002"]})
    return task.model_copy(update={"contract": contract})


def test_task068_ac6_uncovered_requirement_fails_a_passing_pytest_gate() -> None:
    # REQ-AUTH-002 is tagged only in a file the task did not change.
    markers = [
        MarkerLine(file="tests/auth/test_login.py", req=["REQ-AUTH-001"]),
        MarkerLine(file="tests/other/test_x.py", req=["REQ-AUTH-002"]),
    ]
    r = Run(task=_two_req_task(), gates={"pytest": _gate_output("pytest", markers=markers)})
    pytest_gate = _gate_events(r)[2]
    assert pytest_gate.payload["gate"] == "pytest"
    assert pytest_gate.payload["passed"] is False
    assert (
        "run_0002",
        "pytest.txt",
        "pytest text\nno tagged test in a changed file: REQ-AUTH-002\n",
    ) in r.run_files.calls
    assert r.shape()[-1] == ("TaskStateChanged", "gating>failed", "pytest")


def test_task068_ac6_lines_follow_contract_order_and_add_a_missing_line_break() -> None:
    out = GateOutput(passed=True, text="no newline", finding=False, marker_lines=[])
    r = Run(task=_two_req_task(), gates={"pytest": out})
    assert (
        "run_0002",
        "pytest.txt",
        "no newline\nno tagged test in a changed file: REQ-AUTH-001\n"
        "no tagged test in a changed file: REQ-AUTH-002\n",
    ) in r.run_files.calls


def test_task068_ac6_lines_are_added_when_pytest_itself_failed() -> None:
    out = _gate_output("pytest", passed=False, markers=[])
    r = Run(gates={"pytest": out})
    assert (
        "run_0002",
        "pytest.txt",
        "pytest text\nno tagged test in a changed file: REQ-AUTH-001\n",
    ) in r.run_files.calls
    assert _gate_events(r)[2].payload["passed"] is False


def test_task068_ac6_covered_requirements_leave_the_text_and_result_unchanged() -> None:
    r = Run(
        task=_two_req_task(),
        gates={
            "pytest": _gate_output(
                "pytest",
                markers=[
                    MarkerLine(file="tests/auth/test_login.py", req=["REQ-AUTH-001"]),
                    MarkerLine(file="app/auth/login.py", req=["REQ-AUTH-002"]),
                ],
            )
        },
    )
    assert ("run_0002", "pytest.txt", "pytest text\n") in r.run_files.calls
    assert _gate_events(r)[2].payload["passed"] is True
    assert r.outcome is not None
    assert r.outcome.state == "passed"
