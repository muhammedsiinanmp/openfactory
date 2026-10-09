---
description: Read-only audit of the spec for one milestone, a proposal, or the whole spec
argument-hint: M<n> | proposal <path> | all
---
Audit the spec. Read only: the one file you write is the report. No other edits, no
staging, no commits, no branch switches. Never edit docs/spec/.

Scope, from $ARGUMENTS:
- `M<n>` (for example M2): the document is docs/spec/phase1-spec.md. Completeness and
  testability cover everything that milestone builds, by "Milestones and definition of
  done", and every section those parts rely on. Report slug: `M<n>`.
- `proposal <path>`: the document is the proposal at <path>, read as if it were the
  spec. Completeness and testability cover the sections that differ from
  docs/spec/phase1-spec.md (`git diff --no-index docs/spec/phase1-spec.md <path>`) and
  every section those rely on. Report slug: `proposal-v<version>`, from the proposal's
  version line.
- `all`: the document is docs/spec/phase1-spec.md, every section. Report slug: `all`.
- Anything else, or nothing: say which scopes exist and stop, with no marker.

1. Read the whole document, docs/decisions.md, every ADR in docs/adr/ (an accepted ADR
   is binding, a proposed one is not), docs/progress.md, and the parts of src/ the scope
   touches.
2. Check, and note the evidence for every problem:
   - Consistency: contradictions between sections, across the whole document whatever
     the scope. Quote both sides.
   - Completeness, for the scope: every command, event, table and rule has its inputs,
     outputs, errors and formats defined. Name what is missing.
   - Ambiguity: wording two careful readers could implement differently. Give both
     readings.
   - Testability: statements no test could pass or fail as written.
   - Decision drift: rows in docs/decisions.md and accepted ADRs whose meaning is not in
     the document. Quote the row date or ADR number.
   - Code drift: behaviour in src/ that the document does not describe, or that
     contradicts it. Give file:line.
3. Draft the findings. Each has:
   - an id, F-1, F-2, ... in report order
   - a class: `blocker` (the scope cannot be planned or built until it is settled), `gap`
     (something is missing, work can start), `drift` (decisions or code and the document
     disagree) or `wording` (the meaning is clear, the text is not)
   - the spec section, by its heading
   - the evidence: quotes, row dates, ADR numbers, file:line
   - a proposed fix: the change to the spec text, or "change the code" when the document
     is right and src/ is wrong
   Do not report style, and do not ask for hardening against exotic inputs.
4. Second pass: run the advisor subagent with the id SPEC and one question per finding,
   "Is F-<n> a real problem, and is the proposed fix right?", with the finding as the
   proposed answer. For a proposal, tell it to read the proposal as well as the spec.
   Then ask it what the audit missed in this scope. Do not drop or change a finding
   because the advisor disagrees; I decide. Add what it found that you missed as new
   findings, marked "(advisor)".
5. Write docs/spec-audits/<YYYY-MM-DD>-<slug>.md, replacing a report of the same name:
   - the scope, the document's version line and the date
   - a count of findings per class
   - the findings, blockers first, each with the five fields from step 3
   - "Advisor": its output, unedited
6. Show me the path, the counts and a one-line list of the findings. Recommend
   `/spec-change` if there is anything to decide.

⏸ End with [[notify:approval|SPEC]] on its own line, as the very last line.
