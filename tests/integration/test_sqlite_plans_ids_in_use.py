"""TASK-100 AC5: the ids in use against the real recorder and plans adapter."""

import pytest

from openfactory.adapters.sqlite_plans import SqlitePlans
from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.app.plan import PlanInputs, PlannerOutcome, create_plan, run_planner
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType
from openfactory.domain.llm import LLMReply
from openfactory.domain.models import AcceptanceCriterion, Adr, AdrStatus, Requirement, SpecSet
from openfactory.domain.payloads import PlanApprovedPayload, PlanCreatedPayload
from openfactory.domain.plan_checks import rejection_lines
from openfactory.domain.policy import Policy

POLICY = Policy(forbidden_paths=["secrets/**"])
IN_USE_LINE = "task-id-in-use  AUTH-001  task id 'AUTH-001' is already in use"


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


def contract(task_id: str) -> TaskContract:
    return TaskContract(
        task_id=task_id,
        objective=f"Do {task_id}",
        requirements=["REQ-AUTH-001"],
        acceptance_criteria=["AC-AUTH-001-1"],
        depends_on=[],
        components=["auth"],
        role="implementer",
        allowed_paths=["app/auth/**"],
        forbidden_paths=["specs/**"],
        required_gates=["path_check", "ruff", "pytest", "gitleaks", "review"],
        limits=Limits(max_runtime_s=1200, max_attempts=2, max_cost_usd=1.5),
    )


def plan_created(plan_id: str, task_id: str) -> Event:
    payload = PlanCreatedPayload(
        plan_id=plan_id,
        spec_version="sv_01",
        policy_hash="a" * 64,
        run_id="run_0001",
        tasks=[contract(task_id)],
    )
    return Event.new(
        stream=f"plan:{plan_id}",
        type=EventType.PlanCreated,
        payload=payload.model_dump(mode="json"),
        actor="orchestrator",
    )


def plan_approved(plan_id: str) -> Event:
    return Event.new(
        stream=f"plan:{plan_id}",
        type=EventType.PlanApproved,
        payload=PlanApprovedPayload(plan_id=plan_id).model_dump(mode="json"),
        actor="human",
    )


def reuse_reply() -> LLMReply:
    task = {
        "task_id": "AUTH-001",
        "objective": "Do AUTH-001",
        "requirements": ["REQ-AUTH-001"],
        "acceptance_criteria": ["AC-AUTH-001-1", "AC-AUTH-001-2"],
        "components": ["auth"],
        "role": "implementer",
        "allowed_paths": ["src/auth/**"],
    }
    return LLMReply(
        structured={"tasks": [task]},
        model="m-1",
        tokens_in=1,
        tokens_out=1,
        cost_usd=0.1,
        duration_s=1.0,
    )


class ScriptLLM:
    def __init__(self, *replies: LLMReply) -> None:
        self.replies = list(replies)
        self.calls = 0

    def complete(self, prompt: str, schema: dict[str, object]) -> LLMReply:
        self.calls += 1
        return self.replies[self.calls - 1]


class CountingRuns:
    def __init__(self) -> None:
        self.n = 0

    def next_id(self) -> str:
        self.n += 1
        return f"run_{self.n + 10:04d}"


class FakeGit:
    def tracked_files(self) -> list[str]:
        return ["app/main.py"]


@pytest.fixture
def db(tmp_path):
    return tmp_path / "openfactory.db"


@pytest.fixture
def recorder(db):
    rec = SqliteEventRecorder(db)
    yield rec
    rec.close()


@pytest.fixture
def plans(db, recorder):
    adapter = SqlitePlans(db)
    yield adapter
    adapter.close()


def test_task100_ac5_a_new_draft_may_reuse_the_ids_of_the_draft_it_replaces(recorder, plans):
    recorder.record(plan_created("plan_01", "AUTH-001"))
    inputs = PlanInputs(
        spec_version="sv_01", spec=sample_set(), policy=POLICY, spec_files_differ=False
    )
    result = create_plan(
        inputs,
        git=FakeGit(),
        llm=ScriptLLM(reuse_reply()),
        runs=CountingRuns(),
        plans=plans,
        recorder=recorder,
    )
    assert result.outcome == PlannerOutcome.created
    assert result.plan_id == "plan_02"
    assert plans.current_draft() is not None
    assert plans.task_ids_in_use() == []


def test_task100_ac5_ids_of_an_approved_plan_reject_the_same_reply(recorder, plans):
    recorder.record(plan_created("plan_01", "AUTH-001"))
    recorder.record(plan_approved("plan_01"))
    result = run_planner(
        "sv_01",
        sample_set(),
        POLICY,
        ["app/main.py"],
        llm=ScriptLLM(reuse_reply(), reuse_reply()),
        runs=CountingRuns(),
        plans=plans,
        recorder=recorder,
        ids_in_use=plans.task_ids_in_use(),
    )
    assert result.outcome == PlannerOutcome.rejected
    assert IN_USE_LINE in rejection_lines(result.rejections)
