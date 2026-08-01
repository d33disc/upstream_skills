---
name: prompt-facts-session-harvest
type: prompt
updated: 2026-08-01T11:40:13.853Z
---

# Session fact harvest -- propose, gate one-by-one, author only on `y`

Harvest durable truth claims out of a working session's memory and admit the approved ones
into the v2 fact engine, one explicit human decision per claim.

## HARD GATE -- READ THE LAW CORPUS BEFORE PROPOSING A SINGLE CANDIDATE

**This is step ZERO and it BLOCKS. Do not harvest, draft, rank, or show a candidate until the
corpus is read.** Harvesting is fact-engine work; the same gate that governs authoring an atom
governs proposing one, because a proposal that reaches the human is already an implicit claim
that the shape is admissible.

```bash
bash bin/facts-law.sh          # derives the 12-doc corpus VERBATIM; --force to reprint
```

The 12 docs it derives, live (never hand-list them from memory -- re-derive):

```text
  docs/superpowers/specs/FACT-ONTOLOGY.md              <- the spine: amendments FIRST, then
                                                          s0 closure, s1 Theorem 1 + A1-A4 +
                                                          R13', s2 registries, s7 T-codes,
                                                          NON-GOALS
  docs/superpowers/specs/2026-07-11-fact-logic-act-design.md
  docs/superpowers/specs/authored-predicate-2026-07-17.md
  references/predicate-registry.md      CLOSED -- the only legal predicates
  references/origin-registry.md         locator TYPE sets the provenance class + window
  references/provenance-lattices.md     what outranks what, and where a grade is REFUSED
  references/conventions.md             the full atom grammar
  references/context-registry.md        export contexts + their evidence floors
  references/inference-registry.md      what may be DERIVED vs must be witnessed
  references/source-derivations.md
  references/judge-operations.md
  references/adjudicated-residuals.md   documented amber, never silently admitted
```

Plus, always, `references/fact-authoring-governing-rules.md` (rule 1, the a308 shape: an
opaque predicate's SUBJECT -- said / texted / believes / promised -- must be WITNESSED by the
locator's provenance, never inferred from prose, context, or role).

**The PreToolUse hook `bin/facts-law-hook.sh` fires on this surface automatically** -- its
regex covers `knowledge/`, `people/`, `bin/facts/`, `doctor`, `facts-gate`, `facts.build`,
and `gate.sh`. **Do not wait for it, and do not treat its output as the reading.** It fires
ONCE per session and then stays silent, so a later harvest in the same session gets NO
injection at all. Run `bin/facts-law.sh --force` by hand rather than assuming the hook covered
you.

**Reading the preview is not reading the law.** On 2026-08-01 this exact shortcut -- skimming
the hook's 2KB preview, then authoring -- produced a PR titled with a claim the law does not
support ("the prose is off by one"), when the law is in fact SILENT on that boundary. The
correction cost more than the reading would have. In a system with proofs, an unread
"first-principles idea" is almost always an existing clause restated without its
justification; the tell is confidence about a shape before having read the constraint that
makes the current shape look awkward. [[feedback-read-schema-docs-before-fact-engine]]

## Why this shape

A session generates far more true statements than belong in the corpus. Two different filters
have to pass, and **they are independent**:

```text
  DURABLE?      is it still true, and still worth knowing, after this session ends?
                (a gate result, a file path, a tool version -> NO. an arrangement,
                 a decision, a purchase, a stated belief -> maybe.)
  AUTHORABLE?   does a CLOSED-registry predicate already carry this shape,
                and does a locator WITNESS it?
```

A fact can be durable and unauthorable (no predicate exists -> the value goes in as entity
PROSE and an amendment is FLAGGED, never minted mid-task). A fact can be authorable and not
worth durable storage (most operational noise). **Only propose what clears both**, and say
plainly which candidates fail which filter rather than padding to a target count.

The human gate is the point: admission is a judgment, and the corpus is a trust artifact.
Never batch-admit; never infer a `y` from silence or from a general "sounds good".

## Inputs

- `{SESSION_SOURCE}` -- what to mine (this conversation, a journal file, a transcript JSONL)
- `{SESSION_UUID}` -- for `session:` locators; the transcript under `~/.claude/projects/`
- `{COUNT}` -- how many candidates to surface (default 10)

## Procedure

1. **The HARD GATE above -- read the corpus.** Blocking. Nothing below runs until it is done,
   and it is not satisfied by the hook's injection.
2. **Harvest candidates** from `{SESSION_SOURCE}`. Prefer: decisions made, arrangements
   stated, purchases, beliefs asserted by a named human, relationships. Reject: gate results,
   tool versions, file paths, anything re-derivable from the repo or git history.
3. **For each candidate, draft the FULL atom before showing it** -- subject, predicate,
   locator, verbatim quote, `at`. If drafting reveals no predicate fits, keep the candidate
   but label it `PROSE ONLY -- registry amendment required`, and do not mint a predicate.
4. **Present ONE candidate at a time.** Show the rendered atom line, the provenance grade it
   will earn, and the one reason it might not belong. Then stop and wait for `y` / `n`.
5. **On `y`:** verify the subject/object slugs EXACT-resolve to `name:` stubs in `people/` or
   `knowledge/` (mint the stub first if missing), append the atom to the right note, mint
   `^f-YYYYMMDD-<4hex>` as `sha256(prop)[:4]`, bump `updated:` with a REAL
   `gdate -u +%Y-%m-%dT%H:%M:%S.%3NZ` -- never a typed stamp.
   **On `n`:** drop it silently. Do not re-argue it; a `n` is data about the corpus, not an
   objection to overcome.
6. **After the last decision:** gates BARE, never piped --
   `PYTHONPATH=bin .venv/bin/python -m facts.build` (0 rejected) ->
   `bash bin/doctor-all.sh` -> `bash bin/facts-gate.sh`. Then a `journal/` breadcrumb
   recording what was admitted AND what was declined, with reasons.

## Guardrails

- The quote is VERBATIM and must literally contain every number, date, name, negation, and
  unit in the proposition. If the quote does not carry it, the proposition may not claim it.
- `at` is WORLD time (when the fact HELD), never capture time. `report_lag` is derived from
  the gap -- collapsing them destroys it.
- One claim per atom. No ` and `. A conditional needs a `[when:]` guard.
- R5: never let a git-tracked proposition carry more precision than its git-tracked quote
  (full account numbers, DOB, addresses stay local). **A search pattern for a secret IS the
  secret** -- describe a verification, never paste the needle into a tracked file.
- A `session:` locator is `self-report` grade and PERMANENT stability. It witnesses that the
  subject SAID it -- never that the content is true. `said` / `believes` are the honest
  predicates for testimony; do not upgrade testimony into a status claim.

## Links

[[reference-v2-fact-engine-streaming]] [[feedback-read-schema-docs-before-fact-engine]]
[[fact-authoring-governing-rules]] [[predicate-registry]] [[origin-registry]]
[[feedback-all-facts-through-v2-ontology]] [[feedback-operational-claims-are-facts-too]]
[[feedback-grade-evidence-per-proposition]]
