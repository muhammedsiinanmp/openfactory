"""TASK-081 AC1: Traces port (docs/tasks/TASK-081-traces-port.md).

The port grows by one read per M5 task, so this test checks that `untested_requirements`
is present and does not assert an exact method set (Decision 1).
"""

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


def test_ac1_traces_is_a_protocol_with_untested_requirements():
    from openfactory.ports.traces import Traces

    assert issubclass(Traces, Protocol)
    assert getattr(Traces, "_is_protocol", False)
    assert callable(vars(Traces).get("untested_requirements"))


def test_ac1_port_module_imports_no_adapters_or_app():
    from openfactory.ports import traces as port_module

    assert not forbidden_in(port_module, ("openfactory.adapters", "openfactory.app"))


def test_ac1_adapter_module_imports_no_app():
    from openfactory.adapters import sqlite_traces

    assert not forbidden_in(sqlite_traces, ("openfactory.app",))


def test_ac1_adapter_ends_with_the_type_checking_assertion():
    from openfactory.adapters import sqlite_traces

    tree = ast.parse(Path(sqlite_traces.__file__).read_text(encoding="utf-8"))
    last = tree.body[-1]
    assert isinstance(last, ast.If)
    assert ast.unparse(last.test) == "TYPE_CHECKING"
    assert ast.unparse(last.body[0]) == "_: type[Traces] = SqliteTraces"


def test_task083_ac1_traces_has_requirement_trace():
    from openfactory.ports.traces import Traces

    assert callable(vars(Traces).get("requirement_trace"))


def test_task083_ac1_domain_traces_imports_no_outer_layer():
    from openfactory.domain import traces as domain_traces

    forbidden = ("openfactory.ports", "openfactory.adapters", "openfactory.app")
    assert not forbidden_in(domain_traces, forbidden)


def test_task085_ac1_traces_has_file_trace():
    from openfactory.ports.traces import Traces

    assert callable(vars(Traces).get("file_trace"))


def test_task085_ac1_domain_traces_still_imports_no_outer_layer():
    from openfactory.domain import traces as domain_traces

    forbidden = ("openfactory.ports", "openfactory.adapters", "openfactory.app")
    assert not forbidden_in(domain_traces, forbidden)
