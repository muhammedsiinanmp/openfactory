"""The code against what docs/spec/phase1-spec.md states literally.

Each test parses one part of the spec and compares it with the code that mirrors it.
A part whose code does not exist yet is skipped. If the spec and the code disagree, the
spec wins: fix the code, or take the spec to the next /spec-change.
"""

import ast
import importlib
import re
import sqlite3
from pathlib import Path
from typing import Any

import pytest
import yaml

SPEC = Path(__file__).resolve().parents[2] / "docs" / "spec" / "phase1-spec.md"
SPEC_TEXT = SPEC.read_text()
CODE_BLOCKS = re.findall(r"^```[^\n]*\n(.*?)^```", SPEC_TEXT, flags=re.S | re.M)

M1_TABLES = ("spec_versions", "requirements", "adrs")


def code(module: str, name: str) -> Any:
    """`name` from `module`, or skip the test when the code does not exist yet."""
    try:
        return getattr(importlib.import_module(module), name)
    except (ImportError, AttributeError):
        pytest.skip(f"{module}.{name} does not exist yet")


def code_block(marker: str) -> str:
    """The one spec code block that contains `marker`."""
    blocks = [block for block in CODE_BLOCKS if marker in block]
    assert len(blocks) == 1, f"expected one spec code block containing {marker!r}"
    return blocks[0]


def names_after(label: str) -> list[str]:
    """The backticked names in the first sentence after `label`."""
    match = re.search(re.escape(label) + r"(.*?)\.(?:\s|$)", SPEC_TEXT)
    assert match, f"spec has no sentence starting with {label!r}"
    return re.findall(r"`([^`]+)`", match.group(1))


def table_info(conn: sqlite3.Connection, table: str) -> list[tuple[Any, ...]]:
    """(name, type, notnull, default, primary key position) per column, in order."""
    return [row[1:] for row in conn.execute(f"PRAGMA table_info({table})")]


def test_event_types_match_the_spec_list() -> None:
    event_type = code("openfactory.domain.events", "EventType")
    in_spec = names_after("**Event types in Phase 1:**")
    assert len(in_spec) == len(set(in_spec))
    assert {e.value for e in event_type} == set(in_spec)


@pytest.mark.parametrize("table", M1_TABLES)
def test_projection_table_matches_the_spec_create_table(table: str) -> None:
    projector = code("openfactory.adapters.sqlite_projector", "SqliteProjector")
    from_spec = sqlite3.connect(":memory:")
    from_spec.executescript(code_block("CREATE TABLE spec_versions"))
    from_code = sqlite3.connect(":memory:")
    projector(from_code).create_tables()

    created = table_info(from_code, table)
    if not created:
        pytest.skip(f"the projector does not create the {table} table yet")
    assert created == table_info(from_spec, table)


def test_policy_defaults_match_the_spec_example() -> None:
    policy = code("openfactory.domain.policy", "Policy")
    example = yaml.safe_load(code_block("# policies.yaml"))
    assert policy().model_dump() == example


def test_baseline_forbidden_paths_match_the_spec() -> None:
    baseline = code("openfactory.domain.policy", "BASELINE_FORBIDDEN_PATHS")
    in_spec = names_after("baseline paths are always forbidden:")
    assert list(baseline) == in_spec


def test_task_states_match_the_spec_list() -> None:
    task_state = code("openfactory.domain.states", "TaskState")
    section = SPEC_TEXT.split("## Task state machine", 1)[1].split("\n## ", 1)[0]
    in_spec = re.findall(r"^- `([^`]+)`:", section, flags=re.M)
    assert len(in_spec) == len(set(in_spec))
    assert [s.value for s in task_state] == in_spec


def test_task_transitions_match_the_spec_block() -> None:
    transitions = code("openfactory.domain.states", "TRANSITIONS")
    block = code_block("TRANSITIONS = {")
    in_spec = ast.literal_eval(block.split("TRANSITIONS = ", 1)[1])
    assert {str(k): {str(t) for t in v} for k, v in transitions.items()} == in_spec


def test_task_contract_example_matches_the_spec() -> None:
    contract = code("openfactory.domain.contracts", "TaskContract")
    example = yaml.safe_load(code_block("task_id: AUTH-002"))
    assert contract.model_validate(example).model_dump(mode="json") == example
