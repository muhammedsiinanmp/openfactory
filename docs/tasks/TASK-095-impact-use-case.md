# TASK-095: `impact` use case

- Milestone: M6
- Status: done
- Tests: acceptance
- ADR: ADR-019 (accepted). Its "`ImpactComputed`", "Classifier" and "Ports" bullets cover the work: `impact` compares the approved plan's spec version with the latest approved one, makes at most one classifier call with one retry, and records `ImpactComputed` on `spec:<to_version>`, actor `orchestrator`. "No new port: `Traces` gains the traversal … the diff reads `SpecVersions`, the classifier goes through `LLMProvider`." The task adds one `app` module and no port, adapter, event type, payload change, table, dependency or convention. Its design choices become rows in `docs/decisions.md`.
- Spec impact: wording (see Spec gaps). Neither item blocks on the spec's text, but Open question 2 is on the human's own deadline.
- Spec sections (spec v1.18; SC-160, SC-161, SC-174, SC-177):
  - "Spec diff and impact analysis", opening: "`openfactory impact` compares two approved spec versions: `from`, the spec version of the approved plan, and `to`, the latest approved version."
  - "Step 2: change classification (LLM, validated)": "When some requirement is `modified`, `impact` makes one classifier call, set up as a planner call … and recorded as an agent run with role `classifier` and no task." Also: "A criterion of a modified requirement that is absent from `to` is always obsolete …"
  - "Classifier checks", last paragraph: "A rejected reply is retried once, and its `AgentRunFinished` is recorded, as for a planner reply. A second rejected reply or a failed process makes `impact` write `classifier call failed: <error>` … with `<error>` the first line of the last classifier run's `AgentRunFinished.error`, record no `ImpactComputed`, and exit 1."
  - "Step 3: traversal (deterministic)": "The seeds are the requirements whose change is `removed` or `deprecated`, and the `modified` ones classified `behavioral` or `replacement`."
  - "Step 4: impact report": "`impact` records the classifier's run events when it made a call, then `ImpactComputed` … Each `impact` records a new `ImpactComputed`."
  - "Domain model and storage" › "Event payloads": the `ImpactComputed` block (`run_id`: "the classifier run whose reply was accepted; null when no call was made"; `requirements`: "each requirement that is not unchanged, sorted by id"; `adrs`: "each ADR that is not unchanged, sorted by id"), and the paragraph after it.
  - "Domain model and storage" › "Streams and actors": "`ImpactComputed` | `spec:<to_version>` | `orchestrator`"; "`impact` and `replan` record their events as `plan` does: each points at the event recorded just before it in the same command, and the first has none."
  - "CLI commands" › "Output", `impact`: "It refuses with one line on standard error and exits 1, before any event: `no approved plan`; `no spec change since sv_NN` when the approved plan's spec version is the latest approved one."

## Outline item
M6 outline item 3, first half (3a). The second half (3b, proposed TASK-096) is the `impact` command in `cli.py`: the `requirement`, `adr`, `task`, `downstream`, `file`, `test`, `obsolete` and `new-work` lines, the `impact sv_NN..sv_NN` status line, the refusal lines and `classifier call failed: <first line>`, plus `tests/integration/test_cli_impact.py`. This follows the TASK-075/076 split. Plan step 6 updates the outline.

## Objective
A new `app/impact.py` with `compute_impact`. It does three things:
- refuses when there is no approved plan or no spec change;
- otherwise diffs the two stored spec sets and makes the classifier call with its single retry when a requirement is `modified`;
- runs the traversal from the seeds, records `ImpactComputed` and returns its payload, or returns the classifier failure.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In:
- New `src/openfactory/app/impact.py`:
  - `ImpactRefusal` (`no_approved_plan`, `no_spec_change`);
  - frozen `ImpactResult` (`refusal`, `detail` (the `sv_NN` for `no_spec_change`), `impact: ImpactComputedPayload | None`, `error: str | None`), as in Design choice 2;
  - `compute_impact(*, versions, plans, runs, traces, llm, recorder) -> ImpactResult`.
- What it uses:
  - `diff_specs`, `parse_classifier_reply`, `check_classification` and `add_lost_criteria`;
  - `rejection_lines`;
  - `build_classifier_prompt`, and `context_hash` from `app/planner_prompt.py` (TASK-093 decision);
  - `Traces.impact_traversal(plan_id, seeds)`.
- A private classifier attempt helper in `impact.py`, following `plan._attempt` (Design choice 3).
- New `tests/unit/test_impact.py`, with fakes modelled on `tests/unit/test_plan_use_case.py` (`FakeLLM`, `FakeRecorder`, `FakeRuns`, `FakePlans`) and `tests/unit/test_coverage.py` (`FakeVersions`, `FakeTraces`).

Out:
- The `impact` command, its output lines and its exit codes (3b).
- `replan`, `approve plan` after a replan, the projector move (items 4 to 7).
- Changing which requirements `diff_specs` marks `modified` (Open question 2).
- Changing `app/plan.py` or its `_attempt`.

## Acceptance criteria
- [ ] **AC1** ("CLI commands" › "Output", `impact`: "before any event: `no approved plan`; `no spec change since sv_NN` when the approved plan's spec version is the latest approved one"):
  - With no approved plan, the result's refusal is `no_approved_plan`.
  - With an approved plan whose spec version is the latest approved version, the refusal is `no_spec_change` and `detail` is that version id.
  - The two checks run in that order.
  - Neither refusal records an event or calls the LLM.
- [ ] **AC2** ("Event payloads", `ImpactComputed` and the paragraph after it; "Streams and actors"; "Step 4": "Each `impact` records a new `ImpactComputed`"):
  - With no `modified` requirement, `impact` makes no LLM call and records no run event.
  - It records exactly one `ImpactComputed`: stream `spec:<to_version>`, actor `orchestrator`, no `causation_id`.
  - `from_version` is the approved plan's spec version, `to_version` is the latest approved version, and `run_id` is null.
  - `requirements` holds each requirement of the diff that is not `unchanged`, sorted by id, with its `change`, `kind` null, `rationale` null and both lists `[]`.
  - `adrs` holds each ADR that is not `unchanged`, sorted by id, with its `change`.
  - The result's `impact` equals the recorded payload. A second call records a second `ImpactComputed`.
- [ ] **AC3** ("Step 2": "one classifier call, set up as a planner call … recorded as an agent run with role `classifier` and no task"; "Event payloads"; "Streams and actors": "as `plan` does"):
  - With some requirement `modified`, `impact` records `AgentRunStarted` with:
    - the run id from `Runs.next_id`, stream `run:<id>`;
    - role `classifier`, `task_id` null, runtime `claude-code`;
    - `context_hash` of `build_classifier_prompt(old, new, diff)`.
  - It calls `LLMProvider.complete` with that prompt and `ClassifierReply`'s JSON schema.
  - It records `AgentRunFinished` as a planner run does: exit `ok`, the reply's model, tokens, cost and duration, `error` null.
  - On an accepted reply, `ImpactComputed` has `run_id` that run, and each `modified` entry has the classifier's `kind`, `rationale` and `new_work`, with `obsolete_criteria` from `add_lost_criteria` (each id once, sorted). `new_work` follows the answer to Open question 1.
  - Each event's `causation_id` is the event recorded just before it in this call; the first has none.
- [ ] **AC4** ("Classifier checks": "A rejected reply is retried once, and its `AgentRunFinished` is recorded, as for a planner reply. A second rejected reply or a failed process … record no `ImpactComputed`"; "Plan checks": "When there is any `schema` rejection, the other checks are not run"):
  - A reply rejected by `parse_classifier_reply` or, when that passes, by `check_classification` gets an `AgentRunFinished` whose `error` is its `rejection_lines` joined by `\n`.
  - A second run follows. Its prompt has the first reply's rejections, and its `AgentRunStarted` points at the first `AgentRunFinished`.
  - If the second reply is accepted, `run_id` is the second run.
  - If the second reply is rejected, or an `LLMError` occurs, the result's `error` is the last run's `AgentRunFinished.error` (whole text) and no `ImpactComputed` is recorded.
  - An `LLMError` is not retried. Its `AgentRunFinished` has exit `timeout` or `error`, the error's `duration_s`, null metrics and `error` equal to `str(error)`.
- [ ] **AC5** ("Step 3": "The seeds are the requirements whose change is `removed` or `deprecated`, and the `modified` ones classified `behavioral` or `replacement`"; "Event payloads": `tasks`, `downstream`, `files`, `tests`):
  - `impact` calls `Traces.impact_traversal` once, with the approved plan's id and exactly those seeds. `added` and `cosmetic` requirements are not seeds.
  - The returned `tasks`, `downstream`, `files` and `tests` are the `ImpactComputed` lists unchanged.
  - With no call made, the seeds are the `removed` and `deprecated` requirements only.
  - A classifier failure calls no traversal.
- [ ] **AC6** (CLAUDE.md "app: use cases, depends on domain + ports only"; ADR-019 "No new port"):
  - `app/impact.py` imports from `openfactory` only `domain`, `ports` and `app` modules, and prints nothing.
  - No port, adapter, `cli.py`, `app/plan.py` or `domain/` file changes.
  - The existing tests pass without edits.

## Architecture rules that apply
- All state changes go through `EventRecorder.record`. `ImpactComputed` changes no projection.
- LLM output is validated by `ClassifierReply` (through `parse_classifier_reply`) before use.
- The use case returns data. 3b's `cli.py` prints the lines and sets the exit code.

## Plan
1. Create branch `task/TASK-095-impact-use-case` from an up-to-date main.
2. Record the human's answers to Design choices 1 to 3 and Open questions 1 and 2 in this record.
3. Test-writer: failing tests `test_task095_ac<N>_...` in a new `tests/unit/test_impact.py`.
   - `sv_01` vs `sv_02` spec sets, built inline:
     - REQ-AUTH-001 modified (one criterion removed);
     - REQ-AUTH-002 modified through an ADR;
     - REQ-AUTH-003 added;
     - REQ-AUTH-004 deprecated;
     - REQ-AUTH-005 removed;
     - one ADR modified.
   - A recording `FakeTraces` that returns a fixed `ImpactTraversal`.
4. Implement `app/impact.py`:
   - the refusals;
   - the spec sets read through `SpecVersions.spec_set`, asserting non-None as `prepare_plan` does;
   - `diff_specs`;
   - the classifier attempt helper, with the retry;
   - the seeds, the traversal, the payload and the record.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all pass.
6. Docs:
   - `docs/architecture.md`: a new "Impact use case" section;
   - `docs/progress.md`: Current, a Done line, item 3 split into 3a (done) and 3b, and the settled Later lines updated;
   - `docs/decisions.md`: one row per answer;
   - this record's Outcome.
7. Commit `feat(app): add the impact use case` with trailers `Task: TASK-095` and `Milestone: M6`. Do not push.

## Files expected to change
- `src/openfactory/app/impact.py` (new, about +180)
- `tests/unit/test_impact.py` (new, about +320)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`, this record

Not expected to change: `app/plan.py`, `app/classifier_prompt.py`, `app/planner_prompt.py`, `domain/`, ports, adapters, `cli.py`, `docs/spec/`, `docs/adr/`.

## Design choices to confirm at planning
1. **Split.**
   - Proposed: 3a is the use case (this task), 3b is the command and output (TASK-096), as TASK-075/076 did.
   - Alternative: one task; about 650 lines with the CLI integration test.
2. **Result shape.**
   - Proposed: frozen `ImpactResult(refusal, detail, impact, error)`, where `impact` is the recorded `ImpactComputedPayload`. 3b prints straight from it, since the spec defines the output over `ImpactComputed.requirements` and the rest.
   - Alternative: a separate report model that copies the fields.
3. **Classifier attempt helper.**
   - Proposed: a private helper in `impact.py` that mirrors `plan._attempt` with role `classifier` and the classifier parse and checks. About 60 lines repeat the planner's pattern, and `plan.py` is untouched.
   - Alternative: generalise `plan._attempt` over role, schema and checks. That changes a working use case and its tests' assumptions.

## Answers (human, 2026-10-24)
Design choices 1 to 3 and Open questions 1 and 2 are approved as proposed (advisor: 5 AGREE). Open question 1: (b), `new_work` is sorted as strings in the stored payload, like `obsolete_criteria`. Open question 2: (b), the literal reading stands for this task; the deprecated-in-both-versions Later line's deadline moves from before M6 item 3 to before M6 item 5, settled at the `/spec-change` with F-1, F-2 and F-7.

## Open questions
1. **Is `new_work` sorted in the payload?** "Event payloads": "… then they are the classifier's, with the criteria that `to` lost added to `obsolete_criteria` …, sorted as strings." It is not clear whether "sorted as strings" covers `new_work` too (Later line, TASK-092; deferred to "when M6 item 3 is planned").
   - (a) Keep the classifier's order.
   - (b) Sort as strings.
   - The printed `new-work` group is sorted either way ("each group is sorted as strings"), so only the stored order differs.
2. **A requirement deprecated in both versions with a changed hash or ADR** (Later line; deadline "before M6 item 3"). Read literally, Step 1 makes it `modified`: it reaches the classifier, `missing-requirement` demands an entry for it, and a `behavioral` or `replacement` answer makes it a seed.
   - (a) Run `/spec-change` first, together with F-1, F-2 and F-7 of `docs/spec-audits/2026-10-24-proposal-v1.18.md`. If the fix goes into Step 1, only `domain/spec_diff.py` changes, in its own small task, and this task is unchanged.
   - (b) Accept the literal reading for now. This task passes `diff_specs`' result as given, and the line stays Later.

## Spec gaps
- "Domain model and storage" › "Event payloads", the paragraph after the block, "… sorted as strings": unclear whether this covers `new_work`. Does not block: both readings give a valid payload and the same printed output (already in Later).
- "Spec diff and impact analysis" › "Step 1" (with "Step 2"): a requirement deprecated in both versions with a changed hash or ADR is `modified` read literally. Does not block on the text; a Step 1 fix does not touch this task (already in Later).
- Already recorded: F-7 is implemented as "not deprecated in `from`" by TASK-091.

## Outcome
- Added `src/openfactory/app/impact.py` (`ImpactRefusal`, `ImpactResult`, `compute_impact`, private `_attempt` and `_classify`) and `tests/unit/test_impact.py`. No port, adapter, event, dependency or `cli.py` change.
- 15 tests pass.
- One mechanical test fix: the `TRAVERSAL` fixture in `tests/unit/test_impact.py` used task ids "T-1", "T-2", "T-9", which fail the `TaskId` pattern `^[A-Z]+-\d{3}$` at collection; changed to "AUTH-001", "AUTH-002", "AUTH-009" (assertion intent unchanged), and `ruff format` rewrapped that line.
- Implementation note: `_Attempt.error` holds the `AgentRunFinished.error` text for both rejected replies and LLM failures; `compute_impact` asserts a latest approved version exists once a plan is approved.
- Docs: `docs/architecture.md` (Impact use case), `docs/progress.md` (item 3 split into 3a and 3b, Later lines updated), `docs/decisions.md` (five rows).
