"""TASK-047 AC1 to AC3: AgentExecutor port and RunResult (docs/tasks/TASK-047-*.md)."""

import ast
import inspect
from pathlib import Path
from typing import Protocol, get_type_hints

import pytest
from pydantic import ValidationError

FIELDS = ("exit", "model", "tokens_in", "tokens_out", "cost_usd", "duration_s", "error", "summary")
OK = {
    "exit": "ok",
    "model": "claude-x",
    "tokens_in": 10,
    "tokens_out": 20,
    "cost_usd": 0.5,
    "duration_s": 1.5,
    "error": None,
    "summary": "done",
}
TIMEOUT = {
    "exit": "timeout",
    "model": None,
    "tokens_in": None,
    "tokens_out": None,
    "cost_usd": None,
    "duration_s": 9.0,
    "error": "timed out",
    "summary": "",
}


def imported_modules(module):
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


def forbidden_in(module, forbidden):
    return {
        n
        for n in imported_modules(module)
        if any(n == f or n.startswith(f + ".") for f in forbidden)
    }


def test_ac1_agent_executor_is_a_protocol_with_only_run():
    from openfactory.ports.agent_executor import AgentExecutor

    assert issubclass(AgentExecutor, Protocol)
    assert getattr(AgentExecutor, "_is_protocol", False)
    public = {
        name
        for name, value in vars(AgentExecutor).items()
        if not name.startswith("_") and callable(value)
    }
    assert public == {"run"}


def test_ac1_run_signature_is_contract_context_workdir_output_dir():
    from openfactory.domain.agent_run import ContextPack, RunResult
    from openfactory.domain.contracts import TaskContract
    from openfactory.ports.agent_executor import AgentExecutor

    params = list(inspect.signature(AgentExecutor.run).parameters)
    assert params == ["self", "contract", "context", "workdir", "output_dir"]
    hints = get_type_hints(AgentExecutor.run)
    assert hints == {
        "contract": TaskContract,
        "context": ContextPack,
        "workdir": Path,
        "output_dir": Path,
        "return": RunResult,
    }


def test_ac1_port_module_imports_no_adapters_or_app():
    from openfactory.ports import agent_executor

    assert not forbidden_in(agent_executor, ("openfactory.adapters", "openfactory.app"))


def test_ac1_domain_agent_run_imports_no_ports_adapters_or_app():
    from openfactory.domain import agent_run

    forbidden = ("openfactory.ports", "openfactory.adapters", "openfactory.app")
    assert not forbidden_in(agent_run, forbidden)


def test_ac2_every_field_is_required():
    from openfactory.domain.agent_run import RunResult

    for name in FIELDS:
        with pytest.raises(ValidationError):
            RunResult(**{k: v for k, v in OK.items() if k != name})


@pytest.mark.parametrize("value", ["ok", "error", "timeout"])
def test_ac2_exit_accepts_the_three_values(value):
    from openfactory.domain.agent_run import RunResult

    assert RunResult(**{**OK, "exit": value}).exit == value


def test_ac2_exit_rejects_any_other_value():
    from openfactory.domain.agent_run import RunResult

    with pytest.raises(ValidationError):
        RunResult(**{**OK, "exit": "failed"})


@pytest.mark.parametrize("name", ["model", "tokens_in", "tokens_out", "cost_usd", "error"])
def test_ac2_optional_fields_accept_none(name):
    from openfactory.domain.agent_run import RunResult

    assert getattr(RunResult(**{**OK, name: None}), name) is None


@pytest.mark.parametrize("name", ["duration_s", "summary"])
def test_ac2_duration_and_summary_reject_none(name):
    from openfactory.domain.agent_run import RunResult

    with pytest.raises(ValidationError):
        RunResult(**{**OK, name: None})


def test_ac2_context_pack_is_str():
    from openfactory.domain.agent_run import ContextPack

    assert ContextPack is str


def test_ac3_run_result_fields_without_summary_are_the_payload_fields_without_run_id():
    from openfactory.domain.agent_run import RunResult
    from openfactory.domain.payloads import AgentRunFinishedPayload

    result_fields = set(RunResult.model_fields) - {"summary"}
    payload_fields = set(AgentRunFinishedPayload.model_fields) - {"run_id"}
    assert result_fields == payload_fields


@pytest.mark.parametrize("values", [OK, TIMEOUT], ids=["ok", "timeout"])
def test_ac3_result_becomes_the_payload_with_the_same_seven_values(values):
    from openfactory.domain.agent_run import RunResult
    from openfactory.domain.payloads import AgentRunFinishedPayload

    result = RunResult(**values)
    payload = AgentRunFinishedPayload(run_id="run_0002", **result.model_dump(exclude={"summary"}))
    expected = {k: v for k, v in values.items() if k != "summary"}
    assert payload.model_dump(exclude={"run_id"}) == expected
