---
description: Run the autonomous self-healing code loop. systematic-debugging on every fix, infrastructure self-heal blocked.
argument-hint: "[--interactive | --autonomous] [company-list]"
---

Run the `self-heal` skill at `~/code/upstream_skills/skills/self-heal/SKILL.md` (symlinked into `~/.claude/skills/self-heal/`).

# Step 1 — Parse `$ARGUMENTS`

Tokenize `$ARGUMENTS` on whitespace. Then:

- If the first token is `--autonomous`, set `MODE=autonomous` and consume the token.
- Else if the first token is `--interactive`, set `MODE=interactive` and consume the token.
- Otherwise, default `MODE=interactive`.

Remaining tokens form the `COMPANIES` list (may be empty — empty means "resume any companies with unfinished `reports/<slug>/`").

# Step 2 — Pre-flight

Before invoking the skill:

```bash
SELF_HEAL_DIR="$HOME/code/upstream_skills/skills/self-heal"
POLICY="$SELF_HEAL_DIR/scripts/policy.py"
REPO_ROOT="$(git rev-parse --show-toplevel)"

python3 "$POLICY" validate-config --repo-root "$REPO_ROOT"
PIPELINE_ENTRY="$(python3 "$POLICY" config-value pipeline.entry --repo-root "$REPO_ROOT")"
STATE_DIR="$(python3 "$POLICY" config-value paths.state_dir --repo-root "$REPO_ROOT")"
HEARTBEAT_INTERVAL="$(python3 "$POLICY" config-value heartbeat.interval_seconds --repo-root "$REPO_ROOT")"
PIPELINE_COUNT="$(pgrep -fc "$PIPELINE_ENTRY" || true)"
test "$PIPELINE_COUNT" = "0"
```

1. **Policy validation.** `policy.py validate-config` verifies cwd is dd-bigbio OR a `.self-heal.toml` exists at the repo root. If neither exists it refuses with: "self-heal requires either the dd-bigbio repo or a .self-heal.toml config."
2. **Check no pipeline is mid-run.** `pgrep -fc "$PIPELINE_ENTRY"` must be 0.
3. **Run a one-shot invariant assertion** (correctness + liveness only — hygiene is the loop's job). If any fails on entry, surface it and abort. Do not enter the loop on a corrupted state.

# Step 3 — Start the heartbeat daemon

```bash
python3 "$SELF_HEAL_DIR/scripts/heartbeat_writer.py" \
  --state-dir "$STATE_DIR" --interval "$HEARTBEAT_INTERVAL" &
HEARTBEAT_PID=$!

cleanup_self_heal_heartbeat() {
  kill "$HEARTBEAT_PID" 2>/dev/null || true
  wait "$HEARTBEAT_PID" 2>/dev/null || true
}

trap cleanup_self_heal_heartbeat EXIT
trap 'cleanup_self_heal_heartbeat; exit 130' INT
trap 'cleanup_self_heal_heartbeat; exit 143' TERM
```

The trap is mandatory. The heartbeat process must stop when the loop exits, is interrupted, or hard-halts.

# Step 4 — Invoke the skill

Invoke the `self-heal` skill via the Skill tool with the parsed arguments in the prompt:

```
Skill("self-heal", "MODE=<MODE> COMPANIES=<comma-separated-list>")
```

The skill body reads MODE and COMPANIES from the invocation prompt and runs the five-step loop accordingly.

# Step 5 — The discipline (reminder)

Rule zero of the skill: **every bug fix runs `superpowers:systematic-debugging` end-to-end (all four phases).** No exceptions. The enforcement chain is three layers (SessionStart hook + dispatch prompt + commit-trailer audit) — see the SKILL.md's Enforcement chain section.

Hard-blocked paths cannot be auto-healed regardless of risk class: `audit_gate`, the skill itself, `scripts/bug_signature.py`, `scripts/heartbeat_writer.py`, anything in `.self-heal/`. Check them with:

```bash
git diff --name-only main...HEAD \
  | python3 "$POLICY" blocked-paths --repo-root "$REPO_ROOT" --stdin
```

Any output escalates to the user.

After tests pass AND Phase 4 completes AND the original failing signal has cleared, the loop auto-merges `safe`-tier (R<=2) PRs in `--interactive` mode; in `--autonomous` mode the same gates apply and non-critical escalations are parked instead of halting.

# Commit trailer (mandatory, written by the orchestrator)

```text
Heal-Model: claude-<model-id>
Heal-Risk: R=<n> (<class>)
Heal-Bug: <sha1-from-bug_signature.py>
Heal-SystematicDebugging-Phase: 4
Heal-Signal-Cleared: yes
```

`Auto` model routing is banned.

# Now begin

Parse `$ARGUMENTS`, run pre-flight, start the heartbeat daemon, then invoke the skill.
