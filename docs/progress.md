# Progress

## Current
- Milestone: M1 — Specs and events
- Task: none

## Milestones
- [ ] M1 Specs and events
- [ ] M2 Planner
- [ ] M3 Executor
- [ ] M4 Gates and remediation
- [ ] M5 Traceability
- [ ] M6 Impact and replan
- [ ] M7 Eval, report, demo

## M1 outline
<!-- remaining M1 tasks in order, from spec v1.7; an outline, not task records: the planner sets ids and scope -->
1. Validate use case: load and hash the spec set, record `SpecImported` when the files changed (canonical order, draft id kept), run the rules, record `SpecValidated`; return policy problems without recording them · depends on TASK-004, TASK-005, TASK-007, TASK-008, TASK-010, TASK-011
2. Approve spec use case: import if changed, `SpecValidated` before `SpecApproved`, refusal on violations, "nothing to approve" · depends on 1
3. CLI entry point and `init`: Typer app, `.openfactory/` with its database and `.gitignore`, default `specs/policies.yaml`, safe to repeat, no events; "run `openfactory init` first" for the other commands · depends on TASK-010
4. `validate` and `approve spec` commands: one `rule  subject  message` line per violation and policy problem, a count, exit codes · depends on 1, 2, 3
5. `events [--stream S]` command: one JSON object per line in `seq` order · depends on 3, TASK-002
6. M1 close: integration test of `init`, `validate`, `approve spec` and `events` on a sample repo, with the projections identical after a rebuild from its log · depends on 4, 5

## Done
<!-- newest first: date · task id · one line -->
- 2026-10-09 · TASK-011 · SpecVersions port and SQLite adapter: read-only `SqliteSpecVersions` in `adapters/sqlite_spec_versions.py` gives the latest approved spec version, the current draft (`SpecVersionRef` in `domain/spec_versions.py`) and the next spec version id from the `spec_versions` projection, on its own connection (ADR-001, ADR-010)
- 2026-10-09 · TASK-010 · EventRecorder port and SQLite recorder: `SqliteEventRecorder` in `adapters/sqlite_recorder.py` appends an event, applies it and sets `projection_state.last_seq` in one transaction, catches up when it opens a database, and rebuilds the projections in one transaction; the `events` table SQL moved to `adapters/sqlite_events.py`, shared with `SqliteEventStore` (ADR-010)
- 2026-10-09 · TASK-009 · SQLite projector: `SqliteProjector` in `adapters/sqlite_projector.py` creates `spec_versions`, `requirements` and `adrs`, applies `SpecImported`, `SpecValidated` and `SpecApproved` events after validating their payloads, and rebuilds the tables from the event log identically; no port (ADR-009)
- 2026-10-09 · TASK-008 · Policy model and loader: frozen `Policy` and `BASELINE_FORBIDDEN_PATHS` in `domain/policy.py`; `load_policy` in `app/spec_loader.py` reads `policies.yaml` through the `SpecFiles` port and returns a `Policy` or every `schema` violation
- 2026-10-08 · TASK-007 · Spec loader: `load_spec` reads `requirements.yaml` and `adrs/*.md` through the `SpecFiles` port and returns a `SpecSet` or every `schema` violation; `schema` added to `Rule`; `pyyaml` added
- 2026-10-08 · TASK-006 · SpecFiles port and filesystem adapter: read-only access to `requirements.yaml`, `policies.yaml` and `adrs/*.md` text by path relative to `specs/`, with `None` for a missing file
- 2026-10-08 · TASK-005 · Payload models for the spec events: `SpecImportedPayload`, `SpecValidatedPayload`, `SpecApprovedPayload`, `RecordedViolation`, `SpecWarning` and `PAYLOAD_MODELS` in `domain/payloads.py`
- 2026-10-08 · TASK-004 · Spec model fields and canonical hashing: `deprecated` on `Requirement`, `body` on `Adr`, and `content_hash`/`canonical_json` functions for acceptance criteria, requirements, ADRs and spec sets
- 2026-10-08 · TASK-003 · Spec models and validation rules: `SpecSet`, `Requirement`, `AcceptanceCriterion`, `Adr` models and `validate_spec` for deterministic rules
- 2026-10-08 · TASK-002 · EventStore port and SQLite adapter: append-only event log with `seq` assignment and stream filtering
- 2026-10-08 · TASK-001 · Domain event model: `EventType` (11 types), `Event` and `StoredEvent` envelope models

## Blockers

## Later (out of current scope)
- payload depth limit
- CLI task (`validate`, `approve spec`): `SqliteSpecVersions` uses a plain `sqlite3.connect`, which creates an empty database file when the path does not exist, and it fails with `sqlite3.OperationalError` when the `spec_versions` table is missing. The command must check that the database file exists and open the recorder before this adapter, or the adapter must open the database read-only (`mode=ro`) (decisions of 2026-10-09, TASK-011)
- Narrow `EventStore` to reading, or otherwise stop `EventStore.append` being used next to an open recorder: an event appended that way is not applied by the recorder, and the next `record` moves `last_seq` past it (ADR-010; ADR-001 left the narrowing to a later task)
- No repair path for a stored event whose payload its model rejects: every recorder open fails until the log is fixed by hand (ADR-010)
- `validate` task: print the `schema` line `load_policy` now produces for a missing `policies.yaml` (subject `specs/policies.yaml`, message "missing; run openfactory init") and exit 1 (decision of 2026-10-08)
- M2: merge the baseline, policy and planner forbidden paths into each task contract (baseline, then policy, then planner, without duplicates)
- Advisory LLM spec checks (vague wording, possible duplicates): removed from Phase 1 in the spec v1.4 proposal; `validate` is deterministic only
- workflow metrics: events in git worktrees are not logged
- Spec wording (next spec revision): reword the "Tech stack" line "read with PyYAML (`yaml.safe_load`)", since rejecting duplicate keys needs `yaml.load` with a `SafeLoader` subclass
- Spec wording (next spec revision): anchors and merge keys are not supported
- Spec gap (before M2 is planned): "Projection rules" says M2 adds `agent_runs`, but the DDL block "The tables built in M1 and M2" has no `CREATE TABLE agent_runs`
