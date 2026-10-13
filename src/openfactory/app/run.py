"""Run use case, one task: the per-task sequence and the events it records.

See docs/spec/phase1-spec.md ("Execution": "Per-task sequence", "Base and branches", "The
path check", "The commit", "Events of one task", "Adapter interface"; "Task state
machine"; "Domain model and storage": "Streams and actors", "Event payloads"; "Gates and
remediation") and ADR-014. `run_task` takes one `ready` task through the worktree, the
agent run, the path check and the commit, and records each step through the
`EventRecorder` port, every event pointing at the one before it. A `GitError` from a port
call propagates. The use case returns data and prints nothing.
"""

from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from openfactory.app.context_pack import build_context_pack
from openfactory.app.planner_prompt import context_hash
from openfactory.domain.commit_message import build_commit_message
from openfactory.domain.events import Event, EventType
from openfactory.domain.models import SpecSet
from openfactory.domain.path_patterns import violating_paths
from openfactory.domain.payloads import (
    AgentRunFinishedPayload,
    AgentRunStartedPayload,
    CommitRecordedPayload,
    GateEvaluatedPayload,
    TaskStateChangedPayload,
)
from openfactory.domain.plans import PlanRef, Task
from openfactory.domain.states import TRANSITIONS, TaskState
from openfactory.ports.agent_executor import AgentExecutor
from openfactory.ports.event_recorder import EventRecorder
from openfactory.ports.git_provider import GitProvider
from openfactory.ports.plans import Plans
from openfactory.ports.run_files import RunFiles
from openfactory.ports.runs import Runs
from openfactory.ports.workspace_manager import WorkspaceManager

_RUNS_DIR = Path(".openfactory/runs")
_PATH_CHECK = "path_check"


class TaskRunResult(BaseModel):
    """Where one task ended and the last event recorded for it.

    `state` is `passed`, `failed` or `escalated`. For a pass, `last_event_id` is the
    `gating` to `passed` event.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    state: TaskState
    last_event_id: UUID


class _Chain:
    """Records the events of one task, each pointing at the one recorded before it."""

    def __init__(self, task: Task, recorder: EventRecorder, causation_id: UUID | None) -> None:
        self._task_id = task.id
        self._recorder = recorder
        self._last = causation_id
        self._state = task.state

    def record(self, stream: str, type: EventType, payload: BaseModel) -> None:
        stored = self._recorder.record(
            Event.new(
                stream=stream,
                type=type,
                payload=payload.model_dump(mode="json"),
                actor="orchestrator",
                causation_id=self._last,
            )
        )
        self._last = stored.event_id

    def task_event(self, type: EventType, payload: BaseModel) -> None:
        self.record(f"task:{self._task_id}", type, payload)

    def move(self, to: TaskState, reason: str | None = None) -> None:
        if to not in TRANSITIONS[self._state]:
            raise ValueError(f"{self._task_id}: no transition from {self._state} to {to}")
        # Built from a dict: `from` is a Python keyword, and pyright rejects `from_=`.
        payload = TaskStateChangedPayload.model_validate(
            {"task_id": self._task_id, "from": self._state, "to": to, "reason": reason}
        )
        self.task_event(EventType.TaskStateChanged, payload)
        self._state = to

    def result(self) -> TaskRunResult:
        assert self._last is not None
        return TaskRunResult(task_id=self._task_id, state=self._state, last_event_id=self._last)


def run_task(
    task: Task,
    plan: PlanRef,
    spec: SpecSet,
    *,
    causation_id: UUID | None = None,
    git: GitProvider,
    workspace: WorkspaceManager,
    executor: AgentExecutor,
    run_files: RunFiles,
    runs: Runs,
    plans: Plans,
    recorder: EventRecorder,
) -> TaskRunResult:
    """Run the per-task sequence on `task` and record its events.

    `spec` is the stored set of the plan's spec version. `causation_id` is the id of the
    event recorded just before for this task in the same command, or `None`.
    """
    chain = _Chain(task, recorder, causation_id)
    chain.move(TaskState.running)

    latest = plans.latest_commit(plan.id)
    base = latest.sha if latest is not None else git.head_commit()
    assert base is not None
    workspace.remove(task.id)
    worktree = workspace.create(task.id, base)
    pack = build_context_pack(task.contract, spec, git.tracked_files(worktree))

    run_id = runs.next_id()
    run_stream = f"run:{run_id}"
    chain.record(
        run_stream,
        EventType.AgentRunStarted,
        AgentRunStartedPayload(
            run_id=run_id,
            task_id=task.id,
            role="implementer",
            runtime="claude-code",
            context_hash=context_hash(pack),
        ),
    )
    result = executor.run(task.contract, pack, worktree, _RUNS_DIR / run_id)
    chain.record(
        run_stream,
        EventType.AgentRunFinished,
        AgentRunFinishedPayload(run_id=run_id, **result.model_dump(exclude={"summary"})),
    )
    if result.exit != "ok":
        chain.move(TaskState.failed, f"run {result.exit}")
        return chain.result()

    chain.move(TaskState.gating)
    changed = git.stage_changes(worktree, base)
    if not changed:
        chain.move(TaskState.failed, "no changes")
        return chain.result()

    violations = violating_paths(changed, task.contract)
    output_path: str | None = None
    if violations:
        text = "".join(f"{path}\n" for path in violations)
        output_path = run_files.write(run_id, f"{_PATH_CHECK}.txt", text).as_posix()
    chain.task_event(
        EventType.GateEvaluated,
        GateEvaluatedPayload(
            run_id=run_id,
            task_id=task.id,
            gate=_PATH_CHECK,
            passed=not violations,
            output_path=output_path,
        ),
    )
    if violations:
        chain.move(TaskState.failed, _PATH_CHECK)
        chain.move(TaskState.escalated, "path violation")
        return chain.result()

    message = build_commit_message(task.contract, result.summary, run_id, plan.spec_version)
    sha = git.commit(worktree, message)
    chain.task_event(
        EventType.CommitRecorded,
        CommitRecordedPayload(
            sha=sha,
            task_id=task.id,
            run_id=run_id,
            branch=f"openfactory/{task.id}",
            spec_version=plan.spec_version,
            files=sorted(changed),
        ),
    )
    chain.move(TaskState.passed)
    workspace.remove_worktree(task.id)
    return chain.result()
