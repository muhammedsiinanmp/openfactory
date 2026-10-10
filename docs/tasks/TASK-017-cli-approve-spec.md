# TASK-017: `approve spec` command

- Milestone: M1
- Status: done
- Tests: acceptance
- ADR: ADR-011 (accepted) (`cli.py` is the composition root: it builds the adapters, calls the use case, prints and sets the exit code; `require_init()` is called first). ADR-010 (accepted) covers the recorder creating the database and tables when it opens; ADR-001 (accepted) covers the `EventRecorder` and `SpecVersions` ports. No new port, adapter, dependency, event type, payload, storage change or convention. The `approve` command group is the spec's own command name ("CLI commands" table), not a new convention.
- Spec impact: none. Spec v1.9 settles the lines, their order, the count line, the `approved sv_NN` status line, the `nothing to approve` message and its stream, and the exit codes.
- Spec sections (spec v1.9): "CLI commands" (the command table, "Other commands", "Output"); "Spec input format" ("Spec versions", "Policies"); "Domain model and storage" ("Streams and actors"); "Milestones and definition of done" (milestone 1)

## Objective
Add the `openfactory approve spec` command to `src/openfactory/cli.py`: it wires the SQLite and filesystem adapters to the approve-spec use case, prints the violation lines, the policy lines, the count line and the `approved sv_NN` status line, writes `nothing to approve` to standard error when the files equal the latest approved version, and sets the exit code.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Acceptance criteria trace to spec headings instead.

## Scope
In:
- An `approve` command group in `cli.py` (a Typer sub-app added with `app.add_typer(..., name="approve")`) with one command, `spec`, that takes no arguments.
- The `spec` command calls `require_init()`, opens `SqliteEventRecorder` on the returned path, then `SqliteSpecVersions` on the same path, builds `FilesystemSpecFiles(Path("specs"))`, calls `approve_spec(files, versions, recorder)` and closes both adapters.
- Printing through the existing `_result_lines` helper, with the status line `approved <id>` only for the `approved` outcome.
- `nothing to approve` on standard error for the `nothing_to_approve` outcome.
- Exit code 0 for `approved`, 1 for `unloadable`, `refused` and `nothing_to_approve`.
- Tests that run the real app through `typer.testing.CliRunner` in directories under `tmp_path`, with `monkeypatch.chdir`.

Out (follow-up tasks, not this one):
- The `approve plan` command (M2). The group is created with `spec` only.
- The `events` command (outline item 2) and the M1 close integration test (outline item 3).
- What a command prints when the recorder's catch-up fails (Later, F-1): the exception propagates.
- structlog configuration: this command writes no log line.
- The deleted-requirement rule (M2).
- Any change to `domain/`, `ports/`, `adapters/` or `app/`, to `_result_lines`' behaviour, to the `validate` command's behaviour, and any change to an existing test file.
- Cases the use case tests already cover and that print nothing new: nothing to approve while a draft exists (TASK-013 AC4), a duplicated id (TASK-015 AC5).
- Hardening against exotic inputs: a `specs` path that is a file, an unreadable database, a message that contains a line break.

## Acceptance criteria
Each criterion cites the spec v1.9 text it traces to. "Output" and "Other commands" are blocks under "CLI commands"; "Spec versions" and "Policies" are under "Spec input format"; "Streams and actors" is under "Domain model and storage". In every criterion the real Typer app runs `approve spec` through `CliRunner` with the current directory set to a repo under `tmp_path` on which `init` was run, unless stated. "Valid spec files" means a `specs/requirements.yaml` and ADRs with no violation. Unless stated, `specs/policies.yaml` is the default file `init` wrote.

- [x] AC1 (Output: "`approve spec` exits 0 on success, and its output ends with the status line `approved sv_NN`", "then a count line that is always printed" and "Command results (violation, policy, count and status lines; event lines) go to standard output"; Spec versions: "`openfactory approve spec` does not rely on an earlier `validate`", "`approve spec` records `SpecValidated` with the rule results before `SpecApproved`" and "Edits after that create a new draft version on the next `validate` or `approve spec`"; Streams and actors: the table row "`SpecApproved` | `spec:<spec version id>` | `human`"): valid spec files, no spec version yet, and `validate` was never run.
  - Standard output is exactly `0 violations, 0 policy problems` then `approved sv_01`; standard error is empty; the exit code is 0.
  - The event log holds `SpecImported`, `SpecValidated`, `SpecApproved` in that order, all on stream `spec:sv_01`; `SpecApproved` has actor `human`. The `spec_versions` row `sv_01` has status `approved`.
  - After the test edits a requirement's statement, a second `approve spec` prints `0 violations, 0 policy problems` then `approved sv_02` and exits 0.
- [x] AC2 (Output: "`validate` and `approve spec` print one line per violation and per policy problem as `rule  subject  message`: first the violation lines, sorted by rule name, then by subject, then by message, as strings", "A refused `approve spec` prints no status line" and "It exits 1 when it refuses because of violations"; Spec versions: "If they load but have violations, it records `SpecImported` (if the files changed) and `SpecValidated` with the violations, then refuses without recording `SpecApproved`"): the spec files load and break at least two content rules.
  - Standard output is exactly one line per violation as `<rule>  <subject>  <message>`, in the order of `sorted` on `(rule, subject, message)`, followed by `N violations, 0 policy problems`. No line starts with `approved`.
  - The exit code is 1.
  - The event log holds `SpecImported` then `SpecValidated` and no `SpecApproved`; the `spec_versions` row `sv_01` has status `draft`.
- [x] AC3 (Spec versions: "If the spec files cannot be loaded, it prints the violations and any policy problems, records no events, and exits 1, like `validate`"): `specs/requirements.yaml` is not valid YAML and `specs/policies.yaml` has an unknown key.
  - Standard output has a line starting `schema  specs/requirements.yaml  `, then a line starting `schema  specs/policies.yaml  `, then `1 violations, 1 policy problems`, and no status line.
  - The exit code is 1 and the `events` table has no rows.
- [x] AC4 (Output: "When there is nothing to approve it still prints the policy lines and the count line on standard output, prints no status line, writes `nothing to approve` to standard error and exits 1" and "Failure messages (`nothing to approve`, ...) and log lines go to standard error"; Spec versions: "If the files equal the latest approved version, it records no events and exits 1 with `nothing to approve`"): valid spec files that a first `approve spec` run approved as `sv_01`.
  - A second run prints exactly `0 violations, 0 policy problems` on standard output; standard error contains `nothing to approve`; the exit code is 1; the number of rows in `events` is the same before and after.
  - With `max_attempts: 0` then written to `specs/policies.yaml`, a further run prints the policy line then `0 violations, 1 policy problems` on standard output, `nothing to approve` on standard error, and exits 1. Standard output has no line starting `approved` or `matches approved`.
- [x] AC5 (Policies: "Policy problems are not recorded in `SpecValidated`, do not stop the content rules, and do not block `approve spec`"; Output: "policy problems do not change its exit code" and "then the policy lines, sorted the same way"): valid spec files, no spec version yet, and `max_attempts: 0` in `specs/policies.yaml`.
  - Standard output is exactly the policy line (`schema  specs/policies.yaml  ...`), then `0 violations, 1 policy problems`, then `approved sv_01`; the exit code is 0.
  - The event log holds a `SpecApproved`, and the stored `SpecValidated.violations` is empty.
- [x] AC6 (Other commands: "run against the current directory and fail with "run `openfactory init` first" if `./.openfactory/` is missing"; Output: "A command that fails exits 1" and "Failure messages (...) go to standard error"): in a directory with valid spec files and no `.openfactory/`, `approve spec` exits 1, standard error contains "run `openfactory init` first", standard output is empty, and no `.openfactory/` is created.

## Architecture rules that apply
- The change is inside `src/openfactory/cli.py`, the composition root (ADR-011). It parses, wires, prints and sets the exit code, and holds no rule of its own: validation, the decision to approve and the events stay in `app/approve_spec.py` and `app/validate.py`.
- The command maps `ApproveOutcome` to a status line, a standard-error message and an exit code. It does not look at the violations to decide whether the approval was refused.
- No module under `domain/`, `ports/`, `adapters/` or `app/` imports `openfactory.cli`; none of them is changed.
- "All state changes go through the events table. Never write projections directly": the command's only write path is `EventRecorder.record` inside the use cases.
- The recorder is opened before `SqliteSpecVersions`, because only the recorder creates the tables (ADR-010).
- No filesystem work is added to `cli.py`: spec files are read through `FilesystemSpecFiles`. The `init` exception is not copied (ADR-011).
- No LLM call is made.

## Plan
1. Create branch `task/TASK-017-cli-approve-spec` from an up-to-date main and commit this record.
2. Write failing tests in `tests/integration/test_cli_approve_spec.py`, one or more per criterion AC1 to AC6, with `CliRunner`, `tmp_path` and `monkeypatch.chdir`. Helpers (repo setup, sample spec texts, reading `events` and `spec_versions`) are defined in the file, in the same shape as those in `tests/integration/test_cli_validate.py`; that file is not edited.
3. In `src/openfactory/cli.py` add the `approve` sub-app and register it with `app.add_typer(approve_app, name="approve")`. Check first that `openfactory approve spec` is the invocation: a sub-app with one command is expected to stay a group, but this was derived by reading and not run. If Typer collapses it, stop and report before choosing a workaround.
4. Add the `spec` command: `require_init()`, open the recorder then `SqliteSpecVersions`, call `approve_spec`, close both in a `finally`. The adapter wiring may be shared with `validate` through a small private helper, as long as `validate` behaves the same and its tests pass unchanged.
5. Print `_result_lines(result.violations, result.policy_problems, status)`, where `status` is `approved <spec_version>` for the `approved` outcome and `None` otherwise. For `nothing_to_approve`, write `nothing to approve` with `typer.echo(..., err=True)` after the standard-output lines. Raise `typer.Exit(1)` for every outcome except `approved`.
6. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
7. Update living docs and this record's Outcome; commit with trailers `Task: TASK-017` and `Milestone: M1`.

## Files expected to change
- `src/openfactory/cli.py` (the `approve` group and the `spec` command)
- `tests/integration/test_cli_approve_spec.py` (new)
- `docs/architecture.md` ("CLI": add `approve spec`, and `_result_lines` now has two callers; "Data flow": replace the two sentences saying the approve-spec use case is not yet wired to a command)
- `docs/progress.md` (Current task, then Done; remove item 1 from the M1 outline and renumber the "depends on" references in the remaining items)
- `CHANGELOG.md` and `README.md` (the `approve spec` command)
- `docs/tasks/TASK-017-cli-approve-spec.md` (this record; Outcome at close)

Not expected to change: everything under `src/openfactory/domain/`, `src/openfactory/ports/`, `src/openfactory/adapters/` and `src/openfactory/app/`, `pyproject.toml`, `docs/adr/`, and every existing test file. Expected size: under 300 lines, most of it tests.

## Living docs to update
- `docs/architecture.md`: the "CLI" component and Data flow.
- `docs/progress.md`: Current, M1 outline and Done.
- `CHANGELOG.md` and `README.md`: the `approve spec` command.
- `docs/decisions.md`: no row expected.

## New dependencies
None.

## Spec gaps
None. Spec v1.9 states every line, order, stream and exit code this task prints or sets (SC-14 to SC-17).

One reading to record, which is not a gap: the spec names no standard-error message for a refusal or for unloadable files ("It exits 1 when it refuses because of violations"; "Failure messages (`nothing to approve`, "run `openfactory init` first", usage errors)"). The command therefore writes nothing to standard error in those two cases. AC2 and AC3 assert standard output and the exit code only, so no test depends on this reading.

## Open questions
None.

## Outcome
Built as planned. `cli.py` has an `approve` group (`approve_app`, registered with `app.add_typer(approve_app, name="approve")`, with a callback so it stays a group) and the `spec` command.
- Plan step 3's check passed: `openfactory approve --help` shows a group with the `spec` command, so the invocation is `approve spec`.
- The adapter wiring was not shared with `validate` through a helper; the `spec` command repeats the same two try/finally blocks.
- No test from the test-writer was edited. 8 tests in `tests/integration/test_cli_approve_spec.py`; 573 tests pass, ruff, pyright and check_docs are clean.
- Deviations: plan step 1's separate commit of this record was not made; the record is in the task's one commit.
- Follow-ups: bare `openfactory approve` prints the help on standard output and exits 2, like bare `openfactory` since TASK-014, where the spec's "Output" block sends usage errors to standard error; added to "Later" in `docs/progress.md` (reviewer's note).
