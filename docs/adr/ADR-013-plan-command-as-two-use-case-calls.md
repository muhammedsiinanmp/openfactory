# ADR-013: The `plan` command calls two use-case functions and prints the warning between them

- Status: proposed
- Date: 2026-10-11

## Context
`openfactory plan` warns when the spec files differ from the approved version. The spec
gives the warning a time, not only a place among the lines ("CLI commands" › "Output"):
"The warning is written after the first three refusals have been checked and before
`git ls-files` runs". After `git ls-files` come up to two planner calls of up to 300
seconds each.

Two existing rules pull against that sentence:

- Use cases return data and print nothing (decisions row of 2026-10-10, TASK-018), and
  `cli.py` is the module that prints
  ([ADR-011](ADR-011-cli-composition-root.md)).
- `CLAUDE.md` says "`init` is the one command whose filesystem work lives in cli.py;
  every other command calls a use case", which has so far meant one call per command.

A single use case that checks the refusals, runs `git ls-files` and calls the planner
cannot have its warning printed at the stated time unless it prints, or is told how to.
Audit finding F-7 / M-2 of `docs/spec-audits/2026-10-11-proposal-v1.11.md` left the choice
between the time and a line order to the human. The human chose the time (TASK-031, open
question 8; decisions row of 2026-10-11). The choice shapes the slice of M2 outline item 9
that builds the refusals (9b), and no code depends on it yet.

## Decision
The `plan` command is two use-case functions in `app`, called in turn by `cli.py`.

1. The entry function checks the three refusals in the spec's order (no approved spec
   version, an invalid policy, an approved plan). It returns either a refusal, or the
   approved spec set, the policy and a flag that says whether the spec files differ.
2. `cli.py` prints the refusal and exits, or prints the `spec files differ` warning when
   the flag is set.
3. `cli.py` then calls the second function with what the first returned. It calls
   `GitProvider`, makes the planner call with its single retry, records the events and
   returns the result.

Both functions return data and print nothing. `cli.py` holds no rule: it passes the first
result to the second function unchanged and decides nothing but what to print and the
exit code. Names, signatures and result types are settled in the tasks that build them.

This is a pattern for a command whose output the spec places at a time between two pieces
of work. A command with no such sentence stays one use-case call.

## Alternatives considered
- **One use case that returns a flag; `cli.py` prints the warning first.** The simplest
  shape, with one call per command and one result type. The captured lines come out in
  the same order, but the warning is written after `git ls-files` and after the planner
  calls, so the code would not do what the spec sentence says until the spec is reworded,
  and that rewording changes behaviour. A warning that arrives after the planner call
  also cannot let the human stop before a call is spent on a spec they forgot to approve.
- **A callback passed to the use case.** One call per command, and the time is met. But
  the use case then causes printing, against the TASK-018 row, and its tests need a
  callback recorder to check when the warning fired. Every later command with a similar
  sentence would grow its own callback.
- **`/spec-change` to state a line order.** Cleans the text to fit the simplest shape. It
  costs a spec round and gives up the one thing the warning's timing is good for.

## Consequences
Easier:
- The spec sentence is met as written, with no `/spec-change`.
- The human sees the warning before `git ls-files` and before any planner call, and can
  stop the command.
- Each function is tested alone: the refusals with fakes for `SpecVersions`, `SpecFiles`
  and `Plans`; the planner call with fakes for `GitProvider`, `LLMProvider`, `Runs` and
  the recorder.
- Use cases still return data and print nothing.

Harder:
- One command is two use-case calls, so the `CLAUDE.md` line "every other command calls a
  use case" needs a word from the human ("one or more use cases"), and ADR-011's picture
  of `cli.py` as wiring and printing now includes sequencing two calls.
- The order of the two calls is kept by `cli.py` and by nothing else: the second function
  can be called without the first. Only the integration test of the command shows the
  refusals run before `git ls-files`.
- Two result types where one would do, and the first carries data (the spec set, the
  policy) that `cli.py` only hands on.
- If the entry function and the second function each open a recorder or a read port, the
  wiring in `cli.py` must keep them on one view of the database.
