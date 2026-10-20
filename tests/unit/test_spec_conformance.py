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
M2_TABLES = ("plans", "tasks", "task_deps", "agent_runs")
M3_TABLES = ("gate_results", "commits")


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


@pytest.mark.parametrize("table", M1_TABLES + M2_TABLES + M3_TABLES)
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


SPEC_PAYLOAD_ENTRIES = re.findall(
    r"^(\w+)\n(?=  )", code_block("PlanCreated\n  plan_id"), flags=re.M
)


@pytest.mark.parametrize("event", SPEC_PAYLOAD_ENTRIES)
def test_payload_fields_match_the_spec_block(event: str) -> None:
    payload_models = code("openfactory.domain.payloads", "PAYLOAD_MODELS")
    events = code("openfactory.domain.events", "EventType")
    if events(event) not in payload_models:
        pytest.skip(f"PAYLOAD_MODELS has no entry for {event} yet")
    model = payload_models[events(event)]
    block = code_block("PlanCreated\n  plan_id")
    section = re.search(rf"^{event}\n((?:  .*\n)+)", block, flags=re.M)
    assert section, f"the spec block has no {event} entry"
    in_spec = re.findall(r"^  (\w+):", section.group(1), flags=re.M)
    dumped = [f.alias or key for key, f in model.model_fields.items()]
    assert dumped == in_spec


def test_required_gates_match_the_spec_bullet() -> None:
    gates = code("openfactory.domain.contracts", "REQUIRED_GATES")
    match = re.search(r"sets `required_gates` to `\[(.*?)\]`", SPEC_TEXT)
    assert match, "spec has no bullet setting `required_gates`"
    assert list(gates) == match.group(1).split(", ")


def test_plan_rules_match_the_spec_table() -> None:
    plan_rule = code("openfactory.domain.plan_checks", "PlanRule")
    section = SPEC_TEXT.split("**Plan checks:**", 1)[1].split("\n## ", 1)[0]
    in_spec = re.findall(r"^\| `([^`]+)` \|", section, flags=re.M)
    assert len(in_spec) == len(set(in_spec))
    assert {rule.value for rule in plan_rule} == set(in_spec)


def test_validation_rules_match_the_spec_sentence() -> None:
    rule = code("openfactory.domain.spec_validation", "Rule")
    in_spec = names_after("The rule names are")
    assert len(in_spec) == 7
    assert {r.value for r in rule} == set(in_spec)


def test_path_pattern_statement_in_the_planner_prompt_matches_the_spec() -> None:
    """TASK-039 AC6: the opening sentence and six bullets are in the prompt word for word."""
    from openfactory.app.planner_prompt import build_planner_prompt
    from openfactory.domain.models import SpecSet
    from openfactory.domain.policy import Policy

    section = SPEC_TEXT.split("**Path patterns:** ", 1)[1].split("\n\n**Planning:**", 1)[0]
    opening, _, bullets = section.partition("\n\n")
    lines = [opening, *[b[2:] for b in bullets.splitlines() if b.startswith("- ")]]
    assert len(lines) == 7
    prompt = build_planner_prompt(SpecSet(components=["auth"], requirements=[]), Policy(), [])
    for line in lines:
        assert line in prompt


def test_run_result_fields_match_the_spec_class_block() -> None:
    """TASK-047 AC2: the field names of RunResult, in order, are the spec block's."""
    from openfactory.domain.agent_run import RunResult

    block = code_block("class RunResult(BaseModel)").split("class RunResult(BaseModel):", 1)[1]
    in_spec = re.findall(r"^    (\w+):", block, flags=re.M)
    assert len(in_spec) == 8
    assert list(RunResult.model_fields) == in_spec


def test_path_pattern_statement_in_the_context_pack_matches_the_spec() -> None:
    """TASK-050 AC6: the opening sentence and six bullets are in the pack word for word."""
    from openfactory.app.context_pack import build_context_pack
    from openfactory.domain.contracts import REQUIRED_GATES, Limits, TaskContract
    from openfactory.domain.models import SpecSet

    section = SPEC_TEXT.split("**Path patterns:** ", 1)[1].split("\n\n**Planning:**", 1)[0]
    opening, _, bullets = section.partition("\n\n")
    lines = [opening, *[b[2:] for b in bullets.splitlines() if b.startswith("- ")]]
    assert len(lines) == 7
    contract = TaskContract(
        task_id="AUTH-002",
        objective="x",
        requirements=["REQ-AUTH-001"],
        acceptance_criteria=["AC-AUTH-001-1"],
        components=["auth"],
        role="implementer",
        allowed_paths=["app/**"],
        required_gates=list(REQUIRED_GATES),
        limits=Limits(max_runtime_s=1, max_attempts=1, max_cost_usd=1),
    )
    pack = build_context_pack(contract, SpecSet(components=["auth"], requirements=[]), [])
    for line in lines:
        assert line in pack


def test_commit_message_matches_the_spec_example_block() -> None:
    """TASK-051 AC5: the message built for the example's values equals the spec block."""
    build = code("openfactory.domain.commit_message", "build_commit_message")
    from openfactory.domain.contracts import REQUIRED_GATES, Limits, TaskContract

    block = code_block("<the run's summary>")
    contract = TaskContract(
        task_id="AUTH-002",
        objective="Implement login endpoint using membership number",
        requirements=["REQ-AUTH-001"],
        acceptance_criteria=["AC-AUTH-001-1", "AC-AUTH-001-2"],
        components=["auth"],
        role="implementer",
        allowed_paths=["app/**"],
        required_gates=list(REQUIRED_GATES),
        limits=Limits(max_runtime_s=1, max_attempts=1, max_cost_usd=1),
    )
    built = build(contract, "<the run's summary>", "run_0091", "sv_01")
    assert built.strip() == block.strip()


def test_tag_rule_line_matches_the_spec_sentence_and_domain_stays_pure() -> None:
    """TASK-062 AC5: the line is the spec's literal and tag_rule.py imports only domain."""
    lines = code("openfactory.domain.tag_rule", "tag_rule_lines")
    literal = re.search(r"`(no tagged test in a changed file: <requirement id>)`", SPEC_TEXT)
    assert literal, "spec has no `no tagged test in a changed file: <requirement id>` literal"
    assert lines(["REQ-AUTH-001"]) == [literal.group(1).replace("<requirement id>", "REQ-AUTH-001")]

    source = Path(importlib.import_module("openfactory.domain.tag_rule").__file__ or "")
    imported: list[str] = []
    for node in ast.walk(ast.parse(source.read_text())):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    own = [m for m in imported if m == "openfactory" or m.startswith("openfactory.")]
    assert all(m.startswith("openfactory.domain") for m in own), own


def test_review_verdict_matches_the_spec_class_block() -> None:
    """TASK-069 AC1: field names and `verdict` values are the spec's block."""
    verdict_cls = code("openfactory.domain.review", "ReviewVerdict")
    block = code_block("class ReviewVerdict(BaseModel):")
    node = next(n for n in ast.parse(block).body if isinstance(n, ast.ClassDef))
    fields: dict[str, ast.expr] = {
        n.target.id: n.annotation
        for n in node.body
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
    }
    assert set(verdict_cls.model_fields) == set(fields)
    literal = fields["verdict"]
    assert isinstance(literal, ast.Subscript)
    values = [c.value for c in ast.walk(literal.slice) if isinstance(c, ast.Constant)]
    assert set(values) == {"approve", "reject"}
    for value in values:
        verdict_cls(verdict=value, comments="x")
