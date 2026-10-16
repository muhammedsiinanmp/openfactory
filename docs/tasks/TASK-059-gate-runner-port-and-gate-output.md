# TASK-059: `GateRunner` port, `GateOutput` and `MarkerLine`

- Milestone: M4
- Status: done
- Tests: acceptance
- ADR: ADR-015 (accepted), "Ports and adapters (SC-84 ...)": "`GateRunner`, adapter `process_gates`: `run(gate, worktree, timeout_s) -> GateOutput`, with `passed`, `text` and, for `pytest`, the collected marker lines". ADR-016 (accepted) adds `missing_tool() -> str | None` to `GateRunner`. ADR-017 (accepted) adds `GateOutput.finding: bool`. ADR-006 (accepted) covers the layers. This task adds no adapter, dependency, event type, payload or storage change. Module names, field names and the model config go in as rows in `docs/decisions.md` (Open questions 2 to 4).
- Spec impact: wording. One item, which does not block (see "Spec gaps").
- Spec sections (spec v1.16; SC-84, SC-111, SC-121):
  - "Tech stack and repo layout": the layout block (`ports/ # interfaces: ..., GateRunner`) and "The gates that start a process (ruff, pytest, gitleaks) run behind the `GateRunner` port, whose adapter is `process_gates`".
  - "Domain model and storage", the M4 paragraph after "Ids": "`GateRunner`, whose adapter is `process_gates`, runs a gate that starts a process and names the first of `uv` and `gitleaks` missing from `PATH`".
  - "Gates and remediation" › "Running a gate that starts a process" (the port, `GateOutput`, `finding`, `missing_tool()`).
  - "Gates and remediation" › "The pytest gate and `req` markers" (the JSON line shape only).
  - "Execution" › "`run`", the `<tool> not found` refusal ("as `GateRunner.missing_tool()` gives it"). This task only gives the method its signature.

## Outline item
M4 outline item 1, first of two pieces (Open question 1). The `process_gates` adapter for `ruff` and `gitleaks`, with `missing_tool()` and the gitleaks confirmation, is left in item 1 as TASK-060.

## Objective
Give the M4 use cases the `GateRunner` port, with its result model `GateOutput`, the marker-line model and the closed set of gates that start a process. The adapter, the pytest plugin, the tag rule and the run use case can then be built against them.

## Requirement IDs
None. OpenFactory's own tests carry no `req` markers (decision of 2026-10-08).

## Scope
In (names per Open questions 2 to 4):
- `src/openfactory/domain/gates.py` (new), pure:
  - `ProcessGate = Literal["ruff", "pytest", "gitleaks"]`.
  - `MarkerLine`: frozen, `extra="forbid"`, with `file: str` and `req: list[str]`, both required.
  - `GateOutput`: frozen, `extra="forbid"`, with `passed: bool`, `text: str`, `finding: bool` and `marker_lines: list[MarkerLine]`, all required. No check across fields.
- `src/openfactory/ports/gate_runner.py` (new): Protocol `GateRunner` with two methods.
  - `run(self, gate: ProcessGate, worktree: Path, timeout_s: int) -> GateOutput`. The docstring says:
    - a failure is returned, not raised: a command that cannot start or runs past `timeout_s` fails its gate;
    - `worktree` is passed relative to the repo and the adapter resolves it against its own repo (the F-7 rule of 2026-10-13);
    - `finding` is true only when `gitleaks` exits 3;
    - `marker_lines` is empty for `ruff` and `gitleaks`.
  - `missing_tool(self) -> str | None`: the first of `uv` and `gitleaks` not on `PATH`, else `None`.
  - No exception type.
- Tests: a new unit file for the port and the models.

Out:
- The `process_gates` adapter: command lines, `uv run`, `PATH`, timeouts, the text format, exit 3, the `TYPE_CHECKING` assertion, the gitleaks 8.30.1 confirmation (TASK-060).
- The `pytest` gate's adapter half and the `openfactory_req` plugin (outline item 2).
- The tag rule (item 3) and any caller of the port, including `run_plan`'s `<tool> not found` refusal (item 7).
- Parsing a marker line from the plugin's output (item 2). This task only fixes the model's shape against the spec's line.
- Any change to `domain/payloads.py` (`GateName` stays as it is), the existing ports, adapters, `app/` and `cli.py`.
- A spec conformance test: the spec gives `GateOutput` in prose, with no code block to read.

## Acceptance criteria
- [x] **AC1** ("Running a gate that starts a process": "`GateOutput` holds `passed`, `text`, `finding` and, for `pytest`, the collected marker lines"; SC-121, ADR-017):
  - `GateOutput.model_fields` are exactly `passed`, `text`, `finding`, `marker_lines`, in that order, and all are required.
  - `passed` and `finding` are `bool`, and `text` is `str`. `marker_lines` holds `MarkerLine` values and accepts an empty list.
  - An unknown key raises `ValidationError`, and the model is frozen.
- [x] **AC2** ("The pytest gate and `req` markers": "writes one JSON line per collected test, `{"file": "<path relative to the repo>", "req": ["<id>", ...]}`"):
  - `MarkerLine.model_validate_json('{"file": "tests/test_login.py", "req": ["REQ-AUTH-001"]}')` gives `file` `tests/test_login.py` and `req` `["REQ-AUTH-001"]`.
  - `model_dump(mode="json")` returns that dict exactly.
  - `req: []` validates, for a collected test with no marker.
  - A missing field or an unknown key raises `ValidationError`, and the model is frozen.
- [x] **AC3** ("Running a gate that starts a process": "the `GateRunner` port ... has `run(gate, worktree, timeout_s) -> GateOutput`" and "`GateRunner` also gives `missing_tool() -> str | None`"; "Tech stack and repo layout", `ports/ # interfaces: ..., GateRunner`; SC-84, SC-111, ADR-016):
  - `GateRunner` is a Protocol whose public methods are exactly `run` and `missing_tool`.
  - The parameters of `run` after `self` are `gate`, `worktree`, `timeout_s`, in that order. They are annotated `ProcessGate`, `Path`, `int`, and `run` returns `GateOutput`.
  - `missing_tool` takes no parameter after `self` and returns `str | None`.
  - Read with `inspect.signature` and `typing.get_type_hints`.
- [x] **AC4** ("Tech stack and repo layout": "The gates that start a process (ruff, pytest, gitleaks) run behind the `GateRunner` port"; "Execution" › "Per-task sequence" step 4, where `path_check` is built in; "The review gate": one `LLMProvider` call):
  - `get_args(ProcessGate)` is exactly `("ruff", "pytest", "gitleaks")`.
  - Each value is in `get_args(GateName)`, so a `GateEvaluated` can record it. Neither `path_check` nor `review` is in `ProcessGate`.
- [x] **AC5** ("Tech stack and repo layout": "the domain never imports infrastructure"; ADR-006):
  - `ports/gate_runner.py` imports from `openfactory` only `openfactory.domain` modules.
  - `domain/gates.py` imports nothing from `openfactory.ports`, `openfactory.adapters` or `openfactory.app`.
  - Imports are checked by parsing with `ast`, as in `tests/unit/test_agent_executor_port.py`.

## Architecture rules that apply
- `ports` holds Protocols only and imports from `openfactory.domain` only. The models live in `domain`, as `RunResult` does in `domain/agent_run.py`.
- `domain/gates.py` is pure: no I/O.
- No adapter is added, so there is no `TYPE_CHECKING` assertion in this task.
- No event is recorded and no projection is read or written. `cli.py` and `app/` are not changed.
- No new dependency and no `req` markers. No hardening beyond the spec (for example, no pattern check on `req` ids).

## Plan
1. Create branch `task/TASK-059-gate-runner-port-and-gate-output` from an up-to-date main and commit this record.
2. Get the human's answers to Open questions 1 to 4, and record them here and as rows in `docs/decisions.md`. Adjust the criteria before any test is written if an answer differs from a proposal.
3. Test-writer: write failing tests for AC1 to AC5 in `tests/unit/test_gate_runner_port.py` (new). No existing test is changed.
4. Add `domain/gates.py`.
5. Add `ports/gate_runner.py` with the Protocol and its docstrings.
6. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
7. Update the living docs and the Outcome. Commit `feat(ports): add the GateRunner port and GateOutput` with the trailers `Task: TASK-059` and `Milestone: M4`. Do not push.

## Files expected to change
- `src/openfactory/domain/gates.py` (new, about 35 lines)
- `src/openfactory/ports/gate_runner.py` (new, about 35 lines)
- `tests/unit/test_gate_runner_port.py` (new, about 140 lines)
- `docs/architecture.md`: new sections "Gate output" (`domain/gates.py`) and "GateRunner port". "Data flow" notes that the port has no adapter yet and nothing calls it.
- `docs/progress.md`: Current, Done, outline item 1 reworded to the adapter piece (below), and the Later lines below.
- `docs/decisions.md`: rows for the answers.
- `docs/tasks/TASK-059-gate-runner-port-and-gate-output.md` (this record; Outcome at close).

Not expected to change: `adapters/`, `app/`, `cli.py`, `domain/payloads.py`, the other ports, `pyproject.toml`, `docs/adr/`, `docs/spec/`, every existing test file, `README.md` and `CHANGELOG.md`.

Expected size: about 210 lines with tests, about 70 of them in `src/`.

## Outline item 1 after this task
"1. The `process_gates` adapter for `ruff` and `gitleaks` with `missing_tool()`: `uv run` in the worktree and `gitleaks` from `PATH` with `--exit-code 3`; the time limit per command, the gate text, and a command that cannot start; `finding` only on gitleaks exit 3. It also confirms on the installed gitleaks (8.30.1) that its own errors do not exit 3, and decides what `run("pytest", ...)` does until item 2 (SC-84, SC-94, SC-111, SC-115, SC-121; ADR-015, ADR-016, ADR-017). Depends on TASK-059."

## Spec gaps
Spec impact is "wording". One item, which does not block.

1. **"Gates and remediation" › "Running a gate that starts a process"**: "`GateOutput` holds `passed`, `text`, `finding` and, for `pytest`, the collected marker lines."
   - Unclear: the text does not name the field. It does not say whether the lines are raw text or parsed records, nor what `ruff` and `gitleaks` give for it (empty, or absent).
   - Does not block. The line's shape is fixed by "The pytest gate and `req` markers" (`{"file": ..., "req": [...]}`), so a parsed model traces to spec text. The rest is a code-shape choice inside what the spec allows.
   - Not assumed: Open questions 2 and 3 carry proposals for the human. The answer becomes a `docs/decisions.md` row, and the spec text is left to a later `/spec-change`.

Readings, not gaps:
- `timeout_s` is an `int`, because "`timeout_s` is the contract's `max_runtime_s`", and `Limits.max_runtime_s` is `int`.
- `worktree` is passed relative to the repo and resolved by the adapter. This is the decided F-7 rule (2026-10-13) that `WorkspaceManager.create`, `GitCli` and `ClaudeCodeExecutor` already follow.
- A failed gate is returned, not raised: "A command that cannot be started or runs past `timeout_s` fails its gate, and the text says why".
- `missing_tool` returns `str | None` as the spec writes it, not a `Literal`.

## Later lines in `docs/progress.md`
Taken: none. The two real-run Later lines (the user's connectors in agent runs; the `req` marker registered by the agent) belong to later items.

To add at close:
- "`GateOutput` checks no link between `finding`, `passed` and the gate (a `finding` with `passed` true would validate); the adapter keeps it, as for `RunResult` (TASK-059, planner)."
- The "Spec wording" line below, completed with the answer.

## Open questions
None blocks planning. Each has a proposal and an alternative, and all must be answered before the tests are written (Plan step 2).

1. **The split of outline item 1.**
   - Proposed: two tasks. This one (about 210 lines). Then TASK-060, `process_gates` for `ruff` and `gitleaks` with `missing_tool()`, the per-command time limit, the text format, a command that cannot start, `finding` on exit 3, and the gitleaks 8.30.1 check (about 330 lines, on stand-in `uv` and `gitleaks` executables). This follows the TASK-047 precedent.
   - Alternative: one task of about 480 lines. Six criteria only fit if the model and port criteria are folded together. TASK-025 (450) and TASK-034 (430) were kept whole, and TASK-022 (430) was split.
2. **Names and modules.**
   - Proposed: `ProcessGate`, `MarkerLine` and `GateOutput` in a new `domain/gates.py` (this is not the deleted top-level `gates/` package). The Protocol goes in `ports/gate_runner.py`. The field is `marker_lines`, after the spec's "collected marker lines".
   - Alternative: `GateOutput` in `domain/gate_output.py`, with `CollectedTest` and field `collected`.
3. **What the marker-lines field holds.**
   - Proposed: parsed `MarkerLine` records, a required `list[MarkerLine]`, empty for `ruff` and `gitleaks`. The adapter parses the plugin's JSON lines (item 2), and the tag rule (item 3) is a pure function over typed records.
   - Alternative (a): `list[MarkerLine] | None`, with `None` for `ruff` and `gitleaks`.
   - Alternative (b): raw JSON line strings (`list[str]`), parsed in the domain by the tag rule.
4. **Gate parameter type and model config.**
   - Proposed: a new narrower `ProcessGate` Literal, so pyright rejects `run("review", ...)`; both models frozen and `extra="forbid"`, with all fields required (as `RunResult`); no cross-field validator; no exception type on the port.
   - Alternative: type `gate` as the existing `GateName` (five values), and leave the adapter to reject `path_check` and `review`.

## Answers (2026-10-16, the human, following the advisor)
1. Split as proposed: this task is the port and models; TASK-060 is the `process_gates` adapter for `ruff` and `gitleaks`.
2. As proposed: `ProcessGate`, `MarkerLine` and `GateOutput` in `domain/gates.py`, the Protocol in `ports/gate_runner.py`, the field `marker_lines`. `ProcessGate` is deliberately kept out of `domain/payloads.py`, though that file names the closed sets of payloads, because no payload records it.
3. As proposed: a required `list[MarkerLine]` of parsed records, empty for `ruff` and `gitleaks`.
4. As proposed: `gate` typed `ProcessGate`; both models frozen, `extra="forbid"`, every field required; no cross-field validator; no exception type on the port.

## Outcome
- Built: `src/openfactory/domain/gates.py` with `ProcessGate = Literal["ruff", "pytest", "gitleaks"]`, frozen `MarkerLine` (`file`, `req`) and frozen `GateOutput` (`passed`, `text`, `finding`, `marker_lines`), all `extra="forbid"` with every field required and no check across fields; `src/openfactory/ports/gate_runner.py` with the Protocol `GateRunner` (`run(gate: ProcessGate, worktree: Path, timeout_s: int) -> GateOutput`, `missing_tool() -> str | None`), its docstrings carrying the returned-not-raised rule, the relative `worktree`, `finding` only on gitleaks exit 3 and empty `marker_lines` for `ruff` and `gitleaks`. No adapter; nothing calls the port.
- Tests: 21 new tests in `tests/unit/test_gate_runner_port.py` from the test-writer, failing first (the modules did not exist) and passing now. No existing test changed. Full suite: 1337 passed; ruff, pyright and check_docs clean.
- No deviation from the plan. Reviewer: approve, no blocking issues. Of its non-blocking notes, applied at the human's word: Status set to done and the boxes ticked, and the comments on `GateOutput.passed` and `text` say they describe what the adapter returns, since for `pytest` the use case also applies the tag rule. Not applied: `issubclass(GateRunner, Protocol)` in the AC3 test is a loose check (test style only).
