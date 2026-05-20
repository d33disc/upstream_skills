---
description: Run the autonomous self-healing code loop. Smart Orchestrator + cheap workers; superpowers:systematic-debugging on every fix.
argument-hint: "[--interactive | --autonomous] [company-list]"
---

Invoke the `self-heal` skill via the Skill tool and follow it exactly.

The skill lives at `~/code/upstream_skills/skills/self-heal/SKILL.md` (symlinked into `~/.claude/skills/self-heal/SKILL.md`). It defines the operational protocol — invariants, risk score, subagent policy, commit attribution.

# Arguments

`$ARGUMENTS` may contain a mode flag and an optional company list:

- `--interactive` (default) — auto-heal `safe`-tier (R<=2) fixes only when tests + lint + signal-cleared + systematic-debugging Phase 4 all pass. Open PRs for `review`-tier (3<=R<6). Escalate `hard`-tier (R>=6) to the user immediately with `advisor()` consult first.
- `--autonomous` — overnight mode. Auto-merge safes under the same gates. Park (don't halt) on MEMORY.md ceiling, individual-company hard fixes, and non-critical hygiene escalations. Correctness and liveness invariants still hard-halt.

Anything not matching `--interactive|--autonomous` is treated as the company list (slugs or names).

# Before starting

1. **Verify cwd is dd-bigbio or a configured equivalent.** If not, the skill's invariants (verified.json, audit_gate, --skip-to-step) won't apply. Refuse and ask the user to specify the truth-vector artifact, pipeline entry point, and audit gate for the current repo.
2. **Check pipeline isn't already mid-run.** `pgrep -fc "src.dd_pipeline"` must be 0 or only background-safe workers.
3. **Assert invariants once before entering the loop.** If any correctness/liveness invariant fails on entry, surface it and stop — do not enter the loop on a corrupted state.

# The discipline

Rule zero of the skill: **every fix runs `superpowers:systematic-debugging` end-to-end, all four phases.** No exceptions, no shortcuts, regardless of risk class. That is the consistency mechanism — fixes look identical every time because the same skill produced them. Phase 4 completion is required for auto-merge; if a subagent exits before Phase 4, the PR is demoted to review-tier.

After tests pass and Phase 4 completes, the loop ALSO verifies the original failing signal (ERROR line, audit_gate exit code, adversarial finding) is actually gone. "Tests pass" is necessary but not sufficient.

# Commit attribution (mandatory)

Every heal commit carries:

```text
Heal-Model: claude-<model-id>
Heal-Risk: R=<n> (<class>)
Heal-Bug: <sha1-signature>
Heal-SystematicDebugging-Phase: 4
Heal-Signal-Cleared: yes
```

`Auto` routing is banned — every dispatch names the model so `git log --grep='Heal-Model:'` gives a clean audit trail months later.

# Now begin

Read the SKILL.md if it isn't already loaded, set up the heartbeat at `reports/_runs/heartbeat.json`, parse `$ARGUMENTS`, and enter the loop.
