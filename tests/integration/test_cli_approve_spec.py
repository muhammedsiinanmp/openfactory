"""TASK-017 AC1..AC6: the `approve spec` command (see docs/tasks/TASK-017-cli-approve-spec.md)."""

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from openfactory.adapters.filesystem_spec_files import FilesystemSpecFiles
from openfactory.app.spec_loader import load_policy, load_spec
from openfactory.domain.spec_validation import SpecViolation, validate_spec

runner = CliRunner()

DB = Path(".openfactory/openfactory.db")
REQS = Path("specs/requirements.yaml")
POLICIES = Path("specs/policies.yaml")
NO_PROBLEMS = "0 violations, 0 policy problems"

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

# At least two content rules are broken.
BROKEN_REQUIREMENTS = """\
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


def run_approve(repo: Path, monkeypatch: pytest.MonkeyPatch):
    from openfactory.cli import app

    monkeypatch.chdir(repo)
    return runner.invoke(app, ["approve", "spec"])


def query(repo: Path, sql: str) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(repo / DB)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def events(repo: Path) -> list[tuple[str, str, str, dict[str, Any]]]:
    rows = query(repo, "SELECT type, stream, actor, payload FROM events ORDER BY seq")
    return [(t, s, a, json.loads(p)) for t, s, a, p in rows]


def event_types(repo: Path) -> list[str]:
    return [t for t, _, _, _ in events(repo)]


def sorted_lines(violations: list[SpecViolation]) -> list[str]:
    key = sorted(violations, key=lambda v: (v.rule.value, v.subject, v.message))
    return [f"{v.rule.value}  {v.subject}  {v.message}" for v in key]


def test_ac1_approves_valid_spec_without_earlier_validate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path)

    result = run_approve(repo, monkeypatch)

    assert result.exit_code == 0
    assert result.stdout.splitlines() == [NO_PROBLEMS, "approved sv_01"]
    assert result.stderr == ""
    stored = events(repo)
    assert [t for t, _, _, _ in stored] == ["SpecImported", "SpecValidated", "SpecApproved"]
    assert {s for _, s, _, _ in stored} == {"spec:sv_01"}
    assert stored[2][2] == "human"
    assert query(repo, "SELECT id, status FROM spec_versions") == [("sv_01", "approved")]


def test_ac1_edit_after_approval_creates_next_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path)
    assert run_approve(repo, monkeypatch).exit_code == 0
    (repo / REQS).write_text(
        VALID_REQUIREMENTS.replace("Users can log in.", "Users can sign in."), encoding="utf-8"
    )

    result = run_approve(repo, monkeypatch)

    assert result.exit_code == 0
    assert result.stdout.splitlines() == [NO_PROBLEMS, "approved sv_02"]


def test_ac2_refuses_violations_and_prints_sorted_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path, BROKEN_REQUIREMENTS)
    spec = load_spec(FilesystemSpecFiles(repo / "specs")).spec
    assert spec is not None
    violations = validate_spec(spec)
    assert len({v.rule for v in violations}) >= 2

    result = run_approve(repo, monkeypatch)

    assert result.exit_code == 1
    assert result.stdout.splitlines() == [
        *sorted_lines(violations),
        f"{len(violations)} violations, 0 policy problems",
    ]
    assert not any(ln.startswith("approved") for ln in result.stdout.splitlines())
    assert event_types(repo) == ["SpecImported", "SpecValidated"]
    assert query(repo, "SELECT id, status FROM spec_versions") == [("sv_01", "draft")]


def test_ac3_unloadable_files_print_violations_and_record_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path, "requirements: [unclosed\n")
    (repo / POLICIES).write_text("surprise: 1\n", encoding="utf-8")

    result = run_approve(repo, monkeypatch)

    out = result.stdout.splitlines()
    assert result.exit_code == 1
    assert len(out) == 3
    assert out[0].startswith("schema  specs/requirements.yaml  ")
    assert out[1].startswith("schema  specs/policies.yaml  ")
    assert out[2] == "1 violations, 1 policy problems"
    assert events(repo) == []


def test_ac4_second_run_has_nothing_to_approve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path)
    assert run_approve(repo, monkeypatch).exit_code == 0
    before = len(events(repo))

    result = run_approve(repo, monkeypatch)

    assert result.exit_code == 1
    assert result.stdout.splitlines() == [NO_PROBLEMS]
    assert "nothing to approve" in result.stderr
    assert len(events(repo)) == before


def test_ac4_nothing_to_approve_still_prints_policy_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path)
    assert run_approve(repo, monkeypatch).exit_code == 0
    (repo / POLICIES).write_text("max_attempts: 0\n", encoding="utf-8")
    problems = load_policy(FilesystemSpecFiles(repo / "specs")).violations
    assert len(problems) == 1

    result = run_approve(repo, monkeypatch)

    assert result.exit_code == 1
    assert result.stdout.splitlines() == [
        *sorted_lines(problems),
        "0 violations, 1 policy problems",
    ]
    assert "nothing to approve" in result.stderr


def test_ac5_policy_problem_does_not_block_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path)
    (repo / POLICIES).write_text("max_attempts: 0\n", encoding="utf-8")
    problems = load_policy(FilesystemSpecFiles(repo / "specs")).violations
    assert len(problems) == 1

    result = run_approve(repo, monkeypatch)

    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        *sorted_lines(problems),
        "0 violations, 1 policy problems",
        "approved sv_01",
    ]
    stored = events(repo)
    assert "SpecApproved" in [t for t, _, _, _ in stored]
    validated = [p for t, _, _, p in stored if t == "SpecValidated"]
    assert validated[0]["violations"] == []


def test_ac6_fails_without_init_and_creates_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "plain"
    (repo / "specs").mkdir(parents=True)
    (repo / REQS).write_text(VALID_REQUIREMENTS, encoding="utf-8")

    result = run_approve(repo, monkeypatch)

    assert result.exit_code == 1
    assert "run `openfactory init` first" in result.stderr
    assert result.stdout == ""
    assert not (repo / ".openfactory").exists()
