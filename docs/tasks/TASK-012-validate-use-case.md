# TASK-012: Validate use case

- Milestone: M1
- Status: planned
- Tests: acceptance
- ADR: ADR-001 and ADR-007 (both accepted). ADR-001 covers recording through `EventRecorder` and reading through `SpecVersions`; ADR-007 covers building events through the payload models, converting `SpecViolation` to `RecordedViolation`, and storing `SpecImported.spec` in canonical order. No new port, adapter, dependency, event type or payload change. The function signature and result model are a row in `docs/decisions.md`.
- Spec impact: contradiction, does not block this task: "Spec versions" imports a spec set with a duplicated requirement or ADR id and then reports `id-unique`, but the M1 DDL's `PRIMARY KEY (spec_version, id)` makes that `SpecImported` unprojectable (see "Spec gaps", item 2). To be decided through `/spec-change` before M1 outline item 4. Item 1 of "Spec gaps" is wording.
- Spec sections (spec v1.8): "Spec input format" ("Validation rules", "Spec field rules", "Hashing", "Spec versions", "Policies"); "Domain model and storage" ("Projection rules", "Streams and actors", "Event payloads", "Ids"); "Tech stack and repo layout"

## Objective
Add the validate use case in `src/openfactory/app/`, which loads and hashes the spec set, records `SpecImported` when the files changed and `SpecValidated` with the rule results, and returns the violations and the policy problems, so the `validate` command and the approve-spec use case have it to build on.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Acceptance criteria trace to spec headings instead.

## Scope
In:
- A new module `app/validate.py` with one use case function and its frozen result model (proposed shape under Open questions, item 2). It depends on `openfactory.domain`, `openfactory.ports` and `app/spec_loader.py` only.
- The four cases of "Spec versions": spec files that cannot be loaded; hash equal to the latest approved version; hash equal to the current draft; otherwise import.
- Building both events through `SpecImportedPayload` and `SpecValidatedPayload`, with stream `spec:<spec version id>`, actor `orchestrator`, and `causation_id` as "Streams and actors" states.
- `SpecImported.spec` in canonical order; `SpecValidated.violations` converted to `RecordedViolation` in the order `validate_spec` returned them (SC-10); `warnings` empty.
- Loading the policy with `load_policy` in every case and returning its problems without recording them.
- Unit tests with in-memory fakes of `EventRecorder`, `SpecVersions` and `SpecFiles`. No database, no files.

Out (follow-up tasks, not this one):
- `approve spec` (outline item 2), `SpecApproved`, "nothing to approve".
- Typer, the CLI, printing, the sort of printed lines, the count line, the status line and exit codes (outline items 3 and 4). The use case returns data and prints nothing.
- The deleted-requirement rule (M2).
- A spec set in which two requirements or two ADRs share an id (Spec gaps, item 2). No test in this task covers it.
- Any change to `domain/`, `ports/`, `adapters/` or `app/spec_loader.py`.
- What the use case does when the recorder raises: the error propagates.

## Acceptance criteria
Each criterion cites the spec v1.8 text it traces to. "Spec versions", "Policies", "Hashing", "Validation rules" and "Spec field rules" are blocks under "Spec input format"; "Streams and actors", "Event payloads", "Ids" and "Projection rules" are under "Domain model and storage". In every criterion the use case runs with a fake `SpecFiles` holding file texts, a fake `SpecVersions` whose latest approved version, current draft and next id the test sets, and a fake `EventRecorder` that keeps the events it is given. "The files' hash" is `content_hash` of the `SpecSet` that `load_spec` returns. Unless stated, `policies.yaml` is valid.

- [ ] AC1 (Spec versions: "If the spec files cannot be loaded (any `schema` violation in them), `validate` prints the violations, records no events"; Validation rules: "When there is any `schema` violation in the spec files, the rules above are not run"; Policies: "It prints them even when the spec files cannot be loaded"): `requirements.yaml` is not valid YAML and `policies.yaml` has an unknown key.
  - The recorder received no event.
  - The result says the spec files could not be loaded, has no spec version id, holds the loader's `schema` violations as its violations, and holds the policy's `schema` violation (subject `specs/policies.yaml`) as its policy problems.
- [ ] AC2 (Spec versions: "Otherwise it records `SpecImported` (... if there is no draft, the next id is used), then runs the rules and records `SpecValidated`"; Event payloads: "the full spec set, ADR bodies included, stored in canonical order (sorted as for hashing)"; Streams and actors: the table row for `SpecImported`, `SpecValidated`, and "`causation_id` is the `event_id` of the event recorded just before it in the same command; the first event a command records has none"; Projection rules: "Use cases record every event through the `EventRecorder` port"; Ids: "chosen by the use case from the projections"): the files hold a valid spec set (two requirements written out of id order, unsorted `components`, one accepted ADR with a body); there is no draft and no approved version; the next id is `sv_01`.
  - The recorder received exactly two events, `SpecImported` then `SpecValidated`, both with stream `spec:sv_01` and actor `orchestrator`.
  - The `SpecImported` payload validates as `SpecImportedPayload`, with `spec_version` `sv_01`, `hash` equal to the files' hash, and `spec` equal to the parsed canonical JSON of the loaded spec set (lists in canonical order, ADR body included).
  - The `SpecValidated` payload validates as `SpecValidatedPayload`, with `spec_version` `sv_01`, the same `hash`, and empty `violations` and `warnings`.
  - `SpecImported` has no `causation_id`; the `causation_id` of `SpecValidated` is the `event_id` of the `SpecImported`.
  - The result says the spec was validated, names `sv_01`, and has no violations and no policy problems.
  - With a latest approved `sv_01` of a different hash, no draft and next id `sv_02`, both events are on stream `spec:sv_02` with `spec_version` `sv_02`.
  - `openfactory.app.validate` imports nothing from `openfactory.adapters` (checked by parsing its imports with `ast`).
- [ ] AC3 (Spec versions: "an existing draft keeps its id and its content is replaced"; "At most one draft exists at a time"): the latest approved version is `sv_01`, the current draft is `sv_02`, both with hashes different from the files', and the next id is `sv_03`.
  - The recorder received `SpecImported` then `SpecValidated`, both with `spec_version` `sv_02` and stream `spec:sv_02`, and `hash` equal to the files' hash.
  - The result names `sv_02`.
- [ ] AC4 (Spec versions: "If the hash equals the current draft's, it records no `SpecImported`. It runs the rules and records `SpecValidated` for the draft again"; Streams and actors: "the first event a command records has none"): the current draft is `sv_01` with the files' hash.
  - The recorder received exactly one event, a `SpecValidated` on stream `spec:sv_01` with `spec_version` `sv_01`, the files' hash and no `causation_id`.
  - The result says the spec was validated and names `sv_01`.
- [ ] AC5 (Spec versions: "If the hash equals the latest approved version's, it records no events, prints `matches approved sv_NN` ... The rules are not run. A draft that exists is left as it is"; Policies: "`openfactory validate` prints policy problems ... and exits 1"): the latest approved version is `sv_01` with the files' hash.
  - With no draft, and again with a draft `sv_02` of another hash, the recorder received no event, and the result says the files match the approved version and names `sv_01`.
  - When the files hold a requirement with no acceptance criteria (the fake still reports their hash as approved), the result has no violations.
  - When `policies.yaml` has `max_attempts: 0`, the result still says the files match `sv_01`, records nothing, and holds the policy problem.
- [ ] AC6 (Spec field rules: "Validation returns every violation in one run, each with the rule name, the ID it concerns, and a message"; Event payloads: "`violations: [ { rule, subject, message } ]  # rule is a plain string`"; Policies: "Policy problems are not recorded in `SpecValidated`, do not stop the content rules"): the files load, one requirement has no acceptance criteria and is constrained by an ADR that does not exist, and `policies.yaml` has `max_attempts: 0`; there is no draft and no approved version.
  - `SpecImported` and `SpecValidated` are both recorded: violations do not stop the import.
  - `SpecValidated.violations` has one `{rule, subject, message}` object per violation that `validate_spec` returns for the loaded spec set, with `rule` as the rule's name string. `warnings` is empty.
  - Not in the spec text; from decisions row SC-10 (audit finding F-4 of `docs/spec-audits/2026-10-09-proposal-v1.8.md`): the stored violations are in the order `validate_spec` returned them, so `missing-acceptance-criteria` comes before `constrained-by`. They are not sorted by rule name.
  - No stored violation has the subject `specs/policies.yaml`.
  - The result's violations equal what `validate_spec` returns, and its policy problems hold the policy's `schema` violation.

## Architecture rules that apply
- `src/openfactory/app` depends on domain and ports only. `app/validate.py` imports `load_spec` and `load_policy` from `app/spec_loader.py`, the domain modules and the three port Protocols; nothing from `adapters`.
- "All state changes go through the events table. Never write projections directly": the use case's only write is `EventRecorder.record`.
- Events are built through the payload models (ADR-007); every field is passed explicitly, including the empty `warnings` list.
- No LLM call is made.

## Plan
1. Create branch `task/TASK-012-validate-use-case` from an up-to-date main and commit this record.
2. Get the human's answers to the Open questions; record them here and in `docs/decisions.md`; add the Later lines to `docs/progress.md` (Spec gaps, items 1 and 2).
3. Write failing tests in `tests/unit/test_validate_use_case.py`, one or more per criterion AC1 to AC6. The three fakes live in the test file: a `SpecFiles` over a dict of texts (as in `tests/unit/test_spec_loader.py`), a `SpecVersions` with three settable values, and an `EventRecorder` that appends to a list and returns a `StoredEvent` with the next `seq`.
4. Add `src/openfactory/app/validate.py`:
   - load the policy and the spec; on `schema` violations in the spec, return without reading versions or recording;
   - hash with `content_hash`; compare with `latest_approved()`, then with `current_draft()`, in the spec's order;
   - if neither matches, record `SpecImported` under the draft's id, or `next_id()` when there is no draft. The canonical-order spec is `SpecSet.model_validate_json(canonical_json(spec))`, which uses only the public hashing API and changes no domain module;
   - run `validate_spec`, convert each result to `RecordedViolation` in the order returned, and record `SpecValidated` with `causation_id` set to the `SpecImported` event's id when one was recorded in this call;
   - keep "import if changed, run the rules, record `SpecValidated`" as one function, so outline item 2 can call it instead of copying it.
5. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
6. Update living docs and this record's Outcome; commit with trailers `Task: TASK-012` and `Milestone: M1`.

## Files expected to change
- `src/openfactory/app/validate.py` (new)
- `tests/unit/test_validate_use_case.py` (new)
- `docs/architecture.md` (Components: add "Validate use case"; Data flow: replace the "No use case exists yet" and "Nothing calls `load_spec` / `load_policy` / the recorder / the port yet" sentences with what now exists)
- `docs/progress.md` (Current task, then Done; remove item 1 from the M1 outline and renumber the references to it; new Later lines)
- `docs/decisions.md` (a row for the signature and result model; a row for how the canonical-order spec is built)
- `docs/tasks/TASK-012-validate-use-case.md` (this record; Outcome at close)

Not expected to change: everything under `src/openfactory/domain/`, `src/openfactory/ports/` and `src/openfactory/adapters/`, `src/openfactory/app/spec_loader.py`, `pyproject.toml`, and every existing test file.

## Living docs to update
- `docs/architecture.md`: Components and Data flow.
- `docs/progress.md`: Current, M1 outline, Done and Later.
- `docs/decisions.md`: the rows above.
- `CHANGELOG.md`: no entry expected (no user-visible change).
- `README.md`: no change expected.

## New dependencies
None.

## Spec gaps
1. **"Domain model and storage" › Event payloads (`SpecValidated`), and "CLI commands" › Output — wording, does not block.**
   - The spec gives `violations` no order.
   - Decisions row SC-10 settles it: "The sort applies to the printed lines only; the order stored in `SpecValidated` is unchanged."
   - This is finding F-4 of `docs/spec-audits/2026-10-09-proposal-v1.8.md`. The task follows SC-10, and AC6 tags that bullet as tracing to the decision rather than the spec text.
2. **"Spec input format" › Spec versions, against "Domain model and storage" › the M1 DDL — contradiction, does not block this task.**
   - Spec versions says: "Otherwise it records `SpecImported` (...), then runs the rules and records `SpecValidated`."
   - Validation rules says ids "are unique across the whole spec set", and Hashing says "so two items with the same id still have one order". So a spec set with a duplicated id is meant to be hashed, imported and then reported under `id-unique`.
   - The DDL gives `requirements` and `adrs` `PRIMARY KEY (spec_version, id)`, so that `SpecImported` cannot be projected, and the recorder stores nothing when the projection fails ("Projection rules"). The projector uses a plain `INSERT` (`src/openfactory/adapters/sqlite_projector.py`, lines 112 and 132). Derived by reading; nothing was run.
   - The spec does not say which gives way. Duplicate acceptance criterion ids are not affected; they sit in a JSON column.
   - It does not block TASK-012: the use case follows the Spec versions text, the fakes have no primary key, and no criterion covers the case.
   - It does block a correct `validate` command (outline item 4) and the M1 close test (item 6) for this input.

## Open questions
Both answered by the human on 2026-10-09.

1. **Duplicate requirement or ADR ids (Spec gaps, item 2). Proceed, or stop for a spec change first?**
   - Answer: proceed with TASK-012 as written. A "Spec gap (before outline item 4, the validate command)" line is under Later in `docs/progress.md`; it is decided through `/spec-change`, leaning to the projector tolerating duplicates deterministically.
2. **Signature and result model (the spec gives none).**
   - Answer: `validate(files: SpecFiles, versions: SpecVersions, recorder: EventRecorder) -> ValidateResult` in `app/validate.py`. `ValidateResult` is a frozen model with:
     - `outcome`: one of `unloadable`, `matches_approved`, `validated`;
     - `spec_version: str | None`: the approved id for `matches_approved`, the draft id for `validated`, `None` for `unloadable`;
     - `violations: list[SpecViolation]`: the `schema` violations when unloadable, the rule results when validated, empty when the files match the approved version;
     - `policy_problems: list[SpecViolation]`;
     - `hash: str | None`: the files' hash, `None` when nothing was recorded;
     - `validated_event_id: UUID | None`: the `event_id` of the `SpecValidated` recorded in this call, `None` when nothing was recorded.
   - The last two fields were added on the advisor's recommendation, so the approve-spec use case (outline item 2) can call `validate` and chain `SpecApproved` to it.
   - Tests: the fake `SpecFiles` always holds a `policies.yaml`, or `load_policy` reports "missing; run openfactory init" in every case.

## Outcome
<!-- filled at close: what was built, deviations from plan, follow-ups -->
