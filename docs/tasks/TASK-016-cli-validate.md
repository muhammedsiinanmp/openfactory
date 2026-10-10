# TASK-016: `validate` command

- Milestone: M1
- Status: done
- Tests: acceptance
- ADR: ADR-011 (accepted) (`cli.py` is the composition root: it builds the adapters, calls the use case, prints and sets the exit code; `require_init()` is called first). ADR-010 (accepted) covers the recorder creating the database and tables when it opens; ADR-001 (accepted) covers the `EventRecorder` and `SpecVersions` ports. No new port, adapter, dependency, event type, payload, storage change or convention.
- Spec impact: none. Spec v1.9 settles the lines, their order, the count line, the status line, the exit codes, the streams and the missing `policies.yaml` line.
- Spec sections (spec v1.9): "CLI commands" (the command table, "Other commands", "Output"); "Spec input format" ("Validation rules", "Spec versions", "Policies"); "Milestones and definition of done" (milestone 1)

## Objective
Add the `openfactory validate` command to `src/openfactory/cli.py`: it wires the SQLite and filesystem adapters to the validate use case, prints one `rule  subject  message` line per violation and policy problem, the count line and the status line, and sets the exit code.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Acceptance criteria trace to spec headings instead.

## Scope
In:
- A `validate` command in `cli.py` with no arguments. It calls `require_init()`, opens `SqliteEventRecorder` on the returned path, then `SqliteSpecVersions` on the same path, builds `FilesystemSpecFiles(Path("specs"))`, calls `validate(files, versions, recorder)` and closes both adapters.
- A small helper in `cli.py` that turns violations, policy problems and an optional status line into the output lines (sorted violation lines, sorted policy lines, count line, status line). The `approve spec` command reuses it in the next task.
- Exit code 1 when there is any violation or policy problem, otherwise 0.
- The `schema` line for a missing `specs/policies.yaml` ("Later" item, decision of 2026-10-08; spec v1.9 "Policies"). `load_policy` already returns it; the command prints it like any other policy line.
- Tests that run the real app through `typer.testing.CliRunner` in directories under `tmp_path`, with `monkeypatch.chdir`.

Out (follow-up tasks, not this one):
- The `approve spec` command, its `approve` command group, the `approved sv_NN` status line, `nothing to approve` and its exit codes (the rest of outline item 1; next task).
- The `events` command (outline item 2) and the M1 close integration test (outline item 3).
- What a command prints when the recorder's catch-up fails (Later, F-1): the exception propagates.
- structlog configuration: this command writes no log line.
- The deleted-requirement rule (M2).
- Any change to `domain/`, `ports/`, `adapters/` or `app/`, and any change to an existing test file.
- Hardening against exotic inputs: a `specs` path that is a file, an unreadable database, a message that contains a line break.

## Acceptance criteria
Each criterion cites the spec v1.9 text it traces to. "Output" and "Other commands" are blocks under "CLI commands"; "Spec versions", "Policies" and "Validation rules" are under "Spec input format". In every criterion the real Typer app runs `validate` through `CliRunner` with the current directory set to a repo under `tmp_path` on which `init` was run, unless stated. "Valid spec files" means a `specs/requirements.yaml` and ADRs with no violation. Unless stated, `specs/policies.yaml` is the default file `init` wrote.

- [x] AC1 (Output: "`validate` and `approve spec` print one line per violation and per policy problem as `rule  subject  message`: first the violation lines, sorted by rule name, then by subject, then by message, as strings ... then a count line that is always printed, `N violations, M policy problems`", "The three fields are separated by exactly two spaces, with no padding", "The sort applies to the printed lines only; `SpecValidated.violations` is recorded in the order the rules returned it" and "`validate` exits with 1 if there is any violation or policy problem"): the spec files load and break at least two content rules, with two violations that share a rule.
  - Standard output is exactly one line per violation as `<rule>  <subject>  <message>`, in the order of `sorted` on `(rule, subject, message)` as strings, followed by the line `N violations, 0 policy problems`, where N is the number of violations. There is no status line.
  - The exit code is 1.
  - The event log holds `SpecImported` then `SpecValidated`, and the stored `SpecValidated.violations` is in the order `validate_spec` returns for the loaded spec set, not the printed order (the fixture makes the two orders differ).
- [x] AC2 (Output: "a count line that is always printed" and "`validate` exits with 1 if there is any violation or policy problem, otherwise 0"; Spec versions: "Otherwise it records `SpecImported` (...), then runs the rules and records `SpecValidated`"; Output: "Command results (violation, policy, count and status lines; event lines) go to standard output"): valid spec files, no spec version yet.
  - Standard output is exactly the one line `0 violations, 0 policy problems`; standard error is empty; the exit code is 0.
  - The `spec_versions` projection has one row, `sv_01`, with status `draft`.
  - With exactly one violation the count line is `1 violations, 0 policy problems` (Output: "The count line is not inflected").
- [x] AC3 (Spec versions: "If the spec files cannot be loaded (any `schema` violation in them), `validate` prints the violations, records no events, and exits 1. Policy problems are still printed"; Validation rules: "A file that cannot be loaded into the models is reported under the rule `schema`"): `specs/requirements.yaml` is not valid YAML.
  - Standard output has a line starting `schema  specs/requirements.yaml  `, then the count line `1 violations, 0 policy problems`; the exit code is 1; the `events` table has no rows.
  - With `specs/requirements.yaml` deleted, the output has a `schema` line with subject `specs/requirements.yaml`, the exit code is 1 and no event is recorded.
  - With an unknown key added to `specs/policies.yaml` as well, the policy line is printed after the violation line and the count line is `1 violations, 1 policy problems`.
- [x] AC4 (Spec versions: "If the hash equals the latest approved version's, it records no events, its output ends with the status line `matches approved sv_NN`, and it exits 0, or 1 if there are policy problems. The rules are not run"; Output: "then the status line, `matches approved sv_NN` or `approved sv_NN`, when there is one"): valid spec files that the test approved as `sv_01` by calling the `approve_spec` use case on the real adapters.
  - Standard output is exactly `0 violations, 0 policy problems` then `matches approved sv_01`; the exit code is 0; the number of rows in `events` is the same before and after the command.
  - With `max_attempts: 0` in `specs/policies.yaml`, the output is the policy line, `0 violations, 1 policy problems`, then `matches approved sv_01`, and the exit code is 1.
- [x] AC5 (Policies: "`openfactory validate` prints policy problems under the rule `schema`, with the file path as subject, and exits 1 ... Policy problems are not recorded in `SpecValidated`, do not stop the content rules" and "A missing file is a policy problem: a `schema` line with subject `specs/policies.yaml` and the message `missing; run openfactory init`, printed on standard output like any other policy line"; Output: "then the policy lines, sorted the same way"):
  - With valid spec files and `specs/policies.yaml` deleted, standard output is exactly `schema  specs/policies.yaml  missing; run openfactory init` then `0 violations, 1 policy problems`; the exit code is 1; the stored `SpecValidated.violations` is empty.
  - With spec files that have one content violation and a `specs/policies.yaml` with two problems (for example an unknown key and `max_attempts: 0`), the violation line comes first, then the two policy lines in sorted order, then `1 violations, 2 policy problems`; the exit code is 1; the stored `SpecValidated.violations` holds the content violation only.
- [x] AC6 (Other commands: "run against the current directory and fail with "run `openfactory init` first" if `./.openfactory/` is missing ... Only the directory is checked. A command creates a missing `openfactory.db`, and the tables it uses, when it opens the database"; Output: "A command that fails exits 1" and "Failure messages (...) and log lines go to standard error"):
  - In a directory with valid spec files and no `.openfactory/`, `validate` exits 1, standard error contains "run `openfactory init` first", standard output is empty, and no `.openfactory/` is created.
  - In an initialised repo whose `openfactory.db` the test deleted, `validate` on valid spec files exits 0, prints `0 violations, 0 policy problems`, and the database file exists again with a `SpecImported` and a `SpecValidated` in `events`.

## Architecture rules that apply
- The change is inside `src/openfactory/cli.py`, the composition root (ADR-011). It parses, wires, prints and sets the exit code, and holds no rule of its own: loading, hashing, the rules and the events stay in `app/validate.py`.
- No module under `domain/`, `ports/`, `adapters/` or `app/` imports `openfactory.cli`; none of them is changed.
- "All state changes go through the events table. Never write projections directly": the command's only write path is `EventRecorder.record` inside the use case.
- The recorder is opened before `SqliteSpecVersions`, because only the recorder creates the tables (ADR-010; decision of 2026-10-09, TASK-011).
- No filesystem work is added to `cli.py`: spec files are read through `FilesystemSpecFiles`. The `init` exception is not copied (ADR-011).
- No LLM call is made.

## Plan
1. Create branch `task/TASK-016-cli-validate` from an up-to-date main and commit this record.
2. Write failing tests in `tests/integration/test_cli_validate.py`, one or more per criterion AC1 to AC6, with `CliRunner`, `tmp_path` and `monkeypatch.chdir`. Helpers (repo setup, sample spec texts, reading `events`) are defined in the file; `tests/integration/test_cli_init.py` is not edited.
3. In `src/openfactory/cli.py` add the output helper: violation lines sorted by `(rule, subject, message)`, policy lines sorted the same way, the count line, then the status line when given; each line is `"  ".join(...)`.
4. Add the `validate` command: `require_init()`, open the recorder then `SqliteSpecVersions`, call the use case, close both in a `finally`, print the lines with the status line `matches approved <id>` for the `matches_approved` outcome, and raise `typer.Exit(1)` when there is any violation or policy problem.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
6. Update living docs and this record's Outcome; commit with trailers `Task: TASK-016` and `Milestone: M1`.

## Files expected to change
- `src/openfactory/cli.py` (the helper and the `validate` command)
- `tests/integration/test_cli_validate.py` (new)
- `docs/architecture.md` ("CLI": add `validate`, and `require_init` now has a caller; "Data flow": the validate use case is wired to a command)
- `docs/progress.md` (Current task, then Done; outline item 1 becomes "`approve spec` command" with its dependency on TASK-016; remove the Later line on the missing `policies.yaml`)
- `CHANGELOG.md` and `README.md` (the `validate` command)
- `docs/tasks/TASK-016-cli-validate.md` (this record; Outcome at close)

Not expected to change: everything under `src/openfactory/domain/`, `src/openfactory/ports/`, `src/openfactory/adapters/` and `src/openfactory/app/`, `pyproject.toml`, `docs/adr/`, and every existing test file. Expected size: under 300 lines, most of it tests.

## Living docs to update
- `docs/architecture.md`: the "CLI" component and Data flow.
- `docs/progress.md`: Current, M1 outline, Done and Later.
- `CHANGELOG.md` and `README.md`: the `validate` command.
- `docs/decisions.md`: no row expected.

## New dependencies
None.

## Spec gaps
None. Spec v1.9 states every line, order, stream and exit code this task prints or sets, including the missing `policies.yaml` line ("Policies", SC-25).

## Open questions
None.

## Outcome
- Built: the `validate` command in `src/openfactory/cli.py` (no arguments; `require_init()`, then `SqliteEventRecorder`, `SqliteSpecVersions` and `FilesystemSpecFiles(Path("specs"))`, the `validate` use case, both adapters closed, exit 1 on any violation or policy problem) and the helper `_result_lines(violations, policy_problems, status)`. The helper sorts the field tuples before joining them with two spaces, so the order is by rule, then subject, then message, as the spec says. Nothing changed under `domain/`, `ports/`, `adapters/` or `app/`.
- Tests: `tests/integration/test_cli_validate.py`, 13 tests for AC1 to AC6: 12 from the test-writer and one added after review.
- Deviations from plan: none in scope.
- Test edits: none while implementing. After the review, on the human's instruction, two additions that weaken nothing: the test `test_ac5_policy_lines_are_sorted_by_message` (two policy problems with one rule and one subject, returned by the loader in an order that is not the printed one, so the policy sort and the tie-break on the message are both exercised), and an assertion in the `run_validate` helper that standard error is empty for every run in an initialised repo.
- Review: verdict approve, no blocking issue. Its three non-blocking notes were applied on the human's instruction: the two test additions above, and the README usage line, which failed in a clean shell outside the checkout (`Failed to spawn: openfactory`) and now uses `uv run --project <path-to-openfactory>`.
- Follow-up: the `approve spec` command (TASK-017) reuses `_result_lines`.
