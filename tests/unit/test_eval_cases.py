"""TASK-113: the eval labels loader (AC2 to AC5)."""

import ast
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from openfactory.app.eval_cases import parse_eval_labels
from openfactory.domain.eval_scoring import EvalLabels

MODULE = Path(__file__).parents[2] / "src" / "openfactory" / "app" / "eval_cases.py"


def test_parse_full_labels_keeps_order_and_kinds() -> None:
    text = """
tasks: [TASK-003, TASK-001]
files: [src/b.py, src/a.py]
tests: [tests/test_b.py::test_y, tests/test_a.py::test_x]
kinds:
  REQ-AUTH-001: behavioral
  REQ-AUTH-002: cosmetic
  REQ-AUTH-003: replacement
"""
    assert parse_eval_labels(text) == EvalLabels(
        tasks=["TASK-003", "TASK-001"],
        files=["src/b.py", "src/a.py"],
        tests=["tests/test_b.py::test_y", "tests/test_a.py::test_x"],
        kinds={
            "REQ-AUTH-001": "behavioral",
            "REQ-AUTH-002": "cosmetic",
            "REQ-AUTH-003": "replacement",
        },
    )


def test_parse_preserves_list_order() -> None:
    labels = parse_eval_labels("tasks: [b, a, c]\nfiles: [z, y]\ntests: []\nkinds: {}\n")
    assert labels.tasks == ["b", "a", "c"]
    assert labels.files == ["z", "y"]


def test_parse_empty_labels() -> None:
    labels = parse_eval_labels("tasks: []\nfiles: []\ntests: []\nkinds: {}\n")
    assert labels == EvalLabels(tasks=[], files=[], tests=[], kinds={})


def test_parse_empty_lists_with_one_kind() -> None:
    labels = parse_eval_labels("tasks: []\nfiles: []\ntests: []\nkinds: {REQ-AUTH-002: cosmetic}\n")
    assert labels == EvalLabels(tasks=[], files=[], tests=[], kinds={"REQ-AUTH-002": "cosmetic"})


@pytest.mark.parametrize(
    "text",
    [
        "tasks: []\nfiles: []\ntests: []\nkinds: {REQ-A-001: minor}\n",
        "tasks: []\nfiles: []\ntests: []\n",  # missing kinds
        "files: []\ntests: []\nkinds: {}\n",  # missing tasks
        "tasks: []\nfiles: []\ntests: []\nkinds: {}\nextra: 1\n",  # extra key
        "tasks: [a\nfiles: ]: :\n  - [",  # not YAML
        "- tasks\n- files\n",  # not a mapping
        "just a string\n",  # not a mapping
    ],
)
def test_parse_rejects_bad_labels(text: str) -> None:
    with pytest.raises((ValueError, ValidationError)):
        parse_eval_labels(text)


def test_eval_cases_module_imports_and_does_no_io() -> None:
    tree = ast.parse(MODULE.read_text())
    allowed = {"openfactory", "pydantic", "yaml"} | set(sys.stdlib_module_names)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
            if node.module.split(".")[0] == "openfactory":
                assert node.module.startswith("openfactory.domain"), node.module
    assert roots <= allowed, roots - allowed
    assert not {"pathlib", "os", "io", "subprocess", "shutil", "sqlite3"} & roots
    calls = {
        n.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "open" not in calls
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not {"read_text", "write_text", "open"} & attrs
