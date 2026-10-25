"""TASK-114 AC1..AC6: the eval case procedure (docs/tasks/TASK-114-eval-case-procedure.md)."""

import hashlib
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

# tests/eval/harness.py; pytest's prepend import mode puts this directory on sys.path
import harness
import pytest

from openfactory.adapters.filesystem_spec_files import FilesystemSpecFiles
from openfactory.adapters.sqlite_plans import SqlitePlans
from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.adapters.sqlite_spec_versions import SqliteSpecVersions
from openfactory.app.approve_spec import ApproveOutcome, approve_spec
from openfactory.app.impact import ImpactRefusal
from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.events import Event, EventType
from openfactory.domain.llm import LLMReply
from openfactory.domain.payloads import (
    CommitRecordedPayload,
    ImpactComputedPayload,
    PlanApprovedPayload,
    PlanCreatedPayload,
    TaskStateChangedPayload,
)
from openfactory.ports.llm_provider import LLMError

HASH = "a" * 64
TASK = "AUTH-001"

POLICIES = """\
protected_branches: [main, master]
forbidden_paths: []
max_attempts: 2
max_runtime_s: 1200
max_cost_usd: 1.50
"""


def requirements(statement: str) -> str:
    return f"""\
components: [auth]
requirements:
  - id: REQ-AUTH-001
    title: Login
    statement: {statement}
    priority: must
    components: [auth]
    acceptance_criteria:
      - id: AC-AUTH-001-1
        text: Valid login returns a JWT.
"""


def adr(adr_id: str, body: str) -> str:
    return f"---\nid: {adr_id}\nstatus: accepted\ntitle: {adr_id}\ndate: 2026-01-01\n---\n{body}\n"


FIXTURE_REQS = requirements("Users can log in.")
FIXTURE_ADRS = {
    "ADR-001-jwt.md": adr("ADR-001", "We use JWT."),
    "ADR-002-db.md": adr("ADR-002", "x"),
}


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


def write_specs(root: Path, reqs: str, adrs: dict[str, str]) -> None:
    (root / "adrs").mkdir(parents=True, exist_ok=True)
    (root / "requirements.yaml").write_text(reqs, encoding="utf-8")
    for name, text in adrs.items():
        (root / "adrs" / name).write_text(text, encoding="utf-8")


def contract() -> TaskContract:
    return TaskContract(
        task_id=TASK,
        objective="Do it",
        requirements=["REQ-AUTH-001"],
        acceptance_criteria=["AC-AUTH-001-1"],
        depends_on=[],
        components=["auth"],
        role="implementer",
        allowed_paths=["app/**"],
        forbidden_paths=["specs/**"],
        required_gates=["path_check", "ruff", "pytest", "gitleaks", "review"],
        limits=Limits(max_runtime_s=1200, max_attempts=2, max_cost_usd=1.5),
    )


@pytest.fixture
def fixture(tmp_path: Path) -> Path:
    """A synthetic eval fixture: repo.bundle and openfactory.db (ADR-021)."""
    repo = tmp_path / "build"
    repo.mkdir()
    git(repo, "init", "--quiet", "-b", "main")
    (repo / "specs").mkdir()
    (repo / "specs" / "policies.yaml").write_text(POLICIES, encoding="utf-8")
    write_specs(repo / "specs", FIXTURE_REQS, FIXTURE_ADRS)
    (repo / "app").mkdir()
    (repo / "app" / "a.py").write_text("x = 1\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "initial build")
    sha = git(repo, "rev-parse", "HEAD")

    (repo / ".openfactory").mkdir()
    db = repo / ".openfactory" / "openfactory.db"
    with closing(SqliteEventRecorder(db)) as recorder:
        with closing(SqliteSpecVersions(db)) as versions, closing(SqlitePlans(db)) as plans:
            result = approve_spec(FilesystemSpecFiles(repo / "specs"), versions, plans, recorder)
        assert result.outcome is ApproveOutcome.approved
        assert result.spec_version == "sv_01"

        def rec(stream: str, type_: EventType, payload, actor: str = "orchestrator") -> None:  # noqa: ANN001
            recorder.record(
                Event.new(
                    stream=stream,
                    type=type_,
                    payload=payload.model_dump(mode="json"),
                    actor=actor,
                )
            )

        rec(
            "plan:plan_01",
            EventType.PlanCreated,
            PlanCreatedPayload(
                plan_id="plan_01",
                spec_version="sv_01",
                policy_hash=HASH,
                run_id="run_0001",
                tasks=[contract()],
            ),
        )
        rec("plan:plan_01", EventType.PlanApproved, PlanApprovedPayload(plan_id="plan_01"), "human")
        rec(
            f"task:{TASK}",
            EventType.TaskStateChanged,
            TaskStateChangedPayload(task_id=TASK, from_="ready", to="running", reason=None),
        )
        rec(
            f"task:{TASK}",
            EventType.CommitRecorded,
            CommitRecordedPayload(
                sha=sha,
                task_id=TASK,
                run_id="run_0002",
                branch=f"task/{TASK}",
                spec_version="sv_01",
                files=["app/a.py"],
            ),
        )
    with closing(sqlite3.connect(db)) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("PRAGMA journal_mode=DELETE")

    out = tmp_path / "fixture"
    out.mkdir()
    git(repo, "bundle", "create", str(out / "repo.bundle"), "--all")
    (out / "openfactory.db").write_bytes(db.read_bytes())
    (out / "sha").write_text(sha, encoding="utf-8")
    return out


def make_case(root: Path, name: str, reqs: str, adrs: dict[str, str]) -> Path:
    case = root / name
    write_specs(case / "specs", reqs, adrs)
    (case / "labels.yaml").write_text(
        "tasks: []\nfiles: []\ntests: []\nkinds: {}\n", encoding="utf-8"
    )
    return case


@pytest.fixture
def modify_case(tmp_path: Path) -> Path:
    return make_case(
        tmp_path / "cases",
        "modify",
        requirements("Users can log in with a password."),
        {"ADR-001-jwt.md": FIXTURE_ADRS["ADR-001-jwt.md"]},
    )


@pytest.fixture
def same_case(tmp_path: Path) -> Path:
    return make_case(tmp_path / "cases", "same", FIXTURE_REQS, FIXTURE_ADRS)


class StandIn:
    """A stand-in LLMProvider: a fixed classifier reply, or a failed process."""

    def __init__(self, kind: str | None = "behavioral", error: str | None = None) -> None:
        self.kind = kind
        self.error = error
        self.calls = 0

    def complete(self, prompt: str, schema: dict[str, object]) -> LLMReply:
        self.calls += 1
        if self.error is not None:
            raise LLMError(self.error, duration_s=0.1, timeout=False)
        change = {
            "req_id": "REQ-AUTH-001",
            "kind": self.kind,
            "rationale": "because",
            "obsolete_criteria": [],
            "new_work": ["password check"],
        }
        return LLMReply(
            structured={"changes": [change]},
            model="stand-in",
            tokens_in=1,
            tokens_out=1,
            cost_usd=0.0,
            duration_s=0.1,
        )


def events(db: Path) -> list[tuple[int, str, str]]:
    with closing(sqlite3.connect(db)) as conn:
        return conn.execute("SELECT seq, event_id, type FROM events ORDER BY seq").fetchall()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_restore_gives_a_clone_with_the_event_log(fixture: Path, tmp_path: Path) -> None:
    dest = tmp_path / "copy"
    harness.restore_fixture(fixture, dest)
    sha = (fixture / "sha").read_text(encoding="utf-8")
    assert git(dest, "cat-file", "-t", sha) == "commit"
    assert (dest / ".git").exists()
    assert events(dest / ".openfactory" / "openfactory.db") == events(fixture / "openfactory.db")


def test_two_cases_leave_the_fixture_untouched_and_apart(
    fixture: Path, modify_case: Path, same_case: Path, tmp_path: Path
) -> None:
    before = (digest(fixture / "repo.bundle"), digest(fixture / "openfactory.db"))
    original = events(fixture / "openfactory.db")
    harness.run_case(fixture, modify_case, tmp_path / "one", llm=StandIn())
    harness.run_case(fixture, same_case, tmp_path / "two", llm=StandIn())
    assert (digest(fixture / "repo.bundle"), digest(fixture / "openfactory.db")) == before
    one = events(tmp_path / "one" / ".openfactory" / "openfactory.db")
    two = events(tmp_path / "two" / ".openfactory" / "openfactory.db")
    assert any(t == "ImpactComputed" for _, _, t in one)
    assert not any(t == "ImpactComputed" for _, _, t in two)
    assert not any(t == "SpecApproved" for _, _, t in two[len(original) :])
    assert {e for _, e, _ in one[len(original) :]}.isdisjoint({e for _, e, _ in two})


def test_replace_specs_swaps_requirements_and_adrs(
    fixture: Path, modify_case: Path, tmp_path: Path
) -> None:
    dest = tmp_path / "copy"
    harness.restore_fixture(fixture, dest)
    bundle_policies = (dest / "specs" / "policies.yaml").read_text(encoding="utf-8")
    assert (dest / "specs" / "adrs" / "ADR-002-db.md").exists()
    harness.replace_specs(modify_case, dest)
    assert (dest / "specs" / "requirements.yaml").read_text(encoding="utf-8") == (
        modify_case / "specs" / "requirements.yaml"
    ).read_text(encoding="utf-8")
    assert sorted(p.name for p in (dest / "specs" / "adrs").iterdir()) == ["ADR-001-jwt.md"]
    assert (dest / "specs" / "policies.yaml").read_text(encoding="utf-8") == bundle_policies


def test_run_case_approves_and_computes_impact(
    fixture: Path, modify_case: Path, tmp_path: Path
) -> None:
    dest = tmp_path / "copy"
    run = harness.run_case(fixture, modify_case, dest, llm=StandIn("behavioral"))
    assert run.approve.outcome is ApproveOutcome.approved
    assert run.approve.spec_version == "sv_02"
    assert run.impact.impact is not None
    assert run.impact.impact.from_version == "sv_01"
    assert run.impact.impact.to_version == "sv_02"
    assert run.impact.impact.tasks == [TASK]
    assert run.impact.impact.files == ["app/a.py"]
    with closing(sqlite3.connect(dest / ".openfactory" / "openfactory.db")) as conn:
        rows = conn.execute("SELECT payload FROM events WHERE type = 'ImpactComputed'").fetchall()
    assert len(rows) == 1
    assert ImpactComputedPayload.model_validate_json(rows[0][0]) == run.impact.impact


def test_run_case_returns_the_classifier_error(
    fixture: Path, modify_case: Path, tmp_path: Path
) -> None:
    dest = tmp_path / "copy"
    run = harness.run_case(fixture, modify_case, dest, llm=StandIn(error="claude exited 1"))
    assert run.approve.outcome is ApproveOutcome.approved
    assert run.impact.impact is None
    with closing(sqlite3.connect(dest / ".openfactory" / "openfactory.db")) as conn:
        finished = conn.execute(
            "SELECT payload FROM events WHERE type = 'AgentRunFinished' ORDER BY seq DESC"
        ).fetchone()
        impacts = conn.execute("SELECT 1 FROM events WHERE type = 'ImpactComputed'").fetchall()
    assert impacts == []
    assert run.impact.error is not None
    assert "claude exited 1" in run.impact.error
    assert run.impact.error in finished[0]


def test_unchanged_case_gives_both_results_without_raising(
    fixture: Path, same_case: Path, tmp_path: Path
) -> None:
    llm = StandIn()
    run = harness.run_case(fixture, same_case, tmp_path / "copy", llm=llm)
    assert run.approve.outcome is ApproveOutcome.nothing_to_approve
    assert run.impact.refusal is ImpactRefusal.no_spec_change
    assert run.impact.impact is None
    assert llm.calls == 0


def test_case_run_is_frozen(fixture: Path, same_case: Path, tmp_path: Path) -> None:
    run = harness.run_case(fixture, same_case, tmp_path / "copy", llm=StandIn())
    with pytest.raises(Exception):  # noqa: B017, PT011
        run.approve = run.approve  # type: ignore[misc]


def test_harness_tests_run_in_the_default_suite() -> None:
    marks = [m.name for m in getattr(test_run_case_approves_and_computes_impact, "pytestmark", [])]
    assert "eval" not in marks
