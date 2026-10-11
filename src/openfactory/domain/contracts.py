"""Task contract models: what the planner emits and what is stored and executed.

Mirrors "Task contract" in docs/spec/phase1-spec.md. The planner emits a `PlannedTask`;
the orchestrator completes it into a `TaskContract` with `complete_contract`, so the
planner can never set gates or limits (ADR-008).
"""

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from openfactory.domain.policy import BASELINE_FORBIDDEN_PATHS, Policy

# The gates of every contract, in the spec's order; neither the planner nor the policy sets them.
REQUIRED_GATES: Final = ("path_check", "ruff", "pytest", "gitleaks", "review")


class PlannedTask(BaseModel):
    """What the planner emits."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str = Field(pattern=r"^[A-Z]+-\d{3}$")
    objective: str
    requirements: list[str] = Field(min_length=1)
    acceptance_criteria: list[str] = Field(min_length=1)
    depends_on: list[str] = []
    components: list[str]
    role: Literal["implementer"]
    allowed_paths: list[str] = Field(min_length=1)
    forbidden_paths: list[str] = []


class Limits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_runtime_s: int = Field(gt=0)
    max_attempts: int = Field(gt=0)
    max_cost_usd: float = Field(gt=0)


class TaskContract(PlannedTask):
    """What is stored and executed."""

    required_gates: list[Literal["path_check", "ruff", "pytest", "gitleaks", "review"]]
    limits: Limits


def complete_contract(planned: PlannedTask, policy: Policy) -> TaskContract:
    """Complete a planned task: merged forbidden paths, the fixed gates, the policy's limits."""
    # Baseline, then the policy's list, then the planner's; each path at its first position.
    forbidden = dict.fromkeys(
        [*BASELINE_FORBIDDEN_PATHS, *policy.forbidden_paths, *planned.forbidden_paths]
    )
    return TaskContract(
        task_id=planned.task_id,
        objective=planned.objective,
        requirements=list(planned.requirements),
        acceptance_criteria=list(planned.acceptance_criteria),
        depends_on=list(planned.depends_on),
        components=list(planned.components),
        role=planned.role,
        allowed_paths=list(planned.allowed_paths),
        forbidden_paths=list(forbidden),
        required_gates=list(REQUIRED_GATES),
        limits=Limits(
            max_runtime_s=policy.max_runtime_s,
            max_attempts=policy.max_attempts,
            max_cost_usd=policy.max_cost_usd,
        ),
    )
