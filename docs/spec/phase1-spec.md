# OpenFactory — Phase 1 Spec

Version 1.2 · 2026-10-08 · Owner: Muhammed

## Purpose and demo scenario

Phase 1 proves one claim end to end: when a human changes a requirement, the platform finds exactly the affected tasks, files and tests, replans only those, and re-executes them with traceability intact. Everything in this spec serves that single demo.

**The demo, step by step:**

1. The human writes `REQ-AUTH-001`: users authenticate with a membership number. Plus one ADR and a few supporting requirements.
2. `openfactory validate` checks the specs; the human runs `openfactory approve spec` to freeze spec v1.
3. `openfactory plan` produces a task DAG; the human approves the plan.
4. `openfactory run` executes each task in its own git worktree with Claude Code, runs the gates, and commits with traceability trailers.
5. `openfactory trace REQ-AUTH-001` shows requirement → tasks → commits → files → tests.
6. The human edits the requirement: users authenticate with OTP instead. Approves spec v2.
7. `openfactory impact` shows the impacted subgraph: which tasks, files and tests are affected, and what new work is needed.
8. `openfactory replan` creates new and revised tasks only for the impacted subgraph; untouched tasks stay `passed`.
9. `openfactory run` executes only those; `openfactory report` prints the final traceability report.

**Success criteria:**

- The demo runs on a real target repo with no manual code edits between steps.
- Every commit made by the platform maps to a task and at least one requirement.
- Impact analysis on the eval set (see Evaluation plan) reaches at least 0.9 recall on affected files and tests.
- Re-execution after the change touches only impacted tasks.
- Every state change can be reconstructed from the event log.

## Scope

Phase 1 is a single-user CLI that drives one agent runtime against one local repo, sequentially. Anything not needed for the demo waits.

| In Phase 1 | Deferred to later phases |
| --- | --- |
| CLI only (Typer) | Web UI (Next.js or similar) |
| One runtime: Claude Code headless, behind an adapter interface | OpenCode, OpenHands, Ollama |
| Three agent roles: planner, implementer, reviewer | Requirements, architecture, security, docs, DevOps agents |
| Sequential task execution, one worktree per task | Parallel execution, merge-conflict handling |
| Local git branches and commits | Push, PRs, GitHub provider |
| Deterministic gates: pytest, ruff, gitleaks, path check | Semgrep, Trivy, CI integration |
| SQLite + append-only events | PostgreSQL, NATS, durable workflow engine |
| Requirement-level semantic diff | Full spec conflict detection, ADR contradiction detection |
| Bounded remediation: one retry with failure context | Failure classifier, multi-step self-healing |
| Approval via CLI commands | Configurable approval policies, RBAC |
| Token, cost and latency per run | Dashboards, OpenTelemetry |

The target repo is a small Python auth service (FastAPI), so the whole demo stays in one language.

## Tech stack and repo layout

Python 3.12, with a hexagonal layout: the domain never imports infrastructure, so SQLite, git and Claude Code can be swapped later.

| Concern | Choice |
| --- | --- |
| Language | Python 3.12, managed with uv |
| CLI | Typer |
| Schemas and LLM output validation | Pydantic v2 |
| Storage | SQLite via the standard `sqlite3` module, WAL mode |
| Agent runtime | Claude Code headless (`claude -p` with JSON output) behind `AgentExecutor` |
| Planner and diff LLM calls | Claude Code headless (`claude -p --output-format json`) behind `LLMProvider`, validated by Pydantic |
| Git | Git CLI via `subprocess` |
| Graph queries | Recursive SQL CTEs; networkx only for cycle checks |
| Tests | pytest |
| Lint and format | ruff |
| Secret scan | gitleaks |
| Logging | structlog, JSON lines |

All model calls go through Claude Code using the user's Claude subscription login; no API key is required. `ANTHROPIC_API_KEY` must not be set, because Claude Code would use it instead of the subscription. If a reply fails Pydantic validation, the call is retried once with the validation error in the prompt, then fails.

```
src/openfactory/
  domain/          # pure models, state machine, rules; no I/O
    models.py      # Requirement, Task, AgentRun, Gate, ...
    states.py      # task state machine + allowed transitions
    events.py      # event types
  app/             # use cases: validate, plan, run, impact, replan
  ports/           # interfaces: EventStore, AgentExecutor, WorkspaceManager, GitProvider, LLMProvider
  adapters/        # sqlite_store, claude_code_executor, claude_code_llm, git_worktree
  gates/           # pytest, ruff, gitleaks, path_check
  cli.py
tests/
  unit/ integration/ eval/
```

## Spec input format

Specs are structured YAML with stable IDs written by a human; the LLM may help draft them, but only approved YAML is authoritative. Free-text PRDs are out of scope for Phase 1.

```
specs/
  requirements.yaml
  adrs/ADR-001-auth-method.md   # markdown body + YAML front matter
  policies.yaml                 # protected branches, forbidden paths, retry limit
```

```yaml
# requirements.yaml
requirements:
  - id: REQ-AUTH-001
    title: Login with membership number
    statement: Users authenticate using their membership number and password.
    priority: must
    constrained_by: [ADR-001]
    components: [auth]
    acceptance_criteria:
      - id: AC-AUTH-001-1
        text: Valid membership number and password returns a JWT.
      - id: AC-AUTH-001-2
        text: Unknown membership number returns 401.
```

**Validation rules (deterministic, run by `openfactory validate`):**

- IDs match `REQ-[A-Z]+-\d{3}`, `ADR-\d{3}`, `AC-...`, and are unique.
- Every requirement has at least one acceptance criterion.
- Every `constrained_by` reference points to an existing ADR with status `accepted`.
- Every component named by a requirement is declared in the top-level `components` list.
- No requirement is deleted while tasks still reference it, unless the new version marks it `deprecated`. Enforced from M2, when tasks exist.

**Advisory checks (LLM, reported as warnings, never blocking):** vague wording such as "fast" or "secure" without a measure, and possible duplicates.

On `openfactory approve spec`, the spec set is hashed and stored as an immutable `spec_version`. Edits after that create a new draft version.

## Domain model and storage

The `events` table is the source of truth; every other table is a projection rebuilt from it. This gives auditability, resumability after a crash, and a replayable history in one design choice.

```sql
CREATE TABLE events (
  seq          INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id     TEXT UNIQUE NOT NULL,     -- uuid; idempotency key
  stream       TEXT NOT NULL,            -- e.g. 'task:AUTH-002'
  type         TEXT NOT NULL,            -- e.g. 'TaskStarted'
  payload      TEXT NOT NULL,            -- JSON, validated by Pydantic
  actor        TEXT NOT NULL,            -- 'human' | 'orchestrator' | 'agent:implementer'
  causation_id TEXT,                     -- event that caused this one
  created_at   TEXT NOT NULL
);
```

**Projections:**

| Table | Holds |
| --- | --- |
| `spec_versions` | id, hash, status (draft, approved), approved_at |
| `requirements` | id, spec_version, title, statement, components, hash |
| `adrs` | id, spec_version, status, hash |
| `plans` | id, spec_version, status (draft, approved, superseded) |
| `tasks` | id, plan_id, state, objective, contract JSON, attempt |
| `task_deps` | task_id, depends_on |
| `agent_runs` | id, task_id, role, runtime, started_at, ended_at, exit, tokens_in, tokens_out, cost_usd, context_hash |
| `gate_results` | run_id, gate, passed, output_path |
| `commits` | sha, task_id, run_id, branch |
| `trace_links` | from_kind, from_id, to_kind, to_id, source (trailer, contract, diff, test_tag) |

`trace_links` is the traceability graph: one generic edge table that all queries traverse. Each edge records how it was established, so deterministic and inferred links are never confused.
**Event types in Phase 1:** `SpecImported`, `SpecValidated`, `SpecApproved`, `PlanCreated`, `PlanApproved`, `TaskStateChanged`, `AgentRunStarted`, `AgentRunFinished`, `GateEvaluated`, `CommitRecorded`, `ImpactComputed`. Approvals are recorded by `SpecApproved` and `PlanApproved` with actor `human`; invalidation is a `TaskStateChanged` to `invalidated` with a reason in its payload.

**Event envelope rules:**

- `event_id`: any valid UUID; new events use UUID4.
- `actor`: one of `human`, `orchestrator`, or `agent:<role>` (lowercase role name).
- `created_at`: timezone-aware UTC, stored as ISO 8601.
- `payload`: a JSON object.
- `seq` is assigned by the store. New events have no `seq`; stored events always do, and only stored events are replayed.

## Task contract

The planner LLM emits tasks in this shape; Pydantic rejects anything that doesn't validate, and the plan is rejected if the DAG has a cycle or references an unknown requirement.

```yaml
task_id: AUTH-002
objective: Implement login endpoint using membership number
requirements: [REQ-AUTH-001]
acceptance_criteria: [AC-AUTH-001-1, AC-AUTH-001-2]
depends_on: [AUTH-001]
components: [auth]
role: implementer
allowed_paths:
  - app/auth/**
  - tests/auth/**
forbidden_paths:
  - .env
  - specs/**
required_gates: [pytest, ruff, gitleaks, path_check]
limits:
  max_runtime_s: 1200
  max_attempts: 2
  max_cost_usd: 1.50
```

```python
class TaskContract(BaseModel):
    task_id: str = Field(pattern=r"^[A-Z]+-\d{3}$")
    objective: str
    requirements: list[str] = Field(min_length=1)
    acceptance_criteria: list[str] = Field(min_length=1)
    depends_on: list[str] = []
    components: list[str]
    role: Literal["implementer", "reviewer"]
    allowed_paths: list[str] = Field(min_length=1)
    forbidden_paths: list[str] = []
    required_gates: list[str]
    limits: Limits
```

The orchestrator adds the policy's global forbidden paths to every contract, so the planner can never widen access past policy.

## Task state machine

A task has nine states, and only the orchestrator moves it between them; every transition is a `TaskStateChanged` event.

- `pending`: waiting on dependencies.
- `ready`: dependencies passed; can be scheduled.
- `running`: the agent is working.
- `gating`: gates are running on the result.
- `passed`: all gates passed; the orchestrator has committed.
- `failed`: the run errored, timed out, or a gate failed; output is saved.
- `escalated`: needs a human decision.
- `abandoned`: closed by a human.
- `invalidated`: hit by a spec change; replan needed.

Failures loop back to `ready` until attempts run out; path or secret violations skip the retry and escalate at once. Any task not currently running can be invalidated by a spec change.

```python
TRANSITIONS = {
    "pending":     {"ready", "invalidated"},
    "ready":       {"running", "invalidated"},
    "running":     {"gating", "failed"},
    "gating":      {"passed", "failed"},
    "failed":      {"ready", "escalated", "invalidated"},
    "escalated":   {"ready", "abandoned", "invalidated"},
    "passed":      {"invalidated"},
    "invalidated": set(),
    "abandoned":   set(),
}
```

## Execution

Each task runs in its own git worktree on its own branch; the orchestrator, not the agent, decides whether the result is accepted.

**Per-task sequence:**

1. `git worktree add .openfactory/worktrees/AUTH-002 -b openfactory/AUTH-002 <base>`, where `<base>` is the branch holding the task's dependencies.
2. Build the context pack: the task contract, full text of its requirements and acceptance criteria, linked ADRs, the current contents of files under `allowed_paths`, and the last failure report if this is a retry. Hash it and store the hash on the agent run.
3. Call `AgentExecutor.run(contract, context, workdir)`. The Claude Code adapter runs headless with a restricted tool allowlist and the worktree as its working directory, and parses token usage and cost from its JSON output.
4. After the agent exits, the orchestrator runs `git status --porcelain` and checks every changed path against `allowed_paths` and `forbidden_paths`. Any violation fails the run, whatever the agent claims.
5. Run the required gates in the worktree.
6. If all gates pass, the orchestrator itself commits with trailers (see Traceability). The agent never commits.

**Isolation, honestly stated:** in Phase 1, the path check after the run is the real enforcement; Claude Code's own permission settings are defence in depth. Running the agent in a Docker container with only the worktree mounted is a Phase 1 stretch goal, not a requirement.

**Adapter interface:**

```python
class AgentExecutor(Protocol):
    def run(self, contract: TaskContract, context: ContextPack, workdir: Path) -> RunResult: ...

class RunResult(BaseModel):
    exit_status: Literal["ok", "error", "timeout"]
    summary: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    duration_s: float
    transcript_path: Path
```

## Gates and remediation

A task passes only when every required gate passes; the reviewer agent's verdict is recorded but cannot override a failed deterministic gate.

| Gate | Command | Blocks on |
| --- | --- | --- |
| path_check | built in: diff paths vs contract | any write outside `allowed_paths` or inside `forbidden_paths` |
| ruff | `ruff check` and `ruff format --check` | any error |
| pytest | `pytest tests/` | any failure, or zero tests tagged with the task's requirements |
| gitleaks | `gitleaks detect --no-git --source .` | any finding |
| review | reviewer agent reads diff + contract, returns structured verdict | `reject` verdict (advisory if `approve` but gates fail) |

**Remediation:** on a failed gate, the task moves to `failed` and, if attempts remain, back to `ready` with the gate output attached to its next context pack. After `max_attempts` (default 2), it moves to `escalated` and waits for a human. A path violation or a gitleaks finding escalates immediately, with no retry.

Gate output is stored as a file, with its path on `gate_results`, so the audit trail keeps the evidence, not just a pass or fail.

## Traceability

Every link in the graph is established mechanically, never guessed by an LLM. That is what makes impact analysis trustworthy.

| Link | Established by |
| --- | --- |
| requirement → ADR | `constrained_by` in the spec |
| requirement → task | task contract `requirements` |
| task → task | contract `depends_on` |
| task → agent run → commit | orchestrator records them as they happen |
| commit → file | `git diff --name-only` of the commit |
| test → requirement | pytest marker `@pytest.mark.req("REQ-AUTH-001")`, collected with `pytest --collect-only` |
| test → file | the test file path |

**Commit trailers**, written by the orchestrator:

```
auth: add membership-number login endpoint

Task: AUTH-002
Requirements: REQ-AUTH-001
Acceptance-Criteria: AC-AUTH-001-1, AC-AUTH-001-2
Agent-Run: run_0091
Spec-Version: sv_01
```

Trailers make the graph rebuildable from git history alone, even if the SQLite file is lost.

The implementer's instructions require every new test to carry a `req` marker; the pytest gate fails if a task produces no test tagged with its requirements.

**Queries:**

- `openfactory trace REQ-AUTH-001`: requirement → tasks → commits → files and tests.
- `openfactory why app/auth/login.py`: file → commits → tasks → requirements and ADRs.
- `openfactory coverage`: requirements with no passing tagged test.

## Spec diff and impact analysis

Impact analysis is two steps: a structural diff that finds which requirements changed, then a deterministic graph traversal that finds what depends on them. The LLM only classifies the change; it never decides what is affected.

**Step 1: structural diff (deterministic).** Compare spec v1 and v2 by ID and content hash. Each requirement, ADR and acceptance criterion is `added`, `removed`, `modified` or `unchanged`.

**Step 2: change classification (LLM, validated).** For each `modified` requirement, the LLM returns:

```python
class ChangeClass(BaseModel):
    req_id: str
    kind: Literal["cosmetic", "behavioral", "replacement"]
    rationale: str
    obsolete_criteria: list[str]   # AC ids no longer valid
    new_work: list[str]            # short descriptions
```

`cosmetic` changes (wording only) are shown but trigger no work. The human can override any classification before approving.

**Step 3: traversal (deterministic).** Starting from each non-cosmetic changed requirement, walk `trace_links` with a recursive CTE: requirement → tasks → downstream dependent tasks → commits → files → tests tagged with the requirement or touching those files.

**Step 4: impact report and replan.**

```
Impact: REQ-AUTH-001 (replacement)
  Tasks invalidated:   AUTH-002, AUTH-003
  Downstream tasks:    AUTH-005
  Files:               app/auth/login.py, app/auth/schemas.py
  Tests:               tests/auth/test_login.py (4 tests)
  Obsolete criteria:   AC-AUTH-001-1, AC-AUTH-001-2
  New work:            OTP issue endpoint, OTP verify endpoint, attempt rate limit
```

On `openfactory replan`, impacted tasks move to `invalidated`; the planner receives only the impacted subgraph, the new spec, and the untouched tasks as fixed context, and proposes new or revised tasks. Untouched tasks keep their state and commits. After approval, only the new tasks run, branching from the last commit of the untouched work.

**Mid-execution change:** if a spec version is approved while tasks are running, running tasks finish, then any that fall in the impacted set are invalidated before their results merge.

## Metrics

Every LLM call and agent run records tokens in, tokens out, cost in USD, and wall-clock latency, so each task and each plan has a known price. On a Claude subscription the cost is notional: it is the API-rate equivalent that Claude Code reports, and `max_cost_usd` limits apply to that figure.

- Stored per agent run and per planner or classifier call, with role and model name.
- `openfactory stats` prints totals per task, per plan, and per role, plus p50 and p95 run latency.
- A task's `max_cost_usd` is checked after each run; exceeding it escalates the task.
- The final report includes total cost of the initial build and of the replan, which shows the saving from re-executing only impacted work.

## CLI commands

| Command | Does |
| --- | --- |
| `openfactory init <repo>` | Creates `.openfactory/`, the SQLite file and default `policies.yaml` |
| `openfactory validate` | Runs deterministic and advisory spec checks |
| `openfactory approve spec` | Freezes the current spec as a new version |
| `openfactory plan` | Generates a task DAG for the approved spec |
| `openfactory approve plan` | Marks the plan approved; tasks become `ready` |
| `openfactory run [--task ID]` | Executes ready tasks in dependency order |
| `openfactory status` | Shows tasks, states, attempts and last gate result |
| `openfactory trace REQ-ID` | Requirement to code and tests |
| `openfactory why PATH` | File to requirements and ADRs |
| `openfactory impact` | Diffs the latest two spec versions and prints the impact report |
| `openfactory replan` | Invalidates impacted tasks and plans new ones |
| `openfactory resolve TASK-ID` | Human action on an escalated task: retry or abandon |
| `openfactory stats` | Tokens, cost and latency |
| `openfactory report` | Final traceability report as Markdown |
| `openfactory events [--stream S]` | Raw audit log |

## Evaluation plan

Impact analysis is measured against hand-labelled ground truth, so the core claim is backed by numbers rather than a single demo.

- **Fixture:** a frozen snapshot of the target repo after the initial build, with its event log and git history.
- **Cases:** 8 spec changes, each with a hand-written list of truly affected tasks, files and tests. Mix: 2 cosmetic, 3 behavioral, 2 replacement, 1 new requirement.
- **Metrics:** precision and recall of affected files and tests per case; classification accuracy of `ChangeClass.kind`.
- **Targets:** recall ≥ 0.9 on files and tests (missing an affected test is the expensive error); precision ≥ 0.7; zero work triggered for cosmetic changes.
- **Run:** `pytest tests/eval -m eval`, outputs a Markdown table committed to the repo.

The traversal steps are deterministic and tested by unit tests; only the classifier varies, so eval runs 3 times and reports the spread. Eval runs use the same Claude subscription as development, so run them deliberately rather than on every change.

## Milestones and definition of done

Each milestone ends with something that runs and is tested before the next one starts.

1. **Specs and events.** `init`, `validate`, `approve spec`; events table and projections; replay rebuilds projections identically.
2. **Planner.** `plan`, `approve plan`; Claude Code LLM adapter; contract validation, cycle check, unknown-requirement check.
3. **Executor.** One task end to end: worktree, context pack, Claude Code run, path check, commit with trailers.
4. **Gates and remediation.** ruff, pytest with req markers, gitleaks, reviewer; retry with failure context; escalation.
5. **Traceability.** `trace`, `why`, `coverage`; rebuild links from git trailers alone.
6. **Impact and replan.** Structural diff, classifier, traversal, `impact`, `replan`, partial re-execution.
7. **Eval, report and demo.** Eval suite with results, `stats`, `report`, a demo video, and a design write-up.

**Phase 1 is done when:**

- [ ] The 9-step demo runs on the target repo with no manual code edits.
- [ ] Every platform commit has trailers and resolves in `openfactory why`.
- [ ] Eval meets the recall and precision targets.
- [ ] Killing the process mid-run and restarting resumes from the event log without duplicate commits.
- [ ] README, design write-up and demo video are published.