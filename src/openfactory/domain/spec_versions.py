"""Spec version reference: the id and content hash of one spec version.

See "Spec versions" under "Spec input format" in docs/spec/phase1-spec.md. This is what
the `SpecVersions` port returns for the latest approved version and the current draft.
"""

from pydantic import BaseModel, ConfigDict

from openfactory.domain.payloads import ContentHash, SpecVersionId


class SpecVersionRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: SpecVersionId
    hash: ContentHash
