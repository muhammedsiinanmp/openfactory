"""Aggregation logic of scripts/workflow_metrics.py, on a small fixture log."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "workflow_metrics.py"
_spec = importlib.util.spec_from_file_location("workflow_metrics", SCRIPT)
wm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wm)


def ev(minute, event, task_id="TASK-007", session="s1", tool=None, subagent=None):
    return {
        "ts": f"2026-10-08T10:{minute:02d}:00+00:00",
        "event": event,
        "session_id": session,
        "transcript_path": None,
        "task_id": task_id,
        "tool_name": tool,
        "subagent_type": subagent,
    }


# One /next-task session: planning on main (no task yet), then work on the branch.
LOG = [
    ev(0, "UserPromptSubmit", task_id=None),
    ev(1, "PreToolUse", task_id=None, tool="Agent", subagent="planner"),
    ev(5, "UserPromptSubmit"),
    ev(6, "PreToolUse", tool="Task", subagent="test-writer"),
    ev(8, "PreToolUse", tool="Bash"),
    ev(9, "PreToolUse", tool="Agent", subagent="reviewer"),
    ev(10, "Stop"),
    {
        "ts": "2026-10-08T10:10:30+00:00",
        "event": "StopBlocked",
        "session_id": "s1",
        "task_id": "TASK-007",
    },
    ev(11, "PreToolUse", tool="Agent", subagent="reviewer"),
    ev(12, "SubagentStop"),
    ev(50, "UserPromptSubmit"),
    # a session on a non-task branch
    ev(20, "UserPromptSubmit", task_id=None, session="s2"),
    ev(21, "PreToolUse", task_id=None, session="s2", tool="Read"),
]


def metrics():
    return wm.aggregate(wm.prepare(LOG))


def test_null_events_join_the_sessions_single_task_else_untracked():
    result = metrics()
    assert set(result) == {"TASK-007", wm.UNTRACKED}
    assert result["TASK-007"].subagent_runs["planner"] == 1
    assert result[wm.UNTRACKED].prompts == 1
    assert result[wm.UNTRACKED].tool_calls == 1


def test_counts_per_task():
    m = metrics()["TASK-007"]
    assert m.prompts == 3
    assert m.tool_calls == 5
    assert m.subagent_runs == {"planner": 1, "test-writer": 1, "reviewer": 2}
    assert m.review_rounds == 2
    assert m.stop_blocks == 1


def test_active_time_caps_each_gap_at_15_minutes():
    # 10:00 -> 10:12 is 12 minutes; the 38 minute gap to 10:50 counts as 15.
    assert metrics()["TASK-007"].active_seconds == (12 + 15) * 60
    assert wm.active_seconds([]) == 0


def test_usage_is_counted_once_per_message_id():
    def row(message_id, out):
        usage = {
            "input_tokens": 10,
            "cache_creation_input_tokens": 5,
            "cache_read_input_tokens": 100,
            "output_tokens": out,
        }
        return {
            "type": "assistant",
            "timestamp": "2026-10-08T10:07:00Z",
            "message": {"id": message_id, "usage": usage},
        }

    rows = [
        row("msg_a", 1),
        row("msg_a", 40),
        row("msg_b", 7),
        {"type": "user", "message": {"content": "hi"}},
        {"type": "assistant", "message": {"id": "msg_c"}},  # no usage
    ]
    usages = wm.dedupe_usage(rows)
    assert [(u.tokens_in, u.cache_read, u.tokens_out) for u in usages] == [
        (15, 100, 40),
        (15, 100, 7),
    ]

    tokens = wm.attribute_tokens(wm.prepare(LOG), {"s1": usages})
    assert tokens == {"TASK-007": (30, 200, 47)}


def test_acceptance_criteria_are_counted_in_their_section_only():
    record = (
        "# TASK-007\n\n## Acceptance criteria\nIntro.\n\n- [x] AC1: a\n- [ ] AC2: b\n\n"
        "## Plan\n- [ ] not a criterion\n"
    )
    assert wm.count_acceptance_criteria(record) == 2


def test_splice_replaces_only_what_is_between_the_markers():
    text = f"# Title\n\nmy notes\n\n{wm.START}\nold table\n{wm.END}\n\nfooter\n"
    out = wm.splice(text, "NEW")
    assert out == f"# Title\n\nmy notes\n\n{wm.START}\nNEW\n{wm.END}\n\nfooter\n"
    assert wm.splice(out, "NEW") == out

    created = wm.splice("", "NEW")
    assert created.endswith(f"{wm.START}\nNEW\n{wm.END}\n")


def test_rows_of_tasks_missing_from_the_log_are_kept():
    old = wm.render_table({"TASK-001": wm.TaskMetrics("TASK-001", prompts=9)}, {})
    table = wm.render_table(metrics(), wm.existing_rows(old))
    rows = wm.existing_rows(table)
    assert list(rows) == ["TASK-001", "TASK-007", wm.UNTRACKED]
    assert rows["TASK-001"] == wm.existing_rows(old)["TASK-001"]
