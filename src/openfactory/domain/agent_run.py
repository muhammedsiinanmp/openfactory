"""Agent run models: what the `AgentExecutor` port takes and returns, and the `Runs`
read of one recorded run.

See "Adapter interface" and "The context pack" under "Execution" in
docs/spec/phase1-spec.md, and ADR-014. `RunRecord` follows the M7 paragraph of
"Domain model and storage" and ADR-020. The fields of `RunResult` other than `summary`
are the fields of `AgentRunFinished`. No link between `exit`, `error` and `summary` is
checked here: the adapter keeps it.
"""

from pydantic import BaseModel, ConfigDict

from openfactory.domain.payloads import RunExit, RunId, RunRole, TaskId

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


class RunRecord(BaseModel):
    """One row of `agent_runs`. No link between `exit` and the figures is checked here:
    the projector keeps it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: RunId
    # None for a planner or classifier run.
    task_id: TaskId | None
    role: RunRole
    # The rest are None until `AgentRunFinished`; tokens and cost also when the runtime
    # reported none.
    exit: RunExit | None
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: float | None
    duration_s: float | None
