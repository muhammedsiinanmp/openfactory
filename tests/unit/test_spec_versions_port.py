"""TASK-011 AC1: SpecVersions port and SpecVersionRef (docs/tasks/TASK-011-*.md)."""

import ast
from pathlib import Path
from typing import Protocol

import pytest
from pydantic import ValidationError

from openfactory.adapters import sqlite_spec_versions
from openfactory.domain import spec_versions as domain_spec_versions
from openfactory.domain.spec_versions import SpecVersionRef
from openfactory.ports import spec_versions as port_module
from openfactory.ports.spec_versions import SpecVersions

HASH = "a" * 64


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


def test_ac1_spec_versions_is_a_protocol_with_the_three_methods():
    assert issubclass(SpecVersions, Protocol)
    assert getattr(SpecVersions, "_is_protocol", False)
    public = {
        name
        for name, value in vars(SpecVersions).items()
        if not name.startswith("_") and callable(value)
    }
    assert public == {"latest_approved", "current_draft", "next_id"}


def test_ac1_port_module_imports_no_adapters_or_app():
    assert not forbidden_in(port_module, ("openfactory.adapters", "openfactory.app"))


def test_ac1_spec_version_ref_is_built_from_id_and_hash_and_is_frozen():
    ref = SpecVersionRef(id="sv_01", hash=HASH)
    assert (ref.id, ref.hash) == ("sv_01", HASH)
    with pytest.raises(ValidationError):
        ref.id = "sv_02"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"id": "sv_01", "hash": HASH, "status": "draft"},
        {"id": "v1", "hash": HASH},
        {"id": "sv_01", "hash": "A" * 64},
        {"id": "sv_01", "hash": "a" * 63},
    ],
    ids=["unknown-field", "bad-id", "uppercase-hash", "short-hash"],
)
def test_ac1_spec_version_ref_rejects_what_we_constrain(kwargs):
    with pytest.raises(ValidationError):
        SpecVersionRef(**kwargs)


def test_ac1_domain_module_imports_no_adapters_app_or_ports():
    forbidden = ("openfactory.adapters", "openfactory.app", "openfactory.ports")
    assert not forbidden_in(domain_spec_versions, forbidden)


def test_ac1_adapter_module_imports_no_app():
    assert not forbidden_in(sqlite_spec_versions, ("openfactory.app",))
