---
name: self-heal
description: |
  Autonomous self-healing code loop for long-running pipelines. Use when the user says
  "self-heal this code", "/self-heal", "autonomous fix loop", "fix and retry", or when a
  pipeline emits ERROR/Traceback/non-empty steps[].errors/halt.reason and the user wants
  unattended remediation. Smart Orchestrator (main Opus) dispatches Haiku/Sonnet/Opus
  workers in worktree isolation; every fix runs superpowers:systematic-debugging end-to-end
  (Phases 1-4); the loop never lowers an invariant to make progress. Tuned for dd-bigbio
  (verified.json + audit_gate); generalized via .self-heal.toml.
metadata:
  type: workflow
  trigger: explicit-or-pipeline-failure
  version: "1.4"
  related:
    - superpowers:systematic-debugging
    - superpowers:test-driven-development
    - superpowers:verification-before-completion
    - superpowers:using-git-worktrees
---

# Self-Heal — autonomous code-healing loop

This file is the execution contract. Load references only when needed:

- `references/rationale.md`: design rationale, version history, and deferred mode notes. Read before changing the protocol itself.
- `references/dd-bigbio-defaults.md`: dd-bigbio defaults and portability boundaries. Read when adapting this skill to another repo or changing `.self-heal.toml` semantics.

The runtime policy that must stay executable lives in `scripts/policy.py`.

## The five-step canonical loop

```text
   +-----------+   +-----------+   +-----------+   +-----------+   +-----------+
   | 0. ASSERT |   | 1.PIPELINE|   | 2. DETECT |   | 3. HEAL   |   | 4. RESUME |
   |INVARIANTS |-->|   RUN     |-->|   BUG     |-->|   BUG     |-->| PIPELINE  |
   +-----------+   +-----------+   +-----------+   +-----------+   +-----------+
   halt loop OR    system being   Haiku Explore   Sonnet/Opus     resume from
   auto-heal       observed --    subagents grep  subagent runs   last-known-
   hygiene #2/#3   not the loop's signals since   ALL 4 phases    good schema-
   per mode        action; emits  last_ts from    of systematic-  valid step
   policy          logs+summary   log+summary+    debugging       via --skip-
                   +gate+findings gate+findings   (Repro->Verify) to-step N+1
        ^                                                              |
        +---- after run completes: re-assert, record, loop to step 0 --+
```

**Step 3 is the load-bearing step.** Every bug fix — regardless of risk class, regardless of how trivial — invokes `superpowers:systematic-debugging` and runs it end-to-end through all four phases (Reproduce, Localize, Fix, Verify). No exceptions. This is the protocol for every bug repair, and it is what makes fixes look identical across runs: the same skill produced them.

**Step 1 is NOT the loop's first action.** Step 1 is the pipeline running — the system being observed. The loop's own first action is step 0 (asserting invariants). A pipeline can be mid-run while the loop is between iterations; the loop never interrupts a running pipeline (see Conflict avoidance).

## Rule zero — every fix runs systematic-debugging, end-to-end

The four phases of systematic-debugging are non-negotiable on every fix:

1. **Reproduce** — get the failing signal reliably observable
2. **Localize** — root-cause; trace from symptom to source
3. **Fix** — minimum code that stops Phase 1 reproducing
4. **Verify** — re-run the original failing signal AND the test suite; both must pass

The subagent records its highest completed phase in the `Heal-SystematicDebugging-Phase:` commit trailer. If it exits before Phase 4, the PR is demoted to review-tier even if R<=2.

## Enforcement chain — how the rule survives adversarial subagents

`require_skills=[...]` in the loop pseudocode is shorthand. There is no Agent-tool parameter that forces a subagent to invoke a skill. Enforcement is a three-layer chain:

1. **SessionStart hook (default).** Subagents inherit `using-superpowers` via the SessionStart hook in `~/.claude/settings.json`. That skill mandates "if a skill might apply, invoke it before any substantive work." Since `superpowers:systematic-debugging` matches "any bug, test failure, or unexpected behavior," the subagent's own discipline forces it to invoke before writing code.
2. **Dispatch prompt (belt and suspenders).** The orchestrator's dispatch text says verbatim: *"Before writing any fix code, invoke the `superpowers:systematic-debugging` skill via the Skill tool and follow all four phases. Record the highest phase completed in your final report so the orchestrator can write the Heal-SystematicDebugging-Phase trailer."*
3. **Commit-trailer audit (terminal gate).** At merge time the orchestrator runs:


   ```bash
   git log -1 --format='%(trailers:key=Heal-SystematicDebugging-Phase,valueonly)' <pr-head>

   ```

   If the trailer is missing or its value is `< 4`, the PR is demoted to review-tier regardless of risk class. A subagent that bypassed layers 1 and 2 cannot bypass this one.

Layers 1+2 are best-effort instruction; layer 3 is the verifiable gate. Together they make rule zero survive subagents that ignore prompts.

## Hard-blocked paths — the loop cannot heal its own infrastructure

A bug in `audit_gate` cannot be "fixed" by an `audit_gate` invocation that itself trusts the broken gate. Same for the bug-signature function, the heartbeat writer, the risk-score implementation, the skill itself. The following paths are **escalate-only** — the loop refuses to auto-heal them regardless of risk score:

- `src/dd_audit_gate.py` and any module it imports transitively
- `src/dd_schemas.py` (schema migrations redefine the truth vector)
- Anything under `~/code/upstream_skills/skills/self-heal/` (the skill itself)
- Anything under `scripts/` in this skill dir (`bug_signature.py`, `heartbeat_writer.py`)
- Anything matching `.self-heal/` in the host repo (loop's config / state)
- Plus any glob listed under `[hard_blocked_paths] extra_globs` in `.self-heal.toml`

**Detection.** Before merging any heal PR the orchestrator runs `git diff --name-only main...<pr-head>` and matches every changed path against the block list. Any match -> escalate to user with the matching path as the reason. No auto-merge, no review-tier downgrade — escalate.

Executable check:

```bash
git diff --name-only main...<pr-head> \
  | python3 ~/code/upstream_skills/skills/self-heal/scripts/policy.py \
      blocked-paths --repo-root <repo-root> --stdin
```

## The load-bearing pattern: Smart Orchestrator + cheap workers

```text
                    +------------------------+
                    |     MAIN SESSION       |
                    |   (Opus, the user)     |
                    |  - holds the plan      |
                    |  - reviews diffs       |
                    |  - decides merges      |
                    |  - never edits bulk    |
                    +-----------+------------+
                                |
              dispatches in parallel, isolated
                                |
        +-----------------------+-----------------------+
        v                       v                       v
+----------------+    +-------------------+    +----------------+
|  HAIKU agents  |    |   SONNET agents   |    |   OPUS agent   |
|   (Explore)    |    | (general-purpose) |    |(general-purpose|
| grep, log scan |    | execute plan      |    |  rare, hard)   |
| read-only      |    | superpowers gates |    | cross-file,    |
+----------------+    +-------------------+    +----------------+
```

Orchestrator thinks; workers type. Under Max 20x the cheapness of workers is **context discipline first, cost second** — every minute Opus spends grepping a logfile is a minute its working memory is full of grep output instead of the plan.

## Invariants — assert every iteration

Each invariant is an *executable check*. If any fails the loop halts; it never lowers a threshold to make progress.

**Correctness (truth vectors — always halt, never auto-heal):**

1. `verified.json` (or `.self-heal.toml [truth_vector] artifact`) exists and validates against its schema BEFORE `report.md` is written
2. Every digit in `report.md` traces to a `claim_id` in `verified.json` with `url + verbatim + retrieved` (via audit_gate)
3. `git status` clean OR uncommitted changes only on `fix/*` or `wip/*` branches, never main

**Liveness:**

1. `pipeline.log` heartbeats at least every 90s during any step >120s wall-clock
2. `<state_dir>/heartbeat.json` (written by `scripts/heartbeat_writer.py`) is updated every 15s; external monitors trip on `now - ts > 45s`

**Hygiene (auto-heal #2 and #3; #1 escalation policy depends on mode):**

1. `wc -l < <MEMORY.md>` returns `<= 200` for BOTH `~/.claude/projects/-Users-davis/memory/MEMORY.md` (global) AND `~/.claude/projects/-Users-davis-code-dd-bigbio/memory/MEMORY.md` (project)
2. `grep -REn 'httpx\.Client\(\)|requests\.get\(' src/ | grep -v 'timeout='` returns zero matches
3. `find src -name '*.py' -exec wc -l {} \; | awk '$1>200'` files all carry `# TODO(<ISO>): refactor`

**MEMORY.md ceiling policy by mode:**

- `--interactive` (default): HALT and ask user.
- `--autonomous`: SOFT escalation. Park decision in `<state_dir>/MEMORY_PRUNE_QUEUED.md`, continue. The 200-line ceiling is an index auto-load limit only — entries past line 200 stay readable by full path.

## What counts as a bug (signal whitelist)

Anything not on this list is logged to `<state_dir>/SELF_HEAL_LOG_<ISO-date>.md` but does NOT trigger a heal cycle.

- `pipeline.log` line matching `^(ERROR|CRITICAL|Traceback)` not seen prior iteration
- `run_summary.json` `steps[].errors` array length > 0
- `run_summary.json` `halt.reason` non-null
- `adversarial_findings.json` entry `severity >= high` referencing a `claim_id` in `verified.json`
- `audit_gate` exit code > 0
- `ruff` / `mypy` / `pytest` failure on any tracked file

## Bug signature

Canonical implementation: `scripts/bug_signature.py` in this skill dir.

```python
from scripts.bug_signature import compute_signature
sig = compute_signature(
    step=bug["step"],
    signal_type=bug["signal_type"],
    raw_pattern=bug["raw_pattern"],
    claim_id=bug.get("claim_id"),
)
```

Or as a CLI:

```bash
echo '{"step":3,"signal_type":"python_traceback",
       "raw_pattern":"...","claim_id":null}' \
  | python3 scripts/bug_signature.py
```

The script strips ephemerals (timestamps, `/tmp/*` paths, line numbers, PIDs, memory addresses, UUIDs, hex IDs) before SHA1-ing the JSON of `{step, signal_type, normalized_pattern, claim_id}`. Same logical bug → same signature → 3-attempt budget cannot be reset by cosmetic drift across retries.

Regression tests live in `test_bug_signature.py`. Add a test before changing normalization rules.

## State persistence — files, writers, readers

| State | Path (under `<state_dir>`) | Writer | Reader | Lifetime |
|---|---|---|---|---|
| `last_ts` (detect cursor) | `detect_cursor.json` | Orchestrator (end of DETECT) | Orchestrator (next DETECT) | Across sessions |
| Heal attempts (per-signature counter) | `heal_attempts.json` | Orchestrator (end of HEAL) | Orchestrator (risk classifier) | Across sessions |
| Heartbeat | `heartbeat.json` | `scripts/heartbeat_writer.py` daemon | External monitors | While daemon runs |
| Loop state (heartbeat source) | `loop_state.json` | Orchestrator (on every state change) | `heartbeat_writer.py` | While daemon runs |
| Parked items | `../<slug>/PARKED.md` | Orchestrator (soft escalation) | User (next session) | Persistent |
| Halt reports | `HALT_<ISO>.md` | Orchestrator (hard halt) | User (next session) | Persistent |
| Heal log debrief | `SELF_HEAL_LOG_<ISO-date>.md` | Orchestrator (on exit) | User | Persistent |

`<state_dir>` defaults to `reports/_runs/` (dd-bigbio); override via `.self-heal.toml [paths] state_dir`.

## The loop

```python
while companies_remaining:
    # 0. PROTECT
    assert_invariants()                 # halt on correctness/liveness; auto-heal hygiene per mode

    # 2. DETECT (between iterations only; step 1 = the running pipeline)
    last_ts = read_json("<state_dir>/detect_cursor.json").get("last_ts")
    bugs = []
    for src in ["pipeline.log", "run_summary.json",
                "adversarial_findings.json", "audit_gate stdout"]:
        bugs += dispatch_subagent(
            subagent_type="Explore", model="haiku",
            task=f"scan {src} for new bug signals since {last_ts}",
        )
    write_json("<state_dir>/detect_cursor.json", {"last_ts": now_iso()})

    # 3. HEAL (parallel, isolated; systematic-debugging enforced via three-layer chain)
    if bugs:
        plan = author_fix_plan(bugs)    # specs + todos + acceptance tests, IN MAIN SESSION
        for bug in bugs:
            sig = compute_signature(**bug)              # scripts/bug_signature.py
            if attempts_for(sig) >= 3:
                escalate_to_user(bug, reason="3-attempt budget exhausted")
                continue
            R = classify_fix_risk(bug)
            if R >= 6:
                escalate_to_user(bug)                   # no advisor consult per bug; see advisor scope
                continue
            if touches_hard_blocked_paths(plan.diff_for(bug)):
                escalate_to_user(bug, reason="changes hard-blocked infrastructure path")
                continue
            dispatch_subagent(
                subagent_type="general-purpose",
                model="sonnet",                         # bump to opus only on Sonnet "stuck after 3"
                task=plan.for_bug(bug),                 # prompt includes the dispatch text
                                                        # from "Enforcement chain" section
                isolation="worktree",
                pr_required=True,
            )
        wait_for_all_subagents()

        # 3a. POST-FIX SIGNAL VERIFICATION + TRAILER AUDIT
        for pr in clean_PRs():
            phase = read_trailer(pr.head, "Heal-SystematicDebugging-Phase")
            if not original_signal_cleared(pr.heal_bug_signature) or int(phase) < 4:
                pr.demote_to_review_tier()
                continue
            if touches_hard_blocked_paths(pr.diff()):
                pr.escalate(); continue
            pr.auto_merge()                              # R<=2 AND signal cleared AND Phase 4

    # 1+4. RUN — resume from last known good, never from Step 0
    company = next_company_or_resume()
    checkpoint = last_known_good_step(company)
    dispatch_pipeline(company, stage=infer_stage(company),
                      skip_to_step=checkpoint + 1 if checkpoint else 0)

    # 5. RE-ASSERT before RECORD — never persist state we cannot verify
    assert_invariants()                                  # tag invariant-fail-<ISO> on regression

    # 6. RECORD (only if re-assert passed)
    update_memory_if_novel(bug_pattern)
    update_PROJECT_STATE_tracker()
```

## Fix risk classification — the greybeard score

```text
R = 3*HOT_PATH
  + 3*SCHEMA_MIGRATION
  + 2*SIGNATURE_CHANGE
  + 2*UNCOVERED_LOC_RATIO    # fraction of changed lines with zero test cov; fallback 0.5 if no coverage data
  + 1*log10(BLAST_RADIUS)    # callers/importers, capped at +2
  + 1*log10(LINES_CHANGED)   # capped at +3
  + 1*RECENT_CHURN_BUCKET    # 0 if <3 commits/30d, 1 if 3-10, 2 if >10
  - 2*FAILING_TEST_EXISTS    # subagent built a reproduction test
  - 1*PURE_FUNCTION          # no I/O, no global state
  - 1*REVERSIBLE             # one-commit revert undoes cleanly
```

| Score | Class | Action |
|---|---|---|
| R <= 2 | `safe` | Auto-heal, auto-merge IF tests + lint pass AND signal cleared AND Phase 4 reached AND no hard-blocked-path match |
| 3 <= R < 6 | `review` | Auto-heal in worktree, open PR, do NOT merge |
| R >= 6 | `hard` | Escalate to user with score breakdown |

**`HOT_PATH = 1`** if any of: file in `src/dd_pipeline.py`, `src/dd_schemas.py`, `src/dd_audit_gate.py`; defines `^def main` or `orchestrator|_run_step|main_loop`; path matches `prompts/*.tpl.md`; or path matches `[hot_paths] extra_globs` in `.self-heal.toml`.

**`UNCOVERED_LOC_RATIO` fallback is 0.5 (not 1.0)** when no coverage data exists — bootstrapping a project without coverage shouldn't make every fix maximum-risk.

Executable implementation:

```bash
echo '{"hot_path":true,"lines_changed":40,"failing_test_exists":true}' \
  | python3 ~/code/upstream_skills/skills/self-heal/scripts/policy.py risk-score
```

## Subagent model + type policy

| Work | subagent_type | model |
|---|---|---|
| Grep / log scan / file location | `Explore` | haiku |
| Cross-codebase research | `Explore` | haiku |
| Easy/medium fix WITH plan | `general-purpose` | sonnet |
| Risk class `review` (3 <= R < 6) | `general-purpose` | sonnet |
| Hard fix: cross-file edits, schema migration | `general-purpose` | opus |
| Hard fix: architecture refactor | `general-purpose` | opus |
| Subagent stuck after 3 sonnet attempts | `general-purpose` | opus (one-shot) |
| Opus subagent fails on first attempt | escalate to user | — |
| Adversarial review (Step 6) | `adversarial-reviewer` | (its def) |

Rules: main session orchestrates on Opus; tightly-coupled tasks stay in-thread; haiku never invokes superpowers skills; `Auto` routing is banned (kills attribution).

## advisor() consultation — scope and budget

advisor forwards the full conversation history every call. Across an overnight autonomous run, history grows to many MB and a single advisor call can cost more than the Opus dispatch it was meant to gate. The earlier v1.1/v1.2 rule "consult advisor before every Opus dispatch" inverted the economics.

**Revised policy:**

- **Once per loop session, at startup.** Validate the company list, the initial risk inventory, and the chosen mode. Output captured in `<state_dir>/loop_plan.json`.
- **Once before any hard halt.** Correctness invariant fails -> consult advisor before declaring halt. The asymmetry (publishing a fabricated digit vs. one advisor call) makes this worth the cost.
- **No per-bug advisor calls during the loop.** The per-bug guardrails — risk score, 3-attempt budget, systematic-debugging discipline, signal-cleared gate, commit-trailer audit, hard-blocked-paths check — are sufficient without advisor layered on top.

## Pre-commit hook policy

The user's global CLAUDE.md forbids `--no-verify`. The self-heal loop honors this absolutely:

- Pre-commit failure on a heal commit = a normal bug signal; re-enter the loop with it
- A pre-commit hook that itself crashes = HYGIENE invariant violation; halt and ask
- Hooks taking >120s wall-clock = liveness invariant risk; treat as a bug signal of type `hook_timeout` and escalate (don't auto-heal hooks)
- NEVER pass `--no-verify`, `--no-gpg-sign`, or `-c commit.gpgsign=false`

## Model attribution — every commit

Auto-generated PR description + commit trailer template:

```text
Heal-Model: claude-sonnet-4-6
Heal-Risk: R=2 (safe)
Heal-Bug: <sha1-from-bug_signature.py>
Heal-SystematicDebugging-Phase: 4
Heal-Signal-Cleared: yes
```

`git log --grep='Heal-Model:'` then yields a full audit trail. `Auto` model routing is banned.

## Budget

- Max **3 heal cycles per bug signature, total** (counter in `<state_dir>/heal_attempts.json`). After 3, halt and ask.
- Max **5 concurrent subagents**. GNU `parallel -j min(cores, free_mem / 2_GB)`.
- Do NOT load `report.md` files >5 MB into main context — delegate to subagent, consume only summary.

## User unavailability — park vs. hard halt

- **Soft escalation** (one company's hard fix, MEMORY.md prune in `--autonomous`, non-critical question): write `reports/<slug>/PARKED.md`, CONTINUE with other companies.
- **Hard halt** (correctness invariant failed, truth vector at risk, schema drift): SIGTERM all pipelines, write `<state_dir>/HALT_<ISO>.md`, STOP.

When in doubt, hard halt.

## Conflict avoidance

Before any code change check `pgrep -fc "src.dd_pipeline"` (or `.self-heal.toml [pipeline] entry`). If pipelines are mid-run, only edit files the pipeline does NOT import at runtime (tests, prompts, docs, memory). Defer hot-path edits to between-company gaps.

## Termination

Loop exits cleanly when ANY of:

- All requested companies have `report.md` + `web.json` + `internal_summary.md`
- User types `halt self-healing` / `stop`
- An invariant fails twice in a row
- All remaining companies parked AND no live pipelines (clean drain)

On exit write `<state_dir>/SELF_HEAL_LOG_<ISO-date>.md` with companies completed, bugs detected+fixed (commit refs), bugs detected+escalated (open issues), memory entries added/updated, invariant violation history.

## Mode parameter

The skill accepts a mode argument when invoked. The slash command parses it from `$ARGUMENTS` and forwards it; direct Skill-tool invocation should pass `MODE=interactive` or `MODE=autonomous` in the invocation prompt.

- `MODE=interactive` (default) — auto-merge only `safe`-tier (R<=2) with all gates green; open PRs for `review`-tier; escalate `hard`-tier immediately
- `MODE=autonomous` — same merge gates, but park (don't halt) on non-critical escalations: MEMORY.md ceiling, individual hard fixes, hygiene #1 ambiguity. Correctness and liveness invariants still hard-halt regardless of mode.

If mode is missing from invocation, default to `interactive`. The mode is recorded in `<state_dir>/loop_plan.json` at session start.

## Configuration via `.self-heal.toml`

Place at the host repo root. Every field below is optional; provided fields override the dd-bigbio defaults. Without this file, `policy.py validate-config` permits only a dd-bigbio-shaped repo. For portability details, read `references/dd-bigbio-defaults.md`.

```toml
[paths]
state_dir = "reports/_runs"               # heartbeat, heal_attempts, parked, halt
report_log_prefix = "SELF_HEAL_LOG"

[truth_vector]
artifact = "verified.json"                # the file whose schema validity gates downstream
schema_module = "src/dd_schemas.py"

[pipeline]
entry = "src/dd_pipeline.py"
resume_flag = "--skip-to-step"
audit_gate = "src/dd_audit_gate.py"

[heartbeat]
interval_seconds = 15
alert_threshold_seconds = 45

[budget]
max_attempts_per_bug = 3
max_concurrent_subagents = 5

[hot_paths]
extra_globs = ["prompts/*.tpl.md"]

[hard_blocked_paths]
extra_globs = []                          # added to the built-in escalate-only list
```

Reusing the skill in a different repo means writing this file, not forking.

Validate before entering the loop:

```bash
python3 ~/code/upstream_skills/skills/self-heal/scripts/policy.py \
  validate-config --repo-root <repo-root>
```

## Invocation

- Sentinel phrase: `self-heal this code [optional: company list]`
- Slash command: `/self-heal [--interactive | --autonomous] [company list]` — see `~/code/upstream_skills/commands/self-heal.md`
- Auto-trigger: a watching session detecting a whitelist signal in `pipeline.log` and offering to enter the loop

Before any unattended overnight run, verify schema coverage is broad enough that checkpoint condition #2 (schema-valid artifact at every step boundary) is meaningful. Reference: `~/code/dd-bigbio/docs/superpowers/plans/2026-05-20-json-schema-harmonization.md`.

## Change rationale

Version history and protocol rationale live in `references/rationale.md`. Do not load that file during normal loop execution.
