"""The eval (spec "Evaluation plan" › Run): every case of the real fixture, three runs with the
real classifier; writes docs/generated/eval-results.md, then fails when any run misses a target.
Run deliberately with `uv run pytest tests/eval -m eval`.
"""

from pathlib import Path

# tests/eval/*.py; pytest's prepend import mode puts this directory on sys.path
import harness
import pytest

from openfactory.adapters.claude_code_llm import ClaudeCodeLLM

EVAL_DIR = Path(__file__).parent
FIXTURE = EVAL_DIR / "fixture"
CASES = EVAL_DIR / "cases"
RESULTS = EVAL_DIR.parent.parent / "docs" / "generated" / "eval-results.md"


@pytest.mark.eval
def test_eval(tmp_path: Path) -> None:
    for path in (FIXTURE / "repo.bundle", FIXTURE / "openfactory.db", CASES):
        if not path.exists():
            pytest.fail(f"missing {path}")
    runs = harness.run_eval(FIXTURE, CASES, tmp_path, RESULTS, llm=ClaudeCodeLLM())
    assert harness.missed_runs(runs) == []
