# Spec gaps blocking the remaining M1 and M2 work

Written 2026-10-08 against spec v1.3 (`docs/spec/phase1-spec.md`), `docs/progress.md`,
`docs/decisions.md` and task records TASK-001 to TASK-003. This is a proposal for the
human to decide on. Nothing here is binding until it is written into the spec or
`docs/decisions.md`. The spec was not edited.

## What is left

- **M1:** YAML loader, spec hashing and `spec_version`, payload models for the spec events,
  projections and replay, `init`, `validate`, `approve spec` (and `events`).
- **M2:** `LLMProvider` port and Claude Code adapter, planner, plan validation, `plan`,
  `approve plan`, the fifth validation rule (deleted requirements).

## Summary

"Spec edit" means the answer contradicts or extends text in the spec, so the spec needs a
new version. "Decision" means a row in `docs/decisions.md` is enough.

| # | Gap | Blocks | Needs |
| --- | --- | --- | --- |
| G1 | YAML parser | M1 loader | Decision (new dependency) |
| G2 | ADR file format and what the loader reads | M1 loader | Spec edit |
| G3 | How loader errors become violations | M1 loader, `validate` | Decision |
| G4 | Canonical form and hash algorithm | M1 hashing | Spec edit |
| G5 | What an ADR's hash covers | M1 hashing | Spec edit |
| G6 | `deprecated` field must exist before the first hash | M1 hashing, M2 rule 5 | Spec edit |
| G7 | Spec version lifecycle and id format | M1 `validate`, `approve spec` | Spec edit |
| G8 | Advisory LLM checks in M1 | M1 `validate` | Spec edit |
| G9 | Stream names and actors | M1 events | Spec edit |
| G10 | Where payloads are validated | M1 events | Decision |
| G11 | Payload shapes for M1 and M2 events | M1, M2 | Spec edit |
| G12 | Projection table schemas | M1, M2 projections | Spec edit |
| G13 | How projections are kept up to date and what "identically" means | M1 replay | Spec edit |
| G14 | Which projections each milestone builds | M1, M2 | Decision |
| G15 | `policies.yaml` schema | M1 `init`, M2 planner | Spec edit |
| G16 | Is `policies.yaml` part of the spec version | M1 hashing, M2 | Spec edit |
| G17 | `init`: file locations and repeat runs | M1 `init` | Spec edit |
| G18 | `LLMProvider` signature and where the retry lives | M2 adapter | Decision |
| G19 | How structured output is obtained from `claude -p` | M2 adapter | Decision |
| G20 | `ANTHROPIC_API_KEY` handling | M2 adapter | Decision |
| G21 | What the planner is given | M2 planner | Spec edit |
| G22 | Plan checks beyond the three in the spec | M2 plan validation | Spec edit |
| G23 | What the orchestrator overrides in a contract | M2 planner | Spec edit |
| G24 | Initial task state and what `approve plan` does | M2 `approve plan` | Spec edit (contradiction) |
| G25 | Task and plan ids, and re-running `plan` | M2 | Spec edit |
| G26 | Where planner call metrics are stored | M2 | Spec edit |
| G27 | Fifth validation rule: what "still reference it" means | M2 | Spec edit |
| G28 | `Limits` model | M2 contract | Spec edit |

Suggested order to decide: G6 and G5 first (they change every hash), then G4, G7, G11,
G12, G13. The M2 items can wait until M1's loader and hashing tasks are done.

---

## Loading specs

### G1. YAML parser

**Question.** Which YAML library does the loader use? None is installed, and the spec's
tech stack table names none.

**Proposed.** PyYAML with `yaml.safe_load`, plus a small loader subclass that rejects
duplicate mapping keys. PyYAML keeps the last of two duplicate keys without complaint, and
a spec file with two `statement:` keys should be an error, not a silent choice. Record the
dependency in `docs/decisions.md`.

One consequence to accept: PyYAML follows YAML 1.1, so an unquoted `no`, `on` or
`2026-10-08` is read as a boolean or a date. Where a string is expected, Pydantic then
rejects it and the loader reports a `schema` violation (G3) telling the author to quote it.

**Alternative.** `ruamel.yaml`: YAML 1.2 (no `no` → `false` surprise) and duplicate keys
rejected by default, but a larger dependency with a more awkward API. Or PyYAML with no
duplicate-key check, which is the least code.

### G2. ADR file format and what the loader reads

**Question.** The spec says an ADR is "markdown body + YAML front matter" and shows one
file name. It does not say how front matter is delimited, which files are read, whether the
file name must agree with the `id`, or what a missing file means.

**Proposed.**
- The loader reads `specs/requirements.yaml` (required) and every `specs/adrs/*.md`
  (a missing or empty `adrs/` directory means no ADRs).
- An ADR file starts with a line `---`, then YAML, then a line `---`. Everything after
  that is the body. A file without front matter is a `schema` violation.
- The `id` in front matter is authoritative. The file name is not checked.
- Files are read as UTF-8. Line endings in the body are normalised to `\n`.

**Alternative.** Require the file name to start with the `id` (`ADR-001-*.md`) and report a
violation when they disagree. Slightly safer, one more rule.

### G3. How loader errors become violations

**Question.** `docs/decisions.md` already says the loader converts `pydantic.ValidationError`
into violations so that everything is reported as one list. Not yet decided: the rule name,
the `subject` when no id can be determined, and what happens to the other rules when the
structure is broken.

**Proposed.**
- One new rule, `schema`. It covers YAML syntax errors, a missing `requirements.yaml`,
  missing front matter, and every Pydantic error.
- `subject` is the id of the item when it can be read from the raw data, otherwise the file
  path relative to the repo (for example `specs/requirements.yaml`).
- `message` includes the field path from Pydantic (for example
  `requirements[2].priority: must be one of must, should, could`).
- If any `schema` violation exists, the five content rules are not run: there is no
  trustworthy `SpecSet` to run them on. `validate` reports the `schema` violations and
  exits non-zero.

**Alternative.** Parse item by item, drop the broken items, and run the content rules on
the rest. Reports more in one run, but the content rules then report follow-on errors
(for example `constrained-by` for an ADR that was dropped for a different reason).

---

## Hashing

### G4. Canonical form and hash algorithm

**Question.** The spec says the spec set "is hashed" and that requirements and ADRs have a
`hash`, and the M6 diff compares "by ID and content hash". It defines neither the algorithm
nor what bytes are hashed.

**Proposed.** One rule for everything: the hash of a thing is the SHA-256 of the canonical
JSON of its parsed model, as 64 lowercase hex characters.

- Canonical JSON: `json.dumps(model.model_dump(mode="json"), sort_keys=True,
  separators=(",", ":"), ensure_ascii=False)` encoded as UTF-8.
- The models are hashed, not the files. Comments, key order, indentation and quoting style
  do not change a hash. An omitted optional field and an explicit empty list hash the same.
- Order in the file does not matter: before hashing, `requirements` and `adrs` are sorted
  by `id`, `acceptance_criteria` by `id`, and `components` and `constrained_by` as strings.
- Strings are hashed as parsed: no trimming, no case folding, no Unicode normalisation.
- Requirement hash: the whole `Requirement`, including its acceptance criteria. Changing a
  criterion makes its requirement `modified`, which is what the M6 classifier works on.
- Acceptance criterion hash: the `AcceptanceCriterion` model (`id`, `text`). Not stored;
  computed when M6 needs it.
- Spec set hash: the whole `SpecSet` (components, requirements, ADRs).

**Alternative.** Hash the raw file bytes. Simpler, but reformatting a file or reordering
two requirements creates a new spec version and a `modified` result in the diff with no
change in meaning. Or build the set hash from the item hashes (a Merkle-style hash), which
gains nothing at this size.

### G5. What an ADR's hash covers

**Question.** `Adr` has only `id` and `status` and ignores other front matter. Hashing
that model would mean a rewritten decision text does not change the hash, so the diff
would call the ADR `unchanged`.

**Proposed.** Add `body: str` to `Adr`, filled by the loader with the markdown after the
front matter. The ADR hash then covers `id`, `status` and `body` under the G4 rule. Other
front matter (title, date) stays ignored and does not affect the hash. The body is also
what the planner (G21) and the M3 context pack ("linked ADRs") need.

**Alternative.** Hash the ADR file's text as a whole and keep the model as it is. Any edit,
including a changed date in front matter, then counts as a change. Or hash only `id` and
`status`, which hides real changes.

### G6. The `deprecated` field must exist before the first hash is stored

**Question.** The fifth validation rule needs a way to mark a requirement `deprecated`,
and the spec field rules define no such field (`docs/progress.md`, Later). The rule is M2,
but adding a field to `Requirement` changes the canonical form, so every hash stored before
that would no longer match.

**Proposed.** Add `deprecated: bool = False` to `Requirement` in the M1 hashing task,
before any hash is stored. The rule that uses it stays in M2 (G27). A deprecated
requirement is still validated like any other, but the planner creates no tasks for it.

**Alternative.** `status: active | deprecated`, which leaves room for more states later.
Or add the field in M2 and accept that M1 databases are discarded (acceptable only because
nothing outside development exists yet).

---

## Spec version lifecycle

### G7. When versions are created, and their ids

**Question.** `spec_versions.status` can be `draft`, but the spec only describes approval:
"the spec set is hashed and stored as an immutable `spec_version`. Edits after that create
a new draft version." It does not say which command creates a draft, whether `validate`
writes events, what `approve spec` does if the files changed since `validate`, or how ids
are formed (the trailer example shows `sv_01`).

**Proposed.**
- Ids are `sv_NN`, two digits, counted from `sv_01`, wider when needed.
- At most one draft exists. A draft is created or replaced by `SpecImported`.
- `validate` loads the files and hashes them.
  - Hash equals the latest approved version: nothing is imported; it says so.
  - Hash equals the current draft: no new `SpecImported`.
  - Otherwise: append `SpecImported`. If a draft exists it keeps its id and its content is
    replaced; if not, the next id is used.
  - Then run the rules and append `SpecValidated` with the result. Exit code 1 if there is
    any violation, else 0. Warnings never change the exit code.
- `approve spec` does not trust an earlier `validate`. It loads, hashes, imports if
  changed, runs the deterministic rules, and refuses if there is any violation. Otherwise
  it appends `SpecApproved`. If the files equal the latest approved version it exits
  non-zero with "nothing to approve".
- Because drafts reuse their id, approved versions are numbered without gaps: the demo's
  "spec v1" and "spec v2" are `sv_01` and `sv_02`.

**Alternative.** Every import gets a new id, and drafts that are never approved stay in
the table. Simpler projector, but ids skip and "the latest two spec versions" in `impact`
needs a filter. Or `validate` writes no events at all and only `approve spec` does, which
leaves `SpecImported`, `SpecValidated` and the `draft` status without a purpose.

### G8. Advisory LLM checks in M1

**Question.** `validate` "runs deterministic and advisory spec checks", and M1 includes
`validate`. The advisory checks need the LLM adapter, which is an M2 deliverable. Their
output shape is also undefined.

**Proposed.** M1 ships `validate` with deterministic rules only. Advisory checks are added
after the M2 adapter exists, in their own task, and are off unless asked for
(`validate --advisory`) so that a plain `validate` costs nothing and is repeatable.
`SpecValidated` carries a `warnings` list from the start (G11), empty in M1.

**Alternative.** Build the adapter early, in M1. That reorders the milestones. Or drop
advisory checks from Phase 1: they are not needed by the nine-step demo.

---

## Events

### G9. Stream names and actors

**Question.** The spec gives one stream example (`task:AUTH-002`) and says approvals have
actor `human`. Other streams and actors are not defined.

**Proposed.**

| Event | Stream | Actor |
| --- | --- | --- |
| `SpecImported`, `SpecValidated` | `spec:<spec version id>` | `orchestrator` |
| `SpecApproved` | `spec:<spec version id>` | `human` |
| `PlanCreated` | `plan:<plan id>` | `orchestrator` |
| `PlanApproved` | `plan:<plan id>` | `human` |
| `TaskStateChanged` | `task:<task id>` | `orchestrator` |
| `AgentRunStarted`, `AgentRunFinished` | `run:<run id>` | `orchestrator` |

`human` is used only where a human decision is the event (approvals now, `resolve` later).
`agent:<role>` is not used by any M1 or M2 event: the orchestrator records what agents did.
`causation_id` is set where one event directly causes another (for example each
`TaskStateChanged` written by `approve plan` points at the `PlanApproved` event).

**Alternative.** Run events on the stream of the thing they belong to (`plan:<id>` or
`task:<id>`). Fewer streams, but a planner run that fails has no plan to belong to (G26).

### G10. Where payloads are validated

**Question.** The DDL says `payload` is "validated by Pydantic". `Event` currently accepts
any JSON object for any type, and the TASK-001 tests (fixed) build events of every type
with arbitrary payloads. Enforcing per-type payloads inside `Event` would break those tests.

**Proposed.** Per-type payload models live in the domain, next to the events
(`domain/payloads.py`), with one mapping from `EventType` to its model. `Event` stays
generic. Use cases build events through the payload models, and the projector validates
each payload against its model before applying it, failing loudly on a mismatch. A bad
payload can be stored only by code that bypasses the use cases, and replay detects it.

**Alternative.** Validate inside `Event` by type, so a bad payload can never be built.
Stricter, but it needs the human to approve changing the TASK-001 tests.

### G11. Payload shapes for M1 and M2 events

**Question.** No payload shape is defined for any event. Replay must rebuild projections
from events alone, so each payload must carry everything its projections hold: the spec
files and the LLM's reply cannot be read again later.

**Proposed.** All payload models forbid unknown fields.

```
SpecImported
  spec_version: "sv_01"
  hash:         "<64 hex>"            # spec set hash (G4)
  spec:         { components, requirements, adrs }   # full canonical SpecSet, ADR bodies included

SpecValidated
  spec_version: "sv_01"
  hash:         "<64 hex>"
  violations:   [ { rule, subject, message } ]
  warnings:     [ { check, subject, message } ]      # advisory; empty in M1 (G8)

SpecApproved
  spec_version: "sv_01"
  hash:         "<64 hex>"

PlanCreated
  plan_id:      "plan_01"
  spec_version: "sv_01"
  policy_hash:  "<64 hex>"            # G16
  run_id:       "run_0001"            # the planner run that produced it (G26)
  tasks:        [ TaskContract ]      # after orchestrator overrides (G23)

PlanApproved
  plan_id:      "plan_01"

TaskStateChanged
  task_id:      "AUTH-002"
  from:         "pending"
  to:           "ready"
  reason:       null | "<text>"       # required when to = invalidated (spec)

AgentRunStarted                        # M2 uses it for planner runs only (G26)
  run_id:       "run_0001"
  task_id:      null | "AUTH-002"
  role:         "planner"
  runtime:      "claude-code"
  context_hash: "<64 hex>"            # hash of the prompt for planner runs

AgentRunFinished
  run_id:       "run_0001"
  exit:         "ok" | "error" | "timeout"
  model:        "<model name>" | null
  tokens_in, tokens_out, cost_usd, duration_s
  error:        null | "<text>"
```

Item hashes are not in `SpecImported`: the projector computes them from the content with
the G4 function. `approved_at`, `started_at` and `ended_at` come from the events'
`created_at`, never from the clock at replay time.

**Alternative.** `SpecImported` carries only the hash and file paths, and the content is
read from git or from a copy under `.openfactory/`. Smaller events, but the event log alone
no longer reconstructs state, which the spec's success criteria require.

---

## Projections

### G12. Projection table schemas

**Question.** The spec lists what each projection "holds" but gives no types, keys or
JSON encodings. The `requirements` list also omits `priority`, `constrained_by` and the
acceptance criteria, and `adrs` omits the body, though later steps need all of them.

**Proposed.** For the M1 and M2 tables:

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

Plus two columns on `agent_runs` when M2 creates it: `task_id` nullable and a `model`
column (G26). No foreign key constraints and no `CHECK` constraints: projections are
disposable, and the payload models are the validation.

**Alternative.** A separate `acceptance_criteria` table (`id`, `requirement_id`,
`spec_version`, `text`, `hash`) instead of a JSON column. Better for the M6 diff if it is
done in SQL; more tables to keep identical on replay. Or keep exactly the columns the spec
lists and read the rest from the `SpecImported` payload when needed.

### G13. How projections are kept up to date, and what "identically" means

**Question.** "Replay rebuilds projections identically" is M1's test, but the spec does
not say when projections are written, what happens after a crash between the event append
and the projection write, or how "identically" is checked. The `EventStore` port has only
`append` and `read`.

**Proposed.**
- A projector in the adapters layer applies one stored event at a time. Use cases append
  an event, then apply it. They never write projection tables in any other way.
- A one-row table records the `seq` of the last applied event. When the database is
  opened, events with a higher `seq` are applied first, so a crash between append and
  apply repairs itself.
- Rebuild means: drop the projection tables, recreate them, apply every event in `seq`
  order.
- "Identically" means: for every projection table, the rows read in primary-key order are
  equal before and after a rebuild. The projector therefore uses only data in the event
  (no clock, no generated ids, no file reads).
- No new CLI command in M1. Rebuild is a function covered by tests.

**Alternative.** Append and project in one SQLite transaction, so the two can never
disagree. Needs the port widened (a unit of work or an `append` hook), since the app layer
may not touch SQLite. Or add `openfactory rebuild` to the CLI table, which is useful for
the "SQLite file is lost" story but is a new command.

### G14. Which projections each milestone builds

**Question.** M1 says "events table and projections", but most projection tables hold data
that no M1 event produces.

**Proposed.** Each milestone adds the tables for the events it introduces: M1
`spec_versions`, `requirements`, `adrs`; M2 `plans`, `tasks`, `task_deps`, `agent_runs`.
`trace_links` waits for M5. A projection added later is filled by a rebuild, so nothing is
lost by waiting.

This postpones two questions about `trace_links` that are not blocking now but need an
answer by M5: its `source` list (`trailer`, `contract`, `diff`, `test_tag`) has no value
for links declared in the spec (`constrained_by`), and requirement ids repeat across spec
versions while `from_id` and `to_id` have no version.

**Alternative.** Create all ten tables in M1, empty. Fixes their schemas before the
milestones that use them have been planned.

---

## Policies and init

### G15. `policies.yaml` schema

**Question.** The spec says only that the file holds "protected branches, forbidden paths,
retry limit" and that `init` writes a default.

**Proposed.** Three keys, unknown keys rejected, each optional with the default shown:

```yaml
protected_branches: [main, master]
forbidden_paths:
  - .env
  - .env.*
  - specs/**
  - .openfactory/**
max_attempts: 2
```

- `forbidden_paths` uses the same glob syntax as contract paths. The exact matching rules
  are needed by the M3 path check, not before.
- `max_attempts` is an integer of at least 1 and is a ceiling on a contract's
  `limits.max_attempts` (G23).
- `protected_branches` is stored now and first used in M3, where the orchestrator refuses
  to commit on a listed branch.
- A `PolicySet` model in the domain; the loader reports problems as `schema` violations
  with the file path as subject (G3). A missing file is an error that says to run `init`.

**Alternative.** Put all three limits in the policy (`max_runtime_s`, `max_attempts`,
`max_cost_usd`) so the planner chooses none of them. Arguably better, since an LLM setting
its own cost ceiling is odd, but it changes the task contract's meaning (G23).

### G16. Is `policies.yaml` part of the spec version

**Question.** `policies.yaml` sits under `specs/`. Is it covered by the spec hash, so that
editing it creates a new spec version?

**Proposed.** No. It is checked by `validate` but not hashed into the spec version, so a
policy edit does not start a spec diff and impact analysis. It is read when a plan is
created; its own hash (G4 rule on the `PolicySet` model) is recorded in `PlanCreated`, and
the contracts stored in that event already contain the merged forbidden paths, so the
policy in force is reconstructable from the log.

**Alternative.** Include it in the spec hash. Then a policy change needs `approve spec`,
appears as a new version, and the structural diff must learn to ignore or handle it.

### G17. `init`: file locations and repeat runs

**Question.** `init <repo>` "creates `.openfactory/`, the SQLite file and default
`policies.yaml`". Not stated: the database file name, where `policies.yaml` goes (the
layout puts it in `specs/`), what a second `init` does, how other commands find the repo,
and how `.openfactory/` stays out of the target repo's git status.

**Proposed.**
- `<repo>/.openfactory/openfactory.db`, created through `SqliteEventStore`.
- `<repo>/specs/policies.yaml`, creating `specs/` if needed. An existing file is never
  overwritten.
- `<repo>/.openfactory/.gitignore` containing `*`, so the directory ignores itself without
  touching the repo's own `.gitignore`.
- `init` is safe to repeat: it creates what is missing and reports what already exists.
  It writes no events.
- `<repo>` must be an existing git repository; otherwise `init` fails.
- Every other command runs against the current directory and fails with "run
  `openfactory init` first" if `./.openfactory/` is missing. No upward search.

**Alternative.** A `--repo PATH` option on every command, or searching parent directories
the way git does. Or keep `policies.yaml` in `.openfactory/`, which matches the `init`
sentence but not the layout and leaves the policy out of version control.

---

## M2: LLM adapter

### G18. `LLMProvider` signature and where the retry lives

**Question.** The spec names `LLMProvider` and says a reply that fails Pydantic validation
"is retried once with the validation error in the prompt, then fails". It gives no
signature and does not say which layer retries.

**Proposed.**
- Port: `complete(prompt: str, schema: dict) -> LLMReply`, where `LLMReply` has `text`,
  `model`, `tokens_in`, `tokens_out`, `cost_usd`, `duration_s`. A process failure or
  timeout raises `LLMError`.
- The retry is one function in the app layer: call, validate against the Pydantic model,
  and on failure call once more with the errors appended to the prompt. It is tested with
  a fake provider and shared by the planner and, later, the classifier.
- `tokens_in` counts cached input tokens as well, so totals reflect what was processed.
- Adapter tests use a stand-in executable and one captured reply. No test in the default
  run starts `claude`; one real call may sit behind the existing `eval` marker.

**Alternative.** The adapter takes the Pydantic model and retries itself. Less code in the
app, but the retry rule is then repeated in every future provider.

### G19. How structured output is obtained from `claude -p`

**Question.** `claude -p --output-format json` returns an envelope whose result is the
model's text. The spec does not say how a JSON object is reliably obtained from that text,
which tools the call may use, or what its time limit is.

**Proposed.** Pass the Pydantic model's JSON Schema with `--json-schema` (present in the
installed Claude Code 2.1.286) and read the structured result from the envelope. Pydantic
still validates the result, because the schema cannot express cross-field rules. Run with
tools disabled, a fixed time limit of 300 seconds, and the default model; the model name
reported in the envelope is what gets recorded. The exact envelope field names are pinned
by a captured fixture in the adapter task rather than written down here.

**Alternative.** Ask for JSON in the prompt and parse the text, stripping one optional
code fence. Works on any version; fails more often and spends the single retry on format
mistakes.

### G20. `ANTHROPIC_API_KEY` handling

**Question.** The spec says the variable "must not be set". It does not say what the
adapter does when it is. `CLAUDE.md` forbids reading it.

**Proposed.** The adapter starts `claude` with an environment from which the variable has
been removed, without looking at its value, and logs one warning if it was present. The
subscription login is then always the one used.

**Alternative.** Refuse to run and tell the user to unset it. More explicit, but it blocks
users who have the key set for other tools.

---

## M2: Planner

### G21. What the planner is given

**Question.** The planner must emit `allowed_paths` for a repo, but the spec does not say
what it sees when planning. (For replanning, M6, the spec does say.)

**Proposed.** One prompt, no tools: the approved spec (requirements that are not
deprecated, their acceptance criteria, the ADR bodies they are constrained by, the declared
components), the policy's forbidden paths, the names of the gates, and the list of tracked
files from `git ls-files`. No file contents. `plan` uses the latest approved spec version;
it fails if there is none, and warns if the files on disk differ from it.

**Alternative.** Let Claude Code explore the repo with read-only tools from the repo
directory. Likely better `allowed_paths` on a larger repo; costlier, slower and less
repeatable, and the target repo is small.

### G22. Plan checks beyond the three in the spec

**Question.** The spec rejects a plan for a Pydantic failure, a cycle, or an unknown
requirement. Other broken plans are not mentioned, and neither is whether a rejection
that is not a Pydantic failure gets the one retry.

**Proposed.** The planner replies with `{"tasks": [TaskContract, ...]}`. A plan is also
rejected when:
- two tasks share a `task_id`;
- `depends_on` names a task that is not in the plan;
- an acceptance criterion is unknown, or does not belong to one of the task's requirements;
- a component is not declared in the spec;
- a task names a deprecated requirement;
- a requirement that is not deprecated, or one of its acceptance criteria, appears in no
  task.

All rejections, including cycles, are collected into one list and get the same single
retry as a Pydantic failure. If the second reply is also rejected, `plan` exits non-zero
and no `PlanCreated` is written. The checks are a pure domain function; `networkx` is
added for the cycle check as the spec says, with a row in `docs/decisions.md`.

**Alternative.** Only the three checks in the spec, no retry for cycles or unknown
requirements. Smaller, but an incomplete plan is then found only when a task runs or a
requirement turns out to have no work.

### G23. What the orchestrator overrides in a contract

**Question.** The spec says the orchestrator adds the policy's forbidden paths to every
contract. The planner also emits `required_gates` and `limits`; nothing says whether it may
leave out a gate or raise its own attempt limit.

**Proposed.** Before `PlanCreated` is written, for every task:
- `forbidden_paths` becomes the policy's list followed by the planner's, without
  duplicates;
- `required_gates` is set to `[path_check, ruff, pytest, gitleaks]`, whatever the planner
  sent;
- `limits.max_attempts` is lowered to the policy's `max_attempts` if it is higher.

The contract stored in the event and in `tasks.contract` is the result. The planner keeps
its say over `max_runtime_s` and `max_cost_usd`.

**Alternative.** Trust the planner for gates and limits and only merge forbidden paths, as
the spec literally says. Or move all limits into the policy (G15 alternative).

### G24. Initial task state and what `approve plan` does

**Question.** The CLI table says `approve plan` "marks the plan approved; tasks become
`ready`". The state machine says `ready` means "dependencies passed" and `pending` means
"waiting on dependencies". For a task with dependencies these contradict. The state of a
task in a plan that is not yet approved is also not defined.

**Proposed.** Tasks are created `pending` by `PlanCreated`, with no `TaskStateChanged`
event for the initial state. `approve plan` approves the latest draft plan (failing if
there is none), appends `PlanApproved`, and then the orchestrator appends
`TaskStateChanged` `pending` → `ready` only for tasks with no dependencies. The others
become `ready` in M3, when their dependencies pass.

**Alternative.** Follow the CLI table literally: every task becomes `ready` on approval,
and `run` works out the order from `task_deps`. `ready` then no longer means "can be
scheduled", and M3 has to check dependencies again.

### G25. Task and plan ids, and re-running `plan`

**Question.** `tasks` has `id` and `plan_id`, and task streams are `task:<id>`. The spec
does not say whether a task id is unique across plans, how plan ids are formed, or what
happens to a draft plan when `plan` is run again. `plans.status` can be `superseded`, but
no event says so.

**Proposed.**
- Plan ids are `plan_NN`, counted from `plan_01`.
- A task id is unique among all tasks in the `tasks` table. `invalidated` is a terminal
  state, so a revised task in a later plan always gets a new id.
- Running `plan` again while a draft plan exists writes a new `PlanCreated`. The projector
  marks the earlier draft `superseded` and removes its tasks from `tasks` and `task_deps`
  (they never ran, and they remain in the event log), so the new draft may reuse their ids.
- `plan` fails if an approved plan already exists for the current spec version. Changing
  an approved plan is `replan`, M6.

**Alternative.** Key tasks by `(plan_id, id)` and keep the tasks of superseded drafts.
Nothing is ever removed from a projection, but task streams, trailers (`Task: AUTH-002`)
and every query must then carry the plan id as well.

### G26. Where planner call metrics are stored

**Question.** The spec says tokens, cost and latency are "stored per agent run and per
planner or classifier call, with role and model name". `agent_runs` has no model column and
its rows belong to a task; there is no table or event for an LLM call that is not a task
run. A planner call that is rejected twice produces no `PlanCreated` at all.

**Proposed.** Record every planner call as an agent run with role `planner` and no task:
`AgentRunStarted` then `AgentRunFinished`, run ids `run_NNNN`. `agent_runs.task_id`
becomes nullable and a `model` column is added. The retry is a second run. No new event
type or table is needed, failed calls are kept with their cost, and `stats` per role works
without a special case. `PlanCreated` names the run that produced it.

**Alternative.** Put the call's metrics inside `PlanCreated`. Simpler, but the cost of a
rejected plan is recorded nowhere. Or add an `LLMCallRecorded` event and an `llm_calls`
table, which is the cleanest model and the largest spec change.

### G27. Fifth validation rule: what "still reference it" means

**Question.** "No requirement is deleted while tasks still reference it, unless the new
version marks it `deprecated`. Enforced from M2." Not defined: which earlier version is
compared, which tasks count, and the rule's name.

**Proposed.** Rule name `deleted-requirement`, subject the requirement id. A requirement
counts as deleted when it is in the latest approved spec version and absent from the files
being validated. It is a violation when some task in `tasks` lists it in its contract and
that task's state is neither `abandoned` nor `invalidated`. The fix offered in the message
is to restore the requirement with `deprecated: true`. `validate_spec` stays pure: the
use case passes it the previous version's requirement ids and the set of referenced ids.

**Alternative.** Count every task that ever referenced the requirement, whatever its
state. Stricter, and it makes a requirement impossible to delete once planned.

### G28. The `Limits` model

**Question.** `TaskContract` has `limits: Limits`, but `Limits` is shown only as a YAML
example.

**Proposed.** `max_runtime_s: int`, `max_attempts: int`, `max_cost_usd: float`, all
required and all greater than zero. `TaskContract` and `Limits` forbid unknown fields,
like the other models, and `required_gates` entries must be known gate names.

**Alternative.** Give each a default (1200, 2, 1.50, the values in the example) so the
planner may omit them.

---

## Smaller points, proposed without alternatives

These would otherwise come up as questions inside a task. Say so if any is wrong.

- `openfactory events [--stream S]` is not in any milestone's list. Proposed: M1, printing
  one JSON object per line in `seq` order.
- `validate` output: one line per violation as `rule  subject  message`, then a count.
- Ids such as `sv_NN`, `plan_NN` and `run_NNNN` are chosen by the use case from the
  projections when the command runs and are then fixed in the event. Replay never
  generates ids.
- PyYAML and `networkx` are the only new dependencies M1 and M2 need.
- A change to the canonical form (G4) after hashes exist changes every hash. Until Phase 1
  ships, that is handled by discarding the development database, not by versioning the
  hash.

## Contradictions and omissions in the spec itself

Listed separately because each needs a spec edit whichever answer is chosen:

1. `approve plan` "tasks become `ready`" against the state definitions (G24).
2. Metrics "per planner or classifier call" have no table or event (G26).
3. `validate` includes advisory LLM checks, but the LLM adapter is M2 (G8).
4. `init` creates "default `policies.yaml`" without a location; the layout shows it under
   `specs/` (G17).
5. `spec_versions` has a `draft` status that no described step produces (G7).
6. The `requirements` and `adrs` projections omit fields that the planner, the context
   pack and the diff need (G12).
7. `deprecated` is used by a validation rule but is not a spec field (G6).
8. `trace_links.source` has no value for links declared in the spec (G14; not blocking
   until M5).
9. `Limits` is referenced but not defined (G28).
