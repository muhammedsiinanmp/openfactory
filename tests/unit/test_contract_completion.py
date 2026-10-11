"""TASK-026: completing a planned task into a task contract.

Each test names the acceptance criterion it covers (AC1..AC4 in
docs/tasks/TASK-026-contract-completion-and-policy-hash.md).
"""

import ast
import importlib
from pathlib import Path
from typing import Any

import pytest
import yaml

from openfactory.domain.policy import Policy

DOMAIN = Path(__file__).resolve().parents[2] / "src" / "openfactory" / "domain"
SPEC = Path(__file__).resolve().parents[2] / "docs" / "spec" / "phase1-spec.md"

BASELINE = ["specs/**", ".openfactory/**", ".env", ".env.*"]
GATES = ["path_check", "ruff", "pytest", "gitleaks", "review"]
PLANNED: dict[str, Any] = {
    "task_id": "AUTH-002",
    "objective": "Implement login endpoint using membership number",
    "requirements": ["REQ-AUTH-001", "REQ-AUTH-002"],
    "acceptance_criteria": ["AC-AUTH-001-2", "AC-AUTH-001-1"],
    "depends_on": ["AUTH-001"],
    "components": ["auth"],
    "role": "implementer",
    "allowed_paths": ["tests/auth/**", "app/auth/**"],
    "forbidden_paths": [],
}


def contracts() -> Any:
    # Imported lazily so the failure is the missing function, not the import.
    return importlib.import_module("openfactory.domain.contracts")


def planned(**kw: Any) -> Any:
    return contracts().PlannedTask.model_validate({**PLANNED, **kw})


def complete(task: Any, policy: Policy) -> Any:
    return contracts().complete_contract(task, policy)


def test_ac1_default_policy_gives_the_baseline() -> None:
    assert complete(planned(), Policy()).forbidden_paths == BASELINE


def test_ac1_baseline_then_policy_then_planner_in_order() -> None:
    policy = Policy(forbidden_paths=["secrets/**", "infra/**"])
    task = planned(forbidden_paths=["migrations/**", "docs/private/**"])
    expected = [*BASELINE, "secrets/**", "infra/**", "migrations/**", "docs/private/**"]
    assert complete(task, policy).forbidden_paths == expected


def test_ac1_duplicates_are_kept_once_at_their_first_position() -> None:
    policy = Policy(forbidden_paths=["secrets/**", ".env"])
    task = planned(forbidden_paths=["specs/**", "secrets/**", "migrations/**", "migrations/**"])
    expected = [*BASELINE, "secrets/**", "migrations/**"]
    assert complete(task, policy).forbidden_paths == expected


@pytest.mark.parametrize(
    "policy",
    [
        Policy(),
        Policy(
            forbidden_paths=["x/**"],
            protected_branches=["dev"],
            max_runtime_s=60,
            max_attempts=5,
            max_cost_usd=9.0,
        ),
    ],
)
def test_ac2_required_gates_are_fixed(policy: Policy) -> None:
    assert complete(planned(), policy).required_gates == GATES


def test_ac2_required_gates_constant_holds_the_five_names() -> None:
    assert list(contracts().REQUIRED_GATES) == GATES


def test_ac3_default_policy_limits() -> None:
    limits = complete(planned(), Policy()).limits
    assert limits == contracts().Limits(max_runtime_s=1200, max_attempts=2, max_cost_usd=1.50)


def test_ac3_limits_come_from_the_policy_fields() -> None:
    policy = Policy(max_runtime_s=600, max_attempts=3, max_cost_usd=0.75)
    limits = complete(planned(), policy).limits
    assert (limits.max_runtime_s, limits.max_attempts, limits.max_cost_usd) == (600, 3, 0.75)


def test_ac4_planned_fields_are_copied_in_order() -> None:
    task = planned()
    contract = complete(task, Policy())
    assert isinstance(contract, contracts().TaskContract)
    for name in (
        "task_id",
        "objective",
        "requirements",
        "acceptance_criteria",
        "depends_on",
        "components",
        "role",
        "allowed_paths",
    ):
        assert getattr(contract, name) == getattr(task, name)


def test_ac4_planned_example_completes_to_the_spec_contract_example() -> None:
    spec_text = SPEC.read_text()
    block = next(b for b in spec_text.split("```") if "task_id: AUTH-002" in b)
    example = yaml.safe_load(block.split("\n", 1)[1])
    task = contracts().PlannedTask.model_validate(
        {k: v for k, v in example.items() if k not in ("required_gates", "limits")}
    )
    contract = complete(task, Policy())
    assert contract.model_dump(mode="json") == example


def test_ac4_inputs_are_unchanged() -> None:
    task = planned(forbidden_paths=["m/**"])
    policy = Policy(forbidden_paths=["s/**"])
    task_before, policy_before = task.model_dump(), policy.model_dump()
    complete(task, policy)
    assert task.model_dump() == task_before
    assert policy.model_dump() == policy_before


@pytest.mark.parametrize("module", ["contracts", "spec_hash"])
def test_ac4_domain_modules_import_no_outer_layer(module: str) -> None:
    tree = ast.parse((DOMAIN / f"{module}.py").read_text())
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    for name in imported:
        for layer in ("adapters", "app", "ports"):
            assert not name.startswith(f"openfactory.{layer}")
