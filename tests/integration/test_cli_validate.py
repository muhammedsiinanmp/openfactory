"""TASK-016 AC1..AC6: the `validate` command (see docs/tasks/TASK-016-cli-validate.md)."""

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from openfactory.adapters.filesystem_spec_files import FilesystemSpecFiles
from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.adapters.sqlite_spec_versions import SqliteSpecVersions
from openfactory.app.approve_spec import approve_spec
from openfactory.app.spec_loader import load_policy, load_spec
from openfactory.domain.spec_validation import SpecViolation, validate_spec

runner = CliRunner()

DB = Path(".openfactory/openfactory.db")
REQS = Path("specs/requirements.yaml")
POLICIES = Path("specs/policies.yaml")
NO_POLICY_PROBLEMS = "0 violations, 0 policy problems"

VALID_REQUIREMENTS = """\
components: [auth]
requirements:
  - id: REQ-AUTH-001
    title: Login
    statement: Users can log in.
    priority: must
    components: [auth]
    acceptance_criteria:
      - id: AC-AUTH-001-1
        text: Valid login returns a JWT.
"""

# One violation: missing-acceptance-criteria.
ONE_VIOLATION_REQUIREMENTS = """\
requirements:
  - id: REQ-AUTH-001
    title: Login
    statement: Users can log in.
    priority: must
"""

# Returned order: missing-acceptance-criteria 002, missing-acceptance-criteria 001,
# constrained-by 002. Printed order: constrained-by, then missing ... 001, then 002.
UNSORTED_REQUIREMENTS = """\
requirements:
  - id: REQ-AUTH-002
    title: Logout
    statement: Users can log out.
    priority: should
    constrained_by: [ADR-099]
  - id: REQ-AUTH-001
    title: Login
    statement: Users can log in.
    priority: must
"""


def make_repo(tmp_path: Path, requirements: str | None = VALID_REQUIREMENTS) -> Path:
    from openfactory.cli import app

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    assert runner.invoke(app, ["init", str(repo)]).exit_code == 0
    if requirements is not None:
        (repo / REQS).write_text(requirements, encoding="utf-8")
    return repo


def run_validate(repo: Path, monkeypatch: pytest.MonkeyPatch):
    from openfactory.cli import app

    monkeypatch.chdir(repo)
    result = runner.invoke(app, ["validate"])
    # Added after review: result lines never go to standard error.
    if (repo / ".openfactory").is_dir():
        assert result.stderr == ""
    return result


def query(repo: Path, sql: str) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(repo / DB)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def events(repo: Path) -> list[tuple[str, dict[str, Any]]]:
    rows = query(repo, "SELECT type, payload FROM events ORDER BY seq")
    return [(t, json.loads(p)) for t, p in rows]


def line(v: SpecViolation) -> str:
    return f"{v.rule.value}  {v.subject}  {v.message}"


def sorted_lines(violations: list[SpecViolation]) -> list[str]:
    key = sorted(violations, key=lambda v: (v.rule.value, v.subject, v.message))
    return [line(v) for v in key]


def loaded_violations(repo: Path) -> list[SpecViolation]:
    spec = load_spec(FilesystemSpecFiles(repo / "specs")).spec
    assert spec is not None
    return validate_spec(spec)


def test_ac1_prints_sorted_violations_but_records_rule_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path, UNSORTED_REQUIREMENTS)
    returned = loaded_violations(repo)
    assert len({v.rule for v in returned}) >= 2
    assert returned != sorted(returned, key=lambda v: (v.rule.value, v.subject, v.message))

    result = run_validate(repo, monkeypatch)

    assert result.exit_code == 1
    assert result.stdout.splitlines() == [
        *sorted_lines(returned),
        f"{len(returned)} violations, 0 policy problems",
    ]
    stored = events(repo)
    assert [t for t, _ in stored] == ["SpecImported", "SpecValidated"]
    assert stored[1][1]["violations"] == [
        {"rule": v.rule.value, "subject": v.subject, "message": v.message} for v in returned
    ]


def test_ac2_valid_spec_prints_count_and_creates_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path)
    result = run_validate(repo, monkeypatch)
    assert result.exit_code == 0
    assert result.stdout.splitlines() == [NO_POLICY_PROBLEMS]
    assert result.stderr == ""
    assert query(repo, "SELECT id, status FROM spec_versions") == [("sv_01", "draft")]


def test_ac2_count_line_is_not_inflected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path, ONE_VIOLATION_REQUIREMENTS)
    result = run_validate(repo, monkeypatch)
    assert result.exit_code == 1
    assert result.stdout.splitlines()[-1] == "1 violations, 0 policy problems"


def test_ac3_unparsable_requirements_prints_schema_and_records_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path, "requirements: [unclosed\n")
    result = run_validate(repo, monkeypatch)
    out = result.stdout.splitlines()
    assert result.exit_code == 1
    assert len(out) == 2
    assert out[0].startswith("schema  specs/requirements.yaml  ")
    assert out[1] == "1 violations, 0 policy problems"
    assert events(repo) == []


def test_ac3_missing_requirements_is_a_schema_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path, None)
    result = run_validate(repo, monkeypatch)
    out = result.stdout.splitlines()
    assert result.exit_code == 1
    assert out[0].startswith("schema  specs/requirements.yaml  ")
    assert events(repo) == []


def test_ac3_policy_problem_is_printed_after_the_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path, "requirements: [unclosed\n")
    (repo / POLICIES).write_text("surprise: 1\n", encoding="utf-8")
    result = run_validate(repo, monkeypatch)
    out = result.stdout.splitlines()
    assert result.exit_code == 1
    assert len(out) == 3
    assert out[0].startswith("schema  specs/requirements.yaml  ")
    assert out[1].startswith("schema  specs/policies.yaml  ")
    assert out[2] == "1 violations, 1 policy problems"
    assert events(repo) == []


def approve(repo: Path) -> None:
    db = repo / DB
    recorder = SqliteEventRecorder(db)
    versions = SqliteSpecVersions(db)
    try:
        approve_spec(FilesystemSpecFiles(repo / "specs"), versions, recorder)
    finally:
        versions.close()
        recorder.close()


def test_ac4_matching_approved_version_records_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path)
    approve(repo)
    assert query(repo, "SELECT id, status FROM spec_versions") == [("sv_01", "approved")]
    before = len(events(repo))

    result = run_validate(repo, monkeypatch)

    assert result.exit_code == 0
    assert result.stdout.splitlines() == [NO_POLICY_PROBLEMS, "matches approved sv_01"]
    assert len(events(repo)) == before


def test_ac4_policy_problem_fails_a_matching_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path)
    approve(repo)
    (repo / POLICIES).write_text("max_attempts: 0\n", encoding="utf-8")
    problems = load_policy(FilesystemSpecFiles(repo / "specs")).violations
    assert len(problems) == 1

    result = run_validate(repo, monkeypatch)

    assert result.exit_code == 1
    assert result.stdout.splitlines() == [
        line(problems[0]),
        "0 violations, 1 policy problems",
        "matches approved sv_01",
    ]


def test_ac5_missing_policies_file_is_a_policy_problem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path)
    (repo / POLICIES).unlink()
    result = run_validate(repo, monkeypatch)
    assert result.exit_code == 1
    assert result.stdout.splitlines() == [
        "schema  specs/policies.yaml  missing; run openfactory init",
        "0 violations, 1 policy problems",
    ]
    stored = events(repo)
    assert [t for t, _ in stored] == ["SpecImported", "SpecValidated"]
    assert stored[1][1]["violations"] == []


def test_ac5_policy_problems_follow_violations_and_are_not_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path, ONE_VIOLATION_REQUIREMENTS)
    (repo / POLICIES).write_text("surprise: 1\nmax_attempts: 0\n", encoding="utf-8")
    violations = loaded_violations(repo)
    problems = load_policy(FilesystemSpecFiles(repo / "specs")).violations
    assert len(violations) == 1
    assert len(problems) == 2

    result = run_validate(repo, monkeypatch)

    assert result.exit_code == 1
    assert result.stdout.splitlines() == [
        *sorted_lines(violations),
        *sorted_lines(problems),
        "1 violations, 2 policy problems",
    ]
    recorded = events(repo)[-1][1]["violations"]
    assert [(v["rule"], v["subject"]) for v in recorded] == [
        (v.rule.value, v.subject) for v in violations
    ]


def test_ac5_policy_lines_are_sorted_by_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Added after review: the problems share a rule and a subject, and the loader
    # returns them in an order that is not the printed one.
    repo = make_repo(tmp_path)
    (repo / POLICIES).write_text("protected_branches: 3\nmax_attempts: 0\n", encoding="utf-8")
    problems = load_policy(FilesystemSpecFiles(repo / "specs")).violations
    assert len(problems) == 2
    assert len({(v.rule, v.subject) for v in problems}) == 1
    assert [line(v) for v in problems] != sorted_lines(problems)

    result = run_validate(repo, monkeypatch)

    assert result.exit_code == 1
    assert result.stdout.splitlines() == [
        *sorted_lines(problems),
        "0 violations, 2 policy problems",
    ]


def test_ac6_fails_without_init_and_creates_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "plain"
    (repo / "specs").mkdir(parents=True)
    (repo / REQS).write_text(VALID_REQUIREMENTS, encoding="utf-8")
    result = run_validate(repo, monkeypatch)
    assert result.exit_code == 1
    assert "run `openfactory init` first" in result.stderr
    assert result.stdout == ""
    assert not (repo / ".openfactory").exists()


def test_ac6_recreates_a_deleted_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path)
    for suffix in ("", "-wal", "-shm"):
        (repo / f"{DB}{suffix}").unlink(missing_ok=True)
    result = run_validate(repo, monkeypatch)
    assert result.exit_code == 0
    assert result.stdout.splitlines() == [NO_POLICY_PROBLEMS]
    assert (repo / DB).is_file()
    assert [t for t, _ in events(repo)] == ["SpecImported", "SpecValidated"]
