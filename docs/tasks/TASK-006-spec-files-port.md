# TASK-006: SpecFiles port and filesystem adapter

- Milestone: M1
- Status: done
- Tests: acceptance
- Spec sections (spec v1.5): "Spec input format" ("Loading", "Validation rules", "Policies"); "Tech stack and repo layout"

## Objective
Add the `SpecFiles` port and a filesystem adapter that returns the text of `requirements.yaml`, `policies.yaml` and each `adrs/*.md` by path relative to `specs/`, so the loader task (application layer) can parse spec files without reading the filesystem itself.

## Requirement IDs
None. The spec defines no REQ ids for OpenFactory itself, and OpenFactory's own tests carry no `req` markers (decision of 2026-10-08, `docs/decisions.md`). Acceptance criteria trace to spec headings instead.

## Scope
In:
- `SpecFiles`: a `Protocol` in `ports/spec_files.py` with two methods (see Interpretations, item 1):
  - `read(path: str) -> str | None`
  - `list_adrs() -> list[str]`
- `FilesystemSpecFiles(specs_dir)`: an adapter in `adapters/filesystem_spec_files.py` that implements the port with `pathlib`.
- Tests for the port and the adapter, using a `specs/` directory under pytest's `tmp_path`.

Out (follow-up M1 tasks, not this one):
- The loader in the application layer: parsing YAML, splitting ADR front matter from the body, normalising ADR body line endings to `\n`, building a `SpecSet`, and the PyYAML dependency with its duplicate-key check.
- The `schema` rule: turning a missing `requirements.yaml`, a YAML syntax error, an ADR without front matter or a `pydantic.ValidationError` into violations, and choosing their subject (stays in `docs/progress.md` under Later).
- The `policies.yaml` model, its defaults, its hash, and the "run `openfactory init`" error for a missing policy file. This task only lets the caller see that the file is missing.
- The projector, the projection tables and rebuild.
- Spec version ids, the draft and approved logic, and the `validate` and `approve spec` use cases.
- CLI commands `init`, `validate`, `approve spec`, `events`, and finding `./.openfactory/`.
- Writing spec files. The port is read-only; `init` creating the default `policies.yaml` is its own task.
- Files that are not valid UTF-8, a byte order mark, symlinks, directories named `*.md`, and paths that leave `specs/` (see Open questions; not hardened here).
- Payload depth limit (stays under Later).

## Acceptance criteria
Each criterion cites the spec v1.5 heading it traces to. "Loading" means the list of that name under "Spec input format". In every criterion the adapter is built on a `specs/` directory created under `tmp_path`.

- [x] AC1 ("Tech stack and repo layout": `ports/ # interfaces: EventStore, SpecFiles, ...`, `adapters/ # ..., filesystem_spec_files, ...` and "the domain never imports infrastructure"; Loading: "A filesystem adapter implements it"): `openfactory.ports.spec_files.SpecFiles` is a `typing.Protocol` that declares `read` and `list_adrs`. The module imports nothing from `openfactory.adapters` or `openfactory.app` (checked by parsing its imports with `ast`). `FilesystemSpecFiles` lives in `openfactory.adapters.filesystem_spec_files` and provides both methods.
- [x] AC2 (Loading: "Spec files are read through a `SpecFiles` port that returns each file's text by path relative to `specs/` (`requirements.yaml`, `adrs/*.md`, `policies.yaml`)"): with `requirements.yaml`, `policies.yaml` and `adrs/ADR-001-auth-method.md` present, `read("requirements.yaml")`, `read("policies.yaml")` and `read("adrs/ADR-001-auth-method.md")` each return that file's full text as a `str`.
- [x] AC3 (Loading: "Files are read as UTF-8"): a file written as the UTF-8 bytes of a text containing non-ASCII characters (for example `Café ≥ 1`) is returned by `read` as exactly that text. The adapter passes the encoding explicitly, so the result does not depend on the platform's default encoding.
- [x] AC4 (Loading: "The loader reads `specs/requirements.yaml` (required) and every `specs/adrs/*.md`"; "The `id` in front matter is authoritative; the file name is not checked"): with `adrs/` holding `ADR-002-b.md`, `ADR-001-a.md`, `notes.md` and `README.txt`, `list_adrs()` returns `["adrs/ADR-001-a.md", "adrs/ADR-002-b.md", "adrs/notes.md"]`: every `*.md` file directly in `adrs/` whatever its name, no other file, as paths relative to `specs/`, in ascending order. Each returned path gives that file's text when passed to `read`.
- [x] AC5 (Loading: "A missing or empty `adrs/` directory means no ADRs"; "Validation rules": "a missing `requirements.yaml`" is reported under the rule `schema`; "Policies": "A missing file is an error that says to run `openfactory init`"): `list_adrs()` returns an empty list when `adrs/` does not exist and when it exists but is empty. `read("requirements.yaml")` and `read("policies.yaml")` return `None` when the file does not exist, without raising, so the caller can tell a missing file from an empty one; an existing empty file returns the empty string.
- [x] AC6 (Loading: "Line endings in an ADR body are normalised to `\n`" and "Parsing YAML and ADR front matter happens in the application layer"): `read` returns the text as decoded, without translating line endings: a file written as bytes with `\r\n` line endings is returned with `\r\n` in the string, and a file with `\n` line endings is returned unchanged. Normalising the ADR body is left to the loader.

## Interpretations
The spec names the port and says what it returns, but gives no signature. These four were proposed by the planner and confirmed by the human as proposed on 2026-10-08 (recorded in `docs/decisions.md`).

1. Port surface. Proposed: `read(path: str) -> str | None` and `list_adrs() -> list[str]`. `path` is a POSIX-style path relative to `specs/`. This is the minimum the loader needs: read two named files, and discover and read the ADR files. Alternative: one method returning every file's text as a `dict[str, str]`.
2. A missing file (AC5). Proposed: `read` returns `None`. The loader needs to tell a missing `requirements.yaml` (a `schema` violation) and a missing `policies.yaml` ("run `openfactory init`") from an empty file. Alternative: raise a `SpecFileNotFoundError` defined in the port module, as `EventConflictError` is in `ports/event_store.py`.
3. Line endings (AC6). Proposed: the adapter does not translate line endings (it opens files with `newline=""`); the loader normalises the ADR body, so the rule lives in one place that is testable without files. Note that Python's default text mode would translate `\r\n` to `\n` silently. Alternative: the adapter normalises every file's line endings to `\n`, and AC6 is inverted.
4. Constructor and ordering. Proposed: `FilesystemSpecFiles(specs_dir: Path)` takes the `specs/` directory itself; the caller (CLI, later task) passes `./specs`. `list_adrs()` returns paths in ascending string order so that later output does not depend on directory listing order. Only files directly in `adrs/` are listed; sub-directories are not searched, following the `specs/adrs/*.md` pattern.

Kept as already decided: the port returns plain text and does no parsing (decision of 2026-10-08, spec v1.5 proposal).

## Plan
1. Create branch `task/TASK-006-spec-files-port` from an up-to-date main.
2. Get the human's answers to Interpretations 1 to 4 and record them here and in `docs/decisions.md`; adjust AC5 and AC6 if items 2 or 3 are answered with the alternative.
3. Write failing tests: `tests/unit/test_spec_files_port.py` for AC1, and `tests/integration/test_filesystem_spec_files.py` for AC2 to AC6, writing files as bytes under `tmp_path`.
4. Add `src/openfactory/ports/spec_files.py`: the `SpecFiles` protocol with docstrings stating the path convention, the `None` result for a missing file and the ordering of `list_adrs`.
5. Add `src/openfactory/adapters/filesystem_spec_files.py`: `FilesystemSpecFiles(specs_dir)`. `read` returns `None` if the path is not a file, otherwise the text opened with `encoding="utf-8"` and `newline=""`. `list_adrs` returns the sorted `adrs/<name>` paths of the `*.md` files in `specs_dir / "adrs"`, or an empty list if that directory does not exist.
6. Run `uv run pytest -q`, `uv run ruff check --fix . && uv run ruff format .`, and `uv run python scripts/check_docs.py` until all are green.
7. Update living docs and this record's Outcome; commit with trailers `Task: TASK-006` and `Milestone: M1`.

## Files expected to change
- `src/openfactory/ports/spec_files.py` (new)
- `src/openfactory/adapters/filesystem_spec_files.py` (new)
- `tests/unit/test_spec_files_port.py` (new)
- `tests/integration/test_filesystem_spec_files.py` (new)
- `docs/architecture.md` (Components: add "SpecFiles port" and "Filesystem spec files"; Data flow: spec file text reaches the application layer through the port)
- `docs/progress.md` (Current task, then Done)
- `docs/decisions.md` (rows for the confirmed interpretations)
- `docs/tasks/TASK-006-spec-files-port.md` (this record; Outcome at close)

Not expected to change: everything under `src/openfactory/domain/`, `src/openfactory/ports/event_store.py`, `src/openfactory/adapters/sqlite_store.py`, `pyproject.toml`, and every existing test file.

## Living docs to update
- `docs/architecture.md`: Components and Data flow.
- `docs/progress.md`: Current and Done.
- `docs/decisions.md`: the confirmed interpretations.
- `CHANGELOG.md`: no entry expected (no user-visible change).
- `README.md`: no change expected.

## New dependencies
None. `pathlib` is in the standard library. PyYAML is added by the loader task, not this one.

## Outcome
Built as planned:
- `ports/spec_files.py` with the `SpecFiles` Protocol: `read(path: str) -> str | None` and `list_adrs() -> list[str]`. Paths are POSIX-style and relative to `specs/`; the port is read-only and returns plain text.
- `adapters/filesystem_spec_files.py` with `FilesystemSpecFiles(specs_dir: Path)`. `read` returns `None` for a missing file and opens files with `encoding="utf-8"` and `newline=""`. `list_adrs` returns sorted `adrs/<name>` for the `*.md` files directly in `adrs/`, or `[]` if the directory is missing or empty.
- Tests: `tests/unit/test_spec_files_port.py` (AC1) and `tests/integration/test_filesystem_spec_files.py` (AC2 to AC6). 402 tests pass in the full suite.

Deviations from plan: none.

Test edits: none. The test-writer's tests are unchanged.

Notes on how the tests read the criteria (test-writer's observations, not changed):
- AC1 checks that `read` and `list_adrs` are callable on the port and the adapter, not their signatures.
- AC3 cannot prove independence from the platform's default encoding on a machine where that default is UTF-8.

Follow-ups for later tasks (all recorded in `docs/decisions.md`):
- The loader normalises ADR body line endings to `\n`, since the adapter returns them as on disk.
- The loader catches invalid UTF-8 as a `schema` violation and prefixes `specs/` in violation subjects.
- `validate` reports a missing `policies.yaml` as a `schema` line.
