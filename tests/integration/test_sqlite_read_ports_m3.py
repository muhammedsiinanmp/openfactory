"""TASK-042 AC2 to AC5: SqlitePlans.latest_commit and SqliteRuns.unfinished_run
(docs/tasks/TASK-042-read-ports-latest-commit-and-unfinished-run.md)."""

import sqlite3

import pytest

from openfactory.adapters.sqlite_plans import SqlitePlans
from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.adapters.sqlite_runs import SqliteRuns
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType
from openfactory.domain.payloads import (
    AgentRunFinishedPayload,
    AgentRunStartedPayload,
    CommitRecordedPayload,
    PlanApprovedPayload,
    PlanCreatedPayload,
)

HASH = "a" * 64
SHA_A = "a" * 40
SHA_B = "b" * 40
TABLES = (
    "events",
    "plans",
    "tasks",
    "task_deps",
    "commits",
    "agent_runs",
    "projection_state",
)


def contract(task_id, depends_on=()):
    return TaskContract(
        task_id=task_id,
        objective=f"Do {task_id}",
        requirements=["REQ-AUTH-001"],
        acceptance_criteria=["AC-AUTH-001-1"],
        depends_on=list(depends_on),
        components=["auth"],
        role="implementer",
        allowed_paths=["app/auth/**"],
        forbidden_paths=["specs/**"],
        required_gates=["path_check", "ruff", "pytest", "gitleaks", "review"],
        limits=Limits(max_runtime_s=1200, max_attempts=2, max_cost_usd=1.5),
    )


AUTH_001 = contract("AUTH-001")
AUTH_002 = contract("AUTH-002", depends_on=["AUTH-001"])
API_001 = contract("API-001")


def plan_created(plan_id="plan_01", tasks=(AUTH_001, AUTH_002)):
    payload = PlanCreatedPayload(
        plan_id=plan_id,
        spec_version="sv_01",
        policy_hash=HASH,
        run_id="run_0001",
        tasks=list(tasks),
    )
    return Event.new(
        stream=f"plan:{plan_id}",
        type=EventType.PlanCreated,
        payload=payload.model_dump(mode="json"),
        actor="orchestrator",
    )


def plan_approved(plan_id="plan_01"):
    payload = PlanApprovedPayload(plan_id=plan_id)
    return Event.new(
        stream=f"plan:{plan_id}",
        type=EventType.PlanApproved,
        payload=payload.model_dump(mode="json"),
        actor="human",
    )


def commit_recorded(sha, task_id, run_id):
    payload = CommitRecordedPayload(
        sha=sha,
        task_id=task_id,
        run_id=run_id,
        branch=f"openfactory/{task_id}",
        spec_version="sv_01",
        files=["app/auth/login.py"],
    )
    return Event.new(
        stream=f"task:{task_id}",
        type=EventType.CommitRecorded,
        payload=payload.model_dump(mode="json"),
        actor="orchestrator",
    )


def started(run_id, task_id="AUTH-001"):
    payload = AgentRunStartedPayload(
        run_id=run_id,
        task_id=task_id,
        role="implementer" if task_id else "planner",
        runtime="claude-code",
        context_hash=HASH,
    )
    return Event.new(
        stream=f"run:{run_id}",
        type=EventType.AgentRunStarted,
        payload=payload.model_dump(mode="json"),
        actor="orchestrator",
    )


def finished(run_id):
    payload = AgentRunFinishedPayload(
        run_id=run_id,
        exit="ok",
        model="claude-sonnet",
        tokens_in=10,
        tokens_out=5,
        cost_usd=0.01,
        duration_s=1.5,
        error=None,
    )
    return Event.new(
        stream=f"run:{run_id}",
        type=EventType.AgentRunFinished,
        payload=payload.model_dump(mode="json"),
        actor="orchestrator",
    )


def commit_ref(sha, task_id):
    from openfactory.domain.plans import CommitRef

    return CommitRef(sha=sha, task_id=task_id)


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


@pytest.fixture
def runs(db, recorder):
    adapter = SqliteRuns(db)
    yield adapter
    adapter.close()


@pytest.fixture
def approved_plan(recorder):
    recorder.record(plan_created())
    recorder.record(plan_approved())


# AC2: no commit


def test_ac2_approved_plan_without_a_commit_gives_none(approved_plan, plans):
    assert plans.latest_commit("plan_01") is None


def test_ac2_unknown_plan_and_empty_log_give_none(recorder, plans):
    assert plans.latest_commit("plan_01") is None
    recorder.record(plan_created())
    assert plans.latest_commit("plan_99") is None


# AC3: latest commit of a plan


def test_ac3_latest_commit_follows_the_highest_run(approved_plan, recorder, plans):
    recorder.record(commit_recorded(SHA_A, "AUTH-001", "run_0002"))
    assert plans.latest_commit("plan_01") == commit_ref(SHA_A, "AUTH-001")
    recorder.record(commit_recorded(SHA_B, "AUTH-002", "run_0003"))
    assert plans.latest_commit("plan_01") == commit_ref(SHA_B, "AUTH-002")


def test_ac3_run_ids_are_compared_by_number(approved_plan, recorder, plans):
    recorder.record(commit_recorded(SHA_A, "AUTH-001", "run_9999"))
    recorder.record(commit_recorded(SHA_B, "AUTH-002", "run_10000"))
    assert plans.latest_commit("plan_01") == commit_ref(SHA_B, "AUTH-002")


def test_ac3_only_the_tasks_of_the_plan_count(approved_plan, recorder, plans):
    recorder.record(plan_created("plan_02", tasks=(API_001,)))
    recorder.record(commit_recorded(SHA_A, "AUTH-001", "run_0002"))
    assert plans.latest_commit("plan_02") is None
    assert plans.latest_commit("plan_01") == commit_ref(SHA_A, "AUTH-001")


# AC4: unfinished run of a task


def test_ac4_no_run_gives_none(runs):
    assert runs.unfinished_run("AUTH-001") is None


def test_ac4_started_run_is_unfinished_until_finished(recorder, runs):
    recorder.record(started("run_0002"))
    assert runs.unfinished_run("AUTH-001") == "run_0002"
    recorder.record(finished("run_0002"))
    assert runs.unfinished_run("AUTH-001") is None


def test_ac4_runs_of_others_are_not_given(recorder, runs):
    recorder.record(started("run_0001", task_id=None))
    recorder.record(started("run_0002", task_id="AUTH-002"))
    assert runs.unfinished_run("AUTH-001") is None
    assert runs.next_id() == "run_0003"


# AC5: read-only, sees later events


def test_ac5_adapters_opened_early_see_later_events(approved_plan, recorder, plans, runs):
    assert plans.latest_commit("plan_01") is None
    assert runs.unfinished_run("AUTH-001") is None
    recorder.record(started("run_0002"))
    recorder.record(commit_recorded(SHA_A, "AUTH-001", "run_0002"))
    assert plans.latest_commit("plan_01") == commit_ref(SHA_A, "AUTH-001")
    assert runs.unfinished_run("AUTH-001") == "run_0002"
    recorder.record(finished("run_0002"))
    assert runs.unfinished_run("AUTH-001") is None


def test_ac5_the_reads_change_no_row(db, approved_plan, recorder):
    recorder.record(started("run_0002"))
    recorder.record(commit_recorded(SHA_A, "AUTH-001", "run_0002"))

    def snapshot():
        conn = sqlite3.connect(db)
        try:
            return {t: conn.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall() for t in TABLES}
        finally:
            conn.close()

    before = snapshot()
    plans_adapter = SqlitePlans(db)
    runs_adapter = SqliteRuns(db)
    plans_adapter.latest_commit("plan_01")
    runs_adapter.unfinished_run("AUTH-001")
    plans_adapter.close()
    runs_adapter.close()
    assert snapshot() == before
