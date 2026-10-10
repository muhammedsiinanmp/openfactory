"""Task contract models: what the planner emits and what is stored and executed.

Mirrors "Task contract" in docs/spec/phase1-spec.md. The planner emits a `PlannedTask`;
the orchestrator completes it into a `TaskContract`, so the planner can never set gates
or limits (ADR-008).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
