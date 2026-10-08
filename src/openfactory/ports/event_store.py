"""EventStore port: the append-only event log.

See docs/spec/phase1-spec.md ("Domain model and storage"). The port has no update or
delete method; that is how append-only is enforced.
"""

from typing import Protocol

from openfactory.domain.events import Event, StoredEvent


class EventConflictError(Exception):
    """An `event_id` was appended again with different content."""


class EventStore(Protocol):
    def append(self, event: Event) -> StoredEvent:
        """Store a new event and return it with its assigned `seq`.

        `event_id` is the idempotency key: appending the same event again writes nothing
        and returns the stored event. The same `event_id` with different content raises
        `EventConflictError`.
        """
        ...

    def read(self, stream: str | None = None) -> list[StoredEvent]:
        """Return stored events in ascending `seq`, optionally only those of one stream."""
        ...
