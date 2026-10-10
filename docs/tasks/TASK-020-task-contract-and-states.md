# TASK-020: Task contract models and the task state machine

- Milestone: M2
- Status: done
- Tests: acceptance
- ADR: none new. ADR-008 (accepted) covers the split this task encodes: `PlannedTask` has neither `required_gates` nor `limits`, and `Limits` has three required fields with no defaults. ADR-007 (accepted), with its 2026-10-11 amendment, covers the closed sets the models hold (a task's `role` and `required_gates`, the task states): widened only. No new port, adapter, dependency, event type, payload or storage change. Module and type names are rows in `docs/decisions.md` (Open questions 1 to 3).
- Spec impact: none. Spec v1.10 gives the three models as a class block, the nine states as a list and `TRANSITIONS` as a code block; this task mirrors them.
- Spec sections (spec v1.10): "Task contract" (the YAML example, the class block, the paragraph after it); "Task state machine"; "Domain model and storage" ("Event payloads": the closed-sets sentence); "Tech stack and repo layout"

## Objective
Add the pure domain models `PlannedTask`, `Limits` and `TaskContract`, and the task state machine (the nine states and `TRANSITIONS`), exactly as spec v1.10 gives them, so the M2 payload, projector, contract-completion and plan-check tasks build on one validated shape.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Acceptance criteria trace to spec headings instead.

## Scope
In:
- A new pure module `src/openfactory/domain/contracts.py` with `PlannedTask`, `Limits` and `TaskContract(PlannedTask)`, field for field as the spec's class block (Open question 1 for the module name).
- A new pure module `src/openfactory/domain/states.py` (the name the spec's layout gives) with `TaskState`, the nine states, and `TRANSITIONS` (Open question 2 for the types).
- Unit tests that build the models from Python dicts. No files, no database, no LLM.
- Three tests added to `tests/unit/test_spec_conformance.py` that parse the spec's contract example, state list and `TRANSITIONS` block and compare them with the code (Open question 4).

Out (later outline items, not this task):
- Payload models for `PlanCreated`, `PlanApproved`, `TaskStateChanged`, `AgentRunStarted`, `AgentRunFinished`, any change to `PAYLOAD_MODELS`, and a stored-event fixture per closed value (outline item 2; audit finding F-9).
- The projector tables `plans`, `tasks`, `task_deps`, `agent_runs`, and the initial state `pending` set by `PlanCreated` (item 3).
- Contract completion: merging forbidden paths, a constant for the fixed gate list, limits from the policy, the policy hash (item 5). This task only defines the shapes; `Policy` and `BASELINE_FORBIDDEN_PATHS` are not touched.
- Plan checks, including turning `pydantic.ValidationError` into `schema` rejections and their subjects (item 6; audit finding F-3 belongs there).
- A transition-checking function or any enforcement of `TRANSITIONS`. No M2 text asks for one: payload models check shape only (ADR-007) and the projector does not check event sequences (ADR-009). `TRANSITIONS` is data here.
- The run roles (`planner`, `implementer`, `reviewer`, `classifier`) and `exit` values: they belong to the run payloads (item 2).
- Glob syntax of `allowed_paths` and `forbidden_paths` (Later, F-9 of the 2026-10-09 report); entries are plain strings.
- Checks across fields or tasks: a `depends_on` entry's form, duplicates inside a list, a task depending on itself.
- Hardening against exotic inputs: numeric strings, booleans or `NaN` where a number is expected, empty strings in lists, an empty `objective`.
- Any change to `domain/models.py`, `domain/policy.py`, `domain/payloads.py`, `domain/events.py`, and every existing test other than the three added conformance tests.

## Acceptance criteria
Each criterion cites the spec v1.10 text it traces to. "Class block" means the Python block under "Task contract" that defines `PlannedTask`, `Limits` and `TaskContract`. "The example contract" means the YAML block under "Task contract" that starts `task_id: AUTH-002`, as a dict. "The planned example" is the example contract without `required_gates` and `limits`. Names follow the proposed answers to Open questions 1 and 2; if the human answers otherwise, the names change and the assertions do not.

- [x] AC1 ("Task contract": the YAML example; the class block, "`class TaskContract(PlannedTask)`: What is stored and executed"; "The completed contract is what `PlanCreated` and `tasks.contract` hold"; "Tech stack and repo layout": "`domain/ # pure models, state machine, rules; no I/O`" and "the domain never imports infrastructure"):
  - `TaskContract` validates from the example contract, and each field equals the example's value; `limits` is a `Limits`.
  - `model_dump(mode="json")` of the result equals the example contract, with every list in the example's order.
  - `TaskContract.model_validate_json(contract.model_dump_json())` equals the original.
  - `TaskContract` is a subclass of `PlannedTask`.
  - `openfactory.domain.contracts` and `openfactory.domain.states` import nothing from `openfactory.adapters`, `openfactory.app` or `openfactory.ports` (checked by parsing imports with `ast`).
- [x] AC2 ("Task contract": "The planner LLM emits tasks in the shape of `PlannedTask`"; the class block's `PlannedTask` fields, `depends_on: list[str] = []`, `forbidden_paths: list[str] = []`, `Field(min_length=1)`; "Planning": "The planner replies with `{"tasks": [PlannedTask, ...]}`"):
  - `PlannedTask` validates from the planned example.
  - Without `depends_on` and `forbidden_paths` it validates, and both are `[]`.
  - Leaving out any one of `task_id`, `objective`, `requirements`, `acceptance_criteria`, `components`, `role` or `allowed_paths` raises `pydantic.ValidationError`.
  - An empty list for `requirements`, `acceptance_criteria` or `allowed_paths` raises it; an empty `components` list is accepted.
- [x] AC3 ("Task contract": the class block, "`task_id: str = Field(pattern=r"^[A-Z]+-\d{3}$")`" and "`role: Literal["implementer"]`"):
  - `task_id` accepts `AUTH-002` and `A-000`.
  - `task_id` rejects `auth-002`, `AUTH-02`, `AUTH-0020`, `AUTH002` and the empty string.
  - `role` accepts `implementer` and rejects `reviewer` and `planner`.
  - The same holds on `TaskContract`.
- [x] AC4 ("Task contract": "The planner does not emit `required_gates` or `limits`; a reply that contains either fails validation" and "`model_config = ConfigDict(extra="forbid")`"; the YAML example's comment "set by the orchestrator, never by the planner"):
  - The planned example plus `required_gates` raises `pydantic.ValidationError` on `PlannedTask`.
  - So does the planned example plus `limits`, and the planned example plus an unknown key (for example `priority`).
  - On `TaskContract`, the example contract plus an unknown key raises it.
  - On `TaskContract`, the example contract without `required_gates`, or without `limits`, raises it.
- [x] AC5 ("Task contract": the class block's `Limits`, "`max_runtime_s: int = Field(gt=0)`", "`max_attempts: int = Field(gt=0)`", "`max_cost_usd: float = Field(gt=0)`", and "`required_gates: list[Literal["path_check", "ruff", "pytest", "gitleaks", "review"]]`"; "Event payloads": "the lists inside a contract keep their order"):
  - `Limits` validates from `{max_runtime_s: 1200, max_attempts: 2, max_cost_usd: 1.50}`.
  - Each of the three fields at `0`, and at a negative value, raises `pydantic.ValidationError`.
  - Leaving out any one of the three raises it, as does an unknown key.
  - `required_gates` accepts the five names and keeps the order given; a name outside the five (for example `semgrep`) raises it.
- [x] AC6 ("Task state machine": "A task has nine states", the list of nine names, and the `TRANSITIONS` block; "Planning": "`invalidated` is a terminal state"; "Event payloads": the closed sets "and the task states"; "Tech stack and repo layout": "`states.py # task state machine + allowed transitions`"):
  - `openfactory.domain.states` has exactly the nine states `pending`, `ready`, `running`, `gating`, `passed`, `failed`, `escalated`, `abandoned`, `invalidated`.
  - `TRANSITIONS` equals the spec's dict when compared with plain strings and sets.
  - Its keys are exactly the nine states, every target is one of the nine, and `invalidated` and `abandoned` have no targets.
  - In `tests/unit/test_spec_conformance.py`, parsed from the spec file itself: the state names in the list under "Task state machine" equal the code's states; the spec's `TRANSITIONS` block equals the code's `TRANSITIONS`; the spec's YAML contract example validates as `TaskContract` and dumps back equal to it.

## Architecture rules that apply
- `src/openfactory/domain` stays pure: both modules hold Pydantic models, an enum and a constant only, with no I/O and no import from `adapters`, `app` or `ports`.
- "All LLM output is validated by a Pydantic model before use": `PlannedTask` is that model for the planner's reply. The call and the retry are later tasks.
- The closed sets in these models (`role`, `required_gates`, the task states) reach stored payloads through `PlanCreated` and `TaskStateChanged`. From the first stored event they may be widened but never renamed or narrowed (ADR-007 amendment).
- The planner cannot set gates or limits (ADR-008): `PlannedTask` has neither field and forbids unknown ones.
- No event is recorded, no projection is written, no LLM call is made.

## Plan
1. Create branch `task/TASK-020-task-contract-and-states` from an up-to-date main.
2. Get the human's answers to Open questions 1 to 4; record them here and as rows in `docs/decisions.md`.
3. Write failing tests:
   - `tests/unit/test_contracts.py` for AC1 to AC5.
   - `tests/unit/test_task_states.py` for AC6's first three bullets.
   - Three tests added to `tests/unit/test_spec_conformance.py` for AC6's last bullet, using the file's `code()`, `code_block()` and section-parsing style.
   - By that file's convention the conformance tests skip, not fail, until the code exists. The two new files are the failing tests.
   - Suggested markers: `code_block("task_id: AUTH-002")` and `code_block("TRANSITIONS = {")`. Check that each matches exactly one block. The dict can be read with `ast.literal_eval` on the text after `TRANSITIONS = `, which accepts `set()`.
   - No existing test is changed.
4. Add `src/openfactory/domain/contracts.py`: the three models as in the class block, with `model_config` per Open question 3. `TaskContract` adds only `required_gates` and `limits`, with no defaults.
5. Add `src/openfactory/domain/states.py`: `TaskState` with the nine members in the spec's list order, and `TRANSITIONS` as in the spec's block.
6. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
7. Update the living docs and this record's Outcome. Commit with subject `feat(domain): add the task contract models and the task state machine` and trailers `Task: TASK-020` and `Milestone: M2`.

## Files expected to change
- `src/openfactory/domain/contracts.py` (new, about 40 lines)
- `src/openfactory/domain/states.py` (new, about 30 lines)
- `tests/unit/test_contracts.py` (new)
- `tests/unit/test_task_states.py` (new)
- `tests/unit/test_spec_conformance.py` (three tests added; nothing existing changed)
- `docs/architecture.md`, `docs/progress.md`, `docs/decisions.md`
- `docs/tasks/TASK-020-task-contract-and-states.md` (this record; Outcome at close)

Not expected to change: every other module under `src/`, `pyproject.toml`, `docs/adr/`, `docs/spec/`, and every other existing test file.

## Living docs to update
- `docs/architecture.md`: Components gains "Task contract models" and "Task state machine". Data flow gets one sentence at most, since nothing uses them yet.
- `docs/progress.md`: Current, then Done; remove item 1 from the M2 outline and point the "depends on 1" of items 2, 5 and 6 at TASK-020.
- `docs/decisions.md`: rows for the answered open questions.
- `CHANGELOG.md` and `README.md`: no change (nothing a user sees).

## New dependencies
None.

## Spec gaps
None. Three readings to record; none is a gap and no test depends on them beyond the spec's own words.
- The sentence "Any task not currently running can be invalidated by a spec change" disagrees with the `TRANSITIONS` block for `gating` and `abandoned`. This is the known finding F-7 of the 2026-10-09 report, already under Later in `docs/progress.md` (before M6). It does not block: this task mirrors the code block, and no criterion asserts the sentence.
- The layout comment "`models.py # Requirement, Task, AgentRun, Gate, ...`" is an example by the spec's own words ("the modules below are examples, not the full list"), so the module that holds the contract models is a decision row (Open question 1).
- The widen-only rule for closed sets is a rule for future changes, kept by review (audit finding F-9). Nothing here tests it.

## Open questions
All four answered by the human on 2026-10-11, each as proposed.
1. **Module for the contract models.** A new `domain/contracts.py`; the state machine in `domain/states.py`.
2. **Types of the states and of `TRANSITIONS`.** `TaskState(StrEnum)` with the nine members in the spec's list order, and `TRANSITIONS: dict[TaskState, frozenset[TaskState]]`. The target sets are immutable; the outer dict is a plain dict. No transition-checking function.
3. **Frozen models.** `ConfigDict(frozen=True, extra="forbid")` on `PlannedTask` and `Limits`, inherited by `TaskContract`. The spec's class block shows `extra="forbid"` only; `frozen` is an addition the human allowed.
4. **Conformance tests in this task.** Yes: three tests added to `tests/unit/test_spec_conformance.py`. They skip until the code exists, so the fail-first step rests on the two new test files.

The human also confirmed that this task mirrors the spec's `TRANSITIONS` block where the sentence "Any task not currently running can be invalidated by a spec change" disagrees with it (F-7, under Later before M6).

## Outcome
**Built**
- `src/openfactory/domain/contracts.py`: `PlannedTask`, `Limits` and `TaskContract(PlannedTask)`, field for field as the spec v1.10 class block, with `ConfigDict(frozen=True, extra="forbid")`. `TaskContract` adds only `required_gates` and `limits`, with no defaults.
- `src/openfactory/domain/states.py`: `TaskState(StrEnum)` with the nine states in the spec's list order, and `TRANSITIONS: dict[TaskState, frozenset[TaskState]]` as the spec's block. `TRANSITIONS` is data; nothing enforces it.
- Tests: `tests/unit/test_contracts.py` (AC1 to AC5), `tests/unit/test_task_states.py` (AC6) and three tests added to `tests/unit/test_spec_conformance.py` (state list, `TRANSITIONS` block, YAML contract example). 651 tests pass with none skipped; ruff, pyright and check_docs are clean.

**Deviations from the plan**
- Test fix after the test-writer staged its files: in `tests/unit/test_contracts.py`, `test_ac3_task_id_accepts` and `test_ac3_role_accepts_implementer` passed the full contract example (`EXAMPLE`, with `required_gates` and `limits`) to `PlannedTask`, which AC4 requires `PlannedTask` to reject. They now pass `EXAMPLE` to `TaskContract` and `PLANNED` to `PlannedTask`, as the sibling `..._rejects` tests already did. The assertions' intent is unchanged.
- The three conformance tests in `tests/unit/test_spec_conformance.py` skipped before the code existed, by that file's convention, and run now.

**Follow-ups**
- None beyond the M2 outline. F-7 (the sentence on invalidating a task not currently running against `TRANSITIONS`) stays under Later before M6.
