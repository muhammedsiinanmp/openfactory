# ADR-007: Event payloads as stable contracts

- Status: accepted
- Date: 2026-10-09

## Context
Projections are rebuilt by replaying the event log
([ADR-002](ADR-002-event-sourcing-as-the-core.md)), and the projector validates each
payload against its model before applying it, failing on a mismatch. A stored event is
therefore read by code written after it, for as long as the log exists.

Spec v1.3 defined no payload shape for any event (gap G11) and did not say where
payloads are validated (gap G10). The first payload task then met a concrete case: the
violations in `SpecValidated` could reuse the domain's `SpecViolation`, whose `rule` is
a closed enum. Renaming or removing a rule later would make old events fail validation
at replay.

## Decision
A payload model is a contract with the stored log, not a view of the current domain
models.

- Each event type has one payload model in `domain/payloads.py`, with one mapping from
  `EventType` to its model. `Event` stays generic: the envelope accepts any JSON object.
- Use cases build events through the payload models. The projector validates each
  payload against its model before applying it.
- Payload models forbid unknown fields.
- A payload does not reuse a closed domain type where that type may change.
  `SpecValidated.violations` is a list of `RecordedViolation(rule, subject, message)`, a
  payload-only model in which `rule` is a plain string. The use case converts each
  `SpecViolation` to a `RecordedViolation`.
- Every field is required, including `violations` and `warnings`, so a stored event
  always states every field and replay never depends on a default that could change.
- Each payload carries everything its projections hold, because the spec files and an
  LLM's reply cannot be read again at replay. `SpecImported` holds the full spec set in
  canonical order, and `PlanCreated` holds the complete contracts as the orchestrator
  stored them.
- Ids (`sv_NN`, `plan_NN`, `run_NNNN`) are fixed in the event. Replay never generates
  ids.
- Payload models check shape only. `hash` is checked for its form (64 lowercase hex
  characters) and is not verified against `spec`; the model does not reorder `spec`.

## Alternatives considered
- **Reuse `SpecViolation` and the closed `Rule` enum in the payload.** One violation
  type instead of two, but a closed enum in the payload would make old events fail
  validation at replay once a rule is renamed or removed (decisions log, TASK-005).
- **Validate the payload inside `Event`, by type**, so a bad payload can never be built.
  Stricter, but the fixed TASK-001 tests build events of every type with arbitrary
  payloads, and changing them needs the human's approval (gap G10).
- **Payload fields with defaults.** Replay would then depend on a default that could
  change (decisions log, TASK-005).
- **`SpecImported` carries only the hash and file paths.** Smaller events, but the event
  log alone no longer reconstructs state, which the spec's success criteria require
  (gap G11).

## Consequences
Easier:
- A domain rule can be renamed or removed without breaking replay of old events.
- A rebuild needs nothing but the log.
- A malformed payload is caught when it is applied rather than silently projected.

Harder:
- There are two violation models, and the use case must convert between them.
- Use cases must pass every field explicitly, such as an empty `warnings` list in
  Phase 1.
- Events are large, because they carry content rather than references.
- Since the envelope accepts any JSON object, a bad payload can be built by code that
  bypasses the payload models; it is caught only when the projector applies it.
- A change to the canonical form changes every hash. During Phase 1 development that is
  handled by discarding the development database, not by versioning the hash.
- The payloads of `GateEvaluated`, `CommitRecorded` and `ImpactComputed` are still to be
  defined, when their milestones are planned.
