"""TASK-060 AC1-AC5: the process_gates adapter, run against stand-in uv and gitleaks."""

import stat
import subprocess
from pathlib import Path

import pytest

from openfactory.adapters.process_gates import ProcessGates

WORKTREE = Path(".openfactory/worktrees/T-1")
CHECK = "run ruff check"
FORMAT = "run ruff format --check"
GITLEAKS_ARGS = "git --pre-commit --staged --redact --no-banner --exit-code 3 ."
CHECK_LINE = "$ uv run ruff check"
FORMAT_LINE = "$ uv run ruff format --check"
GITLEAKS_LINE = "$ gitleaks " + GITLEAKS_ARGS


def make_tool(bin_dir: Path, record: Path, name: str, behaviours: dict, *, executable=True):
    """A /bin/sh stand-in. `behaviours` maps the joined args to (out, err, code, sleep)."""
    arms = []
    for args, (out, err, code, sleep) in behaviours.items():
        body = ""
        if out:
            body += f"echo {out}\n"
        if err:
            body += f"echo {err} >&2\n"
        if sleep:
            body += "exec /bin/sleep 30\n"
        body += f"exit {code}\n"
        arms.append(f'  "{args}")\n{body}  ;;\n')
    script = (
        "#!/bin/sh\n"
        f'echo "$*" >> {record}/{name}.args\n'
        f"pwd -P >> {record}/{name}.cwd\n"
        'case "$*" in\n' + "".join(arms) + "esac\nexit 99\n"
    )
    path = bin_dir / name
    path.write_text(script, encoding="utf-8")
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IRWXU if executable else mode & ~0o111)
    return path


@pytest.fixture
def env(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    record = tmp_path / "record"
    record.mkdir()
    repo = tmp_path / "repo"
    (repo / WORKTREE).mkdir(parents=True)
    monkeypatch.setenv("PATH", str(bin_dir))
    return bin_dir, record, repo


def uv(env, check=(0, False), fmt=(0, False)):
    bin_dir, record, _ = env
    behaviours = {
        CHECK: ("CHECK_OUT", "CHECK_ERR", check[0], check[1]),
        FORMAT: ("FORMAT_OUT", "FORMAT_ERR", fmt[0], fmt[1]),
    }
    make_tool(bin_dir, record, "uv", behaviours)


def gitleaks(env, code):
    bin_dir, record, _ = env
    make_tool(bin_dir, record, "gitleaks", {GITLEAKS_ARGS: ("GL_OUT", "GL_ERR", code, False)})


def lines(record, name, kind):
    f = record / f"{name}.{kind}"
    return f.read_text(encoding="utf-8").splitlines() if f.exists() else []


def in_order(text, parts):
    pos = -1
    for part in parts:
        nxt = text.find(part, pos + 1)
        assert nxt > pos, f"{part!r} missing or out of order in {text!r}"
        pos = nxt


# AC1


def test_missing_tool_none_when_both_present(env):
    bin_dir, record, repo = env
    uv(env)
    gitleaks(env, 0)
    assert ProcessGates(repo).missing_tool() is None


def test_missing_tool_names_gitleaks_when_only_it_is_missing(env):
    _, _, repo = env
    uv(env)
    assert ProcessGates(repo).missing_tool() == "gitleaks"


def test_missing_tool_names_uv_when_uv_or_both_missing(env):
    _, _, repo = env
    assert ProcessGates(repo).missing_tool() == "uv"
    gitleaks(env, 0)
    assert ProcessGates(repo).missing_tool() == "uv"


def test_missing_tool_counts_a_non_executable_file_as_missing(env):
    bin_dir, record, repo = env
    make_tool(bin_dir, record, "uv", {}, executable=False)
    gitleaks(env, 0)
    assert ProcessGates(repo).missing_tool() == "uv"


# AC2


def test_ruff_runs_both_commands_in_the_worktree(env, tmp_path, monkeypatch):
    _, record, repo = env
    uv(env)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    out = ProcessGates(repo).run("ruff", WORKTREE, 30)
    assert lines(record, "uv", "args") == [CHECK, FORMAT]
    expected = (repo / WORKTREE).resolve()
    assert [Path(c).resolve() for c in lines(record, "uv", "cwd")] == [expected, expected]
    assert out.passed is True
    assert out.finding is False
    assert out.marker_lines == []


@pytest.mark.parametrize(
    ("check", "fmt", "passed"),
    [(0, 0, True), (1, 0, False), (0, 1, False), (1, 1, False)],
)
def test_ruff_passes_only_when_both_exit_zero(env, check, fmt, passed):
    _, record, repo = env
    uv(env, check=(check, False), fmt=(fmt, False))
    out = ProcessGates(repo).run("ruff", WORKTREE, 30)
    assert lines(record, "uv", "args") == [CHECK, FORMAT]
    assert out.passed is passed
    assert out.finding is False
    assert out.marker_lines == []


# AC3


@pytest.mark.parametrize(
    ("code", "passed", "finding"),
    [(0, True, False), (3, False, True), (1, False, False), (2, False, False)],
)
def test_gitleaks_exit_status_decides_passed_and_finding(env, code, passed, finding):
    _, record, repo = env
    gitleaks(env, code)
    out = ProcessGates(repo).run("gitleaks", WORKTREE, 30)
    assert lines(record, "gitleaks", "args") == [GITLEAKS_ARGS]
    assert Path(lines(record, "gitleaks", "cwd")[0]).resolve() == (repo / WORKTREE).resolve()
    assert out.passed is passed
    assert out.finding is finding
    assert out.marker_lines == []


# AC4


@pytest.mark.parametrize(("check", "fmt"), [(0, 0), (1, 1)])
def test_ruff_text_holds_each_command_line_output_then_error(env, check, fmt):
    _, _, repo = env
    uv(env, check=(check, False), fmt=(fmt, False))
    text = ProcessGates(repo).run("ruff", WORKTREE, 30).text
    in_order(text, [CHECK_LINE, "CHECK_OUT", "CHECK_ERR", FORMAT_LINE, "FORMAT_OUT", "FORMAT_ERR"])
    assert text.startswith(CHECK_LINE + "\n")
    assert text.endswith("\n")


def test_gitleaks_text_holds_command_line_output_then_error(env):
    _, _, repo = env
    gitleaks(env, 3)
    text = ProcessGates(repo).run("gitleaks", WORKTREE, 30).text
    assert text == GITLEAKS_LINE + "\nGL_OUT\nGL_ERR\n"


# AC5


def test_a_timeout_fails_the_gate_and_the_second_command_still_runs(env):
    _, record, repo = env
    uv(env, check=(0, True))
    # Warm-up: macOS's first exec of a new script can take most of the 1 s limit.
    bin_dir = env[0]
    subprocess.run([str(bin_dir / "uv"), "warm-up"], capture_output=True, check=False)
    (record / "uv.args").unlink()
    (record / "uv.cwd").unlink()
    out = ProcessGates(repo).run("ruff", WORKTREE, 1)
    assert out.passed is False
    assert out.finding is False
    assert lines(record, "uv", "args") == [CHECK, FORMAT]
    assert "timed out after 1 s" in out.text
    in_order(out.text, [CHECK_LINE, "timed out after 1 s", FORMAT_LINE, "FORMAT_OUT"])


def test_gitleaks_that_cannot_start_fails_without_a_finding(env):
    _, _, repo = env
    out = ProcessGates(repo).run("gitleaks", WORKTREE, 30)
    assert out.passed is False
    assert out.finding is False
    assert out.marker_lines == []
    in_order(out.text, [GITLEAKS_LINE, "gitleaks could not be started"])


def test_ruff_without_uv_fails_and_both_commands_are_tried(env):
    _, _, repo = env
    out = ProcessGates(repo).run("ruff", WORKTREE, 30)
    assert out.passed is False
    assert out.finding is False
    assert out.marker_lines == []
    in_order(
        out.text,
        [CHECK_LINE, "uv could not be started", FORMAT_LINE, "uv could not be started"],
    )
