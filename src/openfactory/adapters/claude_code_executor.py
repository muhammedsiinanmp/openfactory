"""Claude Code implementation of the AgentExecutor port.

Starts `claude -p --output-format json` once per run in the task's worktree, as described
under "Execution" ("The agent call", "Adapter interface") in docs/spec/phase1-spec.md and
in ADR-005 and ADR-014. The envelope's field names are pinned by
tests/fixtures/claude_agent_envelope.json, not by the spec.

A failed process is returned, not raised: a timeout has `exit` `timeout`; a `claude` that
cannot be started, an envelope that reports an error, a non-zero exit and an envelope that
cannot be parsed have `exit` `error`. The texts and the order of the checks are rows of
2026-10-14 in docs/decisions.md.
"""

import json
import os
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, Field, ValidationError

from openfactory.domain.agent_run import ContextPack, RunResult
from openfactory.domain.contracts import TaskContract
from openfactory.domain.payloads import RunExit
from openfactory.ports.agent_executor import AgentExecutor

_API_KEY = "ANTHROPIC_API_KEY"
_TOOLS = "Read,Glob,Grep,Edit,Write,Bash"

_log = structlog.get_logger()


class _Usage(BaseModel):
    input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    output_tokens: int | None = None


class _ModelUsage(BaseModel):
    output_tokens: int = Field(default=0, alias="outputTokens")


class _Metrics(BaseModel):
    usage: _Usage | None = None
    model_usage: dict[str, _ModelUsage] | None = Field(default=None, alias="modelUsage")
    total_cost_usd: float | None = None


class _Envelope(_Metrics):
    result: str
    duration_ms: float | None = None


class _Reported(_Metrics):
    # What a failed process printed. Every field is optional, and the three that decide
    # whether the envelope reports an error take any value.
    is_error: object = None
    subtype: object = None
    result: object = None


class ClaudeCodeExecutor:
    def __init__(self, repo: Path, executable: str = "claude") -> None:
        self.repo = repo
        self.executable = executable

    def run(
        self, contract: TaskContract, context: ContextPack, workdir: Path, output_dir: Path
    ) -> RunResult:
        # --tools limits the tools available, --allowedTools approves them in advance.
        args = [
            self.executable,
            "-p",
            "--output-format",
            "json",
            "--tools",
            _TOOLS,
            "--allowedTools",
            _TOOLS,
        ]
        # Built from the names, so the key's value is never read.
        env = {name: os.environ[name] for name in os.environ if name != _API_KEY}
        if _API_KEY in os.environ:
            _log.warning("anthropic_api_key_removed")
        limit = contract.limits.max_runtime_s
        started = time.monotonic()
        # Relative paths are resolved against the repo, not the caller's working directory.
        try:
            done = subprocess.run(
                args,
                input=context.encode("utf-8"),
                capture_output=True,
                timeout=limit,
                env=env,
                cwd=self.repo / workdir,
                check=False,
            )
        except subprocess.TimeoutExpired:
            measured = time.monotonic() - started
            self._write_transcript(output_dir, b"")
            return _result("timeout", None, measured, f"timed out after {limit} s")
        except OSError as error:
            measured = time.monotonic() - started
            self._write_transcript(output_dir, b"")
            return _result("error", None, measured, f"claude could not be started: {error}")
        measured = time.monotonic() - started
        # The bytes as printed, written before they are parsed.
        self._write_transcript(output_dir, done.stdout)
        try:
            loaded: object = json.loads(done.stdout)
        except ValueError:
            loaded = None
        reported = _reported(loaded)
        if reported is not None and _reports_error(reported):
            return _result("error", reported, measured, _reported_error(reported))
        if done.returncode != 0:
            text = done.stderr.decode("utf-8", errors="replace").strip()
            return _result(
                "error", reported, measured, text or f"claude exited with status {done.returncode}"
            )
        try:
            envelope = _Envelope.model_validate(loaded)
        except ValidationError:
            return _result("error", reported, measured, "claude output is not a JSON envelope")
        duration_s = measured if envelope.duration_ms is None else envelope.duration_ms / 1000
        return _result("ok", envelope, duration_s, None, envelope.result)

    def _write_transcript(self, output_dir: Path, printed: bytes) -> None:
        directory = self.repo / output_dir
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "transcript.json").write_bytes(printed)


def _result(
    exit_: RunExit,
    metrics: _Metrics | None,
    duration_s: float,
    error: str | None,
    summary: str = "",
) -> RunResult:
    # Model, tokens and cost are whatever the process printed, also when it failed.
    usage = None if metrics is None else metrics.usage
    return RunResult(
        exit=exit_,
        model=None if metrics is None else _model(metrics.model_usage),
        tokens_in=None if usage is None else _tokens_in(usage),
        tokens_out=None if usage is None else usage.output_tokens,
        cost_usd=None if metrics is None else metrics.total_cost_usd,
        duration_s=duration_s,
        error=error,
        summary=summary,
    )


def _reported(loaded: object) -> _Reported | None:
    # None when the output is not a JSON object or its metric fields do not validate.
    if not isinstance(loaded, dict):
        return None
    try:
        return _Reported.model_validate(loaded)
    except ValidationError:
        return None


def _reports_error(reported: _Reported) -> bool:
    return reported.is_error is True or (
        isinstance(reported.subtype, str) and reported.subtype != "success"
    )


def _reported_error(reported: _Reported) -> str:
    if isinstance(reported.result, str) and reported.result:
        return reported.result
    if isinstance(reported.subtype, str):
        return f"claude reported an error: {reported.subtype}"
    return "claude reported an error"


def _tokens_in(usage: _Usage) -> int | None:
    # The sum of the counts the runtime reported; None when it reported none of them.
    counts = [
        count
        for count in (
            usage.input_tokens,
            usage.cache_creation_input_tokens,
            usage.cache_read_input_tokens,
        )
        if count is not None
    ]
    return sum(counts) if counts else None


def _model(usage: dict[str, _ModelUsage] | None) -> str | None:
    # With several models, the one with the most output tokens; the first on a tie.
    if not usage:
        return None
    return max(usage, key=lambda name: usage[name].output_tokens)


if TYPE_CHECKING:
    _: type[AgentExecutor] = ClaudeCodeExecutor
