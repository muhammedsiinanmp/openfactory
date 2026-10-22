"""TASK-084: the `trace_requirement` use case (docs/tasks/TASK-084-trace.md)."""

import inspect

from openfactory.domain.states import TaskState
from openfactory.domain.traces import RequirementTrace, TracedCommit, TracedTask, TracedTest


class FakeTraces:
    def __init__(self, result: RequirementTrace | None) -> None:
        self.result = result
        self.calls: list[tuple[str, tuple]] = []

    def requirement_trace(self, requirement_id: str) -> RequirementTrace | None:
        self.calls.append(("requirement_trace", (requirement_id,)))
        return self.result

    def untested_requirements(self, spec_version: str) -> list[str]:
        self.calls.append(("untested_requirements", (spec_version,)))
        return []


TRACE = RequirementTrace(
    tasks=[TracedTask(task_id="AUTH-010", state=TaskState.passed)],
    commits=[TracedCommit(sha="b" * 40, task_id="AUTH-010")],
    files=["z.py", "a.py"],
    tests=[TracedTest(node_id="t.py::test_z", tagged=True), TracedTest(node_id="a", tagged=False)],
)


def test_none_from_the_read_is_an_unknown_requirement_refusal() -> None:
    from openfactory.app.trace import TraceRefusal, TraceReport, trace_requirement

    report = trace_requirement("REQ-X-1", traces=FakeTraces(None))

    assert report == TraceReport(refusal=TraceRefusal.unknown_requirement, trace=None)
    assert report.refusal == TraceRefusal.unknown_requirement


def test_the_trace_is_returned_unchanged_without_a_second_sort() -> None:
    from openfactory.app.trace import trace_requirement

    report = trace_requirement("REQ-A-1", traces=FakeTraces(TRACE))

    assert report.refusal is None
    assert report.trace == TRACE
    assert report.trace is not None
    assert report.trace.files == ["z.py", "a.py"]
    assert [t.node_id for t in report.trace.tests] == ["t.py::test_z", "a"]


def test_the_id_is_passed_through_and_only_requirement_trace_is_called() -> None:
    from openfactory.app.trace import trace_requirement

    fake = FakeTraces(TRACE)
    trace_requirement("REQ-A-1", traces=fake)

    assert fake.calls == [("requirement_trace", ("REQ-A-1",))]


def test_the_use_case_takes_only_the_id_and_traces() -> None:
    from openfactory.app.trace import trace_requirement

    params = inspect.signature(trace_requirement).parameters
    assert list(params) == ["requirement_id", "traces"]
    assert params["traces"].kind is inspect.Parameter.KEYWORD_ONLY
