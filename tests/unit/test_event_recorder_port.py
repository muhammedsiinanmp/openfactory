"""TASK-010 AC1: the EventRecorder port (docs/tasks/TASK-010-event-recorder-sqlite.md)."""

import ast
from pathlib import Path
from typing import Protocol

from openfactory.ports import event_recorder
from openfactory.ports.event_recorder import EventRecorder


def test_ac1_event_recorder_is_a_protocol_whose_only_public_method_is_record():
    assert issubclass(EventRecorder, Protocol)
    assert getattr(EventRecorder, "_is_protocol", False)
    public = {
        name
        for name, value in vars(EventRecorder).items()
        if not name.startswith("_") and callable(value)
    }
    assert public == {"record"}


def test_ac1_port_module_imports_no_adapters_or_app():
    tree = ast.parse(Path(event_recorder.__file__).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(f"{node.module}.{a.name}" for a in node.names)
    forbidden = ("openfactory.adapters", "openfactory.app")
    bad = {n for n in names if any(n == f or n.startswith(f + ".") for f in forbidden)}
    assert not bad
