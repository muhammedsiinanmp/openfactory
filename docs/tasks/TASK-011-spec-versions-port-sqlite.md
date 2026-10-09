# TASK-011: SpecVersions port and SQLite adapter

- Milestone: M1
- Status: done
- Tests: acceptance
- ADR: ADR-001, accepted (the `SpecVersions` port and its adapter `sqlite_spec_versions`; it leaves "exact signatures and adapter module names" to this task). The adapter opens its own connection, as ADR-010 (accepted) decided for SQLite adapters. The signatures and the other choices under Interpretations go to `docs/decisions.md`; no new ADR is proposed (see Open questions, item 6).
- Spec sections (spec v1.7): "Domain model and storage" ("Ids", "Projections", "Projection rules"); "Spec input format" ("Spec versions"); "Tech stack and repo layout"

## Objective
Add the read-only `SpecVersions` port and its SQLite adapter, which give the latest approved spec version, the current draft and the next spec version id from the `spec_versions` projection, so the `validate` and `approve spec` use cases can compare hashes and choose `sv_NN` without touching SQLite.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Acceptance criteria trace to spec headings instead.

## Scope
In:
- A new pure domain module `domain/spec_versions.py`: the frozen model `SpecVersionRef` with `id` (`SpecVersionId`) and `hash` (`ContentHash`), unknown fields rejected. Both types are reused from `domain/payloads.py`.
- A new port module `ports/spec_versions.py`: the Protocol `SpecVersions` with three methods, `latest_approved() -> SpecVersionRef | None`, `current_draft() -> SpecVersionRef | None` and `next_id() -> str`.
- A new adapter module `adapters/sqlite_spec_versions.py` (the module name is the spec's): the class `SqliteSpecVersions(path: str | Path)` with the three methods and `close()`, ending with the `TYPE_CHECKING` assertion against `SpecVersions`.
- The adapter opens its own connection (ADR-010), sets `PRAGMA busy_timeout = 5000`, and runs only `SELECT` statements on `spec_versions`. It creates no table and writes nothing. Each call runs its query again; nothing is cached.
- "Latest approved" is the approved row with the highest number in its id; the next id is the highest number in any row's id plus one, written with two digits and wider when needed, and `sv_01` when there is no row.
- A unit test for the port and the model, and integration tests on a SQLite file under pytest's `tmp_path` whose rows are produced only by recording events through `SqliteEventRecorder`.

Out (follow-up tasks, not this one):
- The `validate` and `approve spec` use cases, and any in-memory fake `SpecVersions` for their tests (M1 outline items 2 and 3).
- CLI commands `init`, `validate`, `approve spec`, `events` (outline items 4 to 6), and which adapter a command opens first.
- Reading the requirements, ADRs or components of a spec version. No M1 use case needs them; the M2 read ports are decided when M2 is planned (ADR-001).
- The deleted-requirement rule (enforced from M2).
- A database file that no recorder has opened (no `spec_versions` table): the adapter does not create the table and does not turn the `sqlite3` error into anything else (see Open questions, item 4).
- Inconsistent projections that the use cases cannot produce: two draft rows, or an id that does not match `sv_NN`. Not checked, as in the projector (decision of 2026-10-09, TASK-009).
- Any change to `SqliteProjector`, `SqliteEventRecorder`, `SqliteEventStore`, `sqlite_events`, the existing ports, or the existing domain modules.
- Payload depth limit and the other items under Later.

## Acceptance criteria
Each criterion cites the spec v1.7 text it traces to. "Spec versions" is the block of that name under "Spec input format"; "Ids" and "Projection rules" are under "Domain model and storage". In AC2 to AC6 the database is a SQLite file under `tmp_path` opened first by `SqliteEventRecorder`, every row is produced by recording `SpecImported` and `SpecApproved` events through it, and "the adapter" is `SqliteSpecVersions` opened on the same file. The criteria are written for the proposals under Interpretations, which the human approved.

- [x] AC1 ("Tech stack and repo layout": "`ports/ # interfaces: EventStore, EventRecorder, SpecVersions, ...`", "`adapters/ # ..., sqlite_spec_versions, ...`" and "`domain/ # pure models, state machine, rules; no I/O`"; Ids: "the `SpecVersions` port, a read-only port that gives the latest approved version, the current draft and the next spec version id"):
  - `openfactory.ports.spec_versions` defines a Protocol `SpecVersions` whose only public methods are `latest_approved`, `current_draft` and `next_id`, and imports nothing from `openfactory.adapters` or `openfactory.app` (checked by parsing its imports with `ast`).
  - `SpecVersionRef`, imported from `openfactory.domain.spec_versions`, is built from an `id` and a `hash`, is frozen, and rejects an unknown field, an `id` of `v1` and a `hash` that is not 64 lowercase hex characters. Its module imports nothing from `openfactory.adapters`, `openfactory.app` or `openfactory.ports`.
  - `openfactory.adapters.sqlite_spec_versions` imports nothing from `openfactory.app`.
- [x] AC2 (Spec versions: "A spec version has an id of the form `sv_NN` (two digits, counted from `sv_01`, wider when needed)"; "if there is no draft, the next id is used"): on a database with no recorded event, `latest_approved()` and `current_draft()` return `None` and `next_id()` returns `sv_01`.
- [x] AC3 (Spec versions: "is either `draft` or `approved`. At most one draft exists at a time"; "If the hash equals the current draft's, nothing is imported"; "An existing draft keeps its id and its content is replaced"):
  - After a `SpecImported` for `sv_01`, `current_draft()` returns a `SpecVersionRef` with `id` `sv_01` and the payload's `hash`, `latest_approved()` returns `None`, and `next_id()` returns `sv_02`.
  - After a second `SpecImported` for `sv_01` with a different `hash`, `current_draft()` returns `sv_01` with the second hash and `next_id()` is still `sv_02`.
- [x] AC4 (Spec versions: "If the hash equals the latest approved version's, nothing is imported"; "it records `SpecApproved`, and the version is immutable from then on. Edits after that create a new draft version"; "Because a draft keeps its id until it is approved, approved versions are numbered without gaps"):
  - After `sv_01` is imported and approved, `latest_approved()` returns `sv_01` with its hash, `current_draft()` returns `None`, and `next_id()` returns `sv_02`.
  - After a `SpecImported` for `sv_02`, `current_draft()` returns `sv_02` with its hash, `latest_approved()` still returns `sv_01`, and `next_id()` returns `sv_03`.
  - After `sv_02` is approved, `latest_approved()` returns `sv_02` with its hash and `current_draft()` returns `None`.
- [x] AC5 (Spec versions: "two digits, counted from `sv_01`, wider when needed"; Ids: "spec version ids (`sv_NN`) ... are chosen by the use case from the projections when a command runs"):
  - With `sv_01` to `sv_09` imported and approved in order, `next_id()` returns `sv_10`.
  - With `sv_01` to `sv_100` imported and approved in order, `latest_approved()` returns `sv_100` and `next_id()` returns `sv_101`.
- [x] AC6 (Ids: "a read-only port"; Projection rules: "Projection tables are never written in any other way" and "`projection_state` ... The event recorder creates it and is its only writer"):
  - The adapter is opened while the recorder is still open and the database holds no event. Events recorded afterwards (import `sv_01`, then approve it) are seen by the same adapter object: `current_draft()` returns `sv_01` after the first, and `latest_approved()` returns `sv_01` after the second.
  - Opening the adapter, calling the three methods and closing it changes no row: the rows of `events`, `spec_versions`, `requirements`, `adrs` and `projection_state`, read by the test on its own connection, are equal before and after.

## Interpretations
The spec names the port and what it gives, and ADR-001 leaves the signatures to this task. The human approved all of these on 2026-10-09; they are recorded in `docs/decisions.md`.

1. Signatures and return type. The port has `latest_approved() -> SpecVersionRef | None`, `current_draft() -> SpecVersionRef | None` and `next_id() -> str`. `SpecVersionRef` holds `id` and `hash` only, which is all that `validate` and `approve spec` compare. It lives in a new module `domain/spec_versions.py`, because ports import from the domain only and `domain/models.py` cannot import the `SpecVersionId` and `ContentHash` types from `payloads.py` without a cycle. Alternative: a model that also carries `status`, `components` and `approved_at`.
2. "Latest approved" is the approved row with the highest number in its id, compared as an integer. Approved versions are numbered in order without gaps, so this is also the most recently approved one. Alternative: order by `approved_at`.
3. `next_id()` is the highest number in any row's id, draft or approved, plus one, formatted with at least two digits; `sv_01` on an empty table. While a draft exists the use case keeps the draft's id and does not call it, so the value in that state (`sv_02` while `sv_01` is a draft) is defined but unused. Alternative: return the draft's own id while a draft exists, so one call always gives "the id to import under".
4. Connection. `SqliteSpecVersions(path)` opens its own connection and sets `busy_timeout` to 5000 ms, like the recorder (ADR-010). It does not set the journal mode, which is stored in the file by the recorder, and it creates nothing. It is a plain connection, not a `mode=ro` URI.
5. Freshness. Every method runs its query when called and holds no transaction open between calls, so it sees what a recorder on another connection has committed.

Kept as already decided: use cases read the spec version projections only through this port (ADR-001); two adapters on one database file share the file, not a connection object (ADR-010); the projector does not check event sequences, so neither does this adapter (decision of 2026-10-09, TASK-009); `spec_version` ids match `^sv_\d{2,}$` (decision of 2026-10-08, TASK-005).

## Architecture rules that apply
- `src/openfactory/domain` stays pure: `domain/spec_versions.py` is one Pydantic model, with no I/O and no import from `app`, `ports` or `adapters`.
- `src/openfactory/ports` holds Protocols only: `ports/spec_versions.py` defines `SpecVersions` and imports from `openfactory.domain` only.
- Adapters implement ports and end with the `TYPE_CHECKING` assertion: `adapters/sqlite_spec_versions.py` ends with `if TYPE_CHECKING: _: type[SpecVersions] = SqliteSpecVersions`.
- "All state changes go through the events table. Never write projections directly": the adapter only reads. Tests fill the tables by recording events through `SqliteEventRecorder`, never by inserting rows.
- `src/openfactory/app` is not changed; no use case exists yet.
- No LLM call is made.

## Plan
1. Create branch `task/TASK-011-spec-versions-port-sqlite` from an up-to-date main and commit this record.
2. Get the human's answers to the Open questions and Interpretations 1 to 5; record them here and in `docs/decisions.md`. Adjust AC3 and AC5 if items 2 or 3 are answered with the alternative.
3. Write failing tests:
   - `tests/unit/test_spec_versions_port.py` for AC1, following `tests/unit/test_event_recorder_port.py`.
   - `tests/integration/test_sqlite_spec_versions.py`, one or more tests per criterion AC2 to AC6, with helpers that build `SpecImported` and `SpecApproved` events through the payload models and record them through `SqliteEventRecorder`.
4. Add `src/openfactory/domain/spec_versions.py` with `SpecVersionRef`.
5. Add `src/openfactory/ports/spec_versions.py` with the `SpecVersions` Protocol.
6. Add `src/openfactory/adapters/sqlite_spec_versions.py`: open, the three queries (the number is taken from the id with `CAST(substr(id, 4) AS INTEGER)`), `close`, and the conformance assertion.
7. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
8. Update living docs and this record's Outcome; commit with trailers `Task: TASK-011` and `Milestone: M1`.

## Files expected to change
- `src/openfactory/domain/spec_versions.py` (new)
- `src/openfactory/ports/spec_versions.py` (new)
- `src/openfactory/adapters/sqlite_spec_versions.py` (new)
- `tests/unit/test_spec_versions_port.py` (new)
- `tests/integration/test_sqlite_spec_versions.py` (new)
- `docs/architecture.md` (Components: add "Spec version reference", "SpecVersions port" and "SQLite spec versions"; Data flow: say the port and adapter exist and that no use case calls them yet)
- `docs/progress.md` (Current task, then Done; remove item 1 from the M1 outline and renumber the references to it)
- `docs/decisions.md` (rows for the confirmed interpretations)
- `docs/tasks/TASK-011-spec-versions-port-sqlite.md` (this record; Outcome at close)

Not expected to change: `src/openfactory/domain/models.py`, `src/openfactory/domain/payloads.py`, every existing module under `src/openfactory/ports/` and `src/openfactory/adapters/`, everything under `src/openfactory/app/`, `pyproject.toml`, and every existing test file.

## Living docs to update
- `docs/architecture.md`: Components and Data flow.
- `docs/progress.md`: Current, M1 outline and Done.
- `docs/decisions.md`: the confirmed interpretations.
- `CHANGELOG.md`: no entry expected (no user-visible change).
- `README.md`: no change expected.

## New dependencies
None. `sqlite3` is in the standard library; Pydantic v2 is already declared.

## Open questions
None open. The human approved the plan on 2026-10-09 with the proposed answer to each question:

1. Signatures and return type: three methods, and a `SpecVersionRef` with `id` and `hash` only, in a new `domain/spec_versions.py`.
2. "Latest approved": the highest number in the id among approved rows, compared as an integer.
3. `next_id()` while a draft exists: the highest number of any row plus one.
4. A database without the `spec_versions` table: out of scope; the adapter creates no table and the `sqlite3.OperationalError` is left as it is.
5. Connection mode: a plain connection that only runs `SELECT`, with `busy_timeout` 5000 ms.
6. ADR: no new ADR; the answers above are rows in `docs/decisions.md`.

## Outcome
What was built:
- `src/openfactory/domain/spec_versions.py`: `SpecVersionRef`, a frozen model with `id` (`SpecVersionId`) and `hash` (`ContentHash`); unknown fields are rejected.
- `src/openfactory/ports/spec_versions.py`: the Protocol `SpecVersions` with `latest_approved()`, `current_draft()` and `next_id()`.
- `src/openfactory/adapters/sqlite_spec_versions.py`: `SqliteSpecVersions(path)` with its own connection (ADR-010), `busy_timeout` 5000 ms, `SELECT` only on `spec_versions`, no table created, no caching, ids compared by `CAST(substr(id, 4) AS INTEGER)`, `close()`, and the `TYPE_CHECKING` assertion against the port.
- `tests/unit/test_spec_versions_port.py` (AC1) and `tests/integration/test_sqlite_spec_versions.py` (AC2 to AC6), written by the test-writer.
- Six rows in `docs/decisions.md` and updates to `docs/architecture.md` and `docs/progress.md`. No new ADR (ADR-001 and ADR-010 cover the port, the adapter and the connection).

Deviations from plan: none.

Test edits: no test was edited after the test-writer wrote it.

Follow-ups:
- The `validate` and `approve spec` use cases are next in the M1 outline; they are the first callers of the port.
