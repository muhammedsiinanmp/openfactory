"""TASK-039: path patterns and the path check (AC1..AC5).

See docs/tasks/TASK-039-path-patterns-and-path-check.md.
"""

import pytest

from openfactory.domain.contracts import Limits, TaskContract
from openfactory.domain.path_patterns import matches, matches_any, violating_paths

MATCH_CASES = [
    # AC1: `*`, `?`, whole-path match, case-sensitive
    ("app/*.py", "app/main.py", True),
    ("app/*.py", "app/auth/main.py", False),
    ("app/*.py", "app/main.pyc", False),
    ("app/*.py", "src/app/main.py", False),
    ("app/mod?.py", "app/mod1.py", True),
    ("app/mod?.py", "app/mod.py", False),
    ("app/mod?.py", "app/mod12.py", False),
    ("a?b", "a/b", False),
    ("app/Main.py", "app/main.py", False),
    # AC2: `**` as a whole segment
    ("app/**", "app/main.py", True),
    ("app/**", "app/auth/views/login.py", True),
    ("app/**", "application/main.py", False),
    ("app/**", "src/app/main.py", False),
    ("app/**/test_*.py", "app/test_a.py", True),
    ("app/**/test_*.py", "app/x/y/test_a.py", True),
    ("app/**/test_*.py", "app/x/a.py", False),
    ("**/conftest.py", "conftest.py", True),
    ("**/conftest.py", "tests/unit/conftest.py", True),
    # AC3: trailing `/`, and no `/` means any directory
    ("docs/", "docs/a.md", True),
    ("docs/", "docs/x/b.md", True),
    ("docs/", "src/docs/a.md", False),
    (".env", ".env", True),
    (".env", "services/api/.env", True),
    (".env", ".envrc", False),
    (".env.*", ".env.local", True),
    (".env.*", "deploy/.env.prod", True),
    (".env.*", ".env", False),
    ("*.py", "setup.py", True),
    ("*.py", "app/auth/login.py", True),
    ("*.py", "app/login.pyi", False),
    # AC4: `!` and `[` are literal, `.` is literal
    ("!app/main.py", "app/main.py", False),
    ("!app/main.py", "!app/main.py", True),
    ("file[1].txt", "file[1].txt", True),
    ("file[1].txt", "file1.txt", False),
    ("[ab].py", "a.py", False),
    (".env", "xenv", False),
]


@pytest.mark.parametrize(("pattern", "path", "expected"), MATCH_CASES)
def test_matches(pattern: str, path: str, expected: bool) -> None:
    assert matches(pattern, path) is expected


def test_matches_any_is_true_when_one_pattern_matches() -> None:
    assert matches_any(["docs/**", "*.py"], "app/main.py") is True
    assert matches_any(["docs/**", "*.md"], "app/main.py") is False
    assert matches_any([], "app/main.py") is False


def contract() -> TaskContract:
    return TaskContract(
        task_id="TASK-001",
        objective="o",
        requirements=["REQ-AUTH-001"],
        acceptance_criteria=["AC-AUTH-001-1"],
        components=["auth"],
        role="implementer",
        allowed_paths=["app/auth/**", "tests/auth/**"],
        forbidden_paths=["specs/**", ".openfactory/**", ".env", ".env.*", "app/auth/secrets/**"],
        required_gates=["path_check", "ruff", "pytest", "gitleaks", "review"],
        limits=Limits(max_runtime_s=60, max_attempts=2, max_cost_usd=1.0),
    )


def test_violating_paths_in_input_order_and_both_conditions() -> None:
    changed = [
        "app/auth/login.py",
        "app/main.py",
        "tests/auth/test_login.py",
        "specs/requirements.yaml",
        "app/auth/secrets/key.pem",
        "app/auth/.env",
    ]
    assert violating_paths(changed, contract()) == [
        "app/main.py",
        "specs/requirements.yaml",
        "app/auth/secrets/key.pem",
        "app/auth/.env",
    ]


def test_violating_paths_empty_when_all_allowed_or_nothing_changed() -> None:
    assert violating_paths(["app/auth/login.py", "tests/auth/test_login.py"], contract()) == []
    assert violating_paths([], contract()) == []


def test_violating_paths_leaves_contract_and_input_unchanged() -> None:
    c = contract()
    before = c.model_copy(deep=True)
    changed = ["app/main.py", "app/auth/login.py"]
    violating_paths(changed, c)
    assert c == before
    assert changed == ["app/main.py", "app/auth/login.py"]
