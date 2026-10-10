"""Command line entry point and composition root (ADR-011)."""

import json
from pathlib import Path
from typing import Annotated

import typer

from openfactory.adapters.filesystem_spec_files import FilesystemSpecFiles
from openfactory.adapters.sqlite_recorder import SqliteEventRecorder
from openfactory.adapters.sqlite_spec_versions import SqliteSpecVersions
from openfactory.adapters.sqlite_store import SqliteEventStore
from openfactory.app import validate as validate_use_case
from openfactory.app.approve_spec import ApproveOutcome, approve_spec
from openfactory.app.list_events import list_events
from openfactory.domain.events import StoredEvent
from openfactory.domain.spec_validation import SpecViolation

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
approve_app = typer.Typer(no_args_is_help=True, help="Approve a spec version.")
app.add_typer(approve_app, name="approve")


@app.callback()
def main() -> None:
    """Spec-driven control plane for AI agent work."""


def require_init() -> Path:
    """Return the database path, or fail when the current directory is not initialised."""
    if not STATE_DIR.is_dir():
        typer.echo("run `openfactory init` first", err=True)
        raise typer.Exit(1)
    return DATABASE


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
    database = require_init()
    recorder = SqliteEventRecorder(database)
    try:
        # The recorder creates the tables, so it is opened first (ADR-010).
        versions = SqliteSpecVersions(database)
        try:
            result = validate_use_case.validate(
                FilesystemSpecFiles(POLICIES.parent), versions, recorder
            )
        finally:
            versions.close()
    finally:
        recorder.close()
    status = None
    if result.outcome is validate_use_case.Outcome.matches_approved:
        status = f"matches approved {result.spec_version}"
    for line in _result_lines(result.violations, result.policy_problems, status):
        typer.echo(line)
    if result.violations or result.policy_problems:
        raise typer.Exit(1)


@approve_app.callback()
def approve() -> None:
    """Approve a spec version."""


@approve_app.command()
def spec() -> None:
    """Validate the spec files and approve them as the next spec version."""
    database = require_init()
    recorder = SqliteEventRecorder(database)
    try:
        # The recorder creates the tables, so it is opened first (ADR-010).
        versions = SqliteSpecVersions(database)
        try:
            result = approve_spec(FilesystemSpecFiles(POLICIES.parent), versions, recorder)
        finally:
            versions.close()
    finally:
        recorder.close()
    status = None
    if result.outcome is ApproveOutcome.approved:
        status = f"approved {result.spec_version}"
    for line in _result_lines(result.violations, result.policy_problems, status):
        typer.echo(line)
    if result.outcome is ApproveOutcome.nothing_to_approve:
        typer.echo("nothing to approve", err=True)
    if result.outcome is not ApproveOutcome.approved:
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
