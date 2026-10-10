# Changelog

All notable changes to OpenFactory are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Each Phase 1
milestone is released as a minor version: M1 → 0.1.0, M2 → 0.2.0, and so on.

## [Unreleased]

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

<!--
Template for each release:

## [0.1.0] - YYYY-MM-DD
### Added
### Changed
### Fixed
### Removed
-->