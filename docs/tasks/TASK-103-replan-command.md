# TASK-103: `replan` command

- Milestone: M6
- Status: done
- Tests: acceptance
- ADR: ADR-019 (accepted, with its 2026-10-24 amendment), ADR-013 (accepted) and ADR-011 (accepted).
  - ADR-019 covers replan.
  - ADR-013 is the two-call pattern, so the warning can be printed between the two calls.
  - ADR-011 makes `cli.py` the composition root.
  - The task only wires `prepare_replan` and `create_replan` (TASK-102) to adapters `cli.py` already builds: `_open_adapters`, `SqliteEventStore` (as `run` opens it), `FilesystemSpecFiles`, `GitCli` and `ClaudeCodeLLM`. It then formats the result.
  - It adds no port, adapter, event type, payload or schema change, dependency or convention, so no new ADR is needed. Design choices 1 to 3 become one row each in `docs/decisions.md`.
- Spec impact: none (see Spec gaps: readings only, nothing missing)
- Spec sections (spec v1.19; SC-163, SC-174, SC-197):
  - "CLI commands", table row: "`openfactory replan` | Plans new tasks for the impacted work; `approve plan` invalidates the impacted tasks".
  - "CLI commands" › "Output", the `replan` bullet: "`replan` prints as `plan` does, its rejection output included. It refuses with one line on standard error and exits 1, checked in this order: `no approved plan`; `run openfactory impact first` when no `ImpactComputed` has the approved plan's spec version as `from_version` and the latest approved version as `to_version`; `nothing to replan` when the latest such event lists no task and no `added` requirement; `policy is invalid; run openfactory validate`; `git ls-files failed: <error>`; `planner call failed: <error>`. The first three come before any event. It writes `plan`'s warning `spec files differ from approved sv_NN` after its first four refusals have been checked and before `git ls-files` runs."
  - "CLI commands" › "Output", the `plan` bullets that "prints as `plan` does" points to:
    - "`plan` prints one line per task as `task_id  objective`, in ascending task id as strings, then the status line `created plan_NN`, and exits 0. When the second reply is rejected it prints that reply's rejections as `rule  subject  message`, sorted as violation lines are, on standard output, and exits 1."
    - "`<error>` is the first line of the failure's text; for a planner call that text is `AgentRunFinished.error`."
  - "Spec diff and impact analysis" › "Step 5: replan": "It makes the planner call as `plan` does and records the same events, then `PlanCreated` of a draft plan for the latest approved version that holds only the new tasks. It invalidates nothing. Running `replan` again supersedes the draft, as for `plan`."
  - "CLI commands" › "Output": "Command results (… status lines; task and rejection lines …) go to standard output. Failure messages (… the refusals of … `replan` …), warnings and log lines go to standard error"; "A command that fails exits 1".
  - "CLI commands" › "Other commands": "fail with "run `openfactory init` first" if `./.openfactory/` is missing."

## Outline item
This is M6 outline item 6c in `docs/progress.md`.
- It depends on TASK-102 (6b, `app/replan.py`, done) and TASK-101 (6a, the replan prompt, done).
- It follows the split between use case and command that TASK-095 and TASK-096 used for `impact`.
- Item 7 (`approve plan` after a replan) comes next.

## Objective
`openfactory replan` calls `prepare_replan`. It writes the `spec files differ` warning when it applies, then calls `create_replan`, and prints the result exactly as `plan` does. Each refusal writes its one line to standard error and exits 1.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/cli.py`:
  - **New `_replan_refusal_line(refused: ReplanRefused) -> str`.** It maps `ReplanRefusal` to the four lines below and ends in `assert_never`:
    - `no approved plan`
    - `run openfactory impact first`
    - `nothing to replan`
    - `policy is invalid; run openfactory validate`
  - **New `_prepare_and_create_replan(database) -> ReplanRefused | PlannerResult`.** It mirrors `_prepare_and_create_plan`:
    1. Under `_open_adapters(database)` plus `closing(SqliteEventStore(database))`, it calls `prepare_replan(FilesystemSpecFiles(POLICIES.parent), adapters.versions, adapters.plans, store)`.
    2. On a refusal it returns that refusal.
    3. When `inputs.spec_files_differ`, it writes `spec files differ from approved {inputs.spec_version}` to standard error.
    4. It then calls `create_replan(inputs, git=GitCli(Path(".")), llm=ClaudeCodeLLM(), runs=adapters.runs, plans=adapters.plans, recorder=adapters.recorder)`.
  - **New top-level `replan` command, with no arguments.** It calls `require_init()`, then the helper above. A `ReplanRefused` gives its line on standard error and exit 1. Otherwise it prints the `PlannerResult` as `plan` does (Design choice 1).
  - **New shared `_print_planner_result(result: PlannerResult) -> None`** (Design choice 1). It holds the four branches that `plan` has today:
    - `git ls-files failed: <first line>`, exit 1
    - `planner call failed: <first line>`, exit 1
    - the rejection lines on standard output, exit 1
    - the task lines, then `created plan_NN`

    `plan` calls it with no change to what it prints.
- New `tests/integration/test_cli_replan.py`:
  - **Driver and seeding.** It drives the Typer app with `CliRunner` in a `tmp_path` git repo. It seeds events through `SqliteEventRecorder`, as `test_cli_impact.py` does:
    - approved `sv_01` and `sv_02`;
    - an approved `sv_01` plan with an untouched `passed` task, an impacted `passed` task and a downstream `pending` task;
    - one `ImpactComputed` on `spec:sv_02` with `from_version` `sv_01`.

    It writes spec files matching `sv_02` and a valid `specs/policies.yaml`.
  - **Stand-ins.** It copies the stand-in `claude` (a replies file and a start counter) and `fake_git` from `tests/integration/test_cli_plan.py`. They are copied, not imported, so no existing test changes.

Out:
- Any change under `app/`, `domain/`, `ports/` or `adapters/`, and any change to `_Adapters` or `_open_adapters`.
- `approve plan` after a replan: the impact read, the invalidations, the readies and the `run openfactory replan` refusal text (item 7).
- The M6 close integration test (item 8).
- The open Later spec gaps (a second replan omits invalidated ids; no deletion-only task; F-16 cost per plan). They stay open.

## Acceptance criteria
- [x] **AC1** ("Output", `replan`: "prints as `plan` does"; `plan`: "one line per task as `task_id  objective`, in ascending task id as strings, then the status line `created plan_NN`, and exits 0"; "Step 5": "records the same events, then `PlanCreated` of a draft plan for the latest approved version that holds only the new tasks. It invalidates nothing"):
  - The stand-in returns a valid reply with two new tasks, given out of id order. One task depends on the untouched `passed` task.
  - Standard output is exactly the two `task_id  objective` lines in ascending id, then `created plan_02`. Standard error is empty and the exit code is 0.
  - The events added are exactly `AgentRunStarted`, `AgentRunFinished` (role `planner`) and `PlanCreated`. That `PlanCreated` is for `sv_02` and holds only the two new tasks. No `TaskStateChanged` is added, and the seeded tasks keep their states.
- [x] **AC2** ("Step 5": "Running `replan` again supersedes the draft, as for `plan`"; "Output", `plan`: "When the second reply is rejected it prints that reply's rejections as `rule  subject  message`, sorted as violation lines are, on standard output, and exits 1"):
  - After AC1's run, a second `replan` with a valid reply prints `created plan_03` and exits 0. The `plans` projection then shows `plan_02` superseded and `plan_03` as the draft.
  - Two rejected replies, the second with at least two rejection lines: standard output is exactly the second reply's rejection lines, sorted. Lines found only in the first reply do not appear, and `created` does not appear. The exit code is 1. Two planner runs are recorded and no `PlanCreated` is added.
- [x] **AC3** ("Output", `replan`: the first three refusals, "The first three come before any event"; "It writes `plan`'s warning … after its first four refusals have been checked"):
  - Standard error is exactly `no approved plan` when no plan is approved.
  - It is exactly `run openfactory impact first` when the only `ImpactComputed` on `spec:sv_02` has another `from_version`, or there is none.
  - It is exactly `nothing to replan` when the latest matching event has no `tasks` and no `added` requirement.
  - Each of these cases is run with the spec files edited so that they differ from `sv_02`. In each case, standard output is empty, no warning line is written, the exit code is 1, the `events` row count is unchanged and `claude` is not started.
- [x] **AC4** ("Output", `replan`: the fourth refusal `policy is invalid; run openfactory validate`; the warning "after its first four refusals have been checked and before `git ls-files` runs"; `git ls-files failed: <error>`; `plan`: "`<error>` is the first line of the failure's text"; "the warning does not change the exit code"):
  - **Invalid policy:** with the spec files edited and an invalid `policies.yaml`, standard error is exactly `policy is invalid; run openfactory validate`. There is no warning line and the exit code is 1.
  - **Warning on success:** with the spec files edited and a valid reply, standard error is exactly `spec files differ from approved sv_02`, standard output ends with `created plan_02`, and the exit code is 0.
  - **Warning before a git failure:** with the spec files edited and `fake_git` failing with a multi-line error, standard error is exactly two lines:
    1. the warning;
    2. `git ls-files failed: <first line of the git error>`.

    The exit code is 1, `claude` is not started and the `events` row count is unchanged.
- [x] **AC5** ("Output", `replan`: `planner call failed: <error>`; `plan`: "for a planner call that text is `AgentRunFinished.error`"; "Other commands": "run `openfactory init` first"):
  - The stand-in exits non-zero with multi-line standard error. Standard error is then exactly `planner call failed: <first line of that run's AgentRunFinished.error>`, standard output is empty, the exit code is 1 and no `PlanCreated` is added.
  - Without `./.openfactory/`, `replan` writes "run `openfactory init` first" to standard error, exits 1, creates nothing and does not start `claude`.
- [x] **AC6** (CLAUDE.md "cli.py: the composition root … every other command calls one or more use cases"; ADR-011; "Output", `replan`: "prints as `plan` does"):
  - An AST check, as in `test_cli_impact.py`, shows that the `replan` path calls `prepare_replan` and `create_replan` and builds no worktree, executor or gate adapter.
  - No file under `src/openfactory/app`, `domain`, `ports` or `adapters` changes. This is a review check on the diff, as in TASK-096, not a test (see Outcome).
  - `tests/integration/test_cli_plan.py` and every other existing test pass without edits. This shows that moving `plan`'s output into `_print_planner_result` changed nothing.

## Architecture rules that apply
- `cli.py` wires, formats, prints and sets exit codes (ADR-011). The use cases return data.
- All state changes go through the recorder inside `create_replan`, and `cli.py` records nothing. `SqliteEventStore` is opened for reading only, as in `run`.
- The LLM call goes through `ClaudeCodeLLM` (`claude -p`). Its reply is validated inside the use case by `PlannerReply` and the plan checks.

## Plan
1. Create branch `task/TASK-103-replan-command` from an up-to-date main.
2. Record the human's answers to Design choices 1 to 3 and the Open questions in this record.
3. Test-writer: write failing tests `test_task103_ac<N>_...` (AC1 to AC6) in the new `tests/integration/test_cli_replan.py`, with seeded events, a stand-in `claude` on `PATH` and `fake_git`.
4. Implement `_print_planner_result` (moved out of `plan`), `_replan_refusal_line`, `_prepare_and_create_replan` and the `replan` command in `cli.py`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Update the docs:
   - `docs/architecture.md`, CLI section:
     - a `replan` bullet;
     - `replan` added to the `require_init()` list and the `_open_adapters` list;
     - `plan`'s bullet noting `_print_planner_result`.
   - `docs/architecture.md`, "Replan use case" section: replace "(6c, not yet written)" with the caller.
   - `docs/progress.md`: Current, a Done line, and item 6c marked done.
   - `docs/decisions.md`: one row per Design choice.
   - This record's Outcome.
7. Commit `feat(cli): add the replan command` with the trailers `Task: TASK-103` and `Milestone: M6`. Do not push.

## Files expected to change
- `src/openfactory/cli.py` (about +45, of which about 15 move out of `plan`)
- `tests/integration/test_cli_replan.py` (new, about +300)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`, `CHANGELOG.md` (added in review: an `[Unreleased]` line for `replan`)
- `docs/tasks/TASK-103-replan-command.md`

Not expected to change: `app/`, `domain/`, `ports/`, `adapters/`, any existing test, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

Expected size: about 345 lines, about 45 of them in `src/`. That is a little over the ~300 target, almost all of it integration test, the same shape as TASK-096.

## Design choices to confirm at planning
1. **Sharing `plan`'s output.**
   - Proposed: move `plan`'s four result branches into `_print_planner_result(result)` and call it from both `plan` and `replan`. "Prints as `plan` does" then holds by construction, and `test_cli_plan.py` guards the move.
   - Alternative: copy the roughly 15 lines into `replan`. This leaves `plan` untouched but adds a second copy that can drift.
2. **Opening the event store.**
   - Proposed: open `closing(SqliteEventStore(database))` next to `_open_adapters`, as `run` does, and pass it to `prepare_replan` (TASK-102 reads `ImpactComputed` through `EventStore`).
   - Alternative: add the store to `_Adapters`. That touches every command's wiring for one caller.
3. **Refusal-line mapping.**
   - Proposed: a separate `_replan_refusal_line` with `assert_never`, as `_run_refusal_line` has.
   - Alternative: widen `plan`'s `_refusal_line` to a union. That mixes two enums for no gain.

## Open questions
1. Do you accept Design choices 1 to 3 as proposed? In particular, should `plan`'s output move into a shared `_print_planner_result` (choice 1)?
2. Size: about 345 lines with the test, a little over target. Keep it as one task, as TASK-096 did? Or drop AC2's second-`replan` supersede bullet? That bullet re-checks projector behaviour from M2, but it is the only CLI-level check of "Running `replan` again supersedes the draft".

## Answers (human, 2026-10-24)
1. Design choices 1 to 3 accepted as proposed.
2. Kept as one task, with AC2's supersede bullet.

## Spec gaps
None blocking; Spec impact is none. These are readings, not gaps:
1. **`<error>` for `replan`.** "Prints as `plan` does" carries over `plan`'s definition of `<error>`: the first line of the failure's text, `AgentRunFinished.error` for a planner call. The `replan` bullet does not restate it.
2. **An empty accepted reply.** A reply `{"tasks": []}` that `uncovered` accepts (SC-188, TASK-102 AC4) prints only `created plan_NN`. That follows from `plan`'s "one line per task". It is not in the acceptance criteria because the use case already tests it.
3. **The warning's version.** `sv_NN` in the warning is the latest approved version (`ReplanInputs.spec_version`), the version the draft is made for.
4. **Events before the fourth refusal.** "The first three come before any event" does not say that the policy refusal also records nothing. `prepare_replan` records nothing anyway, so AC4 does not assert either way on that case's events.

## Outcome
`openfactory replan` is in `src/openfactory/cli.py`: `replan`, `_prepare_and_create_replan` and `_replan_refusal_line`. `plan`'s result printing moved into the shared `_print_planner_result`. Design choices 1 to 3 were implemented as accepted and are rows in `docs/decisions.md`.
- New `tests/integration/test_cli_replan.py`: 13 tests covering AC1 to AC6.
- Full suite 2050 passed (2051 before the deletion below); ruff, pyright and check_docs clean.
- One test-writer test deleted after the PR's CI run, with the human's approval (2026-10-24): `test_task103_ac6_no_inner_layer_file_changes` ran `git diff --name-only main` over the four inner layers. CI checks out no local `main` (`fatal: bad revision 'main'`), and the test checked the branch diff, not behaviour: always empty once merged, and failing on any later branch that changes `app/`. AC6's no-inner-layer-change bullet is a review check; the reviewer verified it from the diff. No other test edits and no mechanical test fixes. Nothing under `app/`, `domain/`, `ports/` or `adapters/` changed.
- No new ADR; spec gaps unchanged.
- Size: 48 lines in `src/`, 590 in the new test file (planned ~300; the seeding and stand-in helpers are copied from `test_cli_impact.py` and `test_cli_plan.py`).
- Reviewer non-blocking notes: the record's file list now names `CHANGELOG.md`; an event-count check on the AC4 policy refusal was not added (spec gap reading 4 leaves it open); the AC5 `PlanCreated` check was left as written.
