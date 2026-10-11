"""TASK-029 AC2-AC6: Claude Code LLM adapter, run against a stand-in executable."""

import json
import stat
import sys
from pathlib import Path

import pytest
from structlog.testing import capture_logs

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "claude_envelope.json"
SCHEMA = {"type": "object", "properties": {"colour": {"type": "string"}}}

STAND_IN = """\
#!{python}
import json, os, sys, time
from pathlib import Path

rec = Path({record!r})
with (rec / "starts").open("a") as f:
    f.write("x")
(rec / "args.json").write_text(json.dumps(sys.argv[1:]), encoding="utf-8")
(rec / "stdin.txt").write_bytes(sys.stdin.buffer.read())
(rec / "env.json").write_text(json.dumps(sorted(os.environ)), encoding="utf-8")
(rec / "cwd.txt").write_text(os.getcwd(), encoding="utf-8")
(rec / "listing.json").write_text(json.dumps(os.listdir(".")), encoding="utf-8")
time.sleep({sleep!r})
sys.stderr.write({stderr!r})
sys.stdout.write({stdout!r})
sys.exit({exit_code!r})
"""


def make_stand_in(tmp_path, stdout="", exit_code=0, sleep=0, stderr=""):
    record = tmp_path / "record"
    record.mkdir(exist_ok=True)
    script = tmp_path / "fake-claude"
    script.write_text(
        STAND_IN.format(
            python=sys.executable,
            record=str(record),
            sleep=sleep,
            stderr=stderr,
            stdout=stdout,
            exit_code=exit_code,
        ),
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH)
    return str(script), record


def envelope():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def run(tmp_path, env=None, *, timeout_s=30, prompt="plan it", schema=SCHEMA, **stand_in):
    from openfactory.adapters.claude_code_llm import ClaudeCodeLLM

    stdout = stand_in.pop("stdout", json.dumps(env if env is not None else envelope()))
    exe, record = make_stand_in(tmp_path, stdout=stdout, **stand_in)
    reply = ClaudeCodeLLM(executable=exe, timeout_s=timeout_s).complete(prompt, schema)
    return reply, record


def starts(record):
    return len((record / "starts").read_text())


def test_ac2_command_line_holds_the_required_flags(tmp_path):
    _, record = run(tmp_path)
    args = json.loads((record / "args.json").read_text())

    assert starts(record) == 1
    assert "-p" in args
    i = args.index("--output-format")
    assert args[i + 1] == "json"
    assert json.loads(args[args.index("--json-schema") + 1]) == SCHEMA
    assert args[args.index("--tools") + 1] == ""
    assert "--model" not in args


def test_ac2_runs_in_a_new_empty_directory(tmp_path):
    _, record = run(tmp_path)
    cwd = Path((record / "cwd.txt").read_text()).resolve()

    assert cwd != Path.cwd().resolve()
    assert json.loads((record / "listing.json").read_text()) == []


def test_ac2_prompt_arrives_unchanged_on_standard_input(tmp_path):
    prompt = "line one\nline two, café ✓"
    _, record = run(tmp_path, prompt=prompt)

    assert (record / "stdin.txt").read_bytes().decode("utf-8") == prompt


def test_ac2_default_time_limit_is_300_seconds():
    from openfactory.adapters.claude_code_llm import ClaudeCodeLLM

    assert ClaudeCodeLLM().timeout_s == 300


def test_ac3_reply_carries_the_fixture_values(tmp_path):
    reply, _ = run(tmp_path)

    assert reply.structured == {"colour": "red", "letters": 3}
    assert reply.model == "claude-opus-5-5"
    assert reply.tokens_in == 4381
    assert reply.tokens_out == 74
    assert reply.cost_usd == pytest.approx(0.036520000000000004)
    assert reply.duration_s == pytest.approx(2.236)


def test_ac3_absent_token_cost_and_model_fields_are_none(tmp_path):
    env = envelope()
    for key in ("usage", "total_cost_usd", "modelUsage"):
        del env[key]
    reply, _ = run(tmp_path, env)

    assert reply.model is None
    assert reply.tokens_in is None
    assert reply.tokens_out is None
    assert reply.cost_usd is None
    assert reply.structured == {"colour": "red", "letters": 3}


@pytest.mark.parametrize(
    "stand_in",
    [
        {"exit_code": 3, "stdout": "", "stderr": "boom"},
        {"stdout": "not json"},
        {"stdout": ""},
    ],
    ids=["non-zero-exit", "not-json", "no-output"],
)
def test_ac4_failed_process_raises_llm_error(tmp_path, stand_in):
    from openfactory.ports.llm_provider import LLMError

    with pytest.raises(LLMError) as raised:
        run(tmp_path, **stand_in)

    assert raised.value.timeout is False
    assert raised.value.duration_s >= 0
    assert str(raised.value).strip() != ""
    assert starts(tmp_path / "record") == 1


def test_ac4_timeout_raises_llm_error_with_timeout_true(tmp_path):
    from openfactory.ports.llm_provider import LLMError

    with pytest.raises(LLMError) as raised:
        run(tmp_path, timeout_s=2, sleep=10)

    assert raised.value.timeout is True
    assert raised.value.duration_s >= 2
    assert str(raised.value).strip() != ""
    assert starts(tmp_path / "record") == 1


def test_ac5_missing_structured_output_gives_none_and_a_rejection(tmp_path):
    from openfactory.domain.plan_checks import parse_reply

    env = envelope()
    del env["structured_output"]
    reply, _ = run(tmp_path, env)

    assert reply.structured is None
    assert reply.model == "claude-opus-5-5"
    assert reply.tokens_in == 4381
    assert reply.tokens_out == 74
    assert reply.cost_usd == pytest.approx(0.036520000000000004)
    assert reply.duration_s == pytest.approx(2.236)
    parsed = parse_reply(reply.structured)
    assert [r.message for r in parsed.rejections] == ["no structured result"]


def test_ac5_adapter_does_not_validate_the_structured_result(tmp_path):
    env = envelope()
    env["structured_output"] = {"colour": "red"}
    reply, _ = run(tmp_path, env)

    assert reply.structured == {"colour": "red"}


def test_ac6_api_key_is_removed_from_the_child_and_one_warning_logged(tmp_path, monkeypatch):
    secret = "sk-ant-secret-value-123"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    monkeypatch.setenv("OPENFACTORY_TEST_KEEP", "1")
    with capture_logs() as logs:
        _, record = run(tmp_path)

    names = json.loads((record / "env.json").read_text())
    assert "ANTHROPIC_API_KEY" not in names
    assert "OPENFACTORY_TEST_KEEP" in names
    warnings = [e for e in logs if e.get("log_level") == "warning"]
    assert len(warnings) == 1
    assert secret not in str(logs)


def test_ac6_no_warning_when_the_variable_is_not_set(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with capture_logs() as logs:
        run(tmp_path)

    assert [e for e in logs if e.get("log_level") == "warning"] == []
