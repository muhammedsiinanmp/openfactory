# Changelog

All notable changes to OpenFactory are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Each Phase 1
milestone is released as a minor version: M1 → 0.1.0, M2 → 0.2.0, and so on.

## [Unreleased]

### Added
- `openfactory replan`: asks Claude Code for new tasks for the work the latest `impact` found and
  prints them as `plan` does, recording a draft plan for the latest approved spec version that holds
  only the new tasks. Refusals (`no approved plan`, `run openfactory impact first`,
  `nothing to replan`, `policy is invalid; run openfactory validate`), the `spec files differ`
  warning and failures go to standard error (exit 1 on a refusal or failure).
- `openfactory run [--task ID]`: runs the ready tasks of the approved plan and prints one
  `task_id  <state>` line per task taken (exit 1 when any did not pass). Refusals and worktree
  warnings go to standard error; nothing is printed until the run ends.
- `openfactory validate` and `openfactory approve spec` report `deleted-requirement` when a requirement
  of the approved spec version is gone from the files and live tasks still reference it.
- `openfactory approve plan`: approves the draft plan and prints one `task_id  ready` line for each
  task with no dependencies, then `approved plan_NN`. It writes `no draft plan`, or
  `plan_NN was made for sv_NN; run openfactory plan` when the spec has changed, to standard error
  (exit 1).
- `openfactory plan`: asks Claude Code for a plan against the approved spec version, prints one
  `task_id  objective` line per task and `created plan_NN`, or the rejection lines when the second
  reply is also rejected (exit 1). Refusals, the `spec files differ` warning and failures go to
  standard error; log lines are JSON on standard error.

### Changed
- The planner prompt states the path pattern syntax, so the `context_hash` of new planner runs differs
  from earlier ones for the same inputs.

## [0.1.0] - 2026-10-10

Milestone 1: specs and events.

### Added
- Project scaffold: Python 3.12 package with domain, ports, adapters, app and gates layers.
- Phase 1 specification in `docs/spec/phase1-spec.md`.
- Claude Code workflow: planner, test-writer, docs-keeper and reviewer subagents;
  `/next-task` and `/new-adr` commands; hooks that protect the spec, lint on edit
  and block finishing while checks fail.
- Documentation system: ADR and task record templates, progress and decisions logs,
  and `scripts/check_docs.py`.
- CI on GitHub Actions: ruff, pytest, doc check and gitleaks.
- Pull request template, README, MIT license.
- Type checking of `src/` with pyright in strict mode, run by CI; each adapter module
  asserts that it matches its port.
- `openfactory init <repo>`: creates `.openfactory/` with its database and `.gitignore` and a
  default `specs/policies.yaml` in an existing git repository; safe to repeat.
- `openfactory validate`: checks the spec files and prints one `rule  subject  message` line per
  violation and policy problem, then a count line; exits 1 when there is any.
- `openfactory approve spec`: validates the spec files and, when they load, differ from the
  approved version and have no violation, approves them and prints `approved sv_NN` after the
  count line; exits 1 when it refuses, or with `nothing to approve` on standard error.
- `openfactory events [--stream S]`: prints the stored events, one JSON object per line in `seq`
  order, optionally only those of one stream.

<!--
Template for each release:

## [0.1.0] - YYYY-MM-DD
### Added
### Changed
### Fixed
### Removed
-->