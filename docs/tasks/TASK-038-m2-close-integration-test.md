# TASK-038: M2 close integration test

- Milestone: M2
- Status: done
- Tests: integration-only (the deliverable is one integration test file over code that is already built and tested per command and per adapter; no production code is expected to change. TASK-019 is the precedent. See Open questions, item 2)
- ADR: none new. ADR-010 (accepted) puts `rebuild()` on the adapter, not the port, for tests and the close task. ADR-002 (accepted) defines an identical rebuild. ADR-011 covers `cli.py` tested through `CliRunner` on real directories. ADR-013 fixes the time of the `spec files differ` warning. ADR-005 says no test in the default run starts `claude`. ADR-012 left the real adapters under the plan use case to this test. No new port, adapter, dependency, event type, payload, storage change or convention for production code. The shared test fixture and the child-process run of the CLI are rows in `docs/decisions.md` (Open questions 3 and 4).
- Spec impact: none. Spec v1.11 settles every line, exit code, event, stream, `causation_id`, projection row and the meaning of an identical rebuild that this test asserts (see "Spec gaps": readings only).
- Spec sections (spec v1.11): "Purpose and demo scenario" (demo step 3; success criterion "Every state change can be reconstructed from the event log"); "Tech stack and repo layout" (the paragraph on planner calls and `ANTHROPIC_API_KEY`); "Spec input format" › "Validation rules" (the `deleted-requirement` bullet); "Domain model and storage" ("Projections", "Projection rules", "Streams and actors", "Event payloads", "Ids"); "Task contract" (the orchestrator's four bullets; "Planning"; "Plan checks"); "Task state machine" ("When its plan is approved ..."); "Metrics" (`tokens_in`; a retried call is a second run); "CLI commands" › "Output" (the `plan`, warning, `approve plan` and `events` bullets); "Milestones and definition of done" (milestone 2)

## Outline item
M2 outline item 13, whole and last. Closing it completes M2.

## Objective
Add one integration test that runs `plan` (with a retried planner call), `plan` again and `approve plan` through the real Typer app on a sample git repo with a stand-in `claude` first on `PATH`, and shows that the seven projection tables are identical after `SqliteEventRecorder.rebuild()` replays the log those commands wrote.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Criteria trace to spec headings.

## Scope
In:
- One new test file, `tests/integration/test_m2_close.py`, with its helpers, sample spec texts and stand-in scripts defined in the file, as in `tests/integration/test_m1_close.py` and `tests/integration/test_cli_plan.py`.
- The sample repo: a directory under `tmp_path` made with the real `git init` and `git add app/main.py` (no commit), `init` run on it, and `specs/requirements.yaml` and `specs/adrs/ADR-001-auth-method.md` written by the test. `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE` and `ANTHROPIC_API_KEY` are removed from the environment.
- The stand-in `claude`: the script of `tests/integration/test_cli_plan.py` (counts starts, keeps each prompt, replies from a list), copied into the new file. Replies are the envelope of `tests/fixtures/claude_envelope.json` with `structured_output` replaced.
- The real wiring: `ClaudeCodeLLM()`, `GitCli(Path("."))`, `SqliteEventRecorder`, `SqliteSpecVersions`, `SqlitePlans`, `SqliteRuns`, reached only through `openfactory.cli.app`.
- The rebuild is called on the adapter: `SqliteEventRecorder(<repo>/.openfactory/openfactory.db).rebuild()`.
- One check of when the `spec files differ` warning is written, with a stand-in `git` and `plan` run in a child process (AC6; Open question 3).
- `tests/conftest.py` (new): one autouse fixture that calls `structlog.reset_defaults()` after each test (Open question 4).

Out (not this task):
- Any change under `src/`. If an assertion that traces to spec text fails, that is a defect: stop and ask; do not fix it inside this task and do not weaken the test.
- A test that starts the real `claude`. It cannot run in the suite: ADR-005 ("No test in the default run starts `claude`"), and a call spends the human's subscription and is not repeatable. The one real run is a manual step (Plan step 6; Open question 1).
- Reading `is_error` or `subtype` in the adapter, or any `/spec-change` (decision of 2026-10-11).
- Cases the per-command tests already cover: every `plan` refusal on its own, a second rejected reply, a failed process, a `git` failure, the `ANTHROPIC_API_KEY` warning, the two `approve plan` refusals, the missing-init failure.
- The eight content rules one by one and the `schema` rule (unit tests, TASK-027 and TASK-028). The flow has one rejected reply, of one rule.
- A plan with no tasks (Later, TASK-032 and TASK-034).
- A `rebuild` CLI command (spec: "It is a function covered by tests, not a CLI command").
- A FastAPI target repo, a git commit in the sample repo, and anything from M3 on.
- Editing any existing test file. `tests/integration/test_cli_plan.py` keeps its own `structlog.reset_defaults()`.
- Releasing 0.2.0 (Open question 5).

## Sample repo and flow
Titles, statements and objectives are the test's choice; the ids, dependencies and counts below are fixed, because the criteria depend on them.

Spec files:
- State 1: `components: [auth]`; `REQ-AUTH-001` (`constrained_by: [ADR-001]`, criteria `AC-AUTH-001-1` and `AC-AUTH-001-2`); `REQ-AUTH-002` (criterion `AC-AUTH-002-1`); `adrs/ADR-001-auth-method.md` with `status: accepted` and a body.
- State 2: state 1 without `REQ-AUTH-002`.

Planner replies (every task has `components: [auth]`, `role: implementer`, one `allowed_paths` entry):
- R1, rejected: `AUTH-001` (`REQ-AUTH-001`, both criteria, `depends_on: [ZZZ-009]`) and `AUTH-002` (`REQ-AUTH-002`, `AC-AUTH-002-1`). Its only rejection is `unknown-dependency` on `AUTH-001`.
- R2, accepted, tasks given out of id order: `AUTH-003` (`REQ-AUTH-001`, `AC-AUTH-001-2`), `AUTH-002` (`REQ-AUTH-002`, `AC-AUTH-002-1`, `depends_on: [AUTH-001]`), `AUTH-001` (`REQ-AUTH-001`, both criteria).
- R3, accepted: `DB-001` (`REQ-AUTH-002`, `AC-AUTH-002-1`), `AUTH-002` (`REQ-AUTH-002`, `AC-AUTH-002-1`, `depends_on: [AUTH-001]`), `AUTH-001` (`REQ-AUTH-001`, both criteria, `forbidden_paths: [secrets/**]`). Its objectives differ from R2's.

The flow, called "the flow" below:
0. Setup: `git init`, `git add`, `init <repo>`, write state 1, `approve spec` (approves `sv_01`; three events).
1. `plan`, with the stand-in replying R1 then R2.
2. `plan`, with the stand-in replying R3.
3. `approve plan`.

## Acceptance criteria
"Planning" and "Plan checks" are under "Task contract"; "Projections", "Projection rules", "Streams and actors", "Event payloads" and "Ids" under "Domain model and storage"; "Output" under "CLI commands"; "Validation rules" under "Spec input format". A snapshot is every row of the seven projection tables read with `SELECT *` on a connection the test opens: `spec_versions` and `plans` ordered by `id`; `requirements` and `adrs` by `spec_version, id`; `tasks` and `agent_runs` by `id`; `task_deps` by `task_id, depends_on`.

- [x] AC1 ("Purpose and demo scenario": "`openfactory plan` produces a task DAG; the human approves the plan"; "Output": "`plan` prints one line per task as `task_id  objective`, in ascending task id as strings, then the status line `created plan_NN`, and exits 0" and "`approve plan` prints one line per task made ready as `task_id  ready`, in ascending task id as strings, then the status line `approved plan_NN`, and exits 0"; "Plan checks": "A reply rejected by Pydantic or by the plan checks is retried once with the rejections in the prompt; one `plan` makes at most two planner calls"; "Planning": "Running `plan` again while a draft plan exists records a new `PlanCreated`" and "It receives no file contents"). Steps 1 to 3 of the flow:
  - Step 1 prints the three lines `AUTH-001  <objective>`, `AUTH-002  <objective>`, `AUTH-003  <objective>` with R2's objectives, then `created plan_01`. Standard error is empty and the exit code is 0. The stand-in was started twice.
  - The second prompt the stand-in received holds the line recorded as `AgentRunFinished.error` of `run_0001`; the first prompt does not. Both hold `app/main.py`, and neither holds the content of that file.
  - Step 2 prints three task lines for `AUTH-001`, `AUTH-002`, `DB-001` with R3's objectives, then `created plan_02`. Standard error is empty, the exit code is 0, and the stand-in was started once more.
  - Step 3 prints exactly `AUTH-001  ready`, `DB-001  ready`, `approved plan_02`. Standard error is empty and the exit code is 0.
- [x] AC2 ("Streams and actors": "`plan` records `AgentRunStarted` before each planner call and `AgentRunFinished` after it; a retried call is a second pair; then `PlanCreated`. For these events `causation_id` is the `event_id` of the event recorded just before it in the same command, and the first has none" and "`approve plan` records `PlanApproved`, with no `causation_id`, then one `TaskStateChanged` per task with no dependencies, in ascending task id as strings, each pointing at `PlanApproved`", and the table rows for the five event types; "Plan checks": "a rejected reply has `exit: ok` and `error` set to its rejection lines ...; an accepted one has `error: null`"; "Event payloads": the `PlanCreated` block, "sorted by task_id as strings"; "Output": "`events` prints one stored event per line, in `seq` order"). After the flow, `events` exits 0 and prints 14 lines; the last 11 are:
  - Types in order: `AgentRunStarted`, `AgentRunFinished`, `AgentRunStarted`, `AgentRunFinished`, `PlanCreated` (step 1); `AgentRunStarted`, `AgentRunFinished`, `PlanCreated` (step 2); `PlanApproved`, `TaskStateChanged`, `TaskStateChanged` (step 3).
  - Streams in order: `run:run_0001` twice, `run:run_0002` twice, `plan:plan_01`, `run:run_0003` twice, `plan:plan_02`, `plan:plan_02`, `task:AUTH-001`, `task:DB-001`. The actor is `human` on `PlanApproved` and `orchestrator` on the other ten.
  - `causation_id` is `null` on the first line of each step's group. Within steps 1 and 2 every other line holds the `event_id` of the line before. Both `TaskStateChanged` lines hold the `event_id` of `PlanApproved`.
  - `AgentRunFinished` of `run_0001` has `exit` `ok` and an `error` of exactly one line that starts `unknown-dependency  AUTH-001  ` and names `ZZZ-009`. Those of `run_0002` and `run_0003` have `exit` `ok` and `error` null.
  - `PlanCreated` of `plan_01` has `spec_version` `sv_01`, `run_id` `run_0002` and task ids `AUTH-001`, `AUTH-002`, `AUTH-003` in that order. That of `plan_02` has `run_id` `run_0003` and task ids `AUTH-001`, `AUTH-002`, `DB-001`. Both carry the same 64-hex `policy_hash`.
  - Each `TaskStateChanged` has `from` `pending`, `to` `ready` and `reason` null.
- [x] AC3 ("Projections": the rows for `plans`, `tasks`, `task_deps` and `agent_runs`; "Planning": "The projector marks the earlier draft `superseded` and removes its tasks from `tasks` and `task_deps` ... The new draft may reuse their ids"; "Task contract": the four bullets that start "sets `forbidden_paths` to the baseline paths ..." and "The completed contract is what `PlanCreated` and `tasks.contract` hold"; "Task state machine": "a task with no dependencies moves to `ready`. A task with dependencies stays `pending`"; "Event payloads": "`context_hash` ... for a planner or classifier run, the SHA-256 of the prompt text encoded as UTF-8"; "Metrics": "`tokens_in` is every input token the runtime reports: uncached, written to the cache and read from it"). After the flow, read on a connection the test opens:
  - `plans` holds (`plan_01`, `sv_01`, `superseded`) and (`plan_02`, `sv_01`, `approved`).
  - `tasks` holds exactly `AUTH-001` (`ready`), `AUTH-002` (`pending`) and `DB-001` (`ready`), all with `plan_id` `plan_02` and `attempt` 0; there is no `AUTH-003`. `task_deps` holds exactly (`AUTH-002`, `AUTH-001`).
  - The stored contract of `AUTH-001` has `required_gates` `[path_check, ruff, pytest, gitleaks, review]`, `limits` 1200, 2 and 1.5, and `forbidden_paths` `[specs/**, .openfactory/**, .env, .env.*, secrets/**]`.
  - `agent_runs` holds `run_0001`, `run_0002`, `run_0003`, each with a null `task_id`, role `planner`, runtime `claude-code`, exit `ok`, and non-null `started_at` and `ended_at`.
  - Each run's `model`, `tokens_out`, `cost_usd` and `duration_s` equal the fixture envelope's single `modelUsage` key, `usage.output_tokens`, `total_cost_usd` and `duration_ms / 1000`. Its `tokens_in` equals the sum of the fixture's three input counts. The test reads the expected values from the fixture file.
  - Each run's `context_hash` equals the SHA-256 of the bytes the stand-in read on standard input for that start.
  - `projection_state` is the single row (`1`, the highest `seq` in `events`).
- [x] AC4 ("Milestones and definition of done", milestone 2: "the plan, task and agent run projections"; "Projection rules": "Rebuilding means emptying the projection tables ..., replaying all events in `seq` order, and setting `last_seq` to the highest `seq`", "A rebuild is identical when, for every projection table, the rows read in primary-key order are equal before and after" and "M2 `plans`, `tasks`, `task_deps`, `agent_runs`"; "Domain model and storage": "The `events` table is the source of truth; every other table is a projection rebuilt from it"). After the flow, the test takes a snapshot, then deletes every row of the seven projection tables on its own connection and commits:
  - Before the rebuild the snapshot is empty for all seven tables, so it differs from the first one (the comparison is not vacuous).
  - After `SqliteEventRecorder(<db>).rebuild()`, the snapshot equals the one taken before the delete, table by table.
  - `projection_state` is still the single row (`1`, the highest `seq`), and the rows of `events` are the same as before the rebuild.
- [x] AC5 ("Purpose and demo scenario": "Every state change can be reconstructed from the event log"; "Validation rules": "No requirement is deleted while tasks still reference it ... There is one violation per deleted requirement; its message lists the ids of the tasks that reference it, in ascending order as strings"; "Planning": "It fails if an approved plan exists, for any spec version"; "Output": "`plan_NN is already approved; use replan`" and "a `plan` refused by one of them writes no warning"). After the delete and rebuild of AC4, with the spec files changed to state 2, the commands run on the rebuilt projections:
  - `validate` prints one line that starts `deleted-requirement  REQ-AUTH-002  ` and ends `AUTH-002, DB-001`, then `1 violations, 0 policy problems`, and exits 1. The events it adds are exactly `SpecImported` then `SpecValidated`, both on `spec:sv_02`.
  - `plan` then writes exactly `plan_02 is already approved; use replan` to standard error, prints nothing on standard output and exits 1. The stand-in is not started and no event is added.
- [x] AC6 ("Output": "When the spec files differ from the latest approved version, or cannot be loaded, `plan` writes the warning `spec files differ from approved sv_NN` to standard error and carries on; the warning does not change the exit code. The warning is written after the first three refusals have been checked and before `git ls-files` runs"). On a second sample repo after step 0, with one statement in `requirements.yaml` edited:
  - A stand-in `git` is put first on `PATH`. It copies what the command's standard-error file holds at that moment to a record file, prints `app/main.py` ended by NUL and exits 0.
  - `plan` runs in a child process with its standard error redirected to that file (Open question 3).
  - The record file holds exactly the line `spec files differ from approved sv_01`: the warning was already written when `git` started.
  - The child exits 0, its standard output ends with `created plan_01`, and its standard error holds that one line and nothing else.

## Architecture rules that apply
- No module under `src/` changes. The test imports `openfactory.cli.app` and `SqliteEventRecorder` only; `rebuild()` is reached on the adapter class because it is not on the `EventRecorder` port (ADR-010).
- "All state changes go through the events table. Never write projections directly" is a rule for production code. The `DELETE` in AC4 is test-side damage to disposable tables on a temporary database (decisions row of 2026-10-10, TASK-019); the test never writes the `events` table.
- The recorder's catch-up applies nothing when the test opens it for AC4, because `last_seq` already equals the highest `seq`; only `rebuild()` refills the tables. The recorder is closed before the commands of AC5 run.
- All LLM calls go through `claude -p`: the test puts a stand-in named `claude` first on `PATH` and leaves `ClaudeCodeLLM()` as wired. No test starts the real `claude`. `ANTHROPIC_API_KEY` is removed, not read.
- The suite already needs the real `git` (TASK-030); this test starts it for `git init`, `git add` and, in the flow, `git ls-files -z`.
- Tests are fixed once written: no existing test file is edited.
- OpenFactory's own tests carry no `req` markers.
- No hardening beyond the spec's rules.

## Plan
1. Create branch `task/TASK-038-m2-close-integration-test` from an up-to-date main.
2. Get the human's answers to the Open questions; record them here and as rows in `docs/decisions.md`.
3. Add `tests/conftest.py` with the autouse `structlog.reset_defaults()` fixture (if Open question 4 is answered as proposed) and run the whole suite: it must pass unchanged.
4. Write `tests/integration/test_m2_close.py`:
   - The spec texts for states 1 and 2, and the replies R1 to R3.
   - The stand-in `claude` script and its `Claude` helper, as in `test_cli_plan.py`.
   - A `flow` helper that makes the repo and runs steps 0 to 3, returning each step's result.
   - `query`, `snapshot`, `empty_projections` and `rebuild` helpers in the shape of `test_m1_close.py`, over seven tables.
   - For AC6: the stand-in `git` script and a helper that runs `plan` in a child process.
   - One test or more per criterion; each runs on its own `tmp_path`. A module-level autouse fixture puts the stand-in on `PATH` and removes the four environment variables.
5. Run the new file. It is expected to pass without any change under `src/`. AC4's first bullet is the check that the rebuild comparison can fail. For AC6, show once by hand that the record file is empty when the stand-in runs before any warning could be written (for example with the statement not edited), and say so in the Outcome. If an assertion that traces to spec text fails, stop and report the defect with the spec text it breaks.
6. Manual step, outside the suite (Open question 1): the human runs `openfactory plan` once against the real `claude` in a scratch repo with an approved spec, and gives the session the outcome line, the exit code and, from `openfactory events`, the two run events. The session records them in the Outcome. The session does not start `claude` itself.
7. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until green.
8. Update the living docs and the Outcome. Commit `test(cli): add the M2 close integration test` with trailers `Task: TASK-038` and `Milestone: M2`.

## Files expected to change
- `tests/integration/test_m2_close.py` (new, about 330 lines)
- `tests/conftest.py` (new, about 12 lines; Open question 4)
- `docs/progress.md` (Current, Done, the M2 outline becomes empty, the M2 box ticked per Open question 1, Later lines per the section below)
- `docs/decisions.md` (rows for the answered open questions)
- `docs/tasks/TASK-038-m2-close-integration-test.md` (this record; Outcome at close)

Not expected to change: everything under `src/`, every existing test file, `tests/fixtures/claude_envelope.json`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, `docs/architecture.md` (no component or data flow changes), `CHANGELOG.md` and `README.md` (nothing a user sees changes).

Expected size: about 340 lines, almost all of it the test file. That is above the 300-line aim. `test_m1_close.py` is 318 lines, and this file adds two stand-in scripts. AC6 is about 45 of those lines (Open question 3).

## Living docs to update
- `docs/progress.md`: Current, M2 outline, Done, the M2 milestone box, and the Later lines taken here.
- `docs/decisions.md`: rows for the open questions.
- `docs/architecture.md`, `CHANGELOG.md`, `README.md`: no change expected.

## New dependencies
None.

## Spec gaps
Spec impact is "none". Nothing is missing for this task.

Readings, not gaps:
- "A sample repo" is a real git repository made with `git init` and one added file, because `plan` runs `git ls-files`. No commit is needed: `git ls-files` lists a file that is added and not committed (TASK-030).
- An identical rebuild is tested from emptied tables, over all seven projection tables, which is inside the spec's definition ("emptying the projection tables ... replaying all events").
- The spec gives the exact message text of no plan rule and no validation rule. AC2 and AC5 assert the rule, the subject and the ids the spec says the message names; the retry prompt is compared with the recorded `error` text, not with a literal.
- The values in `agent_runs` come from the stand-in's envelope, which is the pinned fixture. Which envelope fields the adapter reads is ADR-005's and TASK-029's, not the spec's.
- Milestone 2 lists "contract validation, cycle check, unknown-requirement check". Each is covered rule by rule in unit tests; the close test shows one rejection travelling through the real adapters, which is what a close adds.

## Later lines in `docs/progress.md`: taken or left
Lines that name the M2 close:
- The timing of the `spec files differ` warning against a stand-in `git` (TASK-034, reviewer): taken, as AC6. ADR-013 says only the command's integration test can hold the order, and no test today can tell the warning written before `git ls-files` from one written after. Remove the line at close. If Open question 3 is answered with the alternative: left, and the line is reworded to drop "the M2 close test".
- Observing exit status and `is_error` at the first real `plan` run (TASK-029, reviewer; TASK-031), and what `claude` prints on a non-zero exit (TASK-029, advisor): not taken by a test, because a test against the real `claude` cannot run in the suite. Taken as the manual step, Plan step 6, if Open question 1 is answered as proposed. A successful run shows the exit status and the recorded run of a good call; it does not produce an error envelope or a non-zero exit, so both lines stay, reworded from "the M2 close" to "the first real run that fails". No adapter change and no `/spec-change` either way.
- The shared structlog reset fixture (TASK-034, planner and advisor): taken, as `tests/conftest.py` (Open question 4). The new file runs five commands through `CliRunner`, each of which configures structlog on a stream that is gone when the invocation ends. Remove the line at close.
- The retried-then-accepted path through the command (TASK-032 follow-up; TASK-034 "Out"): taken, AC1 and AC2.
- The real adapters under `run_planner` (decisions row of 2026-10-11, TASK-032): taken, AC2 and AC3.

Lines left, with the reason:
- A plan with no tasks (TASK-032, TASK-034): left; the spec does not decide it.
- `approve_plan` records its events in separate transactions (TASK-035): left; "before M3 is planned".
- A started run with no finish (TASK-032): left; "before M7 is planned".
- `GitCli` and `GIT_DIR` in the caller's environment, `warning:` lines, names that are not UTF-8 (TASK-030): left; the test removes the variables and uses ASCII names.
- The stored `from_` key (TASK-021): left.
- The eight "Spec wording" lines on "Plan checks", "Tech stack and repo layout", "Planning" and "Event payloads": left for a `/spec-change` by the human; none changes what this test asserts.
- F-1 (catch-up failure output), the test names that no longer match, the two ADR amendments: left.

## Open questions
None is a spec decision. Each has a proposal and an alternative.

1. **The first real `plan` run, and whether it gates the M2 tick.** No test or record shows that `plan` has ever run against the real `claude` with the `PlannerReply` schema; the fixture was captured with a toy schema. Proposed: the human runs `plan` once by hand in a scratch repo before the close (one planner call on the subscription), the session records the outcome in the Outcome, and M2 is ticked only if that run ends in `created plan_NN` or in an outcome the spec describes. A defect it shows goes under "Blockers" and is fixed in its own task. Alternative: tick M2 on the green suite alone and leave the real run to M3, with the Later lines reworded to say so.
2. **Tests field and the "confirm it fails" step.** Proposed: `Tests: integration-only`, as TASK-019. The session writes the one test file itself. "Confirm it fails" is replaced by AC4's first bullet and the one hand check of AC6 in Plan step 5. The session may fix a mechanical error in its own test, and stops to ask when an assertion that traces to spec text fails. Alternative: `Tests: acceptance` with the test-writer, where nothing can fail first because no code is missing.
3. **The warning's timing (AC6) and how the CLI is run for it.** Under `CliRunner` standard error is held in memory, so a stand-in `git` cannot see it. Proposed: take AC6 and run `plan` in a child process, `[sys.executable, "-c", "from openfactory.cli import app; app()", "plan"]`, with standard error redirected to a file whose path the stand-in `git` knows. It is the suite's first child-process run of the CLI; a decisions row. Alternative: leave the timing check out (five criteria, about 45 fewer lines) and keep the Later line. A variant of the proposal is the installed `openfactory` script next to `sys.executable`, which depends on `uv sync` having put it there.
4. **The shared structlog reset.** Proposed: `tests/conftest.py` with one autouse fixture that calls `structlog.reset_defaults()` after every test. The repo has no `conftest.py` today. `test_cli_plan.py` is not edited, and its own reset becomes redundant and harmless. Alternative: the new file resets structlog in its own fixture, as `test_cli_plan.py` does, and the Later line stays.
5. **What closing M2 changes in the docs.** Proposed, as for M1 (decisions row of 2026-10-10): this task ticks `[x] M2 Planner` in `docs/progress.md` (subject to question 1), leaves "Milestone: M2" under Current, and leaves cutting the `0.2.0` section of `CHANGELOG.md` to the human. Alternative: the task also moves Current to M3. The "Spec gap (before M3 is planned)" lines in Later would then need a `/spec-change` round before the next `/next-task`.

## Answers (the human, 2026-10-12: "do as the advisor say")
1. The advisor's answer, not the proposal: the human runs `openfactory plan` once by hand against the real `claude` in a scratch repo with an approved spec and gives the session the outcome line, the exit code, the two run events and `claude --version` (the fixture is pinned to 2.1.287). The session ticks M2 only on `created plan_NN` with an `AgentRunFinished` of `exit: ok`; any other outcome is recorded and the human says whether it ticks. The run may cost two planner calls. The session never starts `claude` itself.
2. As proposed: `Tests: integration-only`; the session writes the test file; AC4's first bullet and one hand check for AC6 replace "confirm it fails".
3. As proposed, with the advisor's two points: the `-c` form of the child process, and the stand-in `git` on the child's `PATH` only, so the setup's real `git init` and `git add` are untouched. The source of AC6 is the spec's "Output" sentence; ADR-013 does not name the warning's timing.
4. As proposed: `tests/conftest.py` with one autouse fixture.
5. As proposed, with the advisor's sentence: tick `[x] M2 Planner`, leave "Milestone: M2" under Current, leave the `0.2.0` changelog section to the human. If the real run is pending or fails when the task is ready to commit, the task commits with the box unticked and a Blockers line, and the tick is a later docs-only change.

## Outcome
<!-- filled at close: what was built, deviations from plan, follow-ups -->
Built:
- `tests/integration/test_m2_close.py`: six tests, one per criterion, each on its own `tmp_path`, with the stand-in `claude` first on `PATH` and the real adapters reached only through `openfactory.cli.app`. All six pass with no change under `src/`.
- `tests/conftest.py`: the autouse `reset_structlog` fixture. The whole suite passes unchanged with it (1003 tests).

Checks that the tests can fail:
- AC4: the snapshot of the emptied tables is asserted empty and different from the first one before the rebuild, and every one of the seven tables is asserted non-empty before the delete (reviewer's note, applied on the human's word).
- AC6, by hand, once: with the statement not edited (so no warning is due), the record file the stand-in `git` writes is empty and the test fails on `[] == ['spec files differ from approved sv_01']`.

Deviations from the plan:
- Size: the test file is 527 lines, not about 330. The six tests assert every bullet of the criteria, and `ruff format` puts the expected lists one item per line.
- The stand-in `claude` is a shorter script than the one in `test_cli_plan.py`: it only counts starts, keeps each prompt and prints a reply, since the flow has no failing process.

The real `plan` run (answer 1): pending when this was written. M2 is not ticked; `docs/progress.md` has a Blockers line for it.

Checks: 1003 tests pass, ruff, pyright and `check_docs` clean.
