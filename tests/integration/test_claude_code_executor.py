"""TASK-048 AC1-AC6: Claude Code executor adapter, run against a stand-in executable."""

import ast
import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from structlog.testing import capture_logs

from openfactory.domain.contracts import Limits, TaskContract

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "claude_agent_envelope.json"
ADAPTER = Path(__file__).resolve().parents[2] / "src/openfactory/adapters/claude_code_executor.py"
TOOLS = "Read,Glob,Grep,Edit,Write,Bash"
WORKDIR = Path(".openfactory/worktrees/AUTH-002")
OUTPUT_DIR = Path(".openfactory/runs/run_0002")

STAND_IN = """\
#!{python}
import json, os, sys
from pathlib import Path

rec = Path({record!r})
with (rec / "starts").open("a") as f:
    f.write("x")
(rec / "args.json").write_text(json.dumps(sys.argv[1:]), encoding="utf-8")
(rec / "stdin.txt").write_bytes(sys.stdin.buffer.read())
(rec / "env.json").write_text(json.dumps(sorted(os.environ)), encoding="utf-8")
(rec / "cwd.txt").write_text(os.getcwd(), encoding="utf-8")
sys.stdout.buffer.write(Path({payload!r}).read_bytes())
sys.exit(0)
"""


def make_stand_in(tmp_path, payload: bytes):
    record = tmp_path / "record"
    record.mkdir(exist_ok=True)
    payload_file = tmp_path / "payload.bin"
    payload_file.write_bytes(payload)
    script = tmp_path / "fake-claude"
    script.write_text(
        STAND_IN.format(python=sys.executable, record=str(record), payload=str(payload_file)),
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH)
    return str(script), record


def contract(max_runtime_s=1200):
    return TaskContract(
        task_id="AUTH-002",
        objective="obj",
        requirements=["r"],
        acceptance_criteria=["a"],
        depends_on=[],
        components=["c"],
        role="implementer",
        allowed_paths=["src/**"],
        forbidden_paths=[],
        required_gates=["path_check", "ruff", "pytest", "gitleaks", "review"],
        limits=Limits(max_runtime_s=max_runtime_s, max_attempts=3, max_cost_usd=5.0),
    )


def run(tmp_path, monkeypatch, payload=None, *, pack="plan it", max_runtime_s=1200):
    """Run the executor on a test repo; return (result, record, repo, elsewhere)."""
    from openfactory.adapters.claude_code_executor import ClaudeCodeExecutor

    repo = tmp_path / "repo"
    (repo / WORKDIR).mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    if payload is None:
        payload = FIXTURE.read_bytes()
    exe, record = make_stand_in(tmp_path, payload)
    result = ClaudeCodeExecutor(repo, exe).run(contract(max_runtime_s), pack, WORKDIR, OUTPUT_DIR)
    return result, record, repo, elsewhere


def test_ac1_command_line_holds_the_flags_and_six_tools(tmp_path, monkeypatch):
    _, record, _, _ = run(tmp_path, monkeypatch)
    args = json.loads((record / "args.json").read_text())

    assert len((record / "starts").read_text()) == 1
    assert "-p" in args
    assert args[args.index("--output-format") + 1] == "json"
    assert args[args.index("--tools") + 1] == TOOLS
    assert args[args.index("--allowedTools") + 1] == TOOLS
    assert "--model" not in args
    assert "--json-schema" not in args


def test_ac1_context_pack_arrives_on_standard_input(tmp_path, monkeypatch):
    pack = "line one\nline two, café ✓"
    _, record, _, _ = run(tmp_path, monkeypatch, pack=pack)

    assert (record / "stdin.txt").read_bytes().decode("utf-8") == pack


def test_ac1_module_does_not_import_app_and_ends_with_type_assertion():
    tree = ast.parse(ADAPTER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("openfactory.app")
        elif isinstance(node, ast.Import):
            assert not any(a.name.startswith("openfactory.app") for a in node.names)
    last = tree.body[-1]
    assert isinstance(last, ast.If)
    assert ast.unparse(last.test) == "TYPE_CHECKING"
    assert "AgentExecutor" in ast.unparse(last)


def test_ac2_process_runs_in_the_worktree_of_the_repo(tmp_path, monkeypatch):
    _, record, repo, _ = run(tmp_path, monkeypatch)
    cwd = Path((record / "cwd.txt").read_text()).resolve()

    assert cwd == (repo / WORKDIR).resolve()


@pytest.mark.parametrize("limit", [1200, 7])
def test_ac3_time_limit_is_the_contracts_max_runtime(tmp_path, monkeypatch, limit):
    import openfactory.adapters.claude_code_executor as mod

    real = subprocess.run
    seen = []

    def spy(*args, **kwargs):
        seen.append(kwargs.get("timeout"))
        return real(*args, **kwargs)

    monkeypatch.setattr(mod.subprocess, "run", spy)
    run(tmp_path, monkeypatch, max_runtime_s=limit)

    assert seen == [limit]


def test_ac4_api_key_is_removed_from_the_child_and_one_warning_logged(tmp_path, monkeypatch):
    secret = "sk-ant-secret-value-123"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    monkeypatch.setenv("OPENFACTORY_TEST_KEEP", "1")
    with capture_logs() as logs:
        _, record, _, _ = run(tmp_path, monkeypatch)

    names = json.loads((record / "env.json").read_text())
    assert "ANTHROPIC_API_KEY" not in names
    assert "OPENFACTORY_TEST_KEEP" in names
    warnings = [e for e in logs if e.get("log_level") == "warning"]
    assert len(warnings) == 1
    assert secret not in str(logs)


def test_ac4_no_warning_when_the_variable_is_not_set(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with capture_logs() as logs:
        run(tmp_path, monkeypatch)

    assert [e for e in logs if e.get("log_level") == "warning"] == []


def test_ac5_result_carries_the_fixture_values(tmp_path, monkeypatch):
    result, _, _, _ = run(tmp_path, monkeypatch)

    assert result.exit == "ok"
    assert result.error is None
    assert result.summary == (
        "I created `hello.txt` containing `hi`, and `ls` shows it as the only file "
        "in the directory."
    )
    assert result.model == "claude-opus-5-5"
    assert result.tokens_in == 26108
    assert result.tokens_out == 251
    assert result.cost_usd == pytest.approx(0.0419402)
    assert result.duration_s == pytest.approx(5.735)


def test_ac5_model_is_the_one_with_most_output_tokens(tmp_path, monkeypatch):
    env = json.loads(FIXTURE.read_text(encoding="utf-8"))
    other = dict(env["modelUsage"]["claude-opus-5-5"], outputTokens=100000)
    env["modelUsage"]["claude-haiku-other"] = other
    result, _, _, _ = run(tmp_path, monkeypatch, json.dumps(env).encode("utf-8"))

    assert result.model == "claude-haiku-other"


def test_ac6_transcript_holds_the_printed_bytes_under_the_repo(tmp_path, monkeypatch):
    _, _, repo, elsewhere = run(tmp_path, monkeypatch)

    transcript = repo / ".openfactory/runs/run_0002/transcript.json"
    assert transcript.read_bytes() == FIXTURE.read_bytes()
    assert not (elsewhere / ".openfactory").exists()
