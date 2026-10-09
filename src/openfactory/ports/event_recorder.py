"""EventRecorder port: the one call a use case makes to record an event.

See docs/spec/phase1-spec.md ("Domain model and storage", "Projection rules") and ADR-001.
"""

from typing import Protocol

from openfactory.domain.events import Event, StoredEvent


class EventRecorder(Protocol):
    def record(self, event: Event) -> StoredEvent:
        """Store the event and apply it to the projections as one unit.

        A repeated `event_id` behaves like `EventStore.append`: the same content returns
        the stored event without applying it again, and different content raises
        `EventConflictError`.
        """
        ...
