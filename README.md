# OpenFactory

A spec-driven control plane for AI coding agents. You write the requirements; OpenFactory
plans the work as a task DAG, runs agents in isolated git worktrees, enforces deterministic
quality gates, and keeps every commit traceable back to a requirement. When a requirement
changes, it finds exactly what is affected and replans only that.

> **Status:** Phase 1 in progress. See [docs/progress.md](docs/progress.md).

## Why

AI coding agents can write code, but they can't answer:

- Which requirement caused this code to exist?
- What breaks if this requirement changes?
- Which tests prove this requirement?

OpenFactory sits above agents like Claude Code and answers those questions by
construction, not by asking an LLM to guess.

## How it works

1. **Specs** — requirements and ADRs as structured YAML with stable IDs.
2. **Plan** — specs become a dependency-aware task DAG with explicit contracts.
3. **Execute** — each task runs in its own git worktree; writes outside its allowed
   paths are rejected.
4. **Gate** — tests, lint and secret scans decide what passes, not model confidence.
5. **Trace** — commit trailers and test markers link requirement → task → commit → code → test.
6. **Impact** — a changed requirement is diffed, the affected subgraph found, and only
   that work is replanned.

## Quick start

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/) and git.

```bash
git clone <repo-url> openfactory && cd openfactory
uv sync
cp .env.example .env   # add your ANTHROPIC_API_KEY
uv run pytest -q
```

## Usage

```bash
uv run openfactory init <repo>
cd <repo> && uv run --project <path-to-openfactory> openfactory validate
cd <repo> && uv run --project <path-to-openfactory> openfactory approve spec
cd <repo> && uv run --project <path-to-openfactory> openfactory events [--stream S]
```

`uv run openfactory` finds the command only inside the OpenFactory checkout. From another
directory, pass the checkout with `--project`.

`init` needs an existing git repository. It creates `<repo>/.openfactory/` (the SQLite
database and a `.gitignore` containing `*`) and, if missing, `<repo>/specs/policies.yaml`
with the default policy. It prints `created <path>` or `exists <path>` for each item, never
overwrites a file and is safe to repeat.

`validate` runs in the initialised repository. It reads `specs/`, records the spec version
and its rule results, and prints one `rule  subject  message` line per violation and per
policy problem, then `N violations, M policy problems`, and `matches approved sv_NN` when
the files equal the approved version. It exits 1 if there is any violation or policy
problem.

`approve spec` runs `validate` itself and prints the same lines. If the files load, differ
from the approved version and have no violation, it records the approval and ends with
`approved sv_NN` (exit 0). Policy problems do not block it. If there is a violation it prints
no status line and exits 1; if the files equal the approved version it writes
`nothing to approve` to standard error and exits 1.

`events` prints the stored events, one JSON object per line in `seq` order, with the keys
`seq`, `event_id`, `stream`, `type`, `payload`, `actor`, `causation_id` and `created_at`
(keys sorted, no spaces). `--stream S` keeps only the events of that stream; with no match it
prints nothing. It exits 0, or 1 if `init` was not run. The other commands are not built yet.

## Project layout

```
src/openfactory/
  domain/     pure models, state machine, rules (no I/O)
  ports/      interfaces
  adapters/   SQLite, git, Claude Code, Anthropic SDK
  app/        use cases
  gates/      quality gates
docs/
  spec/       Phase 1 specification (authoritative)
  adr/        architecture decision records
  tasks/      one record per implemented task
```

## Documentation

- [Phase 1 spec](docs/spec/phase1-spec.md)
- [Architecture](docs/architecture.md)
- [Decisions log](docs/decisions.md)
- [Progress](docs/progress.md)

## Roadmap

| Phase | Focus |
| --- | --- |
| 1 | Local CLI vertical slice: specs, planning, execution, gates, traceability, impact analysis |
| 2 | Parallel worktrees, pull requests, second agent runtime, web UI |
| 3 | PostgreSQL, durable workflows, distributed workers, observability |
| 4 | Multi-tenancy, RBAC, model routing, cost controls |
| 5 | Deployment, runtime monitoring, governed remediation |

## Development

This project is built with Claude Code using a spec-first workflow: one task per session,
tests written before code, hooks that block edits to the spec, and an independent review
before every commit. See [CLAUDE.md](CLAUDE.md).