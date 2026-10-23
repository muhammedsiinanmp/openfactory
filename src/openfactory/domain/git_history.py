"""A commit read back from git, for the rebuild of links from git.

See "Ids" (M5) and "Traceability" in docs/spec/phase1-spec.md, and ADR-018.
"""

from pydantic import BaseModel, ConfigDict


class BranchCommit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sha: str
    # (key, value) pairs in git's order, unfolded; a repeated key is kept.
    trailers: list[tuple[str, str]]
    # The paths changed against the parent, relative to the root with `/`.
    files: list[str]
