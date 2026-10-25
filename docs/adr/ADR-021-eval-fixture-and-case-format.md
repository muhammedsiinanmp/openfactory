# ADR-021: Eval fixture layout and case file format

- Status: accepted
- Date: 2026-10-25

## Context
"Evaluation plan" › Fixture is "a frozen snapshot of the target repo after the initial
build, with its event log and git history". Each of the 8 cases runs on its own copy of
the fixture, and "the case's spec files replace `specs/requirements.yaml` and
`specs/adrs/`" (Procedure, SC-207). Ground truth is the tasks, files and tests a change
truly affects and the kind of each modified requirement (SC-215, SC-227, SC-229). The
spec leaves the fixture's layout and the case file format to the eval task. The human's
item 6 build, TASK-114 and TASK-115 all depend on it.

## Decision
- **Fixture:** `tests/eval/fixture/` holds two files from the human's one real build:
  - `repo.bundle`: `git bundle create repo.bundle --all` of the target repo after the
    initial build. `specs/policies.yaml` comes from it.
  - `openfactory.db`: that repo's `.openfactory/openfactory.db`, checkpointed into one
    file, with no `-wal` or `-shm`.
- **Restoring a copy:** clone the bundle into a fresh directory, then copy
  `openfactory.db` to `.openfactory/openfactory.db` in the clone. Commit shas survive the
  bundle, so `commits` and `trace_links` rows resolve. The clone shows the task branches
  as `refs/remotes/origin/*`; a step that reads branch names fetches with
  `refs/*:refs/*` instead.
- **Case:** `tests/eval/cases/<case id>/` holds:
  - `specs/requirements.yaml` and `specs/adrs/*.md`: the files that replace the copy's;
    no `policies.yaml`;
  - `labels.yaml`: the ground truth.
  The case id is the directory name.
- **Labels file:** a YAML mapping with exactly four keys, all required:
  - `tasks`, `files`, `tests`: each a list of strings, possibly empty;
  - `kinds`: a mapping from a modified requirement's id to `cosmetic`, `behavioral` or
    `replacement`, possibly empty.
  `app/eval_cases.py`'s `parse_eval_labels` turns its text into `EvalLabels`; anything
  else is a `ValueError`. A repeated key keeps its last value.

## Alternatives considered
- **A tarball of the working tree with its `.git`.** Also keeps the history, but puts a
  binary of a nested repo in this one and is larger than a bundle.
- **The database and `specs/` only.** All `impact` reads, but it drops the git history
  the spec puts in the fixture.
- **Optional label keys defaulting to empty.** Shorter for the cosmetic and
  new-requirement cases, but an omitted key silently means "nothing affected" and moves
  the case out of the pools.
- **One `cases.yaml` for all cases.** Splits a case between that file and its spec
  directory.
- **Rejecting duplicate keys.** Would copy or expose `spec_loader.py`'s private loader
  for eight human-reviewed files.

## Consequences
- The fixture is two committed binary files, produced once by the human.
- TASK-114 restores a copy as above and replaces its spec files; TASK-115 lists the case
  directories and reads each `labels.yaml`.
- A duplicated `kinds` key goes unnoticed; this is a Later line in `docs/progress.md`.
