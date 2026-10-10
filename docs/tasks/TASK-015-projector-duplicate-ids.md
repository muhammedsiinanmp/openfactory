# TASK-015: Projector keeps the first of two items with one id

- Milestone: M1
- Status: done
- Tests: acceptance
- ADR: ADR-009 and ADR-010 (both accepted, both already amended for SC-12). ADR-009 states the behaviour: "the projector keeps the first in the payload's order and skips the others". ADR-010 keeps the catch-up's `sqlite3.IntegrityError` case and notes that no M1 event reaches it since spec v1.9. No new port, adapter, dependency, event type, payload change, storage schema change or convention. How the rewritten recorder test makes the projector fail is a row in `docs/decisions.md` (2026-10-10, TASK-015; Open questions, item 1).
- Spec impact: none. Spec v1.9 (SC-12) settles the behaviour; the DDL is unchanged.
- Spec sections (spec v1.9): "Domain model and storage" ("Projection rules", the M1 DDL, "Event payloads"); "Spec input format" ("Validation rules", "Spec field rules", "Spec versions")

## Objective
Make `SqliteProjector` keep the first of two requirements, or two ADRs, with one id in a `SpecImported` and skip the others, so a spec set with a duplicated id is imported and gets its `id-unique` violation instead of ending in `sqlite3.IntegrityError`.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Acceptance criteria trace to spec headings instead.

## Scope
In:
- `adapters/sqlite_projector.py`: the two `INSERT` statements in `_apply_imported` (requirements and ADRs) become `INSERT OR IGNORE` (decisions row SC-12). Rows are inserted in the payload's order, so the first item with an id is the one kept.
- New tests for the projector, the recorder (record, catch-up, rebuild) and the validate and approve-spec use cases on the real SQLite adapters, all with a duplicated id.
- One edit to a fixed test: `test_ac5_stored_event_the_projector_cannot_write_fails_the_open_naming_seq_and_model` in `tests/integration/test_sqlite_recorder.py`. Only its setup changes (lines 433 and 434, the duplicated-id import). Its name and its five assertions stay as they are. The human approves the edit in this task (decisions row SC-12; Open questions, item 1).

Out (follow-up tasks, not this one):
- The `validate` and `approve spec` commands, the printed `id-unique` line, the count line and exit codes (outline item 2).
- The `events` command (outline item 3) and the M1 close integration test (outline item 4).
- Any change to the DDL, the payload models, `domain/`, `ports/`, `app/`, `sqlite_recorder.py` or `sqlite_events.py`. The recorder's `sqlite3.IntegrityError` branch stays (ADR-010).
- Duplicate acceptance criterion ids: they sit in a JSON column and were never affected.
- Deduplicating in the use case or the loader, or reporting the duplicate as `schema` (rejected alternative in SC-12).
- Any other edit to an existing test.

## Acceptance criteria
Each criterion cites the spec v1.9 text it traces to. "Projection rules" and "Event payloads" are blocks under "Domain model and storage"; "Validation rules", "Spec field rules" and "Spec versions" are under "Spec input format". "A duplicated requirement" means two `Requirement` models with the same `id` and different `title`; "a duplicated ADR" means two `Adr` models with the same `id` and different `body`.

- [x] AC1 (Projection rules: "When a `SpecImported` holds two requirements, or two ADRs, with the same id, the projector keeps the first in the payload's order and skips the others"; Event payloads: "Item hashes are not in `SpecImported`; the projector computes them from the content"): `SqliteProjector.apply` on a `SpecImported` whose `spec.requirements` is `[A, B, C]`, where A and B share an id and C has another.
  - `apply` does not raise.
  - `requirements` holds exactly two rows for that version: one for the shared id with A's `title` and `hash` equal to `content_hash(A)`, and C's row.
  - With the payload order `[B, A, C]` the kept row is B's.
  - The `spec_versions` row is written as for any import.
- [x] AC2 (the same Projection rules sentence, "or two ADRs"): `apply` on a `SpecImported` whose `spec.adrs` is `[X, Y]` with one id.
  - `apply` does not raise.
  - `adrs` holds one row for that version, with X's `status`, `body` and `hash` equal to `content_hash(X)`.
  - With the order `[Y, X]` the kept row is Y's.
  - The requirement rows of the same import are written as usual.
- [x] AC3 (Projection rules: "Its adapter appends the event and applies it to the projections in one transaction"; "A rebuild is identical when, for every projection table, the rows read in primary-key order are equal before and after"): on a fresh database, `SqliteEventRecorder.record` is given a `SpecImported` with a duplicated requirement and a duplicated ADR, then a `SpecValidated`.
  - `record` does not raise; both events are stored; `projection_state.last_seq` is the `seq` of the second.
  - After `rebuild()`, the rows of `spec_versions`, `requirements` and `adrs` read in primary-key order equal the rows before, and `last_seq` is unchanged.
  - A later `SpecImported` for the same draft with no duplicate replaces the content: the rows equal those of a database that only ever received the later import.
- [x] AC4 (Projection rules: "When the recorder opens the database, it applies every event with `seq > last_seq`" and "If the catch-up meets a stored event it cannot apply, it applies nothing, and a command that opens the recorder fails, naming the event's `seq`"):
  - A `SpecImported` with a duplicated requirement, appended through `SqliteEventStore` behind a closed recorder, is applied when a recorder next opens: the open does not raise, the projections equal those of a reference database that received the same events through `record`, and `last_seq` is the highest `seq`.
  - The rewritten fixed test still passes with its assertions unchanged: a stored event that passes its model but that the projector cannot write makes the open raise `sqlite3.IntegrityError` whose message contains `seq N` and `SpecImportedPayload`, with a `sqlite3.IntegrityError` as its cause, and the projections and `projection_state` are as before. Its setup no longer uses a duplicated id (Open questions, item 1).
- [x] AC5 (Projection rules: "Such a version has an `id-unique` violation and can never be approved"; Validation rules: "IDs ... are unique across the whole spec set"; Spec field rules: "The subject of `id-format` and `id-unique` is the offending id"; Spec versions: "Otherwise it records `SpecImported` (...), then runs the rules and records `SpecValidated`" and "If they load but have violations, it records `SpecImported` (if the files changed) and `SpecValidated` with the violations, then refuses without recording `SpecApproved`"): spec files under `tmp_path` in which two requirements have the id `REQ-AUTH-001`, read through `FilesystemSpecFiles`, with `SqliteEventRecorder` opened before `SqliteSpecVersions` on one database file.
  - `validate(files, versions, recorder)` does not raise; its outcome is `validated` for `sv_01`, and its violations include one with rule `id-unique` and subject `REQ-AUTH-001`.
  - The event log holds `SpecImported` then `SpecValidated`, and the stored `SpecValidated.violations` includes that `id-unique` entry.
  - `approve_spec(files, versions, recorder)` on the same files returns `refused`; no `SpecApproved` is stored; the `spec_versions` row for `sv_01` still has status `draft`.

## Architecture rules that apply
- The change is inside `src/openfactory/adapters/sqlite_projector.py`. The projector still imports only from `openfactory.domain` and the standard library, has no port and no conformance assertion (ADR-009).
- "All state changes go through the events table. Never write projections directly": the projector remains the only writer of the three tables, and its only caller is the recorder. The trigger a test may create (Open questions, item 1) is test-side SQL on a temporary database, not a projection write.
- The projector uses only data in the event; a rebuild must stay identical. "First" is the payload's order, which the projector does not change.
- `app` is not changed and still imports nothing from `adapters`. The AC5 test wires adapters to use cases in test code only.
- No LLM call is made.

## Plan
1. Create branch `task/TASK-015-projector-duplicate-ids` from an up-to-date main and commit this record.
2. Get the human's answers to the Open questions; record them here and in `docs/decisions.md`.
3. Write failing tests in a new file `tests/integration/test_duplicate_ids.py`, one or more per criterion AC1 to AC5 (first bullet of AC4). If the AC5 test fails for a reason outside the projector, stop and ask; do not widen the scope. Its helpers are defined in the file, in the same shape as those in `tests/integration/test_sqlite_recorder.py`.
4. Rewrite the setup of the one fixed test in `tests/integration/test_sqlite_recorder.py` as answered in Open questions, item 1. With the trigger it passes both before and after step 5. Report the edit in the Outcome.
5. In `src/openfactory/adapters/sqlite_projector.py`, change the two `INSERT INTO` statements in `_apply_imported` to `INSERT OR IGNORE INTO`, with a comment naming the spec rule. `executemany` keeps the list order, so no sorting or Python-side deduplication is added.
6. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
7. Update living docs and this record's Outcome; commit with trailers `Task: TASK-015` and `Milestone: M1`.

## Files expected to change
- `src/openfactory/adapters/sqlite_projector.py` (two statements and a comment)
- `tests/integration/test_duplicate_ids.py` (new)
- `tests/integration/test_sqlite_recorder.py` (setup of one test only)
- `docs/architecture.md` ("SQLite projector": add the keep-first sentence to the `apply` bullet; "SQLite recorder": say that no M1 event reaches the `sqlite3.IntegrityError` case)
- `docs/progress.md` (Current task, then Done; remove item 1 from the M1 outline and renumber the "depends on" references in the remaining items)
- `docs/decisions.md` (one row: how the rewritten test makes the projector fail)
- `docs/tasks/TASK-015-projector-duplicate-ids.md` (this record; Outcome at close)

Not expected to change: everything under `src/openfactory/domain/`, `src/openfactory/ports/` and `src/openfactory/app/`, `src/openfactory/adapters/sqlite_recorder.py`, `src/openfactory/cli.py`, `pyproject.toml`, `docs/adr/` (ADR-009 and ADR-010 already carry SC-12), and every other existing test. Expected size: well under 300 lines, almost all of it tests.

## Living docs to update
- `docs/architecture.md`: the two component bullets above.
- `docs/progress.md`: Current, M1 outline and Done.
- `docs/decisions.md`: the row above.
- `CHANGELOG.md`: no entry expected (no command reaches this code yet).
- `README.md`: no change expected.

## New dependencies
None.

## Spec gaps
None. Spec v1.9 states the rule under "Projection rules", and the decisions row SC-12 names the mechanism (`INSERT OR IGNORE`).

One consequence to record, which is not a spec gap: by SQLite's documentation of the conflict clause, `OR IGNORE` skips a row on any `UNIQUE`, `NOT NULL`, `CHECK` or `PRIMARY KEY` violation, not only on a duplicated key. The projection tables have no `CHECK`, and the payload models make every inserted value non-null, so no other row is skipped in practice. Derived by reading; nothing was run.

## Open questions
Both answered by the human on 2026-10-10, as proposed; the advisor agreed with both.

1. **How the rewritten recorder test makes the projector fail.** Answer: a trigger. After the first recorder closes, the test creates and commits a `BEFORE INSERT ON requirements` trigger with `SELECT RAISE(ABORT, ...)` on the temporary database, then appends a plain `sv_02` import behind the recorder's back. The failure comes from SQLite during the projector's write, and the name and the five assertions of the test stay as they are.
   - Verified on 2026-10-10 in an in-memory database with the project's Python (SQLite 3.54.0): under `INSERT OR IGNORE` through `executemany` the first row of a duplicated key is kept, the trigger's `RAISE(ABORT)` is not swallowed by `OR IGNORE`, and Python raises it as `sqlite3.IntegrityError` (`SQLITE_CONSTRAINT_TRIGGER`).
   - The trigger must be committed before the recorder opens; otherwise the open waits on the lock and fails with `sqlite3.OperationalError`.
   - Fallback, only if the trigger misbehaves in the real test: `monkeypatch` `SqliteProjector.apply` to raise `sqlite3.IntegrityError` for that event. Rejected: deleting the test, since the branch stays in the code under ADR-010.
2. **AC5 in this task, or in outline item 2.** Answer: AC5 stays here. It is the only criterion that shows the failure SC-12 was written for is gone, it is one test file section, and it prints nothing. If it fails for a reason outside the projector, the task stops and asks.

## Outcome
- Built: in `src/openfactory/adapters/sqlite_projector.py` `_apply_imported`, the requirements and ADRs inserts are `INSERT OR IGNORE`, with a comment naming the spec rule (keep the first of two items with one id, in the payload's order). New `tests/integration/test_duplicate_ids.py` (8 tests, AC1 to AC5). AC5 passed with no change outside the projector.
- Fixed-test edit (approved by the human, decisions row SC-12): `test_ac5_stored_event_the_projector_cannot_write_fails_the_open_naming_seq_and_model` in `tests/integration/test_sqlite_recorder.py`. Setup only: the duplicated-id import was replaced by a committed `BEFORE INSERT ON requirements` trigger with `RAISE(ABORT)` and a plain `sv_02` import. Its name and five assertions are unchanged. The trigger worked, so the monkeypatch fallback was not used.
- Checks: 552 tests pass; ruff, pyright and check_docs clean. With the projector change set aside, the 8 new tests fail with `sqlite3.IntegrityError` at the projector's insert and the 18 recorder tests pass; run again after the review, on 2026-10-10.
- Deviations: none in behaviour. The new test file is 329 lines, above the "well under 300 lines" estimate for the task.
- Follow-ups: one "Later" line in `docs/progress.md` for the `OR IGNORE` consequence under "Spec gaps" (reviewer note).
