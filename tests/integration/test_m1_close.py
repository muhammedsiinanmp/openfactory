"""TASK-019 AC1..AC6: M1 close (see docs/tasks/TASK-019-m1-close-integration-test.md)."""

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from openfactory.adapters.sqlite_recorder import SqliteEventRecorder

runner = CliRunner()

DB = Path(".openfactory/openfactory.db")
GITIGNORE = Path(".openfactory/.gitignore")
POLICIES = Path("specs/policies.yaml")
REQS = Path("specs/requirements.yaml")
ADR_1 = Path("specs/adrs/ADR-001-auth-method.md")
ADR_2 = Path("specs/adrs/ADR-002-otp.md")
CLEAN = "0 violations, 0 policy problems"

TABLES = ("spec_versions", "requirements", "adrs")
ORDER = {"spec_versions": "id", "requirements": "spec_version, id", "adrs": "spec_version, id"}

REQ_1_MEMBERSHIP = """\
  - id: REQ-AUTH-001
    title: Login with membership number
    statement: Users authenticate using their membership number and password.
    priority: must
    components: [auth]
    constrained_by: [ADR-001]
    acceptance_criteria:
      - id: AC-AUTH-001-1
        text: Valid membership number and password returns a JWT.
      - id: AC-AUTH-001-2
        text: Unknown membership number returns 401.
"""

REQ_1_OTP = """\
  - id: REQ-AUTH-001
    title: Login with OTP
    statement: Users authenticate using a one-time password sent to their phone.
    priority: must
    components: [auth]
    constrained_by: [ADR-001, ADR-002]
    acceptance_criteria:
      - id: AC-AUTH-001-1
        text: A valid OTP returns a JWT.
      - id: AC-AUTH-001-2
        text: An expired OTP returns 401.
"""

REQ_2 = """\
  - id: REQ-AUTH-002
    title: Logout
    statement: Users can end their session.
    priority: should
    components: [auth]
    acceptance_criteria:
      - id: AC-AUTH-002-1
        text: Logout invalidates the JWT.
"""

REQ_3 = """\
  - id: REQ-AUTH-003
    title: Resend OTP
    statement: Users can ask for a new one-time password.
    priority: could
    components: [auth]
    acceptance_criteria:
      - id: AC-AUTH-003-1
        text: A resend invalidates the previous OTP.
"""

HEADER = "components: [auth]\nrequirements:\n"
STATE_1 = HEADER + REQ_1_MEMBERSHIP + REQ_2
STATE_2 = HEADER + REQ_1_OTP + REQ_2
STATE_3 = STATE_2 + REQ_3

ADR_1_TEXT = "---\nid: ADR-001\nstatus: accepted\n---\nUsers are identified by membership number.\n"
ADR_2_PROPOSED = "---\nid: ADR-002\nstatus: proposed\n---\nLogin uses a one-time password.\n"
ADR_2_ACCEPTED = ADR_2_PROPOSED.replace("proposed", "accepted")


def run(repo: Path, monkeypatch: pytest.MonkeyPatch, *args: str):
    from openfactory.cli import app

    monkeypatch.chdir(repo)
    return runner.invoke(app, list(args))


def query(repo: Path, sql: str) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(repo / DB)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def event_rows(repo: Path) -> list[tuple[Any, ...]]:
    return query(repo, "SELECT * FROM events ORDER BY seq")


def snapshot(repo: Path) -> dict[str, list[tuple[Any, ...]]]:
    """Every row of the three spec projections, in primary-key order."""
    return {t: query(repo, f"SELECT * FROM {t} ORDER BY {ORDER[t]}") for t in TABLES}


def state_rows(repo: Path) -> list[tuple[Any, ...]]:
    return query(repo, "SELECT id, last_seq FROM projection_state")


def max_seq(repo: Path) -> int:
    return query(repo, "SELECT MAX(seq) FROM events")[0][0]


def write(repo: Path, path: Path, text: str) -> None:
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(text, encoding="utf-8")


def flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, dict[int, Any], dict[int, int]]:
    """Run steps 1 to 7 of the record's flow.

    Returns the repo, each step's result, and the event count after steps 1, 3 and 4.
    """
    from openfactory.cli import app

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    steps: dict[int, Any] = {}
    counts: dict[int, int] = {}

    steps[1] = runner.invoke(app, ["init", str(repo)])
    counts[1] = len(event_rows(repo))
    write(repo, REQS, STATE_1)
    write(repo, ADR_1, ADR_1_TEXT)
    steps[2] = run(repo, monkeypatch, "validate")
    steps[3] = run(repo, monkeypatch, "approve", "spec")
    counts[3] = len(event_rows(repo))
    steps[4] = run(repo, monkeypatch, "validate")
    counts[4] = len(event_rows(repo))
    write(repo, REQS, STATE_2)
    write(repo, ADR_2, ADR_2_PROPOSED)
    steps[5] = run(repo, monkeypatch, "validate")
    write(repo, ADR_2, ADR_2_ACCEPTED)
    steps[6] = run(repo, monkeypatch, "approve", "spec")
    write(repo, REQS, STATE_3)
    steps[7] = run(repo, monkeypatch, "validate")
    return repo, steps, counts


def empty_projections(repo: Path) -> None:
    conn = sqlite3.connect(repo / DB)
    try:
        for table in TABLES:
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
    finally:
        conn.close()


def rebuild(repo: Path) -> None:
    recorder = SqliteEventRecorder(repo / DB)
    try:
        recorder.rebuild()
    finally:
        recorder.close()


def test_ac1_init_validate_and_approve_freeze_spec_v1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, steps, counts = flow(tmp_path, monkeypatch)

    assert steps[1].exit_code == 0
    assert steps[1].stdout.splitlines() == [f"created {p}" for p in (DB, GITIGNORE, POLICIES)]
    assert counts[1] == 0

    assert steps[2].exit_code == 0
    assert steps[2].stdout.splitlines() == [CLEAN]

    assert steps[3].exit_code == 0
    assert steps[3].stdout.splitlines() == [CLEAN, "approved sv_01"]

    assert steps[4].exit_code == 0
    assert steps[4].stdout.splitlines() == [CLEAN, "matches approved sv_01"]
    assert counts[4] == counts[3]


def test_ac2_edited_requirement_is_refused_then_approved_as_spec_v2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, steps, _ = flow(tmp_path, monkeypatch)

    out = steps[5].stdout.splitlines()
    assert steps[5].exit_code == 1
    assert len(out) == 2
    assert out[0].startswith("constrained-by  REQ-AUTH-001  ")
    assert out[1] == "1 violations, 0 policy problems"

    assert steps[6].exit_code == 0
    assert steps[6].stdout.splitlines() == [CLEAN, "approved sv_02"]

    assert steps[7].exit_code == 0
    assert steps[7].stdout.splitlines() == [CLEAN]


def test_ac3_events_prints_the_log_the_commands_wrote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _, _ = flow(tmp_path, monkeypatch)

    result = run(repo, monkeypatch, "events")

    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    objs = [json.loads(line) for line in lines]
    assert len(objs) == 11
    assert [o["seq"] for o in objs] == sorted(o["seq"] for o in objs)
    assert [o["type"] for o in objs] == [
        *("SpecImported", "SpecValidated"),
        *("SpecValidated", "SpecApproved"),
        *("SpecImported", "SpecValidated"),
        *("SpecImported", "SpecValidated", "SpecApproved"),
        *("SpecImported", "SpecValidated"),
    ]
    assert [o["stream"] for o in objs] == (
        ["spec:sv_01"] * 4 + ["spec:sv_02"] * 5 + ["spec:sv_03"] * 2
    )
    assert [o["actor"] for o in objs] == [
        "human" if o["type"] == "SpecApproved" else "orchestrator" for o in objs
    ]
    firsts = {0, 2, 4, 6, 9}
    for i, o in enumerate(objs):
        expected = None if i in firsts else objs[i - 1]["event_id"]
        assert o["causation_id"] == expected

    filtered = run(repo, monkeypatch, "events", "--stream", "spec:sv_02")
    assert filtered.exit_code == 0
    assert filtered.stdout.splitlines() == lines[4:9]


def test_ac4_projections_hold_two_approved_versions_and_a_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _, _ = flow(tmp_path, monkeypatch)

    versions = query(repo, "SELECT id, status, approved_at FROM spec_versions ORDER BY id")
    assert [(v[0], v[1]) for v in versions] == [
        ("sv_01", "approved"),
        ("sv_02", "approved"),
        ("sv_03", "draft"),
    ]
    assert versions[0][2] is not None
    assert versions[1][2] is not None
    assert versions[2][2] is None

    per_version = "SELECT spec_version, COUNT(*) FROM {} GROUP BY spec_version ORDER BY 1"
    assert query(repo, per_version.format("requirements")) == [
        ("sv_01", 2),
        ("sv_02", 2),
        ("sv_03", 3),
    ]
    assert query(repo, per_version.format("adrs")) == [("sv_01", 1), ("sv_02", 2), ("sv_03", 2)]
    assert query(
        repo, "SELECT status FROM adrs WHERE spec_version = 'sv_02' AND id = 'ADR-002'"
    ) == [("accepted",)]
    assert state_rows(repo) == [(1, max_seq(repo))]


def test_ac5_rebuild_from_the_log_gives_identical_projections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _, _ = flow(tmp_path, monkeypatch)
    before = snapshot(repo)
    events_before = event_rows(repo)

    empty_projections(repo)
    assert snapshot(repo) == {t: [] for t in TABLES}
    assert snapshot(repo) != before

    rebuild(repo)

    after = snapshot(repo)
    for table in TABLES:
        assert after[table] == before[table]
    assert state_rows(repo) == [(1, max_seq(repo))]
    assert event_rows(repo) == events_before


def test_ac6_approve_spec_runs_on_the_rebuilt_projections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _, _ = flow(tmp_path, monkeypatch)
    empty_projections(repo)
    rebuild(repo)
    seq_before = max_seq(repo)

    result = run(repo, monkeypatch, "approve", "spec")

    assert result.exit_code == 0
    assert result.stdout.splitlines() == [CLEAN, "approved sv_03"]
    assert query(
        repo, f"SELECT type, stream FROM events WHERE seq > {seq_before} ORDER BY seq"
    ) == [
        ("SpecValidated", "spec:sv_03"),
        ("SpecApproved", "spec:sv_03"),
    ]
    assert query(repo, "SELECT id, status FROM spec_versions ORDER BY id") == [
        ("sv_01", "approved"),
        ("sv_02", "approved"),
        ("sv_03", "approved"),
    ]
