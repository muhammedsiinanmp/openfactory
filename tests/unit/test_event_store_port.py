"""TASK-002 AC1: the EventStore port (docs/tasks/TASK-002-event-store-sqlite.md)."""

import ast
import inspect
from pathlib import Path
from typing import Protocol

from openfactory.adapters.sqlite_store import SqliteEventStore
from openfactory.ports import event_store
from openfactory.ports.event_store import EventStore


def test_ac1_event_store_is_a_protocol_declaring_append_and_read():
    assert issubclass(EventStore, Protocol)
    assert getattr(EventStore, "_is_protocol", False)
    assert callable(EventStore.append)
    assert callable(EventStore.read)
    assert "stream" in inspect.signature(EventStore.read).parameters


def test_ac1_port_module_imports_no_adapters_app_or_sqlite3():
    tree = ast.parse(Path(event_store.__file__).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(f"{node.module}.{a.name}" for a in node.names)
    forbidden = ("openfactory.adapters", "openfactory.app", "sqlite3")
    bad = {n for n in names if any(n == f or n.startswith(f + ".") for f in forbidden)}
    assert not bad


def test_ac1_sqlite_event_store_provides_append_and_read():
    assert callable(SqliteEventStore.append)
    assert callable(SqliteEventStore.read)
