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
