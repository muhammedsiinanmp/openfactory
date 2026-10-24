"""TASK-095: the `compute_impact` use case (docs/tasks/TASK-095-impact-use-case.md).

Driven through in-memory fakes of SpecVersions, Plans, Runs, Traces, LLMProvider and
EventRecorder. sv_01 -> sv_02: REQ-AUTH-001 modified (a criterion removed), REQ-AUTH-002
modified through ADR-001, REQ-AUTH-003 added, REQ-AUTH-004 deprecated, REQ-AUTH-005 removed.
"""

import ast
from collections.abc import Collection
from pathlib import Path
from typing import Any

import pytest

from openfactory.app.classifier_prompt import build_classifier_prompt
from openfactory.app.impact import ImpactRefusal, ImpactResult, compute_impact
from openfactory.app.planner_prompt import context_hash
from openfactory.domain.classifier import (
    ClassifierReply,
    check_classification,
    parse_classifier_reply,
)
from openfactory.domain.events import Event, EventType, StoredEvent
from openfactory.domain.llm import LLMReply
from openfactory.domain.models import AcceptanceCriterion, Adr, AdrStatus, Requirement, SpecSet
from openfactory.domain.payloads import ImpactComputedPayload
from openfactory.domain.plan_checks import rejection_lines
from openfactory.domain.plans import PlanRef
from openfactory.domain.spec_diff import diff_specs
from openfactory.domain.spec_versions import SpecVersionRef
from openfactory.domain.traces import ImpactTraversal
from openfactory.ports.llm_provider import LLMError

IMPACT_PY = Path(__file__).resolve().parents[2] / "src" / "openfactory" / "app" / "impact.py"
HASH = "a" * 64
FIRST_RUN = 5
STARTED, FINISHED, IMPACT = (
    EventType.AgentRunStarted,
    EventType.AgentRunFinished,
    EventType.ImpactComputed,
)


def req(
    n: int,
    *,
    statement: str = "s",
    criteria: tuple[int, ...] = (1,),
    adrs: tuple[str, ...] = (),
    deprecated: bool = False,
) -> Requirement:
    return Requirement(
        id=f"REQ-AUTH-00{n}",
        title=f"t{n}",
        statement=statement,
        priority="must",
        components=["auth"],
        acceptance_criteria=[
            AcceptanceCriterion(id=f"AC-AUTH-00{n}-{c}", text=f"c{c}") for c in criteria
        ],
        constrained_by=list(adrs),
        deprecated=deprecated,
    )


def spec(requirements: list[Requirement], adr_body: str) -> SpecSet:
    return SpecSet(
        components=["auth"],
        requirements=requirements,
        adrs=[
            Adr(id="ADR-001", status=AdrStatus.accepted, body=adr_body),
            Adr(id="ADR-002", status=AdrStatus.accepted, body="same"),
        ],
    )


OLD = spec(
    [
        req(1, criteria=(1, 2)),
        req(2, adrs=("ADR-001",)),
        req(4),
        req(5),
        req(6),
    ],
    "old body",
)
NEW = spec(
    [
        req(1, statement="changed", criteria=(1,)),
        req(2, adrs=("ADR-001",)),
        req(3),
        req(4, deprecated=True),
        req(6),
    ],
    "new body",
)
DIFF = diff_specs(OLD, NEW)
PLAN = PlanRef(id="plan_03", spec_version="sv_01")
TRAVERSAL = ImpactTraversal(
    tasks=["AUTH-002", "AUTH-001"],
    downstream=["AUTH-009"],
    files=["b.py", "a.py"],
    tests=["t::z", "t::a"],
)


class FakeVersions:
    def __init__(self, latest: str | None = "sv_02") -> None:
        self.latest = latest
        self.sets = {"sv_01": OLD, "sv_02": NEW}

    def latest_approved(self) -> SpecVersionRef | None:
        return SpecVersionRef(id=self.latest, hash=HASH) if self.latest else None

    def current_draft(self) -> SpecVersionRef | None:
        return None

    def next_id(self) -> str:
        return "sv_99"

    def spec_set(self, version_id: str) -> SpecSet | None:
        return self.sets.get(version_id)


class FakePlans:
    def __init__(self, approved: PlanRef | None = PLAN) -> None:
        self._approved = approved

    def approved(self) -> PlanRef | None:
        return self._approved


class FakeTraces:
    def __init__(self) -> None:
        self.calls: list[tuple[str, set[str]]] = []

    def impact_traversal(self, plan_id: str, seeds: Collection[str]) -> ImpactTraversal:
        self.calls.append((plan_id, set(seeds)))
        return TRAVERSAL


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
    def __init__(self, recorder: FakeRecorder) -> None:
        self.recorder = recorder

    def next_id(self) -> str:
        started = sum(e.type == STARTED for e in self.recorder.events)
        return f"run_{FIRST_RUN + started:04d}"


def entry(n: int, kind: str, **extra: Any) -> dict[str, Any]:
    return {
        "req_id": f"REQ-AUTH-00{n}",
        "kind": kind,
        "rationale": f"why {n}",
        "obsolete_criteria": [],
        "new_work": [],
        **extra,
    }


def structured(kind1: str = "behavioral", kind2: str = "cosmetic") -> dict[str, Any]:
    return {
        "changes": [
            entry(1, kind1, obsolete_criteria=["AC-AUTH-001-1"], new_work=["z work", "a work"]),
            entry(2, kind2),
        ]
    }


def reply(s: object | None, *, model: str = "m-1", tokens: int = 10) -> LLMReply:
    return LLMReply(
        structured=s,
        model=model,
        tokens_in=tokens,
        tokens_out=tokens + 1,
        cost_usd=tokens / 100,
        duration_s=tokens / 2,
    )


class Env:
    def __init__(
        self,
        *script: LLMReply | LLMError,
        versions: FakeVersions | None = None,
        plans: FakePlans | None = None,
    ) -> None:
        self.llm = FakeLLM(*script)
        self.recorder = FakeRecorder()
        self.traces = FakeTraces()
        self.versions = versions or FakeVersions()
        self.plans = plans or FakePlans()

    def go(self) -> ImpactResult:
        return compute_impact(
            versions=self.versions,
            plans=self.plans,
            runs=FakeRuns(self.recorder),
            traces=self.traces,
            llm=self.llm,
            recorder=self.recorder,
        )

    @property
    def events(self) -> list[Event]:
        return self.recorder.events


def unmodified_env() -> Env:
    """sv_02 identical to sv_01 except an added and a removed requirement: no `modified`."""
    env = Env()
    env.versions.sets = {
        "sv_01": spec([req(4), req(5)], "same"),
        "sv_02": spec([req(3), req(4, deprecated=True)], "same"),
    }
    return env


def types(events: list[Event]) -> list[EventType]:
    return [e.type for e in events]


def assert_chained(events: list[Event]) -> None:
    assert events[0].causation_id is None
    for before, after in zip(events, events[1:], strict=False):
        assert after.causation_id == before.event_id


def recorded(env: Env) -> ImpactComputedPayload:
    last = env.events[-1]
    assert last.type == IMPACT
    return ImpactComputedPayload.model_validate(last.payload)


def test_task095_ac1_no_approved_plan_is_refused_first() -> None:
    # Also no spec change: the plan check comes first.
    env = Env(plans=FakePlans(None), versions=FakeVersions("sv_01"))
    result = env.go()
    assert result.refusal is ImpactRefusal.no_approved_plan
    assert result.impact is None
    assert env.events == [] and env.llm.prompts == [] and env.traces.calls == []


def test_task095_ac1_no_spec_change_names_the_version() -> None:
    env = Env(versions=FakeVersions("sv_01"))
    result = env.go()
    assert result.refusal is ImpactRefusal.no_spec_change
    assert result.detail == "sv_01"
    assert result.impact is None
    assert env.events == [] and env.llm.prompts == [] and env.traces.calls == []


def test_task095_ac2_no_modified_requirement_makes_no_call_and_records_one_impact() -> None:
    env = unmodified_env()
    result = env.go()
    assert env.llm.prompts == []
    assert types(env.events) == [IMPACT]
    event = env.events[0]
    assert event.stream == "spec:sv_02"
    assert event.actor == "orchestrator"
    assert event.causation_id is None
    payload = recorded(env)
    assert (payload.from_version, payload.to_version, payload.run_id) == ("sv_01", "sv_02", None)
    assert [(r.id, r.change) for r in payload.requirements] == [
        ("REQ-AUTH-003", "added"),
        ("REQ-AUTH-004", "deprecated"),
        ("REQ-AUTH-005", "removed"),
    ]
    for r in payload.requirements:
        assert (r.kind, r.rationale, r.obsolete_criteria, r.new_work) == (None, None, [], [])
    assert result.impact == payload
    assert result.error is None and result.refusal is None


def test_task095_ac2_adrs_not_unchanged_are_listed_and_each_impact_is_recorded() -> None:
    env = Env()
    env.versions.sets = {
        "sv_01": spec([req(5)], "old"),
        "sv_02": spec([req(3)], "new"),
    }
    env.go()
    env.go()
    assert types(env.events) == [IMPACT, IMPACT]
    payload = ImpactComputedPayload.model_validate(env.events[0].payload)
    assert [(a.id, a.change) for a in payload.adrs] == [("ADR-001", "modified")]


def test_task095_ac3_classifier_run_is_recorded_and_its_reply_used() -> None:
    env = Env(reply(structured(), model="m-x", tokens=40))
    result = env.go()
    prompt = build_classifier_prompt(OLD, NEW, DIFF)
    assert env.llm.prompts == [prompt]
    assert env.llm.schemas == [ClassifierReply.model_json_schema()]
    assert types(env.events) == [STARTED, FINISHED, IMPACT]
    assert_chained(env.events)
    assert {e.actor for e in env.events} == {"orchestrator"}
    run_id = f"run_{FIRST_RUN:04d}"
    assert env.events[0].stream == env.events[1].stream == f"run:{run_id}"
    assert env.events[0].payload == {
        "run_id": run_id,
        "task_id": None,
        "role": "classifier",
        "runtime": "claude-code",
        "context_hash": context_hash(prompt),
    }
    assert env.events[1].payload == {
        "run_id": run_id,
        "exit": "ok",
        "model": "m-x",
        "tokens_in": 40,
        "tokens_out": 41,
        "cost_usd": 0.4,
        "duration_s": 20.0,
        "error": None,
    }
    payload = recorded(env)
    assert payload.run_id == run_id
    by_id = {r.id: r for r in payload.requirements}
    one = by_id["REQ-AUTH-001"]
    assert (one.change, one.kind, one.rationale) == ("modified", "behavioral", "why 1")
    # The lost AC-AUTH-001-2 is added; ids once, sorted. new_work is sorted as strings.
    assert one.obsolete_criteria == ["AC-AUTH-001-1", "AC-AUTH-001-2"]
    assert one.new_work == ["a work", "z work"]
    two = by_id["REQ-AUTH-002"]
    assert (two.change, two.kind, two.obsolete_criteria, two.new_work) == (
        "modified",
        "cosmetic",
        [],
        [],
    )
    assert result.impact == payload


def test_task095_ac4_rejected_reply_is_retried_once_with_its_rejections() -> None:
    bad = {"changes": [entry(1, "behavioral", obsolete_criteria=["AC-AUTH-001-1"])]}
    rejections = check_classification(parse_classifier_reply(bad).changes or [], DIFF)
    assert rejections
    env = Env(reply(bad, model="m-bad", tokens=30), reply(structured(), model="m-good"))
    env.go()
    first_prompt = build_classifier_prompt(OLD, NEW, DIFF)
    second_prompt = build_classifier_prompt(OLD, NEW, DIFF, rejections)
    assert env.llm.prompts == [first_prompt, second_prompt]
    assert types(env.events) == [STARTED, FINISHED, STARTED, FINISHED, IMPACT]
    assert_chained(env.events)
    assert env.events[1].payload["exit"] == "ok"
    assert env.events[1].payload["error"] == "\n".join(rejection_lines(rejections))
    assert env.events[2].payload["context_hash"] == context_hash(second_prompt)
    assert env.events[3].payload["error"] is None
    assert recorded(env).run_id == f"run_{FIRST_RUN + 1:04d}"


def test_task095_ac4_schema_rejection_is_retried_too() -> None:
    env = Env(reply(None), reply(structured()))
    env.go()
    assert len(env.llm.prompts) == 2
    assert env.events[1].payload["error"] == "schema  reply  no structured result"
    assert types(env.events)[-1] == IMPACT


def test_task095_ac4_second_rejected_reply_fails_with_the_whole_error_and_no_traversal() -> None:
    env = Env(reply(None), reply({"changes": []}))
    result = env.go()
    expected = "\n".join(
        rejection_lines(check_classification([], DIFF)),
    )
    assert "\n" in expected
    assert types(env.events) == [STARTED, FINISHED, STARTED, FINISHED]
    assert env.events[3].payload["error"] == expected
    assert result.error == expected
    assert result.impact is None and result.refusal is None
    assert env.traces.calls == []


@pytest.mark.parametrize(("timeout", "exit_value"), [(False, "error"), (True, "timeout")])
def test_task095_ac4_llm_error_is_recorded_and_not_retried(timeout: bool, exit_value: str) -> None:
    env = Env(LLMError("first\nsecond", duration_s=2.5, timeout=timeout))
    result = env.go()
    assert len(env.llm.prompts) == 1
    assert types(env.events) == [STARTED, FINISHED]
    assert_chained(env.events)
    assert env.events[1].payload == {
        "run_id": f"run_{FIRST_RUN:04d}",
        "exit": exit_value,
        "model": None,
        "tokens_in": None,
        "tokens_out": None,
        "cost_usd": None,
        "duration_s": 2.5,
        "error": "first\nsecond",
    }
    assert result.error == "first\nsecond"
    assert result.impact is None
    assert env.traces.calls == []


def test_task095_ac4_failed_second_call_is_a_failure_without_impact() -> None:
    env = Env(reply(None), LLMError("boom", duration_s=1.0, timeout=False))
    result = env.go()
    assert types(env.events) == [STARTED, FINISHED, STARTED, FINISHED]
    assert result.error == "boom"
    assert IMPACT not in types(env.events)


@pytest.mark.parametrize(
    ("kind1", "kind2", "seeds"),
    [
        ("behavioral", "cosmetic", {"REQ-AUTH-001", "REQ-AUTH-004", "REQ-AUTH-005"}),
        (
            "replacement",
            "behavioral",
            {"REQ-AUTH-001", "REQ-AUTH-002", "REQ-AUTH-004", "REQ-AUTH-005"},
        ),
    ],
)
def test_task095_ac5_seeds_are_removed_deprecated_and_non_cosmetic_modified(
    kind1: str, kind2: str, seeds: set[str]
) -> None:
    env = Env(reply(structured(kind1, kind2)))
    result = env.go()
    # REQ-AUTH-003 (added) is never a seed.
    assert env.traces.calls == [("plan_03", seeds)]
    payload = recorded(env)
    assert payload.tasks == TRAVERSAL.tasks
    assert payload.downstream == TRAVERSAL.downstream
    assert payload.files == TRAVERSAL.files
    assert payload.tests == TRAVERSAL.tests
    assert result.impact == payload


def test_task095_ac5_without_a_call_the_seeds_are_removed_and_deprecated_only() -> None:
    env = unmodified_env()
    env.go()
    assert env.traces.calls == [("plan_03", {"REQ-AUTH-004", "REQ-AUTH-005"})]


def test_task095_ac6_module_imports_only_inner_layers_and_prints_nothing() -> None:
    tree = ast.parse(IMPACT_PY.read_text())
    modules = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    own = [m for m in modules if m.startswith("openfactory")]
    assert own
    for name in own:
        assert name.startswith(("openfactory.domain", "openfactory.ports", "openfactory.app")), name
    calls = [
        n.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    ]
    assert "print" not in calls
