"""TASK-046 AC1: RunFiles port (docs/tasks/TASK-046-run-files-port-filesystem-adapter.md)."""

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


def test_ac1_run_files_is_a_protocol_with_one_method():
    from openfactory.ports.run_files import RunFiles

    assert issubclass(RunFiles, Protocol)
    assert getattr(RunFiles, "_is_protocol", False)
    public = {
        name
        for name, value in vars(RunFiles).items()
        if not name.startswith("_") and callable(value)
    }
    assert public == {"write"}


def test_ac1_port_module_imports_no_adapters_or_app():
    from openfactory.ports import run_files

    assert not forbidden_in(run_files, ("openfactory.adapters", "openfactory.app"))


def test_ac1_adapter_imports_no_app():
    from openfactory.adapters import filesystem_run_files

    assert not forbidden_in(filesystem_run_files, ("openfactory.app",))
