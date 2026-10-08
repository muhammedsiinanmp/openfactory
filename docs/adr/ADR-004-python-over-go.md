# ADR-004: Python over Go

- Status: accepted
- Date: 2026-10-09

## Context
Phase 1 is a single-user CLI that drives one agent runtime against one local repo.

The spec's target repo is a small Python auth service (FastAPI). The platform runs that
repo's tools as gates (`pytest`, `ruff`) and reads its tests' `req` markers with
`pytest --collect-only`. Every reply from an LLM is validated by a Pydantic model before
it is used.

Two languages were considered, Python and Go. The spec records the choice but not the
comparison; the reasons marked "author's rationale" below come from the author.

## Decision
OpenFactory is written in Python 3.12, managed with uv. The spec's tech stack follows
from that choice: Typer for the CLI, Pydantic v2 for schemas and for validating LLM
output, the standard `sqlite3` module, pytest, ruff, and structlog.

Reasons:

- The author's main target is AI builder roles, where Python is standard (author's
  rationale).
- Pydantic is the strongest fit for validating LLM output (author's rationale).
- The author is fluent in Python, so the effort goes to traceability and impact
  analysis, not to a new language (author's rationale).
- The target repo is Python, "so the whole demo stays in one language" (spec).

## Alternatives considered
- **Go.** It fits backend and cloud-native roles, has good concurrency, builds to a
  single binary, and the author was learning it. It was not chosen for the reasons
  above: Python is the standard in the roles the author is aiming at, Pydantic is the
  best fit we know of for validating LLM output against models, and learning the
  language would have taken effort away from traceability and impact analysis (author's
  rationale).
- No other language is recorded as considered.

## Consequences
Easier:
- Faster delivery (author's rationale).
- Better LLM tooling (author's rationale). Pydantic models serve as the spec models, the
  event payload models, the task contract and the validation of LLM output.
- The platform, its gates and the target repo share one language and one toolchain
  (pytest, ruff).

Harder:
- The project loses the Go portfolio signal (author's rationale).
- Interface safety needs a type checker (author's rationale). Adapters match their
  ports by structure only, so pyright and an explicit assertion per adapter were added
  ([ADR-006](ADR-006-ports-and-adapters-with-type-checked-conformance.md)).
- PyYAML and networkx are new dependencies that M1 and M2 need.
