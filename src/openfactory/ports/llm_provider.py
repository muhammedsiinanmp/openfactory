"""LLMProvider port: one planner or classifier call to the model runtime.

See docs/spec/phase1-spec.md ("Tech stack and repo layout") and ADR-005.
"""

from typing import Protocol

from openfactory.domain.llm import LLMReply


class LLMError(Exception):
    """The process failed or timed out; the text says how."""

    def __init__(self, message: str, *, duration_s: float, timeout: bool) -> None:
        super().__init__(message)
        self.duration_s = duration_s
        self.timeout = timeout


class LLMProvider(Protocol):
    def complete(self, prompt: str, schema: dict[str, object]) -> LLMReply:
        """Make one call with `schema` as the JSON Schema of the structured result.

        A reply with no structured result, or one the caller's model would reject, is
        returned, not raised. A failed process raises `LLMError`. Nothing is retried.
        """
        ...
