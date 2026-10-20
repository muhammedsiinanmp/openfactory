"""TASK-069: the review prompt and its retry form (AC4, AC5)."""

import ast
import importlib
from pathlib import Path

from openfactory.app.planner_prompt import context_hash
from openfactory.app.review_prompt import build_review_prompt
from openfactory.domain.contracts import REQUIRED_GATES, Limits, TaskContract
from openfactory.domain.plan_checks import PlanRejection, PlanRule, rejection_lines

DIFF = "diff --cached\n+++ b/app/x.py\n+print('zebra-quartz')\n  trailing  \n"
HEADING = (
    "## Rejections of your earlier reply (rule  subject  message); "
    "reply again with a verdict that has none of them"
)
REJECTIONS = [
    PlanRejection(rule=PlanRule.schema, subject="reply", message="verdict: bad"),
    PlanRejection(rule=PlanRule.schema, subject="reply", message="comments: Field required"),
]


def contract() -> TaskContract:
    return TaskContract(
        task_id="AUTH-002",
        objective="Implement login endpoint",
        requirements=["REQ-AUTH-001"],
        acceptance_criteria=["AC-AUTH-001-1"],
        components=["auth"],
        role="implementer",
        allowed_paths=["app/**", "tests/**"],
        required_gates=list(REQUIRED_GATES),
        limits=Limits(max_runtime_s=1, max_attempts=1, max_cost_usd=1),
    )


def test_ac4_prompt_holds_contract_json_and_diff_under_their_headings() -> None:
    prompt = build_review_prompt(contract(), DIFF)
    assert f"## Task contract\n{contract().model_dump_json(indent=2)}" in prompt
    assert f"## Staged diff\n{DIFF}" in prompt
    assert prompt.index("## Task contract") < prompt.index("## Staged diff")
    assert prompt.index("approve") < prompt.index("## Task contract")
    assert "reject" in prompt


def test_ac4_equal_arguments_give_equal_text() -> None:
    assert build_review_prompt(contract(), DIFF) == build_review_prompt(contract(), DIFF)


def test_ac4_module_imports_only_domain_and_stdlib() -> None:
    source = Path(importlib.import_module("openfactory.app.review_prompt").__file__ or "")
    imported: list[str] = []
    for node in ast.walk(ast.parse(source.read_text())):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    own = [m for m in imported if m == "openfactory" or m.startswith("openfactory.")]
    assert all(m.startswith("openfactory.domain") for m in own), own


def test_ac5_retry_prompt_is_first_prompt_plus_one_last_section() -> None:
    first = build_review_prompt(contract(), DIFF)
    retry = build_review_prompt(contract(), DIFF, REJECTIONS)
    assert retry.startswith(first.rstrip("\n"))
    tail = retry[len(first.rstrip("\n")) :]
    assert tail.lstrip("\n").startswith(HEADING + "\n")
    assert retry.count("## Rejections of your earlier reply") == 1
    listed = tail.split(HEADING + "\n", 1)[1]
    assert listed.strip().splitlines() == rejection_lines(REJECTIONS)


def test_ac5_retry_hash_differs_and_no_rejections_means_first_prompt() -> None:
    first = build_review_prompt(contract(), DIFF)
    assert build_review_prompt(contract(), DIFF, []) == first
    assert context_hash(build_review_prompt(contract(), DIFF, REJECTIONS)) != context_hash(first)
