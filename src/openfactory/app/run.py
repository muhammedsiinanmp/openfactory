"""Run use case, one task: the per-task sequence and the events it records.

See docs/spec/phase1-spec.md ("Execution": "Per-task sequence", "Base and branches", "The
path check", "The commit", "Events of one task", "Adapter interface"; "Task state
machine"; "Domain model and storage": "Streams and actors", "Event payloads"; "Gates and
remediation") and ADR-014. `run_task` takes one `ready` task through the worktree, the
agent run, the path check, the `ruff`, `pytest` and `gitleaks` gates (with the pytest tag
rule), the `review` gate (one reviewer call through `LLMProvider`, retried once on a
rejected reply) and the commit, and records each step through the
`EventRecorder` port, every event pointing at the one before it. A `GitError` while the
task is `running` or `gating` fails the task with reason `git: <first line>`; one from
removing the worktree after a pass becomes the result's `warning`. `repair_plan` is the
repair of "Restart": it settles the tasks an interrupted `run` left in `running` or
`gating`, then promotes the `pending` tasks whose dependencies have passed. `run_plan` is
the whole of "`run`": the refusals, the repair, then the `ready` tasks one at a time in
ascending id (or the one `--task` names), promoting the `pending` tasks after each pass.
The use case returns data and prints nothing.
"""

from enum import StrEnum
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from openfactory.app.context_pack import build_context_pack
from openfactory.app.planner_prompt import context_hash
from openfactory.app.review_prompt import build_review_prompt
from openfactory.domain.commit_message import build_commit_message
from openfactory.domain.events import Event, EventType
from openfactory.domain.gates import GateOutput, ProcessGate
from openfactory.domain.models import SpecSet
from openfactory.domain.path_patterns import violating_paths
from openfactory.domain.payloads import (
    AgentRunFinishedPayload,
    AgentRunStartedPayload,
    CommitRecordedPayload,
    GateEvaluatedPayload,
    TaskStateChangedPayload,
)
from openfactory.domain.plan_checks import PlanRejection, rejection_lines
from openfactory.domain.plans import PlanRef, Task
from openfactory.domain.review import ReviewVerdict, parse_review_reply, review_file_text
from openfactory.domain.states import TRANSITIONS, TaskState
from openfactory.domain.tag_rule import tag_rule_lines, uncovered_requirements
from openfactory.ports.agent_executor import AgentExecutor
from openfactory.ports.event_recorder import EventRecorder
from openfactory.ports.gate_runner import GateRunner
from openfactory.ports.git_provider import GitError, GitProvider
from openfactory.ports.llm_provider import LLMError, LLMProvider
from openfactory.ports.plans import Plans
from openfactory.ports.run_files import RunFiles
from openfactory.ports.runs import Runs
from openfactory.ports.spec_versions import SpecVersions
from openfactory.ports.workspace_manager import WorkspaceManager

_RUNS_DIR = Path(".openfactory/runs")
_PATH_CHECK = "path_check"
_REVIEW = "review"
_PROCESS_GATES: tuple[ProcessGate, ...] = ("ruff", "pytest", "gitleaks")
_SECRET_FOUND = "secret found"


class TaskRunResult(BaseModel):
    """Where one task ended and the last event recorded for it.

    `state` is `passed`, `failed` or `escalated`. For a pass, `last_event_id` is the
    `gating` to `passed` event. `warning` is the line `run` writes when the worktree of a
    passed task could not be removed, else `None`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    state: TaskState
    last_event_id: UUID
    warning: str | None = None


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

    def result(self, warning: str | None = None) -> TaskRunResult:
        assert self._last is not None
        return TaskRunResult(
            task_id=self._task_id, state=self._state, last_event_id=self._last, warning=warning
        )


def _first_line(error: GitError) -> str:
    return str(error).splitlines()[0]


class _Review(BaseModel):
    """One reviewer run: the verdict, or the rejections or the process error and none."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: ReviewVerdict | None
    rejections: list[PlanRejection]
    error: str | None


def _review_attempt(
    task: Task, prompt: str, chain: _Chain, *, llm: LLMProvider, runs: Runs
) -> _Review:
    """Record one reviewer run of `task`, as a planner call is recorded."""
    run_id = runs.next_id()
    stream = f"run:{run_id}"
    chain.record(
        stream,
        EventType.AgentRunStarted,
        AgentRunStartedPayload(
            run_id=run_id,
            task_id=task.id,
            role="reviewer",
            runtime="claude-code",
            context_hash=context_hash(prompt),
        ),
    )
    try:
        reply = llm.complete(prompt, ReviewVerdict.model_json_schema())
    except LLMError as error:
        review = _Review(verdict=None, rejections=[], error=str(error))
        finished = AgentRunFinishedPayload(
            run_id=run_id,
            exit="timeout" if error.timeout else "error",
            model=None,
            tokens_in=None,
            tokens_out=None,
            cost_usd=None,
            duration_s=error.duration_s,
            error=review.error,
        )
    else:
        parsed = parse_review_reply(reply.structured)
        rejections = parsed.rejections
        review = _Review(
            verdict=parsed.verdict,
            rejections=rejections,
            error="\n".join(rejection_lines(rejections)) if rejections else None,
        )
        finished = AgentRunFinishedPayload(
            run_id=run_id,
            exit="ok",
            model=reply.model,
            tokens_in=reply.tokens_in,
            tokens_out=reply.tokens_out,
            cost_usd=reply.cost_usd,
            duration_s=reply.duration_s,
            error=review.error,
        )
    chain.record(stream, EventType.AgentRunFinished, finished)
    return review


class RepairResult(BaseModel):
    """What the Restart repair left for `run`.

    `warnings` are the lines `run` writes, in the order they arose. `last_event_ids` maps
    each task the repair recorded an event for to its last repair event, the causation of
    that task's next event in the same command.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    warnings: list[str]
    last_event_ids: dict[str, UUID]


def _promotable(tasks: list[Task]) -> list[str]:
    """Ids of the `pending` tasks whose dependencies have all passed, in ascending id."""
    passed = {task.id for task in tasks if task.state is TaskState.passed}
    return sorted(
        task.id
        for task in tasks
        if task.state is TaskState.pending and set(task.depends_on) <= passed
    )


def repair_plan(
    plan: PlanRef,
    *,
    workspace: WorkspaceManager,
    runs: Runs,
    plans: Plans,
    recorder: EventRecorder,
) -> RepairResult:
    """Repair the approved plan from the projections, as in "Restart", steps 1 to 3.

    Only one `run` works at a time, so a `gating` task holding a `CommitRecorded` was
    interrupted before `passed` and its commit is the plan's newest one. Each repair event
    has no `causation_id`.
    """
    tasks = {task.id: task for task in plans.tasks(plan.id)}
    latest = plans.latest_commit(plan.id)
    committed = latest.task_id if latest is not None else None
    warnings: list[str] = []
    last: dict[str, UUID] = {}

    def move(task: Task, to: TaskState, reason: str | None = None) -> None:
        chain = _Chain(task, recorder, None)
        chain.move(to, reason)
        last[task.id] = chain.result().last_event_id
        tasks[task.id] = task.model_copy(update={"state": to})

    in_flight = sorted(
        task_id
        for task_id, task in tasks.items()
        if task.state in (TaskState.running, TaskState.gating)
    )
    for task_id in in_flight:
        task = tasks[task_id]
        if task.state is TaskState.gating and task_id == committed:
            move(task, TaskState.passed)
            try:
                workspace.remove_worktree(task_id)
            except GitError as error:
                warnings.append(f"worktree of {task_id} not removed: {_first_line(error)}")
    for task_id in in_flight:
        task = tasks[task_id]
        if task.state is TaskState.passed:
            continue
        run_id = runs.unfinished_run(task_id)
        if run_id is not None:
            _Chain(task, recorder, None).record(
                f"run:{run_id}",
                EventType.AgentRunFinished,
                AgentRunFinishedPayload(
                    run_id=run_id,
                    exit="error",
                    model=None,
                    tokens_in=None,
                    tokens_out=None,
                    cost_usd=None,
                    duration_s=0,
                    error="interrupted",
                ),
            )
        move(task, TaskState.failed, "interrupted")
    for task_id in _promotable(list(tasks.values())):
        move(tasks[task_id], TaskState.ready)
    return RepairResult(warnings=warnings, last_event_ids=last)


def run_task(
    task: Task,
    plan: PlanRef,
    spec: SpecSet,
    *,
    causation_id: UUID | None = None,
    git: GitProvider,
    gates: GateRunner,
    workspace: WorkspaceManager,
    executor: AgentExecutor,
    llm: LLMProvider,
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
    try:
        base = latest.sha if latest is not None else git.head_commit()
        assert base is not None
        workspace.remove(task.id)
        worktree = workspace.create(task.id, base)
        tracked = git.tracked_files(worktree)
    except GitError as error:
        chain.move(TaskState.failed, f"git: {_first_line(error)}")
        return chain.result()
    pack = build_context_pack(task.contract, spec, tracked)

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
    try:
        # Every commit on the branch is the orchestrator's: an agent's commits are undone.
        if git.head_commit(worktree) != base:
            git.reset_soft(worktree, base)
        changed = git.stage_changes(worktree, base)
    except GitError as error:
        chain.move(TaskState.failed, f"git: {_first_line(error)}")
        return chain.result()
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

    failed: set[str] = set()
    finding = False
    for gate in _PROCESS_GATES:
        output = gates.run(gate, worktree, task.contract.limits.max_runtime_s)
        passed, text = output.passed, output.text
        if gate == "pytest":
            passed, text = _apply_tag_rule(output, changed, task)
        finding = finding or output.finding
        if not passed:
            failed.add(gate)
        chain.task_event(
            EventType.GateEvaluated,
            GateEvaluatedPayload(
                run_id=run_id,
                task_id=task.id,
                gate=gate,
                passed=passed,
                output_path=run_files.write(run_id, f"{gate}.txt", text).as_posix(),
            ),
        )
    if finding:
        chain.move(TaskState.failed, _SECRET_FOUND)
        chain.move(TaskState.escalated, _SECRET_FOUND)
        return chain.result()
    if failed:
        chain.move(TaskState.failed, next(g for g in task.contract.required_gates if g in failed))
        return chain.result()

    try:
        diff = git.staged_diff(worktree, base)
    except GitError as error:
        chain.move(TaskState.failed, f"git: {_first_line(error)}")
        return chain.result()
    review = _review_attempt(
        task, build_review_prompt(task.contract, diff), chain, llm=llm, runs=runs
    )
    if review.rejections:
        # The single retry: a second run, with the first reply's rejections in the prompt.
        review = _review_attempt(
            task,
            build_review_prompt(task.contract, diff, rejections=review.rejections),
            chain,
            llm=llm,
            runs=runs,
        )
    approved = review.verdict is not None and review.verdict.verdict == "approve"
    review_path = run_files.write(
        run_id, f"{_REVIEW}.txt", review_file_text(review.verdict, review.error)
    )
    chain.task_event(
        EventType.GateEvaluated,
        GateEvaluatedPayload(
            run_id=run_id,
            task_id=task.id,
            gate=_REVIEW,
            passed=approved,
            output_path=review_path.as_posix(),
        ),
    )
    if not approved:
        chain.move(TaskState.failed, _REVIEW)
        return chain.result()

    message = build_commit_message(task.contract, result.summary, run_id, plan.spec_version)
    try:
        sha = git.commit(worktree, message)
    except GitError as error:
        chain.move(TaskState.failed, f"git: {_first_line(error)}")
        return chain.result()
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
    try:
        workspace.remove_worktree(task.id)
    except GitError as error:
        return chain.result(f"worktree of {task.id} not removed: {_first_line(error)}")
    return chain.result()


def _apply_tag_rule(output: GateOutput, changed: list[str], task: Task) -> tuple[bool, str]:
    """The pytest gate's verdict and text once the tag rule is applied.

    When a requirement has no tagged test in a changed file, the gate fails and one line per
    such requirement is added to the text, after a line break if the text lacks one.
    """
    uncovered = uncovered_requirements(output.marker_lines, changed, task.contract)
    if not uncovered:
        return output.passed, output.text
    text = output.text
    if text and not text.endswith("\n"):
        text += "\n"
    return False, text + "".join(f"{line}\n" for line in tag_rule_lines(uncovered))


class RunRefusal(StrEnum):
    """Why `run` worked on no task; `cli.py` turns each into its line."""

    no_approved_plan = "no_approved_plan"
    no_commit = "no_commit"
    git_failed = "git_failed"
    tool_not_found = "tool_not_found"
    unknown_task = "unknown_task"
    not_ready = "not_ready"


class RunReport(BaseModel):
    """What one `run` did.

    `detail` is the first line of the git error, the missing tool, the unknown task id, or
    the state of a task that is not `ready`. `warnings` are the repair's lines; each task
    result keeps its own `warning`. `tasks` are in the order taken.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    refusal: RunRefusal | None = None
    detail: str | None = None
    warnings: list[str] = []
    tasks: list[TaskRunResult] = []


def run_plan(
    *,
    task_id: str | None = None,
    git: GitProvider,
    gates: GateRunner,
    workspace: WorkspaceManager,
    executor: AgentExecutor,
    llm: LLMProvider,
    run_files: RunFiles,
    runs: Runs,
    plans: Plans,
    versions: SpecVersions,
    recorder: EventRecorder,
) -> RunReport:
    """Refuse, or repair the approved plan and take its `ready` tasks, as in "`run`".

    With `task_id` only that task is taken; the tasks its pass makes `ready` are moved to
    `ready` and left for a later `run`.
    """
    plan = plans.approved()
    if plan is None:
        return RunReport(refusal=RunRefusal.no_approved_plan)
    try:
        head = git.head_commit()
    except GitError as error:
        return RunReport(refusal=RunRefusal.git_failed, detail=_first_line(error))
    if head is None:
        return RunReport(refusal=RunRefusal.no_commit)
    tool = gates.missing_tool()
    if tool is not None:
        return RunReport(refusal=RunRefusal.tool_not_found, detail=tool)

    repair = repair_plan(plan, workspace=workspace, runs=runs, plans=plans, recorder=recorder)
    spec = versions.spec_set(plan.spec_version)
    assert spec is not None
    causes = dict(repair.last_event_ids)
    results: list[TaskRunResult] = []

    def take(task: Task) -> None:
        result = run_task(
            task,
            plan,
            spec,
            causation_id=causes.get(task.id),
            git=git,
            gates=gates,
            workspace=workspace,
            executor=executor,
            llm=llm,
            run_files=run_files,
            runs=runs,
            plans=plans,
            recorder=recorder,
        )
        results.append(result)
        if result.state is not TaskState.passed:
            return
        tasks = {task.id: task for task in plans.tasks(plan.id)}
        for promoted in _promotable(list(tasks.values())):
            chain = _Chain(tasks[promoted], recorder, result.last_event_id)
            chain.move(TaskState.ready)
            causes[promoted] = chain.result().last_event_id

    if task_id is not None:
        task = next((t for t in plans.tasks(plan.id) if t.id == task_id), None)
        if task is None:
            return RunReport(
                refusal=RunRefusal.unknown_task, detail=task_id, warnings=repair.warnings
            )
        if task.state is not TaskState.ready:
            return RunReport(
                refusal=RunRefusal.not_ready, detail=task.state.value, warnings=repair.warnings
            )
        take(task)
    else:
        while ready := [t for t in plans.tasks(plan.id) if t.state is TaskState.ready]:
            take(min(ready, key=lambda t: t.id))
    return RunReport(warnings=repair.warnings, tasks=results)
