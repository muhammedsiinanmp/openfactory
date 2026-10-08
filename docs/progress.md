# Progress

## Current
- Milestone: M1 — Specs and events
- Task: none

## Milestones
- [ ] M1 Specs and events
- [ ] M2 Planner
- [ ] M3 Executor
- [ ] M4 Gates and remediation
- [ ] M5 Traceability
- [ ] M6 Impact and replan
- [ ] M7 Eval, report, demo

## Done
<!-- newest first: date · task id · one line -->
- 2026-10-08 · TASK-004 · Spec model fields and canonical hashing: `deprecated` on `Requirement`, `body` on `Adr`, and `content_hash`/`canonical_json` functions for acceptance criteria, requirements, ADRs and spec sets
- 2026-10-08 · TASK-003 · Spec models and validation rules: `SpecSet`, `Requirement`, `AcceptanceCriterion`, `Adr` models and `validate_spec` for deterministic rules
- 2026-10-08 · TASK-002 · EventStore port and SQLite adapter: append-only event log with `seq` assignment and stream filtering
- 2026-10-08 · TASK-001 · Domain event model: `EventType` (11 types), `Event` and `StoredEvent` envelope models

## Blockers

## Later (out of current scope)
- payload depth limit
- Loader task: convert Pydantic ValidationError into SpecViolation(rule='schema', ...) so all problems are reported as one list
- Advisory LLM spec checks (vague wording, possible duplicates): removed from Phase 1 in the spec v1.4 proposal; `validate` is deterministic only
