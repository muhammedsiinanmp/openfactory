"""The eval's per-case procedure: restore a copy of the fixture, swap in a case's spec files,
run `approve spec` and `impact` through the use cases (spec "Evaluation plan" › Procedure,
ADR-021). Test code, so it wires adapters and app itself (TASK-114 decisions row).
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
from openfactory.app.approve_spec import ApproveResult, approve_spec
from openfactory.app.impact import ImpactResult, compute_impact
from openfactory.ports.llm_provider import LLMProvider


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
