# ADR-006: Ports and adapters with type-checked conformance

- Status: accepted
- Date: 2026-10-09

## Context
The spec asks for a hexagonal layout: "the domain never imports infrastructure, so
SQLite, git and Claude Code can be swapped later". Phase 1 has one runtime, one database
and local git, and each has an alternative deferred to a later phase.

Ports are `Protocol` classes, so an adapter matches its port by structure only. Nothing
in `src/` yet passes an adapter where a port is expected, so without an extra step no
checker compares the two (decisions log, 2026-10-08).

## Decision
The code is split into four layers.

- `domain`: pure models, the state machine and rules. No I/O.
- `ports`: interfaces only (`EventStore`, `EventRecorder`, `SpecVersions`, `SpecFiles`,
  `AgentExecutor`, `WorkspaceManager`, `GitProvider`, `LLMProvider`).
- `adapters`: SQLite, the filesystem, git and Claude Code. They implement the ports.
- `app`: use cases. They depend on the domain and the ports only.

Conformance is checked by the type checker.

- Every adapter module ends with `if TYPE_CHECKING: _: type[<Port>] = <Adapter>`.
- `pyright` is a dev dependency and checks `src/` in strict mode.
  `scripts/ci_local.sh` and the stop hook run it. Tests are not type-checked.

## Alternatives considered
- **No conformance check.** Adapters match their ports by structure only and nothing
  passes an adapter where a port is expected, so no checker would compare them.
- **Adapters subclass the Protocol.** Subclassing has a runtime effect; the assertion
  has none.
- **mypy instead of pyright.** pyright was preferred because it understands Pydantic v2
  models without a plugin.
- **One generic query port over the projections** in place of a narrow port per need.
  Considered in [ADR-001](ADR-001-event-recorder-and-spec-versions-ports.md): it leaks
  table shapes into the app layer and cannot be faked in a test without reimplementing
  queries.

## Consequences
Easier:
- SQLite, git and Claude Code can be swapped later without touching the domain or the
  use cases.
- Use cases are tested with in-memory fakes and no database, and the retry rule for LLM
  replies is tested with a fake provider.
- An adapter that drifts from its port fails the type check.

Harder:
- The app layer cannot read the filesystem or touch SQLite, so every such need is a
  port. Spec v1.5 named no port through which a use case could apply an event or read
  `spec_versions`, which blocked M1 work until ADR-001 added two. The `SpecFiles` port
  exists for the same reason.
- M2 needs read access for plan ids, run ids and tasks; those ports are still to be
  decided.
- Each new adapter module needs its assertion line.
- Tests are outside the type check.
