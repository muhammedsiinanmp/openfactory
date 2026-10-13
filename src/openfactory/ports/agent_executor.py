"""AgentExecutor port: one agent run on a task's worktree.

See docs/spec/phase1-spec.md ("Execution", "Adapter interface") and ADR-005, ADR-014.
"""

from pathlib import Path
from typing import Protocol

from openfactory.domain.agent_run import ContextPack, RunResult
from openfactory.domain.contracts import TaskContract


class AgentExecutor(Protocol):
    def run(
        self, contract: TaskContract, context: ContextPack, workdir: Path, output_dir: Path
    ) -> RunResult:
        """Run the agent on `context` in `workdir` under the contract's limits.

        A failed process is returned, not raised: the result has `exit` `error` or
        `timeout`. `output_dir` is the run's directory, `.openfactory/runs/<run id>`,
        passed relative to the repo; the adapter resolves a relative `output_dir`
        against its own repo and creates the directory when it is missing.
        """
        ...
