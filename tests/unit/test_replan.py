"""TASK-102: the `replan` use case (docs/tasks/TASK-102-replan-use-case.md).

Driven through in-memory fakes of SpecFiles, SpecVersions, Plans, EventStore, GitProvider,
LLMProvider, Runs and EventRecorder. The approved plan is on sv_01 and the latest approved
version is sv_02. Tasks: AUTH-001 passed and untouched; AUTH-002 passed and impacted;
AUTH-003 pending and downstream; AUTH-004 abandoned and untouched.
"""

import ast
from pathlib import Path
from typing import Any

import pytest

from openfactory.app import plan as plan_module
from openfactory.app.plan import PlannerOutcome, run_planner
from openfactory.app.planner_prompt import context_hash
from openfactory.app.replan import (
    ReplanInputs,
    ReplanRefusal,
    ReplanRefused,
    create_replan,
    prepare_replan,
)
from openfactory.app.replan_prompt import build_replan_prompt, untouched_tasks
from openfactory.app.spec_loader import load_spec
from openfactory.domain.contracts import PlannedTask, complete_contract
from openfactory.domain.events import Event, EventType, StoredEvent
from openfactory.domain.llm import LLMReply
from openfactory.domain.models import AcceptanceCriterion, Adr, AdrStatus, Requirement, SpecSet
from openfactory.domain.payloads import (
    ImpactComputedPayload,
    PlanCreatedPayload,
    RequirementImpact,
)
from openfactory.domain.plan_checks import PlanRejection, PlanRule, check_plan, rejection_lines
from openfactory.domain.plans import PlanRef, Task
from openfactory.domain.policy import Policy
from openfactory.domain.spec_hash import content_hash
from openfactory.domain.spec_versions import SpecVersionRef
from openfactory.domain.states import TaskState
from openfactory.ports.git_provider import GitError
from openfactory.ports.llm_provider import LLMError

REPLAN_PY = Path(__file__).resolve().parents[2] / "src" / "openfactory" / "app" / "replan.py"
FILES = ["app/main.py", "tests/test_main.py"]
POLICY = Policy(forbidden_paths=["secrets/**"])
POLICY_TEXT = 'forbidden_paths: ["secrets/**"]\n'
PLAN_ID = "plan_07"
FIRST_RUN = 5
STARTED, FINISHED, CREATED = (
    EventType.AgentRunStarted,
    EventType.AgentRunFinished,
    EventType.PlanCreated,
)

REQUIREMENTS_TEXT = """\
components: [auth]
requirements:
  - id: REQ-AUTH-001
    title: One
    statement: s1
    priority: must
    components: [auth]
    acceptance_criteria:
      - id: AC-AUTH-001-1
        text: c1
      - id: AC-AUTH-001-2
        text: c2
  - id: REQ-AUTH-002
    title: Two
    statement: s2
    priority: must
    components: [auth]
    acceptance_criteria:
      - id: AC-AUTH-002-1
        text: c1
  - id: REQ-AUTH-003
    title: Three
    statement: s3
    priority: must
    components: [auth]
    acceptance_criteria:
      - id: AC-AUTH-003-1
        text: c1
"""


class FakeSpecFiles:
    def __init__(self, files: dict[str, str]) -> None:
        self.files = files
        self.reads: list[str] = []

    def read(self, path: str) -> str | None:
        self.reads.append(path)
        return self.files.get(path)

    def list_adrs(self) -> list[str]:
        return []


def spec_files(
    *, requirements: str | None = REQUIREMENTS_TEXT, policy: str | None = POLICY_TEXT
) -> FakeSpecFiles:
    files: dict[str, str] = {}
    if requirements is not None:
        files["requirements.yaml"] = requirements
    if policy is not None:
        files["policies.yaml"] = policy
    return FakeSpecFiles(files)


def stored_set() -> SpecSet:
    spec = load_spec(spec_files()).spec
    assert spec is not None
    return spec


def make_req(n: int, criteria: tuple[int, ...], *, deprecated: bool = False) -> Requirement:
    return Requirement(
        id=f"REQ-AUTH-00{n}",
        title=f"t{n}",
        statement="s",
        priority="must",
        components=["auth"],
        acceptance_criteria=[
            AcceptanceCriterion(id=f"AC-AUTH-00{n}-{c}", text="c") for c in criteria
        ],
        deprecated=deprecated,
    )


def spec_with(*reqs: Requirement) -> SpecSet:
    return SpecSet(
        components=["auth"],
        requirements=list(reqs),
        adrs=[Adr(id="ADR-001", status=AdrStatus.accepted, body="b")],
    )


SPEC = spec_with(make_req(1, (1, 2)), make_req(2, (1,)), make_req(3, (1,)))


class FakeVersions:
    def __init__(self, stored: SpecSet | None = None, latest: str = "sv_02") -> None:
        self.stored = stored or stored_set()
        self.latest = latest
        self.spec_set_ids: list[str] = []

    def latest_approved(self) -> SpecVersionRef:
        return SpecVersionRef(id=self.latest, hash=content_hash(self.stored))

    def current_draft(self) -> SpecVersionRef | None:
        return None

    def next_id(self) -> str:
        return "sv_99"

    def spec_set(self, version_id: str) -> SpecSet | None:
        self.spec_set_ids.append(version_id)
        return self.stored


def task(n: int, state: TaskState, reqs: list[str], acs: list[str], deps: list[str]) -> Task:
    contract = complete_contract(
        PlannedTask(
            task_id=f"AUTH-00{n}",
            objective=f"Do {n}",
            requirements=reqs,
            acceptance_criteria=acs,
            depends_on=deps,
            components=["auth"],
            role="implementer",
            allowed_paths=["src/auth/**"],
        ),
        POLICY,
    )
    return Task(
        id=f"AUTH-00{n}",
        plan_id="plan_03",
        state=state,
        attempt=1,
        contract=contract,
        depends_on=sorted(deps),
    )


PLAN_TASKS = [
    task(1, TaskState.passed, ["REQ-AUTH-001"], ["AC-AUTH-001-1", "AC-AUTH-001-2"], []),
    task(2, TaskState.passed, ["REQ-AUTH-002"], ["AC-AUTH-002-1"], []),
    task(3, TaskState.pending, ["REQ-AUTH-002"], ["AC-AUTH-002-1"], ["AUTH-002"]),
    task(4, TaskState.abandoned, ["REQ-AUTH-001"], ["AC-AUTH-001-1"], []),
]


APPROVED = PlanRef(id="plan_03", spec_version="sv_01")


class FakePlans:
    def __init__(self, approved: PlanRef | None = APPROVED) -> None:
        self._approved = approved
        self.in_use = ["AUTH-001", "AUTH-002", "AUTH-003", "AUTH-004", "AUTH-009"]
        self.in_use_calls = 0
        self.tasks_calls: list[str] = []
        self.plan_tasks = PLAN_TASKS

    def current_draft(self) -> PlanRef | None:
        return None

    def approved(self) -> PlanRef | None:
        return self._approved

    def next_id(self) -> str:
        return PLAN_ID

    def tasks(self, plan_id: str) -> list[Task]:
        self.tasks_calls.append(plan_id)
        return self.plan_tasks

    def live_tasks_referencing(self, requirement_id: str) -> list[str]:
        return []

    def task_ids_in_use(self) -> list[str]:
        self.in_use_calls += 1
        return self.in_use


def impact(
    *,
    from_version: str = "sv_01",
    tasks: list[str] | None = None,
    downstream: list[str] | None = None,
    added: bool = True,
) -> ImpactComputedPayload:
    reqs = [
        RequirementImpact(
            id="REQ-AUTH-002",
            change="modified",
            kind="behavioral",
            rationale="why",
            obsolete_criteria=["AC-AUTH-002-1"],
            new_work=["do it"],
        )
    ]
    if added:
        reqs.append(
            RequirementImpact(
                id="REQ-AUTH-003",
                change="added",
                kind=None,
                rationale=None,
                obsolete_criteria=[],
                new_work=[],
            )
        )
    return ImpactComputedPayload(
        from_version=from_version,
        to_version="sv_02",
        run_id="run_0001",
        requirements=reqs,
        adrs=[],
        tasks=["AUTH-002"] if tasks is None else tasks,
        downstream=["AUTH-003"] if downstream is None else downstream,
        files=["src/auth/a.py"],
        tests=["tests/test_a.py::t"],
    )


class FakeEventStore:
    def __init__(self, *payloads: ImpactComputedPayload, stream: str = "spec:sv_02") -> None:
        self.events = [
            StoredEvent(
                **Event.new(
                    stream=stream,
                    type=EventType.ImpactComputed,
                    payload=p.model_dump(mode="json"),
                    actor="orchestrator",
                ).model_dump(),
                seq=i,
            )
            for i, p in enumerate(payloads, start=1)
        ]
        self.reads: list[str | None] = []
        self.appends = 0

    def append(self, event: Event) -> StoredEvent:
        self.appends += 1
        raise AssertionError("prepare_replan must not append")

    def read(self, stream: str | None = None) -> list[StoredEvent]:
        self.reads.append(stream)
        return [e for e in self.events if stream is None or e.stream == stream]


def prepare(
    *payloads: ImpactComputedPayload,
    files: FakeSpecFiles | None = None,
    plans: FakePlans | None = None,
    versions: FakeVersions | None = None,
) -> tuple[ReplanRefused | ReplanInputs, FakeEventStore, FakeSpecFiles]:
    store = FakeEventStore(*payloads)
    spec_f = files or spec_files()
    result = prepare_replan(spec_f, versions or FakeVersions(), plans or FakePlans(), store)
    return result, store, spec_f


# ---- AC1 ----


def test_task102_ac1_no_approved_plan_is_refused_first() -> None:
    result, store, files = prepare(plans=FakePlans(None))
    assert isinstance(result, ReplanRefused)
    assert result.reason == ReplanRefusal.no_approved_plan
    assert store.appends == 0 and files.reads == []


def test_task102_ac1_no_impact_for_the_approved_plans_version_is_refused() -> None:
    # The only event has another from_version.
    result, store, files = prepare(impact(from_version="sv_00"))
    assert isinstance(result, ReplanRefused)
    assert result.reason == ReplanRefusal.no_impact
    assert "spec:sv_02" in store.reads
    assert store.appends == 0 and files.reads == []


def test_task102_ac1_no_event_at_all_is_no_impact() -> None:
    result, _, _ = prepare()
    assert isinstance(result, ReplanRefused)
    assert result.reason == ReplanRefusal.no_impact


def test_task102_ac1_latest_matching_event_with_nothing_to_do_is_refused() -> None:
    # An earlier matching event listed a task; the latest (highest seq) lists none.
    result, store, files = prepare(impact(), impact(tasks=[], downstream=[], added=False))
    assert isinstance(result, ReplanRefused)
    assert result.reason == ReplanRefusal.nothing_to_replan
    assert store.appends == 0 and files.reads == []


# ---- AC2 ----


@pytest.mark.parametrize("policy", ["bogus_key: 1\n", None])
def test_task102_ac2_invalid_or_missing_policy_is_refused(policy: str | None) -> None:
    result, store, _ = prepare(impact(), files=spec_files(policy=policy))
    assert isinstance(result, ReplanRefused)
    assert result.reason == ReplanRefusal.invalid_policy
    assert store.appends == 0


def test_task102_ac2_inputs_carry_the_latest_matching_impact_and_the_stored_spec() -> None:
    versions = FakeVersions()
    latest = impact(tasks=["AUTH-002", "AUTH-001"])
    result, store, _ = prepare(impact(from_version="sv_00"), latest, versions=versions)
    assert isinstance(result, ReplanInputs)
    assert result.plan_id == "plan_03"
    assert result.spec_version == "sv_02"
    assert result.spec == stored_set()
    assert versions.spec_set_ids == ["sv_02"]
    assert result.impact == latest
    assert result.policy.forbidden_paths == ["secrets/**"]
    assert result.spec_files_differ is False
    assert store.appends == 0


def test_task102_ac2_added_requirement_alone_is_enough_to_replan() -> None:
    result, _, _ = prepare(impact(tasks=[], downstream=[], added=True))
    assert isinstance(result, ReplanInputs)


def test_task102_ac2_differing_files_set_the_flag_and_keep_the_stored_spec() -> None:
    changed = spec_files(requirements=REQUIREMENTS_TEXT.replace("statement: s3", "statement: x"))
    result, _, _ = prepare(impact(), files=changed)
    assert isinstance(result, ReplanInputs)
    assert result.spec_files_differ is True
    assert result.spec == stored_set()


def test_task102_ac2_files_that_cannot_be_loaded_set_the_flag() -> None:
    result, _, _ = prepare(impact(), files=spec_files(requirements=None))
    assert isinstance(result, ReplanInputs)
    assert result.spec_files_differ is True


# ---- create_replan helpers ----


class FakeGit:
    def __init__(self, result: list[str] | GitError = FILES) -> None:
        self.result = result
        self.calls = 0

    def tracked_files(self) -> list[str]:
        self.calls += 1
        if isinstance(self.result, GitError):
            raise self.result
        return self.result


class FakeLLM:
    def __init__(self, *script: LLMReply | LLMError) -> None:
        self.script = list(script)
        self.prompts: list[str] = []

    def complete(self, prompt: str, schema: dict[str, object]) -> LLMReply:
        self.prompts.append(prompt)
        item = self.script[len(self.prompts) - 1]
        if isinstance(item, LLMError):
            raise item
        return item


class FakeRecorder:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def record(self, event: Event) -> StoredEvent:
        self.events.append(event)
        return StoredEvent(**event.model_dump(), seq=len(self.events))


class FakeRuns:
    def __init__(self, recorder: FakeRecorder) -> None:
        self.recorder = recorder

    def next_id(self) -> str:
        started = sum(e.type == STARTED for e in self.recorder.events)
        return f"run_{FIRST_RUN + started:04d}"


def planned(task_id: str, reqs: list[str], acs: list[str], **extra: object) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "objective": f"Do {task_id}",
        "requirements": reqs,
        "acceptance_criteria": acs,
        "components": ["auth"],
        "role": "implementer",
        "allowed_paths": ["src/auth/**"],
        **extra,
    }


def good_structured() -> dict[str, Any]:
    # AUTH-006 listed first; both depend on the untouched passed AUTH-001.
    return {
        "tasks": [
            planned("AUTH-006", ["REQ-AUTH-003"], ["AC-AUTH-003-1"], depends_on=["AUTH-001"]),
            planned("AUTH-005", ["REQ-AUTH-002"], ["AC-AUTH-002-1"], depends_on=["AUTH-001"]),
        ]
    }


def one_task(task_id: str, **extra: object) -> dict[str, Any]:
    all_reqs = ["REQ-AUTH-001", "REQ-AUTH-002", "REQ-AUTH-003"]
    all_acs = ["AC-AUTH-001-1", "AC-AUTH-001-2", "AC-AUTH-002-1", "AC-AUTH-003-1"]
    return {"tasks": [planned(task_id, all_reqs, all_acs, **extra)]}


def reply(structured: object | None, *, model: str = "m-1") -> LLMReply:
    return LLMReply(
        structured=structured,
        model=model,
        tokens_in=10,
        tokens_out=11,
        cost_usd=0.1,
        duration_s=5.0,
    )


def make_inputs(spec: SpecSet = SPEC, imp: ImpactComputedPayload | None = None) -> ReplanInputs:
    return ReplanInputs(
        plan_id="plan_03",
        spec_version="sv_02",
        spec=spec,
        policy=POLICY,
        impact=imp or impact(),
        spec_files_differ=False,
    )


class Env:
    def __init__(
        self,
        *script: LLMReply | LLMError,
        git: FakeGit | None = None,
        spec: SpecSet = SPEC,
    ) -> None:
        self.llm = FakeLLM(*script)
        self.recorder = FakeRecorder()
        self.plans = FakePlans()
        self.git = git or FakeGit()
        self.inputs = make_inputs(spec)

    def go(self) -> Any:
        return create_replan(
            self.inputs,
            git=self.git,
            llm=self.llm,
            runs=FakeRuns(self.recorder),
            plans=self.plans,
            recorder=self.recorder,
        )

    @property
    def events(self) -> list[Event]:
        return self.recorder.events


def types(events: list[Event]) -> list[EventType]:
    return [e.type for e in events]


def replan_prompt(rejections: list[PlanRejection] | None = None, spec: SpecSet = SPEC) -> str:
    return build_replan_prompt(spec, POLICY, FILES, impact(), PLAN_TASKS, rejections or [])


def rejections_of(structured: dict[str, Any], spec: SpecSet = SPEC) -> list[PlanRejection]:
    tasks = [PlannedTask.model_validate(t) for t in structured["tasks"]]
    return check_plan(
        tasks,
        spec,
        ids_in_use=FakePlans().in_use,
        untouched=untouched_tasks(PLAN_TASKS, impact()),
    )


# ---- AC3 ----


def test_task102_ac3_run_context_hash_is_that_of_the_replan_prompt() -> None:
    env = Env(reply(good_structured()))
    env.go()
    started = env.events[0]
    assert started.type == STARTED
    assert started.payload["role"] == "planner" and started.payload["task_id"] is None
    assert started.payload["context_hash"] == context_hash(replan_prompt())
    assert env.llm.prompts == [replan_prompt()]


def test_task102_ac3_retry_hash_is_that_of_the_prompt_with_the_rejections() -> None:
    bad = good_structured()
    bad["tasks"][0]["depends_on"] = ["AUTH-002"]  # impacted
    rejections = rejections_of(bad)
    assert rejections
    env = Env(reply(bad), reply(good_structured()))
    env.go()
    second = replan_prompt(rejections)
    assert env.llm.prompts == [replan_prompt(), second]
    assert env.events[2].payload["context_hash"] == context_hash(second)


def test_task102_ac3_a_git_error_stops_everything_before_any_read() -> None:
    text = "warning: a\nfatal: b"
    env = Env(git=FakeGit(GitError(text)))
    result = env.go()
    assert result.outcome == PlannerOutcome.git_failed
    assert result.error == text
    assert env.events == [] and env.llm.prompts == []
    assert env.plans.in_use_calls == 0 and env.plans.tasks_calls == []


def test_task102_ac3_an_llm_error_fails_with_the_run_error_and_no_plan() -> None:
    env = Env(LLMError("boom\nmore", duration_s=2.5, timeout=False))
    result = env.go()
    assert result.outcome == PlannerOutcome.failed
    assert types(env.events) == [STARTED, FINISHED]
    assert result.error == env.events[1].payload["error"] == "boom\nmore"


# ---- AC4 ----


def test_task102_ac4_new_tasks_may_depend_on_an_untouched_passed_task() -> None:
    # REQ-AUTH-001 is covered only by untouched tasks; the reply names only 002 and 003.
    env = Env(reply(good_structured()))
    result = env.go()
    assert result.outcome == PlannerOutcome.created
    assert env.plans.tasks_calls == ["plan_03"]
    assert len(env.llm.prompts) == 1


def test_task102_ac4_empty_reply_is_accepted_when_untouched_tasks_cover_everything() -> None:
    spec = spec_with(make_req(1, (1, 2)), make_req(2, (1,), deprecated=True))
    env = Env(reply({"tasks": []}), spec=spec)
    result = env.go()
    assert result.outcome == PlannerOutcome.created
    assert result.tasks == []
    assert types(env.events) == [STARTED, FINISHED, CREATED]
    assert PlanCreatedPayload.model_validate(env.events[-1].payload).tasks == []


def test_task102_ac4_empty_reply_is_rejected_when_something_is_uncovered() -> None:
    env = Env(reply({"tasks": []}), reply({"tasks": []}))
    result = env.go()
    assert result.outcome == PlannerOutcome.rejected
    assert "uncovered" in "\n".join(rejection_lines(result.rejections))


@pytest.mark.parametrize("dep", ["AUTH-002", "AUTH-004"])
def test_task102_ac4_depending_on_an_impacted_or_abandoned_task_is_rejected(dep: str) -> None:
    bad = good_structured()
    bad["tasks"][0]["depends_on"] = [dep]
    env = Env(reply(bad), reply(bad))
    result = env.go()
    assert result.outcome == PlannerOutcome.rejected
    assert [(r.rule, r.subject) for r in result.rejections] == [
        (PlanRule.unknown_dependency, "AUTH-006")
    ]
    assert len(env.llm.prompts) == 2


# ---- AC5 ----


def test_task102_ac5_ids_in_use_are_read_once_and_reject_an_impacted_tasks_id() -> None:
    # AUTH-002 is impacted, so not untouched: only `ids_in_use` can reject it.
    bad = one_task("AUTH-002")
    env = Env(reply(bad), reply(good_structured()))
    result = env.go()
    assert result.outcome == PlannerOutcome.created
    line = "task-id-in-use  AUTH-002  task id 'AUTH-002' is already in use"
    assert env.events[1].payload["error"] == line
    rejection = PlanRejection(
        rule=PlanRule.task_id_in_use,
        subject="AUTH-002",
        message="task id 'AUTH-002' is already in use",
    )
    assert env.llm.prompts[1] == replan_prompt([rejection])
    assert env.plans.in_use_calls == 1


def test_task102_ac5_an_id_outside_the_approved_plan_is_rejected_too() -> None:
    # AUTH-009 is in the fake's list but in no task of the approved plan.
    env = Env(reply(one_task("AUTH-009")), reply(one_task("AUTH-009")))
    result = env.go()
    assert result.outcome == PlannerOutcome.rejected
    assert [(r.rule, r.subject) for r in result.rejections] == [
        (PlanRule.task_id_in_use, "AUTH-009")
    ]
    assert env.plans.in_use_calls == 1


def test_task102_ac5_run_planner_without_ids_in_use_still_accepts_the_id() -> None:
    recorder = FakeRecorder()
    result = run_planner(
        "sv_02",
        SPEC,
        POLICY,
        FILES,
        llm=FakeLLM(reply(one_task("AUTH-002"))),
        runs=FakeRuns(recorder),
        plans=FakePlans(),
        recorder=recorder,
    )
    assert result.outcome == PlannerOutcome.created


# ---- AC6 ----


def test_task102_ac6_accepted_reply_records_the_run_and_a_plan_of_the_new_tasks_only() -> None:
    env = Env(reply(good_structured()))
    result = env.go()
    assert types(env.events) == [STARTED, FINISHED, CREATED]
    assert env.events[0].causation_id is None
    assert env.events[1].causation_id == env.events[0].event_id
    assert env.events[2].causation_id == env.events[1].event_id
    created = PlanCreatedPayload.model_validate(env.events[2].payload)
    assert (created.plan_id, created.spec_version) == (PLAN_ID, "sv_02")
    assert created.run_id == f"run_{FIRST_RUN:04d}"
    assert env.events[2].stream == f"plan:{PLAN_ID}"
    assert [t.task_id for t in created.tasks] == ["AUTH-005", "AUTH-006"]
    expected = [
        complete_contract(PlannedTask.model_validate(t), POLICY)
        for t in sorted(good_structured()["tasks"], key=lambda t: t["task_id"])
    ]
    assert created.tasks == expected
    assert result.outcome == PlannerOutcome.created
    assert result.plan_id == PLAN_ID and result.tasks == expected


def test_task102_ac6_a_retry_records_two_runs_chained_then_the_plan() -> None:
    bad = good_structured()
    bad["tasks"][0]["depends_on"] = ["AUTH-004"]
    env = Env(reply(bad), reply(good_structured()))
    env.go()
    assert types(env.events) == [STARTED, FINISHED, STARTED, FINISHED, CREATED]
    assert env.events[0].causation_id is None
    for before, after in zip(env.events, env.events[1:], strict=False):
        assert after.causation_id == before.event_id
    created = PlanCreatedPayload.model_validate(env.events[-1].payload)
    assert created.run_id == f"run_{FIRST_RUN + 1:04d}"
    assert EventType.TaskStateChanged not in types(env.events)
    assert EventType.ImpactComputed not in types(env.events)


def test_task102_ac6_replan_module_imports_no_adapter_cli_or_traces() -> None:
    tree = ast.parse(REPLAN_PY.read_text())
    modules = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)] + [
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    ]
    assert modules
    for module in modules:
        assert not module.startswith(("openfactory.adapters", "openfactory.cli"))
        assert "traces" not in module
    assert plan_module.__file__ is not None
