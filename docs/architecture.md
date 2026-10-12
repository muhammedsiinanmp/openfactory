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
`src/openfactory/domain/spec_hash.py`. Pure functions that compute canonical JSON and SHA-256 hashes of spec items and of the policy.
- `canonical_json(item: SpecItem) -> bytes`: the model dumped in JSON mode with sorted keys, separators `,` and `:` with no spaces, non-ASCII characters left as they are, and encoded as UTF-8.
- `content_hash(item: SpecItem) -> str`: the SHA-256 of the canonical JSON, written as 64 lowercase hex characters.
- `SpecItem`: `AcceptanceCriterion`, `Requirement`, `Adr`, or `SpecSet`.
- Before hashing, lists are sorted innermost first; items with an `id` sort by `(id, canonical JSON of the item)`, and every list of strings is sorted by value, including each requirement's `components` and `constrained_by`. Omitted optional fields hash the same as their defaults.
- `policy_hash(policy: Policy) -> str`: the SHA-256 of the policy dumped in JSON mode and serialised with the same `_dumps`, as 64 lowercase hex characters. It does not sort lists: `forbidden_paths` and `protected_branches` are hashed in file order, because their order reaches the task contracts. It covers the five keys with defaults filled in, not the baseline paths.

### Event payloads
`src/openfactory/domain/payloads.py`. Pure Pydantic v2 models for the payloads of the three M1 spec events and the five M2 plan, task and agent run events, no I/O. Its only first-party imports are from `openfactory.domain`.
- `SpecImportedPayload`: `spec_version`, `hash` and `spec` (a `SpecSet`).
- `SpecValidatedPayload`: `spec_version`, `hash`, `violations` (list of `RecordedViolation`) and `warnings` (list of `SpecWarning`).
- `SpecApprovedPayload`: `spec_version` and `hash`.
- `RecordedViolation`: `rule`, `subject` and `message`, all strings. `rule` is a plain `str`, not the `Rule` enum, so a stored event stays valid if a rule is later renamed or removed. `SpecWarning`: `check`, `subject` and `message`, all strings.
- `SpecVersionId` is a string matching `^sv_\d{2,}$`; `ContentHash` is a string of 64 lowercase hex characters. Only the form of `hash` is checked; it is not compared with `spec`.
- `PlanCreatedPayload`: `plan_id` (`PlanId`), `spec_version`, `policy_hash` (`ContentHash`), `run_id` (`RunId`) and `tasks` (list of `TaskContract`, kept in the order given). `PlanApprovedPayload`: `plan_id`.
- `TaskStateChangedPayload`: `task_id` (`TaskId`), `from_`, `to` (both `TaskState`) and `reason` (`str | None`). `from_` has the alias `from`; the config sets `serialize_by_alias=True` and `validate_by_name=True`, so a plain `model_dump(mode="json")` writes `from` and `from_=` works at run time, though pyright rejects it in typed code (an input key `from_` also validates). A validator rejects a null `reason` when `to` is `invalidated`; a text `reason` with another `to` is allowed. `from` to `to` is not checked against `TRANSITIONS`.
- `AgentRunStartedPayload`: `run_id`, `task_id` (`TaskId | None`, null for a planner or classifier run), `role` (`RunRole`), `runtime` and `context_hash`. `AgentRunFinishedPayload`: `run_id`, `exit` (`RunExit`), `model`, `tokens_in`, `tokens_out`, `cost_usd` (all nullable), `duration_s` (float) and `error` (`str | None`). No link between `exit` and `error` is checked.
- `PlanId` matches `^plan_\d{2,}$`, `RunId` `^run_\d{4,}$` and `TaskId` `^[A-Z]+-\d{3}$` (repeating the pattern of `PlannedTask.task_id`). `RunRole` is a `Literal` of `planner`, `implementer`, `reviewer`, `classifier`; `RunExit` is a `Literal` of `ok`, `error`, `timeout`. The closed sets are widened only (ADR-007 amendment).
- All fields are required. The models are frozen and reject unknown fields. The `SpecImportedPayload` model does not reorder `spec`, and `PlanCreatedPayload` does not reorder `tasks`.
- `PAYLOAD_MODELS: dict[EventType, type[BaseModel]]` maps `SpecImported`, `SpecValidated`, `SpecApproved`, `PlanCreated`, `PlanApproved`, `TaskStateChanged`, `AgentRunStarted` and `AgentRunFinished` to these models (eight entries). `GateEvaluated`, `CommitRecorded` and `ImpactComputed` have no entry yet.

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
`src/openfactory/adapters/sqlite_projector.py`. Builds the projection tables from stored events: `spec_versions`, `requirements`, `adrs`, `plans`, `tasks`, `task_deps` and `agent_runs`. It imports only from `openfactory.domain` and the standard library. It has no port and no `TYPE_CHECKING` conformance assertion (ADR-009; ADR-001 rejected a projector port).
- `SqliteProjector(conn)`: takes an open `sqlite3.Connection`. It never commits or rolls back; the caller owns the transaction.
- `create_tables()`: creates the seven tables with the spec's DDL if missing (no foreign key, no `CHECK`).
- `apply(event: StoredEvent)`: validates the payload against its model in `PAYLOAD_MODELS` before any write, and raises `pydantic.ValidationError` on a mismatch. `SpecImported` writes the draft version row and its requirement and ADR rows, replacing the content of an existing draft with the same id; item hashes come from `content_hash`. When the payload holds two requirements, or two ADRs, with one id, the first in the payload's order is kept and the others are skipped (`INSERT OR IGNORE`; spec v1.9), so such a version imports and gets its `id-unique` violation. `SpecApproved` sets `status` to `approved` and `approved_at` from the event's `created_at`. `PlanCreated` deletes the `task_deps` and `tasks` rows of every `draft` plan and marks those plans `superseded`, then inserts the new plan as `draft`, one `tasks` row per contract (`pending`, `attempt` 0, `contract` as JSON of the validated contract) and one `task_deps` row per `depends_on` entry, all with plain `INSERT`. `PlanApproved` sets the plan's `status` to `approved`. `TaskStateChanged` sets the task's `state` to `to`; for a task not in `tasks` it changes no row. `AgentRunStarted` inserts an `agent_runs` row (`id`, `task_id`, `role`, `runtime`, `context_hash` from the payload, `started_at` from the event's `created_at` as `isoformat()`, the other columns null) with a plain `INSERT`. `AgentRunFinished` sets `model`, `exit`, `tokens_in`, `tokens_out`, `cost_usd`, `duration_s` and `ended_at` (its event's `created_at` as `isoformat()`) on the row whose `id` is `run_id`; for a run not in `agent_runs` it changes no row, and its `error` is not projected (no column). `SpecValidated` is validated and writes nothing. Event types with no entry in `PAYLOAD_MODELS` are ignored.
- `rebuild(events)`: drops the seven tables, recreates them and applies the given events in `seq` order. The caller passes the events (for example `EventStore.read()`).
- It does not check event sequences (a `from` against the stored state, a `PlanApproved` for an unknown or non-draft plan, an `AgentRunFinished` for an unknown or finished run, a second `AgentRunStarted` for one run id, which ends in `sqlite3.IntegrityError`), a payload's `hash` against its `spec`, or the last applied `seq`.

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
- `SqliteEventRecorder(path)`: opens its own connection, sets WAL mode and `PRAGMA busy_timeout = 5000`, then, in one transaction, creates what is missing (the `events` table, the projections, and `projection_state` with its single row `id = 1`, `last_seq = 0`) and catches up.
- Catch-up: every stored event with `seq > last_seq` is applied in `seq` order and `last_seq` is set. It runs only when the recorder opens. A stored payload its model rejects raises `pydantic.ValidationError` whose title is `stored event seq N (<model>)`; a stored event the projector cannot write raises `sqlite3.IntegrityError` whose message starts the same way (no M1 event reaches this case since spec v1.9: a duplicated requirement or ADR id is skipped by the projector, not an error). In both cases the transaction is rolled back, nothing is applied, and the connection is closed.
- `record(event)`: inserts the event, and if it is new applies it with `SqliteProjector` and sets `last_seq` to its `seq`, all in one transaction. Any error rolls the transaction back, so a rejected payload leaves no stored event. A repeated `event_id` applies nothing.
- `rebuild()`: not on the port. In one transaction it reads every stored event, calls `SqliteProjector.rebuild` and sets `last_seq` to the highest `seq` (0 for an empty log); a failure rolls everything back. `projection_state` is updated in place, never dropped.
- `close()` releases the connection.
- Every transaction starts with `BEGIN IMMEDIATE`. `projection_state` is bookkeeping, not a projection; the recorder is its only writer.

### Spec version reference
`src/openfactory/domain/spec_versions.py`. Pure Pydantic v2 model, no I/O. It imports nothing from `adapters`, `app` or `ports`.
- `SpecVersionRef`: `id` (`SpecVersionId`) and `hash` (`ContentHash`), both from `payloads.py`. The model is frozen and rejects unknown fields.

### SpecVersions port
`src/openfactory/ports/spec_versions.py`. The read-only interface to the `spec_versions`, `requirements` and `adrs` projections (ADR-001, ADR-012). It imports from `openfactory.domain` only.
- `SpecVersions` (Protocol): four methods. `latest_approved() -> SpecVersionRef | None` and `current_draft() -> SpecVersionRef | None` return `None` when there is no such version. `next_id() -> str` returns the highest number in any row's id plus one, written with at least two digits (`sv_01` when there is no row), also while a draft exists. `spec_set(version_id: str) -> SpecSet | None` returns the stored spec set of a draft or an approved version, or `None` when the version has no row; a version imported with an empty spec set gives an empty `SpecSet`.

### SQLite spec versions
`src/openfactory/adapters/sqlite_spec_versions.py`. Implements `SpecVersions` over SQLite (ADR-001, ADR-010). It imports nothing from `openfactory.app`.
- `SqliteSpecVersions(path)`: opens its own connection and sets `PRAGMA busy_timeout = 5000`. It runs only `SELECT` on `spec_versions`, `requirements` and `adrs`, creates no table and writes nothing; a database without the `spec_versions` table raises `sqlite3.OperationalError`, which is not handled.
- Every call runs its query again and nothing is cached, so it sees what a recorder on another connection has committed. "Latest approved" is the approved row with the highest id number; ids are compared as integers with `CAST(substr(id, 4) AS INTEGER)`.
- `spec_set(version_id)` reads `components` from the `spec_versions` row (no row gives `None`) and the `requirements` and `adrs` rows of the version with `ORDER BY id`, decodes the JSON columns and validates the result with `SpecSet.model_validate`. The inner lists (`components`, `constrained_by`, `acceptance_criteria`) keep the order the stored arrays hold; item hashes are not returned. For a version imported with a duplicated id the projector kept the first item, so the set is smaller than the payload's.
- `close()` releases the connection.

### Runs port
`src/openfactory/ports/runs.py`. The read-only interface to the `agent_runs` projection (ADR-012). It imports nothing from `adapters` or `app`.
- `Runs` (Protocol): one method. `next_id() -> str` returns the highest run number in any `agent_runs` row, finished or not, plus one, written as `run_NNNN` with at least four digits (`run_0001` when there is no row).

### SQLite runs
`src/openfactory/adapters/sqlite_runs.py`. Implements `Runs` over SQLite (ADR-012, ADR-010). It imports nothing from `openfactory.app`.
- `SqliteRuns(path)`: opens its own connection and sets `PRAGMA busy_timeout = 5000`. It runs only `SELECT` on `agent_runs`, creates no table and writes nothing; a database without the table raises `sqlite3.OperationalError`, which is not handled.
- `next_id` runs one query, `SELECT MAX(CAST(substr(id, 5) AS INTEGER)) FROM agent_runs`, on every call and caches nothing, so it sees what a recorder on another connection has committed.
- `close()` releases the connection. The module ends with the `TYPE_CHECKING` assertion against `Runs`.

### Plan and task references
`src/openfactory/domain/plans.py`. Pure Pydantic v2 models, no I/O. It imports from `openfactory.domain` only.
- `PlanRef`: `id` (`PlanId`) and `spec_version` (`SpecVersionId`). It has no `status`; the method that returns it fixes the status. Frozen, rejects unknown fields.
- `Task`: one row of the `tasks` projection with its dependencies: `id` (`TaskId`), `plan_id` (`PlanId`), `state` (`TaskState`), `attempt` (`int`), `contract` (`TaskContract`) and `depends_on` (`list[TaskId]`, read from `task_deps`). The objective is `contract.objective`. Frozen, rejects unknown fields.

### Plans port
`src/openfactory/ports/plans.py`. The read-only interface to the `plans`, `tasks` and `task_deps` projections (ADR-012). It imports from `openfactory.domain` only.
- `Plans` (Protocol): five methods. `current_draft() -> PlanRef | None` and `approved() -> PlanRef | None` return `None` when there is no such plan; if several rows share the status, the one with the highest id number is returned. `next_id() -> str` returns the highest number in any `plans` row, superseded plans included, plus one, written as `plan_NN` with at least two digits (`plan_01` when there is no row). `tasks(plan_id: str) -> list[Task]` returns the plan's tasks in ascending id, each with its `depends_on`; it returns `[]` for a superseded plan and for a plan id with no row. `live_tasks_referencing(requirement_id: str) -> list[str]` returns, in ascending order, the ids of the tasks whose contract lists the requirement and whose state is neither `abandoned` nor `invalidated`.

### SQLite plans
`src/openfactory/adapters/sqlite_plans.py`. Implements `Plans` over SQLite (ADR-012, ADR-010). It imports nothing from `openfactory.app`.
- `SqlitePlans(path)`: opens its own connection and sets `PRAGMA busy_timeout = 5000`. It runs only `SELECT` on `plans`, `tasks` and `task_deps`, creates no table and writes nothing; a database without those tables raises `sqlite3.OperationalError`, which is not handled.
- Every call runs its queries again and nothing is cached, so it sees what a recorder on another connection has committed. Ids are compared as integers with `CAST(substr(id, 6) AS INTEGER)`; `next_id` takes the `MAX` of that and the two plan reads order by it.
- `tasks` reads the `tasks` rows of the plan with `ORDER BY id` and the `task_deps` rows of those tasks with `ORDER BY depends_on`, and decodes `contract` with `TaskContract.model_validate_json`. The state is returned as the projection holds it; `TRANSITIONS` is not enforced.
- `live_tasks_referencing` selects the tasks not in `abandoned` or `invalidated` with `ORDER BY id` and filters in Python on the decoded contract's `requirements`. It does not look at plan status: the tasks of a superseded draft are gone from `tasks`, and those of a draft plan count.
- `close()` releases the connection. The module ends with the `TYPE_CHECKING` assertion against `Plans`.

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

### List events use case
`src/openfactory/app/list_events.py`. Application-layer use case that reads the event log. It imports only from `openfactory.domain` and `openfactory.ports`, nothing from `adapters`. It returns data and prints nothing.
- `list_events(store: EventStore, stream: str | None = None) -> list[StoredEvent]`: returns `store.read(stream)` unchanged, in ascending `seq`. It never calls `append`.

### CLI
`src/openfactory/cli.py`. The Typer app `app` and the composition root (ADR-011): the one module that may import adapters and use cases and wire them. It sits outside the four layers, and no module under `domain/`, `ports/`, `adapters/` or `app/` imports it. It implements no port. `[project.scripts]` points `openfactory` at `openfactory.cli:app`.
- `init <repo>`: exits 1 with `not a git repository: <repo>` on standard error when `<repo>` has no `.git` entry (a directory or a file); the check runs before anything is created. Otherwise it creates, if missing and in this order, `.openfactory/openfactory.db` (by opening and closing `SqliteEventRecorder`; when the file exists the recorder is not opened), `.openfactory/.gitignore` containing `*`, and `specs/policies.yaml` from the spec's code block, never overwriting a file. It prints `created <path>` or `exists <path>` per item, relative to `<repo>`, and records no events.
- `require_init() -> Path`: the check later commands call first. It returns `Path(".openfactory/openfactory.db")` when `./.openfactory/` is a directory, and otherwise writes "run `openfactory init` first" to standard error and raises `typer.Exit(1)`. It does not search parent directories and does not check that the database file exists. `validate`, `approve spec`, `plan`, `approve plan` and `events` call it first.
- `_open_adapters(database)`: a private context manager that opens `SqliteEventRecorder` first (only the recorder creates the tables, ADR-010), then `SqliteSpecVersions`, `SqlitePlans` and `SqliteRuns` on the same path, always all three, yields them as the frozen dataclass `_Adapters` (`recorder`, `versions`, `plans`, `runs`) and closes them in reverse order (an `ExitStack` with `closing`). `validate`, `approve spec`, `plan` and `approve plan` use it.
- `validate`: no arguments. Calls `require_init()`, opens the adapters with `_open_adapters`, builds `FilesystemSpecFiles(Path("specs"))`, calls the `validate` use case and closes the adapters. It prints the lines from `_result_lines` on standard output and exits 1 when there is any violation or policy problem, otherwise 0.
- `approve spec`: a command in the `approve` group (`approve_app`, a Typer sub-app registered with `app.add_typer(approve_app, name="approve")`, with a callback so it stays a group; the group's help reads "Approve a spec version or a plan."). No arguments. Calls `require_init()`, opens the adapters with `_open_adapters`, builds `FilesystemSpecFiles(Path("specs"))`, calls the `approve_spec` use case and closes the adapters. It prints the lines from `_result_lines` on standard output, with the status line `approved <spec version>` only for the `approved` outcome; for `nothing_to_approve` it writes `nothing to approve` to standard error. It exits 0 for `approved` and 1 for every other outcome.
- `plan`: no arguments. Calls `require_init()`, then `_prepare_and_create_plan(database)`, which opens the adapters with `_open_adapters` (they are closed before the result is printed; the warning and any log line are written while they are open), builds `FilesystemSpecFiles(Path("specs"))`, calls `prepare_plan`, writes `spec files differ from approved <spec version>` to standard error when `PlanInputs.spec_files_differ`, then calls `create_plan` with `GitCli(Path("."))` and `ClaudeCodeLLM()`. `_refusal_line` maps `PlanRefusal` to `no approved spec version`, `policy is invalid; run openfactory validate` and `<plan_id> is already approved; use replan`, written to standard error (exit 1). By outcome: `created` prints one `task_id  objective` line per task and `created <plan_id>` (exit 0); `rejected` prints `rejection_lines` of the second reply on standard output (exit 1); `git_failed` and `failed` write `git ls-files failed: <error>` and `planner call failed: <error>` to standard error (exit 1), where `_first_line` gives `<error>` as the first line of `PlannerResult.error`.
- `approve plan`: a command in the `approve` group, function `approve_plan_command`, registered with `@approve_app.command("plan")` (the name `plan` is taken by the top-level command). No arguments. Calls `require_init()`, opens the adapters with `_open_adapters`, calls `approve_plan(versions, plans, recorder)` and closes the adapters before printing. `approved` prints one `task_id  ready` line per id in `result.ready`, in the order the use case gives them, then `approved <plan_id>`, on standard output (exit 0); `no_draft` writes `no draft plan` and `stale_draft` writes `<plan_id> was made for <spec_version>; run openfactory plan` to standard error (exit 1).
- `_configure_logging()`: configures structlog with `add_log_level` and `JSONRenderer` and `PrintLoggerFactory(file=sys.stderr)`, so a log line is a JSON object with `event` and `level` and no timestamp. It is called from the Typer callback `main()`, so it applies to every command.
- `events`: option `--stream S` (a string, default none). Calls `require_init()`, opens `SqliteEventStore` on the returned path (not the recorder, so no catch-up runs and nothing is written; the store creates a missing database file and the `events` table), calls the `list_events` use case, closes the store and prints one line per event on standard output. It prints nothing and exits 0 for an empty log or a stream with no match.
- `_event_line(event) -> str`: one `StoredEvent` as a JSON object with the keys `seq`, `event_id`, `stream`, `type`, `payload`, `actor`, `causation_id` (`null` when absent) and `created_at`, dumped with `json.dumps` with sorted keys at every level, separators `,` and `:`, and `ensure_ascii=False`. `created_at` is `isoformat()` of the stored datetime (offset `+00:00`), the form the adapters write, not Pydantic's `Z` form.
- `_result_lines(violations, policy_problems, status) -> list[str]`: the violation lines sorted on `(rule, subject, message)`, the policy lines sorted the same way, the count line `N violations, M policy problems`, then the status line (`matches approved sv_NN` from `validate`, `approved sv_NN` from `approve spec`) when there is one (`validate` and `approve spec` call it). Each line joins its fields with two spaces; the field tuples are sorted before joining.

### Task contract models
`src/openfactory/domain/contracts.py`. Pure Pydantic v2 models of a task and the rule that completes one, no I/O. It imports `openfactory.domain.policy` and nothing from `adapters`, `app` or `ports`.
- `PlannedTask`: what the planner emits. `task_id` (string matching `^[A-Z]+-\d{3}$`), `objective`, `requirements`, `acceptance_criteria` and `allowed_paths` (the last three non-empty lists), `components` (list, may be empty), `role` (`implementer` only), and `depends_on` and `forbidden_paths` (lists, default `[]`). It has no `required_gates` or `limits`, and a reply that contains either fails validation.
- `Limits`: `max_runtime_s`, `max_attempts` (integers) and `max_cost_usd` (float), all required and greater than zero.
- `TaskContract(PlannedTask)`: adds `required_gates` (list of `path_check`, `ruff`, `pytest`, `gitleaks`, `review`, in the order given) and `limits`, both required. This is what is stored and executed.
- All three are frozen and reject unknown fields. Entries in the path lists are plain strings; their glob syntax is not checked.
- `REQUIRED_GATES`: tuple of the five gate names `path_check`, `ruff`, `pytest`, `gitleaks`, `review`, declared `Final`.
- `PlannerReply`: frozen, rejects unknown fields; one field, `tasks: list[PlannedTask]`. It is the model that validates the planner's structured result; the list has no minimum length.
- `complete_contract(planned: PlannedTask, policy: Policy) -> TaskContract`: copies the planned task's fields and sets `depends_on` to the planner's list without duplicates, each id at its first position; `forbidden_paths` to the baseline paths, then the policy's list, then the planner's, each string kept at its first position; `required_gates` to `list(REQUIRED_GATES)`; and `limits` from the policy's `max_runtime_s`, `max_attempts` and `max_cost_usd`. Neither input is changed.

### Task state machine
`src/openfactory/domain/states.py`. Pure data, no I/O, no import from `adapters`, `app` or `ports`.
- `TaskState`: `StrEnum` of the nine states `pending`, `ready`, `running`, `gating`, `passed`, `failed`, `escalated`, `abandoned`, `invalidated`, in the spec's order.
- `TRANSITIONS: dict[TaskState, frozenset[TaskState]]`: the allowed transitions, as in the spec's block; `abandoned` and `invalidated` have no targets. It is data only: no function checks a transition and nothing enforces it.

### Plan checks
`src/openfactory/domain/plan_checks.py`. Pure function that checks a planner's tasks against a spec set, no I/O. It imports nothing from `adapters`, `app` or `ports`, and no graph library.
- `PlanRule`: `StrEnum` of the nine rule names of the spec's table: `schema`, `duplicate-task-id`, `unknown-dependency`, `cycle`, `unknown-requirement`, `deprecated-requirement`, `unknown-criterion`, `undeclared-component`, `uncovered`. It is separate from `Rule`. `check_plan` never returns `schema`; that rule belongs to `parse_reply`.
- `ParsedReply`: frozen; `tasks: list[PlannedTask] | None` and `rejections: list[PlanRejection]`. The model does not enforce it, but `parse_reply` returns tasks or rejections, never both: on any rejection `tasks` is `None`, so there is nothing to pass to `check_plan`.
- `parse_reply(structured: object | None) -> ParsedReply`: `None` gives one `schema` rejection with subject `reply` and message `no structured result`. Otherwise it validates with `PlannerReply` and gives one `schema` rejection per Pydantic error, with message `<dotted field path>: <Pydantic msg>` and the subject the `task_id` of the task the error lies in when that value is a string, else `reply`. An empty `tasks` list is not rejected here.
- `PlanRejection`: frozen, rejects unknown fields; `rule` (a `PlanRule`), `subject` (the task id, or the requirement or criterion id for `uncovered`) and `message` (names the offending id).
- `check_plan(tasks: Sequence[PlannedTask], spec: SpecSet) -> list[PlanRejection]`: runs the eight content rules and returns every rejection in one run, one per subject and offending id. Order is the spec table's rule order, then the order of the reply (`uncovered` in spec-set order); no test fixes it, and sorting for output is left to the callers.
- `cycle`: a task is reported when it can reach itself through `depends_on`; a walk in plain Python that does not follow a dependency outside the plan. A task that depends on itself is a `cycle`, not an `unknown-dependency`.
- `uncovered`: each requirement that is not deprecated, and each of its criteria, that no task lists.
- `rejection_lines(rejections: Sequence[PlanRejection]) -> list[str]`: one `rule  subject  message` line per rejection (two spaces between the fields), sorted by rule name, then subject, then message, as strings; the input is not changed. It is the form `plan` prints and `AgentRunFinished.error` stores, and the lines the retry prompt holds.

### Planner prompt
`src/openfactory/app/planner_prompt.py`. Pure functions, no I/O; it imports from `domain` only.
- `build_planner_prompt(spec, policy, tracked_files, rejections=()) -> str`: plain text in fixed order, so equal arguments give equal text. Sections: instructions (the reply form, and what the plan checks enforce: known ids, declared components, full coverage, no cycles, no `required_gates` or `limits`), components, requirements that are not deprecated (id, title, statement, priority, components, `constrained_by` ids, criteria with their text), the bodies of the ADRs those requirements are constrained by (each in an `<adr id="...">` delimiter), forbidden paths (the baseline, then the policy's), the gate names (`REQUIRED_GATES`) and the tracked file names, one per line, in the order given. An empty part (a requirement's `constrained_by`, or the components, ADRs or tracked files) is written as `(none)`.
- Left out: a deprecated requirement whole (id, statement, criteria), an ADR named only by a deprecated requirement or by none, and all file contents.
- Retry form: with `rejections` the prompt is the same text with a last section holding `rejection_lines(rejections)`. It does not hold the rejected reply. One function builds both, so the retry prompt cannot drift from the first.
- `context_hash(prompt) -> str`: SHA-256 of the prompt encoded as UTF-8, 64 lowercase hex characters; the `context_hash` of `AgentRunStarted`.

### LLM reply
`src/openfactory/domain/llm.py`. Pure Pydantic model, no I/O, no import from `ports`, `adapters` or `app`.
- `LLMReply`: frozen, rejects unknown fields. `structured: object | None` is the runtime's structured result, not validated (the caller validates it with its own model; `None` when the runtime gave none). `model`, `tokens_in`, `tokens_out` and `cost_usd` are `None` when the runtime reported none. `tokens_in` is every input token: uncached, written to the cache and read from it. `duration_s` is a float.

### LLMProvider port
`src/openfactory/ports/llm_provider.py`. The interface for one planner or classifier call.
- `LLMProvider` (Protocol): one method, `complete(prompt: str, schema: dict[str, object]) -> LLMReply`. `schema` is the JSON Schema of the structured result. A reply with no structured result, or one the caller's model would reject, is returned, not raised. Nothing is retried.
- `LLMError(Exception)`: keyword-only `duration_s: float` and `timeout: bool`; its text is `str(error)`. It sits beside the Protocol, as `EventConflictError` does.

### Claude Code LLM adapter
`src/openfactory/adapters/claude_code_llm.py`. `ClaudeCodeLLM(executable="claude", timeout_s=300)` implements `LLMProvider` (ADR-005); it ends with the `TYPE_CHECKING` assertion.
- One process per call: `claude -p --output-format json --json-schema <schema as JSON> --tools ""`, no `--model`. The prompt goes on standard input as UTF-8. The process runs in a new empty temporary directory, so no `CLAUDE.md`, settings or hooks of a repo are loaded.
- Its environment is every variable except `ANTHROPIC_API_KEY`, built from the names so the value is never read; one structlog warning (`anthropic_api_key_removed`) is logged when the name was present. structlog is configured by `cli.py` (`_configure_logging`, called from the Typer callback), not here.
- Envelope fields read, pinned by `tests/fixtures/claude_envelope.json` (captured from Claude Code 2.1.287, ADR-005 names 2.1.286): `structured_output`; the keys of `modelUsage` with each one's `outputTokens` (the model is the single key, or the one with the most output tokens, the first on a tie, `None` when absent, `null` or empty); `usage.input_tokens`, `usage.cache_creation_input_tokens` and `usage.cache_read_input_tokens` (those present summed into `tokens_in`, `None` when none is); `usage.output_tokens`; `total_cost_usd`; `duration_ms` (divided by 1000; the measured duration when absent). Absent metric fields give `None`; an absent or `null` `structured_output` gives `structured` `None`. `is_error` and `subtype` are not read.
- `LLMError` with `timeout` true: the limit passed (`timed out after 300 s`). With `timeout` false: a non-zero exit (standard error stripped, or `claude exited with status N` when empty); a `claude` that cannot be started (`claude could not be started: <OS error>`); standard output that is not a JSON object the private envelope model accepts (`claude output is not a JSON envelope`). `duration_s` is the measured time.
- Tests use a stand-in executable written under `tmp_path`; none starts `claude`.

### GitProvider port
`src/openfactory/ports/git_provider.py`. The interface to git for the plan use case. It imports nothing from `adapters` or `app`.
- `GitProvider` (Protocol): one method, `tracked_files() -> list[str]`, the tracked files of the repo as plain strings, relative to the repo with `/` as the separator, in git's order. M3 adds the other git methods (ADR-012).
- `GitError(Exception)`: no extra fields; its text is `str(error)`. It sits beside the Protocol, as `LLMError` does.

### Git CLI adapter
`src/openfactory/adapters/git_cli.py`. `GitCli(repo: Path, executable: str = "git")` implements `GitProvider`; it ends with the `TYPE_CHECKING` assertion.
- `tracked_files` starts one process per call, `git ls-files -z`, with `repo` as its working directory and no time limit. Standard output is split on NUL and empty elements are dropped, so names are returned as git stores them, unquoted. A file added and not committed is listed; an untracked or ignored file is not.
- `GitError` texts: for a non-zero exit, standard error stripped, or `git exited with status N` when that is empty; for an `OSError` on start, `git could not be started: <OS error text>`.
- Tests run the real `git` on a repository under `tmp_path` (`git init`, `git add`, no commit) with `GIT_DIR`, `GIT_WORK_TREE` and `GIT_INDEX_FILE` removed from the environment, and a stand-in executable for the command line and the failure cases. The test suite requires `git` on the machine.

### Plan use case: the planner call
`src/openfactory/app/plan.py`. Depends on `domain` and `ports` and on `app/planner_prompt.py`; it imports nothing from `adapters` or `cli.py`, and prints nothing.
- `run_planner(spec_version, spec, policy, tracked_files, *, llm, runs, plans, recorder) -> PlannerResult` makes at most two attempts. Each attempt is a run: `Runs.next_id` (read after the earlier run started), `AgentRunStarted` (stream `run:<id>`, role `planner`, `context_hash` of the prompt), `LLMProvider.complete(prompt, PlannerReply.model_json_schema())`, `parse_reply`, `check_plan` when tasks loaded, then `AgentRunFinished`. The finish is recorded after the checks: a rejected reply has `exit: ok` and `error` set to its `rejection_lines` joined by newlines; an accepted one has `error: null`.
- Retry: a rejected reply (a `schema` rejection, a missing structured result, or a failed check) is retried once, with `build_planner_prompt(..., rejections=<the first reply's>)`, as a second pair of run events. The retry is inside `run_planner`; a helper shared with the classifier waits for M6.
- Failed process: an `LLMError` ends the attempt with `AgentRunFinished` (`exit` `timeout` or `error`, `error` the `str(error)` unchanged, `duration_s` from the error, model, tokens and cost null). It is not retried, and it ends the function whether it came first or second.
- Accepted reply: `Plans.next_id` is read, `complete_contract` runs per task, the contracts are sorted by `task_id`, and `PlanCreated` is recorded on stream `plan:<id>` with `policy_hash(policy)` and the `run_id` of the accepted run. Every event has actor `orchestrator`, and its `causation_id` is the `event_id` of the event recorded just before it (the first has none).
- `PlannerResult`: frozen, rejects unknown fields; `outcome` (`PlannerOutcome`: `created`, `rejected`, `failed`, and `git_failed`, which only `create_plan` returns), `plan_id`, `tasks` (the stored contracts), `rejections` (the second reply's, for `rejected`) and `error` (the whole text, for `failed` and `git_failed`). A private `_Attempt` model and `_attempt` function carry one run. `create_plan` can also return `git_failed` (next section).
- Tests (`tests/unit/test_plan_use_case.py`) use in-memory fakes for the recorder, `Runs`, `Plans` and the LLM.

### Plan use case: the entry and the refusals
`src/openfactory/app/plan.py`, beside `run_planner`. The `plan` command is two calls (ADR-013); both functions return data and print nothing. The `plan` command in `cli.py` calls them in that order and prints the `spec files differ` warning between them.
- `prepare_plan(files: SpecFiles, versions: SpecVersions, plans: Plans) -> PlanRefused | PlanInputs` takes those three ports and no recorder, `GitProvider` or LLM, and records no event. It returns at the first check that applies: `SpecVersions.latest_approved()` is `None` (`no_approved_spec`); `load_policy(files)` gives no policy, which covers a missing `policies.yaml` (`invalid_policy`); `Plans.approved()` is not `None`, for any spec version (`approved_plan`, with its id).
- Only after those three checks are the spec files loaded, with `load_spec`. `spec_files_differ` is true when that load gives no spec set or `content_hash` of the set is not the approved version's hash. The files are never imported or used for planning: `PlanInputs.spec` is `SpecVersions.spec_set(<approved id>)`, asserted not `None`, also when the files equal it.
- `PlanRefusal` (`StrEnum`: `no_approved_spec`, `invalid_policy`, `approved_plan`); `PlanRefused` (frozen, rejects unknown fields): `reason` and `plan_id`, set only for `approved_plan`. `PlanInputs` (frozen, rejects unknown fields): `spec_version`, `spec`, `policy`, `spec_files_differ`. The refusal texts and the warning are written by `cli.py`, not here.
- `create_plan(inputs, *, git, llm, runs, plans, recorder) -> PlannerResult` calls `GitProvider.tracked_files()` once, then `run_planner` with the inputs and the files. A `GitError` is returned as data: `PlannerResult(outcome=git_failed, error=str(error))`, the whole text; the LLM is not called, no event is recorded and no id is read. The first line of `error` for the `git ls-files failed` and `planner call failed` lines is taken by `cli.py`.
- Tests (`tests/unit/test_plan_entry.py`) use in-memory fakes for `SpecFiles`, `SpecVersions`, `Plans`, `GitProvider`, the LLM, `Runs` and the recorder.

### Approve plan use case
`src/openfactory/app/approve_plan.py`. Application-layer use case that approves the draft plan or says why not. It imports only from `openfactory.domain` and `openfactory.ports`, nothing from `adapters` or `cli`. It returns data and prints nothing. The `approve plan` command calls it.
- `approve_plan(versions: SpecVersions, plans: Plans, recorder: EventRecorder) -> ApprovePlanResult`: no `SpecFiles`, `GitProvider` or LLM; the spec files and the policy are not read.
- Two refusals, in this order, with nothing recorded. `Plans.current_draft()` is `None`: `no_draft`. `SpecVersions.latest_approved()` is `None` or its id differs from the draft's `spec_version`: `stale_draft`, carrying the draft's id and spec version.
- Otherwise it records `PlanApproved` (`PlanApprovedPayload`, stream `plan:<id>`, actor `human`, no `causation_id`), then reads `Plans.tasks(<draft id>)` and records one `TaskStateChanged` (`pending` to `ready`, `reason` null) for each task whose `depends_on` is empty, in ascending task id as strings (sorted by the use case, not taken from the port's order). Each is on stream `task:<id>` with actor `orchestrator` and `causation_id` the `PlanApproved` event id, not chained to the event before it. Tasks with dependencies stay `pending`. A draft with no tasks records `PlanApproved` alone.
- `ApprovePlanResult`: a frozen model (`extra="forbid"`) with `outcome` (`ApprovePlanOutcome`: `no_draft`, `stale_draft`, `approved`), `plan_id` and `spec_version` (the draft's; `None` for `no_draft`) and `ready` (the ids made ready, ascending; empty unless `approved`).
- The `TaskStateChanged` payload is built in the private helper `_made_ready` with `TaskStateChangedPayload.model_validate` from a dict with the key `from`, because pyright rejects `from_=`. The events are recorded in separate transactions; if the recorder raises, the error propagates.
- Tests (`tests/unit/test_approve_plan_use_case.py`) use in-memory fakes for `SpecVersions`, `Plans` and the recorder.

## Data flow
<!-- updated when a milestone changes it -->
Events are stored in the SQLite `events` table, which assigns `seq`. There are two write paths, `EventRecorder.record` and `EventStore.append`; use cases are meant to use only the first (ADR-001). Stored events are read back in `seq` order by `EventStore.read`, whose callers are the `list_events` use case behind the `events` command and, in later tasks, replay. Specs are validated by the `validate_spec` function, which returns every violation found.

Use cases build the payload of a spec event through the models in `payloads.py`. The validate use case (`app/validate.py`) does so for `SpecImported` and `SpecValidated`, converting each `SpecViolation` to a `RecordedViolation`. The approve-spec use case (`app/approve_spec.py`) builds `SpecApproved` through `SpecApprovedPayload`.

`SqliteProjector` validates each stored payload against `PAYLOAD_MODELS` and writes the `spec_versions`, `requirements`, `adrs`, `plans`, `tasks`, `task_deps` and `agent_runs` projections, one event at a time or by a rebuild from the event log. Its only caller is `SqliteEventRecorder`, which appends an event, applies it and sets `projection_state.last_seq` in one transaction, applies unapplied events when it opens a database, and rebuilds the projections in one transaction. The validate use case calls the recorder through the `EventRecorder` port; the approve-spec use case records `SpecApproved` the same way. The `validate` command wires `SqliteEventRecorder` to the validate use case, and the `approve spec` command wires it to the approve-spec use case. Use cases must write through the recorder only; an event appended through `EventStore.append` while a recorder is open is not applied by that recorder (ADR-010).

Spec file text reaches the application layer through the `SpecFiles` port, not by reading the filesystem directly; `FilesystemSpecFiles` is the adapter. `load_spec` parses the YAML and ADR front matter from that text and returns either a `SpecSet` or the `schema` violations. It does not run `validate_spec`; the validate use case runs the content rules only when the load produced a spec set. `validate` calls `load_spec`. `load_policy` reads `policies.yaml` the same way and returns either a `Policy` or the `schema` violations; it is separate from `load_spec`, and the policy is not part of the spec set or its hash. `validate` calls `load_policy` in every case and returns its violations as policy problems.

Use cases read the spec version projections only through the `SpecVersions` port, to compare hashes and choose the spec version id; `SqliteSpecVersions` is the adapter and reads `spec_versions`, `requirements` and `adrs` on its own connection. The validate use case calls the port, and the approve-spec use case reaches it through `validate`. The CLI (`cli.py`) has `init`, which uses `SqliteEventRecorder` to create the database, and `validate`, which wires the recorder, `SqliteSpecVersions` and `FilesystemSpecFiles` to the validate use case, and `approve spec`, which wires the same three to the approve-spec use case; `_open_adapters` now opens the recorder and the three read adapters for `validate`, `approve spec`, `plan` and `approve plan`, and `approve plan` wires them to the approve-plan use case. `events` wires `SqliteEventStore` to the `list_events` use case and renders each stored event with `_event_line`; it reads the log only.

`SpecVersions.spec_set` and `Runs.next_id` exist, with `SqliteSpecVersions` and `SqliteRuns` behind them, for the plan use case; `run_planner` calls `Runs.next_id`, and `prepare_plan` calls `spec_set`. The five `Plans` reads (`current_draft`, `approved`, `next_id`, `tasks`, `live_tasks_referencing`) exist the same way, with `SqlitePlans` behind them, for the plan, approve-plan and `deleted-requirement` code; `run_planner` calls `next_id`, `prepare_plan` calls `approved`, `approve_plan` calls `current_draft` and `tasks`, and no use case calls `live_tasks_referencing` yet.

The task contract models and the task state machine are used by the M2 payload models (`TaskContract` inside `PlanCreatedPayload`, `TaskState` in `TaskStateChangedPayload`); `run_planner` builds `PlanCreated`, and `approve_plan` builds `TaskStateChanged` (the `approve plan` command calls it). `complete_contract` and `policy_hash` are called by `run_planner`, which builds `PlanCreated` with complete contracts and the policy's hash. `check_plan` is run by `run_planner` on a reply that passed the reply model, and the reply is rejected when it returns any rejection. `parse_reply` is the step before it: it turns the planner's structured result into validated tasks or `schema` rejections.

`LLMProvider` and `ClaudeCodeLLM` exist for the plan use case; `run_planner` calls the port, and the `plan` command wires the adapter.

`GitProvider` and `GitCli` exist for the plan use case; `create_plan` calls `GitProvider.tracked_files` to get the files for the planner prompt, and the `plan` command wires them.

`build_planner_prompt`, `context_hash` and `rejection_lines` are called by `run_planner`, which builds the prompt from the approved spec set, the policy and the tracked files, hashes it into `AgentRunStarted`, and builds the retry prompt from a rejected reply's rejections.

`run_planner` (`app/plan.py`) calls `Runs.next_id`, `Plans.next_id`, `LLMProvider.complete`, `parse_reply`, `check_plan`, `complete_contract`, `policy_hash`, `build_planner_prompt`, `context_hash` and `rejection_lines`, and records through `EventRecorder`. The `plan` command reaches it through `create_plan`.

`prepare_plan` (`app/plan.py`) calls `SpecVersions.latest_approved`, `Plans.approved`, `load_policy`, `load_spec`, `content_hash` and `SpecVersions.spec_set`. `create_plan` calls `GitProvider.tracked_files` and `run_planner`. The `plan` command calls `prepare_plan` and then `create_plan`, and wires `SqliteEventRecorder`, `SqliteSpecVersions`, `SqlitePlans`, `SqliteRuns`, `FilesystemSpecFiles`, `GitCli` and `ClaudeCodeLLM`.
