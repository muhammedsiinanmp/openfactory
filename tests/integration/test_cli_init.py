"""TASK-014 AC1..AC5: CLI entry point, init and require_init (see the task record)."""

import sqlite3
import tomllib
from pathlib import Path

import pytest
import typer
import yaml
from typer.testing import CliRunner

from openfactory.adapters.filesystem_spec_files import FilesystemSpecFiles
from openfactory.app.spec_loader import load_policy
from openfactory.domain.policy import Policy

runner = CliRunner()

DB = ".openfactory/openfactory.db"
GITIGNORE = ".openfactory/.gitignore"
POLICIES = "specs/policies.yaml"
ITEMS = (DB, GITIGNORE, POLICIES)


def make_repo(tmp_path: Path, name: str = "repo") -> Path:
    repo = tmp_path / name
    (repo / ".git").mkdir(parents=True)
    return repo


def run_init(repo: Path):
    from openfactory.cli import app

    return runner.invoke(app, ["init", str(repo)])


def lines(result) -> list[str]:
    return result.stdout.splitlines()


def test_ac1_init_creates_database_and_self_ignoring_directory(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    result = run_init(repo)
    assert result.exit_code == 0
    with sqlite3.connect(repo / DB) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        last_seq = [r[0] for r in conn.execute("SELECT last_seq FROM projection_state")]
    conn.close()
    assert {"events", "spec_versions", "requirements", "adrs", "projection_state"} <= tables
    assert last_seq and set(last_seq) == {0}
    assert (repo / GITIGNORE).read_text().strip() == "*"
    assert not (repo / ".gitignore").exists()


def test_ac1_init_leaves_repo_gitignore_untouched(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / ".gitignore").write_bytes(b"build/\n__pycache__/\n")
    assert run_init(repo).exit_code == 0
    assert (repo / ".gitignore").read_bytes() == b"build/\n__pycache__/\n"


def test_ac1_script_points_at_the_typer_app() -> None:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text())
    assert data["project"]["scripts"]["openfactory"] == "openfactory.cli:app"
    from openfactory.cli import app

    assert isinstance(app, typer.Typer)


def test_ac2_default_policies_file_is_the_specs_defaults(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    assert run_init(repo).exit_code == 0
    parsed = yaml.safe_load((repo / POLICIES).read_text())
    assert parsed == {
        "protected_branches": ["main", "master"],
        "forbidden_paths": [],
        "max_attempts": 2,
        "max_runtime_s": 1200,
        "max_cost_usd": 1.50,
    }
    loaded = load_policy(FilesystemSpecFiles(repo / "specs"))
    assert loaded.violations == []
    assert loaded.policy == Policy()


def test_ac2_existing_specs_files_are_not_touched(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "specs").mkdir()
    reqs = b"requirements: []\n# keep me\n"
    (repo / "specs" / "requirements.yaml").write_bytes(reqs)
    assert run_init(repo).exit_code == 0
    assert (repo / "specs" / "requirements.yaml").read_bytes() == reqs
    assert (repo / POLICIES).exists()


def test_ac2_existing_policies_file_is_never_overwritten(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "specs").mkdir()
    custom = b"max_attempts: 5\n"
    (repo / POLICIES).write_bytes(custom)
    result = run_init(repo)
    assert result.exit_code == 0
    assert (repo / POLICIES).read_bytes() == custom


def test_ac3_init_is_repeatable_and_reports_created_or_exists(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)

    first = run_init(repo)
    assert first.exit_code == 0
    assert lines(first) == [f"created {p}" for p in ITEMS]
    gitignore = (repo / GITIGNORE).read_bytes()
    policies = (repo / POLICIES).read_bytes()

    second = run_init(repo)
    assert second.exit_code == 0
    assert lines(second) == [f"exists {p}" for p in ITEMS]
    assert (repo / GITIGNORE).read_bytes() == gitignore
    assert (repo / POLICIES).read_bytes() == policies

    (repo / GITIGNORE).unlink()
    third = run_init(repo)
    assert third.exit_code == 0
    assert lines(third) == [f"exists {DB}", f"created {GITIGNORE}", f"exists {POLICIES}"]
    assert (repo / POLICIES).read_bytes() == policies


def test_ac3_init_records_no_events(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    for _ in range(2):
        assert run_init(repo).exit_code == 0
        conn = sqlite3.connect(repo / DB)
        try:
            assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
        finally:
            conn.close()


def test_ac4_missing_path_and_non_repo_fail_with_exit_1(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    sub_of_repo = make_repo(tmp_path, "outer") / "inner"
    sub_of_repo.mkdir()
    for target in (tmp_path / "does-not-exist", plain, sub_of_repo):
        result = run_init(target)
        assert result.exit_code == 1, target
        assert result.stdout == ""
        assert result.stderr != ""
        if target.exists():
            assert not (target / ".openfactory").exists()
            assert not (target / "specs").exists()


def test_ac4_missing_argument_is_a_usage_error() -> None:
    from openfactory.cli import app

    assert runner.invoke(app, ["init"]).exit_code == 2


def _check_app() -> typer.Typer:
    from openfactory.cli import require_init

    check = typer.Typer()

    @check.callback()
    def _root() -> None:
        pass

    @check.command("check")
    def _check() -> None:
        typer.echo(f"ok {require_init()}")

    return check


def test_ac5_require_init_fails_without_openfactory_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.chdir(plain)
    result = runner.invoke(_check_app(), ["check"])
    assert result.exit_code == 1
    assert "run `openfactory init` first" in result.stderr
    assert result.stdout == ""


def test_ac5_require_init_does_not_search_parent_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path)
    assert run_init(repo).exit_code == 0
    sub = repo / "src"
    sub.mkdir()
    monkeypatch.chdir(sub)
    result = runner.invoke(_check_app(), ["check"])
    assert result.exit_code == 1
    assert "run `openfactory init` first" in result.stderr
    assert result.stdout == ""


def test_ac5_require_init_returns_database_path_in_initialised_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from openfactory.cli import require_init

    repo = make_repo(tmp_path)
    assert run_init(repo).exit_code == 0
    monkeypatch.chdir(repo)
    assert require_init() == Path(".openfactory/openfactory.db")
    result = runner.invoke(_check_app(), ["check"])
    assert result.exit_code == 0
    assert result.stderr == ""
