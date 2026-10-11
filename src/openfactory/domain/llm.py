"""LLM reply: what the `LLMProvider` port returns.

See "Tech stack and repo layout" and the `AgentRunFinished` block under "Event payloads"
in docs/spec/phase1-spec.md, and ADR-005. `structured` is the runtime's structured
result, not yet validated: the caller validates it with its own Pydantic model.
"""

from pydantic import BaseModel, ConfigDict


class LLMReply(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # None when the runtime gave no structured result.
    structured: object | None
    # The next four are None when the runtime reported none.
    model: str | None
    # Every input token: uncached, written to the cache and read from it.
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: float | None
    duration_s: float
