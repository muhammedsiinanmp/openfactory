"""TASK-049 AC1-AC6: Claude Code executor adapter, failed processes, on a stand-in executable."""

import json
import stat
import sys
from pathlib import Path

import pytest

from openfactory.domain.contracts import Limits, TaskContract

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "claude_agent_envelope.json"
TOOLS = "Read,Glob,Grep,Edit,Write,Bash"
WORKDIR = Path(".openfactory/worktrees/AUTH-002")
OUTPUT_DIR = Path(".openfactory/runs/run_0002")

STAND_IN = """\
#!{python}
import json, sys, time
from pathlib import Path

Path({record!r}, "args.json").write_text(json.dumps(sys.argv[1:]), encoding="utf-8")
sys.stdin.buffer.read()
time.sleep({sleep})
sys.stderr.write({stderr!r})
sys.stdout.buffer.write(Path({payload!r}).read_bytes())
sys.stdout.buffer.flush()
sys.exit({status})
"""


def make_stand_in(tmp_path, payload: bytes, status: int, stderr: str, sleep: float):
    record = tmp_path / "record"
    record.mkdir(exist_ok=True)
    payload_file = tmp_path / "payload.bin"
    payload_file.write_bytes(payload)
    script = tmp_path / "fake-claude"
    script.write_text(
        STAND_IN.format(
            python=sys.executable,
            record=str(record),
            payload=str(payload_file),
            status=status,
            stderr=stderr,
            sleep=sleep,
        ),
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


def run(
    tmp_path,
    payload=None,
    *,
    status=0,
    stderr="",
    sleep=0,
    max_runtime_s=1200,
    executable=None,
):
    """Run the executor on a test repo; return (result, record, repo)."""
    from openfactory.adapters.claude_code_executor import ClaudeCodeExecutor

    repo = tmp_path / "repo"
    (repo / WORKDIR).mkdir(parents=True)
    if payload is None:
        payload = FIXTURE.read_bytes()
    exe, record = make_stand_in(tmp_path, payload, status, stderr, sleep)
    result = ClaudeCodeExecutor(repo, executable or exe).run(
        contract(max_runtime_s), "plan it", WORKDIR, OUTPUT_DIR
    )
    return result, record, repo


def transcript(repo) -> Path:
    return repo / ".openfactory/runs/run_0002/transcript.json"


def envelope(**changes) -> bytes:
    env = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for key, value in changes.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return json.dumps(env).encode("utf-8")


def assert_failed(result, exit_):
    assert result.exit == exit_
    assert isinstance(result.error, str) and result.error
    assert result.summary == ""


def assert_no_metrics(result):
    assert result.model is None
    assert result.tokens_in is None
    assert result.tokens_out is None
    assert result.cost_usd is None


def test_ac1_non_zero_exit_returns_standard_error_as_the_error(tmp_path):
    result, _, _ = run(tmp_path, b"", status=3, stderr="boom")

    assert_failed(result, "error")
    assert result.error == "boom"
    assert_no_metrics(result)


def test_ac1_non_zero_exit_without_standard_error_names_the_status(tmp_path):
    result, _, _ = run(tmp_path, b"", status=3)

    assert_failed(result, "error")
    assert result.error == "claude exited with status 3"


def test_ac1_non_zero_exit_with_the_fixture_printed_is_still_a_failure(tmp_path):
    result, _, _ = run(tmp_path, status=3)

    assert_failed(result, "error")
    assert result.duration_s != pytest.approx(5.735)


def test_ac1_missing_executable_returns_a_failed_result(tmp_path):
    result, _, _ = run(tmp_path, executable=str(tmp_path / "no-such-claude"))

    assert_failed(result, "error")
    assert result.error is not None
    assert result.error.startswith("claude could not be started: ")
    assert_no_metrics(result)


def test_ac2_output_that_is_not_json_is_a_failed_process(tmp_path):
    result, _, _ = run(tmp_path, b"not json")

    assert_failed(result, "error")
    assert result.error == "claude output is not a JSON envelope"


def test_ac2_envelope_without_result_is_a_failed_process(tmp_path):
    result, _, _ = run(tmp_path, envelope(result=None))

    assert_failed(result, "error")
    assert result.error == "claude output is not a JSON envelope"


def test_ac3_error_envelope_gives_its_result_as_the_error(tmp_path):
    payload = envelope(
        is_error=True, subtype="error_during_execution", result="Usage limit reached"
    )
    result, _, _ = run(tmp_path, payload)

    assert_failed(result, "error")
    assert result.error == "Usage limit reached"
    assert result.model == "claude-opus-5-5"
    assert result.tokens_in == 26108
    assert result.tokens_out == 251
    assert result.cost_usd == pytest.approx(0.0419402)
    assert result.duration_s != pytest.approx(5.735)


def test_ac3_error_envelope_without_result_names_the_subtype(tmp_path):
    payload = envelope(is_error=True, subtype="error_during_execution", result=None)
    result, _, _ = run(tmp_path, payload)

    assert_failed(result, "error")
    assert result.error == "claude reported an error: error_during_execution"


def test_ac3_error_subtype_alone_is_an_error_envelope(tmp_path):
    result, _, _ = run(tmp_path, envelope(is_error=False, subtype="error_max_turns"))

    assert_failed(result, "error")


def test_ac4_run_past_max_runtime_is_a_timeout(tmp_path):
    result, _, _ = run(tmp_path, sleep=10, max_runtime_s=1)

    assert_failed(result, "timeout")
    assert result.error == "timed out after 1 s"
    assert 1 <= result.duration_s < 10
    assert_no_metrics(result)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"payload": b"not json"},
        {"status": 3},
    ],
    ids=["not-json", "exit-3-with-fixture"],
)
def test_ac5_transcript_holds_the_printed_bytes_of_a_failed_run(tmp_path, kwargs):
    payload = kwargs.get("payload", FIXTURE.read_bytes())
    _, _, repo = run(tmp_path, **kwargs)

    assert transcript(repo).read_bytes() == payload


def test_ac5_transcript_is_empty_after_a_timeout(tmp_path):
    _, _, repo = run(tmp_path, sleep=10, max_runtime_s=1)

    assert transcript(repo).read_bytes() == b""


def test_ac5_transcript_is_empty_after_a_missing_executable(tmp_path):
    _, _, repo = run(tmp_path, executable=str(tmp_path / "no-such-claude"))

    assert transcript(repo).read_bytes() == b""


def test_ac6_successful_run_passes_exactly_this_argument_list(tmp_path):
    # Pin test: passes against the TASK-048 adapter already; not a failing-first test.
    _, record, _ = run(tmp_path)
    args = json.loads((record / "args.json").read_text())

    assert args == ["-p", "--output-format", "json", "--tools", TOOLS, "--allowedTools", TOOLS]
