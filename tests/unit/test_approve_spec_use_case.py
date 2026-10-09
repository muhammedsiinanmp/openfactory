"""TASK-013: approve spec use case.

Each test names the acceptance criterion it covers (AC1..AC6 in
docs/tasks/TASK-013-approve-spec-use-case.md). The use case is driven through in-memory
fakes of SpecFiles, SpecVersions and EventRecorder; no filesystem or database is used.
"""

import ast
from pathlib import Path

from openfactory.app.approve_spec import ApproveResult, approve_spec
from openfactory.app.spec_loader import load_spec
from openfactory.domain.events import Event, StoredEvent
from openfactory.domain.models import SpecSet
from openfactory.domain.payloads import SpecApprovedPayload, SpecValidatedPayload
from openfactory.domain.spec_hash import content_hash
from openfactory.domain.spec_validation import validate_spec
from openfactory.domain.spec_versions import SpecVersionRef

APP_DIR = Path(__file__).resolve().parents[2] / "src" / "openfactory" / "app"

POLICY = "max_attempts: 3\n"

REQUIREMENTS = """\
components: [payments, auth]
requirements:
  - id: REQ-AUTH-002
    title: Logout
    statement: Users can log out.
    priority: should
    components: [payments, auth]
    constrained_by: [ADR-001]
    acceptance_criteria:
      - id: AC-AUTH-002-2
        text: Second.
      - id: AC-AUTH-002-1
        text: First.
  - id: REQ-AUTH-001
    title: Login
    statement: Users can log in.
    priority: must
    acceptance_criteria:
      - id: AC-AUTH-001-1
        text: Valid login returns a JWT.
"""

ADR_001 = "---\nid: ADR-001\nstatus: accepted\ntitle: Auth\n---\nWe use JWT.\n"

# One requirement without acceptance criteria, constrained by an ADR that does not exist.
BAD_REQUIREMENTS = """\
requirements:
  - id: REQ-AUTH-001
    title: Login
    statement: Users can log in.
    priority: must
    constrained_by: [ADR-099]
"""


class FakeSpecFiles:
    def __init__(self, files: dict[str, str]):
        self.files = files

    def read(self, path: str) -> str | None:
        return self.files.get(path)

    def list_adrs(self) -> list[str]:
        return sorted(p for p in self.files if p.startswith("adrs/") and p.endswith(".md"))


class FakeVersions:
    def __init__(
        self,
        approved: SpecVersionRef | None = None,
        draft: SpecVersionRef | None = None,
        next_id: str = "sv_01",
    ):
        self.approved = approved
        self.draft = draft
        self.next = next_id

    def latest_approved(self) -> SpecVersionRef | None:
        return self.approved

    def current_draft(self) -> SpecVersionRef | None:
        return self.draft

    def next_id(self) -> str:
        return self.next


class FakeRecorder:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def record(self, event: Event) -> StoredEvent:
        self.events.append(event)
        return StoredEvent(**event.model_dump(), seq=len(self.events))


def good_files(policy: str | None = POLICY) -> FakeSpecFiles:
    files = {"requirements.yaml": REQUIREMENTS, "adrs/ADR-001-auth.md": ADR_001}
    if policy is not None:
        files["policies.yaml"] = policy
    return FakeSpecFiles(files)


def bad_content_files(policy: str = POLICY) -> FakeSpecFiles:
    return FakeSpecFiles({"requirements.yaml": BAD_REQUIREMENTS, "policies.yaml": policy})


def loaded(files: FakeSpecFiles) -> SpecSet:
    spec = load_spec(files).spec
    assert spec is not None
    return spec


def hash_of(files: FakeSpecFiles) -> str:
    return content_hash(loaded(files))


def ref(id_: str, hash_: str | None = None) -> SpecVersionRef:
    return SpecVersionRef(id=id_, hash=hash_ or "a" * 64)


def run(
    files: FakeSpecFiles, versions: FakeVersions | None = None
) -> tuple[ApproveResult, FakeRecorder]:
    recorder = FakeRecorder()
    result = approve_spec(files, versions or FakeVersions(), recorder)
    return result, recorder


def types(recorder: FakeRecorder) -> list[str]:
    return [e.type.value for e in recorder.events]


def test_ac1_fresh_spec_records_imported_validated_approved() -> None:
    files = good_files()
    expected_hash = hash_of(files)
    result, recorder = run(files)

    assert types(recorder) == ["SpecImported", "SpecValidated", "SpecApproved"]
    assert all(e.stream == "spec:sv_01" for e in recorder.events)
    _, validated, approved = recorder.events

    assert approved.actor == "human"
    payload = SpecApprovedPayload.model_validate(approved.payload)
    assert payload.spec_version == "sv_01"
    assert payload.hash == expected_hash
    assert approved.causation_id == validated.event_id

    assert validated.actor == "orchestrator"
    validated_payload = SpecValidatedPayload.model_validate(validated.payload)
    assert validated_payload.hash == expected_hash
    assert validated_payload.violations == []

    assert result.outcome == "approved"
    assert result.spec_version == "sv_01"
    assert result.violations == []
    assert result.policy_problems == []


def test_ac1_use_case_does_not_import_adapters() -> None:
    tree = ast.parse((APP_DIR / "approve_spec.py").read_text())
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    assert not [m for m in modules if m.startswith("openfactory.adapters")]


def test_ac2_existing_draft_is_validated_and_approved_without_import() -> None:
    files = good_files()
    versions = FakeVersions(
        approved=ref("sv_01"), draft=ref("sv_02", hash_of(files)), next_id="sv_03"
    )
    result, recorder = run(files, versions)

    assert types(recorder) == ["SpecValidated", "SpecApproved"]
    validated, approved = recorder.events
    for event in recorder.events:
        assert event.stream == "spec:sv_02"
        assert event.payload["spec_version"] == "sv_02"
    assert validated.causation_id is None
    assert approved.causation_id == validated.event_id
    assert result.outcome == "approved"
    assert result.spec_version == "sv_02"


def test_ac3_violations_without_draft_record_imported_and_validated_then_refuse() -> None:
    files = bad_content_files()
    expected = validate_spec(loaded(files))
    assert expected
    result, recorder = run(files)

    assert types(recorder) == ["SpecImported", "SpecValidated"]
    payload = SpecValidatedPayload.model_validate(recorder.events[1].payload)
    assert len(payload.violations) == len(expected)
    assert result.outcome == "refused"
    assert result.spec_version == "sv_01"
    assert result.violations == expected


def test_ac3_violations_with_matching_draft_record_only_validated_then_refuse() -> None:
    files = bad_content_files()
    expected = validate_spec(loaded(files))
    result, recorder = run(files, FakeVersions(draft=ref("sv_01", hash_of(files))))

    assert types(recorder) == ["SpecValidated"]
    payload = SpecValidatedPayload.model_validate(recorder.events[0].payload)
    assert len(payload.violations) == len(expected)
    assert result.outcome == "refused"
    assert result.spec_version == "sv_01"
    assert result.violations == expected


def test_ac4_nothing_to_approve_records_no_events() -> None:
    files = good_files()
    approved = ref("sv_01", hash_of(files))
    for draft in (None, ref("sv_02", "b" * 64)):
        result, recorder = run(files, FakeVersions(approved=approved, draft=draft))
        assert recorder.events == []
        assert result.outcome == "nothing_to_approve"


def test_ac5_unloadable_records_nothing_and_reports_both_problem_lists() -> None:
    files = FakeSpecFiles(
        {"requirements.yaml": "requirements: [unclosed\n", "policies.yaml": "bogus_key: 1\n"}
    )
    result, recorder = run(files)

    assert recorder.events == []
    assert result.outcome == "unloadable"
    assert result.spec_version is None
    assert result.violations == load_spec(files).violations
    assert result.violations
    assert all(v.rule.value == "schema" for v in result.violations)
    assert [v.subject for v in result.policy_problems] == ["specs/policies.yaml"]
    assert result.policy_problems[0].rule.value == "schema"


def test_ac6_policy_problem_does_not_block_approval() -> None:
    files = good_files(policy="max_attempts: 0\n")
    result, recorder = run(files)

    assert types(recorder) == ["SpecImported", "SpecValidated", "SpecApproved"]
    validated_payload = SpecValidatedPayload.model_validate(recorder.events[1].payload)
    assert validated_payload.violations == []
    assert result.outcome == "approved"
    assert [v.subject for v in result.policy_problems] == ["specs/policies.yaml"]
    assert result.policy_problems[0].rule.value == "schema"
    assert result.violations == []
