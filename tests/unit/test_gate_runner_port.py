"""TASK-059 AC1 to AC5: GateRunner port, GateOutput, MarkerLine (docs/tasks/TASK-059-*.md)."""

import ast
import inspect
from pathlib import Path
from typing import Protocol, get_args, get_type_hints

import pytest
from pydantic import ValidationError

OUTPUT = {"passed": True, "text": "ok", "finding": False, "marker_lines": []}
LINE_JSON = (
    '{"node_id": "tests/test_login.py::test_x", '
    '"file": "tests/test_login.py", "req": ["REQ-AUTH-001"]}'
)


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


# AC1


def test_ac1_gate_output_fields_in_order_and_all_required():
    from openfactory.domain.gates import GateOutput

    assert list(GateOutput.model_fields) == ["passed", "text", "finding", "marker_lines"]
    assert all(f.is_required() for f in GateOutput.model_fields.values())


def test_ac1_gate_output_field_types():
    from openfactory.domain.gates import GateOutput, MarkerLine

    hints = get_type_hints(GateOutput)
    assert hints["passed"] is bool
    assert hints["finding"] is bool
    assert hints["text"] is str
    assert hints["marker_lines"] == list[MarkerLine]


def test_ac1_gate_output_accepts_empty_and_filled_marker_lines():
    from openfactory.domain.gates import GateOutput, MarkerLine

    assert GateOutput(**OUTPUT).marker_lines == []
    line = MarkerLine(node_id="tests/a.py::t", file="tests/a.py", req=["REQ-A-001"])
    assert GateOutput(**{**OUTPUT, "marker_lines": [line]}).marker_lines == [line]


@pytest.mark.parametrize("name", list(OUTPUT))
def test_ac1_gate_output_rejects_a_missing_field(name):
    from openfactory.domain.gates import GateOutput

    with pytest.raises(ValidationError):
        GateOutput(**{k: v for k, v in OUTPUT.items() if k != name})


def test_ac1_gate_output_rejects_unknown_key_and_is_frozen():
    from openfactory.domain.gates import GateOutput

    with pytest.raises(ValidationError):
        GateOutput(**OUTPUT, extra=1)
    out = GateOutput(**OUTPUT)
    with pytest.raises(ValidationError):
        out.passed = False


# AC2


def test_ac2_marker_line_round_trips_the_spec_json():
    import json

    from openfactory.domain.gates import MarkerLine

    line = MarkerLine.model_validate_json(LINE_JSON)
    assert line.file == "tests/test_login.py"
    assert line.req == ["REQ-AUTH-001"]
    assert line.model_dump(mode="json") == json.loads(LINE_JSON)


def test_ac2_marker_line_accepts_empty_req():
    from openfactory.domain.gates import MarkerLine

    assert (
        MarkerLine.model_validate_json(
            '{"node_id": "tests/a.py::t", "file": "tests/a.py", "req": []}'
        ).req
        == []
    )


@pytest.mark.parametrize(
    "raw",
    [
        '{"node_id": "a.py::t", "file": "a.py"}',
        '{"node_id": "a.py::t", "req": []}',
        '{"node_id": "a.py::t", "file": "a.py", "req": [], "x": 1}',
    ],
    ids=["no-req", "no-file", "unknown-key"],
)
def test_ac2_marker_line_rejects_missing_field_or_unknown_key(raw):
    from openfactory.domain.gates import MarkerLine

    with pytest.raises(ValidationError):
        MarkerLine.model_validate_json(raw)


def test_task079_ac2_marker_line_fields_are_node_id_file_req_and_node_id_is_required():
    from openfactory.domain.gates import MarkerLine

    assert list(MarkerLine.model_fields) == ["node_id", "file", "req"]
    with pytest.raises(ValidationError):
        MarkerLine.model_validate_json('{"file": "a.py", "req": []}')


def test_ac2_marker_line_is_frozen():
    from openfactory.domain.gates import MarkerLine

    line = MarkerLine(node_id="a.py::t", file="a.py", req=[])
    with pytest.raises(ValidationError):
        line.file = "b.py"


# AC3


def test_ac3_gate_runner_is_a_protocol_with_run_and_missing_tool():
    from openfactory.ports.gate_runner import GateRunner

    assert issubclass(GateRunner, Protocol)
    assert getattr(GateRunner, "_is_protocol", False)
    public = {
        name
        for name, value in vars(GateRunner).items()
        if not name.startswith("_") and callable(value)
    }
    assert public == {"run", "missing_tool"}


def test_ac3_run_signature():
    from openfactory.domain.gates import GateOutput, ProcessGate
    from openfactory.ports.gate_runner import GateRunner

    assert list(inspect.signature(GateRunner.run).parameters) == [
        "self",
        "gate",
        "worktree",
        "timeout_s",
    ]
    assert get_type_hints(GateRunner.run) == {
        "gate": ProcessGate,
        "worktree": Path,
        "timeout_s": int,
        "return": GateOutput,
    }


def test_ac3_missing_tool_signature():
    from openfactory.ports.gate_runner import GateRunner

    assert list(inspect.signature(GateRunner.missing_tool).parameters) == ["self"]
    assert get_type_hints(GateRunner.missing_tool) == {"return": str | None}


# AC4


def test_ac4_process_gate_is_exactly_ruff_pytest_gitleaks():
    from openfactory.domain.gates import ProcessGate

    assert get_args(ProcessGate) == ("ruff", "pytest", "gitleaks")


def test_ac4_process_gate_is_recordable_and_excludes_builtin_gates():
    from openfactory.domain.gates import ProcessGate
    from openfactory.domain.payloads import GateName

    names = get_args(GateName)
    assert set(get_args(ProcessGate)) <= set(names)
    assert not {"path_check", "review"} & set(get_args(ProcessGate))


# AC5


def test_ac5_port_imports_only_domain_from_openfactory():
    from openfactory.ports import gate_runner

    own = {n for n in imported_modules(gate_runner) if n.split(".")[0] == "openfactory"}
    assert own
    assert all(n == "openfactory.domain" or n.startswith("openfactory.domain.") for n in own)


def test_ac5_domain_gates_imports_no_ports_adapters_or_app():
    from openfactory.domain import gates

    forbidden = ("openfactory.ports", "openfactory.adapters", "openfactory.app")
    assert not forbidden_in(gates, forbidden)
