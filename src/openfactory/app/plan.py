"""Plan use case, the planner call: one planner call with its single retry, recorded.

See docs/spec/phase1-spec.md ("Task contract": "Planning", "Plan checks"; "Domain model
and storage": "Streams and actors", "Event payloads", "Ids"; "Tech stack and repo layout")
and ADR-005. Each call is a run of its own: `AgentRunStarted`, the call, the checks, then
`AgentRunFinished`. A rejected reply is retried once with its rejections in the prompt; a
failed process is not retried. An accepted reply ends in `PlanCreated`.
The use case returns data and prints nothing.
"""

from collections.abc import Sequence
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from openfactory.app.planner_prompt import build_planner_prompt, context_hash
from openfactory.domain.contracts import PlannedTask, PlannerReply, TaskContract, complete_contract
from openfactory.domain.events import Event, EventType
from openfactory.domain.models import SpecSet
from openfactory.domain.payloads import (
    AgentRunFinishedPayload,
    AgentRunStartedPayload,
    PlanCreatedPayload,
)
from openfactory.domain.plan_checks import PlanRejection, check_plan, parse_reply, rejection_lines
from openfactory.domain.policy import Policy
from openfactory.domain.spec_hash import policy_hash
from openfactory.ports.event_recorder import EventRecorder
from openfactory.ports.llm_provider import LLMError, LLMProvider
from openfactory.ports.plans import Plans
from openfactory.ports.runs import Runs


class PlannerOutcome(StrEnum):
    created = "created"
    rejected = "rejected"
    failed = "failed"


class PlannerResult(BaseModel):
    """What one planner call, with its retry, ended in.

    `plan_id` and `tasks` are set when a plan was created, `rejections` (the second
    reply's) when both replies were rejected, and `error` (the whole text) when a call
    failed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: PlannerOutcome
    plan_id: str | None = None
    tasks: list[TaskContract] = []
    rejections: list[PlanRejection] = []
    error: str | None = None


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
            rejections = check_plan(parsed.tasks, spec)
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
) -> PlannerResult:
    attempt = _attempt(
        build_planner_prompt(spec, policy, tracked_files),
        spec,
        None,
        llm=llm,
        runs=runs,
        recorder=recorder,
    )
    if attempt.rejections:
        # The single retry: a second run, with the first reply's rejections in the prompt.
        attempt = _attempt(
            build_planner_prompt(spec, policy, tracked_files, rejections=attempt.rejections),
            spec,
            attempt.last_event_id,
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
