"""TASK-008: policy model and loader.

Each test names the acceptance criterion it covers (AC1..AC6 in
docs/tasks/TASK-008-policy-model-loader.md). The loader is driven through an in-memory
fake SpecFiles; no filesystem or database is used. The names under test are imported
inside each test so a missing module fails that test rather than the whole file.
"""

import ast
from pathlib import Path
from typing import Any

import pytest

from openfactory.app.spec_loader import load_spec

POLICY_PATH = Path(__file__).resolve().parents[2] / "src" / "openfactory" / "domain" / "policy.py"
SUBJECT = "specs/policies.yaml"

EXAMPLE_POLICY = """\
# policies.yaml
protected_branches: [main, master]
forbidden_paths: []
max_attempts: 2
max_runtime_s: 1200
max_cost_usd: 1.50
"""

REQUIREMENTS = """\
components: [auth]
requirements:
  - id: REQ-AUTH-001
    title: Login with membership number
    statement: Users authenticate using their membership number and password.
    priority: must
    acceptance_criteria:
      - id: AC-AUTH-001-1
        text: Valid membership number and password returns a JWT.
"""


class RecordingSpecFiles:
    """Dict of path (relative to specs/) to text; records every call made to it."""

    def __init__(self, files: dict[str, str | None], bad_utf8: set[str] | None = None):
        self.files = files
        self.bad_utf8 = bad_utf8 or set()
        self.read_paths: list[str] = []
        self.list_adrs_called = False

    def read(self, path: str) -> str | None:
        self.read_paths.append(path)
        if path in self.bad_utf8:
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
        return self.files.get(path)

    def list_adrs(self) -> list[str]:
        self.list_adrs_called = True
        paths = set(self.files) | self.bad_utf8
        return sorted(p for p in paths if p.startswith("adrs/") and p.endswith(".md"))


def load(text: str | None) -> Any:
    from openfactory.app.spec_loader import load_policy

    return load_policy(RecordingSpecFiles({"policies.yaml": text}))


def assert_single_schema(result: Any, *, names: str | None = None) -> None:
    assert result.policy is None
    assert len(result.violations) == 1
    (v,) = result.violations
    assert v.rule.value == "schema"
    assert v.subject == SUBJECT
    assert v.message
    if names is not None:
        assert names in v.message


def defaults() -> Any:
    from openfactory.domain.policy import Policy

    return Policy()


def test_ac1_policy_defaults() -> None:
    p = defaults()
    assert p.protected_branches == ["main", "master"]
    assert p.forbidden_paths == []
    assert p.max_attempts == 2
    assert p.max_runtime_s == 1200
    assert p.max_cost_usd == 1.50


def test_ac1_spec_example_loads_as_defaults() -> None:
    result = load(EXAMPLE_POLICY)
    assert result.violations == []
    assert result.policy == defaults()


def test_ac1_baseline_forbidden_paths() -> None:
    from openfactory.domain.policy import BASELINE_FORBIDDEN_PATHS

    assert BASELINE_FORBIDDEN_PATHS == ("specs/**", ".openfactory/**", ".env", ".env.*")


def test_ac1_policy_module_is_pure() -> None:
    tree = ast.parse(POLICY_PATH.read_text())
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    forbidden = ("openfactory.adapters", "openfactory.app", "openfactory.ports")
    assert not [m for m in modules if m.startswith(forbidden)]


def test_ac2_single_key_leaves_other_defaults() -> None:
    result = load("max_attempts: 3\n")
    assert result.violations == []
    assert result.policy == defaults().model_copy(update={"max_attempts": 3})


def test_ac2_forbidden_paths_not_merged_with_baseline() -> None:
    result = load("forbidden_paths: [secrets/**]\n")
    assert result.violations == []
    assert result.policy == defaults().model_copy(update={"forbidden_paths": ["secrets/**"]})
    assert result.policy.forbidden_paths == ["secrets/**"]


@pytest.mark.parametrize(
    "text", ["{}\n", "", "# only a comment\n"], ids=["braces", "empty", "comment"]
)
def test_ac2_empty_documents_give_defaults(text: str) -> None:
    result = load(text)
    assert result.violations == []
    assert result.policy == defaults()


def test_ac3_unknown_key_is_named() -> None:
    assert_single_schema(load("max_retries: 3\n"), names="max_retries")


@pytest.mark.parametrize(
    "text",
    ["max_attempts: 2\nmax_attempts: 3\n", "max_attempts: [unclosed\n", "- main\n- master\n"],
    ids=["duplicate-key", "syntax-error", "top-level-list"],
)
def test_ac3_unparseable_policy(text: str) -> None:
    assert_single_schema(load(text))


@pytest.mark.parametrize(
    "text, key",
    [
        ("max_attempts: 0\n", "max_attempts"),
        ("max_runtime_s: -1\n", "max_runtime_s"),
        ("max_cost_usd: 0\n", "max_cost_usd"),
    ],
)
def test_ac4_non_positive_limit(text: str, key: str) -> None:
    assert_single_schema(load(text), names=key)


def test_ac4_all_three_limits_bad() -> None:
    result = load("max_attempts: 0\nmax_runtime_s: -1\nmax_cost_usd: 0\n")
    assert result.policy is None
    assert len(result.violations) == 3
    assert all(v.rule.value == "schema" and v.subject == SUBJECT for v in result.violations)
    for key in ("max_attempts", "max_runtime_s", "max_cost_usd"):
        assert sum(key in v.message for v in result.violations) == 1


def test_ac4_small_positive_cost_is_valid() -> None:
    result = load("max_cost_usd: 0.01\n")
    assert result.violations == []
    assert result.policy is not None
    assert result.policy.max_cost_usd == 0.01


def test_ac5_missing_file() -> None:
    result = load(None)
    assert_single_schema(result, names="run openfactory init")


def test_ac5_file_not_utf8() -> None:
    from openfactory.app.spec_loader import load_policy

    result = load_policy(RecordingSpecFiles({}, bad_utf8={"policies.yaml"}))
    assert_single_schema(result, names="not valid UTF-8")


@pytest.mark.parametrize("text", [EXAMPLE_POLICY, "max_retries: 3\n", None])
def test_ac5_exactly_one_of_policy_or_violations(text: str | None) -> None:
    result = load(text)
    if result.violations:
        assert result.policy is None
    else:
        from openfactory.domain.policy import Policy

        assert isinstance(result.policy, Policy)


def test_ac6_reads_only_policies_yaml() -> None:
    from openfactory.app.spec_loader import load_policy

    files = RecordingSpecFiles({"policies.yaml": EXAMPLE_POLICY})  # no requirements.yaml
    result = load_policy(files)
    assert result.violations == []
    assert result.policy is not None
    assert files.read_paths == ["policies.yaml"]
    assert files.list_adrs_called is False


def test_ac6_load_spec_ignores_policy() -> None:
    # Fail on the missing behaviour first: the policy loader must exist.
    from openfactory.app.spec_loader import load_policy  # noqa: F401

    results = [
        load_spec(RecordingSpecFiles({"requirements.yaml": REQUIREMENTS, "policies.yaml": policy}))
        for policy in (EXAMPLE_POLICY, None, "max_retries: 3\n")
    ]
    assert results[0].violations == []
    assert results[0].spec is not None
    assert results[0] == results[1] == results[2]
