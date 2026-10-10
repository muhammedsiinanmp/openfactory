"""TASK-018 AC1..AC5: the `events` command (see docs/tasks/TASK-018-cli-events.md)."""

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

runner = CliRunner()

DB = Path(".openfactory/openfactory.db")
REQS = Path("specs/requirements.yaml")

VALID_REQUIREMENTS = """\
components: [auth]
requirements:
  - id: REQ-AUTH-001
    title: Login
    statement: Users can log in.
    priority: must
    components: [auth]
    acceptance_criteria:
      - id: AC-AUTH-001-1
        text: Valid login returns a JWT.
"""

# Returned order: missing-acceptance-criteria 002, missing-acceptance-criteria 001,
# constrained-by 002. Sorted order differs.
UNSORTED_REQUIREMENTS = """\
requirements:
  - id: REQ-AUTH-002
    title: Logout
    statement: Users can log out.
    priority: should
    constrained_by: [ADR-099]
  - id: REQ-AUTH-001
    title: Login
    statement: Users can log in.
    priority: must
"""

KEYS = {"seq", "event_id", "stream", "type", "payload", "actor", "causation_id", "created_at"}


def make_repo(tmp_path: Path, requirements: str = VALID_REQUIREMENTS) -> Path:
    from openfactory.cli import app

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    assert runner.invoke(app, ["init", str(repo)]).exit_code == 0
    (repo / REQS).write_text(requirements, encoding="utf-8")
    return repo


def run(repo: Path, monkeypatch: pytest.MonkeyPatch, *args: str):
    from openfactory.cli import app

    monkeypatch.chdir(repo)
    return runner.invoke(app, list(args))


def run_ok(repo: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> None:
    assert run(repo, monkeypatch, *args).exit_code in (0, 1)


def query(repo: Path, sql: str) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(repo / DB)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def approved_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, requirements: str) -> Path:
    repo = make_repo(tmp_path, requirements)
    assert run(repo, monkeypatch, "approve", "spec").exit_code == 0
    return repo


def test_ac1_prints_one_json_object_per_event_matching_the_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = approved_repo(tmp_path, monkeypatch, VALID_REQUIREMENTS)

    result = run(repo, monkeypatch, "events")

    assert result.exit_code == 0
    assert result.stderr == ""
    lines = result.stdout.splitlines()
    assert len(lines) == 3
    objs = [json.loads(line) for line in lines]
    assert all(set(o) == KEYS for o in objs)
    assert [o["seq"] for o in objs] == sorted(o["seq"] for o in objs)
    assert [o["type"] for o in objs] == ["SpecImported", "SpecValidated", "SpecApproved"]
    for o in objs:
        row = query(
            repo,
            "SELECT event_id, stream, type, actor, causation_id, payload FROM events "
            f"WHERE seq = {o['seq']}",
        )[0]
        assert (o["event_id"], o["stream"], o["type"], o["actor"], o["causation_id"]) == row[:5]
        assert isinstance(o["payload"], dict)
        assert o["payload"] == json.loads(row[5])
    assert objs[0]["causation_id"] is None
    assert objs[1]["causation_id"] == objs[0]["event_id"]
    assert objs[2]["causation_id"] == objs[1]["event_id"]


def test_ac2_lines_are_canonical_json_and_created_at_is_as_stored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = approved_repo(tmp_path, monkeypatch, VALID_REQUIREMENTS.replace("Login", "Connexion é"))

    result = run(repo, monkeypatch, "events")

    lines = result.stdout.splitlines()
    assert len(lines) == 3
    for line in lines:
        obj = json.loads(line)
        assert line == json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        stored = query(repo, f"SELECT created_at FROM events WHERE seq = {obj['seq']}")[0][0]
        assert obj["created_at"] == stored
        assert stored.endswith("+00:00")
    assert "é" in lines[0]
    assert "\\u" not in lines[0]
    approved_at = query(repo, "SELECT approved_at FROM spec_versions WHERE id = 'sv_01'")[0][0]
    assert json.loads(lines[2])["created_at"] == approved_at


def test_ac3_list_order_is_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path, UNSORTED_REQUIREMENTS)
    run_ok(repo, monkeypatch, "validate")
    stored = json.loads(
        query(repo, "SELECT payload FROM events WHERE type = 'SpecValidated'")[0][0]
    )["violations"]
    key = [(v["rule"], v["subject"], v["message"]) for v in stored]
    assert key != sorted(key)

    result = run(repo, monkeypatch, "events")

    validated = [
        json.loads(ln) for ln in result.stdout.splitlines() if '"type":"SpecValidated"' in ln
    ]
    assert len(validated) == 1
    assert validated[0]["payload"]["violations"] == stored


def test_ac4_stream_filter_returns_only_that_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = approved_repo(tmp_path, monkeypatch, VALID_REQUIREMENTS)
    (repo / REQS).write_text(
        VALID_REQUIREMENTS.replace("Users can log in.", "Users can sign in."), encoding="utf-8"
    )
    run_ok(repo, monkeypatch, "validate")
    everything = run(repo, monkeypatch, "events").stdout.splitlines()
    by_seq = {json.loads(ln)["seq"]: ln for ln in everything}

    result = run(repo, monkeypatch, "events", "--stream", "spec:sv_02")

    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    objs = [json.loads(ln) for ln in lines]
    assert objs
    assert {o["stream"] for o in objs} == {"spec:sv_02"}
    assert [o["seq"] for o in objs] == sorted(o["seq"] for o in objs)
    assert all(by_seq[o["seq"]] == ln for o, ln in zip(objs, lines, strict=True))
    assert len(lines) < len(everything)

    none = run(repo, monkeypatch, "events", "--stream", "spec:sv_99")
    assert none.exit_code == 0
    assert none.stdout == ""
    assert none.stderr == ""


def test_ac5_fails_without_init_and_creates_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()

    result = run(plain, monkeypatch, "events")

    assert result.exit_code == 1
    assert "run `openfactory init` first" in result.stderr
    assert result.stdout == ""
    assert not (plain / ".openfactory").exists()


def test_ac5_empty_log_prints_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path)

    result = run(repo, monkeypatch, "events")

    assert result.exit_code == 0
    assert result.stdout == ""


def test_ac5_missing_database_is_recreated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path)
    (repo / DB).unlink()

    result = run(repo, monkeypatch, "events")

    assert result.exit_code == 0
    assert result.stdout == ""
    assert (repo / DB).is_file()
    assert query(repo, "SELECT name FROM sqlite_master WHERE name = 'events'") == [("events",)]
