"""TASK-037: the deleted-requirement rule (AC1 domain part to AC5).

See docs/tasks/TASK-037-deleted-requirement-rule.md. The use case is driven through
in-memory fakes of SpecFiles, SpecVersions, Plans and the recorder.
"""

from openfactory.app.spec_loader import load_spec
from openfactory.app.validate import ValidateResult, validate
from openfactory.domain.events import Event, StoredEvent
from openfactory.domain.models import SpecSet
from openfactory.domain.payloads import SpecValidatedPayload
from openfactory.domain.spec_hash import content_hash
from openfactory.domain.spec_validation import (
    Rule,
    deleted_requirement_violation,
    deleted_requirements,
    validate_spec,
)
from openfactory.domain.spec_versions import SpecVersionRef

POLICY = "max_attempts: 3\n"


def _req(n: int, criteria: bool = True, deprecated: bool = False) -> str:
    text = (
        f"  - id: REQ-AUTH-{n:03d}\n"
        f"    title: Req {n}\n"
        f"    statement: Statement {n}.\n"
        "    priority: must\n"
    )
    if deprecated:
        text += "    deprecated: true\n"
    if criteria:
        text += f"    acceptance_criteria:\n      - id: AC-AUTH-{n:03d}-1\n        text: Works.\n"
    return text


def _yaml(*reqs: str) -> str:
    return "requirements:\n" + "".join(reqs)


class FakeSpecFiles:
    def __init__(self, requirements: str | None) -> None:
        self.files = {"policies.yaml": POLICY}
        if requirements is not None:
            self.files["requirements.yaml"] = requirements

    def read(self, path: str) -> str | None:
        return self.files.get(path)

    def list_adrs(self) -> list[str]:
        return []


class FakeVersions:
    def __init__(
        self,
        approved: SpecVersionRef | None = None,
        draft: SpecVersionRef | None = None,
        approved_set: SpecSet | None = None,
    ) -> None:
        self.approved = approved
        self.draft = draft
        self.approved_set = approved_set

    def latest_approved(self) -> SpecVersionRef | None:
        return self.approved

    def current_draft(self) -> SpecVersionRef | None:
        return self.draft

    def next_id(self) -> str:
        return "sv_02"

    def spec_set(self, version_id: str) -> SpecSet | None:
        assert self.approved is not None and version_id == self.approved.id
        return self.approved_set


class FakePlans:
    def __init__(self, answers: dict[str, list[str]] | None = None) -> None:
        self.answers = answers or {}
        self.asked: list[str] = []

    def current_draft(self):  # noqa: ANN201
        return None

    def approved(self):  # noqa: ANN201
        return None

    def next_id(self) -> str:
        return "plan_01"

    def tasks(self, plan_id: str):  # noqa: ANN201
        return []

    def live_tasks_referencing(self, requirement_id: str) -> list[str]:
        self.asked.append(requirement_id)
        return list(self.answers.get(requirement_id, []))


class FakeRecorder:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def record(self, event: Event) -> StoredEvent:
        self.events.append(event)
        return StoredEvent(**event.model_dump(), seq=len(self.events))


def _loaded(files: FakeSpecFiles) -> SpecSet:
    spec = load_spec(files).spec
    assert spec is not None
    return spec


APPROVED_FILES = FakeSpecFiles(_yaml(*(_req(n) for n in range(1, 6))))
APPROVED_SET = _loaded(APPROVED_FILES)
APPROVED = SpecVersionRef(id="sv_01", hash=content_hash(APPROVED_SET))


def _run(
    files: FakeSpecFiles,
    plans: FakePlans,
    versions: FakeVersions | None = None,
) -> tuple[ValidateResult, FakeRecorder]:
    versions = versions or FakeVersions(APPROVED, approved_set=APPROVED_SET)
    recorder = FakeRecorder()
    return validate(files, versions, plans, recorder), recorder


def _types(recorder: FakeRecorder) -> list[str]:
    return [e.type.value for e in recorder.events]


def _without_002() -> FakeSpecFiles:
    return FakeSpecFiles(_yaml(_req(1), _req(3), _req(4), _req(5)))


def test_ac1_deleted_requirements_are_absent_ids_in_order_and_deprecated_is_kept() -> None:
    loaded = _loaded(FakeSpecFiles(_yaml(_req(1), _req(4, deprecated=True), _req(6))))

    assert deleted_requirements(APPROVED_SET, loaded) == [
        "REQ-AUTH-002",
        "REQ-AUTH-003",
        "REQ-AUTH-005",
    ]
    assert not [v for v in validate_spec(loaded) if v.rule.value == "deleted-requirement"]


def test_ac2_message_lists_task_ids_in_ascending_order() -> None:
    violation = deleted_requirement_violation("REQ-AUTH-002", ["AUTH-010", "AUTH-002"])

    assert violation.rule is Rule.deleted_requirement
    assert violation.subject == "REQ-AUTH-002"
    assert violation.message == (
        "requirement 'REQ-AUTH-002' is deleted but tasks still reference it: AUTH-002, AUTH-010"
    )


def test_ac2_validate_reports_one_violation_and_records_it() -> None:
    plans = FakePlans({"REQ-AUTH-002": ["AUTH-010", "AUTH-002"]})
    result, recorder = _run(_without_002(), plans)

    assert result.outcome == "validated"
    (violation,) = result.violations
    assert violation.rule.value == "deleted-requirement"
    assert violation.subject == "REQ-AUTH-002"
    assert violation.message.index("AUTH-002,") < violation.message.index("AUTH-010")

    assert _types(recorder) == ["SpecImported", "SpecValidated"]
    assert {e.stream for e in recorder.events} == {"spec:sv_02"}
    payload = SpecValidatedPayload.model_validate(recorder.events[1].payload)
    assert [(v.rule, v.subject, v.message) for v in payload.violations] == [
        ("deleted-requirement", "REQ-AUTH-002", violation.message)
    ]


def test_ac3_one_violation_per_deleted_requirement_with_live_tasks_in_rule_order() -> None:
    files = FakeSpecFiles(_yaml(_req(1, criteria=False), _req(4, deprecated=True)))
    plans = FakePlans(
        {
            "REQ-AUTH-002": ["AUTH-002", "AUTH-003"],
            "REQ-AUTH-004": ["AUTH-004"],
            "REQ-AUTH-005": ["AUTH-005"],
        }
    )
    result, recorder = _run(files, plans)

    expected = [
        ("missing-acceptance-criteria", "REQ-AUTH-001"),
        ("deleted-requirement", "REQ-AUTH-002"),
        ("deleted-requirement", "REQ-AUTH-005"),
    ]
    assert [(v.rule.value, v.subject) for v in result.violations] == expected
    payload = SpecValidatedPayload.model_validate(recorder.events[-1].payload)
    assert [(v.rule, v.subject) for v in payload.violations] == expected
    assert plans.asked == ["REQ-AUTH-002", "REQ-AUTH-003", "REQ-AUTH-005"]


def test_ac4_no_approved_version_never_asks_plans() -> None:
    plans = FakePlans({"REQ-AUTH-002": ["AUTH-002"]})
    result, _ = _run(_without_002(), plans, FakeVersions())

    assert result.outcome == "validated"
    assert not [v for v in result.violations if v.rule.value == "deleted-requirement"]
    assert plans.asked == []


def test_ac4_unloadable_files_never_ask_plans_and_record_nothing() -> None:
    plans = FakePlans({"REQ-AUTH-002": ["AUTH-002"]})
    result, recorder = _run(FakeSpecFiles("requirements: [unclosed\n"), plans)

    assert result.outcome == "unloadable"
    assert not [v for v in result.violations if v.rule.value == "deleted-requirement"]
    assert recorder.events == []
    assert plans.asked == []


def test_ac4_files_equal_to_approved_never_ask_plans_and_record_nothing() -> None:
    plans = FakePlans({"REQ-AUTH-002": ["AUTH-002"]})
    result, recorder = _run(APPROVED_FILES, plans)

    assert result.outcome == "matches_approved"
    assert result.violations == []
    assert recorder.events == []
    assert plans.asked == []


def test_ac5_revalidating_an_unchanged_draft_follows_the_tasks() -> None:
    files = _without_002()
    draft = SpecVersionRef(id="sv_02", hash=content_hash(_loaded(files)))
    versions = FakeVersions(APPROVED, draft, APPROVED_SET)
    plans = FakePlans({"REQ-AUTH-002": ["AUTH-002"]})
    recorder = FakeRecorder()

    first = validate(files, versions, plans, recorder)
    assert _types(recorder) == ["SpecValidated"]
    assert [v.rule.value for v in first.violations] == ["deleted-requirement"]
    first_payload = SpecValidatedPayload.model_validate(recorder.events[0].payload)
    assert [v.rule for v in first_payload.violations] == ["deleted-requirement"]

    plans.answers = {"REQ-AUTH-002": []}  # the task was abandoned
    second = validate(files, versions, plans, recorder)
    assert _types(recorder) == ["SpecValidated", "SpecValidated"]
    assert recorder.events[1].stream == "spec:sv_02"
    assert SpecValidatedPayload.model_validate(recorder.events[1].payload).violations == []
    assert second.violations == []
