"""Eval results: renders the text of `docs/generated/eval-results.md`.

Implements the results part of "Evaluation plan" › Run and Targets in
docs/spec/phase1-spec.md; the layout is the TASK-115 row of docs/decisions.md. Pure: the
eval builds each run's `RunScore` and writes the file.
"""

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from openfactory.domain.eval_scoring import EvalLabels, PrecisionRecall, RunScore, score_case
from openfactory.domain.payloads import ImpactComputedPayload

FAILED = "classifier call failed"


class EvalCaseResult(BaseModel):
    """One case of one run; `impact` is `None` when the case's `impact` failed (SC-226)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    labels: EvalLabels
    impact: ImpactComputedPayload | None


class EvalRunResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cases: list[EvalCaseResult]
    score: RunScore


def _ratio(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


def _kinds(kinds: dict[str, str]) -> str:
    return ", ".join(f"{rid} {kinds[rid]}" for rid in sorted(kinds)) or "-"


def _row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _table(head: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    return [_row(head), _row(["---"] * len(head)), *(_row(r) for r in rows)]


def _pair(pr: PrecisionRecall) -> list[str]:
    return [_ratio(pr.precision), _ratio(pr.recall)]


def _case_row(run: int, case: EvalCaseResult) -> list[str]:
    if case.impact is None:
        return [str(run), case.case_id, *[FAILED] * 8]
    score = score_case(case.labels, case.impact)
    classified = {r.id: r.kind for r in case.impact.requirements if r.kind is not None}
    return [
        str(run),
        case.case_id,
        _kinds(dict(case.labels.kinds)),
        _kinds(dict(classified)),
        *_pair(score.tasks),
        *_pair(score.files),
        *_pair(score.tests),
    ]


def _figures(score: RunScore) -> list[float | None]:
    return [
        score.files.precision,
        score.files.recall,
        score.tests.precision,
        score.tests.recall,
        score.accuracy,
    ]


def _spread(name: str, values: Sequence[float | None]) -> list[str]:
    defined = [v for v in values if v is not None]
    if not defined:
        return [name, "-", "-"]
    return [name, _ratio(min(defined)), _ratio(max(defined))]


def render_eval_results(runs: Sequence[EvalRunResult]) -> str:
    """Cases in run order then `case_id`; each run's figures as given; ends in a line break."""
    case_rows = [
        _case_row(n, case)
        for n, run in enumerate(runs, start=1)
        for case in sorted(run.cases, key=lambda c: c.case_id)
    ]
    run_rows = [
        [
            str(n),
            *(_ratio(v) for v in _figures(run.score)),
            "yes" if run.score.cosmetic_no_work else "no",
        ]
        for n, run in enumerate(runs, start=1)
    ]
    names = ["Files P", "Files R", "Tests P", "Tests R", "Accuracy"]
    figures = [_figures(run.score) for run in runs]
    spread_rows = [_spread(name, [f[i] for f in figures]) for i, name in enumerate(names)]
    lines = [
        "# Eval results",
        "",
        "## Cases",
        "",
        *_table(
            ["Run", "Case", "Labelled kinds", "Classified kinds", "Tasks P", "Tasks R"]
            + ["Files P", "Files R", "Tests P", "Tests R"],
            case_rows,
        ),
        "",
        "## Runs",
        "",
        *_table(["Run", *names, "Cosmetic no work"], run_rows),
        "",
        "## Spread",
        "",
        *_table(["Figure", "Min", "Max"], spread_rows),
    ]
    return "\n".join(lines) + "\n"
