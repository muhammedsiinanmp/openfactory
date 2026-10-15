# ADR-016: gitleaks finding exit code and `GateRunner.missing_tool`

- Status: accepted
- Date: 2026-10-15

## Context
[ADR-015](ADR-015-m4-gates-retry-resolve-and-cost.md) (accepted) says "A gitleaks finding
(exit 1) gives `secret found`" and "only exit status 1 of gitleaks is a finding". gitleaks
uses exit status 1 as its default `--exit-code` for a finding, and very likely also for its
own fatal errors, so exit 1 cannot tell a secret from a broken scan; a broken scan would
then escalate as `secret found` with no retry, and the rule's test could not be written as
stated (audit `docs/spec-audits/2026-10-15-proposal-v1.14.md`, F-11).

ADR-015 also has `run` refuse with `<tool> not found` when `uv` or `gitleaks` is not on
`PATH`, but does not say where the check lives. `app` has no I/O, and the M4 port
operations are listed exactly (F-7).

Spec v1.15 settles both (decisions SC-111, SC-115).

## Decision
- The gitleaks gate runs `gitleaks git --pre-commit --staged --redact --no-banner
  --exit-code 3 .`. Exit status 3 is a finding and gives `secret found`; any other non-zero
  exit is a failed gate that is not a finding. This replaces ADR-015's "exit 1" in
  "Gates and retry" and in "How accepted ADRs are read from now on"; ADR-008's "a gitleaks
  finding escalates at once" keeps its meaning, with the finding now told by exit status 3.
  The task that builds `process_gates` confirms on the installed gitleaks (8.30.1) that its
  own errors do not exit 3.
- `GateRunner` gains `missing_tool() -> str | None`, the first of `uv` and `gitleaks` that
  is not on `PATH`, or `None`. `run_plan` calls it after the `git failed` check and turns a
  name into the `<tool> not found` refusal, before any event.

## Alternatives considered
- **Keep exit 1 as a finding** and check in the `GateRunner` task what gitleaks's errors
  exit with. If they exit 1, a scan error escalates as a secret.
- **Check `PATH` in `cli.py`** before the use case runs. It stretches
  [ADR-011](ADR-011-cli-composition-root.md), under which commands other than `init` do
  their work in use cases.
- **A separate `Tools` port** for the `PATH` lookup. One more concept for one method;
  `GateRunner` is the port that needs both tools.

## Consequences
- The human accepts this ADR before spec v1.15 is applied, since it changes a clause of
  accepted ADR-015.
- `uv` is not a gate, so `missing_tool` sits a little oddly on `GateRunner`.
- Every fake of `GateRunner` gains the method when the port is built.
