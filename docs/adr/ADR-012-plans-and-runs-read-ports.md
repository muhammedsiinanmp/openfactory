# ADR-012: Plans and Runs read ports, and the first GitProvider method

- Status: accepted
- Date: 2026-10-11

## Context
M2 builds `plan`, `approve plan` and the deleted-requirement rule. Their use cases live in
`app`, which may depend on the domain and the ports only
([ADR-006](ADR-006-ports-and-adapters-with-type-checked-conformance.md)), and they need
to read what the projections hold:

- `plan` chooses the next plan id and the next run id "from the projections", needs the
  approved version's requirements, criteria and ADR bodies for the prompt, and must know
  whether a draft or an approved plan exists.
- `approve plan` needs the draft plan, its spec version and its tasks with their
  dependencies.
- The deleted-requirement rule, run by `validate` and `approve spec`, needs the tasks
  that still reference a requirement.
- The planner prompt holds the list of tracked files from `git ls-files`.

The only read port is `SpecVersions`, which returns a version's id and hash, not its
content. [ADR-001](ADR-001-event-recorder-and-spec-versions-ports.md) says "M2 needs the
same kind of read access for plan ids, run ids and tasks. This ADR adds only
`SpecVersions`; the M2 read ports are decided when M2 is planned." The same kind of gap
blocked M1 until ADR-001 (audit finding F-3 of `docs/spec-audits/2026-10-10-M2.md`,
decision SC-28).

## Decision
Add two read-only ports, extend one, and give `GitProvider` its first method.

- `Plans`, over the `plans`, `tasks` and `task_deps` projections. It gives the current
  draft plan, the approved plan if there is one, the next plan id, the tasks of a plan
  with their dependencies, and the live tasks that reference a requirement (a task that
  is in neither state `abandoned` nor `invalidated`). Its adapter is `sqlite_plans`.
- `Runs`, over `agent_runs`. It gives the next run id. Its adapter is `sqlite_runs`.
- `SpecVersions` gains one method that returns the stored spec set of a version, read
  from `requirements`, `adrs` and `spec_versions.components`. This extends ADR-001.
- `GitProvider` gets its first method, the tracked files of the repo (`git ls-files`),
  implemented by a new adapter `git_cli`.
  [ADR-011](ADR-011-cli-composition-root.md) says the port "arrives in M3"; it arrives in
  M2 with this one method, and M3 adds the rest. Nothing else in ADR-011 changes.

Each adapter opens its own connection, as `sqlite_spec_versions` does (ADR-001,
[ADR-010](ADR-010-sqlite-recorder-adapter.md)), and ends with the `TYPE_CHECKING`
assertion against its port (ADR-006). Exact signatures are settled in the tasks that
build them.

`validate` and `approve_spec` gain a `Plans` argument for the deleted-requirement rule.
The task that adds it must keep the M1 tests' assertions as they are.

The `agent_runs` table and the types of `AgentRunFinished` are fixed by spec v1.10
(SC-26, SC-27). They follow the rules of
[ADR-007](ADR-007-event-payloads-as-stable-contracts.md) and need no decision here.

## Alternatives considered
- **One `Planning` port** for plans, tasks and run ids. One fake fewer in M2, but M3's
  `run` and M6's classifier need run ids and would then depend on plan reads they do not
  use.
- **One generic query port over the projections.** Rejected in ADR-001 and ADR-006: it
  leaks table shapes into the app layer and cannot be faked without reimplementing
  queries.
- **Read through `EventStore.read` and rebuild in memory.** Rejected in ADR-001: it
  duplicates the projector's logic in the app layer and grows with the log.
- **Run `git ls-files` from `cli.py`** and pass the list to the use case. No port is
  needed in M2, but ADR-011 keeps git operations behind `GitProvider`, and M3 needs the
  port anyway.

## Consequences
Easier:
- The M2 use cases are tested with in-memory fakes and no database or git repository.
- `Runs` is ready for the executor in M3 and the classifier in M6.
- No new storage: every read is of a projection that the M2 projector already fills.

Harder:
- Three more adapter modules, each with its assertion line, and three more fakes.
- `Runs` is a whole port for one method in M2.
- `validate` and `approve_spec` change signature, and every caller and fake with them.
- A read port sees a recorded event only after its transaction commits. A retried
  planner call reads its run id after the first `AgentRunStarted` is recorded, which
  holds because each `record` commits.
