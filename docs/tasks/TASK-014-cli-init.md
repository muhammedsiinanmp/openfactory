# TASK-014: CLI entry point and `init`

- Milestone: M1
- Status: done
- Tests: acceptance
- ADR: ADR-011 (proposed) (the CLI as composition root: `cli.py` is the one module that imports adapters and use cases and wires them; `init`'s filesystem work lives there and behind no port; the shared "run `openfactory init` first" check every later command calls). Triggers: "a new convention other code must follow" and "a choice between real alternatives with lasting consequences" (see Open questions, item 1). ADR-010 (accepted) covers creating the database by opening `SqliteEventRecorder`; ADR-002 (accepted) already says `init` records no events. No new port, adapter, runtime dependency, event type, payload or storage change.
- Spec impact: wording. The spec settles what `init` creates, that it is repeatable, that it records no events, and the exit codes and streams. It leaves four things unsaid, none of which blocks (see "Spec gaps").
- Spec sections (spec v1.8): "CLI commands" (the command table, "`init`", "Other commands", "Output"); "Spec input format" ("Policies"); "Tech stack and repo layout"; "Domain model and storage" ("Projection rules"); "Milestones and definition of done" (milestone 1)

## Objective
Add the Typer entry point `src/openfactory/cli.py` with the `init <repo>` command, which creates `.openfactory/` with its database and `.gitignore` and a default `specs/policies.yaml`, and the "run `openfactory init` first" check that the other commands will call.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Acceptance criteria trace to spec headings instead.

## Scope
In:
- A new module `src/openfactory/cli.py` holding a Typer app with one command, `init <repo>`, and a callback so that `init` stays a subcommand while it is the only command.
- `[project.scripts]` in `pyproject.toml` pointing at the Typer app, and removal of the placeholder `main()` in `src/openfactory/__init__.py`.
- `init`: refuse a `<repo>` that is not an existing git repository; create `<repo>/.openfactory/`, `<repo>/.openfactory/openfactory.db` (by opening and closing `SqliteEventRecorder`, decision of 2026-10-09, TASK-011: "`init` opens it first"), `<repo>/.openfactory/.gitignore` containing `*`, and `<repo>/specs/policies.yaml` with the defaults; create only what is missing and report what already exists; record no events.
- A helper in `cli.py` that later commands call first: it fails with "run `openfactory init` first" on standard error and exit code 1 when `./.openfactory/` is missing, with no search of parent directories.
- Tests that run the app through `typer.testing.CliRunner` on directories under pytest's `tmp_path`.

Out (follow-up tasks, not this one):
- The `validate`, `approve spec` and `events` commands, their output and exit codes (the next two outline items), and wiring `SqliteSpecVersions`, `FilesystemSpecFiles` and the use cases to a command.
- The order in which a command opens the recorder and `SqliteSpecVersions`, and a `.openfactory/` whose database file is missing (Later, the `SqliteSpecVersions` line).
- The M1 close integration test (the last outline item).
- A `GitProvider` port or a git adapter (M3). This task starts no `git` process (Open questions, item 2).
- An `app/` use case and ports for `init` (Open questions, item 1).
- structlog configuration. No code in this task writes a log line; it is set up by the first command that logs.
- A repeated `init` on a database whose stored payload its model rejects (Later, "No repair path"; ADR-010).
- Hardening against exotic inputs: a `<repo>` that is a file, a symlink loop, a read-only directory, `specs` or `.openfactory` existing as a file.
- Any change to `domain/`, `ports/`, `adapters/`, `app/`, and any change to an existing test file.

## Acceptance criteria
Each criterion cites the spec v1.8 text it traces to. "`init`", "Other commands" and "Output" are blocks under "CLI commands"; "Policies" is under "Spec input format". In every criterion a Typer app is run with `typer.testing.CliRunner`: the real app for AC1 to AC4, and for AC5 a test-only app whose single command calls `require_init()`. "A git repo" is a directory under `tmp_path` that the test turned into a repository (see Open questions, item 2, for how `init` recognises one). The items that depended on an open question follow the human's answers of 2026-10-09.

- [x] AC1 ("`init`": "It creates `<repo>/.openfactory/openfactory.db`, and `<repo>/.openfactory/.gitignore` containing `*`, so the directory ignores itself without touching the repo's own `.gitignore`"; the command table: "`openfactory init <repo>` | Creates `.openfactory/`, the SQLite file and, if missing, a default `specs/policies.yaml`"; "Tech stack and repo layout": "CLI | Typer", "`cli.py`", and "Storage | SQLite via the standard `sqlite3` module, WAL mode"; "Projection rules": "The event recorder creates it and is its only writer"): `init <repo>` on a git repo with no `.openfactory/` and no `specs/`.
  - It exits 0.
  - `<repo>/.openfactory/openfactory.db` exists and is a SQLite database holding the tables `events`, `spec_versions`, `requirements`, `adrs` and `projection_state`, with `projection_state.last_seq` 0.
  - `<repo>/.openfactory/.gitignore` exists and its content, stripped of surrounding whitespace, is `*`.
  - A `<repo>/.gitignore` the test wrote beforehand is byte-identical afterwards; when there was none, none is created.
  - `openfactory.cli` exposes the Typer app, and the `openfactory` script in `pyproject.toml` points at it.
- [x] AC2 ("`init`": "It creates `<repo>/specs/policies.yaml` with the defaults, creating `specs/` if needed. An existing file is never overwritten"; "Policies": "`specs/policies.yaml` has five keys. Each is optional with the default shown" and the `policies.yaml` code block):
  - After `init` on a git repo with no `specs/`, `<repo>/specs/policies.yaml` exists; parsed as YAML it has exactly the five keys `protected_branches`, `forbidden_paths`, `max_attempts`, `max_runtime_s` and `max_cost_usd` with the values of the spec's code block; `load_policy(FilesystemSpecFiles(<repo>/specs))` returns a policy equal to `Policy()` and no violations.
  - With an existing `specs/` that holds a `requirements.yaml`, that file is byte-identical afterwards.
  - With an existing `specs/policies.yaml` whose content differs from the defaults (for example `max_attempts: 5`), the file is byte-identical after `init`, and `init` exits 0.
- [x] AC3 ("`init`": "It is safe to repeat: it creates what is missing and reports what already exists. It records no events"): `init <repo>` is run twice on the same git repo.
  - Both runs exit 0.
  - The `events` table has no rows after the first run and after the second.
  - `.openfactory/.gitignore` and `specs/policies.yaml` are byte-identical after the second run.
  - After the test deletes only `.openfactory/.gitignore`, a third run recreates it and leaves `specs/policies.yaml` as it was.
  - The first run's standard output is exactly the three lines `created .openfactory/openfactory.db`, `created .openfactory/.gitignore`, `created specs/policies.yaml`, in that order.
  - The second run's standard output is the same three lines with `exists` in place of `created`.
  - The third run (after `.openfactory/.gitignore` was deleted) prints `exists`, `created`, `exists` for the three items in the same order.
- [x] AC4 ("`init`": "`<repo>` must be an existing git repository; otherwise `init` fails"; "Output": "A command that fails exits 1; a usage error exits 2" and "Failure messages (...) and log lines go to standard error"):
  - `init` on a path that does not exist exits 1, not 2.
  - `init` on an existing directory that is not a git repository exits 1.
  - In both cases standard output is empty and standard error is not; the text of the message is not asserted.
  - In both cases no `.openfactory/` and no `specs/` is created. A sub-directory of a git repo that has no `.git` entry of its own is refused the same way.
  - `init` with no `<repo>` argument exits 2.
- [x] AC5 ("Other commands": "run against the current directory and fail with "run `openfactory init` first" if `./.openfactory/` is missing. There is no search of parent directories"; "Output": "Failure messages (`nothing to approve`, "run `openfactory init` first", usage errors) and log lines go to standard error" and "A command that fails exits 1"): the check that the other commands will call, `require_init()` in `openfactory.cli`, run through a test-only Typer app.
  - With the current directory a directory that has no `.openfactory/`, it stops the command with exit code 1, writes a line containing "run `openfactory init` first" to standard error, and writes nothing to standard output.
  - With the current directory a sub-directory of an initialised repo, it fails the same way.
  - With the current directory an initialised repo (after `init`), it does not fail and returns `Path(".openfactory/openfactory.db")`.

## Architecture rules that apply
- `src/openfactory/domain`, `ports` and `app` are not changed. `app` still imports nothing from `adapters`.
- `cli.py` sits outside the four layers (spec, "Tech stack and repo layout"). It may import from `adapters` and `app`; no module under `domain/`, `ports/`, `adapters/` or `app/` imports `openfactory.cli`.
- "All state changes go through the events table. Never write projections directly": `init` records no event and writes no projection row; the tables are created by `SqliteEventRecorder` when it opens (ADR-010).
- `cli.py` implements no port, so it carries no `TYPE_CHECKING` conformance assertion.
- No LLM call is made.

## Plan
1. Create branch `task/TASK-014-cli-init` from an up-to-date main and commit this record.
2. Record the human's answers to the Open questions here and in `docs/decisions.md`.
3. Draft `docs/adr/ADR-011-cli-composition-root.md` as Status: proposed.
4. Write failing tests in `tests/integration/test_cli_init.py`, one or more per criterion AC1 to AC5, with `CliRunner` and `tmp_path`; `monkeypatch.chdir` for AC5.
5. Add `src/openfactory/cli.py`:
   - the Typer app with a callback, so `init` is a subcommand;
   - `init(repo: Path)`: check the repository without Typer's `exists=True`, which would turn a missing path into a usage error with exit 2; then create each missing item and print one line per item;
   - the database is created by `SqliteEventRecorder(<repo>/.openfactory/openfactory.db)` followed by `close()`;
   - the init check for other commands.
6. Point `[project.scripts]` at the Typer app and remove the placeholder `main()` from `src/openfactory/__init__.py` (`tests/unit/test_smoke.py` only imports the package and is not affected).
7. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
8. Update living docs and this record's Outcome; commit with trailers `Task: TASK-014` and `Milestone: M1`.

## Files expected to change
- `src/openfactory/cli.py` (new)
- `src/openfactory/__init__.py` (remove the placeholder `main`)
- `pyproject.toml` (`[project.scripts]` only; no dependency change)
- `tests/integration/test_cli_init.py` (new)
- `docs/adr/ADR-011-cli-composition-root.md` (new, Status: proposed)
- `docs/architecture.md` (Components: add "CLI"; Data flow: replace "There is still no CLI, and nothing wires the SQLite and filesystem adapters to the use cases")
- `docs/progress.md` (Current task, then Done; remove item 1 from the M1 outline and renumber the references to it, including "before outline item 2" in the Later line on duplicate ids; add the Later lines under "Spec gaps"; reword the `SqliteSpecVersions` Later line to say `init` now creates the tables)
- `docs/decisions.md` (rows for the answered questions)
- `CHANGELOG.md` and `README.md` (first user-visible command: `openfactory init <repo>`)
- `docs/tasks/TASK-014-cli-init.md` (this record; Outcome at close)

Not expected to change: everything under `src/openfactory/domain/`, `src/openfactory/ports/`, `src/openfactory/adapters/` and `src/openfactory/app/`, and every existing test file.

## Living docs to update
- `docs/architecture.md`: Components and Data flow.
- `docs/progress.md`: Current, M1 outline, Done and Later.
- `docs/decisions.md`: the answered questions.
- `CHANGELOG.md` and `README.md`: the `init` command.

## New dependencies
None. `typer` (which provides `typer.testing.CliRunner`) is already declared in `pyproject.toml`.

## Spec gaps
All four are wording. None blocks: each has one reading the criteria can be tested against once the human confirms it, and the items that depend on an answer are marked in the criteria. Each becomes a "Spec wording (M1, next spec revision)" line under Later in `docs/progress.md`.

1. **"CLI commands" › `init`: "`<repo>` must be an existing git repository" — wording, does not block.**
   - Missing: how a git repository is recognised (a `.git` entry in `<repo>`, or what `git` reports), whether a sub-directory of a repository or a bare repository counts, and whether a failed `init` leaves anything behind.
   - Why it does not block: a missing path and a plain directory fail under every reading, and AC4 tests only those.
2. **"CLI commands" › `init`: "reports what already exists" — wording, does not block.**
   - Missing: the text and form of `init`'s output lines, whether created items are reported too, and whether `.openfactory/` itself is an item. "Output" lists the result lines of `validate`, `approve spec` and `events` but none for `init`.
   - Why it does not block: the meaning is clear (a repeat says what was already there); AC3 asserts only that each existing path is named, and only once Q3 is answered.
3. **"CLI commands" › `init`: "creates `<repo>/specs/policies.yaml` with the defaults" — wording, does not block.**
   - Missing: the exact text of the file (the spec's code block with its `# policies.yaml` comment line, or the five keys only). An empty file is also a valid policy with all defaults (decision of 2026-10-09, TASK-008), so "with the defaults" has a second, weaker reading.
   - Why it does not block: AC2 asserts the parsed content, five keys with the spec's values, which is the reading the code block supports; the exact bytes are not asserted.
4. **"CLI commands" › Other commands: "fail ... if `./.openfactory/` is missing" — wording, does not block.**
   - Missing: what a command does when `.openfactory/` exists but `openfactory.db` does not.
   - Why it does not block: this task checks the directory only, as written. The missing-file case belongs to the `validate` and `approve spec` task and is already under Later (the `SqliteSpecVersions` line).

## Open questions
1. **Where `init`'s work lives, and the ADR.** `app` depends on domain and ports only, and `init` creates directories and files and checks for a repository.
   - Proposed: `cli.py` is the composition root. It imports adapters and use cases and wires them, and `init`'s filesystem work is plain code in `cli.py` with no use case and no port. `init` has no domain rule and records no event, so a use case would be a pass-through. Recorded as ADR-011 (proposed), since every later command follows it.
   - Alternative: an `app/init.py` use case behind a new writing port and a `GitProvider` port, with their adapters. This keeps all I/O behind ports but adds two ports and two adapters for a command with no domain logic, and takes the task past one session.
   - Also to confirm: an ADR, or a row in `docs/decisions.md` only.
   - **Answer (human, 2026-10-09):** the proposal as it stands, with an ADR (ADR-011, proposed).
2. **What counts as "an existing git repository", and what a failed `init` leaves.**
   - Proposed: `<repo>` is an existing directory that contains a `.git` entry (a directory, or a file as in a linked worktree). No `git` process is started, so M1 needs no git adapter. A sub-directory of a repository is refused, in line with "There is no search of parent directories". The check runs before anything is created, so a failed `init` creates nothing.
   - Alternative: ask git (`git -C <repo> rev-parse --show-toplevel` must equal `<repo>`). This is exact, but it is the first `subprocess` call and belongs behind `GitProvider`, which is M3 work.
   - **Answer (human, 2026-10-09):** the proposal as it stands, worded as "a refused `init` creates nothing": a failure part-way (for example a permission error) can leave items behind, and a repeat creates the rest.
3. **What `init` prints.**
   - Proposed: one line per item on standard output, in a fixed order (`.openfactory/openfactory.db`, `.openfactory/.gitignore`, `specs/policies.yaml`), as `created <path>` or `exists <path>`, with the path relative to `<repo>`. `.openfactory/` and `specs/` are not items of their own.
   - Alternative: print only what already exists, the minimum the spec's sentence asks for.
   - Also to confirm: the wording of the not-a-repository message on standard error. Proposed: `not a git repository: <repo>`. Not asserted by the tests.
   - **Answer (human, 2026-10-09):** the proposal as it stands, including the message.
4. **The init check for the other commands: in this task, and its shape.** No other command exists yet, so nothing can show the message through the CLI.
   - Proposed: build it now as a function in `cli.py`, `require_init() -> Path`, which returns `Path(".openfactory/openfactory.db")` when `./.openfactory/` is a directory, and otherwise writes "run `openfactory init` first" to standard error and raises `typer.Exit(1)`. AC5 tests the function directly. Outline items 2 and 3 both depend on it and then only call it.
   - Alternative: leave it out and build it in the `validate` and `approve spec` task with its first caller. AC5 then moves to that task and this one has four criteria.
   - **Answer (human, 2026-10-09):** the proposal as it stands. AC5 runs the function through a test-only Typer app with `CliRunner`. The returned path does not mean the database file exists: a `.openfactory/` without `openfactory.db` is still open (Spec gaps, item 4).
5. **The exact text of the default `policies.yaml`.**
   - Proposed: the spec's code block as it stands, the `# policies.yaml` comment line included, with a final newline. `tests/unit/test_spec_conformance.py` already ties that block to `Policy()`.
   - Alternative: the five keys dumped from `Policy()` with no comment line.
   - **Answer (human, 2026-10-09):** the proposal as it stands.

## Outcome
**Built**
- `src/openfactory/cli.py`: Typer app `app` with a callback and `init <repo>`. A path without a `.git` entry is refused with `not a git repository: <repo>` on standard error and exit 1, before anything is created. Otherwise `init` creates `.openfactory/openfactory.db` (by opening and closing `SqliteEventRecorder`), `.openfactory/.gitignore` containing `*` and `specs/policies.yaml` from the spec's code block, prints `created <path>` or `exists <path>` per item in that order, and records no events. `require_init() -> Path` is the "run `openfactory init` first" check.
- `[project.scripts]` points at `openfactory.cli:app`; the placeholder `main()` in `src/openfactory/__init__.py` is removed.
- `tests/integration/test_cli_init.py` covers AC1 to AC5.
- ADR-011 (proposed) and the decisions rows for the four answered questions.

**Deviations from plan**
- ADR-011 is named in this record only after it was drafted, because `check_docs` rejects a reference to a missing ADR.
- A repeated `init` does not open the recorder on an existing database; it reports `exists` for the file.
- AC5 runs `require_init` through a test-only Typer app, as answered in Open questions, item 4.
- Wording "a refused `init` creates nothing" (Open questions, item 2): a failure part-way can leave items behind and a repeat creates the rest.

**Test edits:** none.

**Follow-ups**
- The four "Spec wording (M1, next spec revision), from TASK-014" lines under Later in `docs/progress.md` (Spec gaps, items 1 to 4).
- `require_init` has no caller until the `validate` and `events` commands.
- A database file that exists without its tables is not repaired by a repeated `init`; the `validate` task decides who repairs it (decision of 2026-10-09; fourth Spec wording line).
- ADR-011 is still proposed; the human marks it accepted. `CLAUDE.md` gained a `cli.py` line in its architecture rules at the human's request.
