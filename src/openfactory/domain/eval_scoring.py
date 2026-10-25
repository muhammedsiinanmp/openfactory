"""Scoring of eval cases against their labels.

Implements "Metrics" and "Targets" under "Evaluation plan" in
docs/spec/phase1-spec.md: per-case precision and recall, the pooled run
figures, the classification accuracy, the cosmetic outcome and the target check.
Pure: the case files, the fixture and the results file are elsewhere.
"""

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from openfactory.domain.payloads import ChangeKind, ImpactComputedPayload

RECALL_TARGET = 0.9
PRECISION_TARGET = 0.7


class EvalLabels(BaseModel):
    """A case's ground truth: affected tasks, files, tests, and the modified requirements' kinds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tasks: list[str]
    files: list[str]
    tests: list[str]
    kinds: dict[str, ChangeKind]


class PrecisionRecall(BaseModel):
    """Precision and recall; `None` where the denominator is 0."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    precision: float | None
    recall: float | None


class Counts(BaseModel):
    """True positives, predicted and labelled, kept so runs pool counts rather than ratios."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hits: int
    predicted: int
    labelled: int

    def ratios(self) -> PrecisionRecall:
        return PrecisionRecall(
            precision=self.hits / self.predicted if self.predicted else None,
            recall=self.hits / self.labelled if self.labelled else None,
        )


class CaseScore(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tasks: PrecisionRecall
    files: PrecisionRecall
    tests: PrecisionRecall
    file_counts: Counts
    test_counts: Counts


class RunScore(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    files: PrecisionRecall
    tests: PrecisionRecall
    accuracy: float | None
    cosmetic_no_work: bool


def _counts(predicted: Sequence[str], labelled: Sequence[str]) -> Counts:
    p, t = set(predicted), set(labelled)
    return Counts(hits=len(p & t), predicted=len(p), labelled=len(t))


def score_case(labels: EvalLabels, impact: ImpactComputedPayload) -> CaseScore:
    """One case; the downstream tasks count as predicted tasks."""
    file_counts = _counts(impact.files, labels.files)
    test_counts = _counts(impact.tests, labels.tests)
    return CaseScore(
        tasks=_counts([*impact.tasks, *impact.downstream], labels.tasks).ratios(),
        files=file_counts.ratios(),
        tests=test_counts.ratios(),
        file_counts=file_counts,
        test_counts=test_counts,
    )


def _has_ground_truth(labels: EvalLabels) -> bool:
    return bool(labels.tasks or labels.files or labels.tests)


def _is_cosmetic(labels: EvalLabels) -> bool:
    return bool(labels.kinds) and all(kind == "cosmetic" for kind in labels.kinds.values())


def _no_work(impact: ImpactComputedPayload) -> bool:
    return not (impact.tasks or impact.downstream or impact.files or impact.tests)


def _pool(counts: Sequence[Counts]) -> PrecisionRecall:
    return Counts(
        hits=sum(c.hits for c in counts),
        predicted=sum(c.predicted for c in counts),
        labelled=sum(c.labelled for c in counts),
    ).ratios()


def score_run(cases: Sequence[tuple[EvalLabels, ImpactComputedPayload]]) -> RunScore:
    """One run's cases that have an `ImpactComputed`; empty-truth cases stay out of the pools."""
    scored = [score_case(labels, impact) for labels, impact in cases if _has_ground_truth(labels)]
    labelled = 0
    correct = 0
    for labels, impact in cases:
        classified = {r.id: r.kind for r in impact.requirements}
        for requirement_id, kind in labels.kinds.items():
            labelled += 1
            correct += classified.get(requirement_id) == kind
    return RunScore(
        files=_pool([s.file_counts for s in scored]),
        tests=_pool([s.test_counts for s in scored]),
        accuracy=correct / labelled if labelled else None,
        cosmetic_no_work=all(_no_work(impact) for labels, impact in cases if _is_cosmetic(labels)),
    )


def _meets(value: float | None, target: float) -> bool:
    return value is not None and value >= target


def meets_targets(run: RunScore, *, any_case_failed: bool) -> bool:
    """A run with a failed case misses every target (SC-226)."""
    return (
        not any_case_failed
        and run.cosmetic_no_work
        and all(_meets(pr.recall, RECALL_TARGET) for pr in (run.files, run.tests))
        and all(_meets(pr.precision, PRECISION_TARGET) for pr in (run.files, run.tests))
    )
