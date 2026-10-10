# Architecture

## Layers
domain → ports ← adapters; app uses domain + ports.

## Components
<!-- one short section per component as it is built -->

### Domain events
`src/openfactory/domain/events.py`. Pure Pydantic v2 models, no I/O.
- `EventType`: the closed set of 11 Phase 1 event type names.
- `Event`: a new event with no `seq`; its fields cannot be reassigned and unknown fields are rejected. Fields mirror the `events` table columns: `event_id` (any UUID; required), `stream` (non-empty), `type`, `payload` (a JSON object; `NaN`, `Infinity`, strings that are not valid Unicode and integers too large to read back are rejected), `actor` (`human`, `orchestrator` or `agent:<role>`), `causation_id` (optional), `created_at` (an aware datetime or ISO 8601 string, normalised to UTC; naive datetimes and numeric timestamps are rejected).
- `Event.new(...)`: builds a new event with a generated UUID4 `event_id` and the current UTC time as `created_at`.
- `StoredEvent`: an `Event` plus the required `seq` assigned by the store, a strict integer of at least 1.

### EventStore port
`src/openfactory/ports/event_store.py`. The append-only event log interface.
- `EventStore` (Protocol): two methods. `append(event: Event) -> StoredEvent` assigns a `seq` and stores the event; if its `event_id` is already stored with identical content, it returns the original row; if content differs, it raises `EventConflictError`. `read(stream: str | None = None) -> list[StoredEvent]` returns stored events in ascending `seq`, optionally filtered by stream.
- `EventConflictError`: raised when an `event_id` is appended with different content than what is already stored.

### SQLite event store
`src/openfactory/adapters/sqlite_store.py`. Implements `EventStore` over SQLite. Its SQL for the `events` table comes from `sqlite_events`.
- `SqliteEventStore(path)`: opens the database file (creating it if it does not exist), creates the `events` table if missing using the spec's DDL, and sets WAL mode.
- Idempotency enforced by `event_id UNIQUE NOT NULL` constraint and `INSERT ... ON CONFLICT(event_id) DO NOTHING`.
- Rows read back are validated as `StoredEvent` before they are returned; `close()` releases the connection.

### Spec models
`src/openfactory/domain/models.py`. Pure Pydantic v2 models for a spec set, no I/O.
- `AcceptanceCriterion`: `id` and `text`.
- `Requirement`: `id`, `title`, `statement`, `priority`, `constrained_by` (list of ADR ids), `components`, `acceptance_criteria` (list of `AcceptanceCriterion`), and `deprecated` (boolean, optional, defaults to `false`); `constrained_by`, `components` and `acceptance_criteria` default to empty lists.
- `Adr`: `id`, `status` (closed set: `proposed`, `accepted`, `superseded`), and `body` (string, optional, defaults to empty string).
- `Priority`: closed set (`must`, `should`, `could`), enforced by enum.
- `SpecSet`: `components` (list of strings), `requirements` (list of `Requirement`), and `adrs` (list of `Adr`).
- All models are frozen. `AcceptanceCriterion`, `Requirement` and `SpecSet` reject unknown fields; `Adr` ignores them, since ADR front matter normally has more than `id` and `status`.

### Spec validation
`src/openfactory/domain/spec_validation.py`. Pure function that validates a spec set against deterministic rules.
- `Rule` enum: `id-format`, `id-unique`, `missing-acceptance-criteria`, `constrained-by`, `undeclared-component`, `schema`. `schema` is reported by the spec loader; `validate_spec` never returns it.
- `SpecViolation`: `rule` (a `Rule`), `subject` (the id the violation concerns), and `message`.
- `validate_spec(spec: SpecSet) -> list[SpecViolation]`: applies the first four deterministic validation rules from the spec (the fifth, on deleted requirements, is enforced from M2 and not implemented) and returns every violation in a fixed rule order, collecting all violations in one run.

### Spec hashing
`src/openfactory/domain/spec_hash.py`. Pure functions that compute canonical JSON and SHA-256 hashes of spec items.
- `canonical_json(item: SpecItem) -> bytes`: the model dumped in JSON mode with sorted keys, separators `,` and `:` with no spaces, non-ASCII characters left as they are, and encoded as UTF-8.
- `content_hash(item: SpecItem) -> str`: the SHA-256 of the canonical JSON, written as 64 lowercase hex characters.
- `SpecItem`: `AcceptanceCriterion`, `Requirement`, `Adr`, or `SpecSet`.
- Before hashing, lists are sorted innermost first; items with an `id` sort by `(id, canonical JSON of the item)`, and every list of strings is sorted by value, including each requirement's `components` and `constrained_by`. Omitted optional fields hash the same as their defaults.

### Event payloads
`src/openfactory/domain/payloads.py`. Pure Pydantic v2 models for the payloads of the three M1 spec events, no I/O. Its only first-party imports are from `openfactory.domain`.
- `SpecImportedPayload`: `spec_version`, `hash` and `spec` (a `SpecSet`).
- `SpecValidatedPayload`: `spec_version`, `hash`, `violations` (list of `RecordedViolation`) and `warnings` (list of `SpecWarning`).
- `SpecApprovedPayload`: `spec_version` and `hash`.
- `RecordedViolation`: `rule`, `subject` and `message`, all strings. `rule` is a plain `str`, not the `Rule` enum, so a stored event stays valid if a rule is later renamed or removed. `SpecWarning`: `check`, `subject` and `message`, all strings.
- `SpecVersionId` is a string matching `^sv_\d{2,}$`; `ContentHash` is a string of 64 lowercase hex characters. Only the form of `hash` is checked; it is not compared with `spec`.
- All fields are required. The models are frozen and reject unknown fields. The `SpecImportedPayload` model does not reorder `spec`.
- `PAYLOAD_MODELS: dict[EventType, type[BaseModel]]` maps `SpecImported`, `SpecValidated` and `SpecApproved` to these models. The other event types have no entry yet.

### SpecFiles port
`src/openfactory/ports/spec_files.py`. The read-only interface to the spec files. It returns plain text and does no parsing. It imports nothing from `adapters` or `app`.
- `SpecFiles` (Protocol): two methods. `read(path: str) -> str | None` returns the text of the file at `path`, a POSIX-style path relative to `specs/` (`requirements.yaml`, `policies.yaml`, `adrs/<name>.md`), or `None` if the file does not exist, so a missing file can be told from an empty one. `list_adrs() -> list[str]` returns the paths relative to `specs/` of the `*.md` files directly in `adrs/`, in ascending order, or an empty list if there are none.

### Filesystem spec files
`src/openfactory/adapters/filesystem_spec_files.py`. Implements `SpecFiles` over a directory.
- `FilesystemSpecFiles(specs_dir: Path)`: takes the `specs/` directory itself.
- `read` opens the file with `encoding="utf-8"` and `newline=""`, so the text does not depend on the platform's default encoding and line endings are returned as they are on disk (normalising an ADR body to `\n` is left to the loader).
- `list_adrs` returns sorted `adrs/<name>` for every `*.md` file directly in `adrs/`, whatever its name; sub-directories are not searched. It returns `[]` if `adrs/` is missing or empty.

### Spec loader
`src/openfactory/app/spec_loader.py`. Application-layer function that loads the spec files into a `SpecSet`. It reads only through the `SpecFiles` port and imports nothing from `adapters`.
- `load_spec(files: SpecFiles) -> SpecLoadResult`: reads `requirements.yaml` and every file `list_adrs` returns, and collects every problem in one run.
- `SpecLoadResult`: a frozen model with `spec` (a `SpecSet` or `None`) and `violations` (a list of `SpecViolation`). It holds either the spec set or violations, never both. Requirements keep file order and ADRs follow `list_adrs` order. `load_spec` does not read `policies.yaml`.
- YAML is parsed with `yaml.load` and a `SafeLoader` subclass that rejects a mapping with the same key twice. An ADR file is split at its first two `---` lines into front matter and body; line endings are normalised to `\n` in the body, which is not trimmed, and a `body` key in the front matter is ignored.
- Every problem is a `SpecViolation` with rule `schema`: a missing file, a file that is not valid UTF-8, a YAML syntax error or duplicate key, an ADR file without front matter, front matter or a top level that is not a mapping, and a value the models reject. A top-level `adrs` key in `requirements.yaml` is rejected as an unknown field. Each requirement and each ADR is validated on its own, and there is one violation per Pydantic error, with the field path in the message.
- The subject is the nearest enclosing item with a readable string `id` (acceptance criterion, then requirement or ADR); otherwise it is the file path relative to the repo, which is the port's path prefixed with `specs/`.

### Policy model
`src/openfactory/domain/policy.py`. Pure Pydantic v2 model of `specs/policies.yaml` and the baseline forbidden paths, no I/O. It imports nothing from `adapters`, `app` or `ports`.
- `Policy`: `protected_branches` (list of strings, default `["main", "master"]`), `forbidden_paths` (list of strings, default `[]`), `max_attempts` (integer, default 2), `max_runtime_s` (integer, default 1200) and `max_cost_usd` (float, default 1.50). The three limits must be greater than zero. The model is frozen and rejects unknown fields. Entries in the lists are plain strings; their glob syntax is not checked.
- `BASELINE_FORBIDDEN_PATHS`: the tuple `("specs/**", ".openfactory/**", ".env", ".env.*")`. It is not a field of `Policy` and cannot be set from the policy file. `Policy.forbidden_paths` holds only the file's list; nothing is merged in the model.

### Policy loader
`src/openfactory/app/spec_loader.py`, next to the spec loader and using its read, YAML and violation helpers.
- `load_policy(files: SpecFiles) -> PolicyLoadResult`: reads only `policies.yaml` through the `SpecFiles` port.
- `PolicyLoadResult`: a frozen model with `policy` (a `Policy` or `None`) and `violations` (a list of `SpecViolation`); it holds either the policy or violations, never both.
- An empty or comment-only file is a valid policy with all defaults. Every problem is a `schema` violation with subject `specs/policies.yaml`: a missing file ("missing; run openfactory init"), a file that is not valid UTF-8, a YAML syntax error or duplicate key, a top level that is not a mapping, and a value or unknown key the model rejects (one violation per Pydantic error).

### SQLite projector
`src/openfactory/adapters/sqlite_projector.py`. Builds the M1 projection tables from stored events. It imports only from `openfactory.domain` and the standard library. It has no port and no `TYPE_CHECKING` conformance assertion (ADR-009; ADR-001 rejected a projector port).
- `SqliteProjector(conn)`: takes an open `sqlite3.Connection`. It never commits or rolls back; the caller owns the transaction.
- `create_tables()`: creates `spec_versions`, `requirements` and `adrs` with the spec's DDL if missing (no foreign key, no `CHECK`).
- `apply(event: StoredEvent)`: validates the payload against its model in `PAYLOAD_MODELS` before any write, and raises `pydantic.ValidationError` on a mismatch. `SpecImported` writes the draft version row and its requirement and ADR rows, replacing the content of an existing draft with the same id; item hashes come from `content_hash`. When the payload holds two requirements, or two ADRs, with one id, the first in the payload's order is kept and the others are skipped (`INSERT OR IGNORE`; spec v1.9), so such a version imports and gets its `id-unique` violation. `SpecApproved` sets `status` to `approved` and `approved_at` from the event's `created_at`. `SpecValidated` is validated and writes nothing. Event types with no entry in `PAYLOAD_MODELS` are ignored.
- `rebuild(events)`: drops the three tables, recreates them and applies the given events in `seq` order. The caller passes the events (for example `EventStore.read()`).
- It does not check event sequences, a payload's `hash` against its `spec`, or the last applied `seq`.

### EventRecorder port
`src/openfactory/ports/event_recorder.py`. The one call a use case makes to record an event (ADR-001). It imports from `openfactory.domain` only.
- `EventRecorder` (Protocol): one method, `record(event: Event) -> StoredEvent`. The event is stored and applied to the projections as one unit. A repeated `event_id` behaves like `EventStore.append`: the same content returns the stored event without applying it again, and different content raises `EventConflictError` (from `ports/event_store.py`).

### SQLite events helpers
`src/openfactory/adapters/sqlite_events.py`. The SQL and row helpers for the `events` table, shared by `sqlite_store` and `sqlite_recorder` so that no SQL for the table is written twice. It has no port and no `TYPE_CHECKING` conformance assertion (ADR-010). None of its functions commits; the caller owns the transaction.
- `create_events_table(conn)`: creates the `events` table with the spec's DDL if it is missing.
- `insert_event(conn, event) -> bool`: `INSERT ... ON CONFLICT(event_id) DO NOTHING`; returns whether a row was written.
- `stored_event(conn, event) -> StoredEvent`: reads the stored row for the event's `event_id` and raises `EventConflictError` if its content, compared as canonical JSON of the envelope, differs from the event's.
- `select_events(conn, *, stream=None, after_seq=0) -> list[StoredEvent]`: stored events with a `seq` above `after_seq`, optionally of one stream, in ascending `seq`.

### SQLite recorder
`src/openfactory/adapters/sqlite_recorder.py`. Implements `EventRecorder` over SQLite (ADR-010). It imports nothing from `openfactory.app`.
- `SqliteEventRecorder(path)`: opens its own connection, sets WAL mode and `PRAGMA busy_timeout = 5000`, then, in one transaction, creates what is missing (the `events` table, the spec projections, and `projection_state` with its single row `id = 1`, `last_seq = 0`) and catches up.
- Catch-up: every stored event with `seq > last_seq` is applied in `seq` order and `last_seq` is set. It runs only when the recorder opens. A stored payload its model rejects raises `pydantic.ValidationError` whose title is `stored event seq N (<model>)`; a stored event the projector cannot write raises `sqlite3.IntegrityError` whose message starts the same way (no M1 event reaches this case since spec v1.9: a duplicated requirement or ADR id is skipped by the projector, not an error). In both cases the transaction is rolled back, nothing is applied, and the connection is closed.
- `record(event)`: inserts the event, and if it is new applies it with `SqliteProjector` and sets `last_seq` to its `seq`, all in one transaction. Any error rolls the transaction back, so a rejected payload leaves no stored event. A repeated `event_id` applies nothing.
- `rebuild()`: not on the port. In one transaction it reads every stored event, calls `SqliteProjector.rebuild` and sets `last_seq` to the highest `seq` (0 for an empty log); a failure rolls everything back. `projection_state` is updated in place, never dropped.
- `close()` releases the connection.
- Every transaction starts with `BEGIN IMMEDIATE`. `projection_state` is bookkeeping, not a projection; the recorder is its only writer.

### Spec version reference
`src/openfactory/domain/spec_versions.py`. Pure Pydantic v2 model, no I/O. It imports nothing from `adapters`, `app` or `ports`.
- `SpecVersionRef`: `id` (`SpecVersionId`) and `hash` (`ContentHash`), both from `payloads.py`. The model is frozen and rejects unknown fields.

### SpecVersions port
`src/openfactory/ports/spec_versions.py`. The read-only interface to the `spec_versions` projection (ADR-001). It imports from `openfactory.domain` only.
- `SpecVersions` (Protocol): three methods. `latest_approved() -> SpecVersionRef | None` and `current_draft() -> SpecVersionRef | None` return `None` when there is no such version. `next_id() -> str` returns the highest number in any row's id plus one, written with at least two digits (`sv_01` when there is no row), also while a draft exists.

### SQLite spec versions
`src/openfactory/adapters/sqlite_spec_versions.py`. Implements `SpecVersions` over SQLite (ADR-001, ADR-010). It imports nothing from `openfactory.app`.
- `SqliteSpecVersions(path)`: opens its own connection and sets `PRAGMA busy_timeout = 5000`. It runs only `SELECT` on `spec_versions`, creates no table and writes nothing; a database without the `spec_versions` table raises `sqlite3.OperationalError`, which is not handled.
- Every call runs its query again and nothing is cached, so it sees what a recorder on another connection has committed. "Latest approved" is the approved row with the highest id number; ids are compared as integers with `CAST(substr(id, 4) AS INTEGER)`.
- `close()` releases the connection.

### Validate use case
`src/openfactory/app/validate.py`. Application-layer use case that loads and hashes the spec set, imports it if it changed and runs the rules. It imports only from `openfactory.domain`, `openfactory.ports` and `app/spec_loader.py`, nothing from `adapters`. It returns data and prints nothing.
- `validate(files: SpecFiles, versions: SpecVersions, recorder: EventRecorder) -> ValidateResult`.
- `ValidateResult`: a frozen model with `outcome` (`unloadable`, `matches_approved` or `validated`), `spec_version` (`None` when unloadable), `violations`, `policy_problems`, `hash` and `validated_event_id` (the last two are set only when a `SpecValidated` was recorded).
- `unloadable`: `load_spec` returned `schema` violations. They are the result's `violations`; no version is read and no event is recorded.
- `matches_approved`: the files' `content_hash` equals the latest approved version's. No event is recorded, the rules are not run, `violations` is empty, and a draft is left as it is.
- `validated`: otherwise. The version id is the current draft's, or `next_id()` when there is no draft. Unless the hash equals the draft's, it records `SpecImported` with `spec` in canonical order, then runs `validate_spec` and records `SpecValidated` with the violations as `RecordedViolation` in the order returned and empty `warnings`. `violations` holds the rule results.
- Both events are built through the payload models, on stream `spec:<version>` with actor `orchestrator`. `SpecImported` has no `causation_id`; `SpecValidated` carries the `SpecImported` event id when one was recorded in the same call.
- `load_policy` runs in every case; its violations are returned as `policy_problems` and never recorded.
- Events are recorded only through `EventRecorder.record`; the spec versions are read only through `SpecVersions`. If the recorder raises, the error propagates.

### Approve spec use case
`src/openfactory/app/approve_spec.py`. Application-layer use case that runs the validate use case and then records `SpecApproved` or reports why it did not. It imports only from `openfactory.domain`, `openfactory.ports` and `app/validate.py`, nothing from `adapters`. It returns data and prints nothing.
- `approve_spec(files: SpecFiles, versions: SpecVersions, recorder: EventRecorder) -> ApproveResult`. It calls `validate` itself and does not rely on an earlier run.
- `ApproveResult`: a frozen model with `outcome` (`ApproveOutcome`: `unloadable`, `nothing_to_approve`, `refused` or `approved`), `spec_version` (the version approved or refused, the latest approved id for `nothing_to_approve`, `None` when unloadable), `violations` and `policy_problems`. It carries no hash and no `SpecApproved` event id.
- `unloadable` and `nothing_to_approve` follow `validate`'s `unloadable` and `matches_approved`; nothing more is recorded. `refused`: `validate` found violations; `SpecApproved` is not recorded.
- `approved`: the files loaded, differ from the latest approved version and have no violations. It records `SpecApproved` through `SpecApprovedPayload` on stream `spec:<version>` with actor `human` and `causation_id` set to the `SpecValidated` event id.
- Policy problems are returned in every case and never block the approval. If the recorder raises, the error propagates.

### CLI
`src/openfactory/cli.py`. The Typer app `app` and the composition root (ADR-011): the one module that may import adapters and use cases and wire them. It sits outside the four layers, and no module under `domain/`, `ports/`, `adapters/` or `app/` imports it. It implements no port. `[project.scripts]` points `openfactory` at `openfactory.cli:app`.
- `init <repo>`: exits 1 with `not a git repository: <repo>` on standard error when `<repo>` has no `.git` entry (a directory or a file); the check runs before anything is created. Otherwise it creates, if missing and in this order, `.openfactory/openfactory.db` (by opening and closing `SqliteEventRecorder`; when the file exists the recorder is not opened), `.openfactory/.gitignore` containing `*`, and `specs/policies.yaml` from the spec's code block, never overwriting a file. It prints `created <path>` or `exists <path>` per item, relative to `<repo>`, and records no events.
- `require_init() -> Path`: the check later commands call first. It returns `Path(".openfactory/openfactory.db")` when `./.openfactory/` is a directory, and otherwise writes "run `openfactory init` first" to standard error and raises `typer.Exit(1)`. It does not search parent directories and does not check that the database file exists. No command calls it yet.

## Data flow
<!-- updated when a milestone changes it -->
Events are stored in the SQLite `events` table, which assigns `seq`. There are two write paths, `EventRecorder.record` and `EventStore.append`; use cases are meant to use only the first (ADR-001). Stored events are read back in `seq` order for replay by later tasks. Specs are validated by the `validate_spec` function, which returns every violation found.

Use cases build the payload of a spec event through the models in `payloads.py`. The validate use case (`app/validate.py`) does so for `SpecImported` and `SpecValidated`, converting each `SpecViolation` to a `RecordedViolation`. The approve-spec use case (`app/approve_spec.py`) builds `SpecApproved` through `SpecApprovedPayload`.

`SqliteProjector` validates each stored payload against `PAYLOAD_MODELS` and writes the `spec_versions`, `requirements` and `adrs` projections, one event at a time or by a rebuild from the event log. Its only caller is `SqliteEventRecorder`, which appends an event, applies it and sets `projection_state.last_seq` in one transaction, applies unapplied events when it opens a database, and rebuilds the projections in one transaction. The validate use case calls the recorder through the `EventRecorder` port; the approve-spec use case records `SpecApproved` the same way, and nothing yet wires `SqliteEventRecorder` to either use case. Use cases must write through the recorder only; an event appended through `EventStore.append` while a recorder is open is not applied by that recorder (ADR-010).

Spec file text reaches the application layer through the `SpecFiles` port, not by reading the filesystem directly; `FilesystemSpecFiles` is the adapter. `load_spec` parses the YAML and ADR front matter from that text and returns either a `SpecSet` or the `schema` violations. It does not run `validate_spec`; the validate use case runs the content rules only when the load produced a spec set. `validate` calls `load_spec`. `load_policy` reads `policies.yaml` the same way and returns either a `Policy` or the `schema` violations; it is separate from `load_spec`, and the policy is not part of the spec set or its hash. `validate` calls `load_policy` in every case and returns its violations as policy problems.

Use cases read the spec version projections only through the `SpecVersions` port, to compare hashes and choose the spec version id; `SqliteSpecVersions` is the adapter and reads `spec_versions` on its own connection. The validate use case calls the port, and the approve-spec use case reaches it through `validate`. The CLI (`cli.py`) has only `init` so far, which uses `SqliteEventRecorder` to create the database; the use cases are not yet wired to any command.
