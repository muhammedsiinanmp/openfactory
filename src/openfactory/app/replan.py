"""Replan use case: the entry with its refusals, then the planner call for the new tasks.

See docs/spec/phase1-spec.md ("Spec diff and impact analysis": "Step 3: traversal",
"Step 5: replan"; "Task contract": "Plan checks"; "CLI commands": "Output"; "Tech stack and
repo layout"), ADR-013 and ADR-019. The `replan` command is two calls, as `plan` is
(ADR-013): `prepare_replan` checks the first four refusals and returns the replan inputs
with the `spec files differ` flag; `create_replan` reads the tracked files, the task ids in
use and the approved plan's tasks, and calls `run_planner` with the replan prompt and the
untouched tasks. The latest `ImpactComputed` from the approved plan's spec version is read
from the stream `spec:<latest approved id>` through `EventStore`, which nothing here
appends to. An accepted reply ends in a draft `PlanCreated` holding only the new tasks;
nothing is invalidated. The use case returns data and prints nothing.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from openfactory.app.plan import PlannerOutcome, PlannerResult, run_planner
from openfactory.app.replan_prompt import build_replan_prompt, untouched_tasks
from openfactory.app.spec_loader import load_policy, load_spec
from openfactory.domain.events import EventType
from openfactory.domain.models import SpecSet
from openfactory.domain.payloads import ImpactComputedPayload
from openfactory.domain.policy import Policy
from openfactory.domain.spec_hash import content_hash
from openfactory.ports.event_recorder import EventRecorder
from openfactory.ports.event_store import EventStore
from openfactory.ports.git_provider import GitError, GitProvider
from openfactory.ports.llm_provider import LLMProvider
from openfactory.ports.plans import Plans
from openfactory.ports.runs import Runs
from openfactory.ports.spec_files import SpecFiles
from openfactory.ports.spec_versions import SpecVersions


class ReplanRefusal(StrEnum):
    no_approved_plan = "no_approved_plan"
    no_impact = "no_impact"
    nothing_to_replan = "nothing_to_replan"
    invalid_policy = "invalid_policy"


class ReplanRefused(BaseModel):
    """Why `replan` does not run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: ReplanRefusal


class ReplanInputs(BaseModel):
    """What the replan's planner call works from: the latest approved version's stored set."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    plan_id: str
    spec_version: str
    spec: SpecSet
    policy: Policy
    impact: ImpactComputedPayload
    spec_files_differ: bool


def _latest_impact(
    events: EventStore, to_version: str, from_version: str
) -> ImpactComputedPayload | None:
    """The last `ImpactComputed` in `seq` order on `spec:<to_version>` from `from_version`."""
    latest: ImpactComputedPayload | None = None
    for event in events.read(f"spec:{to_version}"):
        if event.type != EventType.ImpactComputed:
            continue
        payload = ImpactComputedPayload.model_validate(event.payload)
        if payload.from_version == from_version:
            latest = payload
    return latest


def prepare_replan(
    files: SpecFiles, versions: SpecVersions, plans: Plans, events: EventStore
) -> ReplanRefused | ReplanInputs:
    """The entry of `replan`: the first refusal that applies, or the replan inputs.

    The refusals are checked in the spec's order: no approved plan, no matching
    `ImpactComputed`, nothing to replan (the latest such event lists no task and no
    `added` requirement), an invalid policy (a missing file included). The spec files are
    loaded only after them, for the `spec_files_differ` flag. Records nothing.
    """
    approved_plan = plans.approved()
    if approved_plan is None:
        return ReplanRefused(reason=ReplanRefusal.no_approved_plan)
    latest = versions.latest_approved()
    # An approved plan is always for an approved spec version.
    assert latest is not None
    impact = _latest_impact(events, latest.id, approved_plan.spec_version)
    if impact is None:
        return ReplanRefused(reason=ReplanRefusal.no_impact)
    if not impact.tasks and not any(r.change == "added" for r in impact.requirements):
        return ReplanRefused(reason=ReplanRefusal.nothing_to_replan)
    policy = load_policy(files).policy
    if policy is None:
        return ReplanRefused(reason=ReplanRefusal.invalid_policy)

    loaded = load_spec(files).spec
    spec = versions.spec_set(latest.id)
    # An approved version always has a stored spec set.
    assert spec is not None
    return ReplanInputs(
        plan_id=approved_plan.id,
        spec_version=latest.id,
        spec=spec,
        policy=policy,
        impact=impact,
        spec_files_differ=loaded is None or content_hash(loaded) != latest.hash,
    )


def create_replan(
    inputs: ReplanInputs,
    *,
    git: GitProvider,
    llm: LLMProvider,
    runs: Runs,
    plans: Plans,
    recorder: EventRecorder,
) -> PlannerResult:
    """Read the tracked files, then make the planner call with the replan prompt.

    A `GitError` is returned as `git_failed` with its whole text, before anything else is
    read. The task ids in use and the approved plan's tasks are read once, after the
    tracked files, for both attempts.
    """
    try:
        tracked_files = git.tracked_files()
    except GitError as error:
        return PlannerResult(outcome=PlannerOutcome.git_failed, error=str(error))
    ids_in_use = plans.task_ids_in_use()
    plan_tasks = plans.tasks(inputs.plan_id)
    return run_planner(
        inputs.spec_version,
        inputs.spec,
        inputs.policy,
        tracked_files,
        llm=llm,
        runs=runs,
        plans=plans,
        recorder=recorder,
        ids_in_use=ids_in_use,
        untouched=untouched_tasks(plan_tasks, inputs.impact),
        build_prompt=lambda rejections: build_replan_prompt(
            inputs.spec,
            inputs.policy,
            tracked_files,
            inputs.impact,
            plan_tasks,
            rejections,
        ),
    )
