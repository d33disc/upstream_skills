---
name: shell-discipline
description: Deterministic shell, data-processing, and scripting discipline for the Mac -- tool-tier selection (Claude Code built-ins vs native shell vs a script), format-aware parsing (jq for JSON, sqlite3 for CSV/TSV, never regex on structured data), macOS/BSD guardrails (sed/grep/date differ from GNU), safe curl networking, atomic writes, observability, and GNU parallel. Use BEFORE writing any non-trivial shell command, pipeline, one-off script, or data transformation on this machine.
---

# Shell + data-processing discipline (macOS / M1 Max)

Governing principle: reach for the simplest tool whose DATA MODEL matches the
input's structure -- not the lowest-level tool. Goal is zero SILENT failures,
not minimal abstraction.

- Line-oriented / whitespace-tabular text -> coreutils (awk, sed, grep, cut).
- Structured formats (JSON, CSV, TSV, XML) -> a format-aware parser ONLY. Regex
  on structured data is forbidden; it corrupts silently on quoting, embedded
  delimiters, and newlines.

Native floor (zero Homebrew): coreutils + curl + sqlite3 ship on every Mac --
text, HTTP, SQL, AND correct CSV/TSV (via sqlite3). Only external dep worth
allowing is jq for JSON (native on macOS 15+, Homebrew on 14-). The preflight
makes any missing binary fail loud, not silent.

## Tool tiers -- prefer the lowest error surface

Built-in tools sit BELOW the shell (no quoting, escaping, word-splitting, or
BSD-vs-GNU layer), so for file work they are the most deterministic option and
MUST win over shelling out.

**Tier 0 -- Claude Code built-ins (FIRST for file ops):**

- Read a file -> `Read` (not cat/head/tail) -- line numbers, chunks big files,
  reads images/PDFs/notebooks. Big files: offset/limit; never >500 lines into
  main ctx (large corpus -> subagent).
- Find files -> `Glob` (not find/ls) -- pattern match, mtime-sorted, respects
  `.gitignore` (`CLAUDE_CODE_GLOB_NO_IGNORE=false`).
- Search contents -> `Grep` (not shell grep/rg) -- ripgrep engine + regex, skips
  `.gitignore`, sidesteps BSD-vs-GNU grep. First tool when no LSP; broad sweeps
  -> Explore agent, not main ctx.
- Edit -> `Edit`/`MultiEdit` (not sed -i) -- exact string replace, read-before-
  edit + on-disk staleness check; kills the `sed -i ''` data-loss footgun.
- Create -> `Write` (not `echo >` / heredoc).
- Notebooks -> `NotebookEdit`/`NotebookRead` (not sed/jq on `.ipynb` JSON) --
  cell-aware by `cell_id`; editing notebook JSON by hand corrupts it silently.
- Type errors -> `mcp__ide__getDiagnostics` (optional plugin; VS Code/JetBrains).
- Web -> `WebFetch`/`WebSearch`. Long-running -> `Bash(run_in_background)` /
  `Monitor`.

**Tier 1 -- native shell via `Bash`** (what Tier 0 doesn't cover): stream
transforms, pipelines, HTTP, SQL. coreutils, curl, sqlite3, jq. The BSD
guardrails below apply HERE only.
**Tier 2 -- a script:** only under the scripting exception below.
Rule of thumb: touching a FILE -> Tier 0. Transforming a STREAM -> Tier 1.

| Task | Tool |
| --- | --- |
| Line/tabular text | awk, sed, cut, sort, uniq, head, tail, wc |
| Fixed-string search | `grep -F` (`grep -E` only for real regex) |
| JSON / JSONL | jq (`/opt/homebrew/bin/jq` 1.8.1; `-r` raw, `-c` compact, `-e` exit-on-null). Never a language JSON parser, never sed. |
| CSV / TSV (quoted fields) | `sqlite3`: `.mode csv` + `.import` is a correct RFC-4180 parse (quotes, embedded commas/newlines); query in SQL, `.output` back to CSV. `cut`/`awk` on CSV ONLY if confirmed delimiter-clean, no quotes, no embedded newlines. `mlr`/`qsv` if present (Homebrew, not native). |
| SQLite / Postgres / MySQL | `sqlite3` / `psql` / `mysql` CLI, inline SQL or heredoc |
| HTTP / API | `curl -fsS` (see Networking) |

rg/fd at `/opt/homebrew/bin` for interactive use; `ruff` at
`~/.pyenv/shims/ruff`. markdownlint-cli2 prints a 4-line banner every run --
expected, not an error. jq patterns:

```bash
jq '.files[].title' f.json               # pluck from array
jq -r '.class' f.jsonl | sort | uniq -c  # JSONL frequency
jq 'select(.k=="v")' f.json              # filter
jq '{id,title}' f.json                   # reshape
```

## Script preamble (every script)

```bash
#!/usr/bin/env bash
set -euo pipefail   # -e exit on error, -u unset=error, pipefail=no silent loss
export LC_ALL=C     # deterministic, locale-independent, faster sort/grep/awk
```

Always quote expansions (`"$var"`, `"${arr[@]}"`); never bare `$var`. Use
`printf`, never `echo -e/-n` (BSD vs builtin differ).

## macOS/BSD guardrails (shell-out only)

- In-place sed: `sed -i '' 's/old/new/g' file` (empty backup arg mandatory on
  BSD). Never GNU `sed -i 's/...'`.
- `grep -E` / `grep -F`, never egrep/fgrep.
- date: `date -r <epoch>` is valid BSD. FORBIDDEN (GNU-only): `-d`/`--date`,
  `%N`. (`-r` is NOT the GNU flag.)
- Need real GNU and coreutils is installed -> use prefixed `gsed`/`ggrep`/`gdate`
  explicitly; never assume them.

## Networking

`curl -fsS` -- `-f` makes 4xx/5xx return non-zero (curl otherwise EXITS 0 on a
404 body = silent failure); `-sS` drops the progress bar but keeps errors
visible. Add `-X`/`-H` explicitly; `--fail-with-body` when you need the error
body.

## File modification (no data loss)

Atomic write -- process to a temp file, then `mv` onto target (atomic on same
fs): `awk '...' in.txt > in.txt.tmp && mv in.txt.tmp in.txt`. If in-place, keep
a backup: `sed -i.bak 's/.../' file`, remove `.bak` only after verifying.

## Observability

Never `2>/dev/null` except a KNOWN cosmetic warning -- let stderr flow back so
the raw error is self-correctable. Need the code: `cmd; echo "exit=$?"`. Verify
source before piping: `[ -s input.csv ] || { echo "input.csv missing" >&2; exit
1; }`. Preflight non-preinstalled binaries: `for b in jq mlr curl; do command -v
"$b" >/dev/null || { echo "missing: $b" >&2; exit 1; }; done`.

## Scripting exception (when a real language IS correct)

Write a script -- pure stdlib, zero deps -- ONLY if (1) logic needs math/crypto
not native to UNIX utils, OR (2) structure is deeply nested / non-tabular,
beyond a single `jq` (JSON) or `mlr` (tabular) call, OR (3) shell-boundary
quoting makes a pipeline LESS reliable than a short readable script. Prefer `jq`
for JSON and `mlr` for tabular before invoking this.

## Parallelism (GNU parallel)

`/opt/homebrew/bin/parallel`. Compute `-j` at runtime: `$(sysctl -n hw.ncpu)`
(10 cores on this machine). Never hardcode. `~/.parallel/will-cite` exists -- no
`--will-cite` flag needed.

```bash
printf '%s\n' a b c | parallel -j8 'cmd {}'           # stdin list
parallel -j8 cmd ::: a b c                             # inline args
parallel cmd ::: a b ::: 1 2                           # cartesian product
parallel -a items.txt -j8 'cmd {}'                     # from file
parallel --halt soon,fail=1 -j8 cmd ::: "${arr[@]}"    # stop on first failure
```
