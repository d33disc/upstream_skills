# dd-bigbio Defaults and Portability

Read this only when adapting `self-heal` to a non-dd-bigbio repository or changing `.self-heal.toml` behavior.

## Portable Contract

The portable self-heal contract is:

- a state directory for cursor, heartbeat, attempts, parked items, and halt reports
- a truth-vector artifact that proves downstream output before publication
- a pipeline entrypoint that can be detected, paused between iterations, and resumed
- a hard-blocked path list for infrastructure the loop must not auto-heal
- explicit risk scoring before auto-merge or review-tier PR creation

Everything else is a repo-specific default.

## dd-bigbio Defaults

These defaults are embedded in `scripts/policy.py` and shown in `SKILL.md`:

```toml
[paths]
state_dir = "reports/_runs"
report_log_prefix = "SELF_HEAL_LOG"

[truth_vector]
artifact = "verified.json"
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
extra_globs = []
```

## Porting Checklist

For another repository, create `.self-heal.toml` at the repo root and run:

```bash
python3 ~/code/upstream_skills/skills/self-heal/scripts/policy.py \
  validate-config --repo-root <repo-root>
```

Then verify:

- the truth-vector artifact exists before human-facing output is written
- the pipeline entrypoint is specific enough for `pgrep -fc`
- the resume flag maps to a real checkpoint boundary
- hard-blocked paths include schema, policy, and loop infrastructure
- the relevant tests and linters are known before any unattended run
