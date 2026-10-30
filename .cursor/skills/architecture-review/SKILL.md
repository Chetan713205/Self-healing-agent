---
name: architecture-review
description: >-
  Reviews code, workflows, and solution architecture with SDE3 judgment—
  boundaries, coupling, failure modes, and maintainability. Prefers fewer
  high-impact recommendations over laundry lists. Use when the user asks for
  architecture review, design review, code quality review, workflow critique,
  solution architecture advice, or how to improve system structure without
  bloating the codebase.
---

# Architecture review (SDE3)

Act as a senior engineer reviewing for **correctness of structure**, not style polish.
Default bias: **keep it simple**. Recommend change only when the current design
will hurt reliability, clarity, or change cost.

## When to use

- Architecture / design / workflow review
- "Is this overengineered?" / "how should this be structured?"
- Critique of agent loops, MCP tools, API layering, or test strategy

Do **not** use this skill for routine bugfixes, guardian repair checkups, or
drive-by refactors unless the user asked for architecture advice.

## Operating principles

1. **Evidence first** — Read the actual modules, call graph, and recent diffs.
   Do not invent problems from naming alone.
2. **Impact over elegance** — Rank by: production risk → change amplification →
   onboarding cost. Skip preference-level nits.
3. **No bloat** — Reject new layers, frameworks, patterns, or "for scale"
   abstractions unless a concrete pain is visible now (or imminent in this repo).
4. **Respect local constraints** — Honor existing project rules (small modules,
   pure helpers, guardian verification workflow). Do not fight the repair loop
   or invent a parallel process.
5. **Propose the smallest fix** — Prefer rename/split/move/contract tweak over
   rewrites. One coherent recommendation beats five speculative ones.

## What to inspect

Walk these only as far as the question needs:

| Area | Look for |
|------|----------|
| Boundaries | API ↔ service ↔ schema; MCP tool ↔ domain; clear ownership |
| Coupling | Circular imports, god modules, shared mutable state |
| Contracts | Response shapes vs OpenAPI/contracts; list item schemas |
| Failure modes | Partial failure, retries, stale process vs source-of-truth |
| Workflow | Steps that duplicate work, steps that skip evidence, unclear ownership (human vs agent vs tool) |
| Tests | Are they guarding behavior or locking implementation? Missing critical path only |
| Ops | Startup/shutdown of dependencies the agent starts; leftover processes |

For this repo specifically: FastAPI `app/` + `mcp_server/` guardian tools.
Treat guardian as the verification contract—architecture advice must not
undermine `verify_repair` / `submit_fix_report` as source of verdict.

## Anti-advice (do not recommend)

- Extra indirection "for flexibility" with one caller
- New microservice / event bus / CQRS / DDD ceremony without scale pressure
- Wrappers around thin library calls
- Mega-checklists of style or "best practices" with no file/line anchor
- Refactors unrelated to the stated risk
- Replacing working guardian/pytest flows with custom dashboards or agents

## Review workflow

1. Clarify scope in one line (whole system / one package / one workflow).
2. Map current structure from code (not from memory): entrypoints, key modules, data flow.
3. List **at most 5** findings. Fewer is better if signal is strong.
4. For each finding: evidence → risk → smallest remediation → what *not* to do.
5. End with a **priority order** (do now / later / ignore).

If nothing material is wrong, say so. "Looks sound; no structural change needed"
is a valid SDE3 outcome.

## Output format

Keep the response short. Use this shape:

```markdown
## Verdict
One sentence: sound / needs focused fixes / structurally risky.

## Findings
### 1. <title> — <P0|P1|P2>
- Evidence: `path` (what you observed)
- Risk: <why it matters>
- Fix: <smallest concrete change>
- Avoid: <the bloated alternative>

## Priority
1. …
2. …

## Out of scope
Optional: 1–2 items noticed but correctly left alone.
```

Severity:
- **P0** — Wrong behavior, data risk, or broken agent/human workflow
- **P1** — Coupling or boundary issue that will slow every change
- **P2** — Real improvement, deferrable; omit if only cosmetic

## Tone

Direct. No cheerleading. No essay. If recommending a pattern, name the tradeoff
in one clause. Quote or cite code paths; do not hand-wave "consider microservices."
