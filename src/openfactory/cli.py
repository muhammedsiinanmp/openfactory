"""Command line entry point and composition root (ADR-011)."""

from pathlib import Path

import typer

from openfactory.adapters.sqlite_recorder import SqliteEventRecorder

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
