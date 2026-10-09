"""SpecVersions port: read-only view of the spec version projection.

See docs/spec/phase1-spec.md ("Domain model and storage", "Ids"; "Spec input format",
"Spec versions") and ADR-001.
"""

from typing import Protocol

from openfactory.domain.spec_versions import SpecVersionRef


class SpecVersions(Protocol):
    def latest_approved(self) -> SpecVersionRef | None:
        """The approved version with the highest number in its id, or None."""
        ...

    def current_draft(self) -> SpecVersionRef | None:
        """The draft version, or None. At most one draft exists at a time."""
        ...

    def next_id(self) -> str:
        """The id after the highest one in use, draft or approved; `sv_01` when there is none.

        While a draft exists the caller keeps the draft's id and does not use this one.
        """
        ...
