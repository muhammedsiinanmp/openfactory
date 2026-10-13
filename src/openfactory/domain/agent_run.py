"""Agent run result and context pack: what the `AgentExecutor` port takes and returns.

See "Adapter interface" and "The context pack" under "Execution" in
docs/spec/phase1-spec.md, and ADR-014. The fields of `RunResult` other than `summary`
are the fields of `AgentRunFinished`. No link between `exit`, `error` and `summary` is
checked here: the adapter keeps it.
"""

from pydantic import BaseModel, ConfigDict

from openfactory.domain.payloads import RunExit

# One prompt text.
ContextPack = str


class RunResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exit: RunExit
    # The next four are None when the runtime reported none.
    model: str | None
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: float | None
    duration_s: float
    # None when the run succeeded; the adapter keeps that, nothing here checks it.
    error: str | None
    # The agent's final message; empty when `exit` is `error` or `timeout`.
    summary: str
