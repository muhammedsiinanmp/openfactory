"""TASK-029 AC1: LLMProvider port (docs/tasks/TASK-029-llm-provider-claude-code-adapter.md)."""

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


def test_ac1_llm_provider_is_a_protocol_with_only_complete():
    from openfactory.ports.llm_provider import LLMProvider

    assert issubclass(LLMProvider, Protocol)
    assert getattr(LLMProvider, "_is_protocol", False)
    public = {
        name
        for name, value in vars(LLMProvider).items()
        if not name.startswith("_") and callable(value)
    }
    assert public == {"complete"}


def test_ac1_port_module_imports_no_adapters_or_app():
    from openfactory.ports import llm_provider

    assert not forbidden_in(llm_provider, ("openfactory.adapters", "openfactory.app"))


def test_ac1_domain_llm_imports_no_ports_adapters_or_app():
    from openfactory.domain import llm

    forbidden = ("openfactory.ports", "openfactory.adapters", "openfactory.app")
    assert not forbidden_in(llm, forbidden)


def test_ac1_adapter_imports_no_app_and_no_anthropic():
    from openfactory.adapters import claude_code_llm

    assert not forbidden_in(claude_code_llm, ("openfactory.app", "anthropic"))
