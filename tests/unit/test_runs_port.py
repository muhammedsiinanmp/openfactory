"""TASK-024 AC1: Runs port (docs/tasks/TASK-024-runs-port-and-stored-spec-set.md)."""

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


def test_ac1_runs_is_a_protocol_with_only_next_id():
    from openfactory.ports.runs import Runs

    assert issubclass(Runs, Protocol)
    assert getattr(Runs, "_is_protocol", False)
    public = {
        name for name, value in vars(Runs).items() if not name.startswith("_") and callable(value)
    }
    assert public == {"next_id", "unfinished_run"}


def test_ac1_port_module_imports_no_adapters_or_app():
    from openfactory.ports import runs as port_module

    assert not forbidden_in(port_module, ("openfactory.adapters", "openfactory.app"))


def test_ac1_adapter_module_imports_no_app():
    from openfactory.adapters import sqlite_runs

    assert not forbidden_in(sqlite_runs, ("openfactory.app",))
