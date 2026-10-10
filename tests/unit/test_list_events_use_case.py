"""TASK-018 AC6: the list_events use case (see docs/tasks/TASK-018-cli-events.md)."""

import ast
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from openfactory.domain.events import Event, EventType, StoredEvent


def stored(seq: int, stream: str) -> StoredEvent:
    return StoredEvent(
        seq=seq,
        event_id=uuid4(),
        stream=stream,
        type=EventType.SpecImported,
        payload={},
        actor="orchestrator",
        created_at=datetime.now(UTC),
    )


class FakeStore:
    def __init__(self, events: list[StoredEvent]) -> None:
        self.events = events
        self.read_calls: list[str | None] = []
        self.append_calls: list[Event] = []

    def append(self, event: Event) -> StoredEvent:
        self.append_calls.append(event)
        raise AssertionError("append must not be called")

    def read(self, stream: str | None = None) -> list[StoredEvent]:
        self.read_calls.append(stream)
        return [e for e in self.events if stream is None or e.stream == stream]


def test_ac6_returns_what_read_returns_and_passes_the_stream() -> None:
    from openfactory.app.list_events import list_events

    events = [stored(1, "spec:sv_01"), stored(2, "spec:sv_02"), stored(3, "spec:sv_01")]
    store = FakeStore(events)

    assert list_events(store) == events
    assert list_events(store, "spec:sv_01") == [events[0], events[2]]
    assert store.read_calls == [None, "spec:sv_01"]
    assert store.append_calls == []


def test_ac6_module_imports_nothing_from_adapters() -> None:
    from openfactory.app import list_events

    tree = ast.parse(Path(list_events.__file__).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
    assert not {n for n in names if n.startswith("openfactory.adapters")}
