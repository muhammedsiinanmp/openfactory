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
<!-- remaining M1 tasks in order, from spec v1.9; an outline, not task records: the planner sets ids and scope -->
1. Projector keeps the first of two requirements, or two ADRs, with one id (`INSERT OR IGNORE`), so a spec set with a duplicated id gets its `id-unique` line; rewrites the recorder test that used a duplicated id to make the projector fail (SC-12, spec v1.9) · depends on TASK-009, TASK-010
2. `validate` and `approve spec` commands: one `rule  subject  message` line per violation and policy problem, a count, exit codes · depends on 1, TASK-012, TASK-013, TASK-014
3. `events [--stream S]` command: one JSON object per line in `seq` order · depends on TASK-014, TASK-002
4. M1 close: integration test of `init`, `validate`, `approve spec` and `events` on a sample repo, with the projections identical after a rebuild from its log · depends on 2, 3

## Done
<!-- newest first: date · task id · one line -->
- 2026-10-09 · TASK-014 · CLI entry point and `init`: Typer app in `cli.py` (the composition root, ADR-011) with `init <repo>`, which refuses a path without a `.git` entry and otherwise creates `.openfactory/openfactory.db` (by opening and closing `SqliteEventRecorder`), `.openfactory/.gitignore` containing `*` and `specs/policies.yaml` from the spec's defaults, printing `created <path>` or `exists <path>` per item and recording no events; `require_init()` is the "run `openfactory init` first" check for later commands; `[project.scripts]` points at the app
- 2026-10-09 · TASK-013 · Approve spec use case: `approve_spec(files, versions, recorder)` in `app/approve_spec.py` calls `validate`, then records `SpecApproved` (stream `spec:<version>`, actor `human`, `causation_id` the `SpecValidated` id) only when the files loaded, differ from the latest approved version and have no violations; returns an `ApproveResult` (`ApproveOutcome` of `unloadable`, `nothing_to_approve`, `refused` or `approved`, spec version, violations, policy problems); policy problems never block
- 2026-10-09 · TASK-012 · Validate use case: `validate(files, versions, recorder)` in `app/validate.py` loads and hashes the spec set, records `SpecImported` when the files changed and `SpecValidated` with the rule results, and returns a `ValidateResult` (outcome, violations, policy problems, hash, validated event id); records nothing when the files match the approved version or cannot be loaded
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
- Narrow `EventStore` to reading, or otherwise stop `EventStore.append` being used next to an open recorder: an event appended that way is not applied by the recorder, and the next `record` moves `last_seq` past it (ADR-010; ADR-001 left the narrowing to a later task)
- No repair path for a stored event whose payload its model rejects: every recorder open fails until the log is fixed by hand (ADR-010)
- `validate` task: print the `schema` line `load_policy` now produces for a missing `policies.yaml` (subject `specs/policies.yaml`, message "missing; run openfactory init") and exit 1 (decision of 2026-10-08)
- M2: merge the baseline, policy and planner forbidden paths into each task contract (baseline, then policy, then planner, without duplicates)
- Advisory LLM spec checks (vague wording, possible duplicates): removed from Phase 1 in the spec v1.4 proposal; `validate` is deterministic only
- workflow metrics: events in git worktrees are not logged
- Loader tests: a merge key (`<<`) is reported as a `schema` violation, and an anchor with an alias is expanded (SC-7, spec v1.8)
- Spec gap (not M1), from `docs/spec-audits/2026-10-09-proposal-v1.9.md`: F-1 what a command prints when the recorder's catch-up fails; today the exception propagates, and the M1 command tasks leave that state out of scope
- Spec wording (not M1), same report: F-4 "Every payload field is required" means the fields of the payload model itself; the spec set inside `SpecImported` uses the spec models and their defaults
- Spec gap (before M2 is planned): whether a planner or classifier call that times out, or whose process fails, is retried, and what `plan` records and exits with (audit finding F-26, second half)
- Spec gap (before M2 is planned), from `docs/spec-audits/2026-10-09-all.md`: F-2 `agent_runs` has no DDL; F-9 glob syntax of `allowed_paths` and `forbidden_paths`; F-14 the `reviewer` task role and the classifier role; F-15 `RunResult` against `AgentRunFinished`, field types and file paths; F-21 read ports for plans, tasks and runs; F-22 canonical form of the policy hash; F-36 source of cost per plan and run latency; F-37 approving a draft plan made for an older spec version
- Spec gap (before M3 is planned), same report: F-3 worktree base branch and `protected_branches`; F-8 the path check and its command; F-10 `tasks.attempt` and the cost limit; F-11 worktree on retry and restart; F-12 streams, payloads and milestones of `GateEvaluated`, `CommitRecorded`, `ImpactComputed`, `gate_results` and `commits`; F-13 M3 with four gates not built; F-30 commands missing from the table or the milestones; F-31 commits made by the agent and the tool allowlist; F-32 behaviour of `run`; F-34 the commit's subject and contents; F-39 output of `status` (and of `trace`, `why`, `coverage` for M5, `stats`, `report` for M7)
- Spec gap (before M4 is planned), same report: F-4 `resolve` has no event, actor or input; F-16 the pytest gate's tag rule; F-33 the review gate and gate order
- Spec gap (before M5 is planned), same report: F-5 `trace_links` schema, node kinds and requirement versions; F-35 rebuilding links from trailers against the projection rule
- Spec gap (before M6 is planned), same report: F-6 replan mechanics; F-7 which states can be invalidated; F-17 impact traversal; F-18 which versions `impact` compares and where the classification lives; F-38 the classifier call; F-42 the demo has no approval of the replanned plan
- Spec gap (before M7 is planned), same report: F-19 eval targets cannot be computed for cases with empty ground truth
