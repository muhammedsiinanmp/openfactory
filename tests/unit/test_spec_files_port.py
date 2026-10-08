"""TASK-006 AC1: the SpecFiles port (docs/tasks/TASK-006-spec-files-port.md)."""

import ast
from pathlib import Path
from typing import Protocol

from openfactory.adapters.filesystem_spec_files import FilesystemSpecFiles
from openfactory.ports import spec_files
from openfactory.ports.spec_files import SpecFiles


def test_ac1_spec_files_is_a_protocol_declaring_read_and_list_adrs():
    assert issubclass(SpecFiles, Protocol)
    assert getattr(SpecFiles, "_is_protocol", False)
    assert callable(SpecFiles.read)
    assert callable(SpecFiles.list_adrs)


def test_ac1_port_module_imports_no_adapters_or_app():
    tree = ast.parse(Path(spec_files.__file__).read_text(encoding="utf-8"))
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


def test_ac1_filesystem_spec_files_provides_read_and_list_adrs():
    assert callable(FilesystemSpecFiles.read)
    assert callable(FilesystemSpecFiles.list_adrs)
