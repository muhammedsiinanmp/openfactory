---
description: Decide spec changes with the human and draft the next spec version as a proposal
argument-hint: [extra items or gaps]
---
Take open spec items to a decided, drafted spec version. Never edit docs/spec/: the new
spec is written as a proposal, and I apply it with ./scripts/apply_spec.sh.
Stop and wait for me at each ⏸. A notify marker goes on its own line, as the very last
line of the message, and only when you stop because you need me.

a) Collect the items:
   - every finding in the newest report in docs/spec-audits/ (by the date in its name)
   - the spec items under "Later" in docs/progress.md: the lines that start with
     "Spec wording" or "Spec gap"
   - the items in $ARGUMENTS
   Merge duplicates and keep every source (F-<n>, the Later line, "argument"). For each
   item write the spec section, a proposed answer as the change to the spec text, and
   one real alternative. "No change" is a fair alternative when it is one.
   If there are no items, say so and stop, with no marker.
b) Run the advisor subagent with the id SPEC, the items as numbered questions and the
   proposed answers. Put its output, unedited, under an "Advisor" heading.
c) Give each item a decision id SC-<n>, starting at the next free number: one more than
   the highest SC id in docs/decisions.md, or SC-1 if there is none. Show each item with
   its SC id, section, proposed answer, alternative and the advisor's verdict, and ask
   me to decide each one.
   ⏸ End with [[notify:question|SPEC|<number of items>]], or
   [[notify:attention|SPEC|<number of disagreements>]] if the advisor marked any item
   DISAGREE. Change nothing before I answer, and do not act on the advisor's
   recommendation.
d) After my typed answers. An item I did not answer is not decided: ask again for it
   and nothing else. An item I defer stays where it is and gets no row.
   1. The next version is the minor version after the spec's "Version" line (1.7 gives
      1.8) unless I name another. Run `git switch main && git pull`, then
      `git switch -c spec/v<next>`. An uncommitted audit report comes along.
   2. Write docs/spec-proposals/phase1-spec-v<next>.md: start from a copy of
      docs/spec/phase1-spec.md (`cp`), then make only the decided changes and set the
      version line to the new version and today's date.
   3. At the end of the proposal, add a "## Version history" table, or extend the one
      that is there: `| Version | Date | Changes |`, one row for this version, each
      change in a few words with its SC id. Keep earlier rows as they are.
   4. Add one row per decision to docs/decisions.md, newest first, with the SC id and
      the spec version in the Task column (`SC-<n> · spec v<next>`). An item decided as
      "no change" gets a row too, so its id is not used again.
   5. If a decision hits a trigger from the list under "ADRs" in CLAUDE.md, draft the
      ADR from docs/adr/ADR-000-template.md with Status: proposed. Only I accept it.
   6. Remove the resolved items from "Later" in docs/progress.md. Leave the others.
e) Run `git diff --no-index docs/spec/phase1-spec.md docs/spec-proposals/phase1-spec-v<next>.md`
   and map every changed line to an SC id, hunk by hunk. The version line and the new
   version history row belong to the version bump. Report every other change that maps
   to no SC id; do not invent a decision for it, and do not hide it.
f) Run the audit in .claude/commands/spec-audit.md with the scope
   `proposal docs/spec-proposals/phase1-spec-v<next>.md`, without stopping at its ⏸ and
   without its marker. Report the findings that are new: the ones not in the report
   used in step a. Do not fix them in the proposal; they are items for the next
   /spec-change unless I say otherwise.
g) Run `./scripts/ci_local.sh` and fix what it reports in the files you wrote. Commit
   everything on the spec branch (the proposal, docs/decisions.md, docs/progress.md, the
   audit reports and any ADR) as `docs(spec): draft spec v<next>`, with the SC ids in
   the body. Never commit to main and never push.
   Show me a summary per spec section: what changed and under which SC id. Then the
   unmapped changes from step e, the new findings from step f, and any ADR still
   Status: proposed, which I accept before applying.
   ⏸ Tell me to run `./scripts/apply_spec.sh <next>` and end with
   [[notify:approval|SPEC]].

Extra items from me (may be empty): $ARGUMENTS
