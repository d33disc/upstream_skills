---
name: fact-harvest
description: |
  Use this skill when turning past Claude session transcripts or a document into admitted facts in the `me` v2 fact engine. Triggers: "harvest sessions", "scrape past sessions for facts", "what have I told you that never got written down", "memorize this document", "memorize <path>", "ingest this into the fact engine". Do NOT use to author one already-known fact (edit the note), nor over estate, legal, healthcare or mental-health material without walking the privacy fork.
---

# fact-harvest — transcripts + documents → admitted atoms

Chris has ~3,000 sessions of things he has said about his own life that were never written
down. This skill turns the recoverable part of that into atoms the engine has admitted.

**You are the EXTRACTOR; `bin/facts/` is the unforgeable GATE.** The driver
(`scripts/harvest_sessions.py`) hands you filtered turns and nothing else — it deliberately contains
no drafting logic, because a script that "extracts facts" is a fabrication engine with a
deterministic face. Every judgment below is yours, and every one of them is checkable.

## 0 · Where things live (this skill is global, the engine is not)

This skill ships in `upstream_skills` and is reachable from every repo. The fact engine,
the law corpus and the only legal sinks live in ONE repo. Set the root first; every
`bash bin/...` and every `references/...` / `docs/...` path below is relative to it.

```bash
ME=~/code/me            # the engine, the law, knowledge/ + people/ -- the only sinks
cd "$ME"                # run every gate and every law command from here
```

`scripts/*` paths are relative to THIS skill folder, not to `$ME`. If `$ME` does not exist
on the host, stop: there is nowhere admissible to write, and a harvest with no sink is a
transcript-reading exercise that ends in a lost queue.

## 0 · HARD GATE — read the law first

```bash
bash bin/facts-law.sh            # derives the 12-doc corpus verbatim
```

Minimum: `docs/superpowers/specs/FACT-ONTOLOGY.md` (amendments first, then s0 closure, s1
Theorem 1 + A1–A4 + R13', s2 registries, s7 T-codes, NON-GOALS), `references/origin-registry.md`,
and `references/fact-authoring-governing-rules.md` — **rule 1 (a308) is the one this skill can
violate at scale.**

> **Version check, do not skip.** `FACT-ONTOLOGY.md` and `references/conventions.md` both
> announce **v2.25** in their headers; the engine is at **v2.28**. The registries were amended
> past the prose. When they disagree, `bin/facts/parse.py` + `bin/facts/registries.py` are the
> spec — the regex *is* the grammar. v2.28 adds the `[as: <capacity>]` facet and a **frame
> registry**: every predicate must belong to a family, enforced at load time.

## 1 · The three lanes — get this wrong and the guard is disarmed

A transcript is not a document. It is three provenance classes braided into one file, and
**only one is admissible as `session:`**.

| lane | what it is | verdict |
| --- | --- | --- |
| bytes Chris authored about his own life — any register | TESTIMONY | admit on `session:` |
| ANOTHER PARTY's document he pasted | LEAD | re-anchor to that document's own locator |
| assistant text / tool output | LEAD | no registry type can carry it — never admissible |

The split is **authorship, not register** (see §2 — an earlier version of this table said
"conversational register", which would have discarded Chris's own timeline notes as foreign).

This matters more than it looks. `bin/facts/witness.py` **exempts `session:` from the a308
document-locator check**, because session provenance witnesses the speaker by construction. So a
mis-classified entry does not merely add a wrong row — it mints testimony at the engine's
highest-grade, **permanent, never-expiring** class with the a308 guard structurally disarmed.

`session:` witnesses that **he said it, never that it is true.** `said` is an opaque predicate
(R9): admitting *"Chris said the round closed at $2M"* commits the corpus to the utterance, not
the round. Do not silently upgrade an utterance into a fact about the world.

## 2 · The register rule — register is a SIGNAL, authorship is the TEST

Document register in a quote — headings, third person, bullet syntax, a title-case label
followed by a colon — means **stop and establish who wrote the bytes.** It does NOT by itself
mean the bytes are someone else's, and treating it as if it did will destroy good atoms.

> **Corrected 2026-08-01, by investigation.** An earlier version of this rule cited
> `knowledge/jobs/mango-legal.md` `^f-20260622-e231` as a live paste trap — "structurally his
> typing, semantically someone else's bytes." That was **wrong**, and traced properly it
> falsifies itself. The quote's authoring entry is `attachment.type: "queued_command"` — a
> 24,742-char timeline **Chris compiled about his own life** and submitted himself. No
> third-party markers (`Prepared by`, `Memorandum`, `Dear` all absent). The bytes are HIS, so
> `session:` — self-report, the subject's own statement — is the CORRECT locator. A person
> writing terse notes about themselves is still the author. Acting on the un-investigated
> version would have "re-anchored" three sound atoms (`e232`-`e234`) into gaps.

So the test is **authorship, not style**:

```text
  who typed these bytes?
    |
    +-- Chris, about his own life (even in note/table/timeline form)  -> TESTIMONY, session:
    +-- someone else's document he pasted (letter, filing, report,
        another person's email, a web page)                           -> LEAD, lane 2
    +-- assistant text or tool output                                 -> LEAD, never admissible
```

Resolve it from the transcript entry, never from how the prose reads: `attachment.type`,
`promptSource`, `origin.kind`, and whether the text carries another party's letterhead, byline
or salutation. For lane 2, find the underlying artifact and anchor to `pdf-local`/`email`/`web`.
If the artifact cannot be located, **the fact is a gap, not an atom** — and note that a
self-compiled timeline has no underlying artifact *because there was never one*, which is a
reason to admit it as testimony, not to discard it.

What `e231` actually was: an **entailment** defect, orthogonal to register. Its quote said a
demand was *sent to* "Mango Micro"; the proposition claimed Mango *renamed itself*. The quote
never said that. Repaired 2026-08-01 to what the source entails (`^f-20260801-a57e`). The floor
could not catch it — no number, date, negation or unit to check, and names are deliberately
unchecked. **That** is the failure mode to harvest against: a claim drifting beyond its quote.

## 3 · Run the driver

```bash
python3 scripts/harvest_sessions.py inventory --pending      # what is left to mine
python3 scripts/harvest_sessions.py show <session-uuid>      # the admitted turns
python3 scripts/harvest_sessions.py queue <session-uuid>     # park them locally for review
```

State is **derived, never stored**: `harvested` = the uuid appears in a `session:` locator under
`knowledge/`+`people/`; `reviewed` = a `journal/` breadcrumb cites it. `reviewed && !harvested`
means *looked, nothing survived* — a real and common outcome, not a failure.

**Read the `unknown-origin` count on every run.** The filter fails closed, so an unrecognised
harness shape yields silence rather than garbage — which is the safe direction only while it
stays visible. A non-zero count means turns were refused for want of a provenance marker;
inspect one before trusting the number. The `{typed, queued}` allowlist alone admitted **zero**
turns on the remote harness (where genuine turns carry `origin.kind: human` + `promptSource:
sdk`), and a silent zero-harvest is indistinguishable from a clean run.

## 4 · The privacy fork — before writing, decide the sink

`publishable:` gates **export, not the commit.** Every file under `knowledge/` and `people/` is
git-tracked, so a sensitive atom in a tracked note reaches GitHub regardless of frontmatter
(`projects/fact-ontology/FINDINGS-2026-06-12-restricted-leak.md` BUG 1).

> **BUG 2 in that FINDINGS doc is STALE — do not repeat it.** It says the pre-commit wall guard
> "never runs" because `core.hooksPath` = `~/.githooks`. That was true on 2026-06-12; it has
> since been fixed. Verified empirically 2026-08-01: `core.hooksPath` =
> `/Users/davis/code/me/.git/hooks`, and staging a line containing a trigger term is BLOCKED.
> The guard runs, from worktrees too. Check the live state, never a findings doc — a stale bug
> report is a well-formed claim about a world that no longer exists.

The guard is real but **narrow**: a clinical/crisis deny-list (mental-health terms, the
counselor's name, Section-12 language). It will not stop estate, financial, third-party, or
kid-related material. So it is a backstop for ONE category, never a substitute for the fork.
The fork is yours, and it happens **before** the write:

1. Sensitive? — estate, legal strategy, healthcare, mental health, third-party private facts,
   anything about Chris's kids beyond the mundane, anyone's finances.
2. **If yes: refuse the sink.** Leave it in the local queue and tell Chris plainly —
   *"no admissible sink exists for this one; it needs the git-ignored restricted root
   (FINDINGS BUG 1a), which is not built yet."* Do **not** write it to a tracked file
   intending to sort it out later.
3. If uncertain, treat as sensitive. Fail safe.

## 5 · Author the atom

One claim per line; the engine derives class and id. Consult
`references/fact-authoring-governing-rules.md` first, every time.

```text
- [[subject]] <predicate> [[object]]? <rest>. [when: <guard>]? [src: session:<subject-slug>@<uuid>@<topic>; "<verbatim quote>"; at <world-when>] ^f-YYYYMMDD-<4hex>
```

- **subject/object** — kebab `[[slug]]` that EXACT-resolves to a `name:` stub; mint the stub first.
- **predicate** — lowercase, from the closed registry, and it must belong to a **frame family**
  (v2.28). A new predicate needs an R7 justification line in the registry *first*.
- **locator** — `session:<subject-slug>@<uuid>@<topic-anchor>`. The registry defines
  `<subject-slug>@<session-uuid>`; practice appends a topic anchor and the grammar absorbs it
  into `lanchor`. Use it — a bare uuid is unlocatable inside a 900-turn transcript.
- **quote** — verbatim, containing every number, date, negation and (value, unit) pair in the
  claim. Never paraphrase to make the literal floor pass; if the quote does not carry the number,
  the claim is not that precise. **NOT proper names** — the name clause was retired in v2.25 and
  `bin/facts/floor.py` checks only those four things (verified 2026-08-01). A capitalized-token
  name floor reds 609/2008 atoms (30.3%), almost all benign variants; name identity needs
  interpretation, which the floor's charter forbids. Wrong-counterparty protection lives in the
  R6'' judge layer, not here — do not hand-enforce a floor rule the engine does not have.
- **`at`** — the WORLD time the fact held, not when he said it. This is the most common error in
  session harvesting: a 2026 conversation about founding a company in 2017 is `at 2017`.
- **id** — `sha256(prop)[:4]`, never sequential (sequential ids collided 2026-07-01).
- No ` and ` — split it. A conditional REQUIRES a `[when:]` guard with enforced arity.

## 6 · The review loop — the interaction contract

Work one candidate at a time. For each, show the atom you propose, the verbatim quote, and the
turn it came from. Then:

```text
[Enter] admit    [s] skip    [e] edit    [u] undo last    [q] stop
```

- **Admit is the bare-Enter default** — the volume only works if the common case is one keystroke.
- **The default FLIPS to skip** on any atom that hit the privacy fork. The cheap keystroke must
  never be the unsafe one.
- **`undo last` names its target** ("undo: chris-davis founded mango…"), never a bare confirmation.
- **Batch the writes to the end of the queue.** Undo stays free, `q` is always clean, and a
  half-harvested session never lands in the corpus.

## 7 · Document mode (absorbs `/me:memorize`)

Same skill, different source. Resolve the document to a locator TYPE from
`references/origin-registry.md` and its addressing rule (`path#p<n>@sha256`, `doi@…`,
`gmail-id@…`). No registered type fits → **stop and propose an R7 amendment**; a document with
no stable address cannot anchor facts. Then REAP candidates → ANCHOR each to a verbatim quote →
privacy fork → write → gate. Steps 4–6 above apply unchanged.

Career and biographical atoms have a canonical upstream source and a strict source-first add
order — see `.claude/rules/career-facts.md` before writing any of those.

## 8 · Gate, and report honestly

```bash
bash bin/doctor-all.sh                              # shape gate, exit 0
PYTHONPATH=bin .venv/bin/python -m facts.build      # N parsed / M rejected
bash bin/gate.sh                                    # BARE — never pipe it
bash bin/facts-judge.sh                             # guarded atoms: cross-family verdict
```

**Never pipe `gate.sh` into `tail`** — `$?` is then TAIL's exit code, and that exact seam
produced a session-long false GREEN (the script's own header documents it).

Report shape:

> harvested N atoms from `<uuid>` into `<notes>` · admitted A / rejected R (reasons) / gaps G ·
> refused-for-sink S · unknown-origin U · now answerable: `<one concrete new query>`

A rejected atom is reported **with its reason**, never dropped quietly. Never call a fact
"harvested" without a build line showing it parsed. Then stamp `updated:`
(`gdate -u +%Y-%m-%dT%H:%M:%S.%3NZ`), append a `journal/` breadcrumb citing the session uuid —
**this is what marks the session reviewed** — and wire reciprocal `[[links]]`.

Links: `references/conventions.md` · `references/predicate-registry.md` ·
`references/origin-registry.md` · `[[fact-authoring-governing-rules]]` ·
`[[reference-v2-fact-engine-streaming]]` · `[[feedback-all-facts-through-v2-ontology]]` ·
`[[feedback-read-schema-docs-before-fact-engine]]`.
