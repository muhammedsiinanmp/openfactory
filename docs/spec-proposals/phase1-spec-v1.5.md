# OpenFactory — Phase 1 Spec

Version 1.5 · 2026-10-08 · Owner: Muhammed

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
| Deterministic spec validation | Advisory LLM spec checks (vague wording, possible duplicates) |
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
| Spec files | YAML, read with PyYAML (`yaml.safe_load`); duplicate keys are rejected |
| Storage | SQLite via the standard `sqlite3` module, WAL mode |
| Agent runtime | Claude Code headless (`claude -p` with JSON output) behind `AgentExecutor` |
| Planner and diff LLM calls | Claude Code headless (`claude -p --output-format json --json-schema`) behind `LLMProvider`, validated by Pydantic |
| Git | Git CLI via `subprocess` |
| Graph queries | Recursive SQL CTEs; networkx only for cycle checks |
| Tests | pytest |
| Lint and format | ruff |
| Secret scan | gitleaks |
| Logging | structlog, JSON lines |

All model calls go through Claude Code using the user's Claude subscription login; no API key is required. Claude Code would use `ANTHROPIC_API_KEY` instead of the subscription if it were set, so the adapters start `claude` with that variable removed from its environment, without reading its value, and log a warning if it was present. If a reply fails Pydantic validation, the call is retried once with the validation error in the prompt, then fails.

```
src/openfactory/
  domain/          # pure models, state machine, rules; no I/O
    models.py      # Requirement, Task, AgentRun, Gate, ...
    states.py      # task state machine + allowed transitions
    events.py      # event types
    payloads.py    # one payload model per event type
  app/             # use cases: validate, plan, run, impact, replan
  ports/           # interfaces: EventStore, SpecFiles, AgentExecutor, WorkspaceManager, GitProvider, LLMProvider
  adapters/        # sqlite_store, sqlite_projector, filesystem_spec_files, claude_code_executor, claude_code_llm, git_worktree
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
  policies.yaml                 # protected branches, forbidden paths, limits
```

```yaml
# requirements.yaml
components: [auth]
requirements:
  - id: REQ-AUTH-001
    title: Login with membership number
    statement: Users authenticate using their membership number and password.
    priority: must
    constrained_by: [ADR-001]
    acceptance_criteria:
      - id: AC-AUTH-001-1
        text: Valid membership number and password returns a JWT.
      - id: AC-AUTH-001-2
        text: Unknown membership number returns 401.
```

**Loading:**

- The loader reads `specs/requirements.yaml` (required) and every `specs/adrs/*.md`. A missing or empty `adrs/` directory means no ADRs.
- An ADR file starts with a line `---`, then YAML front matter, then a line `---`. Everything after that is the body.
- The `id` in front matter is authoritative; the file name is not checked.
- Files are read as UTF-8. Line endings in an ADR body are normalised to `\n`.
- Spec files are read through a `SpecFiles` port that returns each file's text by path relative to `specs/` (`requirements.yaml`, `adrs/*.md`, `policies.yaml`). A filesystem adapter implements it. Parsing YAML and ADR front matter happens in the application layer.

**Validation rules (deterministic, run by `openfactory validate`):**

- IDs match `REQ-[A-Z]+-\d{3}`, `ADR-\d{3}` and `AC-[A-Z]+-\d{3}-\d+`, and are unique across the whole spec set.
- Every requirement has at least one acceptance criterion.
- Every `constrained_by` reference points to an existing ADR with status `accepted`.
- Every component named by a requirement is declared in the top-level `components` list.
- No requirement is deleted while tasks still reference it, unless the new version marks it `deprecated`. Enforced from M2, when tasks exist. A requirement is deleted when it is in the latest approved spec version and absent from the files being validated. A task still references it when the task is in the `tasks` projection, lists it in its contract, and is in neither state `abandoned` nor `invalidated`. The fix is to restore the requirement with `deprecated: true`.

A file that cannot be loaded into the models is reported under the rule `schema`: a YAML syntax error, a missing `requirements.yaml`, an ADR file without front matter, or a value the models reject. Its subject is the item's id when that can be read, otherwise the file path relative to the repo. When there is any `schema` violation the rules above are not run, because there is no trustworthy spec set to run them on.

**Spec field rules:**

- `components` is a top-level list of component names in `requirements.yaml`.
- `priority` is one of `must`, `should`, `could`.
- `constrained_by`, `components` and `acceptance_criteria` are optional and default to empty; a requirement with no acceptance criteria is reported by validation rather than rejected while parsing.
- `deprecated` is an optional boolean on a requirement and defaults to `false`. A deprecated requirement is validated like any other, but the planner creates no tasks for it.
- ADR front matter has `id` and `status`; `status` is one of `proposed`, `accepted`, `superseded`. Only `accepted` satisfies `constrained_by`. Other front matter fields are ignored. The ADR model also holds the `body`.
- Validation returns every violation in one run, each with the rule name, the ID it concerns, and a message. It never stops at the first.

**Hashing:**

The hash of a thing is the SHA-256 of the canonical JSON of its parsed model, written as 64 lowercase hex characters.

- Canonical JSON is the model dumped in JSON mode, with sorted keys, separators `,` and `:` with no spaces, non-ASCII characters left as they are, encoded as UTF-8.
- The models are hashed, not the files. Comments, key order, indentation and quoting style do not change a hash, and an omitted optional field hashes the same as its default.
- Order in the files does not matter: before hashing, `requirements` and `adrs` are sorted by `id`, `acceptance_criteria` by `id`, and `components` and `constrained_by` as strings.
- Strings are hashed as parsed: no trimming, no case folding, no Unicode normalisation.
- A requirement's hash covers the whole requirement, including its acceptance criteria, so changing a criterion makes its requirement `modified`.
- An ADR's hash covers `id`, `status` and `body`.
- An acceptance criterion's hash covers `id` and `text`. It is not stored; it is computed when the diff needs it.
- The spec set's hash covers the components, the requirements and the ADRs.

A change to the canonical form changes every hash. During Phase 1 development that is handled by discarding the development database, not by versioning the hash.

**Spec versions:**

A spec version has an id of the form `sv_NN` (two digits, counted from `sv_01`, wider when needed) and is either `draft` or `approved`. At most one draft exists at a time.

`openfactory validate` loads the files and hashes the spec set:

- If the spec files cannot be loaded (any `schema` violation in them), `validate` prints the violations, records no events, and exits 1.
- If the hash equals the latest approved version's, nothing is imported and the command says so.
- If the hash equals the current draft's, nothing is imported.
- Otherwise it records `SpecImported`. An existing draft keeps its id and its content is replaced; if there is no draft, the next id is used.
- It then runs the rules and records `SpecValidated` with the result.

`openfactory approve spec` does not rely on an earlier `validate`. It loads and hashes the files, imports them if they changed, runs the rules, and refuses if there is any violation. Otherwise it records `SpecApproved`, and the version is immutable from then on. Edits after that create a new draft version on the next `validate` or `approve spec`. If the files equal the latest approved version, it exits non-zero with "nothing to approve".

`approve spec` records `SpecValidated` with the rule results before `SpecApproved`, so every approval is preceded by the validation it was based on.

Because a draft keeps its id until it is approved, approved versions are numbered without gaps.

**Policies:**

`specs/policies.yaml` has five keys. Each is optional with the default shown, and unknown keys are rejected.

```yaml
# policies.yaml
protected_branches: [main, master]
forbidden_paths:
  - .env
  - .env.*
  - specs/**
  - .openfactory/**
max_attempts: 2
max_runtime_s: 1200
max_cost_usd: 1.50
```

- `forbidden_paths` uses the same glob syntax as the paths in a task contract.
- `max_attempts`, `max_runtime_s` and `max_cost_usd` must be greater than zero. They are the limits of every task contract (see Task contract).
- `protected_branches` lists branches the orchestrator refuses to commit on.
- `openfactory validate` prints policy problems under the rule `schema`, with the file path as subject, and exits 1. Policy problems are not recorded in `SpecValidated`, do not stop the content rules, and do not block `approve spec`.
- `openfactory plan` refuses to run while the policy is invalid.
- A missing file is an error that says to run `openfactory init`.
- The policy is not part of the spec set and is not covered by a spec version's hash, so editing it does not create a new spec version. It is read when a plan is created, and its own hash is recorded with the plan.

## Domain model and storage

The `events` table is the source of truth; every other table is a projection rebuilt from it. This gives auditability, resumability after a crash, and a replayable history in one design choice.

```sql
CREATE TABLE events (
  seq          INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id     TEXT UNIQUE NOT NULL,     -- uuid; idempotency key
  stream       TEXT NOT NULL,            -- e.g. 'task:AUTH-002'
  type         TEXT NOT NULL,            -- e.g. 'TaskStateChanged'
  payload      TEXT NOT NULL,            -- JSON, validated by Pydantic
  actor        TEXT NOT NULL,            -- 'human' | 'orchestrator' | 'agent:implementer'
  causation_id TEXT,                     -- event that caused this one
  created_at   TEXT NOT NULL
);
```

**Projections:**

| Table | Holds |
| --- | --- |
| `spec_versions` | id, hash, status (draft, approved), components, approved_at |
| `requirements` | id, spec_version, title, statement, priority, deprecated, components, constrained_by, acceptance_criteria, hash |
| `adrs` | id, spec_version, status, body, hash |
| `plans` | id, spec_version, status (draft, approved, superseded) |
| `tasks` | id, plan_id, state, objective, contract JSON, attempt |
| `task_deps` | task_id, depends_on |
| `agent_runs` | id, task_id (null for a run that belongs to no task), role, runtime, model, started_at, ended_at, exit, tokens_in, tokens_out, cost_usd, context_hash |
| `gate_results` | run_id, gate, passed, output_path |
| `commits` | sha, task_id, run_id, branch |
| `trace_links` | from_kind, from_id, to_kind, to_id, source (spec, trailer, contract, diff, test_tag) |

`trace_links` is the traceability graph: one generic edge table that all queries traverse. Each edge records how it was established, so deterministic and inferred links are never confused. Links declared in the spec files, such as `constrained_by`, have source `spec`.

The tables built in M1 and M2:

```sql
CREATE TABLE spec_versions (
  id          TEXT PRIMARY KEY,              -- sv_01
  hash        TEXT NOT NULL,
  status      TEXT NOT NULL,                 -- draft | approved
  components  TEXT NOT NULL,                 -- JSON array
  approved_at TEXT                           -- ISO 8601 UTC, from SpecApproved.created_at
);
CREATE TABLE requirements (
  id                  TEXT NOT NULL,
  spec_version        TEXT NOT NULL,
  title               TEXT NOT NULL,
  statement           TEXT NOT NULL,
  priority            TEXT NOT NULL,
  deprecated          INTEGER NOT NULL,      -- 0 | 1
  components          TEXT NOT NULL,         -- JSON array
  constrained_by      TEXT NOT NULL,         -- JSON array of ADR ids
  acceptance_criteria TEXT NOT NULL,         -- JSON array of {id, text}
  hash                TEXT NOT NULL,
  PRIMARY KEY (spec_version, id)
);
CREATE TABLE adrs (
  id           TEXT NOT NULL,
  spec_version TEXT NOT NULL,
  status       TEXT NOT NULL,
  body         TEXT NOT NULL,
  hash         TEXT NOT NULL,
  PRIMARY KEY (spec_version, id)
);
CREATE TABLE plans (
  id           TEXT PRIMARY KEY,             -- plan_01
  spec_version TEXT NOT NULL,
  status       TEXT NOT NULL                 -- draft | approved | superseded
);
CREATE TABLE tasks (
  id        TEXT PRIMARY KEY,                -- AUTH-002
  plan_id   TEXT NOT NULL,
  state     TEXT NOT NULL,
  objective TEXT NOT NULL,
  contract  TEXT NOT NULL,                   -- JSON TaskContract
  attempt   INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE task_deps (
  task_id    TEXT NOT NULL,
  depends_on TEXT NOT NULL,
  PRIMARY KEY (task_id, depends_on)
);
```

Projection tables have no foreign key and no `CHECK` constraints: they are disposable, and the payload models are the validation.

**Projection rules:**

- A projector in the adapters layer applies one stored event at a time. Use cases append an event, then apply it; projection tables are never written in any other way.
- A one-row table records the `seq` of the last applied event. When the database is opened, events with a higher `seq` are applied first, so a crash between append and apply repairs itself.
- Rebuilding means dropping the projection tables, recreating them, and applying every event in `seq` order. It is a function covered by tests, not a CLI command.
- A rebuild is identical when, for every projection table, the rows read in primary-key order are equal before and after. The projector therefore uses only data in the event: no clock, no generated ids, no file reads. `approved_at`, `started_at` and `ended_at` come from the events' `created_at`.
- Each milestone adds the tables for the events it introduces: M1 `spec_versions`, `requirements`, `adrs`; M2 `plans`, `tasks`, `task_deps`, `agent_runs`. `trace_links` is built in M5. A projection added later is filled by a rebuild.

**Event types in Phase 1:** `SpecImported`, `SpecValidated`, `SpecApproved`, `PlanCreated`, `PlanApproved`, `TaskStateChanged`, `AgentRunStarted`, `AgentRunFinished`, `GateEvaluated`, `CommitRecorded`, `ImpactComputed`. Approvals are recorded by `SpecApproved` and `PlanApproved` with actor `human`; invalidation is a `TaskStateChanged` to `invalidated` with a reason in its payload.

**Event envelope rules:**

- `event_id`: any valid UUID; new events use UUID4.
- `actor`: one of `human`, `orchestrator`, or `agent:<role>` (lowercase role name).
- `created_at`: timezone-aware UTC, stored as ISO 8601.
- `payload`: a JSON object.
- `seq` is assigned by the store. New events have no `seq`; stored events always do, and only stored events are replayed.

**Streams and actors:**

| Event | Stream | Actor |
| --- | --- | --- |
| `SpecImported`, `SpecValidated` | `spec:<spec version id>` | `orchestrator` |
| `SpecApproved` | `spec:<spec version id>` | `human` |
| `PlanCreated` | `plan:<plan id>` | `orchestrator` |
| `PlanApproved` | `plan:<plan id>` | `human` |
| `TaskStateChanged` | `task:<task id>` | `orchestrator` |
| `AgentRunStarted`, `AgentRunFinished` | `run:<run id>` | `orchestrator` |

`human` is used only where a human decision is the event: approvals, and later `resolve`. No M1 or M2 event has actor `agent:<role>`; the orchestrator records what agents did. `causation_id` is set where one event directly causes another: for example, each `TaskStateChanged` written by `approve plan` points at the `PlanApproved` event.

**Event payloads:**

Each event type has one payload model in the domain, and the models forbid unknown fields. Use cases build events through these models. The envelope itself accepts any JSON object; the projector validates each payload against its model before applying it and fails on a mismatch. Each payload carries everything its projections hold, because the spec files and an LLM's reply cannot be read again at replay.

```
SpecImported
  spec_version: "sv_01"
  hash:         "<64 hex>"            # spec set hash
  spec:         { components, requirements, adrs }   # the full spec set, ADR bodies included, stored in canonical order (sorted as for hashing)

SpecValidated
  spec_version: "sv_01"
  hash:         "<64 hex>"
  violations:   [ { rule, subject, message } ]       # rule is a plain string
  warnings:     [ { check, subject, message } ]      # always empty in Phase 1

SpecApproved
  spec_version: "sv_01"
  hash:         "<64 hex>"

PlanCreated
  plan_id:      "plan_01"
  spec_version: "sv_01"
  policy_hash:  "<64 hex>"
  run_id:       "run_0001"            # the planner run that produced it
  tasks:        [ TaskContract ]      # complete contracts, as the orchestrator stored them

PlanApproved
  plan_id:      "plan_01"

TaskStateChanged
  task_id:      "AUTH-002"
  from:         "pending"
  to:           "ready"
  reason:       null | "<text>"       # required when to = invalidated

AgentRunStarted
  run_id:       "run_0001"
  task_id:      null | "AUTH-002"     # null for a planner or classifier run
  role:         "planner"
  runtime:      "claude-code"
  context_hash: "<64 hex>"            # for a planner run, the hash of the prompt

AgentRunFinished
  run_id:       "run_0001"
  exit:         "ok" | "error" | "timeout"
  model:        "<model name>" | null
  tokens_in, tokens_out, cost_usd, duration_s
  error:        null | "<text>"
```

Item hashes are not in `SpecImported`; the projector computes them from the content. The payloads of `GateEvaluated`, `CommitRecorded` and `ImpactComputed` are defined when their milestones are planned.

**Ids:** spec version ids (`sv_NN`), plan ids (`plan_NN`) and run ids (`run_NNNN`) are chosen by the use case from the projections when a command runs, and are then fixed in the event. Replay never generates ids.

## Task contract

The planner LLM emits tasks in the shape of `PlannedTask`; the orchestrator completes each one into a `TaskContract`. Pydantic rejects anything that doesn't validate, and the plan is rejected if the DAG has a cycle or references an unknown requirement.

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
# set by the orchestrator, never by the planner:
required_gates: [path_check, ruff, pytest, gitleaks, review]
limits:
  max_runtime_s: 1200
  max_attempts: 2
  max_cost_usd: 1.50
```

```python
class PlannedTask(BaseModel):
    """What the planner emits."""
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(pattern=r"^[A-Z]+-\d{3}$")
    objective: str
    requirements: list[str] = Field(min_length=1)
    acceptance_criteria: list[str] = Field(min_length=1)
    depends_on: list[str] = []
    components: list[str]
    role: Literal["implementer", "reviewer"]
    allowed_paths: list[str] = Field(min_length=1)
    forbidden_paths: list[str] = []

class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_runtime_s: int = Field(gt=0)
    max_attempts: int = Field(gt=0)
    max_cost_usd: float = Field(gt=0)

class TaskContract(PlannedTask):
    """What is stored and executed."""
    required_gates: list[Literal["path_check", "ruff", "pytest", "gitleaks", "review"]]
    limits: Limits
```

The planner does not emit `required_gates` or `limits`; a reply that contains either fails validation. For every task, the orchestrator:

- sets `forbidden_paths` to the policy's list followed by the planner's, without duplicates;
- sets `required_gates` to `[path_check, ruff, pytest, gitleaks, review]`;
- sets `limits` from the policy's `max_runtime_s`, `max_attempts` and `max_cost_usd`.

So the planner can never widen access past policy, drop a gate, or raise a limit. The completed contract is what `PlanCreated` and `tasks.contract` hold.

**Planning:**

- `openfactory plan` uses the latest approved spec version. It fails if there is none, and warns if the files on disk differ from it. It fails if an approved plan already exists for that spec version; changing an approved plan is `replan`.
- The planner receives one prompt and no tools: the requirements that are not deprecated, their acceptance criteria, the bodies of the ADRs they are constrained by, the declared components, the policy's forbidden paths, the names of the gates, and the list of tracked files from `git ls-files`. It receives no file contents.
- The planner replies with `{"tasks": [PlannedTask, ...]}`.
- Plan ids are `plan_NN`, counted from `plan_01`.
- A task id is unique among all tasks in the `tasks` projection. `invalidated` is a terminal state, so a revised task in a later plan always gets a new id.
- Running `plan` again while a draft plan exists records a new `PlanCreated`. The projector marks the earlier draft `superseded` and removes its tasks from `tasks` and `task_deps`; they never ran, and they remain in the event log. The new draft may reuse their ids.

**Plan checks:** besides a cycle and an unknown requirement, a plan is rejected when:

- two tasks share a `task_id`;
- `depends_on` names a task that is not in the plan;
- an acceptance criterion is unknown, or does not belong to one of the task's requirements;
- a component is not declared in the spec;
- a task names a deprecated requirement;
- a requirement that is not deprecated, or one of its acceptance criteria, appears in no task.

All rejections are collected into one list and get the same single retry as a Pydantic failure. If the second reply is also rejected, `plan` exits non-zero and no `PlanCreated` is recorded.

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

A task is created `pending` by `PlanCreated`; the initial state has no `TaskStateChanged` event. When its plan is approved, a task with no dependencies moves to `ready`. A task with dependencies stays `pending` until they have passed.

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

- Stored per agent run, with role and model name. A planner or classifier call is recorded as an agent run with its role and no task: `AgentRunStarted`, then `AgentRunFinished`. A retried call is a second run, so a rejected call keeps its cost.
- `openfactory stats` prints totals per task, per plan, and per role, plus p50 and p95 run latency.
- A task's `max_cost_usd` is checked after each run; exceeding it escalates the task.
- The final report includes total cost of the initial build and of the replan, which shows the saving from re-executing only impacted work.

## CLI commands

| Command | Does |
| --- | --- |
| `openfactory init <repo>` | Creates `.openfactory/`, the SQLite file and, if missing, a default `specs/policies.yaml` |
| `openfactory validate` | Runs the deterministic spec checks |
| `openfactory approve spec` | Freezes the current spec as a new version |
| `openfactory plan` | Generates a task DAG for the approved spec |
| `openfactory approve plan` | Marks the latest draft plan approved; tasks with no dependencies become `ready` |
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

**`init`:**

- `<repo>` must be an existing git repository; otherwise `init` fails.
- It creates `<repo>/.openfactory/openfactory.db`, and `<repo>/.openfactory/.gitignore` containing `*`, so the directory ignores itself without touching the repo's own `.gitignore`.
- It creates `<repo>/specs/policies.yaml` with the defaults, creating `specs/` if needed. An existing file is never overwritten.
- It is safe to repeat: it creates what is missing and reports what already exists. It records no events.

**Other commands** run against the current directory and fail with "run `openfactory init` first" if `./.openfactory/` is missing. There is no search of parent directories.

**Output:**

- `validate` prints one line per violation as `rule  subject  message`, then a count. It exits with 1 if there is any violation, otherwise 0.
- `approve plan` fails if there is no draft plan.
- `events` prints one JSON object per line, in `seq` order.

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

1. **Specs and events.** `init`, `validate`, `approve spec`, `events`; events table and the spec projections; replay rebuilds projections identically.
2. **Planner.** `plan`, `approve plan`; Claude Code LLM adapter; contract validation, cycle check, unknown-requirement check; the plan, task and agent run projections; the deleted-requirement rule.
3. **Executor.** One task end to end: worktree, context pack, Claude Code run, path check, commit with trailers.
4. **Gates and remediation.** ruff, pytest with req markers, gitleaks, reviewer; retry with failure context; escalation.
5. **Traceability.** `trace`, `why`, `coverage`; the `trace_links` projection; rebuild links from git trailers alone.
6. **Impact and replan.** Structural diff, classifier, traversal, `impact`, `replan`, partial re-execution.
7. **Eval, report and demo.** Eval suite with results, `stats`, `report`, a demo video, and a design write-up.

**Phase 1 is done when:**

- [ ] The 9-step demo runs on the target repo with no manual code edits.
- [ ] Every platform commit has trailers and resolves in `openfactory why`.
- [ ] Eval meets the recall and precision targets.
- [ ] Killing the process mid-run and restarting resumes from the event log without duplicate commits.
- [ ] README, design write-up and demo video are published.
