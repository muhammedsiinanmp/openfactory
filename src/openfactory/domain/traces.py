"""Requirement and file traces: what the `Traces` port's `requirement_trace` and
`file_trace` return.

See "Traceability" ("Queries") and "CLI commands" ("Output", `trace` and `why`) in
docs/spec/phase1-spec.md and ADR-018. `TracedTask` is a traced task with its current
state; `TracedCommit` is a commit of such a task; `TracedTest` is a test tagged with the
requirement (`tagged`) or one whose file a traced commit changed. `TraceLink` is one link
of the "Traceability" table, in its stored direction with its `source`, as the rebuild of
links from git returns it.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from openfactory.domain.payloads import CommitSha, TaskId
from openfactory.domain.states import TaskState

LinkKind = Literal["requirement", "adr", "task", "run", "commit", "file", "test"]
LinkSource = Literal["spec", "contract", "trailer", "diff", "test_tag"]


class TracedTask(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: TaskId
    state: TaskState


class TracedCommit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sha: CommitSha
    task_id: TaskId


class TracedTest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: str
    tagged: bool


class RequirementTrace(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tasks: list[TracedTask]
    commits: list[TracedCommit]
    files: list[str]
    tests: list[TracedTest]


class FileTrace(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    commits: list[TracedCommit]
    tasks: list[TracedTask]
    requirements: list[str]
    adrs: list[str]


# Config as class arguments, so pyright sees the model as frozen and hashable (a set entry).
class TraceLink(BaseModel, frozen=True, extra="forbid"):
    from_kind: LinkKind
    from_id: str
    to_kind: LinkKind
    to_id: str
    source: LinkSource
