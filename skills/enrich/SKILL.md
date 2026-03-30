---
name: enrich
description: >-
  Takes an existing biotech report, fact-checks every claim against 1,900+
  scientific databases, discovers novel cross-domain insights, and outputs a
  publishable Tufte-style PDF with full evidence traceability. Zero hallucination
  tolerance. Every fact traceable to its source. LLM designs the document layout,
  picks fonts, and visually inspects every page before delivery.
---

# /enrich

Paste a report. Get back a publishable, fact-checked, insight-enriched PDF.

## When to Use

- "Enrich this report" / "Make this novel" / "Improve this analysis"
- Pasted biotech/pharma report text with request to enhance
- "Fact-check and find what they missed"
- Any existing report that needs cross-domain insights and traceable evidence

## Input

The user pastes a ~500-3000 word report (company analysis, drug profile, disease review, market report, competitive landscape) and asks for enrichment.

## Workflow

Five phases. Each appends to `research_notes.md` — the brain thinks in prose, not data structures.

### Phase 1: Parse

Read the report sentence by sentence. Extract:

- **Claims**: every factual assertion
- **Entities**: genes, drugs, diseases, pathways, companies, trials, natural products
- **Relationships**: "X targets Y", "A causes B"
- **Gaps**: what the report doesn't mention but should

Append to `research_notes.md`. See [references/fact-checking.md](references/fact-checking.md).

### Phase 2: Fact-Check

Verify every claim against databases. For each:

1. Search the tool catalog for relevant databases (`grep_tools`, `find_tools`)
2. `get_tool_info` then `execute_tool` for each relevant tool
3. Verify with 2+ independent sources
4. Classify: Verified / Corrected / Unverifiable / Misleading

**Zero-tolerance**: no T3/T4-only claims presented as fact. See [references/fact-checking.md](references/fact-checking.md).

### Phase 3: Deep Research

Find what the report missed. This creates the novel value.

**First iteration: cast wide.** Don't search narrowly for the report's thesis. Search broadly — what databases even exist for these entities? What adjacent fields touch this topic? Use `find_tools` with broad concepts, `grep_tools` with entity names, `list_tools(mode="by_category")` to discover entire categories of tools. The goal is to be surprised.

**Then follow the expanding frontier**: results reveal new entities, each triggers new catalog searches. A drug leads to targets, targets lead to pathways, pathways lead to other diseases, diseases lead to trials, trials lead to companies, companies lead to SEC filings.

Hunt specifically for:

- **Cross-domain connections**: natural products, venom peptides, plant biotech, environmental factors
- **Market signals**: competitor pipelines, SEC filings, hiring patterns
- **Mechanism connections**: shared pathways between unrelated diseases, repurposing opportunities
- **Safety signals**: FAERS data, drug warnings, enforcement actions

### Phase 4: Classify Findings

Every finding gets a label:

| Label | What it means |
|-------|--------------|
| `VERIFIED` | Original claim confirmed with citations |
| `CORRECTED` | Original claim was wrong or incomplete |
| `NOVEL INSIGHT` | Cross-domain connection not in original, T2+ evidence |
| `NOVEL IP` | New hypothesis with multi-hop evidence chain, commercial potential |
| `MARKET SIGNAL` | Business-relevant finding from regulatory/financial data |

See [references/novelty-detection.md](references/novelty-detection.md) for definitions and evidence bars.

### Phase 5: Compose PDF

Design and typeset the report. No fixed template — the content determines the layout.

**Toolchain**: `tufte-swiss.sty` + `lualatex` (NEVER pdflatex or xelatex).

```bash
cp ~/.claude/skills/tufte-swiss-typography/assets/tufte-swiss.sty ./
cp ~/.claude/skills/tufte-swiss-typography/assets/tufte-swiss-grid.lua ./
lualatex --interaction=nonstopmode report.tex
```

**The LLM decides**:

- Document structure, section order, emphasis
- Font pairing (from 616+ installed OTF fonts, discovered via `fc-list`)
- Whether findings get callout boxes, tables, prose, margin notes, or full pages
- Narrative arc — lead with the headline insight or build to it
- Document length — 2 pages or 12, whatever the content demands
- Which Tufte design principles to apply where

**Constraints** (non-negotiable):

- Tufte asymmetric layout: body text left (~65%), evidence in right margin (~35%)
- Every fact has a margin citation with evidence tier badge
- Novel findings visually distinct from verified claims
- Sparklines inline where data trends exist
- Connection diagrams (TikZ) for multi-hop evidence chains
- Methodology note stating database count and verification standard
- Compile with `lualatex`, never pdflatex

**Visual QA loop**: After compiling, read every page of the PDF as an image. Check for overlapping text, broken figures, colliding margin notes, bad page breaks, aesthetic problems. Fix the `.tex`, recompile, re-inspect. Repeat until every page passes.

See [references/composition.md](references/composition.md) for typography primitives, layout patterns, and Tufte's design principles.

## Output

- `report.pdf` — the publishable document
- `research_notes.md` — the brain's working memory (full audit trail)

## Evidence Standards

| Tier | Sources | Reliability |
|------|---------|-------------|
| T1 | FDA, SEC, ClinicalTrials.gov, FAERS, OMIM | Regulatory / official |
| T2 | PubMed, Crossref, OpenAlex (peer-reviewed) | Validated |
| T3 | BioRxiv, MedRxiv, WebSearch, Wikipedia | Unvalidated |
| T4 | STRING, text-mining, pathway inference | Computational |

Novel insights require minimum T2. Claims presented as fact require minimum T1 or T2.

## Reference Docs

| Document | Load when |
|----------|----------|
| [references/fact-checking.md](references/fact-checking.md) | Phase 2: claim extraction, verification protocol, zero-tolerance rule |
| [references/novelty-detection.md](references/novelty-detection.md) | Phase 3-4: what counts as novel, cross-domain strategies, evidence chains |
| [references/composition.md](references/composition.md) | Phase 5: tufte-swiss primitives, font selection, layout patterns, visual QA |
