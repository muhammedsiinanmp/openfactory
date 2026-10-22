"""TASK-086: the `why_file` use case (docs/tasks/TASK-086-why.md)."""

import inspect

from openfactory.domain.states import TaskState
from openfactory.domain.traces import FileTrace, RequirementTrace, TracedCommit, TracedTask


class FakeTraces:
    def __init__(self, result: FileTrace | None) -> None:
        self.result = result
        self.calls: list[tuple[str, tuple]] = []

    def file_trace(self, path: str) -> FileTrace | None:
        self.calls.append(("file_trace", (path,)))
        return self.result

    def requirement_trace(self, requirement_id: str) -> RequirementTrace | None:
        self.calls.append(("requirement_trace", (requirement_id,)))
        return None

    def untested_requirements(self, spec_version: str) -> list[str]:
        self.calls.append(("untested_requirements", (spec_version,)))
        return []


TRACE = FileTrace(
    commits=[TracedCommit(sha="b" * 40, task_id="AUTH-010")],
    tasks=[TracedTask(task_id="AUTH-010", state=TaskState.passed)],
    requirements=["REQ-Z-1", "REQ-A-1"],
    adrs=["ADR-009", "ADR-001"],
)


def test_none_from_the_read_is_a_no_commit_changed_refusal() -> None:
    from openfactory.app.why import WhyRefusal, WhyReport, why_file

    report = why_file("app/x.py", traces=FakeTraces(None))

    assert report == WhyReport(refusal=WhyRefusal.no_commit_changed, trace=None)
    assert report.refusal == WhyRefusal.no_commit_changed


def test_the_trace_is_returned_unchanged_without_a_second_sort() -> None:
    from openfactory.app.why import why_file

    report = why_file("app/x.py", traces=FakeTraces(TRACE))

    assert report.refusal is None
    assert report.trace == TRACE
    assert report.trace is not None
    assert report.trace.requirements == ["REQ-Z-1", "REQ-A-1"]
    assert report.trace.adrs == ["ADR-009", "ADR-001"]


def test_the_path_is_passed_unchanged_and_only_file_trace_is_called() -> None:
    from openfactory.app.why import why_file

    fake = FakeTraces(TRACE)
    why_file("./app/", traces=fake)

    assert fake.calls == [("file_trace", ("./app/",))]


def test_the_use_case_takes_only_the_path_and_traces() -> None:
    from openfactory.app.why import why_file

    params = inspect.signature(why_file).parameters
    assert list(params) == ["path", "traces"]
    assert params["traces"].kind is inspect.Parameter.KEYWORD_ONLY
