# Project priorities

What to weigh when a decision is open. Read by the advisor subagent. The spec and accepted
ADRs still win over anything here.

1. **Phase 1 scope discipline.** Phase 1 is the 9-step demo in
   [the spec](../spec/phase1-spec.md) and nothing else. Anything the demo does not need
   waits, and goes in progress.md under "Later".
2. **Deterministic checks over model judgement.** Where a rule, a test or a type check
   can decide, it decides. A model is used only where nothing deterministic can do the job.
3. **The human owns specs, ADR acceptance, budgets and safety.** These are never decided
   by an agent. An agent proposes; the human decides.
4. **Proportionality.** No hardening against exotic inputs nobody will produce, unless the
   spec asks for it.
5. **Claude Pro subscription, no API key.** All model calls go through Claude Code on the
   subscription login. Usage is limited, so prefer designs that make fewer model calls.
6. **The smallest design that satisfies the spec.** Between two options that both meet the
   spec, take the one with less code, fewer moving parts and fewer new concepts.
