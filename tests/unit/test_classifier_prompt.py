"""TASK-093: the classifier prompt and its retry form (AC1 to AC5).

Each test names the acceptance criterion it covers in
docs/tasks/TASK-093-classifier-prompt.md. Tests check what the prompt holds and the order
of its parts, never its exact wording or layout.
"""

import ast
import importlib
from pathlib import Path

from openfactory.app.classifier_prompt import build_classifier_prompt
from openfactory.app.planner_prompt import context_hash
from openfactory.domain.classifier import ClassifierRejection, ClassifierRule
from openfactory.domain.models import AcceptanceCriterion, Adr, AdrStatus, Requirement, SpecSet
from openfactory.domain.plan_checks import rejection_lines
from openfactory.domain.spec_diff import SpecDiff, diff_specs

ADR1_OLD = "Sessions are signed with rotating keys zebra-quartz."
ADR1_NEW = "Sessions are signed with hardware keys kiwi-basalt."
ADR2_BODY = "Passwords are hashed with argon2 lorem-ipsum-two."
ADR3_BODY = "Unreferenced decision about caching walrus-nine."
ADR4_BODY = "Tokens are one-time passwords otp-mango-four."
REJECTIONS = [
    ClassifierRejection(
        rule=ClassifierRule.UNKNOWN_REQUIREMENT, subject="REQ-AUTH-099", message="not modified"
    ),
    ClassifierRejection(
        rule=ClassifierRule.MISSING_REQUIREMENT, subject="REQ-AUTH-002", message="no entry"
    ),
]


def make_req(
    req_id: str,
    title: str,
    statement: str,
    criteria: list[tuple[str, str]],
    constrained_by: list[str],
    priority: str = "must",
) -> Requirement:
    return Requirement(
        id=req_id,
        title=title,
        statement=statement,
        priority=priority,  # pyright: ignore[reportArgumentType]
        components=["auth"],
        acceptance_criteria=[AcceptanceCriterion(id=i, text=t) for i, t in criteria],
        constrained_by=constrained_by,
    )


def old_set() -> SpecSet:
    return SpecSet(
        components=["auth"],
        requirements=[
            make_req(
                "REQ-AUTH-001",
                "Login by membership number",
                "A user logs in with a membership number.",
                [
                    ("AC-AUTH-001-1", "Valid number opens a session."),
                    ("AC-AUTH-001-2", "Unknown number is refused politely."),
                ],
                ["ADR-001", "ADR-002"],
            ),
            make_req(
                "REQ-AUTH-002",
                "Session signing",
                "Sessions are signed.",
                [("AC-AUTH-002-1", "Session carries a signature.")],
                ["ADR-001"],
                priority="should",
            ),
            make_req(
                "REQ-AUTH-004",
                "Audit trail",
                "Logins are audited.",
                [("AC-AUTH-004-1", "Each login writes an audit row.")],
                ["ADR-003"],
            ),
        ],
        adrs=[
            Adr(id="ADR-001", status=AdrStatus.accepted, body=ADR1_OLD),
            Adr(id="ADR-002", status=AdrStatus.accepted, body=ADR2_BODY),
            Adr(id="ADR-003", status=AdrStatus.accepted, body=ADR3_BODY),
        ],
    )


def new_set() -> SpecSet:
    return SpecSet(
        components=["auth"],
        requirements=[
            make_req(
                "REQ-AUTH-001",
                "Login by one-time password",
                "A user logs in with a one-time password.",
                [
                    ("AC-AUTH-001-1", "Valid password opens a session."),
                    ("AC-AUTH-001-3", "Password works only once."),
                ],
                ["ADR-001", "ADR-004"],
            ),
            make_req(
                "REQ-AUTH-002",
                "Session signing",
                "Sessions are signed.",
                [("AC-AUTH-002-1", "Session carries a signature.")],
                ["ADR-001"],
                priority="should",
            ),
            make_req(
                "REQ-AUTH-003",
                "Logout",
                "A user can log out.",
                [("AC-AUTH-003-1", "Logout ends the session.")],
                ["ADR-003"],
            ),
            make_req(
                "REQ-AUTH-004",
                "Audit trail",
                "Logins are audited.",
                [("AC-AUTH-004-1", "Each login writes an audit row.")],
                ["ADR-003"],
            ),
        ],
        adrs=[
            Adr(id="ADR-001", status=AdrStatus.accepted, body=ADR1_NEW),
            Adr(id="ADR-003", status=AdrStatus.accepted, body=ADR3_BODY),
            Adr(id="ADR-004", status=AdrStatus.accepted, body=ADR4_BODY),
        ],
    )


def prompt(rejections: list[ClassifierRejection] | None = None) -> str:
    old, new = old_set(), new_set()
    return build_classifier_prompt(old, new, diff_specs(old, new), rejections or ())


def test_scenario_modifies_exactly_001_and_002() -> None:
    diff = diff_specs(old_set(), new_set())
    modified = [r.id for r in diff.requirements if r.change == "modified"]
    assert modified == ["REQ-AUTH-001", "REQ-AUTH-002"]


def test_task093_ac1_one_block_per_modified_requirement_from_then_to() -> None:
    text = prompt()
    in_order = [
        "Login by membership number",
        "A user logs in with a membership number.",
        "Login by one-time password",
        "A user logs in with a one-time password.",
        "Session signing",
    ]
    positions = [text.index(item) for item in in_order]
    assert positions == sorted(positions)
    for item in (
        "AC-AUTH-001-2",
        "Unknown number is refused politely.",
        "AC-AUTH-001-3",
        "Password works only once.",
        "AC-AUTH-001-1",
        "Valid number opens a session.",
        "Valid password opens a session.",
        "should",
        "auth",
    ):
        assert item in text, item
    # from version holds the criterion that was removed, to version the one that was added
    assert text.index("AC-AUTH-001-2") < text.index("Login by one-time password")
    assert text.index("AC-AUTH-001-3") > text.index("Login by one-time password")
    assert text.index("Login by one-time password") < text.index("Session signing")


def test_task093_ac1_other_changes_do_not_appear() -> None:
    text = prompt()
    for absent in ("REQ-AUTH-003", "Logout", "REQ-AUTH-004", "Audit trail", "AC-AUTH-004-1"):
        assert absent not in text, absent


def test_task093_ac2_adr_bodies_sit_in_delimiters_under_their_own_version() -> None:
    text = prompt()
    assert '<adr id="ADR-001">' in text
    assert '<adr id="ADR-002">' in text
    assert '<adr id="ADR-004">' in text
    # REQ-AUTH-001 and REQ-AUTH-002 both name ADR-001 in both versions: four copies.
    assert text.count(ADR1_OLD) == 2
    assert text.count(ADR1_NEW) == 2
    # ADR-002 is named only by the from version, ADR-004 only by the to version.
    assert text.count(ADR2_BODY) == 1
    assert text.count(ADR4_BODY) == 1
    to_start = text.index("Login by one-time password")
    assert text.index(ADR2_BODY) < to_start < text.index(ADR4_BODY)
    # for REQ-AUTH-001 the old ADR-001 body comes before the new one
    assert text.index(ADR1_OLD) < to_start < text.index(ADR1_NEW)


def test_task093_ac2_adr_no_modified_requirement_names_is_absent() -> None:
    text = prompt()
    assert ADR3_BODY not in text
    assert '<adr id="ADR-003">' not in text


def test_task093_ac3_instructions_name_kinds_reply_form_and_cosmetic_rule() -> None:
    text = prompt()
    for item in (
        "cosmetic",
        "behavioral",
        "replacement",
        '{"changes"',
        "req_id",
        "kind",
        "rationale",
        "obsolete_criteria",
        "new_work",
    ):
        assert item in text, item
    first_block = text.index("REQ-AUTH-00")
    instructions = text[:first_block].lower()
    assert "wording" in instructions
    assert "one entry" in instructions


def test_task093_ac3_instruction_text_does_not_change_with_arguments() -> None:
    other_old = SpecSet(
        components=["auth"],
        requirements=[
            make_req("REQ-AUTH-009", "Other", "Other statement.", [("AC-AUTH-009-1", "Other.")], [])
        ],
        adrs=[],
    )
    other_new = SpecSet(
        components=["auth"],
        requirements=[
            make_req(
                "REQ-AUTH-009", "Other", "Changed statement.", [("AC-AUTH-009-1", "Other.")], []
            )
        ],
        adrs=[],
    )
    a = prompt()
    b = build_classifier_prompt(other_old, other_new, diff_specs(other_old, other_new))
    assert a[: a.index("REQ-AUTH-00")] == b[: b.index("REQ-AUTH-00")]


def test_task093_ac4_retry_is_first_prompt_plus_one_last_section_with_the_lines() -> None:
    first = prompt()
    retry = prompt(REJECTIONS)
    assert retry.startswith(first.rstrip("\n"))
    tail = retry[len(first.rstrip("\n")) :].strip().splitlines()
    assert tail[-len(REJECTIONS) :] == rejection_lines(REJECTIONS)
    assert len(tail) > len(REJECTIONS)  # a heading line precedes the lines


def test_task093_ac4_no_rejections_means_the_first_prompt() -> None:
    old, new = old_set(), new_set()
    diff = diff_specs(old, new)
    assert build_classifier_prompt(old, new, diff, []) == build_classifier_prompt(old, new, diff)
    assert rejection_lines(REJECTIONS)[0] not in prompt()


def test_task093_ac5_equal_arguments_equal_text_and_changes_change_the_hash() -> None:
    assert prompt() == prompt()
    base = context_hash(prompt())

    new = new_set()
    old = old_set()
    new.requirements[0] = new.requirements[0].model_copy(
        update={"statement": "A user logs in with a hardware token."}
    )
    changed_statement = build_classifier_prompt(old, new, diff_specs(old, new))
    assert context_hash(changed_statement) != base

    new = new_set()
    new.adrs[0] = new.adrs[0].model_copy(update={"body": "A different ADR-001 body."})
    changed_adr = build_classifier_prompt(old, new, diff_specs(old, new))
    assert context_hash(changed_adr) != base


def test_task093_ac5_inputs_are_not_mutated() -> None:
    old, new = old_set(), new_set()
    diff = diff_specs(old, new)
    before = (old.model_dump(), new.model_dump(), diff.model_dump())
    build_classifier_prompt(old, new, diff, REJECTIONS)
    assert (old.model_dump(), new.model_dump(), diff.model_dump()) == before


def test_task093_ac5_module_imports_only_domain_and_stdlib() -> None:
    source = Path(importlib.import_module("openfactory.app.classifier_prompt").__file__ or "")
    imported: list[str] = []
    for node in ast.walk(ast.parse(source.read_text())):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    own = [m for m in imported if m == "openfactory" or m.startswith("openfactory.")]
    assert all(m.startswith("openfactory.domain") for m in own), own


def test_task093_ac5_empty_diff_still_builds() -> None:
    empty = SpecSet(components=[], requirements=[], adrs=[])
    assert isinstance(
        build_classifier_prompt(empty, empty, SpecDiff(requirements=[], adrs=[])), str
    )


def test_task098_ac5_instructions_say_lost_or_gained_criterion_is_not_cosmetic() -> None:
    text = prompt()
    instructions = " ".join(text[: text.index("REQ-AUTH-00")].lower().split())
    rule = next(line for line in instructions.split("- ") if "not cosmetic" in line)
    assert "lacks a criterion" in rule  # lost: the to version lacks one of the from version
    assert "has a criterion" in rule  # gained: the to version has one the from version lacks
