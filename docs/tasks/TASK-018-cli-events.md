# TASK-018: `events` command

- Milestone: M1
- Status: done
- Tests: acceptance
- ADR: none new. ADR-011 (accepted) covers `cli.py` as the composition root and `require_init()` being called first. ADR-001 (accepted) names `EventStore` as "the port for reading the log (`openfactory events`, rebuild)". ADR-010 (accepted) covers the shared `events` table SQL. No new port, adapter, dependency, event type, payload, storage change or convention. The shape of the use case is a row in `docs/decisions.md` (Open questions, item 1).
- Spec impact: none. Spec v1.9 settles the keys of a line, key order (sorted at every level), separators, non-ASCII, list order, the form of `created_at`, `--stream` with no match, the missing-init failure, a missing database file, the output stream and the exit codes (SC-2, SC-11, SC-19, SC-20).
- Spec sections (spec v1.9): "CLI commands" (the command table, "Other commands", "Output"); "Domain model and storage" (the `events` DDL, "Event envelope rules", "Streams and actors"); "Tech stack and repo layout"; "Milestones and definition of done" (milestone 1)

## Objective
Add the `openfactory events [--stream S]` command to `src/openfactory/cli.py`: it reads the stored events through the `EventStore` port and prints one JSON object per line in `seq` order, in the form the spec's "Output" block gives.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Acceptance criteria trace to spec headings instead.

## Scope
In:
- A use case `list_events(store: EventStore, stream: str | None = None) -> list[StoredEvent]` in a new module `src/openfactory/app/list_events.py`. It reads through the `EventStore` port only and returns data (CLAUDE.md: "every other command calls a use case"; see Open questions, item 1).
- An `events` command in `cli.py` with one option, `--stream S`. It calls `require_init()`, opens `SqliteEventStore` on the returned path, calls `list_events`, closes the store, and prints one line per event on standard output.
- A private helper in `cli.py`, next to `_result_lines`, that turns one `StoredEvent` into its output line.
- Tests through `typer.testing.CliRunner` in directories under `tmp_path` with `monkeypatch.chdir`, and one unit test of the use case with a fake `EventStore`.

Out (not this task):
- The M1 close integration test (outline item 2) and any use of `rebuild()`.
- Opening `SqliteEventRecorder` in this command. The decision of 2026-10-09 (SC-20) keeps `events` off the recorder, so a stored event the catch-up rejects does not block the one command that shows the log.
- Narrowing `EventStore` to reading (Later; ADR-001, ADR-010). The command calls `read` only; `append` stays on the port.
- A stored row whose envelope `StoredEvent` rejects, or a `created_at` written by hand in another form: the exception propagates.
- structlog configuration: this command writes no log line.
- Usage errors on standard error for a bare `openfactory` (Later, TASK-014 and TASK-017).
- Any change to `domain/`, `ports/` or `adapters/`, to the other commands, and to any existing test file.
- Hardening against exotic inputs: an empty `--stream` value, an unreadable database, a payload depth limit (Later).

## Acceptance criteria
Each criterion cites the spec v1.9 text it traces to. "Output" and "Other commands" are blocks under "CLI commands"; "Event envelope rules" and "Streams and actors" are under "Domain model and storage". In AC1 to AC5 the real Typer app runs `events` through `CliRunner` with the current directory set to a repo under `tmp_path` on which `init` was run, unless stated. Events are produced by running `validate` and `approve spec` through the same app.

- [x] AC1 (Output: "`events` prints one stored event per line, in `seq` order, as one JSON object with the keys `seq`, `event_id`, `stream`, `type`, `payload` (a nested object), `actor`, `causation_id` and `created_at`" and "Command results (violation, policy, count and status lines; event lines) go to standard output"; Streams and actors: "the first event a command records has none"): valid spec files approved as `sv_01` by one `approve spec` run.
  - Standard output is exactly three lines, standard error is empty, and the exit code is 0.
  - Each line parses as a JSON object with exactly the eight keys.
  - The lines are in ascending `seq`, with types `SpecImported`, `SpecValidated`, `SpecApproved`.
  - For each line, `seq`, `event_id`, `stream`, `type`, `actor` and `causation_id` equal the row of the `events` table with that `seq`; `payload` is a JSON object (not a string) equal to the stored payload parsed as JSON.
  - `causation_id` of the first line is JSON `null`; of the second and third it is the `event_id` of the line before.
- [x] AC2 (Output: "with sorted keys at every level, separators `,` and `:` with no spaces, and non-ASCII characters left as they are" and "`created_at` is printed as it is stored, in ISO 8601 with the offset `+00:00`, the same form as `approved_at`"): the same flow, with a non-ASCII character in a requirement's title (for example `é`).
  - Every line equals `json.dumps(json.loads(line), sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.
  - The `SpecImported` line contains the non-ASCII character itself and no `\u` escape for it.
  - On every line, `created_at` equals the text in that row's `created_at` column and ends with `+00:00`; on the `SpecApproved` line it equals `spec_versions.approved_at` for `sv_01`.
- [x] AC3 (Output: "lists keep their stored order" and "The sort applies to the printed lines only; `SpecValidated.violations` is recorded in the order the rules returned it"): spec files that load and whose violations, in the order `validate_spec` returns them, are not in sorted order (the kind of fixture `tests/integration/test_cli_validate.py` uses for its AC1), after one `validate` run.
  - In the `SpecValidated` line, `payload.violations` is in the same order as in the stored payload, which is not the order of `sorted` on `(rule, subject, message)`.
- [x] AC4 (the command table: "`openfactory events [--stream S]` | Raw audit log"; Output: "With `--stream S` and no matching events it prints nothing and exits 0"; Event envelope rules: "`seq` is assigned by the store"; Streams and actors: the table rows "`spec:<spec version id>`"): `sv_01` is approved, then a requirement is edited and `validate` is run, so the log holds events on `spec:sv_01` and `spec:sv_02`.
  - `events --stream spec:sv_02` prints only the lines whose `stream` is `spec:sv_02`, in ascending `seq`, and each is identical to the line with the same `seq` in the output of `events` with no option. The exit code is 0.
  - `events --stream spec:sv_99` prints nothing on standard output and exits 0.
- [x] AC5 (Other commands: "run against the current directory and fail with "run `openfactory init` first" if `./.openfactory/` is missing ... Only the directory is checked. A command creates a missing `openfactory.db`, and the tables it uses, when it opens the database"; Output: "`events` prints one stored event per line", "A command that fails exits 1" and "Failure messages (...) and log lines go to standard error"):
  - In a directory with no `.openfactory/`, `events` exits 1, standard error contains "run `openfactory init` first", standard output is empty, and no `.openfactory/` is created.
  - In a repo straight after `init` (no events), `events` prints nothing and exits 0.
  - In an initialised repo whose `openfactory.db` the test deleted, `events` prints nothing, exits 0, and the database file exists again with an `events` table.
- [x] AC6 ("Tech stack and repo layout": "a hexagonal layout: the domain never imports infrastructure", "`app/` # use cases" and "`ports/` # interfaces: EventStore, ..."; depends on Open questions, item 1): the use case, called with a fake `EventStore`.
  - `list_events(store)` returns what `store.read(None)` returns, unchanged and in the same order; `list_events(store, "spec:sv_01")` passes the stream to `read`.
  - The fake's `append` is never called.
  - `src/openfactory/app/list_events.py` imports nothing from `openfactory.adapters`.

## Architecture rules that apply
- `cli.py` is the composition root (ADR-011): it parses, wires, prints and sets the exit code. The command calls a use case; the `init` exception is not copied.
- `app/list_events.py` depends on `openfactory.domain` and `openfactory.ports` only.
- The command writes no event and no projection row. It opens `SqliteEventStore`, not the recorder, so no catch-up runs (SC-20). The store creates a missing database file and the `events` table, the one table this command uses.
- Nothing under `domain/`, `ports/`, `adapters/` or `app/` imports `openfactory.cli`.
- No LLM call is made.

## Plan
1. Create branch `task/TASK-018-cli-events` from an up-to-date main and commit this record.
2. Record the answer to Open questions, item 1, here and as a row in `docs/decisions.md`.
3. Write failing tests: `tests/integration/test_cli_events.py` for AC1 to AC5 (helpers defined in the file, in the shape of those in `tests/integration/test_cli_approve_spec.py`; no existing test file is edited) and `tests/unit/test_list_events_use_case.py` for AC6.
4. Add `src/openfactory/app/list_events.py` with `list_events(store, stream=None)`, which returns `store.read(stream)`.
5. In `cli.py` add the line helper. It builds a dict with the eight keys and dumps it with `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)`. `created_at` must be `event.created_at.isoformat()`, the form `sqlite_events.insert_event` and the projector's `approved_at` use. Do not take it from `model_dump(mode="json")`: Pydantic v2 writes a UTC datetime with a `Z` suffix, which fails AC2 (audit finding F-7, SC-19). `event_id` and `causation_id` are `str(...)`, with `None` for a missing `causation_id`; `type` is the enum's value.
6. Add the `events` command: `require_init()`, open `SqliteEventStore`, call `list_events(store, stream)`, close the store in a `finally`, `typer.echo` each line. The option is `--stream`, a string defaulting to `None`. No exit code is raised on an empty result.
7. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
8. Update living docs and this record's Outcome; commit with trailers `Task: TASK-018` and `Milestone: M1`.

## Files expected to change
- `src/openfactory/app/list_events.py` (new)
- `src/openfactory/cli.py` (the line helper and the `events` command)
- `tests/integration/test_cli_events.py` (new)
- `tests/unit/test_list_events_use_case.py` (new)
- `docs/architecture.md` ("CLI": add `events` and the helper; a short "List events use case" component; "Data flow": `EventStore.read` now has a caller, the `events` command)
- `docs/progress.md` (Current, then Done; remove item 1 from the M1 outline and point the remaining item's "depends on" at TASK-018)
- `docs/decisions.md` (one row: the use case's shape and where the line is rendered)
- `CHANGELOG.md` and `README.md` (the `events` command)
- `docs/tasks/TASK-018-cli-events.md` (this record; Outcome at close)

Not expected to change: everything under `src/openfactory/domain/`, `src/openfactory/ports/` and `src/openfactory/adapters/`, `pyproject.toml`, `docs/adr/`, and every existing test file. Expected size: under 300 lines, most of it tests.

## Living docs to update
- `docs/architecture.md`: Components ("CLI", the new use case) and Data flow.
- `docs/progress.md`: Current, M1 outline and Done.
- `docs/decisions.md`: the row for Open questions, item 1.
- `CHANGELOG.md` and `README.md`: the `events` command.

## New dependencies
None. `json` is in the standard library.

## Spec gaps
None. Three readings to record, none of which is a gap and none of which a test depends on beyond the spec's own words:
- `causation_id` is in the spec's key list and the column is nullable, so the key is always present and is JSON `null` when the event has none.
- "No matching events" is read as no event whose `stream` equals `S`, which is what `EventStore.read(stream)` does (decision of 2026-10-08, TASK-002). AC4 uses only a full stream name and a name no event has; a prefix such as `spec` is not tested.
- "Printed as it is stored": the store returns `StoredEvent`, whose `created_at` is a datetime, so the line is `isoformat()` of the parsed value. That is byte-identical to the column for every value the adapters write; a row written by hand in another form is out of scope.

## Open questions
1. **Shape of the use case, and where the line is rendered.** Answered 2026-10-10 by the human: the proposed option (row in `docs/decisions.md`).
   - Proposed: `list_events(store, stream=None) -> list[StoredEvent]` in `app/list_events.py`, a pass-through over `EventStore.read`; the JSON line is rendered by a private helper in `cli.py`, as `_result_lines` does for `validate` and `approve spec` (use cases "return data and print nothing"). This satisfies CLAUDE.md ("`init` is the one command whose filesystem work lives in cli.py; every other command calls a use case").
   - Alternative A: the use case returns the rendered lines, so the spec's line form sits in one function testable without a database. It moves output formatting into `app/`, against the `_result_lines` precedent.
   - Alternative B: no use case; `cli.py` calls `SqliteEventStore.read` directly. ADR-011 requires a use case only for "a command with a domain rule or an event", and `events` has neither, but CLAUDE.md's sentence is stricter and only the human can change it. AC6 is dropped under this answer.

## Outcome
Built as planned.
- `src/openfactory/app/list_events.py`: `list_events(store, stream=None)`, a pass-through over `EventStore.read`.
- `cli.py`: the private `_event_line` helper (eight keys, `json.dumps` with sorted keys, separators `,` and `:`, `ensure_ascii=False`, `created_at` via `isoformat()`) and the `events` command with `--stream`: `require_init()`, `SqliteEventStore` (not the recorder), `list_events`, close, echo each line.
- Tests: `tests/integration/test_cli_events.py` (AC1 to AC5) and `tests/unit/test_list_events_use_case.py` (AC6).
- Test edits: one, asked for by the human after review (reviewer note 3): `test_ac4_stream_filter_returns_only_that_stream` gained `assert none.stderr == ""` for the `--stream spec:sv_99` case. An added assertion; nothing was weakened.
- Reviewer notes applied at the human's request: the `require_init()` bullet in `docs/architecture.md` now names `events`; the exact-match reading of `--stream` is a "Spec wording" line under Later in `docs/progress.md`.
- Deviations: plan step 1's separate commit of this record was not made; the record is in the task's one commit.
- Follow-ups: none new.
