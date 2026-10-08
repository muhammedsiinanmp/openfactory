"""TASK-006 AC2..AC6: FilesystemSpecFiles (docs/tasks/TASK-006-spec-files-port.md)."""

import pytest

from openfactory.adapters.filesystem_spec_files import FilesystemSpecFiles

ADR = "adrs/ADR-001-auth-method.md"


@pytest.fixture
def specs(tmp_path):
    d = tmp_path / "specs"
    d.mkdir()
    return d


def write(specs, rel, data: bytes):
    p = specs / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


@pytest.mark.parametrize(
    "rel, text",
    [
        ("requirements.yaml", "requirements: []\n"),
        ("policies.yaml", "max_retries: 2\n"),
        (ADR, "---\nid: ADR-001\n---\nBody\n"),
    ],
)
def test_ac2_read_returns_full_text_of_each_spec_file(specs, rel, text):
    write(specs, "requirements.yaml", b"requirements: []\n")
    write(specs, "policies.yaml", b"max_retries: 2\n")
    write(specs, ADR, b"---\nid: ADR-001\n---\nBody\n")
    result = FilesystemSpecFiles(specs).read(rel)
    assert isinstance(result, str)
    assert result == text


def test_ac3_read_decodes_utf8_explicitly(specs):
    text = "Café ≥ 1"
    write(specs, "requirements.yaml", text.encode("utf-8"))
    assert FilesystemSpecFiles(specs).read("requirements.yaml") == text


def test_ac4_list_adrs_returns_sorted_md_files_directly_in_adrs(specs):
    for name in ("ADR-002-b.md", "ADR-001-a.md", "notes.md", "README.txt"):
        write(specs, f"adrs/{name}", f"text of {name}".encode())
    files = FilesystemSpecFiles(specs)
    paths = files.list_adrs()
    assert paths == ["adrs/ADR-001-a.md", "adrs/ADR-002-b.md", "adrs/notes.md"]
    for p in paths:
        assert files.read(p) == f"text of {p.split('/')[-1]}"


def test_ac5_list_adrs_empty_when_adrs_dir_missing(specs):
    assert FilesystemSpecFiles(specs).list_adrs() == []


def test_ac5_list_adrs_empty_when_adrs_dir_empty(specs):
    (specs / "adrs").mkdir()
    assert FilesystemSpecFiles(specs).list_adrs() == []


@pytest.mark.parametrize("rel", ["requirements.yaml", "policies.yaml"])
def test_ac5_read_returns_none_for_missing_file(specs, rel):
    assert FilesystemSpecFiles(specs).read(rel) is None


def test_ac5_read_returns_empty_string_for_existing_empty_file(specs):
    write(specs, "policies.yaml", b"")
    assert FilesystemSpecFiles(specs).read("policies.yaml") == ""


def test_ac6_read_does_not_translate_crlf(specs):
    write(specs, ADR, b"---\r\nid: ADR-001\r\n---\r\nBody\r\n")
    assert FilesystemSpecFiles(specs).read(ADR) == "---\r\nid: ADR-001\r\n---\r\nBody\r\n"


def test_ac6_read_leaves_lf_unchanged(specs):
    write(specs, ADR, b"a\nb\n")
    assert FilesystemSpecFiles(specs).read(ADR) == "a\nb\n"
