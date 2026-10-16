# OpenFactory — Phase 1 Spec

Version 1.16 · 2026-10-16 · Owner: Muhammed

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
| Three agent roles: planner, implementer, reviewer; plus a change classifier call | Requirements, architecture, security, docs, DevOps agents |
| Sequential task execution, one worktree per task | Parallel execution, merge-conflict handling |
| Local git branches and commits | Push, PRs, GitHub provider |
| Deterministic gates: pytest, ruff, gitleaks, path check | Semgrep, Trivy, CI integration |
| SQLite + append-only events | PostgreSQL, NATS, durable workflow engine |
| Deterministic spec validation | Advisory LLM spec checks (vague wording, possible duplicates) |
| Requirement-level semantic diff | Full spec conflict detection, ADR contradiction detection |
| Bounded remediation: retries up to `max_attempts`, with failure context | Failure classifier, multi-step self-healing |
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
| Spec files | YAML, read with PyYAML (`yaml.load` with a `SafeLoader` subclass that rejects duplicate keys); merge keys (`<<`) are rejected as a `schema` violation; anchors and aliases are expanded by PyYAML |
| Storage | SQLite via the standard `sqlite3` module, WAL mode |
| Agent runtime | Claude Code headless (`claude -p` with JSON output) behind `AgentExecutor` |
| Planner, reviewer and diff LLM calls | Claude Code headless (`claude -p --output-format json --json-schema`) behind `LLMProvider`, validated by Pydantic |
| Git | Git CLI via `subprocess` |
| Graph queries | Recursive SQL CTEs; the plan's cycle check is plain Python, with no graph library |
| Tests | pytest |
| Lint and format | ruff |
| Secret scan | gitleaks |
| Logging | structlog, JSON lines; a log line has the keys `event` and `level` |

All model calls go through Claude Code using the user's Claude subscription login; no API key is required. Claude Code would use `ANTHROPIC_API_KEY` instead of the subscription if it were set, so the adapters start `claude` with that variable removed from its environment, without reading its value, and log a warning if it was present. If a reply fails Pydantic validation or has no structured result, the call is retried once with the validation error in the prompt, then fails. A planner, reviewer or classifier call runs with no tools, a 300 second time limit and the default model, in a new empty directory. A non-zero exit, a `claude` that cannot be started, an envelope that cannot be parsed, or a timeout is a failed process: it is not retried, the run is recorded with `exit: error` or `timeout` and `error` set, and the command exits 1. A failed reviewer process, or a reviewer reply rejected twice, is the exception: it fails the `review` gate and `run` goes on (see Gates and remediation). An envelope that cannot be parsed is output that is not JSON, or JSON without the fields the adapter reads. An envelope that parses but whose structured result is missing (a JSON `null` counts as missing) or fails Pydantic validation is a rejected reply.

```
src/openfactory/
  domain/          # pure models, state machine, rules; no I/O (the modules below are examples, not the full list)
    models.py      # Requirement, Task, AgentRun, Gate, ...
    states.py      # task state machine + allowed transitions
    events.py      # event types
    payloads.py    # one payload model per event type
  app/             # use cases: validate, plan, run, impact, replan
  ports/           # interfaces: EventStore, EventRecorder, SpecVersions, Plans, Runs, SpecFiles, RunFiles, AgentExecutor, WorkspaceManager, GitProvider, LLMProvider, GateRunner
  adapters/        # sqlite_store, sqlite_events, sqlite_projector, sqlite_recorder, sqlite_spec_versions, sqlite_plans, sqlite_runs, filesystem_spec_files, filesystem_run_files, claude_code_executor, claude_code_llm, git_cli, git_worktree, process_gates, pytest_plugin/openfactory_req.py
  cli.py
tests/
  unit/ integration/ eval/
```

The path check is a pure function in the domain. The gates that start a process (ruff, pytest, gitleaks) run behind the `GateRunner` port, whose adapter is `process_gates` (see Gates and remediation). `pytest_plugin/openfactory_req.py` is the pytest plugin the `pytest` gate loads into the target repo's tests; it is not imported by OpenFactory's own code.

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
- An ADR file starts with a line `---`, then YAML front matter, then a line `---`. Everything after that is the body. Front matter that is not a YAML mapping is a `schema` violation.
- The `id` in front matter is authoritative; the file name is not checked.
- Files are read as UTF-8. Line endings in an ADR body are normalised to `\n`: `\r\n` and a lone `\r` both become `\n`. The body is not trimmed.
- An empty `requirements.yaml` is a `schema` violation. So is a top-level `adrs` key in it: ADRs come only from `adrs/*.md`.
- PyYAML reads YAML 1.1, so an unquoted `no`, `on` or date is not a string, and is a `schema` violation where a string is expected.
- Spec files are read through a `SpecFiles` port that returns each file's text by path relative to `specs/` (`requirements.yaml`, `adrs/*.md`, `policies.yaml`). A filesystem adapter implements it. Parsing YAML and ADR front matter happens in the application layer.

**Validation rules (deterministic, run by `openfactory validate`):**

- IDs match `REQ-[A-Z]+-\d{3}`, `ADR-\d{3}` and `AC-[A-Z]+-\d{3}-\d+`, and are unique across the whole spec set.
- Every requirement has at least one acceptance criterion.
- Every `constrained_by` reference points to an existing ADR with status `accepted`.
- Every component named by a requirement is declared in the top-level `components` list.
- No requirement is deleted while tasks still reference it, unless the new version marks it `deprecated`. Enforced from M2, when tasks exist. A requirement is deleted when it is in the latest approved spec version and absent from the files being validated. A task still references it when the task is in the `tasks` projection, lists it in its contract, and is in neither state `abandoned` nor `invalidated`. The fix is to restore the requirement with `deprecated: true`. There is one violation per deleted requirement; its message lists the ids of the tasks that reference it, in ascending order as strings. Tasks of a draft plan count.

A file that cannot be loaded into the models is reported under the rule `schema`: a YAML syntax error, a file that is not valid UTF-8, a missing `requirements.yaml`, an ADR file without front matter, or a value the models reject. Its subject is the id of the nearest enclosing item whose id can be read: the acceptance criterion, then its requirement, or the ADR; otherwise the file path relative to the repo. There is one `schema` violation per rejected field, with the field path in its message. When there is any `schema` violation in the spec files, the rules above are not run, because there is no trustworthy spec set to run them on. Policy problems do not count here.

**Spec field rules:**

- `components` is a top-level list of component names in `requirements.yaml`.
- Unknown keys at the top level of `requirements.yaml`, in a requirement and in an acceptance criterion are rejected as a `schema` violation.
- `priority` is one of `must`, `should`, `could`.
- `constrained_by`, `components` and `acceptance_criteria` are optional and default to empty; a requirement with no acceptance criteria is reported by validation rather than rejected while parsing.
- `deprecated` is an optional boolean on a requirement and defaults to `false`. A deprecated requirement is validated like any other, but the planner creates no tasks for it.
- ADR front matter has `id` and `status`; `status` is one of `proposed`, `accepted`, `superseded`. Only `accepted` satisfies `constrained_by`. Other front matter fields are ignored. The ADR model also holds the `body`.
- Validation returns every violation in one run, each with the rule name, the ID it concerns, and a message. It never stops at the first. The rule names are `id-format`, `id-unique`, `missing-acceptance-criteria`, `constrained-by`, `undeclared-component`, `deleted-requirement` (from M2; its subject is the requirement id) and `schema`. The subject of `id-format` and `id-unique` is the offending id; the subject of the other content rules is the requirement id.

**Hashing:**

The hash of a thing is the SHA-256 of the canonical JSON of its parsed model, written as 64 lowercase hex characters.

- Canonical JSON is the model dumped in JSON mode, with sorted keys, separators `,` and `:` with no spaces, non-ASCII characters left as they are, encoded as UTF-8.
- The models are hashed, not the files. Comments, key order, indentation and quoting style do not change a hash, and an omitted optional field hashes the same as its default.
- Order in the files does not matter: before hashing, `requirements`, `adrs` and `acceptance_criteria` are sorted by `id`, then by the item's canonical JSON, so two items with the same id still have one order, and `components` and `constrained_by` as strings.
- Strings are hashed as parsed: no trimming, no case folding, no Unicode normalisation.
- A requirement's hash covers the whole requirement, including its acceptance criteria, so changing a criterion makes its requirement `modified`.
- An ADR's hash covers `id`, `status` and `body`.
- An acceptance criterion's hash covers `id` and `text`. It is not stored; it is computed when the diff needs it.
- The spec set's hash covers the components, the requirements and the ADRs.
- The policy's hash covers its five keys with defaults filled in. Unlike the spec set's lists, its lists are hashed in file order, because their order reaches the task contracts.

A change to the canonical form changes every hash. During Phase 1 development that is handled by discarding the development database, not by versioning the hash.

**Spec versions:**

A spec version has an id of the form `sv_NN` (two digits, counted from `sv_01`, wider when needed) and is either `draft` or `approved`. At most one draft exists at a time.

`openfactory validate` loads the files and hashes the spec set:

- If the spec files cannot be loaded (any `schema` violation in them), `validate` prints the violations, records no events, and exits 1. Policy problems are still printed.
- If the hash equals the latest approved version's, it records no events, its output ends with the status line `matches approved sv_NN`, and it exits 0, or 1 if there are policy problems. The rules are not run. A draft that exists is left as it is.
- If the hash equals the current draft's, it records no `SpecImported`. It runs the rules and records `SpecValidated` for the draft again, because a rule's result can change while the files do not: the deleted-requirement rule depends on the tasks.
- Otherwise it records `SpecImported` (an existing draft keeps its id and its content is replaced; if there is no draft, the next id is used), then runs the rules and records `SpecValidated`.

`openfactory approve spec` does not rely on an earlier `validate`. It loads and hashes the files, imports them if they changed, runs the rules, and refuses if there is any violation. Otherwise it records `SpecApproved`, and the version is immutable from then on. Edits after that create a new draft version on the next `validate` or `approve spec`. If the files equal the latest approved version, it records no events and exits 1 with `nothing to approve`, also when a draft exists.

`approve spec` records `SpecValidated` with the rule results before `SpecApproved`, so every approval is preceded by the validation it was based on. If the spec files cannot be loaded, it prints the violations and any policy problems, records no events, and exits 1, like `validate`. If they load but have violations, it records `SpecImported` (if the files changed) and `SpecValidated` with the violations, then refuses without recording `SpecApproved`.

Because a draft keeps its id until it is approved, approved versions are numbered without gaps.

**Policies:**

`specs/policies.yaml` has five keys. Each is optional with the default shown, and unknown keys are rejected. A file that is empty, holds only comments, or whose top level is `null` is the default policy.

```yaml
# policies.yaml
protected_branches: [main, master]
forbidden_paths: []
max_attempts: 2
max_runtime_s: 1200
max_cost_usd: 1.50
```

- Four baseline paths are always forbidden: `specs/**`, `.openfactory/**`, `.env` and `.env.*`. They are defined in code, not in the policy file, so no policy can remove them.
- `forbidden_paths` adds to the baseline; it never replaces it. It uses the same glob syntax as the paths in a task contract.
- `max_attempts`, `max_runtime_s` and `max_cost_usd` must be greater than zero. They are the limits of every task contract (see Task contract).
- `protected_branches` lists branches the orchestrator refuses to commit on. In Phase 1 the key is inert: the orchestrator commits only on `openfactory/<task id>` branches, which it creates itself, so the rule holds by construction and `run` does not read the policy.
- `openfactory validate` prints policy problems under the rule `schema`, with the file path as subject, and exits 1. It prints them even when the spec files cannot be loaded. Policy problems are not recorded in `SpecValidated`, do not stop the content rules, and do not block `approve spec`.
- `openfactory plan` refuses to run while the policy is invalid.
- A missing file is a policy problem: a `schema` line with subject `specs/policies.yaml` and the message `missing; run openfactory init`, printed on standard output like any other policy line.
- The policy is not part of the spec set and is not covered by a spec version's hash, so editing it does not create a new spec version. It is read when a plan is created, and its own hash is recorded in `PlanCreated`.

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
CREATE TABLE IF NOT EXISTS projection_state (
    id       INTEGER PRIMARY KEY,
    last_seq INTEGER NOT NULL
);
```

**Projections:**

| Table | Holds |
| --- | --- |
| `projection_state` | bookkeeping, not a projection: seq of the last event applied to the projections |
| `spec_versions` | id, hash, status (draft, approved), components, approved_at |
| `requirements` | id, spec_version, title, statement, priority, deprecated, components, constrained_by, acceptance_criteria, hash |
| `adrs` | id, spec_version, status, body, hash |
| `plans` | id, spec_version, status (draft, approved, superseded) |
| `tasks` | id, plan_id, state, objective, contract JSON, attempt, cost_usd |
| `task_deps` | task_id, depends_on |
| `agent_runs` | id, task_id (null for a run that belongs to no task), role, runtime, model, started_at, ended_at, exit, tokens_in, tokens_out, cost_usd, duration_s, context_hash |
| `gate_results` | run_id, gate, passed, output_path |
| `commits` | sha, task_id, run_id, branch |
| `trace_links` | from_kind, from_id, to_kind, to_id, source (spec, trailer, contract, diff, test_tag) |

`trace_links` is the traceability graph: one generic edge table that all queries traverse. Each edge records how it was established, so deterministic and inferred links are never confused. Links declared in the spec files, such as `constrained_by`, have source `spec`.

The tables built in M1 to M4:

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
  attempt   INTEGER NOT NULL DEFAULT 0,
  cost_usd  REAL NOT NULL DEFAULT 0          -- sum of the task's runs' cost_usd since its last `resolve --retry` (M4)
);
CREATE TABLE task_deps (
  task_id    TEXT NOT NULL,
  depends_on TEXT NOT NULL,
  PRIMARY KEY (task_id, depends_on)
);
CREATE TABLE agent_runs (
  id           TEXT PRIMARY KEY,             -- run_0001
  task_id      TEXT,                         -- null for a planner or classifier run
  role         TEXT NOT NULL,
  runtime      TEXT NOT NULL,
  model        TEXT,                         -- null until AgentRunFinished, or when the runtime reported none
  started_at   TEXT NOT NULL,                -- ISO 8601 UTC, from AgentRunStarted.created_at
  ended_at     TEXT,                         -- null until AgentRunFinished; from its created_at
  exit         TEXT,                         -- null until AgentRunFinished
  tokens_in    INTEGER,                      -- null until AgentRunFinished, or when the runtime reported none
  tokens_out   INTEGER,                      -- null until AgentRunFinished, or when the runtime reported none
  cost_usd     REAL,                         -- null until AgentRunFinished, or when the runtime reported none
  duration_s   REAL,                         -- null until AgentRunFinished
  context_hash TEXT NOT NULL
);
CREATE TABLE gate_results (
  run_id      TEXT NOT NULL,
  gate        TEXT NOT NULL,                 -- path_check | ruff | pytest | gitleaks | review
  passed      INTEGER NOT NULL,              -- 0 | 1
  output_path TEXT,                          -- relative to the repo; null when the gate wrote no file
  PRIMARY KEY (run_id, gate)
);
CREATE TABLE commits (
  sha     TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  run_id  TEXT NOT NULL,
  branch  TEXT NOT NULL                      -- openfactory/AUTH-002
);
```

Projection tables have no foreign key and no `CHECK` constraints: they are disposable, and the payload models are the validation.

**Projection rules:**

- A projector in the adapters layer applies one stored event at a time. Use cases record every event through the `EventRecorder` port, `record(event) -> StoredEvent`. Its adapter appends the event and applies it to the projections in one transaction, so an event is never stored without its projections being updated. Recording an `event_id` that is already stored behaves like `EventStore.append`: the same content returns the stored event without applying it again, and different content raises `EventConflictError`. Projection tables are never written in any other way.
- An event type whose milestone has not added a payload model is skipped by the projector.
- When a `SpecImported` holds two requirements, or two ADRs, with the same id, the projector keeps the first in the payload's order and skips the others. Such a version has an `id-unique` violation and can never be approved.
- The projector adds 1 to `tasks.attempt` for each `TaskStateChanged` whose `to` is `running`. A task has attempts left while `attempt < limits.max_attempts`.
- On `AgentRunFinished` the projector adds its `cost_usd`, a null counting as 0, to `tasks.cost_usd` of the run's task, found through `agent_runs.task_id`; a run with no task adds nothing.
- A `TaskResolved` whose `decision` is `retry` sets `tasks.attempt` and `tasks.cost_usd` of its task to 0, so a retried task gets a fresh budget. One whose `decision` is `abandon` changes no row; the `TaskStateChanged` that follows it sets the state.
- `GateEvaluated` inserts one `gate_results` row, and `CommitRecorded` one `commits` row.
- `projection_state` is a bookkeeping table with exactly one row: `id = 1`, holding `last_seq`, the seq of the last event applied. The event recorder creates it and is its only writer. Recording an event appends it to the events table, applies it to the projections, and sets `last_seq` in one transaction. When the recorder opens the database, it applies every event with `seq > last_seq`; if `projection_state` is missing, it is created and catch-up starts from the first event. Because append and apply share a transaction, this catch-up is needed only as a recovery for a database written before they did. If the catch-up meets a stored event it cannot apply, it applies nothing, and a command that opens the recorder fails, naming the event's `seq`.
- Rebuilding means emptying the projection tables (dropping and recreating them counts), replaying all events in `seq` order, and setting `last_seq` to the highest `seq`, or 0 for an empty log, in one transaction; any failure rolls the whole rebuild back. `projection_state` is never dropped. It is a function covered by tests, not a CLI command.
- A rebuild is identical when, for every projection table, the rows read in primary-key order are equal before and after. The projector therefore uses only data in the event: no clock, no generated ids, no file reads. `approved_at`, `started_at` and `ended_at` come from the events' `created_at`.
- Each milestone adds the tables for the events it introduces: M1 `spec_versions`, `requirements`, `adrs`; M2 `plans`, `tasks`, `task_deps`, `agent_runs`; M3 `gate_results`, `commits`; M4 the column `tasks.cost_usd`. `trace_links` is built in M5. A projection added later is filled by a rebuild. A database made before M4 is discarded, as for a change to the canonical form (see Hashing): its `tasks` table has no `cost_usd`.

**Event types in Phase 1:** `SpecImported`, `SpecValidated`, `SpecApproved`, `PlanCreated`, `PlanApproved`, `TaskStateChanged`, `AgentRunStarted`, `AgentRunFinished`, `GateEvaluated`, `CommitRecorded`, `TaskResolved`, `ImpactComputed`. Approvals are recorded by `SpecApproved` and `PlanApproved` with actor `human`, and a human's decision on an escalated task by `TaskResolved`; invalidation is a `TaskStateChanged` to `invalidated` with a reason in its payload.

**Event envelope rules:**

- `event_id`: any valid UUID; new events use UUID4.
- `actor`: one of `human`, `orchestrator`, or `agent:<role>` (lowercase role name).
- `created_at`: timezone-aware UTC, stored as ISO 8601.
- `payload`: a JSON object.
- `seq` is assigned by the store. New events have no `seq`; stored events always do, and only stored events are replayed. `seq` increases but may have gaps.

**Streams and actors:**

| Event | Stream | Actor |
| --- | --- | --- |
| `SpecImported`, `SpecValidated` | `spec:<spec version id>` | `orchestrator` |
| `SpecApproved` | `spec:<spec version id>` | `human` |
| `PlanCreated` | `plan:<plan id>` | `orchestrator` |
| `PlanApproved` | `plan:<plan id>` | `human` |
| `TaskStateChanged` | `task:<task id>` | `orchestrator` |
| `AgentRunStarted`, `AgentRunFinished` | `run:<run id>` | `orchestrator` |
| `GateEvaluated`, `CommitRecorded` | `task:<task id>` | `orchestrator` |
| `TaskResolved` | `task:<task id>` | `human` |

`human` is used only where a human decision is the event: approvals and `resolve`. No Phase 1 event has actor `agent:<role>`; the orchestrator records what agents did. `causation_id` is set where one event directly causes another: for example, each `TaskStateChanged` written by `approve plan` points at the `PlanApproved` event. For the spec events (`SpecImported`, `SpecValidated`, `SpecApproved`), `causation_id` is the `event_id` of the event recorded just before it in the same command; the first event a command records has none.

`plan` records `AgentRunStarted` before each planner call and `AgentRunFinished` after it; a retried call is a second pair; then `PlanCreated`. For these events `causation_id` is the `event_id` of the event recorded just before it in the same command, and the first has none. `approve plan` records `PlanApproved`, with no `causation_id`, then one `TaskStateChanged` per task with no dependencies, in ascending task id as strings, each pointing at `PlanApproved`. `resolve` records `TaskResolved`, with no `causation_id`, then one `TaskStateChanged` pointing at it. The events of `run` and their `causation_id` are given under Execution.

**Event payloads:**

Each event type has one payload model in the domain, and the models forbid unknown fields. Every field of a payload model is required, nullable ones included. The spec set inside `SpecImported` and the contracts inside `PlanCreated` use their own models and defaults; the use case writes every field of them explicitly. Use cases build events through these models. The envelope itself accepts any JSON object; the projector validates each payload against its model before applying it and fails on a mismatch. Each payload carries everything its projections hold, because the spec files and an LLM's reply cannot be read again at replay.

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
  tasks:        [ TaskContract ]      # complete contracts, as the orchestrator stored them, sorted by task_id as strings; the lists inside a contract keep their order

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
  context_hash: "<64 hex>"            # the SHA-256 of the run's prompt text encoded as UTF-8; for an implementer run the prompt is the context pack

AgentRunFinished
  run_id:       "run_0001"
  exit:         "ok" | "error" | "timeout"
  model:        "<model name>" | null
  tokens_in:    <int> | null          # null when the runtime reported none
  tokens_out:   <int> | null          # null when the runtime reported none
  cost_usd:     <float> | null        # null when the runtime reported none
  duration_s:   <float>               # as the runtime reported it, or measured by the adapter when the process failed or timed out
  error:        null | "<text>"
  # for a failed process, model, tokens and cost are read from its standard output when that is a JSON object, each null when absent

GateEvaluated
  run_id:       "run_0002"            # the implementer run whose result the gate judged
  task_id:      "AUTH-002"
  gate:         "path_check"          # one of the five gate names
  passed:       true | false
  output_path:  null | "<path>"       # relative to the repo; null when the gate wrote no file

CommitRecorded
  sha:          "<40 hex>"
  task_id:      "AUTH-002"
  run_id:       "run_0002"
  branch:       "openfactory/AUTH-002"
  spec_version: "sv_01"               # the plan's spec version
  files:        [ "<path>" ]          # the paths the commit changed, relative to the repo, sorted as strings

TaskResolved
  task_id:      "AUTH-002"
  decision:     "retry" | "abandon"
```

`AgentRunStarted.role` is one of `planner`, `implementer`, `reviewer`, `classifier`. `runtime` is a plain string; Phase 1 writes `claude-code`. When the runtime reports several models, `model` is the one with the most output tokens, the first on a tie.

The closed sets a stored payload holds (a requirement's `priority`, an ADR's `status`, a task's `role` and `required_gates`, a run's `role` and `exit`, a gate result's `gate`, a resolve's `decision`, and the task states) may be widened but never renamed or narrowed, so every stored event still validates.

Item hashes are not in `SpecImported`; the projector computes them from the content. The payload of `ImpactComputed` is defined when its milestone is planned.

**Ids:** spec version ids (`sv_NN`), plan ids (`plan_NN`) and run ids (`run_NNNN`) are chosen by the use case from the projections when a command runs, and are then fixed in the event. Replay never generates ids. Use cases read the spec version projections through the `SpecVersions` port, a read-only port that gives the latest approved version, the current draft, the next spec version id and the stored spec set of a version. They read the plan and task projections through the `Plans` port: the current draft plan, the approved plan if there is one, the next plan id, the tasks of a plan with their dependencies, the live tasks that reference a requirement, the latest commit of a plan with its task id, and the last gate result of a task (for `status`). The `Runs` port gives the next run id and the unfinished run of a task. Both are read-only. The list of tracked files comes from `GitProvider`, whose first adapter is `git_cli`.

M3 adds what `run` needs. `GitProvider` also gives the commit `HEAD` points at and the tracked files of a worktree, stages the changes of a worktree and lists the paths that differ from a commit, resets a branch softly, and makes a commit; these operations take the worktree's path. `WorkspaceManager`, whose adapter is `git_worktree`, creates and removes a task's worktree and branch. `RunFiles`, whose adapter is `filesystem_run_files`, writes a file of a run under `.openfactory/runs/<run id>/` and returns its path relative to the repo. `AgentExecutor`, whose adapter is `claude_code_executor`, is given under Execution.

M4 adds what the gates and the retry need. `GitProvider` also gives the text of `git diff --cached <base>` in a worktree, for the reviewer. `RunFiles` also reads a run file by the path it returned. `GateRunner`, whose adapter is `process_gates`, runs a gate that starts a process and names the first of `uv` and `gitleaks` missing from `PATH`; it is given under Gates and remediation.

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
  - specs/**
  - .openfactory/**
  - .env
  - .env.*
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
    role: Literal["implementer"]
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

- sets `forbidden_paths` to the baseline paths, then the policy's list, then the planner's, without duplicates;
- sets `depends_on` to the planner's list without duplicates, each id at its first position;
- sets `required_gates` to `[path_check, ruff, pytest, gitleaks, review]`;
- sets `limits` from the policy's `max_runtime_s`, `max_attempts` and `max_cost_usd`.

So the planner can never widen access past the baseline and the policy, drop a gate, or raise a limit. The completed contract is what `PlanCreated` and `tasks.contract` hold.

**Path patterns:** an entry of `allowed_paths` or `forbidden_paths` is a pattern, matched against a path relative to the repo root, with `/` separators, case-sensitively.

- `*` matches any run of characters except `/`.
- `**` as a whole segment matches zero or more segments.
- `?` matches one character except `/`.
- A pattern that ends with `/` is the same as that pattern followed by `**`.
- A pattern with no `/` matches a file of that name in any directory, so `.env` and `.env.*` cover every directory, and `*.py` in `allowed_paths` allows a Python file in every directory.
- There are no negations and no character classes: `!` and `[` are literal characters.

**Planning:**

- `openfactory plan` uses the latest approved spec version. It fails if there is none, and warns if the files on disk differ from it. It fails if an approved plan exists, for any spec version; changing an approved plan is `replan`, built in M6.
- `openfactory plan` refuses to run while `specs/policies.yaml` is invalid.
- `openfactory approve plan` fails if the draft's spec version is not the latest approved version.
- The planner receives one prompt and no tools: the requirements that are not deprecated, their acceptance criteria, the bodies of the ADRs they are constrained by, the declared components, the baseline and the policy's forbidden paths, the names of the gates, and the list of tracked files from `git ls-files`, each name as it is, unquoted. It receives no file contents. The prompt states the path pattern syntax. It also states that every task adds tests under `tests/` that carry a `req` marker for each of its requirements, so its `allowed_paths` covers the test files it writes.
- The planner replies with `{"tasks": [PlannedTask, ...]}`.
- Plan ids are `plan_NN` and run ids `run_NNNN`, counted from `plan_01` and `run_0001`, wider when needed; the next id is one more than the highest in use, superseded plans included.
- A task id is unique among all tasks in the `tasks` projection. `invalidated` is a terminal state, so a revised task in a later plan always gets a new id.
- Running `plan` again while a draft plan exists records a new `PlanCreated`. The projector marks the earlier draft `superseded` and removes its tasks from `tasks` and `task_deps`; they never ran, and they remain in the event log. The new draft may reuse their ids.

**Plan checks:** a reply is rejected under one of these rules.

| Rule | Rejected when | Subject |
| --- | --- | --- |
| `schema` | Pydantic rejects the reply, or its structured result is missing | the `task_id` of the task the error lies in when that value is a string, otherwise `reply` |
| `duplicate-task-id` | two tasks share a `task_id` | the task id |
| `unknown-dependency` | `depends_on` names a task that is not in the plan | the task id |
| `cycle` | the task lies on a cycle: it can reach itself through `depends_on` | the task id |
| `unknown-requirement` | a task names a requirement that is not in the spec version | the task id |
| `deprecated-requirement` | a task names a deprecated requirement | the task id |
| `unknown-criterion` | an acceptance criterion is unknown, or does not belong to one of the task's requirements | the task id |
| `undeclared-component` | a component is not declared in the spec | the task id |
| `uncovered` | a requirement that is not deprecated, or one of its acceptance criteria, appears in no task | the requirement id or the acceptance criterion id |

There is one rejection per subject and offending id, and the message names the offending id: one `duplicate-task-id` per duplicated id, one `cycle` per task that lies on a cycle, one `uncovered` per id that appears in no task. A `schema` rejection for a Pydantic error has the field path in its message. When there is any `schema` rejection, the other checks are not run. There is one `schema` rejection per Pydantic error. A reply whose structured result is missing is one `schema` rejection with subject `reply` and the message `no structured result`. These names are the plan's own set, separate from the validation rule names.

A reply with no tasks is accepted only when the spec set has no requirement that is not deprecated (otherwise `uncovered` rejects it); the plan is then created with no tasks and `plan` prints only `created plan_NN`.

A reply rejected by Pydantic or by the plan checks, a reply with no structured result included, is retried once with the same prompt and the rejection lines added to it; one `plan` makes at most two planner calls, whichever kind of rejection the first reply had. `AgentRunFinished` is recorded after the checks: a rejected reply has `exit: ok` and `error` set to its rejection lines, as `rule  subject  message` in the sorted order `plan` prints them, joined by newlines; an accepted one has `error: null`. If the second reply is also rejected, `plan` exits 1 and no `PlanCreated` is recorded.

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

A task is created `pending` by `PlanCreated`; the initial state has no `TaskStateChanged` event. When its plan is approved, a task with no dependencies moves to `ready`. A task with dependencies stays `pending` until they have passed; `run` then moves it to `ready` (see Execution).

Failures loop back to `ready` until attempts run out; path or secret violations and the cost limit skip the retry and escalate at once, as two events, to `failed` and then to `escalated` (see Gates and remediation). Any task not currently running can be invalidated by a spec change. The `run` and `resolve` use cases check every transition against `TRANSITIONS` before they record it; a transition that is not there is a programming error, and the use case raises before recording anything.

The dependents of an `escalated` task stay `pending` until it is resolved to a retry and passes, or until `replan` (M6); the dependents of an `abandoned` task stay `pending` until `replan`.

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

**`run`:**

- `run` works on the approved plan, whatever the latest approved spec version is; `replan` (M6) handles a newer one.
- It refuses with one line on standard error and exits 1, before any event. The refusals, checked in this order: `no approved plan`; `repository has no commit`, when `HEAD` points at no commit, also when the plan already has a commit; `git failed: <error>`, when a git command fails before the repair, with `<error>` the first line of the failure's text; `<tool> not found`, when `uv` or `gitleaks` is not on `PATH`, with `<tool>` the first of the two that is missing, as `GateRunner.missing_tool()` gives it.
- It then repairs the plan (see Restart).
- It then repeatedly takes the `ready` task with the lowest task id, as strings, one at a time, and runs the per-task sequence on it. A task that a failure moved back to `ready` (see Remediation) is taken again in the same invocation by the same rule.
- After a task passes, every `pending` task of the plan whose dependencies have all passed moves to `ready`, in ascending task id as strings, and is taken in the same invocation.
- A task that does not pass does not stop the others.
- `--task ID` runs that task only, its retries included. After the repair it refuses with `unknown task <ID>` when the approved plan has no such task, or `<ID> is <state>, not ready`; these two refusals come after the repair, so the repair's events stay recorded and its warnings are written to standard error before the refusal line. The tasks its pass makes `ready` are moved to `ready` and not taken.
- Only one `run` works on a repo at a time; nothing enforces it.

**Per-task sequence:**

1. Record `ready` to `running`. Remove the task's worktree and branch if they exist, then `git worktree add .openfactory/worktrees/AUTH-002 -b openfactory/AUTH-002 <base>` (see Base and branches).
2. Build the context pack and hash it; the hash is the run's `context_hash`.
3. Record `AgentRunStarted`, call `AgentExecutor.run(contract, context, workdir, output_dir)`, and record `AgentRunFinished`. The Claude Code adapter runs headless with a restricted tool allowlist and the worktree as its working directory, and parses token usage and cost from its JSON output.
4. After the agent exits with `exit: ok`, the orchestrator runs the path check. It is the `path_check` gate: it is evaluated once, first, and records one `GateEvaluated`. Any violation fails the task, whatever the agent claims.
5. Run the other required gates in the worktree, in the order given under Gates and remediation.
6. If all gates pass, the orchestrator itself commits with trailers (see Traceability), records `CommitRecorded`, moves the task to `passed` and removes the worktree; the branch stays.

**Base and branches:** execution is a single chain. `<base>` is the `sha` of the `commits` row with the highest run id, compared by number, among the tasks of the plan; when the plan has no commit, it is the commit `HEAD` of the repo points at when the task starts. Each task branch therefore contains every earlier passed task, and the branch of the task that passed last holds the whole build. The orchestrator never merges. It commits only on `openfactory/<task id>` branches; the branch namespace `openfactory/*` and the directory `.openfactory/worktrees/` are its own, and it removes and creates branches and worktrees there freely. The human's checkout and branches never change. A worktree is created from a commit, so uncommitted work in the checkout is not in it.

**The context pack** is one prompt text (`ContextPack` is a `str`):

- the implementer's instructions, which require every new test to be under `tests/` and to carry a `req` marker, forbid `git commit`, and tell the agent to leave no file outside `allowed_paths`, by-products of the tools it runs included (for example `__pycache__/`);
- the task contract;
- the requirements and acceptance criteria the contract names and the bodies of the ADRs they are constrained by, all from the plan's spec version as stored;
- the names of the tracked files in the worktree that match `allowed_paths`;
- the failure report of the previous attempt if this is a retry (see Remediation).

It holds no contents of the repo's files; the agent reads them with its tools. A retry's failure report holds the text of the gates' output files, which may quote lines of code. `context_hash` is the SHA-256 of the text encoded as UTF-8, as for a planner run.

**The agent call:** an implementer run starts `claude -p --output-format json` in the worktree with exactly the tools `Read`, `Glob`, `Grep`, `Edit`, `Write` and `Bash`, all approved in advance and no others available, the default model, and a time limit of the contract's `max_runtime_s`. The exact command-line flags are fixed by the task that builds the adapter. A non-zero exit, a `claude` that cannot be started, an envelope that cannot be parsed, an envelope that reports an error, or a timeout is a failed process: the run has `exit: error` or `timeout` and `error` set, the task fails, and `run` goes on. The agent run loads the target repo's own Claude Code files from the worktree; they are not covered by `context_hash`. The adapter passes the tool list on the command line; the path check stays the enforcement.

**The path check:** the orchestrator runs `git add -A` in the worktree, then `git diff --cached --name-only -z --no-renames <base>`. The paths this prints are the changed paths: they cover untracked files, both names of a rename, and anything the agent committed. A path the repo ignores is outside the check, so a by-product of a tool that the target repo does not ignore is a changed path like any other. A path is a violation when it matches a `forbidden_paths` pattern or matches no `allowed_paths` pattern. When the check fails, the gate's output file lists the violating paths, one per line, and `output_path` holds its path; when it passes, `output_path` is null. A run that changed no path is a failed attempt: no `GateEvaluated` is recorded and nothing is committed.

**The commit:** after an `exit: ok`, once `running` to `gating` is recorded and before the path check, if the branch tip is not `<base>` the orchestrator resets the branch to `<base>` with `git reset --soft`, which keeps the changes staged, so every commit on the branch is the orchestrator's. "The agent never commits" means that no commit of the agent survives. The orchestrator commits what the path check staged, with `--no-verify`, under the repo's configured git identity. `CommitRecorded.files` is the list of changed paths of the path check.

**Events of one task:** for one task `run` records, in order: `TaskStateChanged` `ready` to `running`; `AgentRunStarted`; `AgentRunFinished`; then, when the run's `exit` is `ok`, `running` to `gating`, one `GateEvaluated` per gate run, and either `CommitRecorded` then `gating` to `passed`, or `gating` to `failed`. When the reviewer runs, its `AgentRunStarted` and `AgentRunFinished` (a second pair when its reply is retried) come after the `gitleaks` `GateEvaluated`; they are events of the task for `causation_id`, as the implementer's are.

- A run whose `exit` is `error` or `timeout` goes `running` to `failed` with no gate; the reason is `run error` or `run timeout`.
- A run that changed no path goes `running` to `gating`, then `gating` to `failed` with reason `no changes`.
- A path violation is `gating` to `failed` with reason `path_check`, then `failed` to `escalated` with reason `path violation`.
- When `gitleaks` reported a finding, the task goes `gating` to `failed`, then `failed` to `escalated`, both with reason `secret found`, whichever other gates failed. Otherwise a failed gate other than `path_check` is `gating` to `failed` with reason the name of the first failed gate in `required_gates` order.
- A task over its cost limit goes from `running` or `gating` to `failed`, then to `escalated`, both with reason `cost limit` (see Metrics).
- A `failed` task that does not escalate at once then moves `failed` to `ready`, or `failed` to `escalated` with reason `attempts exhausted` (see Remediation).
- A git command that fails while a task is `running` or `gating` moves the task to `failed` with reason `git: <first line of the error>`, and `run` goes on to the next task. When the worktree cannot be created, no run event is recorded.
- A worktree removal that fails after its task has moved to `passed` (step 6 of the per-task sequence, or step 1 of Restart) changes no state and records no event: `run` writes the warning `worktree of <task id> not removed: <first line of the error>` to standard error and goes on. The warning does not change the exit code.
- Every other `TaskStateChanged` of `run` has a null `reason`.
- `causation_id` is the `event_id` of the event recorded just before it for the same task in the same command; the first event of a task in a command has none. The exception is a `pending` to `ready` event recorded after a pass: it points at the `gating` to `passed` event of the task that passed. The repair's events count as events of the same command, so the first event `run` records for a task the repair touched points at that task's last repair event.

**Restart:** `run` starts by repairing the approved plan from the projections, in this order.

1. A task in `gating` that has a `CommitRecorded` moves to `passed`, and its worktree is removed.
2. Every other task in `running` or `gating` moves to `failed` with reason `interrupted`, except a `gating` task whose `GateEvaluated` events recorded after its last `running` to `gating` include a failed `path_check`, which moves to `failed` with reason `path_check`, and one whose events since then include a failed `gitleaks`, which moves to `failed` with reason `secret found` (any failed `gitleaks` result counts as a finding here, since `GateEvaluated` cannot tell them apart). These events are read from the task's stream through the `EventStore` port, as in step 3. If it has an unfinished run, that run gets `AgentRunFinished` with `exit: error`, `error: interrupted`, `duration_s: 0` and null in the other nullable fields. `AgentRunFinished` is recorded first, then the `TaskStateChanged`.
3. Every `failed` task, including those step 2 just failed, is settled, in ascending task id as strings: one whose last `failed` reason escalates at once (`path_check`, `secret found`, `cost limit`) moves to `escalated` with that escalation's reason (`path violation`, `secret found`, `cost limit`); the others follow the attempts rule of Remediation. The reason is read from the task's stream through the `EventStore` port.
4. Every `pending` task that has no dependencies, or whose dependencies have all passed, moves to `ready`, in ascending task id as strings.

The events of the repair have no `causation_id`, and the repair prints nothing but that warning. An interrupted attempt counts as an attempt. Because a task's worktree and branch are removed and created again before each attempt, a commit made without its `CommitRecorded` becomes unreachable, so the history never holds two commits for one task.

**Isolation, honestly stated:** in Phase 1, the path check after the run is the real enforcement; Claude Code's own permission settings are defence in depth. Running the agent in a Docker container with only the worktree mounted is a Phase 1 stretch goal, not a requirement.

**Adapter interface:**

```python
class AgentExecutor(Protocol):
    def run(self, contract: TaskContract, context: ContextPack, workdir: Path, output_dir: Path) -> RunResult: ...

class RunResult(BaseModel):
    exit: Literal["ok", "error", "timeout"]
    model: str | None
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: float | None
    duration_s: float
    error: str | None
    summary: str
```

`output_dir` is the run's directory, `.openfactory/runs/<run id>/`. The adapter writes the runtime's result envelope to `<output_dir>/transcript.json`; the path follows from the run id, so no event holds it. `summary` is the agent's final message, empty when `exit` is `error` or `timeout`, and is used only as the body of the commit. The other fields of `RunResult` become the fields of `AgentRunFinished`.

## Gates and remediation

A task passes only when every required gate passes; the reviewer agent's verdict is recorded but cannot override a failed deterministic gate.

| Gate | Command | Blocks on |
| --- | --- | --- |
| path_check | built in: diff paths vs contract | any changed path of the worktree outside `allowed_paths` or inside `forbidden_paths` |
| ruff | `uv run ruff check` and `uv run ruff format --check` | any error |
| pytest | `uv run pytest --collect-only -q -p openfactory_req tests/` and `uv run pytest -p openfactory_req tests/` | any failure, or a requirement of the task with no tagged test in a changed file |
| gitleaks | `gitleaks git --pre-commit --staged --redact --no-banner --exit-code 3 .` | a finding (exit 3), or any other failure of the scan |
| review | reviewer call reads diff + contract, returns `ReviewVerdict` | `reject` verdict; runs only when the other gates passed |

**Order:** `path_check` runs first (see Execution); when it fails, no other gate runs. Otherwise `ruff`, `pytest` and `gitleaks` all run, in that order, each recording its `GateEvaluated`, so the failure report holds every failure. `review` runs only when all three passed. The reasons a failure records are given under "Events of one task".

**Running a gate that starts a process:** the `GateRunner` port, adapter `process_gates`, has `run(gate, worktree, timeout_s) -> GateOutput`. `GateOutput` holds `passed`, `text`, `finding` and, for `pytest`, the collected marker lines. `finding` is true only when `gitleaks` exits 3, and false for every other gate and outcome; the use case chooses `secret found` from it. Each command runs in the worktree: `ruff` and `pytest` through `uv run`, in the target repo's environment, and `gitleaks` from `PATH`. `timeout_s` is the contract's `max_runtime_s`, applied to each command. A command that cannot be started or runs past `timeout_s` fails its gate, and the text says why. A gate's commands all run; `passed` is true when every one exits 0. For `gitleaks`, exit status 3 (set by `--exit-code 3`) is a finding; any other failure of it is a failed gate that is not a finding. `GateRunner` also gives `missing_tool() -> str | None`, the first of `uv` and `gitleaks` that is not on `PATH`, for the refusal of `run`. The text holds, for each command, its command line, then its standard output, then its standard error. The use case writes `text` through `RunFiles` on a pass and on a failure.

**Target repo:** `ruff` and `pytest` judge the whole worktree. The target repo is a uv project with `ruff` and `pytest` among its development dependencies, its `.gitignore` covers `.venv`, `__pycache__/`, `.pytest_cache/` and `.ruff_cache/`, and at the commit `run` starts from it has no ruff error and no failing test; `run` does not check this. `gitleaks` scans only what the path check staged (with `HEAD` at `<base>`, that is the task's whole change) and prints no secret. Files the gates create after the path check (`.venv`, caches) are neither scanned nor committed: the commit takes only what the path check staged. gitleaks 8.30 or later is required.

**The pytest gate and `req` markers:** OpenFactory ships the plugin `openfactory_req`, a single file under `adapters/pytest_plugin/` that imports only pytest; the adapter puts its directory on `PYTHONPATH`. The plugin registers the `req` marker and, during collection, writes one JSON line per collected test, `{"file": "<path relative to the repo>", "req": ["<id>", ...]}`, to the file named by the environment variable `OPENFACTORY_REQ_OUT`, a temporary file outside the worktree. The lines are read from the `--collect-only` command. The gate fails when `pytest tests/` does not exit 0 (a run that collects no test included), or when, for a requirement in the contract, no collected test that carries its `req` marker is in a file among the path check's changed paths. When the tag rule fails, also when `pytest tests/` itself failed, the use case adds one line per uncovered requirement, `no tagged test in a changed file: <requirement id>`, to the gate's text before writing it.

**The review gate:** one `LLMProvider` call, set up as a planner call (no tools, the 300 second limit, the default model, a new empty directory). Its prompt is the task contract and the text of `git diff --cached <base>` in the worktree. It replies:

```python
class ReviewVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["approve", "reject"]
    comments: str
```

It is recorded as an agent run: `AgentRunStarted` with `role: reviewer`, the task's id and the prompt's `context_hash`, then `AgentRunFinished`; a rejected reply is retried once, as for a planner call. A rejected reviewer reply has `exit: ok` and `error` set to its rejection lines, `schema  reply  <message>`: one per Pydantic error with the field path in its message, or `no structured result` when the structured result is missing, sorted and joined by newlines, as for a planner reply. A failed reviewer process, or a second rejected reply, fails the gate and `run` goes on. The gate's output file holds the verdict and the comments; when there is no verdict, it holds the run's `error`. The `review` gate's `GateEvaluated.run_id` and its file's directory are those of the implementer run it judged.

**Remediation:** after a `failed` event, unless it escalates at once (path violation, secret found, cost limit), the same command moves the task `failed` to `ready`, reason null, pointing at the `failed` event outside the repair (the repair's events have no `causation_id`), when `attempt < limits.max_attempts`; otherwise `failed` to `escalated` with reason `attempts exhausted`, and the task waits for a human (see `resolve`). Every other failure reason retries this way: a failed gate, `run error`, `run timeout`, `no changes`, `git: ...` and `interrupted`. A path violation, a gitleaks finding or the cost limit escalates immediately, with no retry. A retry starts from `<base>` in a new worktree.

The failure report of the previous attempt is the `reason` of the task's last `failed` event and, for each gate that failed in that attempt, its name and the text of its output file. The use case reads the reason and the gate results from the task's stream through the `EventStore` port, and the file text through `RunFiles`. The report may name code the new worktree no longer holds.

Gate output is stored as a file, with its path on `gate_results`, so the audit trail keeps the evidence, not just a pass or fail. The file is `.openfactory/runs/<run id>/<gate>.txt`, written through the `RunFiles` port. `path_check` writes it only on a failure; the other gates write it on a pass and on a failure.

## Traceability

Every link in the graph is established mechanically, never guessed by an LLM. That is what makes impact analysis trustworthy.

| Link | Established by |
| --- | --- |
| requirement → ADR | `constrained_by` in the spec |
| requirement → task | task contract `requirements` |
| task → task | contract `depends_on` |
| task → agent run → commit | orchestrator records them as they happen |
| commit → file | the `files` of `CommitRecorded` |
| test → requirement | pytest marker `@pytest.mark.req("REQ-AUTH-001")`, collected with `pytest --collect-only` |
| test → file | the test file path |

**Commit trailers**, written by the orchestrator:

```
AUTH-002: Implement login endpoint using membership number

<the run's summary>

Task: AUTH-002
Requirements: REQ-AUTH-001
Acceptance-Criteria: AC-AUTH-001-1, AC-AUTH-001-2
Agent-Run: run_0091
Spec-Version: sv_01
```

The subject is `<task id>: <objective>`, cut to 72 characters. The body is the run's `summary`. The trailers are the last paragraph of the message. `Requirements` and `Acceptance-Criteria` list the contract's ids in contract order, joined by `, `. `Agent-Run` is the implementer run, and `Spec-Version` is the plan's spec version.

Trailers make the graph rebuildable from git history alone, even if the SQLite file is lost.

The implementer's instructions require every new test to carry a `req` marker; the pytest gate fails if a task produces no test tagged with its requirements: for each requirement of the contract, a collected test carrying its marker must be in a file the task changed (see Gates and remediation).

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

Every LLM call and agent run records wall-clock latency, and tokens in, tokens out and cost in USD when the runtime reports them, so each task and each plan has a known price. On a Claude subscription the cost is notional: it is the API-rate equivalent that Claude Code reports, and `max_cost_usd` limits apply to that figure. `tokens_in` is every input token the runtime reports: uncached, written to the cache and read from it.

- Stored per agent run, with role and model name. A planner or classifier call is recorded as an agent run with its role and no task: `AgentRunStarted`, then `AgentRunFinished`. A retried call is a second run, so a rejected call keeps its cost.
- `openfactory stats` prints totals per task, per plan, and per role, plus p50 and p95 run latency.
- A task's `max_cost_usd` is checked after each run; exceeding it escalates the task. After each `AgentRunFinished` of a task, implementer or reviewer, and before that run's `exit` is looked at, the orchestrator reads the task's `tasks.cost_usd`: the sum of `cost_usd` over the task's finished runs since its last retry by `resolve`, a null counting as 0. If it is greater than `limits.max_cost_usd`, the task goes from its state (`running` or `gating`) to `failed` and then to `escalated`, both with reason `cost limit`; no further gate runs and nothing is committed; after a reviewer run, no `review` `GateEvaluated` is recorded. The check is built in M4, with the retry it limits.
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
| `openfactory resolve TASK-ID --retry \| --abandon` | Human action on an escalated task: retry or abandon |
| `openfactory stats` | Tokens, cost and latency |
| `openfactory report` | Final traceability report as Markdown |
| `openfactory events [--stream S]` | Raw audit log |

**`init`:**

- `<repo>` must be an existing git repository; otherwise `init` fails. A git repository is an existing directory that contains a `.git` entry, a directory or a file; no `git` process is started, and a sub-directory of a repository is refused. The check runs before anything is created. A refusal writes `not a git repository: <repo>` to standard error.
- It creates `<repo>/.openfactory/openfactory.db`, and `<repo>/.openfactory/.gitignore` containing `*`, so the directory ignores itself without touching the repo's own `.gitignore`.
- It creates `<repo>/specs/policies.yaml` with the defaults, creating `specs/` if needed. An existing file is never overwritten. The default file is the code block under Policies as it stands, its comment line included, with a final newline.
- It is safe to repeat: it creates what is missing and reports what already exists. It records no events.
- It prints one line per item on standard output, in the order `.openfactory/openfactory.db`, `.openfactory/.gitignore`, `specs/policies.yaml`, as `created <path>` or `exists <path>`, with the path relative to `<repo>`. `.openfactory/` and `specs/` are not items.

**Other commands** run against the current directory and fail with "run `openfactory init` first" if `./.openfactory/` is missing. There is no search of parent directories. Only the directory is checked. A command creates a missing `openfactory.db`, and the tables it uses, when it opens the database. A repeated `init` reports a database file that exists as `exists` and leaves it as it is.

**Output:**

- `validate` and `approve spec` print one line per violation and per policy problem as `rule  subject  message`: first the violation lines, sorted by rule name, then by subject, then by message, as strings; then the policy lines, sorted the same way; then a count line that is always printed, `N violations, M policy problems`; then the status line, `matches approved sv_NN` or `approved sv_NN`, when there is one. The three fields are separated by exactly two spaces, with no padding. The count line is not inflected: `1 violations, 0 policy problems`. The sort applies to the printed lines only; `SpecValidated.violations` is recorded in the order the rules returned it. A refused `approve spec` prints no status line.
- `validate` exits with 1 if there is any violation or policy problem, otherwise 0.
- `approve spec` exits 0 on success, and its output ends with the status line `approved sv_NN`; policy problems do not change its exit code. It exits 1 when it refuses because of violations. When there is nothing to approve it still prints the policy lines and the count line on standard output, prints no status line, writes `nothing to approve` to standard error and exits 1.
- `plan` prints one line per task as `task_id  objective`, in ascending task id as strings, then the status line `created plan_NN`, and exits 0. When the second reply is rejected it prints that reply's rejections as `rule  subject  message`, sorted as violation lines are, on standard output, and exits 1.
- `plan` refuses with one line on standard error and exits 1. The refusals, checked in this order: `no approved spec version`; `policy is invalid; run openfactory validate`; `plan_NN is already approved; use replan`; `git ls-files failed: <error>`; `planner call failed: <error>`. `<error>` is the first line of the failure's text; for a planner call that text is `AgentRunFinished.error`.
- When the spec files differ from the latest approved version, or cannot be loaded, `plan` writes the warning `spec files differ from approved sv_NN` to standard error and carries on; the warning does not change the exit code. The warning is written after the first three refusals have been checked and before `git ls-files` runs, so a `plan` refused by one of them writes no warning.
- `approve plan` prints one line per task made ready as `task_id  ready`, in ascending task id as strings, then the status line `approved plan_NN`, and exits 0. It refuses with one line on standard error and exits 1: `no draft plan`, or `plan_NN was made for sv_NN; run openfactory plan` when the draft's spec version is not the latest approved one.
- `run` prints one line per task it took as `task_id  <final state>`, in the order it first took them, where the final state is the task's state when `run` leaves it; a task taken again after a failure still has one line, at the position it was first taken. It exits 0 when every task it took passed, otherwise 1; with no `ready` task it prints nothing and exits 0. Its refusals are given under Execution.
- `status` prints one line per task of the approved plan, in ascending task id as strings, as `task_id  state  attempt/max_attempts  gate`, where `gate` is `<gate> passed` or `<gate> failed` for the last gate, in `required_gates` order, evaluated for the task's latest implementer run that has a gate result, or `-` when there is none, and exits 0. It records no events and does not repair the plan. With no approved plan it writes `no approved plan` to standard error and exits 1.
- `resolve TASK-ID` takes exactly one of `--retry` and `--abandon`; neither or both is a usage error. It records `TaskResolved` with `decision` `retry` or `abandon`, then the orchestrator's `TaskStateChanged` `escalated` to `ready` or `escalated` to `abandoned`, with a null reason, prints `task_id  <state>` and exits 0. It does not run the task. It refuses with one line on standard error and exits 1, before any event, checked in this order: `no approved plan`; `unknown task <ID>`, when the approved plan has no such task; `<ID> is <state>, not escalated`. A task escalated on a path violation or a secret can be retried.
- `events` prints one stored event per line, in `seq` order, as one JSON object with the keys `seq`, `event_id`, `stream`, `type`, `payload` (a nested object), `actor`, `causation_id` and `created_at`, with sorted keys at every level, separators `,` and `:` with no spaces, and non-ASCII characters left as they are; lists keep their stored order. `created_at` is printed as it is stored, in ISO 8601 with the offset `+00:00`, the same form as `approved_at`. `--stream S` selects the events whose `stream` equals `S` exactly. With `--stream S` and no matching events it prints nothing and exits 0.
- A command that fails exits 1; a usage error exits 2.
- Command results (violation, policy, count and status lines; task and rejection lines; event lines) go to standard output. Failure messages (`nothing to approve`, "run `openfactory init` first", the refusals of `plan`, `approve plan`, `run`, `status` and `resolve`, usage errors), warnings and log lines go to standard error.

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
3. **Executor.** `run`; one task end to end: worktree, context pack, Claude Code run, path check, commit with trailers; the gate result and commit projections. M3 builds the whole `run` loop and is tested end to end on one task. M3 evaluated only `path_check`.
4. **Gates and remediation.** `status`, `resolve`; ruff, pytest with req markers, gitleaks, reviewer; retry with failure context; escalation; the cost limit.
5. **Traceability.** `trace`, `why`, `coverage`; the `trace_links` projection; rebuild links from git trailers alone.
6. **Impact and replan.** Structural diff, classifier, traversal, `impact`, `replan`, partial re-execution.
7. **Eval, report and demo.** Eval suite with results, `stats`, `report`, a demo video, and a design write-up.

**Phase 1 is done when:**

- [ ] The 9-step demo runs on the target repo with no manual code edits.
- [ ] Every platform commit has trailers and resolves in `openfactory why`.
- [ ] Eval meets the recall and precision targets.
- [ ] Killing the process mid-run and restarting resumes from the event log without duplicate commits.
- [ ] README, design write-up and demo video are published.

## Version history

| Version | Date | Changes |
| --- | --- | --- |
| 1.16 | 2026-10-16 | Restart step 2 reads the gate results since the last `running` to `gating` through `EventStore` (SC-120); `GateOutput.finding` (SC-121); line 70 names a reviewer reply rejected twice (SC-122); the tag-rule lines also when `pytest tests/` failed (SC-123); no `review` `GateEvaluated` after a cost-limit failure (SC-124); the gitleaks row's "Blocks on" (SC-125). |
| 1.15 | 2026-10-15 | A reviewer reply rejected twice fails the gate (SC-105); the review file with no verdict (SC-106); the reviewer's run events in a task's order (SC-107); "no contents of the repo's files" in the context pack (SC-108); the tag rule's lines in the pytest gate's text (SC-109); tests under `tests/` (SC-110); `GateRunner.missing_tool()` (SC-111); Restart step 2 for a failed `path_check` or `gitleaks` result (SC-112); no `causation_id` for the repair's `failed` to `ready` (SC-113); a database made before M4 is discarded (SC-114); gitleaks `--exit-code 3` (SC-115); the target repo ignores tool by-products (SC-116); the Remediation parenthesis (SC-117); the `tasks.cost_usd` comment (SC-118); a reviewer reply's rejection lines (SC-119). |
| 1.14 | 2026-10-15 | `GateRunner` port, `process_gates`, `uv` and `gitleaks` refusal (SC-84); pytest tag rule in a changed file (SC-85); `openfactory_req` plugin (SC-86); review gate through `LLMProvider`, `ReviewVerdict` (SC-87); gate order, `secret found` (SC-88); retry, failure report, Restart step 3 (SC-89); `resolve`, `TaskResolved` (SC-90); `tasks.cost_usd` and the cost check (SC-91); output of `status` (SC-92); planner told about tagged tests (SC-93); staged, redacted gitleaks scan, gate by-products (SC-94); target repo precondition (SC-95); `run` refusals, soft reset order, causation after the repair, illegal transition, failed-process metrics (SC-97); dependents of escalated and abandoned tasks (SC-102); "retries up to `max_attempts`" (SC-103); "Until M4" sentences removed (SC-104). SC-96, SC-99 and SC-100 changed no text. |
| 1.13 | 2026-10-14 | A worktree removal that fails after a pass: a warning, no state change; `git failed` refusal before the repair (SC-82); order of the two repair events of an interrupted task (SC-83). |
| 1.12 | 2026-10-13 | M3 passes on `path_check` alone (SC-54); behaviour and output of `run` (SC-55); single chain, `<base>`, `protected_branches` inert (SC-56); `GateEvaluated`, `CommitRecorded`, `gate_results`, `commits`, no `agent:<role>` actor (SC-57); the path check and its command (SC-58); path pattern syntax (SC-59); events, reasons and `causation_id` of one task, git failures (SC-60); `tasks.attempt` (SC-61); restart repair, life of a worktree, one `run` at a time (SC-62); `RunResult`, `output_dir`, run files (SC-63); the context pack (SC-64); the commit (SC-65); the agent call (SC-66); the cost limit (SC-67); ports of M3, `gates/` removed (SC-68); working directory of a planner call, the target repo's Claude Code files (SC-69); `run` in M3, `status` and `resolve` in M4 (SC-70); an envelope that reports an error (SC-71); a repo with no commit (SC-72); `run` under a newer spec version (SC-73); `schema` wording for a missing structured result (SC-74); failed process wording (SC-75); `model` with several models (SC-76); tracked file names unquoted (SC-77); the retry prompt (SC-78); a plan with no tasks (SC-79); keys of a log line (SC-80). SC-81 changed no text. |
| 1.11 | 2026-10-11 | Count and subject of `schema` plan rejections, and the line for a reply with no structured result (SC-44); `depends_on` without duplicates in a completed contract (SC-45); when `plan` writes its warning (SC-46); `tokens_in` is every input token reported (SC-47); tokens and cost recorded when the runtime reports them (SC-48); `runtime` is a plain string (SC-49); source of `<error>` (SC-50). SC-51, SC-52 and SC-53 changed no text. |
| 1.10 | 2026-10-11 | DDL of `agent_runs`, with `duration_s` (SC-26); types of `AgentRunFinished`, failed processes and rejected replies, at most two planner calls (SC-27); `Plans` and `Runs` ports, `git_cli` (SC-28); events and `causation_id` of `plan` and `approve plan`, order of `PlanCreated.tasks` (SC-29); plan-check rule names, output of `plan` and `approve plan` (SC-30); `plan` refused while any approved plan exists, stale drafts not approved (SC-31); policy hash (SC-32); `context_hash` of a planner run (SC-33); `PlannedTask.role`, run roles (SC-34); closed sets in payloads are widened only (SC-35); one `deleted-requirement` violation per requirement, draft plans count (SC-36); cached input tokens (SC-38); plan and run ids (SC-39); required payload fields and nested models (SC-40); cycle check without a graph library (SC-41); `--stream` matches exactly (SC-43). SC-37 changed no text. |
| 1.9 | 2026-10-09 | Projector keeps the first of two items with one id (SC-12); tied lines sorted by message, policy lines sorted (SC-13); output of `approve spec` with nothing to approve (SC-14); "ends with the status line" (SC-15); stored order of violations, no status line on a refusal (SC-16); two-space separator, count line not inflected (SC-17); subject of each content rule (SC-18); an `events` line without the term "canonical JSON" (SC-19); `.openfactory/` without its database or tables (SC-20); `init` repository check, output lines and default policy file (SC-21); loader behaviour (SC-22); skipped event types, catch-up failure, `seq` gaps, repo layout (SC-23); the rebuild sentence (SC-24); unknown keys, required payload fields, a missing `policies.yaml` (SC-25). |
| 1.8 | 2026-10-09 | `validate` has three explicit cases and `nothing to approve` records no events (SC-1); output and exit codes of `approve spec`, the form of an `events` line, exit 1 and 2 (SC-2); standard output and standard error (SC-3); hash sort tie-break (SC-4); rule names (SC-5); limits of a planner or classifier call (SC-6); merge keys, anchors and aliases (SC-7); `causation_id` of the spec events (SC-9); order of the output lines and the count line (SC-10); `events --stream` with no matches (SC-11). SC-8 changed no text. |
