"""Impact use case: the refusals, the diff, the classifier call with its single retry, the
traversal and `ImpactComputed`.

See docs/spec/phase1-spec.md ("Spec diff and impact analysis": Steps 1 to 4, "Classifier
checks"; "Domain model and storage": "Streams and actors", "Event payloads"; "CLI
commands": "Output") and ADR-019. `impact` compares `from`, the approved plan's spec
version, with `to`, the latest approved one. When some requirement is `modified` it makes
one classifier call, recorded as a run with role `classifier` and no task, as a planner
call is: a rejected reply is retried once with its rejections in the prompt; a failed
process is not retried. A second rejected reply or a failed process ends the call with the
last run's `AgentRunFinished.error` and records no `ImpactComputed`. Otherwise the seeds go
to the traversal and `ImpactComputed` is recorded on `spec:<to_version>`.
The use case returns data and prints nothing.
"""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from openfactory.app.classifier_prompt import build_classifier_prompt
from openfactory.app.planner_prompt import context_hash
from openfactory.domain.classifier import (
    ChangeClass,
    ClassifierRejection,
    ClassifierReply,
    add_lost_criteria,
    check_classification,
    parse_classifier_reply,
)
from openfactory.domain.events import Event, EventType
from openfactory.domain.models import SpecSet
from openfactory.domain.payloads import (
    AdrImpact,
    AgentRunFinishedPayload,
    AgentRunStartedPayload,
    ImpactComputedPayload,
    RequirementImpact,
)
from openfactory.domain.plan_checks import rejection_lines
from openfactory.domain.spec_diff import SpecDiff, diff_specs
from openfactory.ports.event_recorder import EventRecorder
from openfactory.ports.llm_provider import LLMError, LLMProvider
from openfactory.ports.plans import Plans
from openfactory.ports.runs import Runs
from openfactory.ports.spec_versions import SpecVersions
from openfactory.ports.traces import Traces


class ImpactRefusal(StrEnum):
    no_approved_plan = "no_approved_plan"
    no_spec_change = "no_spec_change"


class ImpactResult(BaseModel):
    """What one `impact` ended in.

    `refusal` is set when it refused before any event, with `detail` the spec version for
    `no_spec_change`; `error` (the whole text of the last classifier run's
    `AgentRunFinished.error`) when the classifier call failed; otherwise `impact` is the
    recorded `ImpactComputed` payload.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    refusal: ImpactRefusal | None = None
    detail: str | None = None
    impact: ImpactComputedPayload | None = None
    error: str | None = None


class _Attempt(BaseModel):
    """One recorded classifier run: `changes` when its reply was accepted, else `error`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    last_event_id: UUID
    changes: list[ChangeClass] | None = None
    rejections: list[ClassifierRejection] = []
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
    diff: SpecDiff,
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
                role="classifier",
                runtime="claude-code",
                context_hash=context_hash(prompt),
            ),
            causation_id,
        )
    )

    changes: list[ChangeClass] | None = None
    rejections: list[ClassifierRejection] = []
    try:
        reply = llm.complete(prompt, ClassifierReply.model_json_schema())
    except LLMError as error:
        finished_payload = AgentRunFinishedPayload(
            run_id=run_id,
            exit="timeout" if error.timeout else "error",
            model=None,
            tokens_in=None,
            tokens_out=None,
            cost_usd=None,
            duration_s=error.duration_s,
            error=str(error),
        )
    else:
        parsed = parse_classifier_reply(reply.structured)
        rejections = parsed.rejections
        if parsed.changes is not None:
            rejections = check_classification(parsed.changes, diff)
        if not rejections:
            changes = parsed.changes
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
        changes=changes,
        rejections=rejections,
        error=finished_payload.error,
    )


def _classify(
    old: SpecSet,
    new: SpecSet,
    diff: SpecDiff,
    *,
    llm: LLMProvider,
    runs: Runs,
    recorder: EventRecorder,
) -> _Attempt:
    attempt = _attempt(
        build_classifier_prompt(old, new, diff), diff, None, llm=llm, runs=runs, recorder=recorder
    )
    if attempt.rejections:
        # The single retry: a second run, with the first reply's rejections in the prompt.
        attempt = _attempt(
            build_classifier_prompt(old, new, diff, attempt.rejections),
            diff,
            attempt.last_event_id,
            llm=llm,
            runs=runs,
            recorder=recorder,
        )
    return attempt


def _requirements(diff: SpecDiff, changes: list[ChangeClass]) -> list[RequirementImpact]:
    """Each requirement that is not unchanged, sorted by id; a modified one is classified."""
    classes = {c.req_id: c for c in add_lost_criteria(changes, diff)}
    result: list[RequirementImpact] = []
    for r in sorted(diff.requirements, key=lambda r: r.id):
        if r.change == "unchanged":
            continue
        c = classes.get(r.id) if r.change == "modified" else None
        result.append(
            RequirementImpact(
                id=r.id,
                change=r.change,
                kind=c.kind if c else None,
                rationale=c.rationale if c else None,
                obsolete_criteria=c.obsolete_criteria if c else [],
                new_work=sorted(c.new_work) if c else [],
            )
        )
    return result


def compute_impact(
    *,
    versions: SpecVersions,
    plans: Plans,
    runs: Runs,
    traces: Traces,
    llm: LLMProvider,
    recorder: EventRecorder,
) -> ImpactResult:
    approved_plan = plans.approved()
    if approved_plan is None:
        return ImpactResult(refusal=ImpactRefusal.no_approved_plan)
    latest = versions.latest_approved()
    # An approved plan's spec version is approved, so there is a latest approved one.
    assert latest is not None
    from_version = approved_plan.spec_version
    if latest.id == from_version:
        return ImpactResult(refusal=ImpactRefusal.no_spec_change, detail=from_version)

    old = versions.spec_set(from_version)
    new = versions.spec_set(latest.id)
    # An approved version always has a stored spec set.
    assert old is not None and new is not None
    diff = diff_specs(old, new)

    run_id: str | None = None
    causation_id: UUID | None = None
    changes: list[ChangeClass] = []
    if any(r.change == "modified" for r in diff.requirements):
        attempt = _classify(old, new, diff, llm=llm, runs=runs, recorder=recorder)
        if attempt.changes is None:
            return ImpactResult(error=attempt.error)
        run_id = attempt.run_id
        causation_id = attempt.last_event_id
        changes = attempt.changes

    requirements = _requirements(diff, changes)
    seeds = [
        r.id
        for r in requirements
        if r.change in ("removed", "deprecated") or r.kind in ("behavioral", "replacement")
    ]
    traversal = traces.impact_traversal(approved_plan.id, seeds)
    payload = ImpactComputedPayload(
        from_version=from_version,
        to_version=latest.id,
        run_id=run_id,
        requirements=requirements,
        adrs=[
            AdrImpact(id=a.id, change=a.change)
            for a in sorted(diff.adrs, key=lambda a: a.id)
            if a.change != "unchanged"
        ],
        tasks=traversal.tasks,
        downstream=traversal.downstream,
        files=traversal.files,
        tests=traversal.tests,
    )
    recorder.record(_event(f"spec:{latest.id}", EventType.ImpactComputed, payload, causation_id))
    return ImpactResult(impact=payload)
