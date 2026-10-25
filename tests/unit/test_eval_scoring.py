"""TASK-112: eval scoring (AC1..AC6 in docs/tasks/TASK-112-eval-scoring.md)."""

import ast
from pathlib import Path

import pytest

from openfactory.domain.eval_scoring import (
    PRECISION_TARGET,
    RECALL_TARGET,
    EvalLabels,
    PrecisionRecall,
    RunScore,
    meets_targets,
    score_case,
    score_run,
)
from openfactory.domain.payloads import ImpactComputedPayload, RequirementImpact

MODULE = Path(__file__).parents[2] / "src/openfactory/domain/eval_scoring.py"


def impact(tasks=(), downstream=(), files=(), tests=(), kinds=None) -> ImpactComputedPayload:
    reqs = [
        RequirementImpact(
            id=rid,
            change="modified",
            kind=kind,
            rationale="r",
            obsolete_criteria=[],
            new_work=[],
        )
        for rid, kind in (kinds or {}).items()
    ]
    return ImpactComputedPayload(
        from_version="sv_01",
        to_version="sv_02",
        run_id=None,
        requirements=reqs,
        adrs=[],
        tasks=list(tasks),
        downstream=list(downstream),
        files=list(files),
        tests=list(tests),
    )


def labels(tasks=(), files=(), tests=(), kinds=None) -> EvalLabels:
    return EvalLabels(tasks=list(tasks), files=list(files), tests=list(tests), kinds=kinds or {})


def names(prefix: str, n: int) -> list[str]:
    return [f"{prefix}{i}" for i in range(n)]


# AC1
def test_score_case_files_worked_example() -> None:
    s = score_case(
        labels(files=names("f", 5)),
        impact(files=["f0", "f1", "f2", "x"]),
    )
    assert s.files == PrecisionRecall(precision=0.75, recall=0.6)


def test_score_case_downstream_labelled_is_true_positive() -> None:
    s = score_case(
        labels(tasks=["TASK-001", "TASK-002"]),
        impact(tasks=["TASK-001"], downstream=["TASK-002"]),
    )
    assert s.tasks == PrecisionRecall(precision=1.0, recall=1.0)


def test_score_case_undefined_is_none() -> None:
    s = score_case(labels(), impact())
    assert s.files == PrecisionRecall(precision=None, recall=None)
    assert s.tests == PrecisionRecall(precision=None, recall=None)
    assert s.tasks == PrecisionRecall(precision=None, recall=None)
    s = score_case(labels(tests=["t"]), impact())
    assert s.tests == PrecisionRecall(precision=None, recall=0.0)
    s = score_case(labels(), impact(tests=["t"]))
    assert s.tests == PrecisionRecall(precision=0.0, recall=None)


# AC2
def test_score_run_pools_counts_not_ratios() -> None:
    a = (labels(files=names("a", 2), tests=["t"]), impact(files=["a0"], tests=["t"]))
    b = (
        labels(files=names("b", 8), tests=["u"]),
        impact(files=names("b", 8) + ["z", "y"], tests=["u"]),
    )
    r = score_run([a, b])
    # tp 1+8, predicted 1+10, labelled 2+8 (not the mean of 1.0/0.5 and 0.8/1.0)
    assert r.files == PrecisionRecall(precision=9 / 11, recall=9 / 10)
    assert r.tests == PrecisionRecall(precision=1.0, recall=1.0)


def test_score_run_empty_ground_truth_case_left_out() -> None:
    real = (labels(files=["f"], tests=["t"]), impact(files=["f"], tests=["t"]))
    empty = (labels(), impact(files=["x", "y"], tests=["q"]))
    r = score_run([real, empty])
    assert r.files == PrecisionRecall(precision=1.0, recall=1.0)
    assert r.tests == PrecisionRecall(precision=1.0, recall=1.0)


def test_score_run_case_enters_both_pools_when_any_list_non_empty() -> None:
    # labels files only; predicted tests still count against test precision
    c = (labels(files=["f"]), impact(files=["f"], tests=["t1", "t2"]))
    r = score_run([c])
    assert r.tests == PrecisionRecall(precision=0.0, recall=None)
    # tasks-only ground truth also enters the pools
    c2 = (labels(tasks=["TASK-001"]), impact(tasks=["TASK-001"], files=["x"]))
    assert score_run([c2]).files == PrecisionRecall(precision=0.0, recall=None)


def test_score_run_kinds_do_not_make_ground_truth_non_empty() -> None:
    c = (labels(kinds={"REQ-A-001": "cosmetic"}), impact(files=["x"]))
    r = score_run([c])
    assert r.files == PrecisionRecall(precision=None, recall=None)


def test_score_run_no_included_cases_gives_none() -> None:
    r = score_run([(labels(), impact())])
    assert r.files == PrecisionRecall(precision=None, recall=None)
    assert r.tests == PrecisionRecall(precision=None, recall=None)


# AC3
def test_accuracy_counts_labelled_requirements_over_all_cases() -> None:
    c1 = (
        labels(kinds={"REQ-A-001": "behavioral", "REQ-A-002": "cosmetic"}),
        impact(kinds={"REQ-A-001": "behavioral", "REQ-A-002": "replacement"}),
    )
    c2 = (labels(kinds={"REQ-B-001": "cosmetic"}), impact(kinds={"REQ-B-001": "cosmetic"}))
    assert score_run([c1, c2]).accuracy == pytest.approx(2 / 3)


def test_accuracy_missing_requirement_counts_as_wrong() -> None:
    c = (labels(kinds={"REQ-A-001": "behavioral"}), impact())
    assert score_run([c]).accuracy == 0.0


def test_accuracy_none_without_labelled_kinds() -> None:
    assert score_run([(labels(files=["f"]), impact(files=["f"]))]).accuracy is None


# AC4
COSMETIC = {"REQ-A-001": "cosmetic"}


def cosmetic_run(**work: list[str]) -> RunScore:
    return score_run([(labels(kinds=COSMETIC), impact(kinds=COSMETIC, **work))])


def test_cosmetic_no_work_true_when_all_empty() -> None:
    assert cosmetic_run().cosmetic_no_work is True


@pytest.mark.parametrize("field", ["tasks", "downstream", "files", "tests"])
def test_cosmetic_no_work_false_on_any_work(field: str) -> None:
    value = ["TASK-001"] if field in ("tasks", "downstream") else ["x"]
    assert cosmetic_run(**{field: value}).cosmetic_no_work is False


def test_cosmetic_no_work_true_without_cosmetic_case() -> None:
    c = (labels(files=["f"], kinds={"REQ-A-001": "behavioral"}), impact(files=["f", "x"]))
    assert score_run([c]).cosmetic_no_work is True


def test_mixed_kinds_case_is_not_cosmetic() -> None:
    kinds = {"REQ-A-001": "cosmetic", "REQ-A-002": "behavioral"}
    c = (labels(files=["f"], kinds=kinds), impact(files=["f"], kinds=kinds))
    assert score_run([c]).cosmetic_no_work is True


def test_case_without_kinds_is_not_cosmetic() -> None:
    assert score_run([(labels(), impact(files=["x"]))]).cosmetic_no_work is True


# AC5
def run(fp=1.0, fr=1.0, tp=1.0, tr=1.0, cosmetic=True) -> RunScore:
    return RunScore(
        files=PrecisionRecall(precision=fp, recall=fr),
        tests=PrecisionRecall(precision=tp, recall=tr),
        accuracy=None,
        cosmetic_no_work=cosmetic,
    )


def test_targets_constants() -> None:
    assert RECALL_TARGET == 0.9
    assert PRECISION_TARGET == 0.7


def test_meets_targets_all_good() -> None:
    assert meets_targets(run(), any_case_failed=False) is True


def test_meets_targets_boundary_from_counts() -> None:
    # 9 of 10 labelled found (recall 0.9)
    c = (
        labels(files=names("f", 10), tests=names("t", 10)),
        impact(files=names("f", 9), tests=names("t", 9)),
    )
    r = score_run([c])
    assert r.files.recall == pytest.approx(0.9)
    assert meets_targets(run(fp=7 / 10, fr=9 / 10, tp=7 / 10, tr=9 / 10), any_case_failed=False)


@pytest.mark.parametrize(
    "kw",
    [
        {"fr": 0.89},
        {"tr": 0.89},
        {"fp": 0.69},
        {"tp": 0.69},
        {"fp": None},
        {"tr": None},
        {"cosmetic": False},
    ],
)
def test_meets_targets_misses(kw: dict) -> None:
    assert meets_targets(run(**kw), any_case_failed=False) is False


def test_failed_case_misses_every_target() -> None:
    assert meets_targets(run(), any_case_failed=True) is False


# AC6
def test_module_imports_only_domain_pydantic_stdlib() -> None:
    tree = ast.parse(MODULE.read_text())
    allowed = {"openfactory", "pydantic", "collections", "typing", "__future__"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots = [node.module.split(".")[0]]
            if roots == ["openfactory"]:
                assert node.module.startswith("openfactory.domain")
        else:
            continue
        assert set(roots) <= allowed, roots
