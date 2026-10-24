"""Plan use case: the entry with its refusals, then the planner call with its single retry.

See docs/spec/phase1-spec.md ("Task contract": "Planning", "Plan checks"; "Spec input
format": "Policies"; "CLI commands": "Output"; "Domain model and storage": "Streams and
actors", "Event payloads", "Ids"; "Tech stack and repo layout"), ADR-005 and ADR-013.
The `plan` command is two calls (ADR-013): `prepare_plan` checks the three refusals and
returns the planning inputs with the `spec files differ` flag; `create_plan` reads the
tracked files and the task ids in use, and calls `run_planner`, which checks every reply
against those ids (`task-id-in-use`). The caller keeps their order and prints the warning
between them. `replan` (`app/replan.py`) makes the same call through `run_planner`, with
its own prompt builder and the untouched tasks for the plan checks' replan rules. Each
planner call is a run of its own: `AgentRunStarted`, the call, the checks, then
`AgentRunFinished`. A rejected reply is retried once with its rejections in the prompt; a
failed process is not retried. An accepted reply ends in `PlanCreated`.
The use case returns data and prints nothing.
"""

from collections.abc import Callable, Collection, Sequence
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from openfactory.app.planner_prompt import build_planner_prompt, context_hash
from openfactory.app.spec_loader import load_policy, load_spec
from openfactory.domain.contracts import PlannedTask, PlannerReply, TaskContract, complete_contract
from openfactory.domain.events import Event, EventType
from openfactory.domain.models import SpecSet
from openfactory.domain.payloads import (
    AgentRunFinishedPayload,
    AgentRunStartedPayload,
    PlanCreatedPayload,
)
from openfactory.domain.plan_checks import PlanRejection, check_plan, parse_reply, rejection_lines
from openfactory.domain.plans import Task
from openfactory.domain.policy import Policy
from openfactory.domain.spec_hash import content_hash, policy_hash
from openfactory.ports.event_recorder import EventRecorder
from openfactory.ports.git_provider import GitError, GitProvider
from openfactory.ports.llm_provider import LLMError, LLMProvider
from openfactory.ports.plans import Plans
from openfactory.ports.runs import Runs
from openfactory.ports.spec_files import SpecFiles
from openfactory.ports.spec_versions import SpecVersions


class PlannerOutcome(StrEnum):
    created = "created"
    rejected = "rejected"
    failed = "failed"
    # Only `create_plan` returns this; `run_planner` never does.
    git_failed = "git_failed"


class PlannerResult(BaseModel):
    """What one planner call, with its retry, ended in.

    `plan_id` and `tasks` are set when a plan was created, `rejections` (the second
    reply's) when both replies were rejected, and `error` (the whole text) when a call
    failed or, for `git_failed`, when the tracked files could not be read.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: PlannerOutcome
    plan_id: str | None = None
    tasks: list[TaskContract] = []
    rejections: list[PlanRejection] = []
    error: str | None = None


class PlanRefusal(StrEnum):
    no_approved_spec = "no_approved_spec"
    invalid_policy = "invalid_policy"
    approved_plan = "approved_plan"


class PlanRefused(BaseModel):
    """Why `plan` does not run. `plan_id` is set only for `approved_plan`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: PlanRefusal
    plan_id: str | None = None


class PlanInputs(BaseModel):
    """What the planner call works from: the approved version's stored spec set, not the files."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: str
    spec: SpecSet
    policy: Policy
    spec_files_differ: bool


class _Attempt(BaseModel):
    """One recorded run: exactly one of `tasks`, `rejections` and `error` says how it ended."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    last_event_id: UUID
    tasks: list[PlannedTask] | None = None
    rejections: list[PlanRejection] = []
    error: str | None = None


def _event(stream: str, type: EventType, payload: BaseModel, causation_id: UUID | None) -> Event:
    return Event.new(
        stream=stream,
        type=type,
        payload=payload.model_dump(mode="json"),
        actor="orchestrator",
        causation_id=causation_id,
    )


def _attempt(
    prompt: str,
    spec: SpecSet,
    causation_id: UUID | None,
    ids_in_use: Collection[str],
    untouched: Sequence[Task],
    *,
    llm: LLMProvider,
    runs: Runs,
    recorder: EventRecorder,
) -> _Attempt:
    run_id = runs.next_id()
    stream = f"run:{run_id}"
    started = recorder.record(
        _event(
            stream,
            EventType.AgentRunStarted,
            AgentRunStartedPayload(
                run_id=run_id,
                task_id=None,
                role="planner",
                runtime="claude-code",
                context_hash=context_hash(prompt),
            ),
            causation_id,
        )
    )

    tasks: list[PlannedTask] | None = None
    rejections: list[PlanRejection] = []
    failure: str | None = None
    try:
        reply = llm.complete(prompt, PlannerReply.model_json_schema())
    except LLMError as error:
        failure = str(error)
        finished_payload = AgentRunFinishedPayload(
            run_id=run_id,
            exit="timeout" if error.timeout else "error",
            model=None,
            tokens_in=None,
            tokens_out=None,
            cost_usd=None,
            duration_s=error.duration_s,
            error=failure,
        )
    else:
        parsed = parse_reply(reply.structured)
        rejections = parsed.rejections
        if parsed.tasks is not None:
            rejections = check_plan(parsed.tasks, spec, ids_in_use=ids_in_use, untouched=untouched)
        if not rejections:
            tasks = parsed.tasks
        finished_payload = AgentRunFinishedPayload(
            run_id=run_id,
            exit="ok",
            model=reply.model,
            tokens_in=reply.tokens_in,
            tokens_out=reply.tokens_out,
            cost_usd=reply.cost_usd,
            duration_s=reply.duration_s,
            error="\n".join(rejection_lines(rejections)) if rejections else None,
        )

    finished = recorder.record(
        _event(stream, EventType.AgentRunFinished, finished_payload, started.event_id)
    )
    return _Attempt(
        run_id=run_id,
        last_event_id=finished.event_id,
        tasks=tasks,
        rejections=rejections,
        error=failure,
    )


def run_planner(
    spec_version: str,
    spec: SpecSet,
    policy: Policy,
    tracked_files: Sequence[str],
    *,
    llm: LLMProvider,
    runs: Runs,
    plans: Plans,
    recorder: EventRecorder,
    ids_in_use: Collection[str] = frozenset(),
    untouched: Sequence[Task] = (),
    build_prompt: Callable[[Sequence[PlanRejection]], str] | None = None,
) -> PlannerResult:
    """The planner call with its single retry, then `PlanCreated` for an accepted reply.

    `build_prompt` makes the prompt from the rejections to retry with (none on the first
    attempt); without it the prompt is the planner prompt. `untouched` goes to the plan
    checks on both attempts.
    """

    def prompt(rejections: Sequence[PlanRejection]) -> str:
        if build_prompt is not None:
            return build_prompt(rejections)
        return build_planner_prompt(spec, policy, tracked_files, rejections=rejections)

    attempt = _attempt(
        prompt(()),
        spec,
        None,
        ids_in_use,
        untouched,
        llm=llm,
        runs=runs,
        recorder=recorder,
    )
    if attempt.rejections:
        # The single retry: a second run, with the first reply's rejections in the prompt.
        attempt = _attempt(
            prompt(attempt.rejections),
            spec,
            attempt.last_event_id,
            ids_in_use,
            untouched,
            llm=llm,
            runs=runs,
            recorder=recorder,
        )

    if attempt.error is not None:
        return PlannerResult(outcome=PlannerOutcome.failed, error=attempt.error)
    if attempt.tasks is None:
        return PlannerResult(outcome=PlannerOutcome.rejected, rejections=attempt.rejections)

    plan_id = plans.next_id()
    contracts = sorted(
        (complete_contract(task, policy) for task in attempt.tasks),
        key=lambda contract: contract.task_id,
    )
    recorder.record(
        _event(
            f"plan:{plan_id}",
            EventType.PlanCreated,
            PlanCreatedPayload(
                plan_id=plan_id,
                spec_version=spec_version,
                policy_hash=policy_hash(policy),
                run_id=attempt.run_id,
                tasks=contracts,
            ),
            attempt.last_event_id,
        )
    )
    return PlannerResult(outcome=PlannerOutcome.created, plan_id=plan_id, tasks=contracts)


def prepare_plan(
    files: SpecFiles, versions: SpecVersions, plans: Plans
) -> PlanRefused | PlanInputs:
    """The entry of `plan`: the first refusal that applies, or the planning inputs.

    The refusals are checked in the spec's order: no approved spec version, an invalid
    policy (a missing file included), an approved plan for any spec version. The spec
    files are loaded only after them, for the `spec_files_differ` flag. Records nothing.
    """
    approved = versions.latest_approved()
    if approved is None:
        return PlanRefused(reason=PlanRefusal.no_approved_spec)
    policy = load_policy(files).policy
    if policy is None:
        return PlanRefused(reason=PlanRefusal.invalid_policy)
    approved_plan = plans.approved()
    if approved_plan is not None:
        return PlanRefused(reason=PlanRefusal.approved_plan, plan_id=approved_plan.id)

    loaded = load_spec(files).spec
    spec = versions.spec_set(approved.id)
    # An approved version always has a stored spec set.
    assert spec is not None
    return PlanInputs(
        spec_version=approved.id,
        spec=spec,
        policy=policy,
        spec_files_differ=loaded is None or content_hash(loaded) != approved.hash,
    )


def create_plan(
    inputs: PlanInputs,
    *,
    git: GitProvider,
    llm: LLMProvider,
    runs: Runs,
    plans: Plans,
    recorder: EventRecorder,
) -> PlannerResult:
    """Read the tracked files, then make the planner call with what `prepare_plan` returned.

    A `GitError` is returned as `git_failed` with its whole text, before any run starts.
    The task ids in use are read once, after the tracked files, for both attempts.
    """
    try:
        tracked_files = git.tracked_files()
    except GitError as error:
        return PlannerResult(outcome=PlannerOutcome.git_failed, error=str(error))
    return run_planner(
        inputs.spec_version,
        inputs.spec,
        inputs.policy,
        tracked_files,
        llm=llm,
        runs=runs,
        plans=plans,
        recorder=recorder,
        ids_in_use=plans.task_ids_in_use(),
    )
