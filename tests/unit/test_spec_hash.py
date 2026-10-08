"""TASK-004: spec model fields from v1.4 and canonical spec hashing.

Each test names the acceptance criterion it covers (AC1..AC6 in
docs/tasks/TASK-004-spec-hashing.md).
"""

import ast
import hashlib
import json
import re
from pathlib import Path

import pytest

from openfactory.domain.models import AcceptanceCriterion, Adr, Requirement, SpecSet
from openfactory.domain.spec_validation import validate_spec

DOMAIN_DIR = Path(__file__).resolve().parents[2] / "src" / "openfactory" / "domain"
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def canonical_json(item):
    # Imported lazily so the AC1 field tests run before spec_hash.py exists.
    from openfactory.domain.spec_hash import canonical_json as fn

    return fn(item)


def content_hash(item):
    from openfactory.domain.spec_hash import content_hash as fn

    return fn(item)


def ac(id="AC-1", text="x"):
    return {"id": id, "text": text}


def req_data(id="REQ-A-001", **kw):
    data = {
        "id": id,
        "title": "t",
        "statement": "s",
        "priority": "must",
        "acceptance_criteria": [ac()],
    }
    data.update(kw)
    return data


def req(id="REQ-A-001", **kw):
    return Requirement.model_validate(req_data(id, **kw))


def adr(**kw):
    data = {"id": "ADR-001", "status": "accepted", "body": "b"}
    data.update(kw)
    return Adr.model_validate(data)


def spec(requirements=None, adrs=None, components=("auth",)):
    return SpecSet.model_validate(
        {
            "components": list(components),
            "requirements": [req_data()] if requirements is None else requirements,
            "adrs": [] if adrs is None else adrs,
        }
    )


# ---------------------------------------------------------------- AC1


def test_ac1_requirement_deprecated_defaults_false_and_accepts_true():
    assert req().deprecated is False
    assert req(deprecated=True).deprecated is True


def test_ac1_adr_body_is_kept_and_other_front_matter_ignored():
    a = Adr.model_validate(
        {"id": "ADR-001", "status": "accepted", "body": "Text", "title": "T", "date": "2026"}
    )
    assert a.body == "Text"
    assert not hasattr(a, "title")
    assert not hasattr(a, "date")


def test_ac1_adr_body_defaults_to_empty_string():
    assert Adr.model_validate({"id": "ADR-001", "status": "accepted"}).body == ""


def test_ac1_deprecated_requirement_is_still_validated():
    s = spec([req_data(deprecated=True, acceptance_criteria=[])])
    rules = {(v.rule, v.subject) for v in validate_spec(s)}
    assert ("missing-acceptance-criteria", "REQ-A-001") in rules


def test_ac1_spec_hash_module_respects_domain_boundary():
    tree = ast.parse((DOMAIN_DIR / "spec_hash.py").read_text())
    forbidden = ("openfactory.adapters", "openfactory.app", "openfactory.ports")
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        for name in names:
            assert not name.startswith(forbidden), name


# ---------------------------------------------------------------- AC2

AC_LITERAL = '{"id":"AC-AUTH-001-1","text":"Café ≥ 1"}'


def test_ac2_criterion_canonical_json_is_exact_utf8_without_escapes():
    item = AcceptanceCriterion(id="AC-AUTH-001-1", text="Café ≥ 1")
    assert canonical_json(item) == AC_LITERAL.encode("utf-8")


def test_ac2_requirement_canonical_json_has_sorted_keys_and_plain_enum():
    data = json.loads(canonical_json(req(priority="must")))
    keys = list(data)
    assert keys == sorted(keys)
    assert "deprecated" in data
    assert data["priority"] == "must"
    assert data["deprecated"] is False


# ---------------------------------------------------------------- AC3


def test_ac3_hash_of_criterion_matches_independent_sha256_of_literal():
    item = AcceptanceCriterion(id="AC-AUTH-001-1", text="Café ≥ 1")
    assert content_hash(item) == hashlib.sha256(AC_LITERAL.encode("utf-8")).hexdigest()


@pytest.mark.parametrize(
    "item",
    [
        AcceptanceCriterion(id="AC-1", text="x"),
        req(),
        adr(),
        spec(adrs=[{"id": "ADR-001", "status": "accepted"}]),
    ],
    ids=["criterion", "requirement", "adr", "spec_set"],
)
def test_ac3_hash_is_sha256_hex_of_canonical_json(item):
    h = content_hash(item)
    assert HEX64.match(h)
    assert h == hashlib.sha256(canonical_json(item)).hexdigest()
    assert content_hash(item.model_copy()) == h


@pytest.mark.parametrize("other", [{"id": "AC-2", "text": "x"}, {"id": "AC-1", "text": "y"}])
def test_ac3_changing_criterion_id_or_text_changes_hash(other):
    base = AcceptanceCriterion(id="AC-1", text="x")
    assert content_hash(AcceptanceCriterion(**other)) != content_hash(base)


# ---------------------------------------------------------------- AC4


def test_ac4_omitted_optionals_hash_same_as_defaults():
    explicit = req(constrained_by=[], components=[], acceptance_criteria=[], deprecated=False)
    omitted = Requirement.model_validate(
        {"id": "REQ-A-001", "title": "t", "statement": "s", "priority": "must"}
    )
    assert content_hash(omitted) == content_hash(explicit)


def test_ac4_adr_ignored_front_matter_does_not_change_hash():
    assert content_hash(adr(title="One")) == content_hash(adr(title="Two", date="2026"))


@pytest.mark.parametrize(
    "change",
    [{"id": "ADR-002"}, {"status": "proposed"}, {"body": "other"}],
    ids=["id", "status", "body"],
)
def test_ac4_adr_id_status_body_change_hash(change):
    assert content_hash(adr(**change)) != content_hash(adr())


# ---------------------------------------------------------------- AC5


def test_ac5_requirement_hash_ignores_list_order():
    a = req(
        acceptance_criteria=[ac("AC-1", "a"), ac("AC-2", "b")],
        components=["x", "y"],
        constrained_by=["ADR-001", "ADR-002"],
    )
    b = req(
        acceptance_criteria=[ac("AC-2", "b"), ac("AC-1", "a")],
        components=["y", "x"],
        constrained_by=["ADR-002", "ADR-001"],
    )
    assert content_hash(a) == content_hash(b)


def _ordered_spec(reverse):
    def order(items):
        return list(reversed(items)) if reverse else list(items)

    reqs = [
        req_data(
            "REQ-A-001",
            acceptance_criteria=order([ac("AC-1", "a"), ac("AC-2", "b")]),
            components=order(["x", "y"]),
            constrained_by=order(["ADR-001", "ADR-002"]),
        ),
        req_data("REQ-B-001", acceptance_criteria=[ac("AC-3", "c")]),
    ]
    adrs = [
        {"id": "ADR-001", "status": "accepted", "body": "one"},
        {"id": "ADR-002", "status": "proposed", "body": "two"},
    ]
    return spec(order(reqs), order(adrs), components=order(["auth", "web"]))


def test_ac5_spec_set_hash_ignores_order_and_json_is_sorted_by_id():
    forward, backward = _ordered_spec(False), _ordered_spec(True)
    assert content_hash(forward) == content_hash(backward)
    data = json.loads(canonical_json(backward))
    assert [r["id"] for r in data["requirements"]] == ["REQ-A-001", "REQ-B-001"]
    assert [a["id"] for a in data["adrs"]] == ["ADR-001", "ADR-002"]


def test_ac5_duplicate_ids_with_different_content_hash_independent_of_order():
    one = req_data("REQ-A-001", statement="first")
    two = req_data("REQ-A-001", statement="second")
    assert content_hash(spec([one, two])) == content_hash(spec([two, one]))


# ---------------------------------------------------------------- AC6


@pytest.mark.parametrize(
    "a, b",
    [
        ("text", "text "),
        ("text", "Text"),
        ("caf\u00e9", "cafe\u0301"),
    ],
    ids=["trailing-space", "case", "unicode-normalisation"],
)
def test_ac6_strings_are_hashed_as_parsed(a, b):
    assert content_hash(req(statement=a)) != content_hash(req(statement=b))


@pytest.mark.parametrize(
    "changed",
    [
        req_data("REQ-A-001", acceptance_criteria=[ac("AC-1", "changed")]),
        req_data("REQ-A-001", deprecated=True),
    ],
    ids=["criterion-text", "deprecated"],
)
def test_ac6_requirement_change_propagates_but_not_to_untouched_requirement(changed):
    other = req_data("REQ-B-001")
    before, after = spec([req_data(), other]), spec([changed, other])
    assert content_hash(req(**{k: v for k, v in changed.items() if k != "id"})) != content_hash(
        req()
    )
    assert content_hash(before) != content_hash(after)
    assert content_hash(Requirement.model_validate(other)) == content_hash(after.requirements[1])


def test_ac6_spec_set_hash_changes_with_component_or_adr_body():
    base = spec(adrs=[{"id": "ADR-001", "status": "accepted", "body": "one"}])
    more_components = spec(
        adrs=[{"id": "ADR-001", "status": "accepted", "body": "one"}],
        components=("auth", "web"),
    )
    new_body = spec(adrs=[{"id": "ADR-001", "status": "accepted", "body": "two"}])
    assert content_hash(more_components) != content_hash(base)
    assert content_hash(new_body) != content_hash(base)
