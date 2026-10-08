# TASK-007: Spec loader

- Milestone: M1
- Status: done
- Tests: acceptance
- Spec sections (spec v1.5): "Spec input format" ("Loading", "Validation rules", "Spec field rules"); "Tech stack and repo layout"

## Objective
Add the application-layer spec loader that reads `requirements.yaml` and every `adrs/*.md` through the `SpecFiles` port, parses YAML and ADR front matter, and returns either a `SpecSet` or the full list of `schema` violations, so the `validate` and `approve spec` use cases have one function to load the spec files with.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Acceptance criteria trace to spec headings instead.

## Scope
In:
- `load_spec(files: SpecFiles) -> SpecLoadResult` in a new module `app/spec_loader.py` (see Interpretations, item 1).
- Parsing `requirements.yaml` with PyYAML, using a `SafeLoader` subclass that rejects duplicate mapping keys.
- Splitting an ADR file into front matter and body, and normalising the body's line endings to `\n`.
- The `schema` rule: a YAML syntax error, a missing `requirements.yaml`, an ADR file without front matter, a file that is not valid UTF-8, and a value the models reject each become a `SpecViolation` with rule `schema`. The subject is the item's id when it can be read, otherwise the file path relative to the repo (`specs/` prefixed to the port's path).
- `schema` added to the `Rule` enum in `domain/spec_validation.py` (see Interpretations, item 2). `validate_spec` is unchanged and never returns it.
- The PyYAML dependency.
- Unit tests using an in-memory fake `SpecFiles` (a dict of path to text). No filesystem, no database.

Out (follow-up M1 tasks, not this one):
- `policies.yaml`: its model, defaults, unknown-key rejection, hash, and how `validate` reports policy problems or a missing policy file. The loader does not read it.
- Running the content rules (`validate_spec`) after loading, and skipping them when there is a `schema` violation. That is the `validate` use case; the loader only loads.
- Hashing the loaded spec set, storing it in canonical order, choosing `sv_NN` ids, the draft and approved logic, and recording `SpecImported`, `SpecValidated` or `SpecApproved`.
- Converting `SpecViolation` to `RecordedViolation`.
- The projector, the projection tables and rebuild.
- CLI commands `init`, `validate`, `approve spec`, `events`, and their output format and exit codes.
- Any change to `FilesystemSpecFiles` or the `SpecFiles` port.
- A byte order mark, trailing spaces on a `---` line, non-string YAML keys, and other exotic inputs (not hardened here).
- Payload depth limit (stays under Later).

## Acceptance criteria
Each criterion cites the spec v1.5 heading it traces to. "Loading", "Validation rules" and "Field rules" mean the lists "Loading", "Validation rules" (with the `schema` paragraph that follows it) and "Spec field rules" under "Spec input format". In every criterion the loader is called with an in-memory fake `SpecFiles`, "result" is what `load_spec` returns, and a "`schema` violation" is a `SpecViolation` whose `rule` has the value `"schema"`.

- [x] AC1 ("Tech stack and repo layout": `app/ # use cases` and "Spec files | YAML, read with PyYAML"; Loading: "Spec files are read through a `SpecFiles` port ... Parsing YAML and ADR front matter happens in the application layer"): with `requirements.yaml` holding the spec's example and `adrs/ADR-001-auth-method.md` holding an accepted ADR with id `ADR-001`, the result has no violations and a `SpecSet` with `components` equal to `["auth"]`, one requirement `REQ-AUTH-001` with the example's `title`, `statement`, `priority` `must`, `constrained_by` `["ADR-001"]` and its two acceptance criteria in file order, and one ADR. `openfactory.app.spec_loader` imports nothing from `openfactory.adapters` (checked by parsing its imports with `ast`).
- [x] AC2 (Loading: "An ADR file starts with a line `---`, then YAML front matter, then a line `---`. Everything after that is the body"; "The `id` in front matter is authoritative; the file name is not checked"; "Line endings in an ADR body are normalised to `\n`"; "A missing or empty `adrs/` directory means no ADRs"; Field rules: "Other front matter fields are ignored. The ADR model also holds the `body`"): an ADR file named `adrs/notes.md` whose front matter has `id: ADR-007`, `status: accepted`, `title` and `date` loads as an `Adr` with id `ADR-007`, status `accepted` and `body` equal to the text after the closing `---` line. The same file written with `\r\n` line endings gives the same `body`, containing no `\r`. When the fake lists no ADR files, the result's spec set has `adrs` equal to `[]` and no violations.
- [x] AC3 ("Tech stack and repo layout": "duplicate keys are rejected"; Validation rules: "A file that cannot be loaded into the models is reported under the rule `schema`: a YAML syntax error ... Its subject is the item's id when that can be read, otherwise the file path relative to the repo"): a `requirements.yaml` with a YAML syntax error gives a result with no spec set and one `schema` violation with subject `specs/requirements.yaml` and a non-empty message. A `requirements.yaml` in which one mapping has the same key twice (for example `title` twice on a requirement) gives the same. A YAML syntax error in the front matter of `adrs/ADR-001-a.md` gives one `schema` violation with subject `specs/adrs/ADR-001-a.md`.
- [x] AC4 (Validation rules: "a missing `requirements.yaml`, an ADR file without front matter"; Loading: "The loader reads `specs/requirements.yaml` (required)"): when the fake returns `None` for `requirements.yaml`, the result has no spec set and one `schema` violation with subject `specs/requirements.yaml`. An ADR file that does not start with a `---` line, and one that starts with `---` but has no closing `---` line, each give one `schema` violation with subject `specs/adrs/<file name>`. Not in the spec's `schema` list; included on the decision of 2026-10-08 (`docs/decisions.md`, TASK-006): when the fake's `read` raises `UnicodeDecodeError` for `requirements.yaml`, the result has no spec set and one `schema` violation with subject `specs/requirements.yaml` whose message contains "not valid UTF-8"; when it raises for an ADR file, the subject is `specs/adrs/<file name>`.
- [x] AC5 (Validation rules: "or a value the models reject. Its subject is the item's id when that can be read, otherwise the file path relative to the repo"; Field rules: "`priority` is one of `must`, `should`, `could`", "`status` is one of `proposed`, `accepted`, `superseded`", "a requirement with no acceptance criteria is reported by validation rather than rejected while parsing"): a requirement `REQ-AUTH-001` with `priority: urgent` gives a `schema` violation with subject `REQ-AUTH-001` whose message names `priority`. A requirement with a misspelt key (`titel`) gives a `schema` violation with that requirement's id as subject. An ADR whose front matter has `id: ADR-002` and `status: draft` gives a `schema` violation with subject `ADR-002`. A requirement with no `id`, and a `requirements.yaml` whose top level is not a mapping, each give a `schema` violation with subject `specs/requirements.yaml`; ADR front matter with no `id` gives one with subject `specs/adrs/<file name>`. A requirement with no acceptance criteria and a requirement whose id is `REQ-1` both load with no violations, since those are content rules, not `schema`.
- [x] AC6 (Field rules: "Validation returns every violation in one run ... It never stops at the first"; Validation rules: "When there is any `schema` violation in the spec files, the rules above are not run, because there is no trustworthy spec set to run them on"): with a `requirements.yaml` holding one requirement with a rejected `priority` and one valid requirement, one ADR file without front matter and one ADR file with a rejected `status`, the result holds all three `schema` violations (problems in `requirements.yaml` first, then ADR files in the order `list_adrs` returns them) and no spec set. Whenever the result has any violation its spec set is `None`, and whenever it has none its spec set is a `SpecSet`.

## Interpretations
The spec says what the loader reads and what it reports, but leaves these open. The human confirmed all five as proposed on 2026-10-08, kept the task whole (no split at AC5), and added two rulings:

- A spec file that is not valid UTF-8 is in scope, folded into AC4, on the strength of the existing decision row (2026-10-08, TASK-006). The spec's `schema` list does not name it yet; the wording fix is in `docs/progress.md` under Later.
- YAML is parsed with `yaml.load(text, Loader=<SafeLoader subclass>)`. The spec's "`yaml.safe_load`" is read as "safe loading", since `yaml.safe_load` takes no custom loader; the wording fix is in `docs/progress.md` under Later.

1. Function and result shape. Confirmed: `load_spec(files: SpecFiles) -> SpecLoadResult`, where `SpecLoadResult` is a frozen model with `spec: SpecSet | None` and `violations: list[SpecViolation]`, exactly one of them filled. Requirements keep file order and ADRs follow `list_adrs` order; sorting into canonical order is the import use case's job (decision of 2026-10-08, TASK-005). Alternative: return `SpecSet` and raise an error that carries the violations.
2. Where the `schema` rule lives. Confirmed: add `schema = "schema"` to the `Rule` enum so the loader returns the existing `SpecViolation` and `validate` prints one list. `validate_spec` never returns it. Alternative: a separate loader-only violation type.
3. Subject of a nested item. The spec says "the item's id when that can be read". Confirmed: the nearest enclosing item with a readable string `id`: an error inside an acceptance criterion uses the criterion's id if it has one, otherwise its requirement's id, otherwise the file path. An error at the top level of `requirements.yaml` (unknown key, `components` not a list, top level not a mapping, empty file) uses the file path.
4. Granularity. Confirmed: one `schema` violation per Pydantic error, with the Pydantic field path in the message (decision of 2026-10-08, gap G3), so a requirement with two bad fields gives two violations with the same subject. Alternative: one violation per item, listing all its errors.
5. ADR splitting details. Confirmed: the opening and closing lines are exactly `---` (a `\r` before the line break is tolerated); the body is everything after the closing line's line break, not trimmed; `\r\n` and a lone `\r` both become `\n`; front matter that is not a YAML mapping is a `schema` violation with the file path as subject; a `body` key in front matter is ignored and the file's body is used. A top-level `adrs` key in `requirements.yaml` is a `schema` violation with the file path as subject, since ADRs come only from `adrs/*.md`.

Kept as already decided (`docs/decisions.md`, 2026-10-08): PyYAML with a `SafeLoader` subclass that rejects duplicate keys, and the YAML 1.1 consequence for unquoted `no`, `on` and dates; `specs/` is prefixed to the port's paths in violation subjects; closed sets are rejected by the models and converted by the loader; the adapter does not translate line endings.

## Architecture rules that apply
- `src/openfactory/app` depends on domain and ports only. The loader takes a `SpecFiles` and never imports `openfactory.adapters`, `pathlib` file access or `open`. PyYAML is a parsing library, not an adapter; the spec places YAML parsing in the application layer.
- `src/openfactory/domain` stays pure: the only domain change is one enum member. No I/O, no import from `app`, `ports` or `adapters`.
- `src/openfactory/ports` holds Protocols only; the `SpecFiles` port is not changed.
- Adapters implement ports and end with the `TYPE_CHECKING` port assertion; no adapter is added or changed here.
- All state changes go through the events table: the loader records no events and writes nothing.
- No LLM call is made, so the `claude -p` and Pydantic-validated LLM output rules are not exercised. The loader still builds every model through Pydantic validation.

## Plan
1. Create branch `task/TASK-007-spec-loader` from an up-to-date main.
2. Record the human's answers to Interpretations 1 to 5 here and in `docs/decisions.md` (done 2026-10-08; all as proposed).
3. Add `pyyaml` to `pyproject.toml` with `uv add pyyaml`. Run `uv run pyright`; only if it reports missing stubs for `yaml`, add `types-PyYAML` to the dev group and record why in `docs/decisions.md`.
4. Write failing tests in `tests/unit/test_spec_loader.py`, one or more per criterion AC1 to AC6, with a small in-memory fake `SpecFiles` defined in the test file.
5. Add `schema` to `Rule` in `src/openfactory/domain/spec_validation.py`.
6. Add `src/openfactory/app/spec_loader.py`: the duplicate-key-rejecting `SafeLoader` subclass; a function that splits an ADR file into front matter text and normalised body; a function that turns a `pydantic.ValidationError` into `schema` violations with the subject chosen as in Interpretations, item 3; and `load_spec`, which reads `requirements.yaml`, validates each requirement and each ADR separately so every problem is collected, and builds the `SpecSet` only if there is no violation.
7. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, `uv run pyright` and `uv run python scripts/check_docs.py` until all are green.
8. Update living docs and this record's Outcome; commit with trailers `Task: TASK-007` and `Milestone: M1`.

## Files expected to change
- `src/openfactory/app/spec_loader.py` (new)
- `src/openfactory/domain/spec_validation.py` (one enum member; module docstring)
- `tests/unit/test_spec_loader.py` (new)
- `pyproject.toml` and `uv.lock` (PyYAML)
- `docs/architecture.md` (Components: add "Spec loader", update the `Rule` list under "Spec validation"; Data flow: replace "No loader exists yet")
- `docs/progress.md` (Current task, then Done; remove from Later the three loader items this task delivers: the `ValidationError` conversion, the non-UTF-8 file and the `specs/` prefix; add the two spec wording items)
- `docs/decisions.md` (rows for the confirmed interpretations)
- `docs/tasks/TASK-007-spec-loader.md` (this record; Outcome at close)

Not expected to change: `src/openfactory/domain/models.py`, `src/openfactory/domain/payloads.py`, `src/openfactory/domain/spec_hash.py`, everything under `src/openfactory/ports/` and `src/openfactory/adapters/`, and every existing test file.

## Living docs to update
- `docs/architecture.md`: Components and Data flow.
- `docs/progress.md`: Current, Done and Later.
- `docs/decisions.md`: the confirmed interpretations.
- `CHANGELOG.md`: no entry expected (no user-visible change).
- `README.md`: no change expected.

## New dependencies
- `pyyaml` (runtime). The reason is already recorded in `docs/decisions.md` (2026-10-08, gap G1: smallest dependency that does the job, with a loader subclass that rejects duplicate keys); that row says the dependency is added by the loader task.
- `types-PyYAML` (dev) only if pyright in strict mode needs it; if added, record why in `docs/decisions.md`.

## Outcome
What was built:
- `src/openfactory/app/spec_loader.py`: `load_spec(files: SpecFiles) -> SpecLoadResult`. It reads `requirements.yaml` and every `adrs/*.md` through the `SpecFiles` port, parses YAML with `yaml.load` and a `SafeLoader` subclass that rejects duplicate keys, splits ADR files into front matter and body (body line endings normalised to `\n`), and returns either a `SpecSet` or the full list of `schema` violations, never both. Subjects are the nearest readable item id (criterion, then requirement or ADR, then `specs/<path>`); there is one violation per Pydantic error; a non-UTF-8 file gives "not valid UTF-8".
- `src/openfactory/domain/spec_validation.py`: `Rule.schema` added; `validate_spec` never returns it.
- `pyproject.toml` and `uv.lock`: `pyyaml` runtime dependency (reason in `docs/decisions.md`, gap G1 row).
- `tests/unit/test_spec_loader.py`: 24 test cases for AC1 to AC6 (23 from the test-writer, one added after review). The full suite passes with 426 tests.

Deviations from plan:
- None in scope.
- `types-PyYAML` was not needed; pyright in strict mode is clean without it.
- A non-mapping top level of `requirements.yaml` and an empty file are both reported with the message "top level is not a mapping".

Test edits: no test-writer test was changed. One test was added after the first review, `test_ac3_impossible_date_in_adr_front_matter`: the reviewer found that an unquoted impossible date such as `date: 2026-02-30` makes PyYAML raise a plain `ValueError`, which escaped `load_spec`. The loader now reports it as a `schema` violation like any other YAML error, and the new test pins that.

Follow-ups:
- The three "Spec wording" items under Later in `docs/progress.md` (the `schema` list gains "not valid UTF-8"; the "Tech stack" line on `yaml.safe_load` is reworded; anchors and merge keys are not supported).
- The next M1 pieces, the policy model and the `validate` use case, are separate tasks.
