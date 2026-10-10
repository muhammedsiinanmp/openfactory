"""TASK-020: the task contract models.

Each test names the acceptance criterion it covers (AC1..AC5 in
docs/tasks/TASK-020-task-contract-and-states.md).
"""

import ast
import importlib
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

DOMAIN = Path(__file__).resolve().parents[2] / "src" / "openfactory" / "domain"

PLANNED: dict[str, Any] = {
    "task_id": "AUTH-002",
    "objective": "Implement login endpoint using membership number",
    "requirements": ["REQ-AUTH-001"],
    "acceptance_criteria": ["AC-AUTH-001-1", "AC-AUTH-001-2"],
    "depends_on": ["AUTH-001"],
    "components": ["auth"],
    "role": "implementer",
    "allowed_paths": ["app/auth/**", "tests/auth/**"],
    "forbidden_paths": ["specs/**", ".openfactory/**", ".env", ".env.*"],
}
EXAMPLE: dict[str, Any] = {
    **PLANNED,
    "required_gates": ["path_check", "ruff", "pytest", "gitleaks", "review"],
    "limits": {"max_runtime_s": 1200, "max_attempts": 2, "max_cost_usd": 1.5},
}
LIMITS = EXAMPLE["limits"]


def contracts() -> Any:
    return importlib.import_module("openfactory.domain.contracts")


def test_ac1_contract_validates_from_the_example() -> None:
    mod = contracts()
    contract = mod.TaskContract.model_validate(EXAMPLE)
    for name, value in PLANNED.items():
        assert getattr(contract, name) == value
    assert contract.required_gates == EXAMPLE["required_gates"]
    assert isinstance(contract.limits, mod.Limits)
    assert contract.limits.max_runtime_s == 1200
    assert contract.limits.max_attempts == 2
    assert contract.limits.max_cost_usd == 1.5


def test_ac1_contract_dumps_back_to_the_example() -> None:
    contract = contracts().TaskContract.model_validate(EXAMPLE)
    assert contract.model_dump(mode="json") == EXAMPLE


def test_ac1_contract_round_trips_through_json() -> None:
    cls = contracts().TaskContract
    contract = cls.model_validate(EXAMPLE)
    assert cls.model_validate_json(contract.model_dump_json()) == contract


def test_ac1_task_contract_is_a_planned_task() -> None:
    mod = contracts()
    assert issubclass(mod.TaskContract, mod.PlannedTask)


@pytest.mark.parametrize("module", ["contracts", "states"])
def test_ac1_domain_modules_import_no_outer_layer(module: str) -> None:
    tree = ast.parse((DOMAIN / f"{module}.py").read_text())
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    outer = ("adapters", "app", "ports")
    for name in imported:
        assert not any(name.startswith(f"openfactory.{layer}") for layer in outer), name


def test_ac2_planned_task_validates_with_defaults() -> None:
    cls = contracts().PlannedTask
    assert cls.model_validate(PLANNED).task_id == "AUTH-002"
    minimal = {k: v for k, v in PLANNED.items() if k not in ("depends_on", "forbidden_paths")}
    task = cls.model_validate(minimal)
    assert task.depends_on == []
    assert task.forbidden_paths == []


@pytest.mark.parametrize(
    "field",
    [
        "task_id",
        "objective",
        "requirements",
        "acceptance_criteria",
        "components",
        "role",
        "allowed_paths",
    ],
)
def test_ac2_planned_task_requires_field(field: str) -> None:
    data = {k: v for k, v in PLANNED.items() if k != field}
    with pytest.raises(ValidationError):
        contracts().PlannedTask.model_validate(data)


@pytest.mark.parametrize("field", ["requirements", "acceptance_criteria", "allowed_paths"])
def test_ac2_planned_task_rejects_empty_list(field: str) -> None:
    with pytest.raises(ValidationError):
        contracts().PlannedTask.model_validate({**PLANNED, field: []})


def test_ac2_planned_task_accepts_empty_components() -> None:
    task = contracts().PlannedTask.model_validate({**PLANNED, "components": []})
    assert task.components == []


@pytest.mark.parametrize("model", ["PlannedTask", "TaskContract"])
@pytest.mark.parametrize("task_id", ["AUTH-002", "A-000"])
def test_ac3_task_id_accepts(model: str, task_id: str) -> None:
    cls = getattr(contracts(), model)
    data = EXAMPLE if model == "TaskContract" else PLANNED
    assert cls.model_validate({**data, "task_id": task_id}).task_id == task_id


@pytest.mark.parametrize("model", ["PlannedTask", "TaskContract"])
@pytest.mark.parametrize("task_id", ["auth-002", "AUTH-02", "AUTH-0020", "AUTH002", ""])
def test_ac3_task_id_rejects(model: str, task_id: str) -> None:
    cls = getattr(contracts(), model)
    data = EXAMPLE if model == "TaskContract" else PLANNED
    with pytest.raises(ValidationError):
        cls.model_validate({**data, "task_id": task_id})


@pytest.mark.parametrize("model", ["PlannedTask", "TaskContract"])
def test_ac3_role_accepts_implementer(model: str) -> None:
    cls = getattr(contracts(), model)
    data = EXAMPLE if model == "TaskContract" else PLANNED
    assert cls.model_validate(data).role == "implementer"


@pytest.mark.parametrize("model", ["PlannedTask", "TaskContract"])
@pytest.mark.parametrize("role", ["reviewer", "planner"])
def test_ac3_role_rejects_others(model: str, role: str) -> None:
    cls = getattr(contracts(), model)
    data = EXAMPLE if model == "TaskContract" else PLANNED
    with pytest.raises(ValidationError):
        cls.model_validate({**data, "role": role})


@pytest.mark.parametrize(
    "extra",
    [
        {"required_gates": EXAMPLE["required_gates"]},
        {"limits": LIMITS},
        {"priority": "high"},
    ],
)
def test_ac4_planned_task_rejects_extra_keys(extra: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        contracts().PlannedTask.model_validate({**PLANNED, **extra})


def test_ac4_task_contract_rejects_unknown_key() -> None:
    with pytest.raises(ValidationError):
        contracts().TaskContract.model_validate({**EXAMPLE, "priority": "high"})


@pytest.mark.parametrize("field", ["required_gates", "limits"])
def test_ac4_task_contract_requires_gates_and_limits(field: str) -> None:
    data = {k: v for k, v in EXAMPLE.items() if k != field}
    with pytest.raises(ValidationError):
        contracts().TaskContract.model_validate(data)


def test_ac5_limits_validates() -> None:
    limits = contracts().Limits.model_validate(LIMITS)
    assert (limits.max_runtime_s, limits.max_attempts, limits.max_cost_usd) == (1200, 2, 1.5)


@pytest.mark.parametrize("field", list(LIMITS))
@pytest.mark.parametrize("value", [0, -1])
def test_ac5_limits_must_be_positive(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        contracts().Limits.model_validate({**LIMITS, field: value})


@pytest.mark.parametrize("field", list(LIMITS))
def test_ac5_limits_require_every_field(field: str) -> None:
    data = {k: v for k, v in LIMITS.items() if k != field}
    with pytest.raises(ValidationError):
        contracts().Limits.model_validate(data)


def test_ac5_limits_reject_unknown_key() -> None:
    with pytest.raises(ValidationError):
        contracts().Limits.model_validate({**LIMITS, "max_tokens": 5})


def test_ac5_required_gates_keep_order() -> None:
    gates = ["review", "gitleaks", "pytest", "ruff", "path_check"]
    contract = contracts().TaskContract.model_validate({**EXAMPLE, "required_gates": gates})
    assert contract.required_gates == gates


def test_ac5_required_gates_reject_unknown_name() -> None:
    with pytest.raises(ValidationError):
        contracts().TaskContract.model_validate({**EXAMPLE, "required_gates": ["semgrep"]})
