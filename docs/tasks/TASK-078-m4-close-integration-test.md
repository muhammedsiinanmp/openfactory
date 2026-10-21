# TASK-078: M4 close integration test

- Milestone: M4
- Status: done
- Tests: integration-only. The deliverable is one integration test file over code that is already built and tested per command, use case and adapter. No production code is expected to change. TASK-019, TASK-038 and TASK-057 are the precedents. See Open question 4.
- ADR: none. Existing ADRs cover this task:
  - ADR-015 (accepted): gates, retry, `resolve`, `status`, cost. Its Consequences say "the M3 close test, which passes a task on `path_check` alone, is rewritten".
  - ADR-014: run ports.
  - ADR-010: `rebuild()` lives on the adapter.
  - ADR-002: what an identical rebuild means.
  - ADR-011: `cli.py` is driven through `CliRunner`.
  - ADR-005: no test starts `claude`.
  - The task adds no port, adapter, dependency, event type, payload, storage change or production convention. The stand-in `uv` technique gets a row in `docs/decisions.md`.
- Spec impact: none. Every behaviour asserted is settled by spec v1.16 and by earlier `docs/decisions.md` rows (failure-report form and "a retry after `resolve`" from TASK-074, the `resolve` usage text from TASK-076). See "Spec gaps".
- Spec sections (spec v1.16):
  - "Milestones and definition of done", item 4: "**Gates and remediation.** `status`, `resolve`; ruff, pytest with req markers, gitleaks, reviewer; retry with failure context; escalation; the cost limit."
  - "Execution": "`run`", "Per-task sequence", "Events of one task", "Restart", "The context pack" (failure report).
  - "Gates and remediation": the gate table, "Order", "Running a gate that starts a process", "The pytest gate and `req` markers", "The review gate", "Remediation", and the gate output file paragraph.
  - "Task state machine".
  - "Domain model and storage" › "Projection rules": the `attempt` rule, rebuilding, identical rebuild, and "M4 the column `tasks.cost_usd`".
  - "Metrics": "the sum of `cost_usd` over the task's finished runs since its last retry by `resolve`".
  - "CLI commands" › "Output": the `run`, `status` and `resolve` bullets.

## Outline item
This is M4 outline item 13, the whole item and the last one. It depends on items 11 (TASK-075, TASK-076) and 12 (TASK-077), both done. Closing it completes M4, subject to Open question 3.

## Objective
Add `tests/integration/test_m4_close.py`. Through the real Typer app and the real adapters, on a sample git repo with a stand-in `claude`, `uv` and `gitleaks` first on `PATH`, it covers:
- a `run` with all five gates, a retry with its failure report, an attempts-exhausted escalation and a secret escalation;
- `resolve --retry` followed by a passing `run`;
- `status`;
- the nine projection tables, found identical after `SqliteEventRecorder.rebuild()`.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- **New test file.** `tests/integration/test_m4_close.py` holds its own helpers, spec texts and stand-in scripts, as `test_m3_close.py` does. It reuses `tests/fixtures/claude_envelope.json` and `tests/fixtures/claude_agent_envelope.json`.
- **The sample repo.** Built as in `test_m3_close.py`:
  - real `git init`, `app/main.py` committed, local `user.name`, `user.email` and `commit.gpgsign false`;
  - the same environment variables removed;
  - `init`, `specs/requirements.yaml` and one ADR, then `approve spec`, `plan` and `approve plan`;
  - the default policy (`max_attempts: 2`, `max_cost_usd: 1.50`).
- **Stand-in `claude`.** One script plays three roles:
  - planner when `--json-schema` is among its arguments;
  - reviewer when its standard input holds `## Staged diff`, always replying `approve`;
  - implementer otherwise. It takes the task id from its working directory's name and its attempt number from its own start log.
  - Every start appends one JSON line: role, working directory, the SHA-256 of standard input, and whether standard input holds `## Failure report of the previous attempt`. It also saves standard input to a file named by start number, so the test can read the pack.
- **Stand-in `uv`** (Open question 1). `#!/bin/sh`, `shift` drops `run`, then `exec <sys.executable> -m "$@"`. The gates therefore run the real `ruff` and the real `pytest`, with the real `openfactory_req` plugin and the real tag rule, as `make_exec_uv` does in `test_process_gates_pytest.py`.
- **Stand-in `gitleaks`.** In its working directory it runs `git diff --cached`. If the diff holds a fixed marker string (for example `SECRET_TOKEN=`), it prints one line and exits 3; otherwise it exits 0.
- **Real wiring.** `GitCli`, `GitWorktree`, `ClaudeCodeExecutor`, `ClaudeCodeLLM`, `ProcessGates` and `FilesystemRunFiles`, reached only through `openfactory.cli.app`.

Out:
- Any change under `src/`. If an assertion that traces to spec text fails, that is a defect: stop and report it with the spec text it breaks. Do not fix it here.
- Any edit to `tests/integration/test_m3_close.py`, or to any other existing test (Open question 2).
- The cost limit end to end. Unit tests cover it (TASK-071), and outline item 13 does not name it (Open question 5).
- `resolve --abandon` end to end. `test_cli_resolve.py` covers it.
- A kill-and-restart flow. The M3 close test covers it.
- A test that starts the real `claude`, `uv` or `gitleaks`.
- Releasing 0.4.0.

## Sample plan and flow
The ids, dependencies, paths and per-attempt behaviour below are fixed, because the criteria depend on them. Objectives, statements and summaries are the test's choice.

Spec: `components: [auth]`. `REQ-AUTH-001` has criteria `AC-AUTH-001-1` and `AC-AUTH-001-2` and is constrained by `ADR-001`, which is accepted.

Every task has `components: [auth]`, `role: implementer`, `allowed_paths: [app/, tests/]` and `requirements: [REQ-AUTH-001]`. Every test the stand-in writes is self-contained and imports nothing from `app`.

| Task | Depends on | Implementer, per start for that task |
| --- | --- | --- |
| `AUTH-001` | none | Start 1: `app/login.py` with an unused import (ruff F401), plus `tests/test_login.py` tagged `req("REQ-AUTH-001")`. Start 2: the same files, clean and formatted. |
| `AUTH-002` | `AUTH-001` | Starts 1 and 2: `app/otp.py` and `tests/test_otp.py` with no `req` marker, so the tag rule fails. Start 3: the test is tagged. |
| `AUTH-003` | none | Start 1: `app/config.py` holding the marker string, plus a tagged test. |

Run ids: the planner is `run_0001`.

**First `run`** (expected, from "`run`" and "Remediation"):
1. `AUTH-001` start 1 is `run_0002`. `ruff` fails, so the task goes `failed`, then `ready`, and is taken again.
2. `AUTH-001` start 2 is `run_0003`, with reviewer `run_0004`. The task passes, and `AUTH-002` is promoted.
3. `AUTH-002` start 1 is `run_0005`. `pytest` fails, so the task goes `failed`, then `ready`.
4. `AUTH-002` start 2 is `run_0006`. `pytest` fails again, so the task goes `failed`, then `escalated` with reason `attempts exhausted`.
5. `AUTH-003` is `run_0007`. `gitleaks` exits 3, so the task goes `failed`, then `escalated`, both with reason `secret found`.

**Then** `resolve AUTH-002 --retry`, then a second `run`. `AUTH-002` start 3 is `run_0008`, with reviewer `run_0009`, and passes. Then `status`.

## Acceptance criteria
A snapshot is every row of the nine projection tables, read as in `test_m3_close.py`.

- [ ] **AC1** ("CLI commands" › "Output", the `run` bullet: "one line per task it took ... in the order it first took them ... a task taken again after a failure still has one line ... exits 0 when every task it took passed, otherwise 1"; "Execution" › "`run`": "A task that a failure moved back to `ready` ... is taken again in the same invocation"; "Remediation"). First `run`:
  - It prints exactly `AUTH-001  passed`, `AUTH-002  escalated`, `AUTH-003  escalated`.
  - Standard error is empty and the exit code is 1.
  - The implementer starts, in order, are `AUTH-001`, `AUTH-001`, `AUTH-002`, `AUTH-002`, `AUTH-003`. Each standard-input hash equals its `AgentRunStarted.context_hash`.
  - The reviewer started once.
- [ ] **AC2** ("Gates and remediation": the gate table, "Order", "Running a gate that starts a process", "The pytest gate and `req` markers", "The review gate", and "The file is `.openfactory/runs/<run id>/<gate>.txt`"). After the first `run`, `gate_results` holds exactly:
  - `run_0002`: `path_check`, `ruff` (failed), `pytest`, `gitleaks`, and no `review`;
  - `run_0003`: all five passed;
  - `run_0005` and `run_0006`: `pytest` failed;
  - `run_0007`: `gitleaks` failed, and no `review`.

  The gate files:
  - `run_0002/ruff.txt` names `F401` and starts with the line `$ uv run ruff check`.
  - `run_0005/pytest.txt` ends with `no tagged test in a changed file: REQ-AUTH-001`.
  - `run_0003/review.txt` starts with `verdict: approve`.

  Commits:
  - `commits` has one row, for `AUTH-001` with `run_id` `run_0003`.
  - `openfactory/AUTH-001` is one commit above the initial commit, and its `Agent-Run` trailer is `run_0003`.
- [ ] **AC3** ("Events of one task"; "Remediation": "moves the task `failed` to `ready`, reason null, pointing at the `failed` event"; "attempts exhausted"; "secret found"; the failure report in "The context pack" and "Remediation"; decisions of 2026-10-21, TASK-074). First `run`:
  - **`AUTH-001`:** `gating` to `failed` with reason `ruff`, then `failed` to `ready` (null reason, causation the `failed` event), then a `ready` to `running` pointing at that `ready` event.
  - **`AUTH-002`:** two `gating` to `failed` with reason `pytest`. After the first comes `failed` to `ready`. After the second comes `failed` to `escalated` with reason `attempts exhausted`.
  - **`AUTH-003`:** `gating` to `failed`, then `failed` to `escalated`, both with reason `secret found`.
  - Every event has actor `orchestrator`.
  - **Packs.** The pack of `AUTH-001` start 2 holds `reason: ruff` and a `<gate name="ruff">` block naming `F401`. The packs of the first starts of each task hold no failure report.
  - **`tasks` rows:**

    | Task | State | `attempt` | `cost_usd` |
    | --- | --- | --- | --- |
    | `AUTH-001` | `passed` | 2 | sum of `agent_runs.cost_usd` of `run_0002` to `run_0004` |
    | `AUTH-002` | `escalated` | 2 | sum over its runs |
    | `AUTH-003` | `escalated` | 1 | sum over its runs |
- [ ] **AC4** ("CLI commands" › "Output", the `resolve` bullet; "Projection rules"; "Metrics": "since its last retry by `resolve`"; "The context pack"; "Base and branches"). After the first `run`:
  - **`resolve AUTH-002 --retry`** prints exactly `AUTH-002  ready` and exits 0. It records `TaskResolved` (actor `human`), then `escalated` to `ready` pointing at it. The `AUTH-002` row then has `attempt` 0 and `cost_usd` 0.
  - **The second `run`** prints exactly `AUTH-002  passed` and exits 0. `AUTH-003` stays `escalated` and its implementer is not started again.
  - **`AUTH-002` start 3:** its pack holds `reason: pytest` and the tag-rule line.
  - **`AUTH-002` row:** `attempt` 1, and `cost_usd` equal to the sum of `run_0008` and `run_0009` only.
  - **Commit:** `openfactory/AUTH-002`'s parent is `openfactory/AUTH-001`'s tip. Exactly one commit carries the trailer `Task: AUTH-002`.
- [ ] **AC5** ("CLI commands" › "Output", the `status` bullet). After the second `run`, `status` prints exactly the lines below, records no event, and exits 0 with standard error empty:
  - `AUTH-001  passed  2/2  review passed`
  - `AUTH-002  passed  1/2  review passed`
  - `AUTH-003  escalated  1/2  gitleaks failed`
- [ ] **AC6** ("Projection rules": rebuilding, the identical-rebuild definition, "M4 the column `tasks.cost_usd`"; "Purpose" success criterion "Every state change can be reconstructed from the event log"). Applied after the first `run` and again after `status`:
  - The snapshot of the nine tables is non-empty.
  - Emptying the tables gives a different snapshot.
  - After `rebuild()`, the snapshot equals the first, `tasks.cost_usd` and `attempt` included.
  - `projection_state` is (`1`, highest `seq`), and `events` is unchanged.
  - The full suite, `test_m3_close.py` included, passes with no existing test edited.

## Architecture rules that apply
- No module under `src/` changes. The test imports only `openfactory.cli.app` and `SqliteEventRecorder` (for `rebuild()`).
- The `DELETE` of AC6 is test-side damage to disposable tables (decisions row of 2026-10-10). The test never writes `events`.
- All LLM calls go through `claude -p`, here a stand-in. `ANTHROPIC_API_KEY` is removed, not read.

## Plan
1. Create branch `task/TASK-078-m4-close-integration-test` from an up-to-date main.
2. Get the human's answers to the Open questions. Record them here, and the stand-in `uv` row in `docs/decisions.md`.
3. Write `tests/integration/test_m4_close.py`:
   - spec texts and the plan reply;
   - the three stand-ins and the start log;
   - `setup`, `query`, `snapshot`, `empty_projections`, `rebuild` and git read helpers.
   - One flow fixture runs the whole sequence once per module, keeping a snapshot at each checkpoint (Design choice 2).
4. Run the file. It is expected to pass with no `src/` change. As a hand check, make the `AUTH-001` start 2 implementer still write F401, watch AC1 and AC3 fail, then restore the file. Say so in the Outcome.
5. Manual step, per Open question 3.
6. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
7. Update the docs:
   - `docs/progress.md`: Current; a Done line; the M4 outline emptied; the M4 box per Open question 3; the Later lines below.
   - `docs/decisions.md`: the rows for the answers.
   - Fill in the Outcome.
8. Commit `test(cli): add the M4 close integration test` with the trailers `Task: TASK-078` and `Milestone: M4`. Do not push.

## Files expected to change
- `tests/integration/test_m4_close.py` (new, about 450 to 500 lines; see Open question 4)
- `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-078-m4-close-integration-test.md` (this record)

Not expected to change: anything under `src/`, every existing test file (`test_m3_close.py` included), the fixtures, `pyproject.toml`, `docs/adr/`, `docs/spec/`, `docs/architecture.md`, `CHANGELOG.md`, `README.md`.

## Later lines in `docs/progress.md`: taken or left
Taken:
- "The stand-in `gitleaks` and the stand-in `uv` in `tests/integration/test_m3_close.py` always exit 0 ... revisit at M4 outline item 13" (TASK-067, TASK-068). Here the stand-in `gitleaks` reports a finding and the stand-in `uv` runs the real `ruff` and `pytest`. `test_m3_close.py` keeps its own stand-ins (Open question 2). Reword the line at close.

Left:
- "`process_gates` passes the caller's environment to `uv`, `VIRTUAL_ENV` included ... look at it at the M4 close or the first real run" (TASK-060). A stand-in `uv` cannot show it. It goes to the manual run (Open question 3), or stays.
- The connector and user-config observation from the real M3 run (TASK-057). It is not a test matter.

## Design choices to confirm at planning
1. **Pass and fail are driven by real gate output.** `ruff` F401, an untagged test, and a `gitleaks` marker are used instead of a stand-in that prints a chosen exit code. This is what ties AC2's file texts to the real tools and the real plugin.
2. **One flow per module.** A module-scoped fixture (`tmp_path_factory`, `pytest.MonkeyPatch.context()`) runs the flow once, because each attempt starts real `ruff` and `pytest` processes. TASK-057 re-ran its setup per test. The alternative is per-test setup, which is slower (about 6 times the gate processes).

## Open questions
None of these is a spec decision. Each has a proposal and an alternative.

Answered 2026-10-21: the human approved the plan with every proposal as written (advisor: 5 AGREE).

1. **Stand-in `uv`.**
   - Proposed: exec `sys.executable -m <tool>`, so the real `ruff`, `pytest` and `openfactory_req` run. Precedent: `make_exec_uv` in `test_process_gates_pytest.py`.
   - Alternative: a scripted stand-in that writes chosen exit codes and marker lines, as in `test_m3_close.py`. It is simpler, but it never exercises the real tag rule or real tool output.
2. **"The M3 close test that passes a task on `path_check` alone is rewritten"** (outline item 13; ADR-015 Consequences).
   - Since the approved edits of TASK-068 and TASK-070, `test_m3_close.py` no longer passes any task on `path_check` alone. Its passed tasks record all five `GateEvaluated` and a reviewer run, and its `gate_results` rows include `ruff`, `pytest`, `gitleaks` and `review`.
   - Proposed: count the rewrite as done by those two tasks, leave the file unchanged, and say so in the Outcome.
   - Alternative: the human names a further rewrite, for example switching it to the exec stand-in `uv`. That is a non-mechanical edit to a fixed test and needs approval.
3. **A real run before ticking M4.** Nothing has run `ruff`, `pytest` or `gitleaks` against a real uv project with the real `claude`.
   - Proposed, as for M3: the human runs `openfactory run` once on a scratch uv project (ruff and pytest as dev dependencies, the SC-116 `.gitignore`, gitleaks 8.30 or later) with a one-task approved plan.
   - M4 is ticked only on `<task>  passed` with all five gates passed. Any other outcome is recorded, and the human decides.
   - Note `VIRTUAL_ENV` handling while doing it.
   - If the run is still pending at commit time, the box stays unticked with a Blockers line.
   - Alternative: tick on the green suite alone.
4. **Size and Tests field.** About 450 to 500 lines, against the ~300 aim. TASK-057 was 548 lines, approved as one task.
   - Proposed: one task, `integration-only`, written by the session. "Confirm it fails" is covered by AC6's emptied-snapshot check and the hand check in Plan step 4.
   - Alternative: split it.
     - TASK-078 would be the first `run` (AC1 to AC3, and AC6 after it), about 330 lines.
     - TASK-079 would be `resolve`, the second `run`, `status` and the final rebuild (AC4, AC5, AC6), about 200 lines, with the helpers copied over.
5. **Cost limit end to end.**
   - Proposed: out. TASK-071 unit-tests it, and outline item 13 does not name it.
   - Alternative: give `AUTH-003` a stand-in envelope over `1.50` instead of the secret, to show the `cost limit` escalation. The `gitleaks` finding path would then go untested end to end.

## Spec gaps
None.

These are readings, not gaps:
- The failure report after `resolve --retry` carries the reason of the last `failed` event (`pytest`), not `attempts exhausted`, which is on a `failed` to `escalated` event. This was decided 2026-10-21 (TASK-074).
- The second `run` exits 0 with `AUTH-003` still `escalated`, because it took only `AUTH-002` ("exits 0 when every task it took passed").
- The first event of `AUTH-002` in the second `run` has no `causation_id`: it is the first event of the task in that command, and the repair touched it not.
- The sample repo is not a uv project. The stand-in `uv` stands in for "the target repo's environment" ("Target repo"), which `run` does not check.

## Outcome
- `tests/integration/test_m4_close.py` added (607 lines, 7 tests: AC1 to AC5, and AC6 parametrized over the two checkpoints). It passed on its first full run with no change under `src/`, so it found no defect.
- Deviation from "Sample plan and flow": `AUTH-002` carries `AC-AUTH-001-2` and the other two tasks `AC-AUTH-001-1`. The plan check refuses a plan that leaves a criterion uncovered ("uncovered"), as in `test_m3_close.py`.
- The sample repo commits a `.gitignore` covering `.venv`, `__pycache__/`, `.pytest_cache/` and `.ruff_cache/`, as "Target repo" asks.
- The flow fixture removes `PYTEST_ADDOPTS`, `PYTHONPATH` and `VIRTUAL_ENV` so the outer pytest run does not leak into the gates' pytest.
- Hand check: with `AUTH-001` start 2 still writing the F401 import, all 7 tests failed (AC1: `AUTH-001  escalated`; AC3: an extra `failed` to `escalated`; AC6: `commits` empty). The file was then restored and passes.
- Open question 2: `test_m3_close.py` is unchanged. TASK-068 and TASK-070 already did the rewrite that ADR-015 asks for.
- Open question 3: the real `openfactory run` by the human is pending, so the M4 box stays unticked with a Blockers line.
- No existing test was edited. The full suite (1595 tests), ruff, pyright and check_docs pass.
