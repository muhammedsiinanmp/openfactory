"""Claude Code implementation of the LLMProvider port.

Starts `claude -p --output-format json --json-schema` once per call, as described under
"Tech stack and repo layout" in docs/spec/phase1-spec.md and in ADR-005. The envelope's
field names are pinned by tests/fixtures/claude_envelope.json, not by the spec.
"""

import json
import os
import subprocess
import tempfile
import time
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, Field, ValidationError

from openfactory.domain.llm import LLMReply
from openfactory.ports.llm_provider import LLMError, LLMProvider

_API_KEY = "ANTHROPIC_API_KEY"

_log = structlog.get_logger()


class _Usage(BaseModel):
    input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    output_tokens: int | None = None


class _ModelUsage(BaseModel):
    output_tokens: int = Field(default=0, alias="outputTokens")


class _Envelope(BaseModel):
    structured_output: object | None = None
    usage: _Usage | None = None
    model_usage: dict[str, _ModelUsage] | None = Field(default=None, alias="modelUsage")
    total_cost_usd: float | None = None
    duration_ms: float | None = None


class ClaudeCodeLLM:
    def __init__(self, executable: str = "claude", timeout_s: float = 300) -> None:
        self.executable = executable
        self.timeout_s = timeout_s

    def complete(self, prompt: str, schema: dict[str, object]) -> LLMReply:
        args = [
            self.executable,
            "-p",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(schema),
            "--tools",
            "",
        ]
        # Built from the names, so the key's value is never read.
        env = {name: os.environ[name] for name in os.environ if name != _API_KEY}
        if _API_KEY in os.environ:
            _log.warning("anthropic_api_key_removed")
        started = time.monotonic()
        # An empty directory, so Claude Code loads no CLAUDE.md, settings or hooks of a repo.
        with tempfile.TemporaryDirectory() as cwd:
            try:
                done = subprocess.run(
                    args,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=self.timeout_s,
                    env=env,
                    cwd=cwd,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise LLMError(
                    f"timed out after {self.timeout_s:g} s",
                    duration_s=time.monotonic() - started,
                    timeout=True,
                ) from exc
            except OSError as exc:
                raise LLMError(
                    f"claude could not be started: {exc}",
                    duration_s=time.monotonic() - started,
                    timeout=False,
                ) from exc
        measured = time.monotonic() - started
        if done.returncode != 0:
            text = done.stderr.strip() or f"claude exited with status {done.returncode}"
            raise LLMError(text, duration_s=measured, timeout=False)
        try:
            envelope = _Envelope.model_validate(json.loads(done.stdout))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise LLMError(
                "claude output is not a JSON envelope", duration_s=measured, timeout=False
            ) from exc
        usage = envelope.usage
        return LLMReply(
            structured=envelope.structured_output,
            model=_model(envelope.model_usage),
            tokens_in=None if usage is None else _tokens_in(usage),
            tokens_out=None if usage is None else usage.output_tokens,
            cost_usd=envelope.total_cost_usd,
            duration_s=measured if envelope.duration_ms is None else envelope.duration_ms / 1000,
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
    _: type[LLMProvider] = ClaudeCodeLLM
