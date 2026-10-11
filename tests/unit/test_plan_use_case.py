"""TASK-032: the planner call of the plan use case.

Each test names the acceptance criterion it covers (AC1..AC6 in
docs/tasks/TASK-032-plan-use-case-planner-call.md). The function is driven through
in-memory fakes of LLMProvider, Runs, Plans and EventRecorder; no database, git or
`claude` is used. The sample set, policy and files are those of test_planner_prompt.py.
"""

import ast
from pathlib import Path
from typing import Any

import pytest

from openfactory.app import plan as plan_module
from openfactory.app.plan import PlannerOutcome, PlannerResult, run_planner
from openfactory.app.planner_prompt import build_planner_prompt, context_hash
from openfactory.domain.contracts import PlannedTask, PlannerReply, complete_contract
from openfactory.domain.events import Event, EventType, StoredEvent
from openfactory.domain.llm import LLMReply
from openfactory.domain.models import AcceptanceCriterion, Adr, AdrStatus, Requirement, SpecSet
from openfactory.domain.payloads import PlanCreatedPayload
from openfactory.domain.plan_checks import check_plan, rejection_lines
from openfactory.domain.policy import BASELINE_FORBIDDEN_PATHS, Policy
from openfactory.domain.spec_hash import policy_hash
from openfactory.ports.llm_provider import LLMError

PLAN_PY = Path(__file__).resolve().parents[2] / "src" / "openfactory" / "app" / "plan.py"

FILES = ["app/main.py", "tests/test_main.py"]
POLICY = Policy(forbidden_paths=["secrets/**"])
VERSION = "sv_01"
PLAN_ID = "plan_07"
FIRST_RUN = 5  # the fake Runs starts at run_0005, not run_0001
TWO_LINES = "first line\nsecond line"


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


def good_structured() -> dict[str, object]:
    # AUTH-002 first, AUTH-001 second; AUTH-001 has no depends_on or forbidden_paths key.
    return {
        "tasks": [
            planned("AUTH-002", depends_on=["AUTH-001"], forbidden_paths=["legacy/**"]),
            planned("AUTH-001"),
        ]
    }


def bad_structured() -> dict[str, object]:
    # An unknown requirement and an undeclared component: at least two rejections.
    bad = planned("AUTH-001", requirements=["REQ-NOPE-001"], components=["nope"])
    return {"tasks": [bad]}


def reply(structured: object | None, *, model: str = "m-1", tokens: int = 10) -> LLMReply:
    return LLMReply(
        structured=structured,
        model=model,
        tokens_in=tokens,
        tokens_out=tokens + 1,
        cost_usd=tokens / 100,
        duration_s=tokens / 2,
    )


def good_reply(**kw: Any) -> LLMReply:
    return reply(good_structured(), **kw)


class FakeLLM:
    def __init__(self, *script: LLMReply | LLMError) -> None:
        self.script = list(script)
        self.prompts: list[str] = []
        self.schemas: list[dict[str, object]] = []

    def complete(self, prompt: str, schema: dict[str, object]) -> LLMReply:
        self.prompts.append(prompt)
        self.schemas.append(schema)
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
    """The id after the number of AgentRunStarted events recorded so far."""

    def __init__(self, recorder: FakeRecorder) -> None:
        self.recorder = recorder

    def next_id(self) -> str:
        started = sum(e.type == EventType.AgentRunStarted for e in self.recorder.events)
        return f"run_{FIRST_RUN + started:04d}"


class FakePlans:
    def next_id(self) -> str:
        return PLAN_ID


def run(*script: LLMReply | LLMError) -> tuple[PlannerResult, FakeLLM, list[Event]]:
    llm = FakeLLM(*script)
    recorder = FakeRecorder()
    result = run_planner(
        VERSION,
        sample_set(),
        POLICY,
        FILES,
        llm=llm,
        runs=FakeRuns(recorder),
        plans=FakePlans(),
        recorder=recorder,
    )
    return result, llm, recorder.events


def assert_chained(events: list[Event]) -> None:
    assert events[0].causation_id is None
    for before, after in zip(events, events[1:], strict=False):
        assert after.causation_id == before.event_id


def types(events: list[Event]) -> list[EventType]:
    return [e.type for e in events]


STARTED, FINISHED, CREATED = (
    EventType.AgentRunStarted,
    EventType.AgentRunFinished,
    EventType.PlanCreated,
)


def test_ac1_good_reply_makes_one_call_and_records_the_run_and_the_plan() -> None:
    result, llm, events = run(good_reply(model="m-x", tokens=40))
    prompt = build_planner_prompt(sample_set(), POLICY, FILES)
    assert llm.prompts == [prompt]
    assert llm.schemas == [PlannerReply.model_json_schema()]
    assert types(events) == [STARTED, FINISHED, CREATED]
    assert_chained(events)
    assert {e.actor for e in events} == {"orchestrator"}
    run_id = f"run_{FIRST_RUN:04d}"
    assert events[0].stream == events[1].stream == f"run:{run_id}"
    assert events[0].payload == {
        "run_id": run_id,
        "task_id": None,
        "role": "planner",
        "runtime": "claude-code",
        "context_hash": context_hash(prompt),
    }
    assert events[1].payload == {
        "run_id": run_id,
        "exit": "ok",
        "model": "m-x",
        "tokens_in": 40,
        "tokens_out": 41,
        "cost_usd": 0.4,
        "duration_s": 20.0,
        "error": None,
    }
    assert result.outcome == PlannerOutcome.created
    assert result.plan_id == PLAN_ID


def test_ac1_module_imports_no_adapter_or_cli() -> None:
    tree = ast.parse(PLAN_PY.read_text())
    modules = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)] + [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    assert modules
    for name in modules:
        assert not name.startswith(("openfactory.adapters", "openfactory.cli")), name
    assert plan_module.__file__ == str(PLAN_PY)


def test_ac2_plan_created_holds_the_completed_contracts_sorted() -> None:
    result, _, events = run(good_reply())
    created = events[-1]
    assert created.type == CREATED
    assert created.stream == f"plan:{PLAN_ID}"
    payload = PlanCreatedPayload.model_validate(created.payload)
    assert payload.plan_id == PLAN_ID
    assert payload.spec_version == VERSION
    assert payload.policy_hash == policy_hash(POLICY)
    assert payload.run_id == f"run_{FIRST_RUN:04d}"

    planned_tasks = [PlannedTask.model_validate(t) for t in good_structured()["tasks"]]  # type: ignore[index]
    expected = [
        complete_contract(t, POLICY).model_dump(mode="json")
        for t in sorted(planned_tasks, key=lambda t: t.task_id)
    ]
    assert created.payload["tasks"] == expected
    stored: list[Any] = created.payload["tasks"]  # type: ignore[assignment]
    assert [t["task_id"] for t in stored] == ["AUTH-001", "AUTH-002"]
    fields = set(complete_contract(planned_tasks[1], POLICY).model_dump())
    assert all(set(t) == fields for t in stored)
    assert stored[0]["depends_on"] == []
    assert stored[1]["forbidden_paths"] == [
        *BASELINE_FORBIDDEN_PATHS,
        "secrets/**",
        "legacy/**",
    ]
    assert [t.model_dump(mode="json") for t in result.tasks] == expected


def test_ac3_rejected_reply_is_retried_once_with_the_rejections() -> None:
    first = reply(bad_structured(), model="m-bad", tokens=30)
    second = good_reply(model="m-good", tokens=50)
    result, llm, events = run(first, second)

    bad_tasks = PlannerReply.model_validate(bad_structured()).tasks
    rejections = check_plan(bad_tasks, sample_set())
    assert len(rejections) >= 2
    first_prompt = build_planner_prompt(sample_set(), POLICY, FILES)
    second_prompt = build_planner_prompt(sample_set(), POLICY, FILES, rejections=rejections)
    assert llm.prompts == [first_prompt, second_prompt]
    assert types(events) == [STARTED, FINISHED, STARTED, FINISHED, CREATED]
    assert_chained(events)

    assert events[1].payload == {
        "run_id": f"run_{FIRST_RUN:04d}",
        "exit": "ok",
        "model": "m-bad",
        "tokens_in": 30,
        "tokens_out": 31,
        "cost_usd": 0.3,
        "duration_s": 15.0,
        "error": "\n".join(rejection_lines(rejections)),
    }
    second_id = f"run_{FIRST_RUN + 1:04d}"
    assert events[2].stream == events[3].stream == f"run:{second_id}"
    assert events[2].payload["context_hash"] == context_hash(second_prompt)
    assert events[2].payload["context_hash"] != events[0].payload["context_hash"]
    assert events[3].payload["error"] is None
    assert events[4].payload["run_id"] == second_id
    assert result.outcome == PlannerOutcome.created


@pytest.mark.parametrize("task_extra", [None, {"required_gates": ["ruff"]}])
def test_ac4_reply_failing_the_schema_rule_is_retried(task_extra: dict[str, object] | None) -> None:
    if task_extra is None:
        first = reply(None)
    else:
        first = reply({"tasks": [planned("AUTH-001", **task_extra)]})
    result, llm, events = run(first, good_reply())
    assert len(llm.prompts) == 2
    assert events[1].payload["exit"] == "ok"
    error = events[1].payload["error"]
    assert isinstance(error, str)
    if task_extra is None:
        assert error == "schema  reply  no structured result"
    else:
        assert all(line.startswith("schema  ") for line in error.split("\n"))
    assert result.outcome == PlannerOutcome.created


def test_ac5_second_rejected_reply_ends_with_its_own_rejections() -> None:
    result, llm, events = run(reply(bad_structured()), reply(None))
    assert len(llm.prompts) == 2
    assert types(events) == [STARTED, FINISHED, STARTED, FINISHED]
    assert_chained(events)
    assert events[3].payload["exit"] == "ok"
    assert events[3].payload["error"] == "schema  reply  no structured result"
    assert result.outcome == PlannerOutcome.rejected
    assert [(r.rule.value, r.subject, r.message) for r in result.rejections] == [
        ("schema", "reply", "no structured result")
    ]
    assert result.plan_id is None


@pytest.mark.parametrize(("timeout", "exit_value"), [(False, "error"), (True, "timeout")])
def test_ac6_failed_process_is_recorded_and_not_retried(timeout: bool, exit_value: str) -> None:
    error = LLMError(TWO_LINES, duration_s=2.5, timeout=timeout)
    result, llm, events = run(error)
    assert len(llm.prompts) == 1
    assert types(events) == [STARTED, FINISHED]
    assert_chained(events)
    assert events[1].payload == {
        "run_id": f"run_{FIRST_RUN:04d}",
        "exit": exit_value,
        "model": None,
        "tokens_in": None,
        "tokens_out": None,
        "cost_usd": None,
        "duration_s": 2.5,
        "error": TWO_LINES,
    }
    assert result.outcome == PlannerOutcome.failed
    assert result.error == TWO_LINES


def test_ac6_failed_second_call_is_failed_not_rejected() -> None:
    result, llm, events = run(
        reply(bad_structured()), LLMError("boom", duration_s=1.0, timeout=False)
    )
    assert len(llm.prompts) == 2
    assert types(events) == [STARTED, FINISHED, STARTED, FINISHED]
    assert_chained(events)
    assert events[3].payload["exit"] == "error"
    assert CREATED not in types(events)
    assert result.outcome == PlannerOutcome.failed
