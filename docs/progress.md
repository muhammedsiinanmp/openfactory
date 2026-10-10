# Progress

## Current
- Milestone: M2 — Planner
- Task: none

## Milestones
- [x] M1 Specs and events
- [ ] M2 Planner
- [ ] M3 Executor
- [ ] M4 Gates and remediation
- [ ] M5 Traceability
- [ ] M6 Impact and replan
- [ ] M7 Eval, report, demo

## M2 outline
<!-- remaining M2 tasks in order, from spec v1.10; an outline, not task records: the planner sets ids and scope -->
2. Payload models for `PlanCreated`, `PlanApproved`, `TaskStateChanged`, `AgentRunStarted` and `AgentRunFinished` (ADR-007 and its amendment) · depends on TASK-020
3. Projector: the `plans`, `tasks`, `task_deps` and `agent_runs` tables and the five M2 events, including a new draft superseding the earlier one; extend `tests/unit/test_spec_conformance.py` to the four M2 tables · depends on 2
4. `Plans` and `Runs` read ports with `sqlite_plans` and `sqlite_runs`, and the stored spec set of a version on `SpecVersions` (ADR-012) · depends on 3
5. Contract completion and the policy hash: forbidden paths as baseline, then policy, then planner, without duplicates; the fixed gates; limits from the policy · depends on TASK-020
6. Plan checks: the nine rules with their subjects, one rejection per offending id, the cycle check in plain Python · depends on TASK-020
7. `LLMProvider` port and the Claude Code LLM adapter: `claude -p --output-format json --json-schema`, `LLMError` with its duration, `ANTHROPIC_API_KEY` removed from the environment, a captured envelope fixture (ADR-005 and its amendment)
8. `GitProvider` port with the tracked files, and the `git_cli` adapter (ADR-012)
9. Plan use case: the prompt, the single retry, run and plan ids, the events and their `causation_id` · depends on 4, 5, 6, 7, 8
10. `plan` command: task lines, rejection lines, refusals and the warning · depends on 9
11. Approve plan use case and the `approve plan` command · depends on 4
12. The `deleted-requirement` rule in `validate` and `approve spec`, which gain a `Plans` argument · depends on 4
13. M2 close: integration test of `plan` and `approve plan` on a sample repo with a stand-in `claude` executable, with the projections identical after a rebuild · depends on 10, 11, 12

## Done
<!-- newest first: date · task id · one line -->
- 2026-10-11 · TASK-020 · Task contract models and task state machine: frozen `PlannedTask`, `Limits` and `TaskContract(PlannedTask)` in `domain/contracts.py` (field for field as the spec's class block, `extra="forbid"`, no `required_gates` or `limits` on `PlannedTask`), and `TaskState(StrEnum)` with the nine states and `TRANSITIONS: dict[TaskState, frozenset[TaskState]]` in `domain/states.py`; `TRANSITIONS` is data, nothing enforces it; three conformance tests compare the spec's state list, `TRANSITIONS` block and YAML contract example with the code
- 2026-10-10 · TASK-019 · M1 close integration test: `tests/integration/test_m1_close.py` runs `init`, `validate`, `approve spec` and `events` through the Typer app on a sample repo with four inline spec-file states, checks output lines, exit codes, the 11 events with streams, actors and causation, and the projection rows, then empties the three projection tables, runs `SqliteEventRecorder.rebuild()` and finds them identical; `approve spec` then approves `sv_03` on the rebuilt projections; no `src/` change; M1 ticked
- 2026-10-10 · TASK-018 · `events` command: `app/list_events.py` gains `list_events(store, stream=None)`, a pass-through over `EventStore.read`; `cli.py` gains `events [--stream S]`, which after `require_init()` opens `SqliteEventStore` (not the recorder, so no catch-up runs), closes it, and prints one line per event in `seq` order through the `_event_line` helper (the eight envelope keys as sorted-key JSON, `created_at` as `isoformat()`), printing nothing for an empty log or a stream with no match
- 2026-10-10 · TASK-017 · `approve spec` command: `cli.py` gains an `approve` group with `spec`, which wires `SqliteEventRecorder`, `SqliteSpecVersions` and `FilesystemSpecFiles` to the approve-spec use case after `require_init()`, prints the lines from `_result_lines` with the status line `approved sv_NN` only when approved, writes `nothing to approve` to standard error when the files equal the approved version, and exits 1 for every outcome except `approved`
- 2026-10-10 · TASK-016 · `validate` command: `cli.py` wires `SqliteEventRecorder`, `SqliteSpecVersions` and `FilesystemSpecFiles` to the validate use case after `require_init()`, prints the violation lines, the policy lines (including the `schema` line for a missing `policies.yaml`), the count line and the `matches approved sv_NN` status line through the `_result_lines` helper, and exits 1 on any violation or policy problem
- 2026-10-10 · TASK-015 · Projector keeps the first duplicate id: the two inserts in `_apply_imported` are `INSERT OR IGNORE`, so a `SpecImported` with two requirements, or two ADRs, with one id keeps the first in the payload's order; a spec set with a duplicated id is imported and gets its `id-unique` violation instead of ending in `sqlite3.IntegrityError` (SC-12, spec v1.9)
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
- Projector `INSERT OR IGNORE` also skips a row on a `NOT NULL` or `CHECK` violation, not only on a duplicated id: unreachable today (no `CHECK`, and the payload models make every inserted value non-null); check it when a nullable model field is mapped to a `NOT NULL` projection column (TASK-015)
- Narrow `EventStore` to reading, or otherwise stop `EventStore.append` being used next to an open recorder: an event appended that way is not applied by the recorder, and the next `record` moves `last_seq` past it (ADR-010; ADR-001 left the narrowing to a later task)
- No repair path for a stored event whose payload its model rejects: every recorder open fails until the log is fixed by hand (ADR-010)
- Advisory LLM spec checks (vague wording, possible duplicates): removed from Phase 1 in the spec v1.4 proposal; `validate` is deterministic only
- workflow metrics: events in git worktrees are not logged
- Loader tests: a merge key (`<<`) is reported as a `schema` violation, and an anchor with an alias is expanded (SC-7, spec v1.8)
- Bare `openfactory` and bare `openfactory approve` print the help on standard output and exit 2 (`no_args_is_help`); the spec's "Output" block sends usage errors to standard error. No criterion or test covers it (TASK-014, TASK-017)
- Spec gap (not M1, deferred again as SC-42), from `docs/spec-audits/2026-10-09-proposal-v1.9.md`: F-1 what a command prints when the recorder's catch-up fails; today the exception propagates, and the M1 command tasks leave that state out of scope
- Spec gap (before M3 is planned), same report: F-3 worktree base branch and `protected_branches`; F-8 the path check and its command; F-10 `tasks.attempt` and the cost limit; F-11 worktree on retry and restart; F-12 streams, payloads and milestones of `GateEvaluated`, `CommitRecorded`, `ImpactComputed`, `gate_results` and `commits`; F-13 M3 with four gates not built; F-30 commands missing from the table or the milestones; F-31 commits made by the agent and the tool allowlist; F-32 behaviour of `run`; F-34 the commit's subject and contents; F-39 output of `status` (and of `trace`, `why`, `coverage` for M5, `stats`, `report` for M7); F-9 glob syntax of `allowed_paths` and `forbidden_paths`; F-15 `RunResult` against `AgentRunFinished`, and the transcript and gate-output paths
- Spec gap (before M4 is planned), same report: F-4 `resolve` has no event, actor or input; F-16 the pytest gate's tag rule; F-33 the review gate and gate order
- Spec gap (before M5 is planned), same report: F-5 `trace_links` schema, node kinds and requirement versions; F-35 rebuilding links from trailers against the projection rule
- Spec gap (before M6 is planned), same report: F-6 replan mechanics; F-7 which states can be invalidated; F-17 impact traversal; F-18 which versions `impact` compares and where the classification lives; F-38 the classifier call; F-42 the demo has no approval of the replanned plan; task-id uniqueness against the `tasks` projection as a plan check, worded to exclude the draft being replaced (F-7 of `docs/spec-audits/2026-10-10-M2.md`)
- Spec gap (before M7 is planned), same report: F-19 eval targets cannot be computed for cases with empty ground truth; F-36 what cost per plan sums, decided with `stats` (SC-37)
