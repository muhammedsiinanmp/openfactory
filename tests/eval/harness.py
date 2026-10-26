"""The eval's per-case procedure: restore a copy of the fixture, swap in a case's spec files,
run `approve spec` and `impact` through the use cases (spec "Evaluation plan" › Procedure,
ADR-021); and the driver that runs every case three times, scores the runs and writes the
results (spec "Evaluation plan" › Targets, Run). Test code, so it wires adapters and app itself
(TASK-114 decisions row).
"""

import shutil
import subprocess
from contextlib import closing
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from openfactory.adapters.filesystem_spec_files import FilesystemSpecFiles
from openfactory.adapters.sqlite_plans import SqlitePlans
from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.adapters.sqlite_runs import SqliteRuns
from openfactory.adapters.sqlite_spec_versions import SqliteSpecVersions
from openfactory.adapters.sqlite_traces import SqliteTraces
from openfactory.app.approve_spec import ApproveOutcome, ApproveResult, approve_spec
from openfactory.app.eval_cases import parse_eval_labels
from openfactory.app.eval_results import EvalCaseResult, EvalRunResult, render_eval_results
from openfactory.app.impact import ImpactResult, compute_impact
from openfactory.domain.eval_scoring import EvalLabels, meets_targets, score_run
from openfactory.ports.llm_provider import LLMProvider

EVAL_RUNS = 3


class MalformedCase(Exception):
    """A case the eval cannot score: a refusal (SC-234) or a bad case set (TASK-112 Q3)."""


class CaseRun(BaseModel):
    """Both use cases' results for one case, as they gave them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    approve: ApproveResult
    impact: ImpactResult


def restore_fixture(fixture: Path, dest: Path) -> None:
    """Clone the fixture's bundle into `dest` and copy its database into `.openfactory/`."""
    subprocess.run(["git", "clone", "--quiet", str(fixture / "repo.bundle"), str(dest)], check=True)
    (dest / ".openfactory").mkdir()
    shutil.copyfile(fixture / "openfactory.db", dest / ".openfactory" / "openfactory.db")


def replace_specs(case: Path, dest: Path) -> None:
    """Replace `specs/requirements.yaml` and `specs/adrs/` with the case's; keep `policies.yaml`."""
    specs = dest / "specs"
    (specs / "requirements.yaml").unlink(missing_ok=True)
    shutil.rmtree(specs / "adrs", ignore_errors=True)
    shutil.copyfile(case / "specs" / "requirements.yaml", specs / "requirements.yaml")
    (specs / "adrs").mkdir()
    for adr in sorted((case / "specs" / "adrs").glob("*.md")):
        shutil.copyfile(adr, specs / "adrs" / adr.name)


def run_case(fixture: Path, case: Path, dest: Path, *, llm: LLMProvider) -> CaseRun:
    """Run one case on its own copy of the fixture: `approve spec`, then `impact`."""
    restore_fixture(fixture, dest)
    replace_specs(case, dest)
    database = dest / ".openfactory" / "openfactory.db"
    # The adapter set of cli._open_adapters; the recorder creates the tables, so it opens first.
    with (
        closing(SqliteEventRecorder(database)) as recorder,
        closing(SqliteSpecVersions(database)) as versions,
        closing(SqlitePlans(database)) as plans,
        closing(SqliteRuns(database)) as runs,
        closing(SqliteTraces(database)) as traces,
    ):
        approved = approve_spec(FilesystemSpecFiles(dest / "specs"), versions, plans, recorder)
        impact = compute_impact(
            versions=versions, plans=plans, runs=runs, traces=traces, llm=llm, recorder=recorder
        )
    return CaseRun(approve=approved, impact=impact)


def load_cases(cases_dir: Path) -> list[tuple[str, Path, EvalLabels]]:
    """Every case directory in ascending id with its labels; checks the cosmetic cases."""
    cases = [
        (case.name, case, parse_eval_labels((case / "labels.yaml").read_text(encoding="utf-8")))
        for case in sorted(p for p in cases_dir.iterdir() if p.is_dir())
    ]
    cosmetic = [
        (case_id, labels)
        for case_id, _, labels in cases
        if labels.kinds and all(kind == "cosmetic" for kind in labels.kinds.values())
    ]
    if not cosmetic:
        raise MalformedCase(f"no cosmetic case in {cases_dir}")
    for case_id, labels in cosmetic:
        if labels.tasks or labels.files or labels.tests:
            raise MalformedCase(f"case {case_id}: a cosmetic case labels no tasks, files or tests")
    return cases


def _case_result(case_id: str, labels: EvalLabels, run: CaseRun) -> EvalCaseResult:
    if run.approve.outcome is not ApproveOutcome.approved:
        raise MalformedCase(f"case {case_id}: approve spec {run.approve.outcome}")
    if run.impact.refusal is not None:
        raise MalformedCase(f"case {case_id}: impact {run.impact.refusal}")
    return EvalCaseResult(case_id=case_id, labels=labels, impact=run.impact.impact)


def run_eval(
    fixture: Path,
    cases_dir: Path,
    workdir: Path,
    out: Path,
    *,
    llm: LLMProvider,
    runs: int = EVAL_RUNS,
) -> list[EvalRunResult]:
    """Run every case once per run, each on its own copy; write the results to `out`."""
    cases = load_cases(cases_dir)
    results: list[EvalRunResult] = []
    for n in range(1, runs + 1):
        case_results = [
            _case_result(
                case_id, labels, run_case(fixture, case, workdir / f"run_{n}" / case_id, llm=llm)
            )
            for case_id, case, labels in cases
        ]
        score = score_run([(c.labels, c.impact) for c in case_results if c.impact is not None])
        results.append(EvalRunResult(cases=case_results, score=score))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_eval_results(results), encoding="utf-8")
    return results


def missed_runs(runs: list[EvalRunResult]) -> list[int]:
    """The 1-based numbers of the runs that miss a target."""
    return [
        n
        for n, run in enumerate(runs, start=1)
        if not meets_targets(run.score, any_case_failed=any(c.impact is None for c in run.cases))
    ]
