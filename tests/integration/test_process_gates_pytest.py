"""TASK-061 AC1-AC5: the openfactory_req plugin and the `pytest` gate of process_gates."""

import ast
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import openfactory.adapters.process_gates as process_gates_module
from openfactory.adapters.process_gates import ProcessGates
from openfactory.domain.gates import MarkerLine

WORKTREE = Path(".openfactory/worktrees/T-1")
COLLECT = "run pytest --collect-only -q -p openfactory_req tests/"
RUN = "run pytest -p openfactory_req tests/"
COLLECT_LINE = "$ uv " + COLLECT
RUN_LINE = "$ uv " + RUN
SRC = Path(__file__).resolve().parents[2] / "src" / "openfactory"
PLUGIN_DIR = SRC / "adapters" / "pytest_plugin"


def write_script(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IRWXU)


def make_uv(bin_dir: Path, record: Path, behaviours: dict) -> None:
    """Recording /bin/sh stand-in. `behaviours` maps joined args to a dict of
    out, err, code, sleep and write (a line put into OPENFACTORY_REQ_OUT)."""
    arms = []
    for args, b in behaviours.items():
        body = ""
        if b.get("write"):
            body += f"printf '%s\\n' '{b['write']}' > \"$OPENFACTORY_REQ_OUT\"\n"
        if b.get("out"):
            body += f"echo {b['out']}\n"
        if b.get("err"):
            body += f"echo {b['err']} >&2\n"
        if b.get("sleep"):
            body += "exec /bin/sleep 30\n"
        body += f"exit {b.get('code', 0)}\n"
        arms.append(f'  "{args}")\n{body}  ;;\n')
    script = (
        "#!/bin/sh\n"
        f'echo "$*" >> {record}/uv.args\n'
        f"pwd -P >> {record}/uv.cwd\n"
        f'echo "${{PYTHONPATH-}}" >> {record}/uv.pythonpath\n'
        f'echo "${{OPENFACTORY_REQ_OUT-}}" >> {record}/uv.reqout\n'
        'case "$*" in\n' + "".join(arms) + "esac\nexit 99\n"
    )
    write_script(bin_dir / "uv", script)


def make_exec_uv(bin_dir: Path) -> None:
    """A uv that drops `run pytest` and execs the test interpreter's pytest."""
    write_script(
        bin_dir / "uv",
        f'#!/bin/sh\nshift 2\nexec "{sys.executable}" -m pytest "$@"\n',
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    record = tmp_path / "record"
    record.mkdir()
    repo = tmp_path / "repo"
    (repo / WORKTREE).mkdir(parents=True)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.delenv("PYTHONPATH", raising=False)
    return bin_dir, record, repo


def lines(record, kind):
    f = record / f"uv.{kind}"
    return f.read_text(encoding="utf-8").splitlines() if f.exists() else []


def in_order(text, parts):
    pos = -1
    for part in parts:
        nxt = text.find(part, pos + 1)
        assert nxt > pos, f"{part!r} missing or out of order in {text!r}"
        pos = nxt


def sample(repo: Path, files: dict[str, str]) -> Path:
    """A sample project in the worktree. It does not register `req` but is strict."""
    root = repo / WORKTREE
    (root / "pytest.ini").write_text("[pytest]\naddopts = --strict-markers\n", encoding="utf-8")
    (root / "tests").mkdir(exist_ok=True)
    for name, source in files.items():
        path = root / "tests" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return root


# AC1


def test_real_plugin_writes_one_marker_line_per_test_with_req_ids(env):
    bin_dir, _, repo = env
    make_exec_uv(bin_dir)
    sample(
        repo,
        {
            "test_a.py": (
                "import pytest\n\n"
                '@pytest.mark.req("REQ-A-001")\n'
                "def test_marked():\n    pass\n\n"
                "def test_unmarked():\n    pass\n"
            ),
            "sub/test_b.py": (
                "import pytest\n\n"
                '@pytest.mark.req("REQ-B-001", "REQ-B-002")\n'
                "def test_two_ids():\n    pass\n"
            ),
        },
    )
    out = ProcessGates(repo).run("pytest", WORKTREE, 120)
    # --strict-markers in the sample's config and still exit 0: the plugin registers `req`.
    assert out.passed is True, out.text
    assert out.finding is False
    assert all(isinstance(m, MarkerLine) for m in out.marker_lines)
    assert len(out.marker_lines) == 3
    in_a = [m.req for m in out.marker_lines if m.file == "tests/test_a.py"]
    in_b = [m.req for m in out.marker_lines if m.file == "tests/sub/test_b.py"]
    assert in_a == [["REQ-A-001"], []]
    assert in_b == [["REQ-B-001", "REQ-B-002"]]


# AC2


def imports_of(path: Path) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            found.add(node.module or "")
            found |= {a.name for a in node.names}
    return found


def test_plugin_dir_holds_exactly_the_one_plugin_file():
    assert sorted(p.name for p in PLUGIN_DIR.glob("*.py")) == ["openfactory_req.py"]


def test_plugin_imports_only_pytest_json_and_os():
    names = imports_of(PLUGIN_DIR / "openfactory_req.py")
    assert names
    assert {n.split(".")[0] for n in names} <= {"pytest", "json", "os"}


def test_no_other_module_imports_the_plugin():
    plugin = PLUGIN_DIR / "openfactory_req.py"
    assert plugin.exists()
    offenders = [
        str(p)
        for p in SRC.rglob("*.py")
        if p != plugin and any("openfactory_req" in n for n in imports_of(p))
    ]
    assert offenders == []


# AC3


def test_pytest_gate_runs_both_commands_in_the_worktree_with_the_plugin_env(
    env, tmp_path, monkeypatch
):
    bin_dir, record, repo = env
    make_uv(bin_dir, record, {COLLECT: {}, RUN: {}})
    monkeypatch.setenv("PYTHONPATH", "/existing/path")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    ProcessGates(repo).run("pytest", WORKTREE, 30)
    assert lines(record, "args") == [COLLECT, RUN]
    expected = (repo / WORKTREE).resolve()
    assert [Path(c).resolve() for c in lines(record, "cwd")] == [expected, expected]
    plugin_dir = (Path(process_gates_module.__file__).parent / "pytest_plugin").resolve()
    for value in lines(record, "pythonpath"):
        entries = value.split(os.pathsep)
        assert Path(entries[0]).resolve() == plugin_dir
        assert entries[1:] == ["/existing/path"]


def test_req_out_is_a_temp_file_outside_the_repo_removed_afterwards(env):
    bin_dir, record, repo = env
    make_uv(bin_dir, record, {COLLECT: {}, RUN: {}})
    ProcessGates(repo).run("pytest", WORKTREE, 30)
    collect_out, run_out = lines(record, "reqout")
    assert collect_out
    path = Path(collect_out).resolve()
    assert not path.is_relative_to(repo.resolve())
    assert not path.exists()
    # Set only for the --collect-only command.
    assert run_out == ""


# AC4


@pytest.mark.parametrize(
    ("collect", "run", "passed"),
    [(0, 0, True), (1, 0, False), (0, 1, False), (1, 1, False)],
)
def test_passed_only_when_both_commands_exit_zero_and_both_run(env, collect, run, passed):
    bin_dir, record, repo = env
    make_uv(bin_dir, record, {COLLECT: {"code": collect}, RUN: {"code": run}})
    out = ProcessGates(repo).run("pytest", WORKTREE, 30)
    assert lines(record, "args") == [COLLECT, RUN]
    assert out.passed is passed
    assert out.finding is False


def test_real_failing_test_fails_the_gate_but_marker_lines_are_kept(env):
    bin_dir, _, repo = env
    make_exec_uv(bin_dir)
    sample(
        repo,
        {
            "test_a.py": (
                'import pytest\n\n@pytest.mark.req("REQ-A-001")\ndef test_x():\n    assert 0\n'
            )
        },
    )
    out = ProcessGates(repo).run("pytest", WORKTREE, 120)
    assert out.passed is False
    assert out.finding is False
    assert out.marker_lines == [
        MarkerLine(node_id="tests/test_a.py::test_x", file="tests/test_a.py", req=["REQ-A-001"])
    ]


def test_real_run_that_collects_no_test_fails_the_gate(env):
    bin_dir, _, repo = env
    make_exec_uv(bin_dir)
    sample(repo, {})
    out = ProcessGates(repo).run("pytest", WORKTREE, 120)
    assert out.passed is False
    assert out.finding is False
    assert out.marker_lines == []


# AC5


def test_text_holds_each_command_line_output_then_error(env):
    bin_dir, record, repo = env
    make_uv(
        bin_dir,
        record,
        {
            COLLECT: {"out": "COLLECT_OUT", "err": "COLLECT_ERR"},
            RUN: {"out": "RUN_OUT", "err": "RUN_ERR"},
        },
    )
    text = ProcessGates(repo).run("pytest", WORKTREE, 30).text
    in_order(text, [COLLECT_LINE, "COLLECT_OUT", "COLLECT_ERR", RUN_LINE, "RUN_OUT", "RUN_ERR"])
    assert text.startswith(COLLECT_LINE + "\n")


def test_without_uv_the_gate_fails_without_raising(env):
    _, _, repo = env
    out = ProcessGates(repo).run("pytest", WORKTREE, 30)
    assert out.passed is False
    assert out.finding is False
    assert out.marker_lines == []
    assert "uv could not be started" in out.text


def test_a_timeout_on_collect_fails_the_gate_and_the_second_command_still_runs(env):
    bin_dir, record, repo = env
    make_uv(bin_dir, record, {COLLECT: {"sleep": True}, RUN: {"out": "RUN_OUT"}})
    # Warm-up: macOS's first exec of a new script can take most of the 1 s limit.
    subprocess.run([str(bin_dir / "uv"), "warm-up"], capture_output=True, check=False)
    for kind in ("args", "cwd", "pythonpath", "reqout"):
        (record / f"uv.{kind}").unlink()
    out = ProcessGates(repo).run("pytest", WORKTREE, 1)
    assert out.passed is False
    assert out.finding is False
    assert out.marker_lines == []
    assert lines(record, "args") == [COLLECT, RUN]
    in_order(out.text, [COLLECT_LINE, "timed out after 1 s", RUN_LINE, "RUN_OUT"])


def test_an_invalid_marker_line_fails_the_gate_without_raising(env):
    bin_dir, record, repo = env
    bad = '{"node_id": "tests/test_a.py::t", "file": "tests/test_a.py", "req": [123]}'
    make_uv(bin_dir, record, {COLLECT: {"write": bad}, RUN: {}})
    out = ProcessGates(repo).run("pytest", WORKTREE, 30)
    assert out.passed is False
    assert out.finding is False
    assert out.marker_lines == []
    assert out.text.rstrip("\n").splitlines()[-1] == f"invalid marker line: {bad}"


def test_task079_ac2_a_line_without_node_id_fails_the_gate(env):
    bin_dir, record, repo = env
    old = '{"file": "tests/test_a.py", "req": []}'
    make_uv(bin_dir, record, {COLLECT: {"write": old}, RUN: {}})
    out = ProcessGates(repo).run("pytest", WORKTREE, 30)
    assert out.passed is False
    assert out.marker_lines == []
    assert out.text.rstrip("\n").splitlines()[-1] == f"invalid marker line: {old}"


def test_task079_ac1_real_plugin_lines_carry_pytest_node_ids(env):
    bin_dir, _, repo = env
    make_exec_uv(bin_dir)
    sample(
        repo,
        {
            "test_a.py": (
                "import pytest\n\n"
                '@pytest.mark.req("REQ-A-001")\n'
                "def test_marked():\n    pass\n\n"
                "def test_unmarked():\n    pass\n"
            ),
            "sub/test_b.py": (
                "import pytest\n\n"
                '@pytest.mark.req("REQ-B-001", "REQ-B-002")\n'
                "def test_x():\n    pass\n"
            ),
        },
    )
    out = ProcessGates(repo).run("pytest", WORKTREE, 120)
    assert out.passed is True, out.text
    assert sorted(out.marker_lines, key=lambda m: m.node_id) == [
        MarkerLine(
            node_id="tests/sub/test_b.py::test_x",
            file="tests/sub/test_b.py",
            req=["REQ-B-001", "REQ-B-002"],
        ),
        MarkerLine(
            node_id="tests/test_a.py::test_marked", file="tests/test_a.py", req=["REQ-A-001"]
        ),
        MarkerLine(node_id="tests/test_a.py::test_unmarked", file="tests/test_a.py", req=[]),
    ]


def test_task079_ac1_plugin_still_imports_only_pytest_json_os():
    tree = ast.parse((PLUGIN_DIR / "openfactory_req.py").read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            mods.add((node.module or "").split(".")[0])
    assert mods == {"pytest", "json", "os"}
