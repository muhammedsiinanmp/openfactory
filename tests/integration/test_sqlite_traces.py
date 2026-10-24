"""TASK-081 AC2 to AC6: SqliteTraces.untested_requirements
(docs/tasks/TASK-081-traces-port.md)."""

import sqlite3

import pytest

from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.adapters.sqlite_traces import SqliteTraces
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType
from openfactory.domain.models import Priority, Requirement, SpecSet
from openfactory.domain.payloads import (
    CollectedTest,
    PlanApprovedPayload,
    PlanCreatedPayload,
    SpecImportedPayload,
    TestsCollectedPayload,
)

HASH = "a" * 64
GATES = ["path_check", "ruff", "pytest", "gitleaks", "review"]


def req(id, deprecated=False):
    return Requirement(
        id=id,
        title=f"Title {id}",
        statement="Users can do it.",
        priority=Priority.must,
        components=["auth"],
        deprecated=deprecated,
    )


def ev(stream, type_, payload, actor="orchestrator"):
    return Event.new(
        stream=stream, type=type_, payload=payload.model_dump(mode="json"), actor=actor
    )


def imported(version, requirements):
    spec = SpecSet(components=["auth"], requirements=list(requirements), adrs=[])
    payload = SpecImportedPayload(spec_version=version, hash=HASH, spec=spec)
    return ev(f"spec:{version}", EventType.SpecImported, payload)


def collected(*tests):
    payload = TestsCollectedPayload(
        run_id="run_0002",
        task_id="AUTH-001",
        tests=[CollectedTest(node_id=n, file=f, req=r) for n, f, r in tests],
    )
    return ev("task:AUTH-001", EventType.TestsCollected, payload)


def contract(task_id, requirements):
    return TaskContract(
        task_id=task_id,
        objective=f"Do {task_id}",
        requirements=requirements,
        acceptance_criteria=["AC-AUTH-001-1"],
        depends_on=[],
        components=["auth"],
        role="implementer",
        allowed_paths=["app/auth/**"],
        forbidden_paths=["specs/**"],
        required_gates=GATES,
        limits=Limits(max_runtime_s=1200, max_attempts=2, max_cost_usd=1.5),
    )


@pytest.fixture
def db(tmp_path):
    return tmp_path / "openfactory.db"


@pytest.fixture
def recorder(db):
    rec = SqliteEventRecorder(db)
    yield rec
    rec.close()


@pytest.fixture
def traces(db, recorder):
    adapter = SqliteTraces(db)
    yield adapter
    adapter.close()


# AC2: untested requirements of a version


def test_ac2_untagged_requirements_are_returned(recorder, traces):
    recorder.record(imported("sv_01", [req("REQ-A-1"), req("REQ-A-2"), req("REQ-A-3")]))
    recorder.record(
        collected(
            ("t.py::test_one", "t.py", ["REQ-A-1"]),
            ("t.py::test_untagged", "t.py", []),
        )
    )
    assert traces.untested_requirements("sv_01") == ["REQ-A-2", "REQ-A-3"]


def test_ac2_all_tagged_gives_empty_list(recorder, traces):
    recorder.record(imported("sv_01", [req("REQ-A-1"), req("REQ-A-2")]))
    recorder.record(collected(("t.py::test_one", "t.py", ["REQ-A-1", "REQ-A-2"])))
    assert traces.untested_requirements("sv_01") == []


# AC3: deprecated requirements


def test_ac3_deprecated_requirements_are_never_returned(recorder, traces):
    recorder.record(
        imported(
            "sv_01",
            [req("REQ-A-1"), req("REQ-A-2", deprecated=True), req("REQ-A-3", deprecated=True)],
        )
    )
    recorder.record(collected(("t.py::test_dep", "t.py", ["REQ-A-3"])))
    assert traces.untested_requirements("sv_01") == ["REQ-A-1"]


# AC4: only test_tag links from a test count


def test_ac4_a_contract_link_does_not_count_as_a_test(recorder, traces):
    recorder.record(imported("sv_01", [req("REQ-A-1"), req("REQ-A-2")]))
    created = PlanCreatedPayload(
        plan_id="plan_01",
        spec_version="sv_01",
        policy_hash=HASH,
        run_id="run_0001",
        tasks=[contract("AUTH-001", ["REQ-A-1"])],
    )
    recorder.record(ev("plan:plan_01", EventType.PlanCreated, created))
    recorder.record(
        ev("plan:plan_01", EventType.PlanApproved, PlanApprovedPayload(plan_id="plan_01"), "human")
    )
    assert traces.untested_requirements("sv_01") == ["REQ-A-1", "REQ-A-2"]


def test_ac4_a_later_collection_that_drops_a_tag_returns_the_requirement(recorder, traces):
    recorder.record(imported("sv_01", [req("REQ-A-1"), req("REQ-A-2")]))
    recorder.record(collected(("t.py::test_one", "t.py", ["REQ-A-1", "REQ-A-2"])))
    assert traces.untested_requirements("sv_01") == []
    recorder.record(collected(("t.py::test_one", "t.py", ["REQ-A-1"])))
    assert traces.untested_requirements("sv_01") == ["REQ-A-2"]


# AC5: per version, sorted as strings


def test_ac5_each_version_returns_only_its_own_requirements(recorder, traces):
    recorder.record(imported("sv_01", [req("REQ-A-1"), req("REQ-A-2")]))
    recorder.record(imported("sv_02", [req("REQ-B-1"), req("REQ-A-2")]))
    recorder.record(collected(("t.py::test_one", "t.py", ["REQ-A-2"])))
    assert traces.untested_requirements("sv_01") == ["REQ-A-1"]
    assert traces.untested_requirements("sv_02") == ["REQ-B-1"]


def test_ac5_unknown_version_gives_empty_list(recorder, traces):
    recorder.record(imported("sv_01", [req("REQ-A-1")]))
    assert traces.untested_requirements("sv_09") == []


def test_ac5_ids_are_sorted_as_strings(recorder, traces):
    ids = ["REQ-A-2", "REQ-A-10", "REQ-A-1", "REQ-B-1", "REQ-A-20"]
    recorder.record(imported("sv_01", [req(i) for i in ids]))
    assert traces.untested_requirements("sv_01") == sorted(ids)
    assert traces.untested_requirements("sv_01")[:3] == ["REQ-A-1", "REQ-A-10", "REQ-A-2"]


# AC6: read-only


def snapshot(db):
    conn = sqlite3.connect(db)
    try:
        names = [
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY 1")
        ]
        return {t: conn.execute(f"SELECT * FROM {t} ORDER BY 1, 2").fetchall() for t in names}
    finally:
        conn.close()


def test_ac6_the_read_changes_no_row_and_creates_no_table(db, recorder):
    recorder.record(imported("sv_01", [req("REQ-A-1"), req("REQ-A-2")]))
    recorder.record(collected(("t.py::test_one", "t.py", ["REQ-A-1"])))
    before = snapshot(db)
    adapter = SqliteTraces(db)
    adapter.untested_requirements("sv_01")
    adapter.untested_requirements("sv_09")
    adapter.close()
    assert snapshot(db) == before
    assert "trace_links" in before


def test_ac6_a_database_without_projections_raises_operational_error(db):
    adapter = SqliteTraces(db)
    try:
        with pytest.raises(sqlite3.OperationalError):
            adapter.untested_requirements("sv_01")
    finally:
        adapter.close()


# TASK-083: SqliteTraces.requirement_trace (docs/tasks/TASK-083-traces-trace-read.md)

from openfactory.domain.payloads import (  # noqa: E402
    CommitRecordedPayload,
    SpecApprovedPayload,
    TaskStateChangedPayload,
)
from openfactory.domain.states import TaskState  # noqa: E402
from openfactory.domain.traces import (  # noqa: E402
    RequirementTrace,
    TracedCommit,
    TracedTask,
    TracedTest,
)


def approved(version):
    return ev(
        f"spec:{version}",
        EventType.SpecApproved,
        SpecApprovedPayload(spec_version=version, hash=HASH),
        "human",
    )


def state(task_id, from_, to, reason=None):
    payload = TaskStateChangedPayload(task_id=task_id, from_=from_, to=to, reason=reason)
    return ev(f"task:{task_id}", EventType.TaskStateChanged, payload)


def commit(sha_char, task_id, run_id, files):
    payload = CommitRecordedPayload(
        sha=sha_char * 40,
        task_id=task_id,
        run_id=run_id,
        branch=f"task/{task_id}",
        spec_version="sv_02",
        files=files,
    )
    return ev(f"task:{task_id}", EventType.CommitRecorded, payload)


def contract_with_deps(task_id, requirements, depends_on):
    return contract(task_id, requirements).model_copy(update={"depends_on": depends_on})


@pytest.fixture
def world(recorder):
    recorder.record(imported("sv_01", [req("REQ-A-1"), req("REQ-A-2"), req("REQ-OLD-1")]))
    recorder.record(approved("sv_01"))
    recorder.record(imported("sv_02", [req("REQ-A-1"), req("REQ-A-2"), req("REQ-DEP-1", True)]))
    recorder.record(approved("sv_02"))
    recorder.record(imported("sv_03", [req("REQ-DRAFT-1")]))
    created = PlanCreatedPayload(
        plan_id="plan_01",
        spec_version="sv_02",
        policy_hash=HASH,
        run_id="run_0001",
        tasks=[
            contract("AUTH-010", ["REQ-A-1"]),
            contract("AUTH-002", ["REQ-A-1"]),
            contract("AUTH-003", ["REQ-A-2"]),
            contract_with_deps("AUTH-004", ["REQ-A-2"], ["AUTH-002"]),
        ],
    )
    recorder.record(ev("plan:plan_01", EventType.PlanCreated, created))
    recorder.record(
        ev("plan:plan_01", EventType.PlanApproved, PlanApprovedPayload(plan_id="plan_01"), "human")
    )
    recorder.record(state("AUTH-010", TaskState.pending, TaskState.ready))
    recorder.record(state("AUTH-002", TaskState.pending, TaskState.ready))
    recorder.record(state("AUTH-010", TaskState.ready, TaskState.running))
    recorder.record(state("AUTH-010", TaskState.running, TaskState.passed))
    recorder.record(commit("b", "AUTH-010", "run_0002", ["app/z.py", "app/shared.py"]))
    recorder.record(commit("e", "AUTH-010", "run_0003", ["app/shared.py", "app/a.py"]))
    recorder.record(commit("f", "AUTH-002", "run_0004", ["app/m.py"]))
    recorder.record(commit("9", "AUTH-003", "run_0005", ["other/x.py"]))
    recorder.record(
        collected(
            ("t.py::a_tagged", "tests/other.py", ["REQ-A-1"]),
            ("t.py::b_file", "app/m.py", []),
            ("t.py::c_both", "app/z.py", ["REQ-A-1"]),
            ("t.py::d_file", "app/shared.py", ["REQ-A-2"]),
            ("t.py::e_tagged", "tests/other.py", ["REQ-A-1", "REQ-A-2"]),
            ("t.py::f_untagged_outside", "other/x.py", []),
            ("t.py::g_other_req_outside", "other/x.py", ["REQ-A-2"]),
        )
    )


# AC2: unknown against known


@pytest.mark.parametrize("rid", ["REQ-NONE-9", "REQ-DRAFT-1"])
def test_task083_ac2_unknown_or_draft_only_requirement_gives_none(world, traces, rid):
    assert traces.requirement_trace(rid) is None


@pytest.mark.parametrize("rid", ["REQ-OLD-1", "REQ-DEP-1"])
def test_task083_ac2_old_approved_or_deprecated_requirement_gives_empty_trace(world, traces, rid):
    assert traces.requirement_trace(rid) == RequirementTrace(
        tasks=[], commits=[], files=[], tests=[]
    )


# AC3: tasks


def test_task083_ac3_tasks_with_state_sorted_as_strings(world, traces):
    result = traces.requirement_trace("REQ-A-1")
    assert result.tasks == [
        TracedTask(task_id="AUTH-002", state=TaskState.ready),
        TracedTask(task_id="AUTH-010", state=TaskState.passed),
    ]


def test_task083_ac3_dependency_only_task_is_excluded(world, traces):
    ids = [t.task_id for t in traces.requirement_trace("REQ-A-2").tasks]
    assert ids == ["AUTH-003", "AUTH-004"]
    assert "AUTH-004" not in [t.task_id for t in traces.requirement_trace("REQ-A-1").tasks]


# AC4: commits and files


def test_task083_ac4_commits_by_task_id_then_sha(world, traces):
    assert traces.requirement_trace("REQ-A-1").commits == [
        TracedCommit(sha="f" * 40, task_id="AUTH-002"),
        TracedCommit(sha="b" * 40, task_id="AUTH-010"),
        TracedCommit(sha="e" * 40, task_id="AUTH-010"),
    ]


def test_task083_ac4_files_once_sorted_and_only_of_those_commits(world, traces):
    assert traces.requirement_trace("REQ-A-1").files == [
        "app/a.py",
        "app/m.py",
        "app/shared.py",
        "app/z.py",
    ]


# AC5: tests


def test_task083_ac5_tests_interleaved_by_node_id_tagged_wins(world, traces):
    assert traces.requirement_trace("REQ-A-1").tests == [
        TracedTest(node_id="t.py::a_tagged", tagged=True),
        TracedTest(node_id="t.py::b_file", tagged=False),
        TracedTest(node_id="t.py::c_both", tagged=True),
        TracedTest(node_id="t.py::d_file", tagged=False),
        TracedTest(node_id="t.py::e_tagged", tagged=True),
    ]


# AC6: read-only


def test_task083_ac6_requirement_trace_changes_nothing(db, recorder, world):
    before = snapshot(db)
    adapter = SqliteTraces(db)
    adapter.requirement_trace("REQ-A-1")
    adapter.requirement_trace("REQ-NONE-9")
    adapter.close()
    assert snapshot(db) == before


# TASK-085: SqliteTraces.file_trace (docs/tasks/TASK-085-traces-why-read.md)

LOGIN = "app/auth/login.py"


def constrained(requirement, adrs):
    return requirement.model_copy(update={"constrained_by": adrs})


@pytest.fixture
def why(recorder):
    recorder.record(
        imported(
            "sv_01",
            [
                constrained(req("REQ-A-1"), ["ADR-OLD", "ADR-001"]),
                constrained(req("REQ-A-2"), ["ADR-OLD"]),
            ],
        )
    )
    recorder.record(approved("sv_01"))
    recorder.record(
        imported(
            "sv_02",
            [
                constrained(req("REQ-A-1"), ["ADR-003", "ADR-001"]),
                constrained(req("REQ-A-2"), ["ADR-002", "ADR-001"]),
                req("REQ-A-3"),
                constrained(req("REQ-B-1"), ["ADR-009"]),
            ],
        )
    )
    recorder.record(approved("sv_02"))
    created = PlanCreatedPayload(
        plan_id="plan_01",
        spec_version="sv_02",
        policy_hash=HASH,
        run_id="run_0001",
        tasks=[
            contract("AUTH-010", ["REQ-A-1", "REQ-A-2"]),
            contract("AUTH-020", ["REQ-A-1", "REQ-A-3"]),
            contract("AUTH-030", ["REQ-A-1"]),
            contract_with_deps("AUTH-040", ["REQ-B-1"], ["AUTH-010"]),
        ],
    )
    recorder.record(ev("plan:plan_01", EventType.PlanCreated, created))
    recorder.record(
        ev("plan:plan_01", EventType.PlanApproved, PlanApprovedPayload(plan_id="plan_01"), "human")
    )
    recorder.record(state("AUTH-010", TaskState.pending, TaskState.ready))
    recorder.record(state("AUTH-020", TaskState.pending, TaskState.ready))
    recorder.record(state("AUTH-010", TaskState.ready, TaskState.running))
    recorder.record(state("AUTH-010", TaskState.running, TaskState.passed))
    recorder.record(commit("d", "AUTH-010", "run_0002", [LOGIN, "app/x.py"]))
    recorder.record(commit("b", "AUTH-010", "run_0003", ["app/auth/login.py"]))
    recorder.record(commit("e", "AUTH-010", "run_0004", ["app/only_other.py"]))
    recorder.record(commit("a", "AUTH-020", "run_0005", [LOGIN]))
    recorder.record(commit("f", "AUTH-020", "run_0006", ["app/only_other.py"]))
    recorder.record(commit("9", "AUTH-030", "run_0007", ["app/only_other.py"]))
    recorder.record(collected(("t.py::test_one", "tests/only_test.py", ["REQ-A-1"])))


# AC2: exact string match, refusal as None


@pytest.mark.parametrize(
    "path",
    [
        "nope.py",
        "./app/auth/login.py",
        "App/Auth/Login.py",
        "app/",
        "app",
        "app/auth",
        "tests/only_test.py",
    ],
)
def test_task085_ac2_path_no_commit_changed_gives_none(why, traces, path):
    assert traces.file_trace(path) is None


def test_task085_ac2_exact_changed_path_gives_a_file_trace(why, traces):
    from openfactory.domain.traces import FileTrace

    assert isinstance(traces.file_trace(LOGIN), FileTrace)


# AC3: commits


def test_task085_ac3_commits_by_task_id_then_sha(why, traces):
    assert traces.file_trace(LOGIN).commits == [
        TracedCommit(sha="b" * 40, task_id="AUTH-010"),
        TracedCommit(sha="d" * 40, task_id="AUTH-010"),
        TracedCommit(sha="a" * 40, task_id="AUTH-020"),
    ]


# AC4: tasks


def test_task085_ac4_tasks_once_with_current_state_sorted(why, traces):
    assert traces.file_trace(LOGIN).tasks == [
        TracedTask(task_id="AUTH-010", state=TaskState.passed),
        TracedTask(task_id="AUTH-020", state=TaskState.ready),
    ]


# AC5: requirements and ADRs


def test_task085_ac5_requirements_once_sorted_without_dependency_or_other_tasks(why, traces):
    assert traces.file_trace(LOGIN).requirements == ["REQ-A-1", "REQ-A-2", "REQ-A-3"]


def test_task085_ac5_adrs_of_latest_approved_version_once_sorted(why, traces):
    assert traces.file_trace(LOGIN).adrs == ["ADR-001", "ADR-002", "ADR-003"]


# AC6: read-only


def test_task085_ac6_file_trace_changes_nothing(db, recorder, why):
    before = snapshot(db)
    adapter = SqliteTraces(db)
    adapter.file_trace(LOGIN)
    adapter.file_trace("nope.py")
    adapter.close()
    assert snapshot(db) == before


# TASK-094: SqliteTraces.impact_traversal (docs/tasks/TASK-094-traces-impact-traversal.md)

SEEDS = ["REQ-A-1"]


@pytest.fixture
def impact(recorder):
    recorder.record(imported("sv_01", [req("REQ-A-1"), req("REQ-A-2"), req("REQ-A-3")]))
    recorder.record(approved("sv_01"))
    plan_1 = PlanCreatedPayload(
        plan_id="plan_01",
        spec_version="sv_01",
        policy_hash=HASH,
        run_id="run_0001",
        tasks=[
            contract("AUTH-002", ["REQ-A-1"]),
            contract("AUTH-003", ["REQ-A-1"]),
            contract("AUTH-004", ["REQ-A-2"]),
            contract_with_deps("AUTH-005", ["REQ-A-2"], ["AUTH-003"]),
            contract_with_deps("AUTH-006", ["REQ-A-2"], ["AUTH-005"]),
            contract("AUTH-007", ["REQ-A-1"]),
            contract("AUTH-008", ["REQ-A-1"]),
            contract_with_deps("AUTH-009", ["REQ-A-2"], ["AUTH-002"]),
            contract_with_deps("AUTH-010", ["REQ-A-2"], ["AUTH-002"]),
            contract_with_deps("AUTH-011", ["REQ-A-2"], ["AUTH-007"]),
            contract_with_deps("AUTH-012", ["REQ-A-2"], ["AUTH-011"]),
            contract_with_deps("AUTH-013", ["REQ-A-2"], ["AUTH-004"]),
        ],
    )
    recorder.record(ev("plan:plan_01", EventType.PlanCreated, plan_1))
    recorder.record(
        ev("plan:plan_01", EventType.PlanApproved, PlanApprovedPayload(plan_id="plan_01"), "human")
    )
    plan_2 = PlanCreatedPayload(
        plan_id="plan_02",
        spec_version="sv_01",
        policy_hash=HASH,
        run_id="run_0009",
        tasks=[contract("AUTH-020", ["REQ-A-1"])],
    )
    recorder.record(ev("plan:plan_02", EventType.PlanCreated, plan_2))
    recorder.record(state("AUTH-007", TaskState.pending, TaskState.invalidated, "test"))
    recorder.record(state("AUTH-008", TaskState.pending, TaskState.abandoned, "test"))
    recorder.record(state("AUTH-009", TaskState.pending, TaskState.invalidated, "test"))
    recorder.record(state("AUTH-010", TaskState.pending, TaskState.abandoned, "test"))
    recorder.record(commit("a", "AUTH-002", "run_0002", ["app/imp.py", "app/shared.py"]))
    recorder.record(commit("b", "AUTH-005", "run_0003", ["app/down.py", "app/shared.py"]))
    recorder.record(commit("c", "AUTH-006", "run_0004", ["app/down.py"]))
    recorder.record(commit("d", "AUTH-004", "run_0005", ["app/untouched.py"]))
    recorder.record(commit("e", "AUTH-007", "run_0006", ["app/excluded.py"]))
    recorder.record(commit("f", "AUTH-020", "run_0007", ["app/other_plan.py"]))
    recorder.record(
        collected(
            ("t.py::a_tag", "tests/x.py", ["REQ-A-1"]),
            ("t.py::b_file", "app/imp.py", []),
            ("t.py::c_down", "app/down.py", ["REQ-A-2"]),
            ("t.py::d_both", "app/shared.py", ["REQ-A-1"]),
            ("t.py::e_unrelated", "app/untouched.py", ["REQ-A-2"]),
            ("t.py::f_excluded", "app/excluded.py", []),
            ("t.py::g_other_plan", "app/other_plan.py", []),
            ("t.py::h_a3", "tests/y.py", ["REQ-A-3"]),
        )
    )


def test_task094_ac1_impacted_tasks_are_live_in_plan_and_linked_to_a_seed(impact, traces):
    assert traces.impact_traversal("plan_01", SEEDS).tasks == ["AUTH-002", "AUTH-003"]


def test_task094_ac1_a_second_seed_adds_its_tasks(impact, traces):
    result = traces.impact_traversal("plan_01", ["REQ-A-1", "REQ-A-2"])
    assert "AUTH-004" in result.tasks
    assert "AUTH-007" not in result.tasks


def test_task094_ac2_downstream_follows_chains_through_live_tasks_only(impact, traces):
    result = traces.impact_traversal("plan_01", SEEDS)
    assert result.downstream == ["AUTH-005", "AUTH-006"]
    assert not set(result.tasks) & set(result.downstream)


def test_task094_ac3_files_of_impacted_and_downstream_commits_once(impact, traces):
    assert traces.impact_traversal("plan_01", SEEDS).files == [
        "app/down.py",
        "app/imp.py",
        "app/shared.py",
    ]


def test_task094_ac4_tests_tagged_with_seed_or_in_traversal_files(impact, traces):
    assert traces.impact_traversal("plan_01", SEEDS).tests == [
        "t.py::a_tag",
        "t.py::b_file",
        "t.py::c_down",
        "t.py::d_both",
    ]


def test_task094_ac4_seed_tagged_test_is_included_when_no_task_is_impacted(impact, traces):
    result = traces.impact_traversal("plan_01", ["REQ-A-3"])
    assert (result.tasks, result.downstream, result.files) == ([], [], [])
    assert result.tests == ["t.py::h_a3"]


def test_task094_ac5_empty_or_unlinked_seeds_give_empty_lists(impact, traces):
    for seeds in ([], ["REQ-NONE-9"]):
        result = traces.impact_traversal("plan_01", seeds)
        assert (result.tasks, result.downstream, result.files, result.tests) == ([], [], [], [])


def test_task094_ac5_lists_are_sorted_as_strings_without_duplicates(impact, traces):
    result = traces.impact_traversal("plan_01", ["REQ-A-1", "REQ-A-2"])
    for items in (result.tasks, result.downstream, result.files, result.tests):
        assert items == sorted(set(items))


def test_task094_ac6_impact_traversal_changes_nothing(db, recorder, impact):
    before = snapshot(db)
    adapter = SqliteTraces(db)
    adapter.impact_traversal("plan_01", SEEDS)
    adapter.impact_traversal("plan_02", [])
    adapter.close()
    assert snapshot(db) == before
