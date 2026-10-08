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
- 2026-10-09 · TASK-008 · Policy model and loader: frozen `Policy` and `BASELINE_FORBIDDEN_PATHS` in `domain/policy.py`; `load_policy` in `app/spec_loader.py` reads `policies.yaml` through the `SpecFiles` port and returns a `Policy` or every `schema` violation
- 2026-10-08 · TASK-007 · Spec loader: `load_spec` reads `requirements.yaml` and `adrs/*.md` through the `SpecFiles` port and returns a `SpecSet` or every `schema` violation; `schema` added to `Rule`; `pyyaml` added
- 2026-10-08 · TASK-006 · SpecFiles port and filesystem adapter: read-only access to `requirements.yaml`, `policies.yaml` and `adrs/*.md` text by path relative to `specs/`, with `None` for a missing file
- 2026-10-08 · TASK-005 · Payload models for the spec events: `SpecImportedPayload`, `SpecValidatedPayload`, `SpecApprovedPayload`, `RecordedViolation`, `SpecWarning` and `PAYLOAD_MODELS` in `domain/payloads.py`
- 2026-10-08 · TASK-004 · Spec model fields and canonical hashing: `deprecated` on `Requirement`, `body` on `Adr`, and `content_hash`/`canonical_json` functions for acceptance criteria, requirements, ADRs and spec sets
- 2026-10-08 · TASK-003 · Spec models and validation rules: `SpecSet`, `Requirement`, `AcceptanceCriterion`, `Adr` models and `validate_spec` for deterministic rules
- 2026-10-08 · TASK-002 · EventStore port and SQLite adapter: append-only event log with `seq` assignment and stream filtering
- 2026-10-08 · TASK-001 · Domain event model: `EventType` (11 types), `Event` and `StoredEvent` envelope models

## Blockers

## Later (out of current scope)
- payload depth limit
- `validate` task: print the `schema` line `load_policy` now produces for a missing `policies.yaml` (subject `specs/policies.yaml`, message "missing; run openfactory init") and exit 1 (decision of 2026-10-08)
- M2: merge the baseline, policy and planner forbidden paths into each task contract (baseline, then policy, then planner, without duplicates)
- Advisory LLM spec checks (vague wording, possible duplicates): removed from Phase 1 in the spec v1.4 proposal; `validate` is deterministic only
- workflow metrics: events in git worktrees are not logged
- Spec wording (next spec revision): reword the "Tech stack" line "read with PyYAML (`yaml.safe_load`)", since rejecting duplicate keys needs `yaml.load` with a `SafeLoader` subclass
- Spec wording (next spec revision): anchors and merge keys are not supported
