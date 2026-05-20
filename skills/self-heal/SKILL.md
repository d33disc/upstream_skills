---
name: self-heal
description: |
  Autonomous self-healing code loop with Smart Orchestrator (main session, Opus) + cheap workers (Haiku/Sonnet subagents).
  Use when the user says "self-heal this code", "/self-heal", "autonomous fix loop", "fix and retry", "run until green",
  or when a long-running pipeline emits ERROR/Traceback/non-empty steps[].errors/halt.reason and the user wants
  unattended remediation. EVERY fix — regardless of risk class — runs the full `superpowers:systematic-debugging`
  skill end-to-end (all four phases). That is the consistency mechanism: fixes look the same every time because
  the same discipline produced them. The loop also asserts correctness/liveness/hygiene invariants every iteration,
  classifies each proposed fix on a mathematical risk score R (auto-merge if R<=2, PR-only if 3<=R<6, escalate if
  R>=6), dispatches superpowers-gated fix subagents in worktree isolation, verifies the original bug signal cleared
  before marking fixed, resumes the pipeline from last known good schema-valid checkpoint via --skip-to-step, never
  lowers an invariant to make progress, and records every fix with Heal-Model / Heal-Risk / Heal-Bug /
  Heal-SystematicDebugging-Phase commit trailers so auto-routing can never hide attribution. Tuned for the dd-bigbio
  DD pipeline (verified.json + report.md + audit_gate); generalizes to any pipeline that defines schema-valid
  artifacts per step.
metadata:
  type: workflow
  trigger: explicit-or-pipeline-failure
  version: "1.1"
  related:
    - superpowers:systematic-debugging
    - superpowers:test-driven-development
    - superpowers:verification-before-completion
    - superpowers:using-git-worktrees
---

# Self-Heal — autonomous code-healing loop

The full operational protocol (697-line v1 with design rationale, document changelog, and future MODE=team / MODE=cloud expansion stubs) lives at:

`~/.claude/projects/-Users-davis-code-dd-bigbio/memory/project_self_healing_loop_prompt.md`

That memory auto-loads inside dd-bigbio sessions. From any other working directory, read it explicitly via `Read` before starting a long run. **This SKILL.md is v1.1** — a procedurally-sufficient subset of v1 plus the hindsight-refinement deltas listed at the end.

## Rule zero — every fix runs systematic-debugging, end-to-end

This is the load-bearing consistency rule. Every fix the loop dispatches — `safe`, `review`, or `hard`, one-liner typo or schema migration — MUST execute the full `superpowers:systematic-debugging` skill, all four phases:

1. **Reproduce** — get the failing signal reliably observable
2. **Localize** — root-cause it; trace from symptom to source
3. **Fix** — write the minimum code that makes Phase 1 stop reproducing
4. **Verify** — re-run the original failing signal AND the test suite; both must pass

The subagent records the highest phase it completed in the commit trailer (`Heal-SystematicDebugging-Phase: 4`). If it exits before Phase 4, the fix does NOT auto-merge regardless of risk class — it becomes a `review`-tier PR even if R<=2. Phase 4 completion is the audit checkpoint that turns "tests pass" into "bug is gone."

**Why this is rule zero:** "tests pass" is a weak signal — tests can be tautological, mock the wrong layer, or cover the wrong path. The systematic-debugging discipline forces a re-run of the **original** failure signal (ERROR line, audit_gate exit code, adversarial finding) after the fix lands. If that signal is still present, the test passing was a coincidence. This is the difference between a clean codebase and one that drifts toward green-tests-broken-product.

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
        |                       |                       |
        v                       v                       v
+----------------+    +-------------------+    +----------------+
|  HAIKU agents  |    |   SONNET agents   |    |   OPUS agent   |
|   (Explore)    |    | (general-purpose) |    |(general-purpose|
| grep, log scan |    | execute plan      |    |  rare, hard)   |
| read-only      |    | superpowers gates |    | cross-file,    |
|                |    |                   |    | schema, refactor|
+----------------+    +-------------------+    +----------------+
```

Orchestrator thinks; workers type. Under Max 20x the cheapness of workers is **context discipline first, cost second** — every minute Opus 4.7 spends grepping a logfile is a minute its working memory is full of grep output instead of the plan.

## Invariants — assert every iteration

Each invariant is an *executable check*. If any fails the loop halts; it never lowers a threshold to make progress.

**Correctness (truth vectors — never auto-heal, always halt):**

1. `verified.json` exists and validates against `src/dd_schemas.py` BEFORE `report.md` is written for any company in the batch.
2. Every digit in `report.md` traces to a `claim_id` in `verified.json` with `url + verbatim + retrieved` (use existing audit_gate).
3. `git status` clean OR uncommitted changes only on `fix/*` or `wip/*` branches, never main.

**Liveness:**

1. `pipeline.log` heartbeats at least every 90s during any step >120s wall-clock.
2. `reports/_runs/heartbeat.json` updated every 15s with `{ts, iteration, current_company, current_step, last_invariant_check_ts}`. External monitors trip on `now - ts > 45s`.

**Hygiene (auto-heal allowed for #2 and #3; #1 escalation policy depends on mode — see below):**

1. `wc -l < <MEMORY.md>` returns <= 200. Check applies to BOTH the global index (`~/.claude/projects/-Users-davis/memory/MEMORY.md`) AND the project index (`~/.claude/projects/-Users-davis-code-dd-bigbio/memory/MEMORY.md`). Either over the ceiling triggers the policy below.
2. `grep -REn 'httpx\.Client\(\)|requests\.get\(' src/ | grep -v 'timeout='` returns zero matches.
3. `find src -name '*.py' -exec wc -l {} \; | awk '$1>200'` files all carry an inline `# TODO(<ISO>): refactor` marker.

**MEMORY.md ceiling policy by mode:**

- `--interactive` (default): HALT and ask user. Pruning is a judgment call — which findings are still load-bearing? which `[[wiki-link]]`s would break?
- `--autonomous` (overnight / unattended): SOFT escalation. Park the prune decision in `reports/_runs/MEMORY_PRUNE_QUEUED.md`, continue the loop. MEMORY.md hygiene does not corrupt truth, so it does not warrant a hard halt overnight. The 200-line ceiling is only an INDEX auto-load limit — entries past line 200 stay readable by full path, they just lose discoverability for that session.

## What counts as a bug (signal whitelist)

Anything not on this list is logged to `reports/SELF_HEAL_LOG_<ISO-date>.md` but does NOT trigger a heal cycle.

- `pipeline.log` line matching `^(ERROR|CRITICAL|Traceback)` not seen prior iteration
- `run_summary.json` `steps[].errors` array length > 0
- `run_summary.json` `halt.reason` non-null
- `adversarial_findings.json` entry `severity >= high` referencing a `claim_id` in `verified.json`
- `audit_gate` exit code > 0
- `ruff` / `mypy` / `pytest` failure on any tracked file

## Bug signature — canonical definition

The 3-attempts-per-bug budget depends on a stable signature so cosmetic differences (different stack line numbers, different timestamps) can't reset the counter. The signature is the SHA1 of the JSON `{step, signal_type, normalized_pattern, claim_id}` where:

- `step` = pipeline step number that emitted the signal (0..9)
- `signal_type` = one of `python_traceback`, `pipeline_error`, `audit_gate_exit`, `adversarial_finding`, `lint_failure`, `type_failure`, `test_failure`
- `normalized_pattern` = the failing line / exception type / test name with line numbers, file paths under `/tmp/`, timestamps, and PIDs stripped to placeholders
- `claim_id` = the verified.json claim id if the signal cites one, else null

Stored in `reports/_runs/heal_attempts.json` keyed by signature, value = list of `{ts, model, R, outcome, commit_sha}`. Three entries for the same signature -> halt and escalate.

## The loop

```python
while companies_remaining:
    # 1. PROTECT
    assert_invariants()             # halt on correctness/liveness; auto-heal hygiene per mode

    # 2. DETECT (between iterations, never mid-pipeline)
    bugs = []
    for src in ["pipeline.log", "run_summary.json",
                "adversarial_findings.json", "audit_gate stdout"]:
        bugs += dispatch_subagent(
            subagent_type="Explore", model="haiku",
            task=f"scan {src} for new bug signals since {last_ts}",
            return_format="structured_bug_list",
        )

    # 3. HEAL (parallel, isolated, systematic-debugging-gated)
    if bugs:
        plan = author_fix_plan(bugs)        # specs + todos + acceptance tests, IN MAIN SESSION
        for bug in bugs:
            sig = bug_signature(bug)
            if attempts_for(sig) >= 3:
                escalate_to_user(bug, reason="3-attempt budget exhausted")
                continue
            R = classify_fix_risk(bug)
            if R >= 6:
                advisor()                   # consult before escalating; may downgrade R or suggest plan
                escalate_to_user(bug)
                continue
            dispatch_subagent(
                subagent_type="general-purpose",
                model="sonnet",             # bump to opus only if sonnet reports "stuck after 3"
                task=plan.for_bug(bug),
                isolation="worktree",
                require_skills=[
                    "superpowers:systematic-debugging",    # ALL FOUR PHASES, mandatory
                    "superpowers:test-driven-development",
                    "superpowers:verification-before-completion",
                ],
                pr_required=True,
            )
        wait_for_all_subagents()

        # 3a. POST-FIX SIGNAL VERIFICATION — the rule-zero check
        for pr in clean_PRs():
            if not original_signal_cleared(pr.heal_bug_signature):
                pr.demote_to_review_tier(reason="tests pass but signal still present")
                continue
            if pr.systematic_debugging_phase < 4:
                pr.demote_to_review_tier(reason="systematic-debugging exited before Phase 4")
                continue
            pr.auto_merge()                 # R<=2 AND signal cleared AND Phase 4 reached

    # 4. RUN — resume from last known good, never from Step 0
    company = next_company_or_resume()
    checkpoint = last_known_good_step(company)   # deepest schema-valid artifact pre-bug
    dispatch_pipeline(company, stage=infer_stage(company),
                      skip_to_step=checkpoint + 1 if checkpoint else 0)

    # 5. RE-ASSERT before RECORD — never persist state we cannot verify
    assert_invariants()                 # on fail: git tag invariant-fail-<ISO>

    # 6. RECORD (only if re-assert passed)
    update_memory_if_novel(bug_pattern)
    update_PROJECT_STATE_tracker()
```

## Fix risk classification — the greybeard score

```text
R = 3*HOT_PATH
  + 3*SCHEMA_MIGRATION
  + 2*SIGNATURE_CHANGE
  + 2*UNCOVERED_LOC_RATIO    # fraction of changed lines with zero test cov
  + 1*log10(BLAST_RADIUS)    # callers/importers, capped at +2
  + 1*log10(LINES_CHANGED)   # capped at +3
  + 1*RECENT_CHURN_BUCKET    # 0 if <3 commits/30d, 1 if 3-10, 2 if >10
  - 2*FAILING_TEST_EXISTS    # subagent built a reproduction test
  - 1*PURE_FUNCTION          # no I/O, no global state, no side effects
  - 1*REVERSIBLE             # one-commit revert undoes cleanly
```

| Score | Class | Action |
|-------|-------|--------|
| R <= 2 | `safe` | Auto-heal, auto-merge IF tests + lint pass AND signal cleared AND Phase 4 reached |
| 3 <= R < 6 | `review` | Auto-heal in worktree, open PR, do NOT merge |
| R >= 6 | `hard` | Do NOT auto-heal. `advisor()` consult, then escalate with score breakdown. |

**`HOT_PATH` detection includes prompts.** dd-bigbio behavior is prompt-driven; a one-line edit to `prompts/heal_unsupported.tpl.md` can change every report. `HOT_PATH = 1` if any of the following holds:

- File matches `src/dd_pipeline.py`, `src/dd_schemas.py`, `src/dd_audit_gate.py`
- File contains `^def main` or function name matching `orchestrator|_run_step|main_loop`
- File path matches `prompts/*.tpl.md`
- File is referenced by `src/dd_pipeline.py` via `Path(...).read_text()` (prompt-loaders)

All other factors computed from artifacts already in the repo — see v1 memory for the exact shell snippets per factor.

## Subagent model + type policy

| Work | subagent_type | model |
|------|---------------|-------|
| Grep / log scan / file location | `Explore` | haiku |
| Cross-codebase research, "where is X defined" | `Explore` | haiku |
| Easy/medium fix WITH plan + AC | `general-purpose` | sonnet |
| Open-ended easy/medium fix | `general-purpose` | sonnet |
| Risk class `review` (3 <= R < 6) | `general-purpose` | sonnet |
| Hard fix: cross-file edits, schema migrations | `general-purpose` | opus |
| Hard fix: architecture refactor | `general-purpose` | opus |
| Subagent stuck after 3 sonnet attempts | `general-purpose` | opus |
| Opus subagent fails on first attempt | escalate to user | — |
| Adversarial review (Step 6) | `adversarial-reviewer` | (its def) |

Rules:

- Main session runs Opus and orchestrates; tightly-coupled tasks stay in-thread; haiku never invokes superpowers skills; `Auto` routing is banned (kills attribution).
- **`advisor()` consult before any Opus dispatch** AND before any user escalation. Saves quota and catches bad approaches early.
- **Opus failure is terminal for that bug, not a retry trigger.** If Sonnet failed 3 times and Opus then fails, the bug escalates to the user immediately. Retrying Opus rarely changes the outcome and burns quota.

## Pre-commit hook policy

The user's global CLAUDE.md forbids `--no-verify`. The self-heal loop honors this absolutely:

- If a pre-commit hook fails on a heal commit, treat it as a normal bug (lint failure, type failure, etc.) — re-enter the loop with that signal.
- If the hook itself is the problem (e.g., the hook script crashes), that is a HYGIENE invariant violation. Halt and ask the user — don't auto-heal a hook script.
- NEVER pass `--no-verify`, `--no-gpg-sign`, or `-c commit.gpgsign=false`. The audit trail depends on these being intact.

## Model attribution — every commit

Auto-generated PR description + commit trailer template:

```text
Heal-Model: claude-sonnet-4-6
Heal-Risk: R=2 (safe)
Heal-Bug: <sha1 signature>
Heal-SystematicDebugging-Phase: 4
Heal-Signal-Cleared: yes
```

`git log --grep='Heal-Model:'` then yields a full audit trail of which model touched which file, at which phase it exited, and whether the originating signal cleared. Six months later when a regression surfaces, attribution is in the commit, not lost.

## Budget

- Max **3 heal cycles per bug signature, total** (not per iteration). Counter keyed on the canonical signature defined above. After 3, halt and ask.
- Max **5 concurrent subagents**. Use GNU `parallel -j min(cores, free_mem / 2_GB)`.
- Do NOT load `report.md` files >5 MB into main context — delegate to subagent, consume only its summary.

## User unavailability — park vs. hard halt

- **Soft escalation** (one company's hard fix, MEMORY.md prune approval, non-critical question, `--autonomous` mode hygiene fail) -> write `reports/<slug>/PARKED.md` with reason + `Heal-Bug:` ref, CONTINUE with other companies.
- **Hard halt** (correctness invariant failed, truth vector at risk, schema migration drift) -> SIGTERM all pipelines, write `reports/_runs/HALT_<ISO>.md`, STOP. Bad state could leak across companies.

When in doubt, hard halt. Better to wake the user than publish a fabricated digit.

## Conflict avoidance

Before any code change check `pgrep -fc "src.dd_pipeline"`. If pipelines are mid-run, only edit files the pipeline does NOT import at runtime (tests, prompts, docs, memory). Defer hot-path edits to between-company gaps.

## Termination

Loop exits cleanly when ANY of:

- All requested companies have `report.md` + `web.json` + `internal_summary.md`
- User types `halt self-healing` / `stop`
- An invariant fails twice in a row (codebase corruption beyond auto-recovery)
- All remaining companies parked AND no live pipelines (clean drain)

On exit write `reports/SELF_HEAL_LOG_<ISO-date>.md` with companies completed, bugs detected+fixed (commit refs), bugs detected+escalated (open issues), memory entries added/updated, invariant violation history.

## Generalizing beyond dd-bigbio

Three knobs the protocol assumes about the host repo. If invoking in another codebase, the user (or a config file) must supply equivalents:

1. **The truth-vector artifact** — dd-bigbio uses `verified.json`. Generic: name the file whose schema validity gates downstream writes.
2. **The pipeline entry point and step contract** — dd-bigbio uses `src/dd_pipeline.py` with `--skip-to-step N`. Generic: any orchestrator that supports resume-by-step.
3. **The audit gate** — dd-bigbio uses `src/dd_audit_gate.py`. Generic: any CLI that exits non-zero when downstream-truth invariants fail.

Without these three, the loop runs but the invariants degrade to "tests pass + lint clean" — which protects code quality, not the truth vector.

## Invocation

- Sentinel phrase: `self-heal this code [optional: company list]`
- Slash command: `/self-heal [--interactive | --autonomous] [company list]`
  - `--interactive` (default) — auto-heal safes, gate review-tier merges on user input, escalate hard-tier immediately
  - `--autonomous` — overnight mode; auto-merge safes when all gates pass, park anything that would normally halt (except correctness/liveness invariants which still hard-halt)
- Auto-trigger: a watching session detecting a bug-signal whitelist match in `pipeline.log` and offering to enter the loop

Before starting any unattended overnight run, verify schema coverage is broad enough that checkpoint condition #2 (schema-valid artifact at every step boundary) is meaningful. See the JSON-schema-harmonization plan at `~/code/dd-bigbio/docs/superpowers/plans/2026-05-20-json-schema-harmonization.md` — until that ships, only `DDSignalReport` and `RunSummary` are schema-gated. Unattended scaling past one company at a time is unsafe until the rest are covered.

## v1.1 deltas vs. project-memory v1

Folded in with hindsight on 2026-05-20:

1. **Rule zero made explicit and load-bearing.** systematic-debugging runs end-to-end on every fix; Phase 4 completion is required for auto-merge regardless of risk class.
2. **Post-fix signal verification gate.** "Tests pass" insufficient — the original ERROR/Traceback/audit_gate signal must clear. Demote PR to review-tier if not.
3. **Canonical bug signature.** Replaces "log pattern" with a SHA1 over `{step, signal_type, normalized_pattern, claim_id}` so the 3-attempt budget can't be reset by cosmetic differences.
4. **Opus failure is terminal, not retry-trigger.** Sonnet x3 then Opus x1 then user. Retrying Opus rarely helps and burns quota.
5. **`advisor()` consult before Opus dispatch AND before user escalation.** Catches bad approaches before they cost.
6. **HOT_PATH detector covers `prompts/*.tpl.md`.** dd-bigbio is prompt-driven; v1 missed this and underrated risk on prompt edits.
7. **MEMORY.md ceiling policy by mode.** Interactive halts and asks; autonomous parks the prune and continues (does not corrupt truth, so no hard halt).
8. **Pre-commit hook policy.** Treat hook failures as bug signals; never `--no-verify`. If the hook is broken, hygiene-invariant halt.
9. **Enriched commit trailer.** Adds `Heal-SystematicDebugging-Phase:` and `Heal-Signal-Cleared:` so audit captures the discipline state, not just the model.
10. **`--interactive` vs `--autonomous` slash flags.** Default is interactive (gates review merges). Autonomous is opt-in for overnight runs.
