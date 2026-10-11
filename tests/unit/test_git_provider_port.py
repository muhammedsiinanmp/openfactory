"""TASK-030 AC1: GitProvider port (docs/tasks/TASK-030-git-provider-git-cli.md)."""

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


def test_ac1_git_provider_is_a_protocol_with_only_tracked_files():
    from openfactory.ports.git_provider import GitProvider

    assert issubclass(GitProvider, Protocol)
    assert getattr(GitProvider, "_is_protocol", False)
    public = {
        name
        for name, value in vars(GitProvider).items()
        if not name.startswith("_") and callable(value)
    }
    assert public == {"tracked_files"}


def test_ac1_port_module_imports_no_adapters_or_app():
    from openfactory.ports import git_provider

    assert not forbidden_in(git_provider, ("openfactory.adapters", "openfactory.app"))


def test_ac1_adapter_imports_no_app():
    from openfactory.adapters import git_cli

    assert not forbidden_in(git_cli, ("openfactory.app",))
