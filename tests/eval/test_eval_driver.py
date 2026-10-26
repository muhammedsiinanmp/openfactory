"""TASK-116 AC1..AC6: the eval driver (docs/tasks/TASK-116-eval-test.md), on TASK-114's synthetic
fixture with a stand-in LLMProvider. Writes to tmp_path only."""

import inspect
import tomllib
from pathlib import Path

# tests/eval/*.py; pytest's prepend import mode puts this directory on sys.path
import harness
import pytest
from test_harness import (  # noqa: F401  (`fixture` is a pytest fixture)
    FIXTURE_ADRS,
    fixture,
    make_case,
    requirements,
)

from openfactory.app.approve_spec import ApproveOutcome, ApproveResult
from openfactory.app.eval_results import EvalCaseResult, EvalRunResult, render_eval_results
from openfactory.app.impact import ImpactRefusal, ImpactResult
from openfactory.domain.eval_scoring import (
    EvalLabels,
    PrecisionRecall,
    RunScore,
    meets_targets,
    score_run,
)
from openfactory.domain.llm import LLMReply
from openfactory.ports.llm_provider import LLMError

BEHAVIORAL_STATEMENT = "Users can log in with a password."
COSMETIC_STATEMENT = "Users can log in, as before."
ADRS = {"ADR-001-jwt.md": FIXTURE_ADRS["ADR-001-jwt.md"]}

BEHAVIORAL_LABELS = (
    "tasks: [AUTH-001]\nfiles: [app/a.py]\ntests: []\nkinds: {REQ-AUTH-001: behavioral}\n"
)
COSMETIC_LABELS = "tasks: []\nfiles: []\ntests: []\nkinds: {REQ-AUTH-001: cosmetic}\n"


class Classifier:
    """Stand-in LLMProvider: the kind follows the case (by its statement); chosen calls fail."""

    def __init__(self, fail_on: frozenset[int] = frozenset()) -> None:
        self.fail_on = fail_on
        self.calls = 0

    def complete(self, prompt: str, schema: dict[str, object]) -> LLMReply:
        self.calls += 1
        if self.calls in self.fail_on:
            raise LLMError("claude exited 1", duration_s=0.1, timeout=False)
        kind = "behavioral" if BEHAVIORAL_STATEMENT in prompt else "cosmetic"
        change = {
            "req_id": "REQ-AUTH-001",
            "kind": kind,
            "rationale": "because",
            "obsolete_criteria": [],
            "new_work": ["password check"] if kind == "behavioral" else [],
        }
        return LLMReply(
            structured={"changes": [change]},
            model="stand-in",
            tokens_in=1,
            tokens_out=1,
            cost_usd=0.0,
            duration_s=0.1,
        )


def add_case(root: Path, name: str, statement: str, labels: str) -> None:
    case = make_case(root, name, requirements(statement), ADRS)
    (case / "labels.yaml").write_text(labels, encoding="utf-8")


@pytest.fixture
def cases(tmp_path: Path) -> Path:
    root = tmp_path / "cases"
    add_case(root, "c1_behavioral", BEHAVIORAL_STATEMENT, BEHAVIORAL_LABELS)
    add_case(root, "c2_cosmetic", COSMETIC_STATEMENT, COSMETIC_LABELS)
    return root


def run_eval(fixture: Path, cases: Path, tmp_path: Path, llm: Classifier) -> list[EvalRunResult]:  # noqa: F811
    return harness.run_eval(fixture, cases, tmp_path / "work", tmp_path / "out" / "r.md", llm=llm)


def labels_of(text: str) -> EvalLabels:
    from openfactory.app.eval_cases import parse_eval_labels

    return parse_eval_labels(text)


def test_run_eval_runs_every_case_three_times_on_its_own_copy(
    fixture: Path,  # noqa: F811
    cases: Path,
    tmp_path: Path,
) -> None:
    llm = Classifier()
    runs = run_eval(fixture, cases, tmp_path, llm)
    assert harness.EVAL_RUNS == 3
    assert len(runs) == 3
    assert llm.calls == 6
    for n in (1, 2, 3):
        for case_id in ("c1_behavioral", "c2_cosmetic"):
            assert (tmp_path / "work" / f"run_{n}" / case_id / ".openfactory").is_dir()
    for run in runs:
        assert [c.case_id for c in run.cases] == ["c1_behavioral", "c2_cosmetic"]
        assert run.cases[0].labels == labels_of(BEHAVIORAL_LABELS)
        assert run.cases[1].labels == labels_of(COSMETIC_LABELS)
        impacts = [c.impact for c in run.cases]
        assert all(i is not None for i in impacts)
        assert impacts[0] is not None
        assert impacts[0].tasks == ["AUTH-001"]
        assert impacts[0].files == ["app/a.py"]
        assert run.score == score_run([(c.labels, c.impact) for c in run.cases if c.impact])
        assert run.score.cosmetic_no_work


def test_failed_classifier_call_marks_only_that_case_and_run(
    fixture: Path,  # noqa: F811
    cases: Path,
    tmp_path: Path,
) -> None:
    # calls 1-2 are run 1, calls 3-4 run 2; call 3 is run 2's first case
    runs = run_eval(fixture, cases, tmp_path, Classifier(fail_on=frozenset({3})))
    assert len(runs) == 3
    failed = runs[1]
    assert [c.impact is None for c in failed.cases] == [True, False]
    other = failed.cases[1]
    assert other.impact is not None
    assert failed.score == score_run([(other.labels, other.impact)])
    assert all(c.impact is not None for c in runs[0].cases + runs[2].cases)
    assert 2 in harness.missed_runs(runs)
    assert "classifier call failed" in (tmp_path / "out" / "r.md").read_text(encoding="utf-8")


def test_missed_runs_counts_a_run_with_a_failed_case() -> None:
    good = PrecisionRecall(precision=1.0, recall=1.0)
    score = RunScore(files=good, tests=good, accuracy=1.0, cosmetic_no_work=True)
    labels = labels_of(COSMETIC_LABELS)
    ok = EvalRunResult(cases=[EvalCaseResult(case_id="a", labels=labels, impact=None)], score=score)
    assert meets_targets(score, any_case_failed=False)
    assert harness.missed_runs([ok]) == [1]


@pytest.mark.parametrize("refusal_at", ["approve", "impact"])
def test_refused_case_stops_the_eval_before_the_file(
    fixture: Path,  # noqa: F811
    cases: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    refusal_at: str,
) -> None:
    out = tmp_path / "out" / "r.md"
    if refusal_at == "approve":
        # same specs as the fixture's sv_01: approve spec gives nothing_to_approve
        refused = make_case(cases, "c0_refused", requirements("Users can log in."), FIXTURE_ADRS)
        (refused / "labels.yaml").write_text(COSMETIC_LABELS, encoding="utf-8")
        expected = ["c0_refused", "nothing_to_approve"]
    else:
        real = harness.run_case

        def refusing(fx: Path, case: Path, dest: Path, *, llm: Classifier) -> harness.CaseRun:
            if case.name != "c1_behavioral":
                return real(fx, case, dest, llm=llm)
            return harness.CaseRun(
                approve=ApproveResult(outcome=ApproveOutcome.approved, spec_version="sv_02"),
                impact=ImpactResult(refusal=ImpactRefusal.no_approved_plan),
            )

        monkeypatch.setattr(harness, "run_case", refusing)
        expected = ["c1_behavioral", "no_approved_plan"]
    with pytest.raises(harness.MalformedCase) as caught:
        harness.run_eval(fixture, cases, tmp_path / "work", out, llm=Classifier())
    for part in expected:
        assert part in str(caught.value)
    assert not out.exists()


def test_results_file_holds_the_render_even_when_a_run_misses(
    fixture: Path,  # noqa: F811
    cases: Path,
    tmp_path: Path,
) -> None:
    runs = run_eval(fixture, cases, tmp_path, Classifier(fail_on=frozenset({1})))
    assert harness.missed_runs(runs) != []
    assert (tmp_path / "out" / "r.md").read_text(encoding="utf-8") == render_eval_results(runs)


def test_missed_runs_lists_the_runs_that_miss_their_targets() -> None:
    good = PrecisionRecall(precision=1.0, recall=1.0)
    bad = PrecisionRecall(precision=0.2, recall=1.0)
    runs = [
        EvalRunResult(
            cases=[],
            score=RunScore(files=f, tests=good, accuracy=1.0, cosmetic_no_work=True),
        )
        for f in (good, bad, good)
    ]
    assert harness.missed_runs(runs) == [2]
    assert harness.missed_runs([runs[0], runs[2]]) == []


def test_load_cases_lists_cases_in_ascending_id(cases: Path) -> None:
    loaded = harness.load_cases(cases)
    assert [(i, p) for i, p, _ in loaded] == [
        ("c1_behavioral", cases / "c1_behavioral"),
        ("c2_cosmetic", cases / "c2_cosmetic"),
    ]
    assert loaded[0][2] == labels_of(BEHAVIORAL_LABELS)


@pytest.mark.parametrize("fault", ["no_cosmetic", "cosmetic_labels_a_task"])
def test_bad_case_set_stops_before_any_case_runs(fixture: Path, tmp_path: Path, fault: str) -> None:  # noqa: F811
    root = tmp_path / "cases"
    add_case(root, "c1_behavioral", BEHAVIORAL_STATEMENT, BEHAVIORAL_LABELS)
    if fault == "cosmetic_labels_a_task":
        bad = COSMETIC_LABELS.replace("tasks: []", "tasks: [AUTH-001]")
        add_case(root, "c2_cosmetic", COSMETIC_STATEMENT, bad)
    llm = Classifier()
    with pytest.raises(harness.MalformedCase) as caught:
        harness.run_eval(fixture, root, tmp_path / "work", tmp_path / "out" / "r.md", llm=llm)
    if fault == "cosmetic_labels_a_task":
        assert "c2_cosmetic" in str(caught.value)
    assert llm.calls == 0
    assert not (tmp_path / "work").exists()
    assert not (tmp_path / "out").exists()


def test_the_eval_test_is_one_eval_marked_test_on_the_real_inputs() -> None:
    import test_eval

    tests = [
        n for n, f in vars(test_eval).items() if n.startswith("test_") and inspect.isfunction(f)
    ]
    assert len(tests) == 1
    marks = [m.name for m in getattr(getattr(test_eval, tests[0]), "pytestmark", [])]
    assert marks == ["eval"]
    source = inspect.getsource(test_eval)
    for needle in ("ClaudeCodeLLM", "missed_runs", "eval-results.md", "fixture", "cases"):
        assert needle in source


def test_default_suite_deselects_eval_tests() -> None:
    config = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert "not eval" in config["tool"]["pytest"]["ini_options"]["addopts"]
