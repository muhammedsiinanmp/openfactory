"""TASK-082: the `requirement_coverage` use case (docs/tasks/TASK-082-coverage.md)."""

import inspect

import pytest
from pydantic import ValidationError

from openfactory.app.coverage import CoverageRefusal, CoverageReport, requirement_coverage
from openfactory.domain.spec_versions import SpecVersionRef

HASH = "a" * 64


class FakeVersions:
    def __init__(self, approved: SpecVersionRef | None) -> None:
        self.approved = approved
        self.calls: list[str] = []

    def latest_approved(self) -> SpecVersionRef | None:
        self.calls.append("latest_approved")
        return self.approved

    def current_draft(self) -> SpecVersionRef | None:
        self.calls.append("current_draft")
        return None

    def next_id(self) -> str:
        self.calls.append("next_id")
        return "sv_99"

    def spec_set(self, version_id: str):  # noqa: ANN201
        self.calls.append("spec_set")
        return None


class FakeTraces:
    def __init__(self, result: list[str]) -> None:
        self.result = result
        self.asked: list[str] = []

    def untested_requirements(self, spec_version: str) -> list[str]:
        self.asked.append(spec_version)
        return self.result


def test_no_approved_version_is_refused_and_traces_is_not_asked() -> None:
    traces = FakeTraces(["REQ-X-1"])

    report = requirement_coverage(versions=FakeVersions(None), traces=traces)

    assert report.refusal is CoverageRefusal.no_approved_spec
    assert report.untested == []
    assert traces.asked == []


def test_latest_approved_id_is_passed_and_result_returned_unchanged() -> None:
    # Deliberately not in string order: the use case must not sort again.
    given = ["REQ-A-2", "REQ-A-10", "REQ-A-1"]
    traces = FakeTraces(given)

    report = requirement_coverage(
        versions=FakeVersions(SpecVersionRef(id="sv_02", hash=HASH)), traces=traces
    )

    assert traces.asked == ["sv_02"]
    assert report.refusal is None
    assert report.untested == given


def test_only_reads_are_called_and_the_signature_takes_no_recorder() -> None:
    versions = FakeVersions(SpecVersionRef(id="sv_01", hash=HASH))

    requirement_coverage(versions=versions, traces=FakeTraces([]))

    assert set(versions.calls) <= {"latest_approved"}
    params = inspect.signature(requirement_coverage).parameters
    assert set(params) == {"versions", "traces"}
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params.values())


def test_report_is_frozen() -> None:
    report = CoverageReport(refusal=None, untested=[])
    with pytest.raises(ValidationError):
        report.untested = ["x"]  # type: ignore[misc]
