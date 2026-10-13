"""TASK-045 AC1: WorkspaceManager port (docs/tasks/TASK-045-workspace-manager-git-worktree.md)."""

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


def test_ac1_workspace_manager_is_a_protocol_with_three_methods():
    from openfactory.ports.workspace_manager import WorkspaceManager

    assert issubclass(WorkspaceManager, Protocol)
    assert getattr(WorkspaceManager, "_is_protocol", False)
    public = {
        name
        for name, value in vars(WorkspaceManager).items()
        if not name.startswith("_") and callable(value)
    }
    assert public == {"create", "remove", "remove_worktree"}


def test_ac1_port_module_imports_no_adapters_or_app():
    from openfactory.ports import workspace_manager

    assert not forbidden_in(workspace_manager, ("openfactory.adapters", "openfactory.app"))


def test_ac1_adapter_imports_no_app():
    from openfactory.adapters import git_worktree

    assert not forbidden_in(git_worktree, ("openfactory.app",))
