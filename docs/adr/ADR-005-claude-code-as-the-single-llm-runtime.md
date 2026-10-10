# ADR-005: Claude Code as the single LLM runtime, on a subscription with no API key

- Status: accepted
- Date: 2026-10-09

## Context
The platform calls a model in two ways. An agent runs a task in a worktree (implementer,
reviewer), and a single prompt returns structured output (planner, change classifier).
The spec's scope allows one runtime in Phase 1, "Claude Code headless, behind an adapter
interface", and defers OpenCode, OpenHands and Ollama.

The spec also says all model calls use the user's Claude subscription login and that no
API key is required. Claude Code would use `ANTHROPIC_API_KEY` instead of the
subscription if the variable were set, and the spec did not at first say what an adapter
does in that case (gap G20).

## Decision
Every model call goes through Claude Code headless.

- Agent runs use `claude -p` with JSON output behind the `AgentExecutor` port. The
  adapter runs with a restricted tool allowlist and the worktree as its working
  directory, and parses token usage and cost from the JSON output.
- Planner and classifier calls use `claude -p --output-format json --json-schema` behind
  the `LLMProvider` port. The Pydantic model's JSON Schema is passed in and the
  structured result is read from the envelope. The call runs with tools disabled, a 300
  second time limit and the default model, and the model name reported in the envelope
  is recorded.
- Pydantic still validates every reply. A reply that fails is retried once with the
  validation error in the prompt, then fails. The retry is one function in the app
  layer.
- The adapters start `claude` with `ANTHROPIC_API_KEY` removed from its environment,
  without reading its value, and log one warning if it was present. The subscription
  login is then always the one used.
- The Anthropic SDK is not a dependency (`CLAUDE.md`).

## Alternatives considered
- **The Anthropic API through the SDK, with an API key.** It gives native structured
  output and per-token billing. But the author is on Claude Pro with no API key, and it
  would mean two runtimes, since agent runs would still go through Claude Code (author's
  rationale). `CLAUDE.md` makes this a rule: all LLM calls go through `claude -p`, and
  the Anthropic SDK is never added and `ANTHROPIC_API_KEY` is never read.
- **Other runtimes (OpenCode, OpenHands, Ollama).** Deferred to later phases by the
  spec's scope table, under its rule that anything not needed for the demo waits. The
  ports are what keep them possible.
- **Refuse to run when `ANTHROPIC_API_KEY` is set**, and tell the user to unset it. More
  explicit, but it blocks users who have the key set for other tools (gap G20).
- **Ask for JSON in the prompt and parse the text**, stripping one optional code fence.
  It works on any Claude Code version, but it fails more often and spends the single
  retry on format mistakes (gap G19).
- **The adapter takes the Pydantic model and retries itself.** Less code in the app, but
  the retry rule is then repeated in every future provider (gap G18).

## Consequences
Easier:
- One runtime, used with the subscription login; no API key is required.
- Both kinds of call sit behind a port, so the runtime can be swapped later.
- Tokens, cost and latency come from the same JSON output for every call.

Harder:
- Cost is notional. It is the API-rate equivalent that Claude Code reports, and
  `max_cost_usd` limits apply to that figure.
- Eval runs use the same subscription as development, so they are run deliberately
  rather than on every change.
- The adapter depends on the Claude Code CLI: `--json-schema` is present in the
  installed version 2.1.286, and the envelope's field names are pinned by a captured
  fixture rather than by the spec.
- No test in the default run starts `claude`. Adapter tests use a stand-in executable
  and a captured reply.
- Claude Code's own permission settings are only defence in depth. The path check after
  the run is the real enforcement
  ([ADR-008](ADR-008-code-and-the-orchestrator-own-safety.md)).

## Amendment
2026-10-11 (drafted with spec v1.10; the human accepts it with ADR-012): the single retry
is for a rejected reply only, whether Pydantic or the plan checks rejected it, so one
`plan` makes at most two planner calls. A failed process (a non-zero exit, an envelope
that cannot be parsed, or a timeout) is not retried: the run is recorded with
`exit: error` or `timeout` and the command exits 1 (SC-27).
