# TASK-019: M1 close integration test

- Milestone: M1
- Status: done
- Tests: integration-only (the deliverable is one integration test file over code that is already built and tested per command; no production code is expected to change. See Open questions, item 1)
- ADR: none new. ADR-010 (accepted) puts `rebuild()` on the adapter, not the port, and names its callers: "tests and the M1 close task do". ADR-002 (accepted) defines an identical rebuild and keeps rebuild "a function covered by tests", not a command. ADR-011 (accepted) covers `cli.py` as the composition root. No new port, adapter, dependency, event type, payload, storage change or convention.
- Spec impact: none. Spec v1.9 settles every line, exit code, event, stream and projection row this test asserts, and the meaning of an identical rebuild (SC-21, SC-24).
- Spec sections (spec v1.9): "Purpose and demo scenario" (demo steps 1, 2 and 6; success criteria); "Spec input format" ("Loading", "Validation rules", "Spec versions"); "Domain model and storage" ("Projections", "Projection rules", "Streams and actors"); "CLI commands" (the command table, "`init`", "Other commands", "Output"); "Milestones and definition of done" (milestone 1)

## Objective
Add one integration test that runs `init`, `validate`, `approve spec` and `events` through the real Typer app on a sample repo, and shows that the spec projections are identical after `SqliteEventRecorder.rebuild()` replays the log those commands wrote.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Acceptance criteria trace to spec headings instead.

## Scope
In:
- One new test file, `tests/integration/test_m1_close.py`, with its helpers and sample spec texts defined in the file (see Open questions, item 3).
- The sample repo: a directory under `tmp_path` with a `.git` directory, `specs/requirements.yaml` and `specs/adrs/*.md` written by the test, and `specs/policies.yaml` as `init` wrote it.
- The commands run through `typer.testing.CliRunner` with `monkeypatch.chdir`, as in `tests/integration/test_cli_events.py`.
- The rebuild is called on the adapter: `SqliteEventRecorder(<repo>/.openfactory/openfactory.db).rebuild()`.

Out (not this task):
- Any change under `src/`. If an assertion that traces to spec text fails, that is a defect: stop and ask, do not fix it inside this task and do not weaken the test.
- A `rebuild` CLI command (spec: "It is a function covered by tests, not a CLI command").
- Cases the per-command tests already cover: unloadable files, policy problems, the missing-init failure, a deleted database, non-ASCII, the JSON form of an `events` line, a repeated `init`, a failed rebuild rolling back.
- A real `git init`, a FastAPI target repo, or anything from M2 on (`plan`, the deleted-requirement rule).
- Every "Later" line in `docs/progress.md`: catch-up failure output (F-1), narrowing `EventStore`, usage errors on standard error, the exact-match wording of `--stream`, loader tests for merge keys and aliases.
- Releasing 0.1.0 (see Open questions, item 2).

## Sample repo
Three states of the spec files, all written by the test. Exact titles and statements are the test's choice; the ids, statuses and counts below are fixed, because the criteria depend on them.

- State 1: `components: [auth]`; `REQ-AUTH-001` (login with membership number, `constrained_by: [ADR-001]`, two acceptance criteria) and `REQ-AUTH-002` (a supporting requirement, one acceptance criterion); `adrs/ADR-001-auth-method.md` with `status: accepted` and a body.
- State 2a: `REQ-AUTH-001` rewritten to OTP, with `constrained_by: [ADR-001, ADR-002]`; a new `adrs/ADR-002-otp.md` with `status: proposed`. This has exactly one violation, `constrained-by` on `REQ-AUTH-001`.
- State 2b: state 2a with `ADR-002` changed to `status: accepted`. No violation.
- State 3: state 2b plus a new `REQ-AUTH-003` with one acceptance criterion. No violation.

The flow, called "the flow" below:
1. `init <repo>`
2. `validate` (state 1)
3. `approve spec`
4. `validate`
5. write state 2a, `validate`
6. write state 2b, `approve spec`
7. write state 3, `validate`

## Acceptance criteria
Each criterion cites the spec v1.9 text it traces to. "Loading", "Validation rules" and "Spec versions" are blocks under "Spec input format"; "Projections", "Projection rules" and "Streams and actors" are under "Domain model and storage"; "`init`" and "Output" are under "CLI commands". A snapshot is every row of `spec_versions` (ordered by `id`), `requirements` and `adrs` (ordered by `spec_version, id`), read with `SELECT *` on a connection the test opens.

- [x] AC1 ("Purpose and demo scenario": "`openfactory validate` checks the specs; the human runs `openfactory approve spec` to freeze spec v1"; `init`: "It prints one line per item on standard output, in the order `.openfactory/openfactory.db`, `.openfactory/.gitignore`, `specs/policies.yaml`, as `created <path>` or `exists <path>`" and "It records no events"; Loading: "The loader reads `specs/requirements.yaml` (required) and every `specs/adrs/*.md`"; Spec versions: "If the hash equals the latest approved version's, it records no events, its output ends with the status line `matches approved sv_NN`, and it exits 0"; Output: "`approve spec` exits 0 on success, and its output ends with the status line `approved sv_NN`"): steps 1 to 4 of the flow.
  - Step 1 prints the three `created` lines in the spec's order and exits 0; the `events` table is empty.
  - Step 2 prints exactly `0 violations, 0 policy problems` and exits 0.
  - Step 3 prints that line then `approved sv_01` and exits 0.
  - Step 4 prints that line then `matches approved sv_01`, exits 0, and adds no row to `events`.
- [x] AC2 ("Purpose and demo scenario": "The human edits the requirement: users authenticate with OTP instead. Approves spec v2"; Validation rules: "Every `constrained_by` reference points to an existing ADR with status `accepted`"; Spec versions: "an existing draft keeps its id and its content is replaced; if there is no draft, the next id is used", "Edits after that create a new draft version on the next `validate` or `approve spec`" and "Because a draft keeps its id until it is approved, approved versions are numbered without gaps"; Output: "`validate` exits with 1 if there is any violation or policy problem, otherwise 0"): steps 5 to 7 of the flow.
  - Step 5 prints one line starting `constrained-by  REQ-AUTH-001  `, then `1 violations, 0 policy problems`, and exits 1.
  - Step 6 prints `0 violations, 0 policy problems` then `approved sv_02` and exits 0.
  - Step 7 prints exactly `0 violations, 0 policy problems` and exits 0.
- [x] AC3 (the command table: "`openfactory events [--stream S]` | Raw audit log"; Output: "`events` prints one stored event per line, in `seq` order"; Spec versions: "If the hash equals the current draft's, it records no `SpecImported`" and "`approve spec` records `SpecValidated` with the rule results before `SpecApproved`"; Streams and actors: the rows "`SpecImported`, `SpecValidated` | `spec:<spec version id>` | `orchestrator`" and "`SpecApproved` | `spec:<spec version id>` | `human`", and "`causation_id` is the `event_id` of the event recorded just before it in the same command; the first event a command records has none"): after the flow, `events` exits 0 and prints 11 lines in ascending `seq`.
  - The types in order are `SpecImported`, `SpecValidated` (step 2); `SpecValidated`, `SpecApproved` (step 3); `SpecImported`, `SpecValidated` (step 5); `SpecImported`, `SpecValidated`, `SpecApproved` (step 6); `SpecImported`, `SpecValidated` (step 7).
  - The streams are `spec:sv_01` for the first four lines, `spec:sv_02` for the next five and `spec:sv_03` for the last two. The actor is `human` on the two `SpecApproved` lines and `orchestrator` on the others.
  - `causation_id` is `null` on the first line of each command's group (lines 1, 3, 5, 7 and 10) and is the `event_id` of the line before on every other line.
  - `events --stream spec:sv_02` prints exactly the five `spec:sv_02` lines, each identical to the same line of the unfiltered output.
- [x] AC4 (Projections: the table rows for `spec_versions`, `requirements` and `adrs`; Projection rules: "Use cases record every event through the `EventRecorder` port ... so an event is never stored without its projections being updated" and "M1 `spec_versions`, `requirements`, `adrs`"; Spec versions: "an existing draft keeps its id and its content is replaced"): after the flow, read on a connection the test opens.
  - `spec_versions` holds `sv_01` and `sv_02` with status `approved` and a non-null `approved_at`, and `sv_03` with status `draft` and a null `approved_at`.
  - `requirements` holds 2 rows for `sv_01`, 2 for `sv_02` and 3 for `sv_03`; `adrs` holds 1, 2 and 2.
  - The `adrs` row (`sv_02`, `ADR-002`) has status `accepted`: the draft content from step 5 was replaced.
  - `projection_state` is the single row (`1`, the highest `seq` in `events`).
- [x] AC5 ("Milestones and definition of done", milestone 1: "replay rebuilds projections identically"; Projection rules: "Rebuilding means emptying the projection tables (dropping and recreating them counts), replaying all events in `seq` order, and setting `last_seq` to the highest `seq`, or 0 for an empty log, in one transaction", "`projection_state` is never dropped. It is a function covered by tests, not a CLI command" and "A rebuild is identical when, for every projection table, the rows read in primary-key order are equal before and after"; "Domain model and storage": "The `events` table is the source of truth; every other table is a projection rebuilt from it"): after the flow, the test takes a snapshot, then deletes every row of the three projection tables on its own connection and commits.
  - Before the rebuild the snapshot is empty, so it differs from the first one (the comparison is not vacuous).
  - After `SqliteEventRecorder(<db>).rebuild()`, the snapshot equals the one taken before the delete, table by table.
  - `projection_state` is still the single row (`1`, the highest `seq`), and the rows of `events` are the same as before the rebuild.
- [x] AC6 ("Purpose and demo scenario", success criteria: "Every state change can be reconstructed from the event log"; Spec versions: "If the hash equals the current draft's, it records no `SpecImported`. It runs the rules and records `SpecValidated` for the draft again" and "Otherwise it records `SpecApproved`, and the version is immutable from then on"): after the delete and rebuild of AC5, with the files still in state 3, `approve spec` runs on the rebuilt projections.
  - It prints `0 violations, 0 policy problems` then `approved sv_03` and exits 0.
  - The events it adds are exactly `SpecValidated` then `SpecApproved`, both on `spec:sv_03`. No `SpecImported` is added, so the rebuilt draft's hash equals the files' hash.
  - `spec_versions` then holds three rows, all `approved`.

## Architecture rules that apply
- No module under `src/` changes. The test imports `openfactory.cli.app` and `SqliteEventRecorder` only; `rebuild()` is reached on the adapter class because it is not on the `EventRecorder` port (ADR-010).
- "All state changes go through the events table. Never write projections directly" is a rule for production code. The `DELETE` in AC5 is test-side damage to disposable tables, as the stray row in `tests/integration/test_sqlite_recorder.py` AC6 is; the test never writes the `events` table.
- The recorder's catch-up applies nothing when the test opens it for AC5, because `last_seq` already equals the highest `seq`; only `rebuild()` refills the tables. The recorder is closed before `approve spec` runs in AC6.
- OpenFactory's own tests carry no `req` markers.
- No LLM call is made and no `git` process is started.

## Plan
1. Create branch `task/TASK-019-m1-close-integration-test` from an up-to-date main and commit this record.
2. Record the answers to the open questions here and, where they are decisions, as rows in `docs/decisions.md`.
3. Write `tests/integration/test_m1_close.py`: the sample spec texts for states 1, 2a, 2b and 3; a helper that makes the repo under `tmp_path` and runs the flow, returning each step's result; helpers `query` and `snapshot` in the shape of those in `tests/integration/test_cli_events.py` and `tests/integration/test_sqlite_recorder.py`. One test or more per criterion AC1 to AC6; each test runs the flow on its own `tmp_path`. No existing test file is edited.
4. Run the new file. It is expected to pass without any change under `src/`, since each command is already built and tested; "confirm it fails" does not apply as written (Open questions, item 1). AC5's first bullet is the check that the comparison can fail. If any assertion fails, stop and report the defect with the spec text it breaks; do not change `src/` or the assertion without the human's answer.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
6. Update living docs and this record's Outcome; commit with subject `test(cli): add the M1 close integration test` and trailers `Task: TASK-019` and `Milestone: M1`.

## Files expected to change
- `tests/integration/test_m1_close.py` (new, about 200 lines)
- `docs/progress.md` (Current, then Done; the M1 outline becomes empty; the M1 box under "Milestones" per Open questions, item 2)
- `docs/decisions.md` (rows for the answered open questions, if they are decisions)
- `docs/tasks/TASK-019-m1-close-integration-test.md` (this record; Outcome at close)

Not expected to change: everything under `src/`, every existing test file, `pyproject.toml`, `docs/adr/`, `docs/architecture.md` (no component or data flow changes), `CHANGELOG.md` and `README.md` (nothing a user sees changes). Expected size: under 300 lines, almost all of it the test file.

## Living docs to update
- `docs/progress.md`: Current, M1 outline, Done, and the M1 milestone box.
- `docs/decisions.md`: rows for the open questions.
- `docs/architecture.md`, `CHANGELOG.md`, `README.md`: no change expected.

## New dependencies
None.

## Spec gaps
None. Two readings to record, neither a gap:
- "A sample repo" in the outline is read as a directory with a `.git` entry and spec files. The spec's `init` block accepts that as a git repository ("an existing directory that contains a `.git` entry ... no `git` process is started"), and no M1 command reads anything else in the repo.
- "Rows ... are equal before and after" is tested across a rebuild that starts from emptied tables, which is stricter than a rebuild over intact tables and inside the spec's definition ("emptying the projection tables ... replaying all events").

## Open questions
All three answered by the human on 2026-10-10, each as proposed.
1. **Tests field and the "confirm it fails" step.** `Tests: integration-only`. The session writes the one test file itself; "confirm it fails" is replaced by AC5's first bullet (the snapshot is empty after the delete and before the rebuild). The session may fix a mechanical error in its own test, and stops to ask only when an assertion that traces to spec text fails. This deviates from `/next-task` step 2 for this one task.
2. **What closing M1 changes in the docs.** This task ticks `[x] M1 Specs and events` in `docs/progress.md` and leaves "Milestone: M1" under Current. Cutting the `0.1.0` section in `CHANGELOG.md` is left to the human.
3. **Where the sample repo lives.** Inline strings in the test file, written under `tmp_path`.

## Outcome
Built `tests/integration/test_m1_close.py`: six tests (AC1 to AC6) that run `init`, `validate`, `approve spec` and `events` through the Typer app on a sample repo under `tmp_path`, with four spec-file states written inline (state 1, 2a with a proposed ADR-002, 2b with it accepted, 3 with a third requirement). They check the output lines, the exit codes, the 11 events with their streams, actors and causation chain, and the projection rows. They also check that `SqliteEventRecorder.rebuild()` restores the three projection tables identically after the test empties them, and that `approve spec` then approves `sv_03` on the rebuilt projections, adding only `SpecValidated` and `SpecApproved`. No file under `src/` changed. All six tests passed on their first run; 588 tests pass, ruff, pyright and check_docs are clean.

Deviations from the plan:
- The record was not committed on its own in Plan step 1; the task has one commit, as `/next-task` step 6 words it.
- The tests passed on their first run with no fail-first step, as agreed in open question 1. AC5's empty snapshot before the rebuild is the check that the comparison can fail.
- No mechanical fix to the test and no `src/` defect came up.

Follow-ups:
- The human cuts the `0.1.0` section in `CHANGELOG.md` ("M1 -> 0.1.0").
- One "Later" line stays open against M1: bare `openfactory` and `openfactory approve` print help on standard output, where the spec sends usage errors to standard error.
