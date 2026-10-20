"""TASK-025 AC1: Plans port (docs/tasks/TASK-025-plans-port-sqlite.md)."""

import ast
from pathlib import Path
from typing import Protocol


def imported_modules(module):
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


def forbidden_in(module, forbidden):
    return {
        n
        for n in imported_modules(module)
        if any(n == f or n.startswith(f + ".") for f in forbidden)
    }


def test_ac1_plans_is_a_protocol_with_exactly_the_five_reads():
    from openfactory.ports.plans import Plans

    assert issubclass(Plans, Protocol)
    assert getattr(Plans, "_is_protocol", False)
    public = {
        name for name, value in vars(Plans).items() if not name.startswith("_") and callable(value)
    }
    assert public == {
        "current_draft",
        "approved",
        "next_id",
        "tasks",
        "live_tasks_referencing",
        "latest_commit",
        "last_gate_result",
    }


def test_ac1_port_module_imports_no_adapters_or_app():
    from openfactory.ports import plans as port_module

    assert not forbidden_in(port_module, ("openfactory.adapters", "openfactory.app"))


def test_ac1_domain_module_imports_no_ports_adapters_or_app():
    from openfactory.domain import plans as domain_module

    forbidden = ("openfactory.ports", "openfactory.adapters", "openfactory.app")
    assert not forbidden_in(domain_module, forbidden)


def test_ac1_adapter_module_imports_no_app():
    from openfactory.adapters import sqlite_plans

    assert not forbidden_in(sqlite_plans, ("openfactory.app",))


def test_ac1_gate_result_ref_is_frozen_strict_and_gate_named():
    import pytest
    from pydantic import ValidationError

    from openfactory.domain.plans import GateResultRef

    ref = GateResultRef(gate="ruff", passed=True)
    assert set(GateResultRef.model_fields) == {"gate", "passed"}
    with pytest.raises(ValidationError):
        ref.passed = False
    with pytest.raises(ValidationError):
        GateResultRef(gate="ruff", passed=True, output_path="x")
    with pytest.raises(ValidationError):
        GateResultRef(gate="mypy", passed=True)
