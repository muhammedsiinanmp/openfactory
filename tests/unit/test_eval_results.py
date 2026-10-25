"""TASK-115: eval results renderer (AC1..AC6 in docs/tasks/TASK-115-eval-results-renderer.md)."""

import ast
from pathlib import Path

from openfactory.app.eval_results import EvalCaseResult, EvalRunResult, render_eval_results
from openfactory.domain.eval_scoring import EvalLabels, PrecisionRecall, RunScore
from openfactory.domain.payloads import ImpactComputedPayload, RequirementImpact

MODULE = Path(__file__).parents[2] / "src/openfactory/app/eval_results.py"
FAILED = "classifier call failed"


def impact(tasks=(), downstream=(), files=(), tests=(), reqs=None) -> ImpactComputedPayload:
    reqs = reqs or {}
    return ImpactComputedPayload(
        from_version="sv_01",
        to_version="sv_02",
        run_id=None,
        requirements=[
            RequirementImpact(
                id=rid,
                change="modified" if kind else "added",
                kind=kind,
                rationale="r" if kind else None,
                obsolete_criteria=[],
                new_work=[],
            )
            for rid, kind in reqs.items()
        ],
        adrs=[],
        tasks=list(tasks),
        downstream=list(downstream),
        files=list(files),
        tests=list(tests),
    )


def labels(tasks=(), files=(), tests=(), kinds=None) -> EvalLabels:
    return EvalLabels(tasks=list(tasks), files=list(files), tests=list(tests), kinds=kinds or {})


def alpha() -> EvalCaseResult:
    # tasks: 2 predicted (downstream counts), 2 hits, 3 labelled -> 1.000 / 0.667
    # files: 4 predicted, 3 hits, 5 labelled -> 3/4 and 3/5
    return EvalCaseResult(
        case_id="alpha",
        labels=labels(
            tasks=["TASK-001", "TASK-002", "TASK-003"],
            files=[f"f{i}" for i in range(5)],
            kinds={"REQ-002": "behavioral", "REQ-001": "cosmetic"},
        ),
        impact=impact(
            tasks=["TASK-001"],
            downstream=["TASK-002"],
            files=["f0", "f1", "f2", "x"],
            reqs={"REQ-002": "replacement", "REQ-001": "cosmetic", "REQ-009": None},
        ),
    )


def beta() -> EvalCaseResult:
    return EvalCaseResult(case_id="beta", labels=labels(), impact=impact())


def alpha_failed() -> EvalCaseResult:
    return EvalCaseResult(case_id="alpha", labels=alpha().labels, impact=None)


def pr(p: float | None, r: float | None) -> PrecisionRecall:
    return PrecisionRecall(precision=p, recall=r)


RUN1 = EvalRunResult(
    cases=[beta(), alpha()],  # deliberately not in case_id order
    score=RunScore(
        files=pr(26 / 29, 0.9), tests=pr(None, None), accuracy=0.5, cosmetic_no_work=True
    ),
)
RUN2 = EvalRunResult(
    cases=[beta(), alpha_failed()],
    score=RunScore(
        files=pr(0.5, None), tests=pr(None, None), accuracy=None, cosmetic_no_work=False
    ),
)

CASES_HEAD = (
    "| Run | Case | Labelled kinds | Classified kinds | Tasks P | Tasks R "
    "| Files P | Files R | Tests P | Tests R |"
)
ALPHA_ROW = (
    "| 1 | alpha | REQ-001 cosmetic, REQ-002 behavioral | REQ-001 cosmetic, REQ-002 replacement "
    "| 1.000 | 0.667 | 0.750 | 0.600 | - | - |"
)
BETA_ROW = "| {n} | beta | - | - | - | - | - | - | - | - |"
FAILED_ROW = "| 2 | alpha | " + " | ".join([FAILED] * 8) + " |"

EXPECTED = "\n".join(
    [
        "# Eval results",
        "",
        "## Cases",
        "",
        CASES_HEAD,
        "| " + " | ".join(["---"] * 10) + " |",
        ALPHA_ROW,
        BETA_ROW.format(n=1),
        FAILED_ROW,
        BETA_ROW.format(n=2),
        "",
        "## Runs",
        "",
        "| Run | Files P | Files R | Tests P | Tests R | Accuracy | Cosmetic no work |",
        "| " + " | ".join(["---"] * 7) + " |",
        "| 1 | 0.897 | 0.900 | - | - | 0.500 | yes |",
        "| 2 | 0.500 | - | - | - | - | no |",
        "",
        "## Spread",
        "",
        "| Figure | Min | Max |",
        "| --- | --- | --- |",
        "| Files P | 0.500 | 0.897 |",
        "| Files R | 0.900 | 0.900 |",
        "| Tests P | - | - |",
        "| Tests R | - | - |",
        "| Accuracy | 0.500 | 0.500 |",
        "",
    ]
)


# AC1..AC4
def test_two_runs_with_one_failed_case_render_exactly() -> None:
    assert render_eval_results([RUN1, RUN2]) == EXPECTED


# AC1
def test_case_rows_follow_run_order_then_case_id() -> None:
    lines = render_eval_results([RUN1, RUN2]).splitlines()
    rows = [line for line in lines if line.startswith(("| 1 | a", "| 1 | b", "| 2 | a", "| 2 | b"))]
    assert [r.split(" | ")[:2] for r in rows] == [
        ["| 1", "alpha"],
        ["| 1", "beta"],
        ["| 2", "alpha"],
        ["| 2", "beta"],
    ]


# AC2
def test_failed_case_keeps_run_and_id_and_replaces_every_other_cell() -> None:
    text = render_eval_results([RUN1, RUN2])
    row = next(line for line in text.splitlines() if line.startswith("| 2 | alpha"))
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert cells[:2] == ["2", "alpha"]
    assert cells[2:] == [FAILED] * 8


# AC3, AC4
def test_run_with_undefined_pooled_figures_prints_dashes_and_spread_dashes() -> None:
    only = EvalRunResult(
        cases=[beta()],
        score=RunScore(
            files=pr(None, None), tests=pr(None, None), accuracy=None, cosmetic_no_work=True
        ),
    )
    text = render_eval_results([only])
    assert "| 1 | - | - | - | - | - | yes |" in text
    for name in ("Files P", "Files R", "Tests P", "Tests R", "Accuracy"):
        assert f"| {name} | - | - |" in text


# AC3
def test_given_run_score_is_used_as_is() -> None:
    odd = EvalRunResult(
        cases=[beta()],
        score=RunScore(
            files=pr(0.25, 0.125), tests=pr(1.0, 0.0), accuracy=0.75, cosmetic_no_work=False
        ),
    )
    assert "| 1 | 0.250 | 0.125 | 1.000 | 0.000 | 0.750 | no |" in render_eval_results([odd])


# AC5
def test_render_is_deterministic_and_ends_in_a_line_break() -> None:
    first = render_eval_results([RUN1, RUN2])
    assert render_eval_results([RUN1, RUN2]) == first
    assert first.endswith("\n")


# AC5
def test_module_imports_only_domain_pydantic_and_stdlib() -> None:
    tree = ast.parse(MODULE.read_text())
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    for m in mods:
        top = m.split(".")[0]
        assert top != "openfactory" or m.startswith("openfactory.domain"), m
        assert top not in {"sqlite3", "subprocess", "requests", "httpx"}, m
