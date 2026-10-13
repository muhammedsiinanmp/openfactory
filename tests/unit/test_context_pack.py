"""TASK-050: the context pack of an implementer run.

Each test names the acceptance criterion it covers (AC1..AC5 in
docs/tasks/TASK-050-context-pack.md). Tests check what the pack holds, never the
instructions' wording beyond the four strings of AC1, and never layout or spec item order.
"""

import ast
import hashlib
from pathlib import Path

from openfactory.app import context_pack
from openfactory.app.context_pack import build_context_pack
from openfactory.app.planner_prompt import context_hash
from openfactory.domain.contracts import REQUIRED_GATES, Limits, TaskContract
from openfactory.domain.models import AcceptanceCriterion, Adr, AdrStatus, Requirement, SpecSet

FILES = ["README.md", "app/auth/login.py", "app/billing/pay.py", "tests/auth/test_login.py"]
ADR1_BODY = "Sessions are signed with rotating keys zebra-quartz."
ADR2_BODY = "Billing totals are rounded half-even lorem-ipsum-two."
ADR3_BODY = "Unreferenced decision about caching walrus-nine."
BILL_STATEMENT = "A customer can pay an invoice by card."
AC2_TEXT = "Expired token is refused politely."


def make_req(
    req_id: str, title: str, statement: str, criteria: list[tuple[str, str]], adr: str
) -> Requirement:
    return Requirement(
        id=req_id,
        title=title,
        statement=statement,
        priority="must",
        components=["auth"],
        acceptance_criteria=[AcceptanceCriterion(id=i, text=t) for i, t in criteria],
        constrained_by=[adr],
    )


def sample_set(adr1_body: str = ADR1_BODY) -> SpecSet:
    return SpecSet(
        components=["auth", "billing"],
        requirements=[
            make_req(
                "REQ-AUTH-001",
                "Login with token",
                "A user can log in with a bearer token.",
                [
                    ("AC-AUTH-001-1", "Valid token returns session handle."),
                    ("AC-AUTH-001-2", AC2_TEXT),
                ],
                "ADR-001",
            ),
            make_req(
                "REQ-BILL-001",
                "Pay invoice",
                BILL_STATEMENT,
                [("AC-BILL-001-1", "Card is charged once.")],
                "ADR-002",
            ),
        ],
        adrs=[
            Adr(id="ADR-001", status=AdrStatus.accepted, body=adr1_body),
            Adr(id="ADR-002", status=AdrStatus.accepted, body=ADR2_BODY),
            Adr(id="ADR-003", status=AdrStatus.accepted, body=ADR3_BODY),
        ],
    )


def sample_contract(objective: str = "Add token login for café users.") -> TaskContract:
    return TaskContract(
        task_id="AUTH-002",
        objective=objective,
        requirements=["REQ-AUTH-001"],
        acceptance_criteria=["AC-AUTH-001-1"],
        depends_on=["AUTH-001"],
        components=["auth"],
        role="implementer",
        allowed_paths=["app/auth/**", "tests/auth/**"],
        forbidden_paths=["secrets/**", ".env"],
        required_gates=list(REQUIRED_GATES),
        limits=Limits(max_runtime_s=777, max_attempts=4, max_cost_usd=3.5),
    )


def pack(files: list[str] = FILES) -> str:
    return build_context_pack(sample_contract(), sample_set(), files)


def test_ac1_pack_is_text_with_the_four_instruction_strings() -> None:
    text = pack()
    assert isinstance(text, str)
    for item in ["pytest.mark.req", "git commit", "allowed_paths", "__pycache__"]:
        assert item in text


def test_ac2_pack_holds_the_contract() -> None:
    contract = sample_contract()
    text = pack()
    items = [
        contract.task_id,
        contract.objective,
        *contract.requirements,
        *contract.acceptance_criteria,
        *contract.depends_on,
        *contract.components,
        *contract.allowed_paths,
        *contract.forbidden_paths,
        *contract.required_gates,
        "777",
        "4",
        "3.5",
    ]
    for item in items:
        assert item in text
    assert contract.model_dump_json(indent=2) in text


def test_ac3_pack_holds_the_named_spec_items() -> None:
    text = pack()
    for item in [
        "REQ-AUTH-001",
        "Login with token",
        "A user can log in with a bearer token.",
        "AC-AUTH-001-1",
        "Valid token returns session handle.",
        ADR1_BODY,
    ]:
        assert item in text


def test_ac3_pack_leaves_out_what_the_contract_does_not_name() -> None:
    text = pack()
    for item in [BILL_STATEMENT, ADR2_BODY, ADR3_BODY, AC2_TEXT]:
        assert item not in text


def test_ac4_pack_lists_matching_tracked_files_in_order_on_own_lines() -> None:
    lines = pack().splitlines()
    first = lines.index("app/auth/login.py")
    second = lines.index("tests/auth/test_login.py")
    assert first < second
    assert "README.md" not in pack()
    assert "app/billing/pay.py" not in pack()


def test_ac4_no_matching_file_still_holds_instructions_contract_and_spec_items() -> None:
    for files in (["README.md", "app/billing/pay.py"], []):
        text = pack(files)
        for item in [
            "pytest.mark.req",
            sample_contract().model_dump_json(indent=2),
            "REQ-AUTH-001",
            ADR1_BODY,
        ]:
            assert item in text


def test_ac5_equal_arguments_give_equal_text() -> None:
    assert pack() == pack()


def test_ac5_hash_is_sha256_of_utf8_text() -> None:
    text = pack()
    assert "café" in text
    assert context_hash(text) == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_ac5_changed_input_changes_the_hash() -> None:
    base = context_hash(pack())
    other_objective = build_context_pack(sample_contract("Another goal."), sample_set(), FILES)
    other_adr = build_context_pack(sample_contract(), sample_set("Changed decision."), FILES)
    more_files = pack([*FILES, "app/auth/logout.py"])
    hashes = {base, *(context_hash(t) for t in (other_objective, other_adr, more_files))}
    assert len(hashes) == 4


def test_ac5_module_imports_only_domain_and_standard_library() -> None:
    tree = ast.parse(Path(context_pack.__file__).read_text())
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules.append(node.module or "")
    for name in modules:
        if name.startswith("openfactory"):
            assert name.startswith("openfactory.domain")
