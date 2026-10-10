"""List events use case: read the stored events for the `events` command.

See docs/spec/phase1-spec.md ("CLI commands": "Output"). The log is read through the
`EventStore` port (ADR-001). The use case returns data and prints nothing; the command
renders the lines.
"""

from openfactory.domain.events import StoredEvent
from openfactory.ports.event_store import EventStore


def list_events(store: EventStore, stream: str | None = None) -> list[StoredEvent]:
    """Return stored events in ascending `seq`, optionally only those of one stream."""
    return store.read(stream)
