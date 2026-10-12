"""TASK-033: the entry and the refusals of the plan use case.

Each test names the acceptance criterion it covers (AC1..AC6 in
docs/tasks/TASK-033-plan-use-case-entry-and-refusals.md). The functions are driven through
in-memory fakes of SpecFiles, SpecVersions, Plans, GitProvider, LLMProvider, Runs and
EventRecorder; no database, git or `claude` is used.
"""

import inspect
from typing import Any

import pytest

from openfactory.app.plan import (
    PlanInputs,
    PlannerOutcome,
    PlanRefusal,
    PlanRefused,
    create_plan,
    prepare_plan,
)
from openfactory.app.planner_prompt import build_planner_prompt
from openfactory.app.spec_loader import load_policy, load_spec
from openfactory.domain.events import Event, EventType, StoredEvent
from openfactory.domain.llm import LLMReply
from openfactory.domain.models import AcceptanceCriterion, Adr, AdrStatus, Requirement, SpecSet
from openfactory.domain.payloads import PlanCreatedPayload
from openfactory.domain.plans import PlanRef
from openfactory.domain.policy import Policy
from openfactory.domain.spec_hash import content_hash
from openfactory.domain.spec_versions import SpecVersionRef
from openfactory.ports.git_provider import GitError
from openfactory.ports.llm_provider import LLMError

FILES = ["app/main.py", "tests/test_main.py"]
POLICY = Policy(forbidden_paths=["secrets/**"])
PLAN_ID = "plan_07"
FIRST_RUN = 5

POLICY_TEXT = 'forbidden_paths: ["secrets/**"]\n'
BAD_POLICY_TEXT = "bogus_key: 1\n"

REQUIREMENTS_TEXT = """\
components: [auth, billing]
requirements:
  - id: REQ-AUTH-001
    title: Login with token
    statement: A user can log in with a bearer token.
    priority: must
    components: [auth]
    constrained_by: [ADR-001]
    acceptance_criteria:
      - id: AC-AUTH-001-1
        text: Valid token returns session.
      - id: AC-AUTH-001-2
        text: Expired token is refused.
"""
ADR_TEXT = "---\nid: ADR-001\nstatus: accepted\n---\nSessions are signed.\n"


def sample_set() -> SpecSet:
    return SpecSet(
        components=["auth", "billing"],
        requirements=[
            Requirement(
                id="REQ-AUTH-001",
                title="Login with token",
                statement="A user can log in with a bearer token.",
                priority="must",
                components=["auth"],
                acceptance_criteria=[
                    AcceptanceCriterion(id="AC-AUTH-001-1", text="Valid token returns session."),
                    AcceptanceCriterion(id="AC-AUTH-001-2", text="Expired token is refused."),
                ],
                constrained_by=["ADR-001"],
            )
        ],
        adrs=[Adr(id="ADR-001", status=AdrStatus.accepted, body="Sessions are signed.")],
    )


def good_reply() -> LLMReply:
    def planned(task_id: str, **extra: object) -> dict[str, object]:
        return {
            "task_id": task_id,
            "objective": f"Do {task_id}",
            "requirements": ["REQ-AUTH-001"],
            "acceptance_criteria": ["AC-AUTH-001-1", "AC-AUTH-001-2"],
            "components": ["auth"],
            "role": "implementer",
            "allowed_paths": ["src/auth/**"],
            **extra,
        }

    structured = {
        "tasks": [planned("AUTH-002", depends_on=["AUTH-001"]), planned("AUTH-001")],
    }
    return LLMReply(
        structured=structured,
        model="m-1",
        tokens_in=10,
        tokens_out=11,
        cost_usd=0.1,
        duration_s=5.0,
    )


class FakeSpecFiles:
    def __init__(self, files: dict[str, str]):
        self.files = files

    def read(self, path: str) -> str | None:
        return self.files.get(path)

    def list_adrs(self) -> list[str]:
        return sorted(p for p in self.files if p.startswith("adrs/") and p.endswith(".md"))


class FakeVersions:
    def __init__(self, approved: SpecVersionRef | None, stored: SpecSet | None = None):
        self.approved = approved
        self.stored = stored
        self.spec_set_ids: list[str] = []

    def latest_approved(self) -> SpecVersionRef | None:
        return self.approved

    def current_draft(self) -> SpecVersionRef | None:
        return None

    def next_id(self) -> str:
        return "sv_03"

    def spec_set(self, version_id: str) -> SpecSet | None:
        self.spec_set_ids.append(version_id)
        return self.stored


class FakePlans:
    def __init__(self, approved: PlanRef | None = None, draft: PlanRef | None = None):
        self._approved = approved
        self._draft = draft
        self.next_id_calls = 0

    def current_draft(self) -> PlanRef | None:
        return self._draft

    def approved(self) -> PlanRef | None:
        return self._approved

    def next_id(self) -> str:
        self.next_id_calls += 1
        return PLAN_ID

    def tasks(self, plan_id: str) -> list[Any]:
        return []

    def live_tasks_referencing(self, requirement_id: str) -> list[str]:
        return []


class FakeGit:
    def __init__(self, result: list[str] | GitError):
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
        self.next_id_calls = 0

    def next_id(self) -> str:
        self.next_id_calls += 1
        started = sum(e.type == EventType.AgentRunStarted for e in self.recorder.events)
        return f"run_{FIRST_RUN + started:04d}"


def spec_files(
    *, requirements: str | None = REQUIREMENTS_TEXT, policy: str | None = POLICY_TEXT
) -> FakeSpecFiles:
    files = {"adrs/ADR-001-auth.md": ADR_TEXT}
    if requirements is not None:
        files["requirements.yaml"] = requirements
    if policy is not None:
        files["policies.yaml"] = policy
    return FakeSpecFiles(files)


def loaded_set(files: FakeSpecFiles) -> SpecSet:
    spec = load_spec(files).spec
    assert spec is not None
    return spec


def approved_ref(spec: SpecSet, version: str = "sv_02") -> SpecVersionRef:
    return SpecVersionRef(id=version, hash=content_hash(spec))


# The stored spec of an approved version: the set the unchanged spec files load into.
def stored_set() -> SpecSet:
    return loaded_set(spec_files())


def test_ac1_no_approved_spec_is_refused_first() -> None:
    result = prepare_plan(
        spec_files(policy=BAD_POLICY_TEXT),
        FakeVersions(None),
        FakePlans(approved=PlanRef(id="plan_01", spec_version="sv_01")),
    )
    assert isinstance(result, PlanRefused)
    assert result.reason == PlanRefusal.no_approved_spec
    assert result.plan_id is None


@pytest.mark.parametrize("policy", [BAD_POLICY_TEXT, None])
def test_ac2_invalid_or_missing_policy_is_refused_before_the_approved_plan(
    policy: str | None,
) -> None:
    files = spec_files(policy=policy)
    result = prepare_plan(
        files,
        FakeVersions(approved_ref(stored_set()), stored_set()),
        FakePlans(approved=PlanRef(id="plan_01", spec_version="sv_02")),
    )
    assert isinstance(result, PlanRefused)
    assert result.reason == PlanRefusal.invalid_policy
    assert result.plan_id is None


def test_ac3_an_approved_plan_for_any_spec_version_is_refused_with_its_id() -> None:
    result = prepare_plan(
        spec_files(),
        FakeVersions(approved_ref(stored_set()), stored_set()),
        FakePlans(approved=PlanRef(id="plan_03", spec_version="sv_01")),
    )
    assert isinstance(result, PlanRefused)
    assert result.reason == PlanRefusal.approved_plan
    assert result.plan_id == "plan_03"


def test_ac4_equal_files_give_the_stored_spec_the_policy_and_no_difference() -> None:
    files = spec_files()
    stored = stored_set()
    versions = FakeVersions(approved_ref(stored), stored)
    result = prepare_plan(
        files,
        versions,
        FakePlans(draft=PlanRef(id="plan_01", spec_version="sv_02")),
    )
    assert isinstance(result, PlanInputs)
    assert result.spec_version == "sv_02"
    assert versions.spec_set_ids == ["sv_02"]
    assert result.spec == stored
    policy = load_policy(files).policy
    assert policy is not None
    assert result.policy == policy
    assert result.policy.forbidden_paths == ["secrets/**"]
    assert result.spec_files_differ is False


def test_ac4_prepare_plan_takes_only_files_versions_and_plans() -> None:
    assert list(inspect.signature(prepare_plan).parameters) == ["files", "versions", "plans"]


def test_ac5_files_that_differ_from_the_approved_hash_keep_the_stored_spec() -> None:
    stored = stored_set()
    changed = spec_files(
        requirements=REQUIREMENTS_TEXT.replace("Expired token is refused.", "Expired is refused.")
    )
    assert content_hash(loaded_set(changed)) != content_hash(stored)
    result = prepare_plan(changed, FakeVersions(approved_ref(stored), stored), FakePlans())
    assert isinstance(result, PlanInputs)
    assert result.spec_files_differ is True
    assert result.spec == stored
    assert result.spec != loaded_set(changed)


def test_ac5_files_that_cannot_be_loaded_set_the_flag_and_keep_the_stored_spec() -> None:
    stored = stored_set()
    result = prepare_plan(
        spec_files(requirements=None), FakeVersions(approved_ref(stored), stored), FakePlans()
    )
    assert isinstance(result, PlanInputs)
    assert result.spec_files_differ is True
    assert result.spec == stored


def make_inputs() -> PlanInputs:
    return PlanInputs(
        spec_version="sv_02", spec=sample_set(), policy=POLICY, spec_files_differ=False
    )


def call_create(git: FakeGit, llm: FakeLLM) -> tuple[Any, FakeRecorder, FakeRuns, FakePlans]:
    recorder = FakeRecorder()
    runs = FakeRuns(recorder)
    plans = FakePlans()
    result = create_plan(make_inputs(), git=git, llm=llm, runs=runs, plans=plans, recorder=recorder)
    return result, recorder, runs, plans


def test_ac6_tracked_files_feed_the_prompt_and_the_plan_is_created_for_the_version() -> None:
    git = FakeGit(FILES)
    llm = FakeLLM(good_reply())
    result, recorder, _, _ = call_create(git, llm)
    assert git.calls == 1
    assert llm.prompts == [build_planner_prompt(sample_set(), POLICY, FILES)]
    assert [e.type for e in recorder.events] == [
        EventType.AgentRunStarted,
        EventType.AgentRunFinished,
        EventType.PlanCreated,
    ]
    assert PlanCreatedPayload.model_validate(recorder.events[-1].payload).spec_version == "sv_02"
    assert result.outcome == PlannerOutcome.created
    assert result.plan_id == PLAN_ID


def test_ac6_a_git_error_is_returned_whole_and_nothing_else_happens() -> None:
    text = "warning: first\nfatal: second"
    git = FakeGit(GitError(text))
    llm = FakeLLM()
    result, recorder, runs, plans = call_create(git, llm)
    assert result.outcome == PlannerOutcome.git_failed
    assert result.error == text
    assert result.plan_id is None
    assert llm.prompts == []
    assert recorder.events == []
    assert runs.next_id_calls == 0
    assert plans.next_id_calls == 0
