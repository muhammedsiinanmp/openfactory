"""TASK-012: validate use case.

Each test names the acceptance criterion it covers (AC1..AC6 in
docs/tasks/TASK-012-validate-use-case.md). The use case is driven through in-memory
fakes of SpecFiles, SpecVersions and EventRecorder; no filesystem or database is used.
"""

import ast
import json
from pathlib import Path
from uuid import UUID

from openfactory.app.spec_loader import load_spec
from openfactory.app.validate import ValidateResult, validate
from openfactory.domain.events import Event, StoredEvent
from openfactory.domain.models import SpecSet
from openfactory.domain.payloads import SpecImportedPayload, SpecValidatedPayload
from openfactory.domain.spec_hash import canonical_json, content_hash
from openfactory.domain.spec_validation import validate_spec
from openfactory.domain.spec_versions import SpecVersionRef

APP_DIR = Path(__file__).resolve().parents[2] / "src" / "openfactory" / "app"

POLICY = "max_attempts: 3\n"

# Two requirements out of id order, unsorted components, one accepted ADR with a body.
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
) -> tuple[ValidateResult, FakeRecorder]:
    recorder = FakeRecorder()
    result = validate(files, versions or FakeVersions(), recorder)
    return result, recorder


def types(recorder: FakeRecorder) -> list[str]:
    return [e.type.value for e in recorder.events]


def test_ac1_unloadable_records_nothing_and_reports_both_problem_lists() -> None:
    files = FakeSpecFiles(
        {"requirements.yaml": "requirements: [unclosed\n", "policies.yaml": "bogus_key: 1\n"}
    )
    result, recorder = run(files, FakeVersions(approved=ref("sv_01")))
    assert recorder.events == []
    assert result.outcome == "unloadable"
    assert result.spec_version is None
    assert result.hash is None
    assert result.validated_event_id is None
    assert result.violations == load_spec(files).violations
    assert result.violations
    assert all(v.rule.value == "schema" for v in result.violations)
    assert [v.subject for v in result.policy_problems] == ["specs/policies.yaml"]
    assert result.policy_problems[0].rule.value == "schema"


def test_ac2_first_import_records_imported_then_validated() -> None:
    files = good_files()
    result, recorder = run(files)
    expected_hash = hash_of(files)

    assert types(recorder) == ["SpecImported", "SpecValidated"]
    imported, validated = recorder.events
    for event in recorder.events:
        assert event.stream == "spec:sv_01"
        assert event.actor == "orchestrator"

    imported_payload = SpecImportedPayload.model_validate(imported.payload)
    assert imported_payload.spec_version == "sv_01"
    assert imported_payload.hash == expected_hash
    assert imported.payload["spec"] == json.loads(canonical_json(loaded(files)))

    validated_payload = SpecValidatedPayload.model_validate(validated.payload)
    assert validated_payload.spec_version == "sv_01"
    assert validated_payload.hash == expected_hash
    assert validated_payload.violations == []
    assert validated_payload.warnings == []

    assert imported.causation_id is None
    assert validated.causation_id == imported.event_id

    assert result.outcome == "validated"
    assert result.spec_version == "sv_01"
    assert result.violations == []
    assert result.policy_problems == []
    assert result.hash == expected_hash
    assert result.validated_event_id == validated.event_id


def test_ac2_import_uses_next_id_after_an_approved_version() -> None:
    files = good_files()
    _, recorder = run(files, FakeVersions(approved=ref("sv_01"), next_id="sv_02"))
    assert types(recorder) == ["SpecImported", "SpecValidated"]
    for event in recorder.events:
        assert event.stream == "spec:sv_02"
        assert event.payload["spec_version"] == "sv_02"


def test_ac2_use_case_does_not_import_adapters() -> None:
    tree = ast.parse((APP_DIR / "validate.py").read_text())
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    assert not [m for m in modules if m.startswith("openfactory.adapters")]


def test_ac3_existing_draft_keeps_its_id_and_content_is_replaced() -> None:
    files = good_files()
    versions = FakeVersions(approved=ref("sv_01"), draft=ref("sv_02", "b" * 64), next_id="sv_03")
    result, recorder = run(files, versions)
    expected_hash = hash_of(files)

    assert types(recorder) == ["SpecImported", "SpecValidated"]
    for event in recorder.events:
        assert event.stream == "spec:sv_02"
        assert event.payload["spec_version"] == "sv_02"
        assert event.payload["hash"] == expected_hash
    assert result.outcome == "validated"
    assert result.spec_version == "sv_02"
    assert result.hash == expected_hash
    assert result.validated_event_id == recorder.events[1].event_id


def test_ac4_hash_equal_to_draft_records_only_validated() -> None:
    files = good_files()
    expected_hash = hash_of(files)
    result, recorder = run(files, FakeVersions(draft=ref("sv_01", expected_hash)))

    assert types(recorder) == ["SpecValidated"]
    (event,) = recorder.events
    assert event.stream == "spec:sv_01"
    assert event.payload["spec_version"] == "sv_01"
    assert event.payload["hash"] == expected_hash
    assert event.causation_id is None
    assert result.outcome == "validated"
    assert result.spec_version == "sv_01"
    assert result.hash == expected_hash
    assert result.validated_event_id == event.event_id


def test_ac5_hash_equal_to_approved_records_nothing() -> None:
    files = good_files()
    approved = ref("sv_01", hash_of(files))
    for draft in (None, ref("sv_02", "b" * 64)):
        result, recorder = run(files, FakeVersions(approved=approved, draft=draft))
        assert recorder.events == []
        assert result.outcome == "matches_approved"
        assert result.spec_version == "sv_01"
        assert result.hash is None
        assert result.validated_event_id is None
        assert result.policy_problems == []


def test_ac5_rules_are_not_run_when_matching_approved() -> None:
    files = bad_content_files()
    assert validate_spec(loaded(files))  # the files do break rules
    result, recorder = run(files, FakeVersions(approved=ref("sv_01", hash_of(files))))
    assert recorder.events == []
    assert result.outcome == "matches_approved"
    assert result.violations == []


def test_ac5_policy_problem_is_reported_when_matching_approved() -> None:
    files = good_files(policy="max_attempts: 0\n")
    result, recorder = run(files, FakeVersions(approved=ref("sv_01", hash_of(files))))
    assert recorder.events == []
    assert result.outcome == "matches_approved"
    assert result.spec_version == "sv_01"
    assert [v.subject for v in result.policy_problems] == ["specs/policies.yaml"]


def test_ac6_violations_are_recorded_and_do_not_stop_the_import() -> None:
    files = bad_content_files(policy="max_attempts: 0\n")
    expected = validate_spec(loaded(files))
    assert [v.rule.value for v in expected] == ["missing-acceptance-criteria", "constrained-by"]

    result, recorder = run(files)

    assert types(recorder) == ["SpecImported", "SpecValidated"]
    payload = SpecValidatedPayload.model_validate(recorder.events[1].payload)
    # Stored in the order validate_spec returned them (decisions row SC-10), rule as plain string.
    assert [(v.rule, v.subject, v.message) for v in payload.violations] == [
        (v.rule.value, v.subject, v.message) for v in expected
    ]
    assert payload.warnings == []
    assert all(v.subject != "specs/policies.yaml" for v in payload.violations)

    assert result.outcome == "validated"
    assert result.violations == expected
    assert [v.subject for v in result.policy_problems] == ["specs/policies.yaml"]
    assert result.policy_problems[0].rule.value == "schema"
    assert result.validated_event_id == recorder.events[1].event_id
    assert isinstance(result.validated_event_id, UUID)
