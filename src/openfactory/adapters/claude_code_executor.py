"""Claude Code implementation of the AgentExecutor port.

Starts `claude -p --output-format json` once per run in the task's worktree, as described
under "Execution" ("The agent call", "Adapter interface") in docs/spec/phase1-spec.md and
in ADR-005 and ADR-014. The envelope's field names are pinned by
tests/fixtures/claude_agent_envelope.json, not by the spec.

Only a run that succeeds is handled: a failed process raises, and an envelope that reports
an error is read as a success (TASK-048; the failed-process cases are a later task).
"""

import json
import os
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, Field

from openfactory.domain.agent_run import ContextPack, RunResult
from openfactory.domain.contracts import TaskContract
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


class _Envelope(BaseModel):
    result: str
    usage: _Usage | None = None
    model_usage: dict[str, _ModelUsage] | None = Field(default=None, alias="modelUsage")
    total_cost_usd: float | None = None
    duration_ms: float | None = None


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
        started = time.monotonic()
        # Relative paths are resolved against the repo, not the caller's working directory.
        done = subprocess.run(
            args,
            input=context.encode("utf-8"),
            capture_output=True,
            timeout=contract.limits.max_runtime_s,
            env=env,
            cwd=self.repo / workdir,
            check=False,
        )
        measured = time.monotonic() - started
        # The bytes as printed, written before they are parsed.
        directory = self.repo / output_dir
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "transcript.json").write_bytes(done.stdout)
        # A non-zero exit raises; it becomes a returned result with the failed-process cases.
        done.check_returncode()
        envelope = _Envelope.model_validate(json.loads(done.stdout))
        usage = envelope.usage
        return RunResult(
            exit="ok",
            model=_model(envelope.model_usage),
            tokens_in=None if usage is None else _tokens_in(usage),
            tokens_out=None if usage is None else usage.output_tokens,
            cost_usd=envelope.total_cost_usd,
            duration_s=measured if envelope.duration_ms is None else envelope.duration_ms / 1000,
            error=None,
            summary=envelope.result,
        )


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
