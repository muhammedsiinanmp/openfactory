"""Review prompt: the one text a reviewer call receives.

See docs/spec/phase1-spec.md ("Gates and remediation": "The review gate"). The prompt is the
task contract and the text of `git diff --cached <base>`, after a fixed instruction block.
With rejections it is the retry prompt: the same text with the rejection lines added, as
for a planner call. Its hash is `planner_prompt.context_hash`.
"""

from collections.abc import Sequence

from openfactory.domain.contracts import TaskContract
from openfactory.domain.plan_checks import PlanRejection, rejection_lines

_INSTRUCTIONS = """\
You are the reviewer. Judge whether the staged diff below meets the task contract's \
objective and acceptance criteria within its allowed_paths.

Reply with one structured result of the form {"verdict": "approve" | "reject", "comments": "..."}:
- verdict: "approve" when the diff meets the contract, "reject" when it does not
- comments: the reasons for the verdict"""


def _section(heading: str, body: str) -> str:
    return f"## {heading}\n{body}"


def build_review_prompt(
    contract: TaskContract,
    diff: str,
    rejections: Sequence[PlanRejection] = (),
) -> str:
    """The first prompt, or with `rejections` the retry prompt."""
    sections = [
        _INSTRUCTIONS,
        _section("Task contract", contract.model_dump_json(indent=2)),
        _section("Staged diff", diff),
    ]
    if rejections:
        sections.append(
            _section(
                "Rejections of your earlier reply (rule  subject  message); "
                "reply again with a verdict that has none of them",
                "\n".join(rejection_lines(rejections)),
            )
        )
    return "\n\n".join(sections) + "\n"
