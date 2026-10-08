"""Canonical JSON and content hashes of spec items.

Implements "Hashing" under "Spec input format" in docs/spec/phase1-spec.md. The
parsed models are hashed, not the files, so key order, comments and omitted
defaults never change a hash.
"""

import hashlib
import json
from typing import Any

from openfactory.domain.models import AcceptanceCriterion, Adr, Requirement, SpecSet

SpecItem = AcceptanceCriterion | Requirement | Adr | SpecSet


def _dumps(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sort_key(item: Any) -> Any:
    # Items with an id sort by id, then by their own canonical JSON, so two items
    # sharing an id still have one order whatever the order in the files.
    if isinstance(item, dict):
        return (item["id"], _dumps(item))
    return item


def _ordered(data: Any) -> Any:
    """Return `data` with every list sorted, innermost first."""
    if isinstance(data, dict):
        return {key: _ordered(value) for key, value in data.items()}
    if isinstance(data, list):
        return sorted((_ordered(value) for value in data), key=_sort_key)
    return data


def canonical_json(item: SpecItem) -> bytes:
    return _dumps(_ordered(item.model_dump(mode="json"))).encode("utf-8")


def content_hash(item: SpecItem) -> str:
    """SHA-256 of the canonical JSON, as 64 lowercase hex characters."""
    return hashlib.sha256(canonical_json(item)).hexdigest()
