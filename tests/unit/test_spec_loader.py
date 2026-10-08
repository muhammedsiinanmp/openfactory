"""TASK-007: spec loader.

Each test names the acceptance criterion it covers (AC1..AC6 in
docs/tasks/TASK-007-spec-loader.md). The loader is driven through an in-memory
fake SpecFiles; no filesystem or database is used.
"""

import ast
from pathlib import Path

import pytest

from openfactory.app.spec_loader import SpecLoadResult, load_spec
from openfactory.domain.models import AdrStatus, Priority

APP_DIR = Path(__file__).resolve().parents[2] / "src" / "openfactory" / "app"

REQUIREMENTS = """\
# requirements.yaml
components: [auth]
requirements:
  - id: REQ-AUTH-001
    title: Login with membership number
    statement: Users authenticate using their membership number and password.
    priority: must
    constrained_by: [ADR-001]
    acceptance_criteria:
      - id: AC-AUTH-001-1
        text: Valid membership number and password returns a JWT.
      - id: AC-AUTH-001-2
        text: Unknown membership number returns 401.
"""

ADR_001 = """\
---
id: ADR-001
status: accepted
title: Auth method
date: 2026-01-01
---
We use JWT.
"""


def adr(id_: str = "ADR-002", status: str = "accepted") -> str:
    return f"---\nid: {id_}\nstatus: {status}\n---\nbody\n"


def reqs(*items: str) -> str:
    return "requirements:\n" + "".join(items)


def one_req(
    id_: str = "REQ-AUTH-001", priority: str = "must", extra: str = "", acs: bool = True
) -> str:
    text = f"  - id: {id_}\n    title: T\n    statement: S\n    priority: {priority}\n{extra}"
    if acs:
        text += "    acceptance_criteria:\n      - id: AC-AUTH-001-1\n        text: x\n"
    return text


class FakeSpecFiles:
    """Dict of path (relative to specs/) to text; `bad_utf8` paths raise on read."""

    def __init__(self, files: dict[str, str | None], bad_utf8: set[str] | None = None):
        self.files = files
        self.bad_utf8 = bad_utf8 or set()

    def read(self, path: str) -> str | None:
        if path in self.bad_utf8:
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
        return self.files.get(path)

    def list_adrs(self) -> list[str]:
        paths = set(self.files) | self.bad_utf8
        return sorted(p for p in paths if p.startswith("adrs/") and p.endswith(".md"))


def is_schema(violation) -> bool:
    return violation.rule.value == "schema"


def assert_single_schema(result: SpecLoadResult, subject: str) -> None:
    assert result.spec is None
    assert len(result.violations) == 1
    (v,) = result.violations
    assert is_schema(v)
    assert v.subject == subject
    assert v.message


def test_ac1_loads_spec_example() -> None:
    files = FakeSpecFiles(
        {"requirements.yaml": REQUIREMENTS, "adrs/ADR-001-auth-method.md": ADR_001}
    )
    result = load_spec(files)
    assert result.violations == []
    spec = result.spec
    assert spec is not None
    assert spec.components == ["auth"]
    (r,) = spec.requirements
    assert r.id == "REQ-AUTH-001"
    assert r.title == "Login with membership number"
    assert r.statement == "Users authenticate using their membership number and password."
    assert r.priority is Priority.must
    assert r.constrained_by == ["ADR-001"]
    assert [ac.id for ac in r.acceptance_criteria] == ["AC-AUTH-001-1", "AC-AUTH-001-2"]
    assert len(spec.adrs) == 1


def test_ac1_loader_does_not_import_adapters() -> None:
    tree = ast.parse((APP_DIR / "spec_loader.py").read_text())
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    assert not [m for m in modules if m.startswith("openfactory.adapters")]


def test_ac2_adr_front_matter_and_body() -> None:
    text = (
        "---\nid: ADR-007\nstatus: accepted\ntitle: Notes\ndate: 2026-02-03\n---\n"
        "\nFirst line.\n\nSecond line.\n  "
    )
    result = load_spec(FakeSpecFiles({"requirements.yaml": REQUIREMENTS, "adrs/notes.md": text}))
    assert result.spec is not None
    (a,) = result.spec.adrs
    assert a.id == "ADR-007"
    assert a.status is AdrStatus.accepted
    assert a.body == "\nFirst line.\n\nSecond line.\n  "


def test_ac2_crlf_body_is_normalised() -> None:
    text = "---\nid: ADR-007\nstatus: accepted\n---\nline one\nline two\n"
    crlf = text.replace("\n", "\r\n")
    lf_result = load_spec(FakeSpecFiles({"requirements.yaml": REQUIREMENTS, "adrs/n.md": text}))
    crlf_result = load_spec(FakeSpecFiles({"requirements.yaml": REQUIREMENTS, "adrs/n.md": crlf}))
    assert lf_result.spec is not None and crlf_result.spec is not None
    body = crlf_result.spec.adrs[0].body
    assert "\r" not in body
    assert body == lf_result.spec.adrs[0].body == "line one\nline two\n"


def test_ac2_no_adr_files_means_no_adrs() -> None:
    result = load_spec(FakeSpecFiles({"requirements.yaml": REQUIREMENTS}))
    assert result.violations == []
    assert result.spec is not None
    assert result.spec.adrs == []


@pytest.mark.parametrize(
    "bad_yaml",
    [
        "requirements: [unclosed\n",
        reqs(
            "  - id: REQ-AUTH-001\n    title: A\n    title: B\n    statement: S\n"
            "    priority: must\n"
        ),
    ],
    ids=["syntax-error", "duplicate-key"],
)
def test_ac3_bad_requirements_yaml(bad_yaml: str) -> None:
    result = load_spec(FakeSpecFiles({"requirements.yaml": bad_yaml}))
    assert_single_schema(result, "specs/requirements.yaml")


def test_ac3_bad_adr_front_matter_yaml() -> None:
    text = "---\nid: [unclosed\nstatus: accepted\n---\nbody\n"
    result = load_spec(
        FakeSpecFiles({"requirements.yaml": REQUIREMENTS, "adrs/ADR-001-a.md": text})
    )
    assert_single_schema(result, "specs/adrs/ADR-001-a.md")


def test_ac3_impossible_date_in_adr_front_matter() -> None:
    # Added after review: PyYAML raises ValueError, not YAMLError, for such a date.
    text = "---\nid: ADR-001\nstatus: accepted\ndate: 2026-02-30\n---\nbody\n"
    result = load_spec(
        FakeSpecFiles({"requirements.yaml": REQUIREMENTS, "adrs/ADR-001-a.md": text})
    )
    assert_single_schema(result, "specs/adrs/ADR-001-a.md")


def test_ac4_missing_requirements_yaml() -> None:
    result = load_spec(FakeSpecFiles({}))
    assert_single_schema(result, "specs/requirements.yaml")


@pytest.mark.parametrize(
    "text",
    ["id: ADR-001\nstatus: accepted\nbody\n", "---\nid: ADR-001\nstatus: accepted\nbody\n"],
    ids=["no-opening", "no-closing"],
)
def test_ac4_adr_without_front_matter(text: str) -> None:
    result = load_spec(FakeSpecFiles({"requirements.yaml": REQUIREMENTS, "adrs/x.md": text}))
    assert_single_schema(result, "specs/adrs/x.md")


def test_ac4_requirements_not_utf8() -> None:
    result = load_spec(FakeSpecFiles({}, bad_utf8={"requirements.yaml"}))
    assert_single_schema(result, "specs/requirements.yaml")
    assert "not valid UTF-8" in result.violations[0].message


def test_ac4_adr_not_utf8() -> None:
    result = load_spec(FakeSpecFiles({"requirements.yaml": REQUIREMENTS}, bad_utf8={"adrs/bad.md"}))
    assert_single_schema(result, "specs/adrs/bad.md")
    assert "not valid UTF-8" in result.violations[0].message


def test_ac5_bad_priority_names_field() -> None:
    result = load_spec(FakeSpecFiles({"requirements.yaml": reqs(one_req(priority="urgent"))}))
    assert result.spec is None
    assert result.violations
    assert all(is_schema(v) and v.subject == "REQ-AUTH-001" for v in result.violations)
    assert any("priority" in v.message for v in result.violations)


def test_ac5_misspelt_key_uses_requirement_id() -> None:
    item = one_req().replace("title:", "titel:")
    result = load_spec(FakeSpecFiles({"requirements.yaml": reqs(item)}))
    assert result.spec is None
    assert result.violations
    assert all(is_schema(v) and v.subject == "REQ-AUTH-001" for v in result.violations)


def test_ac5_bad_adr_status_uses_adr_id() -> None:
    result = load_spec(
        FakeSpecFiles({"requirements.yaml": REQUIREMENTS, "adrs/a.md": adr("ADR-002", "draft")})
    )
    assert result.spec is None
    assert result.violations
    assert all(is_schema(v) and v.subject == "ADR-002" for v in result.violations)


@pytest.mark.parametrize(
    "text",
    [
        reqs("  - title: T\n    statement: S\n    priority: must\n"),
        "- just\n- a list\n",
    ],
    ids=["requirement-without-id", "top-level-not-mapping"],
)
def test_ac5_unidentifiable_requirements_use_file_path(text: str) -> None:
    result = load_spec(FakeSpecFiles({"requirements.yaml": text}))
    assert result.spec is None
    assert result.violations
    assert all(is_schema(v) and v.subject == "specs/requirements.yaml" for v in result.violations)


def test_ac5_adr_without_id_uses_file_path() -> None:
    text = "---\nstatus: accepted\n---\nbody\n"
    result = load_spec(FakeSpecFiles({"requirements.yaml": REQUIREMENTS, "adrs/noid.md": text}))
    assert result.spec is None
    assert result.violations
    assert all(is_schema(v) and v.subject == "specs/adrs/noid.md" for v in result.violations)


@pytest.mark.parametrize(
    "item",
    [one_req(acs=False), one_req(id_="REQ-1")],
    ids=["no-acceptance-criteria", "bad-id-format"],
)
def test_ac5_content_rule_problems_are_not_schema(item: str) -> None:
    result = load_spec(FakeSpecFiles({"requirements.yaml": reqs(item)}))
    assert result.violations == []
    assert result.spec is not None
    assert len(result.spec.requirements) == 1


def test_ac6_collects_all_violations_in_order() -> None:
    requirements = reqs(
        one_req(id_="REQ-AUTH-001", priority="urgent"),
        one_req(id_="REQ-AUTH-002"),
    )
    files = FakeSpecFiles(
        {
            "requirements.yaml": requirements,
            "adrs/ADR-001-a.md": "no front matter\n",
            "adrs/ADR-002-b.md": adr("ADR-002", "draft"),
        }
    )
    result = load_spec(files)
    assert result.spec is None
    assert all(is_schema(v) for v in result.violations)
    subjects = [v.subject for v in result.violations]
    assert subjects[0] == "REQ-AUTH-001"
    assert subjects[-2:] == ["specs/adrs/ADR-001-a.md", "ADR-002"]
    assert len(subjects) >= 3


def test_ac6_exactly_one_of_spec_or_violations() -> None:
    ok = load_spec(FakeSpecFiles({"requirements.yaml": REQUIREMENTS}))
    assert ok.spec is not None and ok.violations == []
    bad = load_spec(FakeSpecFiles({}))
    assert bad.spec is None and bad.violations
