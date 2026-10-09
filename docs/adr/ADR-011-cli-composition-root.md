# ADR-011: CLI as the composition root

- Status: proposed
- Date: 2026-10-09

## Context
Until now nothing wired the adapters to the use cases. The app layer depends on the
domain and the ports only, and
[ADR-006](ADR-006-ports-and-adapters-with-type-checked-conformance.md) says "The app
layer cannot read the filesystem or touch SQLite, so every such need is a port". The
spec's repo layout lists `cli.py` beside `domain/`, `ports/`, `adapters/` and `app/`, not
inside one of them, and says nothing about what it may import.

`init` is the first command. It checks that `<repo>` is a git repository and creates
`.openfactory/`, its `.gitignore`, the database and a default `specs/policies.yaml`. It
has no domain rule and records no event
([ADR-002](ADR-002-event-sourcing-as-the-core.md)). The database is created by opening
`SqliteEventRecorder` ([ADR-010](ADR-010-sqlite-recorder-adapter.md)).

That leaves open:

- which module builds the adapters and hands them to the use cases;
- whether `init`'s directory and file work goes behind a use case and ports;
- where the "run `openfactory init` first" check lives, since every other command needs
  it.

Every later command (`validate`, `approve spec`, `events`, and those of M2 to M7) will
follow whatever is chosen here.

## Decision
- `src/openfactory/cli.py` is the composition root. It is the one module that imports
  from `adapters` and from `app`, builds the adapters and passes them to the use cases.
  It sits outside the four layers: no module under `domain/`, `ports/`, `adapters/` or
  `app/` imports `openfactory.cli`.
- A command with a domain rule or an event calls a use case in `app/`. `cli.py` then
  parses arguments, wires, prints and sets the exit code, and holds no rule of its own.
- `init` is the exception: its work is plain code in `cli.py`, with no use case and no
  port. This is filesystem I/O outside `adapters/`. It is allowed here because `init`
  only sets up the directory the adapters work in, no use case reads or writes these
  paths through it, and ADR-006's port rule binds the app layer, which is unchanged.
- `init` creates the database by opening `SqliteEventRecorder` and closing it. It writes
  no SQL.
- `init` recognises a git repository by a `.git` entry in `<repo>` and starts no `git`
  process. Git operations stay behind the `GitProvider` port, which arrives in M3.
- The init check is `require_init() -> Path` in `cli.py`. Every command except `init`
  calls it first. It looks at `./.openfactory/` only, with no search of parent
  directories, writes "run `openfactory init` first" to standard error and exits 1 when
  the directory is missing, and otherwise returns the database path.
- `cli.py` implements no port and carries no conformance assertion.

## Alternatives considered
- **An `app/init.py` use case behind a writing port and a `GitProvider` port.** All I/O
  stays behind ports and `init` is tested with fakes like every other use case. But it
  adds two ports and two adapters for a command with no domain rule, the use case would
  only pass calls through, and `GitProvider` would be designed in M1 around one check
  instead of in M3 around worktrees and commits.
- **A helper module in `adapters/` with no port, called by `cli.py`.** All filesystem
  writes stay in `adapters/` and `cli.py` stays thin, as with the projector
  ([ADR-009](ADR-009-sqlite-projector-without-a-port.md)) and `sqlite_events` (ADR-010).
  But it is one more module and a third exemption to the conformance-assertion rule, for
  about thirty lines of code that only `init` calls.
- **A separate wiring module, with `cli.py` only parsing arguments.** The split helps
  when a second entry point exists. Phase 1 has one, so the module would be an extra
  hop.
- **Ask git whether `<repo>` is a repository (`git rev-parse`).** Exact, where the
  `.git` entry is a heuristic. But it is the first subprocess call, it belongs behind
  `GitProvider`, and it makes the `init` tests depend on a `git` binary.

## Consequences
Easier:
- One place shows which adapter backs which port, and a new command adds its wiring
  there.
- `init` is small and has no fake to maintain.
- M1 needs no git adapter and no subprocess.
- The `validate` and `events` commands share one init check and do not depend on each
  other.

Harder:
- `cli.py` is tested only through `CliRunner` on real directories; `init` has no unit
  test with fakes.
- Filesystem writes now exist outside `adapters/`. A later command must not copy this:
  the exception is `init` alone, and a reviewer has to hold that line.
- The `.git` check accepts an empty `.git` directory and refuses a repository found
  only through `GIT_DIR`.
- `require_init` checks the directory, not the database file. What a command does when
  `.openfactory/` exists without `openfactory.db` is still open.
- When a second entry point appears, the wiring has to move out of `cli.py`.
