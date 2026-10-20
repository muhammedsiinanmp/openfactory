"""Command line entry point and composition root (ADR-011)."""

import json
import sys
from collections.abc import Generator
from contextlib import ExitStack, closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, assert_never

import structlog
import typer

from openfactory.adapters.claude_code_executor import ClaudeCodeExecutor
from openfactory.adapters.claude_code_llm import ClaudeCodeLLM
from openfactory.adapters.filesystem_run_files import FilesystemRunFiles
from openfactory.adapters.filesystem_spec_files import FilesystemSpecFiles
from openfactory.adapters.git_cli import GitCli
from openfactory.adapters.git_worktree import GitWorktree
from openfactory.adapters.process_gates import ProcessGates
from openfactory.adapters.sqlite_plans import SqlitePlans
from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.adapters.sqlite_runs import SqliteRuns
from openfactory.adapters.sqlite_spec_versions import SqliteSpecVersions
from openfactory.adapters.sqlite_store import SqliteEventStore
from openfactory.app import validate as validate_use_case
from openfactory.app.approve_plan import ApprovePlanOutcome, approve_plan
from openfactory.app.approve_spec import ApproveOutcome, approve_spec
from openfactory.app.list_events import list_events
from openfactory.app.plan import (
    PlannerOutcome,
    PlannerResult,
    PlanRefusal,
    PlanRefused,
    create_plan,
    prepare_plan,
)
from openfactory.app.run import RunRefusal, run_plan
from openfactory.domain.events import StoredEvent
from openfactory.domain.plan_checks import rejection_lines
from openfactory.domain.spec_validation import SpecViolation
from openfactory.domain.states import TaskState

STATE_DIR = Path(".openfactory")
DATABASE = STATE_DIR / "openfactory.db"
STATE_GITIGNORE = STATE_DIR / ".gitignore"
POLICIES = Path("specs") / "policies.yaml"

DEFAULT_POLICIES = """\
# policies.yaml
protected_branches: [main, master]
forbidden_paths: []
max_attempts: 2
max_runtime_s: 1200
max_cost_usd: 1.50
"""

app = typer.Typer(no_args_is_help=True, add_completion=False)
approve_app = typer.Typer(no_args_is_help=True, help="Approve a spec version or a plan.")
app.add_typer(approve_app, name="approve")


def _configure_logging() -> None:
    """Log lines are JSON lines on standard error, for every command."""
    structlog.configure(
        processors=[structlog.processors.add_log_level, structlog.processors.JSONRenderer()],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )


@app.callback()
def main() -> None:
    """Spec-driven control plane for AI agent work."""
    _configure_logging()


def require_init() -> Path:
    """Return the database path, or fail when the current directory is not initialised."""
    if not STATE_DIR.is_dir():
        typer.echo("run `openfactory init` first", err=True)
        raise typer.Exit(1)
    return DATABASE


@dataclass(frozen=True)
class _Adapters:
    recorder: SqliteEventRecorder
    versions: SqliteSpecVersions
    plans: SqlitePlans
    runs: SqliteRuns


@contextmanager
def _open_adapters(database: Path) -> Generator[_Adapters]:
    """The recorder and the read adapters on one database, closed in reverse order."""
    with ExitStack() as stack:
        # The recorder creates the tables, so it is opened first (ADR-010).
        recorder = stack.enter_context(closing(SqliteEventRecorder(database)))
        versions = stack.enter_context(closing(SqliteSpecVersions(database)))
        plans = stack.enter_context(closing(SqlitePlans(database)))
        runs = stack.enter_context(closing(SqliteRuns(database)))
        yield _Adapters(recorder, versions, plans, runs)


def _create_database(path: Path) -> None:
    SqliteEventRecorder(path).close()


def _create_gitignore(path: Path) -> None:
    path.write_text("*\n", encoding="utf-8")


def _create_policies(path: Path) -> None:
    path.write_text(DEFAULT_POLICIES, encoding="utf-8")


@app.command()
def init(repo: Path) -> None:
    """Create .openfactory/ and a default specs/policies.yaml in a git repository."""
    if not (repo / ".git").exists():
        typer.echo(f"not a git repository: {repo}", err=True)
        raise typer.Exit(1)
    (repo / STATE_DIR).mkdir(exist_ok=True)
    (repo / POLICIES.parent).mkdir(exist_ok=True)
    items = (
        (DATABASE, _create_database),
        (STATE_GITIGNORE, _create_gitignore),
        (POLICIES, _create_policies),
    )
    for item, create in items:
        if (repo / item).exists():
            typer.echo(f"exists {item}")
        else:
            create(repo / item)
            typer.echo(f"created {item}")


def _result_lines(
    violations: list[SpecViolation], policy_problems: list[SpecViolation], status: str | None
) -> list[str]:
    """Violation lines, policy lines, the count line, then the status line when there is one."""
    lines: list[str] = []
    for group in (violations, policy_problems):
        fields = sorted((v.rule.value, v.subject, v.message) for v in group)
        lines += ["  ".join(line) for line in fields]
    lines.append(f"{len(violations)} violations, {len(policy_problems)} policy problems")
    if status is not None:
        lines.append(status)
    return lines


@app.command()
def validate() -> None:
    """Check the spec files against the rules and record the result."""
    with _open_adapters(require_init()) as adapters:
        result = validate_use_case.validate(
            FilesystemSpecFiles(POLICIES.parent),
            adapters.versions,
            adapters.plans,
            adapters.recorder,
        )
    status = None
    if result.outcome is validate_use_case.Outcome.matches_approved:
        status = f"matches approved {result.spec_version}"
    for line in _result_lines(result.violations, result.policy_problems, status):
        typer.echo(line)
    if result.violations or result.policy_problems:
        raise typer.Exit(1)


@approve_app.callback()
def approve() -> None:
    """Approve a spec version or a plan."""


@approve_app.command()
def spec() -> None:
    """Validate the spec files and approve them as the next spec version."""
    with _open_adapters(require_init()) as adapters:
        result = approve_spec(
            FilesystemSpecFiles(POLICIES.parent),
            adapters.versions,
            adapters.plans,
            adapters.recorder,
        )
    status = None
    if result.outcome is ApproveOutcome.approved:
        status = f"approved {result.spec_version}"
    for line in _result_lines(result.violations, result.policy_problems, status):
        typer.echo(line)
    if result.outcome is ApproveOutcome.nothing_to_approve:
        typer.echo("nothing to approve", err=True)
    if result.outcome is not ApproveOutcome.approved:
        raise typer.Exit(1)


@approve_app.command("plan")
def approve_plan_command() -> None:
    """Approve the draft plan; its tasks with no dependencies become ready."""
    with _open_adapters(require_init()) as adapters:
        result = approve_plan(adapters.versions, adapters.plans, adapters.recorder)
    if result.outcome is ApprovePlanOutcome.no_draft:
        typer.echo("no draft plan", err=True)
        raise typer.Exit(1)
    if result.outcome is ApprovePlanOutcome.stale_draft:
        typer.echo(
            f"{result.plan_id} was made for {result.spec_version}; run openfactory plan", err=True
        )
        raise typer.Exit(1)
    for task_id in result.ready:
        typer.echo(f"{task_id}  ready")
    typer.echo(f"approved {result.plan_id}")


def _refusal_line(refused: PlanRefused) -> str:
    if refused.reason is PlanRefusal.no_approved_spec:
        return "no approved spec version"
    if refused.reason is PlanRefusal.invalid_policy:
        return "policy is invalid; run openfactory validate"
    return f"{refused.plan_id} is already approved; use replan"


def _first_line(error: str | None) -> str:
    """The `<error>` of a failure line: the first line of the failure's text."""
    return error.splitlines()[0] if error else ""


def _prepare_and_create_plan(database: Path) -> PlanRefused | PlannerResult:
    """The two calls of `plan` (ADR-013), with the warning written between them."""
    with _open_adapters(database) as adapters:
        inputs = prepare_plan(
            FilesystemSpecFiles(POLICIES.parent), adapters.versions, adapters.plans
        )
        if isinstance(inputs, PlanRefused):
            return inputs
        if inputs.spec_files_differ:
            typer.echo(f"spec files differ from approved {inputs.spec_version}", err=True)
        return create_plan(
            inputs,
            git=GitCli(Path(".")),
            llm=ClaudeCodeLLM(),
            runs=adapters.runs,
            plans=adapters.plans,
            recorder=adapters.recorder,
        )


@app.command()
def plan() -> None:
    """Ask the planner for a plan of the approved spec version and record it as a draft."""
    result = _prepare_and_create_plan(require_init())
    if isinstance(result, PlanRefused):
        typer.echo(_refusal_line(result), err=True)
        raise typer.Exit(1)
    if result.outcome is PlannerOutcome.git_failed:
        typer.echo(f"git ls-files failed: {_first_line(result.error)}", err=True)
        raise typer.Exit(1)
    if result.outcome is PlannerOutcome.failed:
        typer.echo(f"planner call failed: {_first_line(result.error)}", err=True)
        raise typer.Exit(1)
    if result.outcome is PlannerOutcome.rejected:
        for line in rejection_lines(result.rejections):
            typer.echo(line)
        raise typer.Exit(1)
    for task in result.tasks:
        typer.echo(f"{task.task_id}  {task.objective}")
    typer.echo(f"created {result.plan_id}")


def _run_refusal_line(refusal: RunRefusal, detail: str | None, task_id: str | None) -> str:
    if refusal is RunRefusal.no_approved_plan:
        return "no approved plan"
    if refusal is RunRefusal.no_commit:
        return "repository has no commit"
    if refusal is RunRefusal.git_failed:
        return f"git failed: {detail}"
    if refusal is RunRefusal.tool_not_found:
        return f"{detail} not found"
    if refusal is RunRefusal.unknown_task:
        return f"unknown task {detail}"
    if refusal is RunRefusal.not_ready:
        return f"{task_id} is {detail}, not ready"
    assert_never(refusal)


@app.command()
def run(
    task: Annotated[str | None, typer.Option(help="Run this task only.")] = None,
) -> None:
    """Run the ready tasks of the approved plan and print where each ended."""
    repo = Path(".")
    with _open_adapters(require_init()) as adapters:
        report = run_plan(
            task_id=task,
            git=GitCli(repo),
            gates=ProcessGates(repo),
            workspace=GitWorktree(repo),
            executor=ClaudeCodeExecutor(repo),
            run_files=FilesystemRunFiles(repo),
            runs=adapters.runs,
            plans=adapters.plans,
            versions=adapters.versions,
            recorder=adapters.recorder,
        )
    # The repair's warnings come first, also before a `--task` refusal (audit F-4).
    for warning in report.warnings:
        typer.echo(warning, err=True)
    if report.refusal is not None:
        typer.echo(_run_refusal_line(report.refusal, report.detail, task), err=True)
        raise typer.Exit(1)
    # A task's warning follows its own line (audit F-5).
    for result in report.tasks:
        typer.echo(f"{result.task_id}  {result.state.value}")
        if result.warning is not None:
            typer.echo(result.warning, err=True)
    if any(result.state is not TaskState.passed for result in report.tasks):
        raise typer.Exit(1)


def _event_line(event: StoredEvent) -> str:
    """One stored event as a JSON object with sorted keys and no spaces."""
    fields = {
        "seq": event.seq,
        "event_id": str(event.event_id),
        "stream": event.stream,
        "type": event.type.value,
        "payload": event.payload,
        "actor": event.actor,
        "causation_id": None if event.causation_id is None else str(event.causation_id),
        # isoformat() is the stored form (+00:00); Pydantic's JSON mode would write Z.
        "created_at": event.created_at.isoformat(),
    }
    return json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@app.command()
def events(
    stream: Annotated[str | None, typer.Option(help="Only the events of this stream.")] = None,
) -> None:
    """Print the stored events, one JSON object per line."""
    database = require_init()
    # The store, not the recorder: no catch-up runs, so the log can always be shown.
    store = SqliteEventStore(database)
    try:
        stored = list_events(store, stream)
    finally:
        store.close()
    for event in stored:
        typer.echo(_event_line(event))
