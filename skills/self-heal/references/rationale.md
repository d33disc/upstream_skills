# Self-Heal Rationale

Read this only when changing the self-heal protocol. Normal loop execution should rely on `SKILL.md` and the executable scripts.

## Design Rationale

The loop exists to repair long-running pipeline failures without lowering truth or publication invariants. The main session keeps orchestration state and delegates noisy exploration or repair work to isolated workers. Every fix follows systematic debugging because a repeated protocol is easier to audit than improvised repair.

The executable pieces are intentionally small:

- `scripts/bug_signature.py` protects the per-bug attempt budget from cosmetic drift.
- `scripts/heartbeat_writer.py` supplies liveness evidence while the main session is request/response.
- `scripts/policy.py` keeps config validation, hard-blocked path checks, and risk scoring out of prose.

## Original Design Memory

The v1 design rationale, decision changelog, and future MODE=team / MODE=cloud expansion stubs were first recorded at:

`~/.claude/projects/-Users-davis-code-dd-bigbio/memory/project_self_healing_loop_prompt.md`

That memory is background only. The active behavioral spec is `SKILL.md` plus scripts.

## Version History

**v1.4 (2026-05-20):**

1. Added `scripts/policy.py` for config validation, hard-blocked path checks, config value lookup, and risk scoring.
2. Added focused tests for policy, heartbeat writing, and broader bug-signature volatility.
3. Updated `/self-heal` command guidance to validate policy before entry, derive configured paths, and trap heartbeat cleanup.
4. Split dd-bigbio defaults and protocol rationale into one-level references to keep `SKILL.md` execution-focused.

**v1.3 (2026-05-20, hindsight pass 2):**

1. Trimmed YAML description from about 14 to about 7 lines.
2. Diagram changed to five steps with Step 0 as ASSERT INVARIANTS and Step 1 as PIPELINE RUN.
3. Added Enforcement chain to replace fake `require_skills=[...]` with SessionStart hook, dispatch prompt, and commit-trailer audit.
4. Added Hard-blocked paths so the loop cannot heal its own infrastructure.
5. Added State persistence with file, writer, reader, and lifetime.
6. Added `scripts/bug_signature.py` and `scripts/heartbeat_writer.py`.
7. Added explicit interactive/autonomous mode.
8. Added `.self-heal.toml` configuration.
9. Rescoped `advisor()` to once per session plus once before hard halt.
10. Changed `UNCOVERED_LOC_RATIO` fallback from 1.0 to 0.5.
11. Added pre-commit hook timeout as non-auto-healable `hook_timeout`.

**v1.2:** added the canonical N-step diagram and named Step 3 as the load-bearing step.

**v1.1:** added rule zero, post-fix signal verification, canonical bug signature, Opus-failure-terminal, prompt hot paths, MEMORY.md mode policy, enriched commit trailers, and slash flags.

**v1:** original protocol memory. Behavioral spec superseded by v1.1 and later.
