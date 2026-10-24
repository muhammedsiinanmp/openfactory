"""TASK-083 AC1: the frozen result models of domain/traces.py
(docs/tasks/TASK-083-traces-trace-read.md)."""

import pytest
from pydantic import ValidationError

from openfactory.domain.states import TaskState
from openfactory.domain.traces import (
    RequirementTrace,
    TracedCommit,
    TracedTask,
    TracedTest,
)


def make_all():
    task = TracedTask(task_id="AUTH-001", state=TaskState.ready)
    commit = TracedCommit(sha="a" * 40, task_id="AUTH-001")
    test = TracedTest(node_id="t.py::test_one", tagged=True)
    trace = RequirementTrace(tasks=[task], commits=[commit], files=["app/a.py"], tests=[test])
    return [task, commit, test, trace]


@pytest.mark.parametrize("index", range(4))
def test_task083_ac1_models_are_frozen(index):
    model = make_all()[index]
    field = next(iter(type(model).model_fields))
    with pytest.raises(ValidationError):
        setattr(model, field, getattr(model, field))


def test_task083_ac1_models_forbid_extra_fields():
    with pytest.raises(ValidationError):
        TracedTest(node_id="t.py::test_one", tagged=True, kind="file")


# TASK-085 AC1: FileTrace (docs/tasks/TASK-085-traces-why-read.md)


def make_file_trace():
    from openfactory.domain.traces import FileTrace

    return FileTrace(
        commits=[TracedCommit(sha="a" * 40, task_id="AUTH-001")],
        tasks=[TracedTask(task_id="AUTH-001", state=TaskState.ready)],
        requirements=["REQ-A-1"],
        adrs=["ADR-001"],
    )


def test_task085_ac1_file_trace_is_frozen():
    trace = make_file_trace()
    with pytest.raises(ValidationError):
        trace.adrs = []


def test_task085_ac1_file_trace_forbids_extra_fields():
    from openfactory.domain.traces import FileTrace

    with pytest.raises(ValidationError):
        FileTrace(commits=[], tasks=[], requirements=[], adrs=[], files=[])


# TASK-088 AC6


def test_task088_trace_link_is_frozen_hashable_and_forbids_extra_fields():
    from openfactory.domain.traces import TraceLink

    link = TraceLink(
        from_kind="requirement", from_id="REQ-A-1", to_kind="task", to_id="T-1", source="contract"
    )
    same = TraceLink(
        from_kind="requirement", from_id="REQ-A-1", to_kind="task", to_id="T-1", source="contract"
    )
    with pytest.raises(ValidationError):
        link.from_id = "other"
    with pytest.raises(ValidationError):
        TraceLink(
            from_kind="task", from_id="a", to_kind="run", to_id="b", source="trailer", extra=1
        )
    assert link == same
    assert len({link, same}) == 1


@pytest.mark.parametrize(
    "bad",
    [
        {"from_kind": "branch"},
        {"to_kind": "plan"},
        {"source": "git"},
    ],
)
def test_task088_trace_link_rejects_unknown_kind_or_source(bad):
    from openfactory.domain.traces import TraceLink

    fields = {
        "from_kind": "task",
        "from_id": "a",
        "to_kind": "run",
        "to_id": "b",
        "source": "trailer",
    } | bad
    with pytest.raises(ValidationError):
        TraceLink(**fields)


# TASK-094 AC1: ImpactTraversal (docs/tasks/TASK-094-traces-impact-traversal.md)


def make_impact():
    from openfactory.domain.traces import ImpactTraversal

    return ImpactTraversal(
        tasks=["AUTH-002"], downstream=["AUTH-005"], files=["app/a.py"], tests=["t.py::x"]
    )


def test_task094_ac5_impact_traversal_is_frozen():
    with pytest.raises(ValidationError):
        make_impact().tasks = []


def test_task094_ac5_impact_traversal_forbids_extra_fields():
    from openfactory.domain.traces import ImpactTraversal

    with pytest.raises(ValidationError):
        ImpactTraversal(tasks=[], downstream=[], files=[], tests=[], extra=1)
