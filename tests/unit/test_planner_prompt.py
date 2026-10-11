"""TASK-031: the planner prompt and the prompt hash.

Each test names the acceptance criterion it covers (AC1..AC6, except AC4, in
docs/tasks/TASK-031-planner-prompt-and-rejection-lines.md). Tests check what the prompt
holds, never its wording or layout.
"""

import ast
import hashlib
from pathlib import Path

from openfactory.app import planner_prompt
from openfactory.app.planner_prompt import build_planner_prompt, context_hash
from openfactory.domain.models import AcceptanceCriterion, Adr, AdrStatus, Requirement, SpecSet
from openfactory.domain.plan_checks import PlanRejection, PlanRule, rejection_lines
from openfactory.domain.policy import Policy

FILES = ["app/main.py", "tests/test_main.py"]
POLICY = Policy(forbidden_paths=["secrets/**"])
ADR1_BODY = "Sessions are signed with rotating keys zebra-quartz."
ADR2_BODY = "Passwords are hashed with argon2 lorem-ipsum-two."
ADR3_BODY = "Unreferenced decision about caching walrus-nine."


def make_req(
    req_id: str, title: str, statement: str, criteria: list[tuple[str, str]], **kw: object
) -> Requirement:
    return Requirement(
        id=req_id,
        title=title,
        statement=statement,
        priority="must",
        components=["auth"],
        acceptance_criteria=[AcceptanceCriterion(id=i, text=t) for i, t in criteria],
        **kw,  # pyright: ignore[reportArgumentType]
    )


def sample_req() -> Requirement:
    return make_req(
        "REQ-AUTH-001",
        "Login with token",
        "A user can log in with a bearer token.",
        [
            ("AC-AUTH-001-1", "Valid token returns session handle."),
            ("AC-AUTH-001-2", "Expired token is refused politely."),
        ],
        constrained_by=["ADR-001"],
    )


def sample_set() -> SpecSet:
    return SpecSet(
        components=["auth", "billing"],
        requirements=[sample_req()],
        adrs=[Adr(id="ADR-001", status=AdrStatus.accepted, body=ADR1_BODY)],
    )


def deprecated_set() -> SpecSet:
    dep = make_req(
        "REQ-AUTH-002",
        "Legacy cookie",
        "Legacy cookie login persists for ninety days.",
        [("AC-AUTH-002-1", "Cookie survives browser restart in legacy mode.")],
        constrained_by=["ADR-001", "ADR-002"],
        deprecated=True,
    )
    return SpecSet(
        components=["auth", "billing"],
        requirements=[sample_req(), dep],
        adrs=[
            Adr(id="ADR-001", status=AdrStatus.accepted, body=ADR1_BODY),
            Adr(id="ADR-002", status=AdrStatus.accepted, body=ADR2_BODY),
            Adr(id="ADR-003", status=AdrStatus.accepted, body=ADR3_BODY),
        ],
    )


def ac1_items() -> list[str]:
    return [
        "REQ-AUTH-001",
        "Login with token",
        "A user can log in with a bearer token.",
        "AC-AUTH-001-1",
        "Valid token returns session handle.",
        "AC-AUTH-001-2",
        "Expired token is refused politely.",
        ADR1_BODY,
        "ADR-001",
        "auth",
        "billing",
        "specs/**",
        ".openfactory/**",
        ".env",
        ".env.*",
        "secrets/**",
        "path_check",
        "ruff",
        "pytest",
        "gitleaks",
        "review",
    ]


def test_ac1_prompt_holds_the_planning_input() -> None:
    prompt = build_planner_prompt(sample_set(), POLICY, FILES)
    assert isinstance(prompt, str)
    for item in [*ac1_items(), *FILES]:
        assert item in prompt
    # `.env` on its own, not only as the start of `.env.*`
    assert ".env" in prompt.replace(".env.*", "")
    # the ADR's id is with its body and with the requirement it constrains
    assert prompt.count("ADR-001") >= 2


def test_ac1_requirement_without_adrs_and_empty_lists_leave_no_trailing_space() -> None:
    bare = make_req(
        "REQ-AUTH-001", "Login with token", "A user can log in.", [("AC-AUTH-001-1", "x")]
    )
    prompt = build_planner_prompt(SpecSet(components=["auth"], requirements=[bare]), POLICY, [])
    assert all(line == line.rstrip() for line in prompt.splitlines())


def test_ac2_deprecated_requirement_and_its_adr_are_left_out() -> None:
    prompt = build_planner_prompt(deprecated_set(), POLICY, FILES)
    for item in [
        "REQ-AUTH-002",
        "Legacy cookie login persists for ninety days.",
        "AC-AUTH-002-1",
        "Cookie survives browser restart in legacy mode.",
        ADR2_BODY,
    ]:
        assert item not in prompt


def test_ac2_unreferenced_adr_is_left_out() -> None:
    prompt = build_planner_prompt(deprecated_set(), POLICY, FILES)
    assert ADR3_BODY not in prompt


def test_ac2_adr_shared_with_deprecated_requirement_is_kept() -> None:
    prompt = build_planner_prompt(deprecated_set(), POLICY, FILES)
    assert ADR1_BODY in prompt


def test_ac3_tracked_file_names_unchanged_and_in_order() -> None:
    files = ["zeta/a.py", "docs/my notes.md", "src/café.py", "alpha/b.py"]
    prompt = build_planner_prompt(sample_set(), POLICY, files)
    positions = [prompt.index(f) for f in files]
    assert positions == sorted(positions)


def test_ac3_empty_file_list_still_holds_the_rest() -> None:
    prompt = build_planner_prompt(sample_set(), POLICY, [])
    for item in ac1_items():
        assert item in prompt


def test_ac3_module_imports_no_adapter_or_cli() -> None:
    tree = ast.parse(Path(planner_prompt.__file__).read_text())
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules.append(node.module or "")
    for name in modules:
        assert not name.startswith("openfactory.adapters")
        assert not name.startswith("openfactory.cli")


def rejections() -> list[PlanRejection]:
    return [
        PlanRejection(rule=PlanRule.uncovered, subject="REQ-AUTH-001", message="no task covers it"),
        PlanRejection(rule=PlanRule.cycle, subject="AUTH-001", message="loops back to itself"),
    ]


def test_ac5_retry_prompt_holds_rejection_lines_and_planning_input() -> None:
    rej = rejections()
    first = build_planner_prompt(sample_set(), POLICY, FILES)
    retry = build_planner_prompt(sample_set(), POLICY, FILES, rej)
    lines = rejection_lines(rej)
    assert len(lines) == 2
    for line in lines:
        assert line in retry
    for item in [*ac1_items(), *FILES]:
        assert item in retry
    assert retry != first


def test_ac5_first_prompt_holds_no_rejection_lines() -> None:
    first = build_planner_prompt(sample_set(), POLICY, FILES)
    for line in rejection_lines(rejections()):
        assert line not in first


def test_ac6_context_hash_of_empty_prompt() -> None:
    assert context_hash("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_ac6_context_hash_is_sha256_of_utf8() -> None:
    prompt = "plan café ✓"
    digest = context_hash(prompt)
    assert digest == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert len(digest) == 64
    assert digest == digest.lower()


def test_ac6_equal_arguments_give_equal_prompts() -> None:
    a = build_planner_prompt(sample_set(), POLICY, FILES)
    b = build_planner_prompt(sample_set(), POLICY, FILES)
    assert a == b
    assert context_hash(a) == context_hash(b)
