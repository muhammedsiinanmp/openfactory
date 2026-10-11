"""TASK-026: the policy hash.

Each test names the acceptance criterion it covers (AC5, AC6 in
docs/tasks/TASK-026-contract-completion-and-policy-hash.md).
"""

import hashlib
import importlib
from typing import Any

import pytest

from openfactory.domain.policy import Policy

DEFAULT_JSON = (
    '{"forbidden_paths":[],"max_attempts":2,"max_cost_usd":1.5,'
    '"max_runtime_s":1200,"protected_branches":["main","master"]}'
)


def policy_hash(policy: Policy) -> Any:
    # Imported lazily so the failure is the missing function, not the import.
    return importlib.import_module("openfactory.domain.spec_hash").policy_hash(policy)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_ac5_default_policy_hashes_its_canonical_json() -> None:
    assert policy_hash(Policy()) == sha(DEFAULT_JSON)


def test_ac5_explicit_defaults_hash_like_the_default_policy() -> None:
    explicit = Policy(
        forbidden_paths=[],
        protected_branches=["main", "master"],
        max_runtime_s=1200,
        max_attempts=2,
        max_cost_usd=1.50,
    )
    assert policy_hash(explicit) == policy_hash(Policy())


@pytest.mark.parametrize(
    "change",
    [
        {"forbidden_paths": ["x/**"]},
        {"protected_branches": ["main"]},
        {"max_runtime_s": 1201},
        {"max_attempts": 3},
        {"max_cost_usd": 2.0},
    ],
)
def test_ac5_changing_any_key_changes_the_hash(change: dict[str, Any]) -> None:
    assert policy_hash(Policy(**change)) != policy_hash(Policy())


def test_ac5_non_ascii_is_left_as_it_is() -> None:
    expected = DEFAULT_JSON.replace('"forbidden_paths":[]', '"forbidden_paths":["café/**"]')
    assert policy_hash(Policy(forbidden_paths=["café/**"])) == sha(expected)


def test_ac6_forbidden_paths_are_hashed_in_file_order() -> None:
    a = Policy(forbidden_paths=["a/**", "b/**"])
    b = Policy(forbidden_paths=["b/**", "a/**"])
    assert policy_hash(a) != policy_hash(b)


def test_ac6_protected_branches_are_hashed_in_file_order() -> None:
    a = Policy(protected_branches=["main", "master"])
    b = Policy(protected_branches=["master", "main"])
    assert policy_hash(a) != policy_hash(b)
