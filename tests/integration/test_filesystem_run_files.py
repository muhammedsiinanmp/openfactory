"""TASK-046 AC2 to AC4: FilesystemRunFiles (docs/tasks/TASK-046-*.md)."""

from pathlib import Path

import pytest

from openfactory.adapters.filesystem_run_files import FilesystemRunFiles

TEXT = "src/openfactory/domain/modèle.py\ndocs/spec/phase1-spec.md\n"
EXPECTED = Path(".openfactory/runs/run_0007/path_check.txt")


@pytest.fixture
def repo(tmp_path):
    """A test repo: .openfactory/.gitignore holding '*', no .openfactory/runs/."""
    root = tmp_path / "repo"
    (root / ".openfactory").mkdir(parents=True)
    (root / ".openfactory" / ".gitignore").write_text("*\n", encoding="utf-8")
    return root


def test_ac2_write_returns_relative_path_and_stores_utf8_bytes(repo):
    returned = FilesystemRunFiles(repo).write("run_0007", "path_check.txt", TEXT)

    assert returned == EXPECTED
    assert (repo / returned).read_bytes() == TEXT.encode("utf-8")


def test_ac3_path_is_relative_and_independent_of_working_directory(repo, tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    returned = FilesystemRunFiles(repo).write("run_0007", "path_check.txt", TEXT)

    assert returned == EXPECTED
    assert not returned.is_absolute()
    assert (repo / returned).read_bytes() == TEXT.encode("utf-8")
    assert not (elsewhere / ".openfactory").exists()
    assert list(elsewhere.iterdir()) == []


def test_ac4_writes_leave_other_files_of_the_run_and_other_runs_alone(repo):
    run_dir = repo / ".openfactory" / "runs" / "run_0007"
    run_dir.mkdir(parents=True)
    (run_dir / "transcript.json").write_bytes(b'{"result": "ok"}\n')
    files = FilesystemRunFiles(repo)

    files.write("run_0007", "path_check.txt", "A")
    assert (run_dir / "transcript.json").read_bytes() == b'{"result": "ok"}\n'

    files.write("run_0007", "ruff.txt", "B")
    files.write("run_0008", "path_check.txt", "C")

    other_dir = repo / ".openfactory" / "runs" / "run_0008"
    assert (run_dir / "path_check.txt").read_text(encoding="utf-8") == "A"
    assert (run_dir / "ruff.txt").read_text(encoding="utf-8") == "B"
    assert (other_dir / "path_check.txt").read_text(encoding="utf-8") == "C"
    assert {p.name for p in run_dir.iterdir()} == {"transcript.json", "path_check.txt", "ruff.txt"}
    assert {p.name for p in other_dir.iterdir()} == {"path_check.txt"}
