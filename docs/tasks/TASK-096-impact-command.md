# TASK-096: `impact` command

- Milestone: M6
- Status: done
- Tests: acceptance
- ADR: ADR-019 (accepted) covers impact, the classifier and `ImpactComputed`; ADR-011 (accepted) makes `cli.py` the composition root. The task only wires `compute_impact` (TASK-095) to the adapters `_Adapters` already holds, plus `ClaudeCodeLLM()`, and formats its result. It adds no port, adapter, event type, payload or schema change, dependency or convention, so no new ADR. Design choices 1 to 3 go in `docs/decisions.md`, one row each.
- Spec impact: none (see Spec gaps: readings only, nothing missing)
- Spec sections (spec v1.18; SC-164, SC-174, SC-177):
  - "CLI commands" table row: "`openfactory impact` | Diffs the approved plan's spec version against the latest approved one and prints the impact report".
  - "CLI commands" › "Output", `impact`: "`impact` prints `requirement  <id>  <change>  <kind>` for each requirement of `ImpactComputed.requirements` (`<kind>` is `-` when null); then `adr  <id>  <change>`; then `task  <task id>`, `downstream  <task id>`, `file  <path>`, `test  <node id>` and `obsolete  <criterion id>` (each over all requirements, once); then `new-work  <requirement id>  <text>`; then the status line `impact sv_NN..sv_NN`, `from` then `to`; and exits 0. Fields are separated by exactly two spaces, and each group is sorted as strings. It refuses with one line on standard error and exits 1, before any event: `no approved plan`; `no spec change since sv_NN` when the approved plan's spec version is the latest approved one. A failed classifier call writes `classifier call failed: <error>` and exits 1 (see Spec diff and impact analysis)."
  - "Spec diff and impact analysis" › "Classifier checks", last paragraph: "A second rejected reply or a failed process makes `impact` write `classifier call failed: <error>` to standard error, with `<error>` the first line of the last classifier run's `AgentRunFinished.error`, record no `ImpactComputed`, and exit 1."
  - "Spec diff and impact analysis" › "Step 4: impact report": "`impact` records the classifier's run events when it made a call, then `ImpactComputed`, and prints the report (see CLI commands). Each `impact` records a new `ImpactComputed`." The example block there fixes the line forms and the order of the groups.
  - "CLI commands" › "Output": "Command results (… status lines …) go to standard output. Failure messages (… the refusals of … `impact` …) … go to standard error"; "A command that fails exits 1".
  - "CLI commands" › "Other commands": "fail with "run `openfactory init` first" if `./.openfactory/` is missing."

## Outline item
M6 outline item 3b in `docs/progress.md` (proposed TASK-096). It depends on TASK-095 (`compute_impact`, done) and TASK-094 (`Traces.impact_traversal`, done). It follows the split TASK-075/076 made between `resolve`'s use case and its command. Once this is done, item 3 is complete and item 4 (the projector supersede) is next.

## Objective
`openfactory impact` calls `compute_impact` and prints the impact report in the spec's line order with exit 0. A refusal or a failed classifier call writes one line to standard error and exits 1.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- `src/openfactory/cli.py`:
  - New top-level command `impact`, with no arguments. It calls `require_init()`, opens `_open_adapters` and calls `compute_impact(versions=adapters.versions, plans=adapters.plans, runs=adapters.runs, traces=adapters.traces, llm=ClaudeCodeLLM(), recorder=adapters.recorder)`. It prints after the adapters are closed, as `status`, `trace` and `why` do.
  - New private `_impact_refusal_line(refusal, detail) -> str`: `no approved plan`, or `no spec change since <detail>`.
  - New private `_impact_lines(impact: ImpactComputedPayload) -> list[str]`. The groups come in this order, each sorted as strings (Design choice 1):
    1. `requirement  <id>  <change>  <kind or ->`
    2. `adr  <id>  <change>`
    3. `task  <id>`
    4. `downstream  <id>`
    5. `file  <path>`
    6. `test  <node id>`
    7. `obsolete  <criterion id>`: the union over all requirements, each id once
    8. `new-work  <requirement id>  <text>`
    9. `impact <from_version>..<to_version>`
  - A classifier failure writes `classifier call failed: {_first_line(result.error)}`, reusing the existing `_first_line`.
- New `tests/integration/test_cli_impact.py`:
  - It drives the Typer app with `CliRunner` on a `tmp_path` repo.
  - It seeds events through `SqliteEventRecorder`, as `test_cli_trace.py` and `test_cli_why.py` do: two approved spec versions, an approved plan for `sv_01` with tasks, `CommitRecorded`, `TestsCollected`.
  - It puts a stand-in `claude` first on `PATH`, built the way `tests/integration/test_cli_plan.py` builds its own (a replies file and a start counter; `ANTHROPIC_API_KEY` and the `GIT_*` variables removed). The stand-in is copied into the new module, not imported, so no existing test changes.

Out:
- Any change to `app/impact.py`, `domain/`, `ports/`, `adapters/`, `_Adapters` or `_open_adapters`.
- `replan`, `approve plan` after a replan and the projector supersede (items 4 to 7).
- The Later wording items on Step 1 and Step 2 (deprecated in both versions, F-7, the kind definitions). Their deadline is before item 5.
- Validating or reformatting classifier texts (`rationale` is not printed; `new_work` is printed as stored).

## Acceptance criteria
- [ ] **AC1** ("Output", `impact`: line forms, group order, "exactly two spaces", "each group is sorted as strings", "(each over all requirements, once)"; "Step 4" example):
  - Seed `sv_01` and `sv_02` so the diff has:
    - one requirement `modified` (classified `replacement` by the stand-in, which also returns `new_work`);
    - one `added`, one `deprecated` and one `removed` requirement;
    - one `modified` ADR.
  - Seed the approved `sv_01` plan with an impacted task, a downstream task, commits and tests.
  - Standard output is exactly, in order: the `requirement` lines (`-` for the non-`modified` ones), the `adr` lines, then the `task`, `downstream`, `file`, `test`, `obsolete` and `new-work` lines, each group sorted as strings, then `impact sv_01..sv_02`.
  - One criterion id is obsolete in two requirements' lists and gets one `obsolete` line. One requirement has two `new-work` texts; they print sorted as strings (code-point order, as in the spec's example).
  - Fields are separated by exactly two spaces, with no padding. Standard error is empty and the exit code is 0.
- [ ] **AC2** ("Step 4": "records the classifier's run events when it made a call, then `ImpactComputed` … Each `impact` records a new `ImpactComputed`"):
  - After AC1's run, the event log holds `AgentRunStarted` and `AgentRunFinished` (role `classifier`), then one `ImpactComputed` on `spec:sv_02`.
  - With no `modified` requirement (only `added`, `removed` or `deprecated`), the stand-in `claude` is not started, every `requirement` line ends in `-` and there is no `obsolete` or `new-work` line. A second `impact` prints the same output, records a second `ImpactComputed` and exits 0 both times.
- [ ] **AC3** ("Output", `impact`: "It refuses with one line on standard error and exits 1, before any event: `no approved plan`; `no spec change since sv_NN` …"):
  - With an approved spec version and no approved plan, standard error is exactly `no approved plan`.
  - With an approved plan whose spec version is the latest approved one, standard error is exactly `no spec change since sv_NN` with that id.
  - In both cases standard output is empty, the exit code is 1, the `events` row count is unchanged and `claude` is not started.
- [ ] **AC4** ("Classifier checks": "A second rejected reply or a failed process makes `impact` write `classifier call failed: <error>` … the first line of the last classifier run's `AgentRunFinished.error`, record no `ImpactComputed`, and exit 1"):
  - Two rejected replies, with the second giving at least two rejection lines: standard error is exactly `classifier call failed: <first rejection line of the second reply>`, and two classifier runs are recorded.
  - A stand-in that exits non-zero with a multi-line standard error: standard error is `classifier call failed: <first line of that run's AgentRunFinished.error>`, and one run is recorded.
  - In both cases standard output is empty, the exit code is 1 and no `ImpactComputed` is recorded.
- [ ] **AC5** ("Other commands": "fail with "run `openfactory init` first""): without `./.openfactory/`, `impact` writes that line to standard error, exits 1, creates nothing and does not start `claude`.
- [ ] **AC6** (CLAUDE.md "cli.py: the composition root … every other command calls one or more use cases"; ADR-011):
  - The `impact` command calls `compute_impact` and builds no git, worktree, executor or gate adapter. This is an AST check, as in `test_cli_trace.py`.
  - No file under `src/openfactory/app`, `domain`, `ports` or `adapters` changes.
  - The existing tests pass without edits.

## Architecture rules that apply
- `cli.py` wires, formats, prints and sets exit codes (ADR-011). The use case returns data.
- All state changes go through the recorder inside `compute_impact`. `cli.py` records nothing itself.
- The LLM call goes through `ClaudeCodeLLM` (`claude -p`), and its reply is validated inside the use case.

## Plan
1. Create branch `task/TASK-096-impact-command` from an up-to-date main.
2. Record the human's answers to Design choices 1 to 3 in this record.
3. Test-writer: failing tests `test_task096_ac<N>_...` in a new `tests/integration/test_cli_impact.py` (AC1 to AC6), using seeded events and a stand-in `claude` on `PATH`.
4. Implement `_impact_refusal_line`, `_impact_lines` and the `impact` command in `cli.py`.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Docs:
   - `docs/architecture.md`:
     - an `impact` bullet in the CLI section;
     - `impact` added to the `require_init()` and `_open_adapters` lists;
     - in the "Impact use case" section, "the command is a later task" replaced with the caller.
   - `docs/progress.md`: Current, a Done line, item 3b marked done.
   - `docs/decisions.md`: one row per Design choice.
   - This record's Outcome.
7. Commit `feat(cli): add the impact command` with the trailers `Task: TASK-096` and `Milestone: M6`. Do not push.

## Files expected to change
- `src/openfactory/cli.py` (about +55)
- `tests/integration/test_cli_impact.py` (new, about +260)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-096-impact-command.md`

Not expected to change: `app/`, `domain/`, `ports/`, `adapters/`, any existing test, `pyproject.toml`, `docs/adr/`, `docs/spec/`.

Expected size: about 320 lines, about 55 of them in `src/`. That is a little over the ~300 target, almost all of it the integration test (TASK-086 had the same shape).

## Design choices to confirm at planning
1. **Sorting in `cli.py`.**
   - Proposed: `_impact_lines` sorts each group's lines as strings, with `sorted(...)`. The `obsolete` group is `sorted(set(...))` over all requirements. The payload's lists are already sorted (TASK-094, TASK-095), so the extra sort costs nothing. It is needed anyway for the `obsolete` union and the `new-work` group, which `cli.py` builds itself, and it keeps the spec's "each group is sorted as strings" true in the printing code.
   - Alternative: trust the payload's order for `task`, `downstream`, `file` and `test` (as TASK-086 choice 3 did for `why`), and sort only the groups `cli.py` builds.
2. **Formatting from the payload.**
   - Proposed: `_impact_lines` takes the `ImpactComputedPayload` from `ImpactResult.impact` (TASK-095 choice 2), since the spec defines the output over `ImpactComputed`.
   - Alternative: a separate view model in `app`. That adds a type for no gain.
3. **Classifier failure output.**
   - Proposed: only `classifier call failed: <first line>` on standard error, with nothing on standard output. Unlike `plan`, `impact` does not print the rejection lines of a second rejected reply, because the spec names only the failure line for `impact`.
   - Alternative: also print the rejections on standard output as `plan` does. The spec does not ask for it.

## Answers (human, 2026-10-24)
The human approved the plan and the proposed answer to each Design choice ("do as u would do"):
1. `_impact_lines` sorts every group in `cli.py`; `obsolete` is `sorted(set(...))`.
2. `_impact_lines` formats straight from `ImpactComputedPayload`; no view model.
3. A classifier failure prints only `classifier call failed: <first line>` on standard error; nothing on standard output.

## Open questions
None beyond the Design choices.

## Spec gaps
None blocking; Spec impact is none. Readings, not gaps:
1. "each group is sorted as strings" on whole lines gives `new-work` in requirement-id order, then text order, and `requirement` lines in id order (the two-space separator sorts before any id character). This matches the spec's example (`OTP issue endpoint`, `OTP verify endpoint`, `attempt rate limit`).
2. "(each over all requirements, once)" applies to the `task` to `obsolete` groups. The `new-work` lines print one per stored entry. Duplicate `new_work` texts from the classifier are not removed; no hardening, per CLAUDE.md.
3. The existing Later wording lines (Step 1 F-7, deprecated in both versions, the kind definitions, "sorted as strings" for `new_work`) are not touched by this task. They are due at the `/spec-change` before item 5.

## Outcome
- `cli.py` adds `impact`, `_impact_lines` and `_impact_refusal_line`; no change under `app/`, `domain/`, `ports/` or `adapters/`, and no existing test changed.
- New `tests/integration/test_cli_impact.py`: 9 tests, all passing; 1936 passed overall. No test edits were made after the test-writer.
- The test-writer used two modified requirements in AC1 and AC2 instead of one, so a criterion can be obsolete in two requirements' lists and print one `obsolete` line.
- Design choices 1 to 3 are recorded in `docs/decisions.md` (one row each).
- Docs updated: `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`. No ADR needed.
