# ADR-003: Deterministic traceability

- Status: accepted
- Date: 2026-10-09

## Context
Phase 1 proves one claim: when a human changes a requirement, the platform finds exactly
the affected tasks, files and tests. The spec measures it against hand-labelled ground
truth, with a target of at least 0.9 recall on affected files and tests, because missing
an affected test is the expensive error. It also requires that every commit made by the
platform maps to a task and at least one requirement.

Impact analysis walks the traceability graph, so its answer is only as reliable as the
links in that graph.

## Decision
Every link in the graph is established mechanically, never guessed by an LLM. The spec
states the reason: "That is what makes impact analysis trustworthy."

| Link | Established by |
| --- | --- |
| requirement → ADR | `constrained_by` in the spec |
| requirement → task | task contract `requirements` |
| task → task | contract `depends_on` |
| task → agent run → commit | the orchestrator records them as they happen |
| commit → file | `git diff --name-only` of the commit |
| test → requirement | the pytest `req` marker, collected with `pytest --collect-only` |
| test → file | the test file path |

- `trace_links` is one generic edge table that all queries traverse. Each edge records
  its `source` (`spec`, `trailer`, `contract`, `diff` or `test_tag`), so how a link was
  established is never in doubt.
- The orchestrator writes the commit trailers (`Task`, `Requirements`,
  `Acceptance-Criteria`, `Agent-Run`, `Spec-Version`). The agent never commits.
- The implementer's instructions require every new test to carry a `req` marker, and the
  pytest gate fails if a task produces no test tagged with its requirements.
- In impact analysis the LLM only classifies a change (`cosmetic`, `behavioral`,
  `replacement`); it never decides what is affected. The structural diff and the
  traversal are deterministic.

## Alternatives considered
- **Links between code and requirements inferred by an LLM or by embeddings.** Easier,
  and it works on existing code. But the links are probabilistic, so impact analysis
  could not be trusted or evaluated against ground truth (author's rationale). The spec
  excludes it in the same terms: links are "never guessed by an LLM", and that is what
  makes impact analysis trustworthy.
- **The LLM decides what a spec change affects.** Excluded by the spec: the LLM only
  classifies the change. Because the traversal steps are deterministic they are covered
  by unit tests, and only the classifier varies, so only the classifier needs repeated
  eval runs.
- **Links held only in SQLite, without commit trailers.** The spec adds trailers because
  they "make the graph rebuildable from git history alone, even if the SQLite file is
  lost".
- **`trace_links.source` without a value for links declared in the spec.** The original
  list (`trailer`, `contract`, `diff`, `test_tag`) had no value for `constrained_by`
  links; `spec` was added (gap G14).

## Consequences
Easier:
- `trace`, `why` and `coverage` are graph queries over one table, with recursive CTEs.
- The graph can be rebuilt from git trailers alone, which is an M5 deliverable.
- Eval variance is confined to the classifier.

Harder:
- A link exists only if its mechanical source exists. A test without a `req` marker is
  not linked to a requirement, so the marker has to be enforced by the pytest gate.
- The orchestrator must be the one that commits, so that every commit carries trailers.
- Requirement ids repeat across spec versions while `from_id` and `to_id` have no
  version. Gap G14 lists this as a question that needs an answer by M5.
