"""Task state machine: the nine states and the allowed transitions between them.

Mirrors "Task state machine" in docs/spec/phase1-spec.md. `TRANSITIONS` is data; nothing
here enforces it.
"""

from enum import StrEnum


class TaskState(StrEnum):
    pending = "pending"
    ready = "ready"
    running = "running"
    gating = "gating"
    passed = "passed"
    failed = "failed"
    escalated = "escalated"
    abandoned = "abandoned"
    invalidated = "invalidated"


_S = TaskState

TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    _S.pending: frozenset({_S.ready, _S.invalidated}),
    _S.ready: frozenset({_S.running, _S.invalidated}),
    _S.running: frozenset({_S.gating, _S.failed}),
    _S.gating: frozenset({_S.passed, _S.failed}),
    _S.failed: frozenset({_S.ready, _S.escalated, _S.invalidated}),
    _S.escalated: frozenset({_S.ready, _S.abandoned, _S.invalidated}),
    _S.passed: frozenset({_S.invalidated}),
    _S.invalidated: frozenset(),
    _S.abandoned: frozenset(),
}
