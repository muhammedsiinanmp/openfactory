# ADR-017: `GateOutput.finding`

- Status: proposed
- Date: 2026-10-16

## Context
[ADR-015](ADR-015-m4-gates-retry-resolve-and-cost.md) (accepted) fixes the fields of
`GateOutput`: `passed`, `text` and, for `pytest`, the collected marker lines.
[ADR-016](ADR-016-gitleaks-finding-exit-code-and-missing-tool.md) (accepted) makes exit
status 3 of `gitleaks` a finding, which gives the reason `secret found` and escalates at
once. The use case has no I/O and sees only `GateOutput`, so it cannot tell a finding from
any other failure of the scan (audit `docs/spec-audits/2026-10-15-proposal-v1.15.md`,
F-4). Spec v1.16 settles it (decision SC-121).

## Decision
`GateOutput` gains `finding: bool`. `process_gates` sets it to true only when `gitleaks`
exits 3, and to false for every other gate and outcome. The use case chooses `secret found`
from `finding`; the exit-code rule stays in the adapter. This amends the `GateOutput`
fields of ADR-015's "Ports and adapters" and completes ADR-016's Decision.

## Alternatives considered
- **Each command's exit status in `GateOutput`** (`exits: list[int]`), with `app` reading
  exit 3 itself. It moves a tool's exit codes into `app` and makes `app` depend on the order
  of a gate's commands, for one bit of information.
- **Storing `finding` on `GateEvaluated`.** A payload change under
  [ADR-007](ADR-007-event-payloads-as-stable-contracts.md); it would let Restart step 2 tell
  a finding from a scan error, which matters only in a rare window where counting any
  failed gitleaks result as a finding fails safe.

## Consequences
- The human accepts this ADR before spec v1.16 is applied.
- Every fake of `GateRunner` gains the field when the port is built.
- Restart step 2 still counts any failed `gitleaks` result as a finding, since `finding` is
  not stored.
