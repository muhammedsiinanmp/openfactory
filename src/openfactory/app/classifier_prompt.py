"""Classifier prompt: the one text a classifier call receives.

See docs/spec/phase1-spec.md ("Spec diff and impact analysis": "Step 2", "Classifier
checks"). The prompt is fixed instructions that define the three kinds, then, for each
modified requirement in ascending id, its `from` and `to` versions with their acceptance
criteria and the bodies of the ADRs each version is constrained by, each read from that
version's own spec set. With rejections it is the retry prompt: the same text with the
rejection lines added, as for a planner call. Its hash is `planner_prompt.context_hash`.
"""

from collections.abc import Sequence

from openfactory.domain.classifier import ClassifierRejection
from openfactory.domain.models import Requirement, SpecSet
from openfactory.domain.plan_checks import rejection_lines
from openfactory.domain.spec_diff import SpecDiff

_INSTRUCTIONS = """\
You are the change classifier. Each requirement below changed between two approved spec \
versions. Classify each change as one of three kinds:
- cosmetic: only the wording changed; what the system must do did not. It triggers no work, \
so its obsolete_criteria and new_work are empty.
- behavioral: the requirement keeps its purpose, but what the system must do changed: \
behaviour or acceptance criteria were added, removed or altered. Existing work is revised.
- replacement: the requirement now asks for a different way of meeting its purpose, so the \
existing implementation is replaced.

Reply with one structured result of the form {"changes": [...]}, one entry per requirement \
below. Each entry has:
- req_id: the requirement's id
- kind: "cosmetic", "behavioral" or "replacement"
- rationale: why the change has that kind
- obsolete_criteria: the ids of the from version's acceptance criteria that are no longer valid
- new_work: short descriptions of the work the change needs

Rules:
- Give one entry for each requirement below and none for any other; no requirement twice.
- obsolete_criteria holds only acceptance criterion ids of that requirement's from version.
- A cosmetic entry has empty obsolete_criteria and new_work.
- A requirement whose to version lacks a criterion of its from version, or has a criterion \
its from version lacks, is not cosmetic."""


_NONE = "(none)"


def _version_text(label: str, requirement: Requirement, spec: SpecSet) -> str:
    lines = [
        f"### {label}: {requirement.id}: {requirement.title}",
        f"statement: {requirement.statement}",
        f"priority: {requirement.priority.value}",
        f"components: {', '.join(requirement.components)}",
        f"constrained_by: {', '.join(requirement.constrained_by) or _NONE}",
        "acceptance criteria:",
    ]
    lines.extend(f"- {ac.id}: {ac.text}" for ac in requirement.acceptance_criteria)
    lines.append("ADRs:")
    adrs = [adr for adr in spec.adrs if adr.id in requirement.constrained_by]
    lines.extend([f'<adr id="{adr.id}">\n{adr.body}\n</adr>' for adr in adrs] or [_NONE])
    return "\n".join(lines)


def _section(heading: str, lines: Sequence[str]) -> str:
    return "\n".join([f"## {heading}", *(lines or [_NONE])])


def build_classifier_prompt(
    old: SpecSet,
    new: SpecSet,
    diff: SpecDiff,
    rejections: Sequence[ClassifierRejection] = (),
) -> str:
    """The first prompt, or with `rejections` the retry prompt; `diff` is `diff_specs(old, new)`."""
    old_requirements = {r.id: r for r in old.requirements}
    new_requirements = {r.id: r for r in new.requirements}
    modified = sorted(r.id for r in diff.requirements if r.change == "modified")

    sections = [_INSTRUCTIONS]
    for req_id in modified:
        sections.append(
            "\n\n".join(
                [
                    f"## {req_id}",
                    _version_text("from", old_requirements[req_id], old),
                    _version_text("to", new_requirements[req_id], new),
                ]
            )
        )
    if rejections:
        sections.append(
            _section(
                "Rejections of your earlier reply (rule  subject  message); "
                "reply again with a classification that has none of them",
                rejection_lines(rejections),
            )
        )
    return "\n\n".join(sections) + "\n"
