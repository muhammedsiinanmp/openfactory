"""Policy model: the contents of `specs/policies.yaml`, and the baseline forbidden paths.

Mirrors "Policies" in docs/spec/phase1-spec.md. The policy is not part of the spec set
and is not covered by a spec version's hash.
"""

from pydantic import BaseModel, ConfigDict, Field

# Always forbidden, whatever the policy file says; `Policy.forbidden_paths` adds to these.
BASELINE_FORBIDDEN_PATHS: tuple[str, ...] = ("specs/**", ".openfactory/**", ".env", ".env.*")


class Policy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    protected_branches: list[str] = ["main", "master"]
    forbidden_paths: list[str] = []
    max_attempts: int = Field(default=2, gt=0)
    max_runtime_s: int = Field(default=1200, gt=0)
    max_cost_usd: float = Field(default=1.50, gt=0)
