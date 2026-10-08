"""Spec loader: reads the spec files through the SpecFiles port into a `SpecSet`.

See docs/spec/phase1-spec.md ("Spec input format": "Loading", "Validation rules"). A file
that cannot be loaded into the models is reported under the rule `schema`; the content
rules in `domain.spec_validation` are the caller's to run, and only on a loaded spec set.

`load_policy` reads `policies.yaml` into a `Policy` the same way ("Policies"). The policy
is not part of the spec set: `load_spec` never reads it, and its problems are separate.
"""

from typing import Any, cast

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from openfactory.domain.models import Adr, Requirement, SpecSet
from openfactory.domain.policy import Policy
from openfactory.domain.spec_validation import Rule, SpecViolation
from openfactory.ports.spec_files import SpecFiles

REQUIREMENTS_PATH = "requirements.yaml"
POLICY_PATH = "policies.yaml"


class SpecLoadResult(BaseModel):
    """Either the loaded spec set or the `schema` violations, never both."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    spec: SpecSet | None = None
    violations: list[SpecViolation] = []


class PolicyLoadResult(BaseModel):
    """Either the loaded policy or the `schema` violations, never both."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy: Policy | None = None
    violations: list[SpecViolation] = []


class _RequirementsFile(BaseModel):
    """Top level of `requirements.yaml`; each requirement is validated on its own."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    components: list[str] = []
    requirements: list[Any] = []


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects a mapping with the same key twice."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: list[Any] = []
        for key_node, _ in node.value:
            key = cast("Any", self.construct_object(key_node, deep=True))  # pyright: ignore[reportUnknownMemberType]
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {key!r}", key_node.start_mark
                )
            seen.append(key)
        return super().construct_mapping(node, deep)


def _repo_path(path: str) -> str:
    # The port's paths are relative to `specs/`; a violation subject is relative to the repo.
    return f"specs/{path}"


def _schema(subject: str, message: str) -> SpecViolation:
    return SpecViolation(rule=Rule.schema, subject=subject, message=message)


def _read(files: SpecFiles, path: str) -> str | None | SpecViolation:
    try:
        return files.read(path)
    except UnicodeDecodeError:
        return _schema(_repo_path(path), "not valid UTF-8")


def _parse_yaml(text: str, path: str) -> Any | SpecViolation:
    try:
        return yaml.load(text, Loader=_UniqueKeyLoader)
    # PyYAML raises a plain ValueError for an impossible date such as 2026-02-30.
    except (yaml.YAMLError, ValueError) as error:
        return _schema(_repo_path(path), f"invalid YAML: {' '.join(str(error).split())}")


def _readable_id(raw: object) -> str | None:
    if isinstance(raw, dict):
        id_ = cast("dict[object, object]", raw).get("id")
        if isinstance(id_, str):
            return id_
    return None


def _from_validation_error(error: ValidationError, subject: str) -> list[SpecViolation]:
    """One violation per Pydantic error, with the field path in the message."""
    violations: list[SpecViolation] = []
    for detail in error.errors():
        field_path = ".".join(str(part) for part in detail["loc"])
        message = f"{field_path}: {detail['msg']}" if field_path else detail["msg"]
        violations.append(_schema(subject, message))
    return violations


def _requirement_subject(raw: object, loc: tuple[int | str, ...], file_subject: str) -> str:
    """The nearest enclosing item with a readable id: criterion, requirement, then file."""
    fallback = _readable_id(raw) or file_subject
    if isinstance(raw, dict) and len(loc) >= 2 and loc[0] == "acceptance_criteria":
        criteria = cast("dict[object, object]", raw).get("acceptance_criteria")
        index = loc[1]
        if isinstance(criteria, list) and isinstance(index, int):
            items = cast("list[object]", criteria)
            if index < len(items) and (criterion_id := _readable_id(items[index])) is not None:
                return criterion_id
    return fallback


def _load_requirements(files: SpecFiles) -> tuple[_RequirementsFile | None, list[SpecViolation]]:
    subject = _repo_path(REQUIREMENTS_PATH)
    text = _read(files, REQUIREMENTS_PATH)
    if isinstance(text, SpecViolation):
        return None, [text]
    if text is None:
        return None, [_schema(subject, "missing")]
    raw = _parse_yaml(text, REQUIREMENTS_PATH)
    if isinstance(raw, SpecViolation):
        return None, [raw]
    if not isinstance(raw, dict):
        return None, [_schema(subject, "top level is not a mapping")]
    try:
        return _RequirementsFile.model_validate(raw), []
    except ValidationError as error:
        return None, _from_validation_error(error, subject)


def _validate_requirements(
    top: _RequirementsFile,
) -> tuple[list[Requirement], list[SpecViolation]]:
    subject = _repo_path(REQUIREMENTS_PATH)
    requirements: list[Requirement] = []
    violations: list[SpecViolation] = []
    for index, raw in enumerate(top.requirements):
        try:
            requirements.append(Requirement.model_validate(raw))
        except ValidationError as error:
            for detail in error.errors():
                loc = detail["loc"]
                field_path = ".".join(str(part) for part in ("requirements", index, *loc))
                violations.append(
                    _schema(
                        _requirement_subject(raw, loc, subject), f"{field_path}: {detail['msg']}"
                    )
                )
    return requirements, violations


def _split_adr(text: str) -> tuple[str, str] | None:
    """Return (front matter, body) with `\\n` line endings, or None without front matter."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines[0] != "---" or "---" not in lines[1:]:
        return None
    end = lines.index("---", 1)
    return "\n".join(lines[1:end]), "\n".join(lines[end + 1 :])


def _load_adr(files: SpecFiles, path: str) -> Adr | list[SpecViolation]:
    subject = _repo_path(path)
    text = _read(files, path)
    if isinstance(text, SpecViolation):
        return [text]
    if text is None:
        return [_schema(subject, "missing")]
    parts = _split_adr(text)
    if parts is None:
        return [_schema(subject, "no front matter: expected a `---` line, YAML, a `---` line")]
    front_matter_text, body = parts
    front_matter = _parse_yaml(front_matter_text, path)
    if isinstance(front_matter, SpecViolation):
        return [front_matter]
    if not isinstance(front_matter, dict):
        return [_schema(subject, "front matter is not a mapping")]
    fields = cast("dict[object, object]", front_matter)
    try:
        return Adr.model_validate({**fields, "body": body})
    except ValidationError as error:
        return _from_validation_error(error, _readable_id(fields) or subject)


def load_spec(files: SpecFiles) -> SpecLoadResult:
    """Load `requirements.yaml` and every `adrs/*.md`, collecting every `schema` violation.

    Requirements keep file order and ADRs follow `list_adrs` order.
    """
    top, violations = _load_requirements(files)
    requirements: list[Requirement] = []
    if top is not None:
        requirements, violations = _validate_requirements(top)

    adrs: list[Adr] = []
    for path in files.list_adrs():
        loaded = _load_adr(files, path)
        if isinstance(loaded, Adr):
            adrs.append(loaded)
        else:
            violations.extend(loaded)

    if violations or top is None:
        return SpecLoadResult(violations=violations)
    return SpecLoadResult(
        spec=SpecSet(components=top.components, requirements=requirements, adrs=adrs)
    )


def load_policy(files: SpecFiles) -> PolicyLoadResult:
    """Load `policies.yaml`, collecting every `schema` violation. Reads no other file."""
    subject = _repo_path(POLICY_PATH)
    text = _read(files, POLICY_PATH)
    if isinstance(text, SpecViolation):
        return PolicyLoadResult(violations=[text])
    if text is None:
        return PolicyLoadResult(violations=[_schema(subject, "missing; run openfactory init")])
    raw = _parse_yaml(text, POLICY_PATH)
    if isinstance(raw, SpecViolation):
        return PolicyLoadResult(violations=[raw])
    # Every key is optional, so an empty file (or only comments) is the default policy.
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        return PolicyLoadResult(violations=[_schema(subject, "top level is not a mapping")])
    try:
        return PolicyLoadResult(policy=Policy.model_validate(raw))
    except ValidationError as error:
        return PolicyLoadResult(violations=_from_validation_error(error, subject))
