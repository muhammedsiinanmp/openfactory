"""TASK-060 AC6: process_gates on the real gitleaks and git (skipped without gitleaks)."""

import shutil
import subprocess
from pathlib import Path

import pytest

from openfactory.adapters.process_gates import ProcessGates

pytestmark = pytest.mark.skipif(shutil.which("gitleaks") is None, reason="gitleaks is not on PATH")

# Built at runtime: no source file may hold a detectable secret (CI runs gitleaks-action).
TOKEN = "gh" + "p_" + "aB3dE5gH7jK9mN1pQ3sT5vW7yZ9bC1dE3fG5"


def git_repo(path: Path, files: dict[str, str]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    for name, content in files.items():
        (path / name).write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True)


def test_staged_secret_is_a_finding_and_is_not_printed(tmp_path):
    git_repo(tmp_path / "wt", {"settings.txt": f'token = "{TOKEN}"\n'})
    out = ProcessGates(tmp_path).run("gitleaks", Path("wt"), 60)
    assert out.finding is True
    assert out.passed is False
    assert TOKEN not in out.text


def test_clean_staged_file_passes(tmp_path):
    git_repo(tmp_path / "wt", {"notes.txt": "nothing secret here\n"})
    out = ProcessGates(tmp_path).run("gitleaks", Path("wt"), 60)
    assert out.passed is True
    assert out.finding is False


def test_a_gitleaks_scan_error_is_a_failure_without_a_finding(tmp_path):
    # An invalid config makes gitleaks itself fail (exit 1 on 8.30.1). A plain non-git
    # directory does not: gitleaks logs an error there but still exits 0.
    git_repo(tmp_path / "wt", {"a.txt": "hi\n", ".gitleaks.toml": "this is [not valid toml\n"})
    out = ProcessGates(tmp_path).run("gitleaks", Path("wt"), 60)
    assert out.passed is False
    assert out.finding is False
