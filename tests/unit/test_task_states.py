"""TASK-020: the task state machine.

Each test names the acceptance criterion it covers (AC6 in
docs/tasks/TASK-020-task-contract-and-states.md).
"""

import importlib
from typing import Any

NINE = [
    "pending",
    "ready",
    "running",
    "gating",
    "passed",
    "failed",
    "escalated",
    "abandoned",
    "invalidated",
]

EXPECTED = {
    "pending": {"ready", "invalidated"},
    "ready": {"running", "invalidated"},
    "running": {"gating", "failed"},
    "gating": {"passed", "failed"},
    "failed": {"ready", "escalated", "invalidated"},
    "escalated": {"ready", "abandoned", "invalidated"},
    "passed": {"invalidated"},
    "invalidated": set(),
    "abandoned": set(),
}


def states() -> Any:
    return importlib.import_module("openfactory.domain.states")


def test_ac6_task_state_has_the_nine_states() -> None:
    task_state = states().TaskState
    assert [s.value for s in task_state] == NINE
    assert [s.name for s in task_state] == NINE


def test_ac6_transitions_equal_the_spec_dict() -> None:
    transitions = states().TRANSITIONS
    assert {str(k): {str(t) for t in v} for k, v in transitions.items()} == EXPECTED


def test_ac6_transitions_are_closed_over_the_nine_states() -> None:
    mod = states()
    assert set(mod.TRANSITIONS) == set(mod.TaskState)
    assert all(targets <= set(mod.TaskState) for targets in mod.TRANSITIONS.values())
    assert not mod.TRANSITIONS[mod.TaskState("invalidated")]
    assert not mod.TRANSITIONS[mod.TaskState("abandoned")]
