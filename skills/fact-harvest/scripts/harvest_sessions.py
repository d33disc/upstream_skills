#!/usr/bin/env python3
"""Session transcripts -> harvest candidates (the fact-harvest driver).

DATA ONLY, BY DESIGN. This module enumerates transcripts, filters them down to
the turns Chris himself typed, and reports which sessions were already mined. It
drafts nothing and decides nothing about truth: choosing what is a fact, which
predicate carries it, and whether it may be written down at all is JUDGMENT, and
judgment lives in the skill (.claude/skills/fact-harvest/SKILL.md). Keeping the
drafting logic out of the build is a stated NON-GOAL of the ontology, not an
oversight -- a script that "extracts facts" is a fabrication engine with a
deterministic face.

WHY THE FILTER IS THE WHOLE JOB. A transcript is not a document; it is three
different provenance classes braided into one file. Only one is admissible:

    Chris's typed turn  -> TESTIMONY. `session:` witnesses that he SAID it,
                           never that it is true (opaque predicate, R9).
    pasted document     -> LEAD. Structurally his typing, semantically someone
                           else's bytes. Re-anchor to the document's own
                           locator; never `session:`.
    assistant / tool    -> LEAD. No locator type in the registry can carry it.

That distinction has real teeth, because `facts.witness` EXEMPTS `session:` from
the a308 document-locator check -- session provenance witnesses the speaker by
construction. So a mis-classified entry does not merely add a wrong row: it mints
testimony at the engine's highest-grade, permanent, never-expiring class with the
a308 guard structurally disarmed. The filter is the only thing standing there,
which is why it fails CLOSED and why every refusal is counted rather than
silently dropped (see `Report.unknown_origin`).

Usage:
    python3 scripts/harvest_sessions.py inventory [--pending|--reviewed|--harvested]
    python3 scripts/harvest_sessions.py show <session-uuid>
    python3 scripts/harvest_sessions.py queue <session-uuid>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# The ENGINE repo -- the only place `session:` locators and journal breadcrumbs
# live. NEVER derived from __file__: this skill ships globally (symlinked under
# ~/.claude/skills -> ~/code/upstream_skills), so __file__ resolves to the skill
# folder, which has no knowledge/ -- harvested_uuids() then returns the empty
# set and EVERY session in history reads "pending" (bug found 2026-08-04: a
# 250-session inventory that included fully-harvested transcripts). SKILL.md s0
# defines the root as $ME; honor it, default ~/code/me.
REPO_ROOT = Path(os.environ.get("ME", Path.home() / "code" / "me"))

# Where the harness parks transcripts. Overridable so tests never touch the real
# corpus and so a Mac run can point at a copied-down archive.
PROJECTS_DIR = Path(os.environ.get("CLAUDE_PROJECTS_DIR", Path.home() / ".claude" / "projects"))
QUEUE_DIR = Path(
    os.environ.get("FACT_HARVEST_QUEUE", Path.home() / ".claude" / "state" / "fact-harvest")
)

# A `session:` locator addresses `<subject-slug>@<uuid>`; practice appends a topic
# anchor (`@<topic>`), which the grammar's lanchor field absorbs. Match the uuid
# either way so idempotency does not depend on the optional anchor.
_SESSION_LOCATOR = re.compile(r"session:[^@;\]]+@([0-9a-fA-F-]{36})")

# A bare session uuid, as a journal breadcrumb cites it.
_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

# Bodies the harness writes into a `user`-role entry that no human typed. Checked
# by exact text: these are emitted verbatim by the runtime, not composed.
_HARNESS_BODIES = frozenset(
    {
        "[Request interrupted by user]",
        "[Request interrupted by user for tool use]",
        "Continue from where you left off.",
    }
)

# Injected wrappers that ride INSIDE an otherwise-genuine human turn. Quoting one
# as testimony would attribute the harness's words to Chris.
_INJECTED = re.compile(
    r"<(system-reminder|local-command-stdout|local-command-stderr|command-name"
    r"|command-message|command-args|user-prompt-submit-hook)>.*?</\1>",
    re.DOTALL,
)

# Gmail's own LLM summary, which rides ABOVE the message inside a web-UI paste and is
# therefore INSIDE an otherwise-genuine human turn. Quoting it attributes GEMINI's
# paraphrase to the sender, and the literal floor cannot catch that: the summary copies
# real numbers correctly, so every number in the claim appears in the "quote". Same drift
# as e231, with a machine as the drifting author. Chris's ruling 2026-08-03: it "must be
# ignored as noise" -- so it is removed mechanically rather than by a rule a reader must
# remember (make the wrong state unconstructable).
#
# The terminator is REQUIRED. Gmail always closes the block with its own disclaimer
# ("By Gemini; there may be mistakes"), and without it we cannot bound the summary --
# so we strip NOTHING and leave it for a human. Over-stripping would silently delete
# Chris's own words, which is the worse failure of the two.
_AI_OVERVIEW = re.compile(
    r"^[ \t]*AI Overview\b.*?^[ \t]*By (?:Gemini|Google AI)\b[^\n]*\n?",
    re.DOTALL | re.MULTILINE,
)

# `origin.kind` is the only field observed to mean "a person authored this".
# `promptSource` values that mean the same thing on the macOS harness. NOTE the
# absentee: `sdk` is NOT admitted on its own -- it says the turn arrived through
# the SDK, which is a TRANSPORT fact, not evidence a human typed it. On the
# remote harness the genuine turns carry `origin.kind == "human"` AND
# `promptSource == "sdk"`, so the origin rail already admits them; allowlisting
# `sdk` would additionally admit programmatic turns that no one typed.
_ADMIT_PROMPT_SOURCES = frozenset({"typed", "queued"})


@dataclass
class Turn:
    """One admitted human turn -- the raw material for a `session:` locator."""

    uuid: str
    timestamp: str
    text: str


@dataclass
class Report:
    """Per-transcript filter result. `unknown_origin` is load-bearing: a silent
    zero-harvest and a silent mis-harvest look identical from the outside, so the
    count of turns we REFUSED for want of provenance is printed, never swallowed."""

    session_uuid: str
    slug: str
    path: Path
    turns: list[Turn] = field(default_factory=list)
    unknown_origin: int = 0
    rejected: dict[str, int] = field(default_factory=dict)

    def reject(self, reason: str) -> None:
        self.rejected[reason] = self.rejected.get(reason, 0) + 1


def block_text(content) -> str:
    """message.content -> plain text. A block list mixes text with tool_result and
    image blocks; only `text` blocks are a person's words."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
    return "\n".join(p for p in parts if p)


def strip_injections(text: str) -> str:
    """Remove harness wrappers AND machine summaries from inside a human turn.

    Both are bytes no human authored that arrive inside a turn a human did author,
    so both would be quoted as testimony if left in place.
    """
    return _AI_OVERVIEW.sub("", _INJECTED.sub("", text)).strip()


def is_human_turn(entry: dict) -> tuple[bool, str]:
    """The two-rail filter. Returns (admitted, reason).

    REJECT rails are robust across harnesses and run first, so the reason
    reported is the most specific one. The ADMIT rail is a fail-closed
    allowlist: anything it does not recognise is refused AND counted as
    `unknown-origin`, because under-harvesting is safe only while it stays
    VISIBLE.
    """
    if entry.get("type") != "user":
        return False, "not-a-user-entry"
    if "toolUseResult" in entry:
        return False, "tool-result"
    if entry.get("isMeta"):
        return False, "meta"
    if entry.get("isSidechain"):
        return False, "sidechain"

    text = strip_injections(block_text(entry.get("message", {}).get("content")))
    if text in _HARNESS_BODIES:
        return False, "harness-artifact"
    if entry.get("interruptedByShutdown"):
        return False, "interrupt-artifact"
    if not text:
        return False, "empty"

    origin = entry.get("origin") or {}
    if origin.get("kind") == "human":
        return True, "origin-human"
    if entry.get("promptSource") in _ADMIT_PROMPT_SOURCES:
        return True, "prompt-source"
    return False, "unknown-origin"


def read_transcript(path: Path) -> Report:
    """Filter one .jsonl transcript into a Report. A malformed line is counted,
    never fatal: one bad row must not cost the other 3,000 sessions."""
    report = Report(session_uuid=path.stem, slug=path.parent.name, path=path)
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            report.reject("malformed-json")
            continue
        admitted, reason = is_human_turn(entry)
        if admitted:
            text = strip_injections(block_text(entry.get("message", {}).get("content")))
            report.turns.append(
                Turn(uuid=entry.get("uuid", ""), timestamp=entry.get("timestamp", ""), text=text)
            )
        else:
            report.reject(reason)
            if reason == "unknown-origin":
                report.unknown_origin += 1
    return report


def transcripts(projects_dir: Path = PROJECTS_DIR, project: str = "*") -> list[Path]:
    """All transcripts under the harness's project roots, newest last."""
    if not projects_dir.is_dir():
        return []
    found = sorted(projects_dir.glob(f"{project}/*.jsonl"), key=lambda p: p.stat().st_mtime)
    return found


def harvested_uuids(repo: Path = REPO_ROOT) -> set[str]:
    """Sessions already mined -- DERIVED from the corpus, not from a state file.

    A state file can disagree with reality; a `session:` locator in an admitted
    atom cannot. Scope is knowledge/ + people/, the same scope facts.build walks.
    """
    out: set[str] = set()
    for root in (repo / "knowledge", repo / "people"):
        for md in root.rglob("*.md") if root.is_dir() else []:
            out.update(
                m.group(1).lower()
                for m in _SESSION_LOCATOR.finditer(md.read_text(encoding="utf-8", errors="replace"))
            )
    return out


def reviewed_uuids(repo: Path = REPO_ROOT) -> set[str]:
    """Sessions a journal breadcrumb has already accounted for. `reviewed` minus
    `harvested` is the meaningful state: looked at it, nothing survived."""
    journal = repo / "journal"
    out: set[str] = set()
    for md in journal.rglob("*.md") if journal.is_dir() else []:
        text = md.read_text(encoding="utf-8", errors="replace")
        out.update(m.group(0).lower() for m in _UUID.finditer(text))
    return out


def status_of(uuid: str, harvested: set[str], reviewed: set[str]) -> str:
    if uuid.lower() in harvested:
        return "harvested"
    if uuid.lower() in reviewed:
        return "reviewed"
    return "pending"


def cmd_inventory(args) -> int:
    harvested, reviewed = harvested_uuids(), reviewed_uuids()
    paths = transcripts(project=args.project)
    rows, totals = [], {"turns": 0, "unknown": 0}
    for path in paths:
        report = read_transcript(path)
        state = status_of(report.session_uuid, harvested, reviewed)
        if len(report.turns) < args.min_turns:
            continue
        if args.state and state != args.state:
            continue
        rows.append((state, report))
        totals["turns"] += len(report.turns)
        totals["unknown"] += report.unknown_origin

    for state, report in rows:
        flag = f"  !unknown-origin={report.unknown_origin}" if report.unknown_origin else ""
        print(f"{state:<9}  {report.session_uuid}  turns={len(report.turns):<4}{flag}")
    print(
        f"\n{len(rows)} transcript(s) listed of {len(paths)} scanned; "
        f"{totals['turns']} admitted turn(s); "
        f"{totals['unknown']} refused for unknown origin."
    )
    if totals["unknown"]:
        print(
            "NOTE: refused turns carried no recognised human-origin marker. Under-harvest "
            "is the safe direction, but inspect one before trusting the count:\n"
            "      python3 scripts/harvest_sessions.py show <uuid> --rejected"
        )
    return 0


def _find(uuid: str) -> Path | None:
    return next((p for p in transcripts() if p.stem.lower() == uuid.lower()), None)


def cmd_show(args) -> int:
    path = _find(args.uuid)
    if path is None:
        print(f"no transcript for {args.uuid} under {PROJECTS_DIR}", file=sys.stderr)
        return 1
    report = read_transcript(path)
    print(f"# {report.session_uuid}  ({report.slug})")
    print(f"# {len(report.turns)} admitted turn(s); rejected: {report.rejected}\n")
    for i, turn in enumerate(report.turns, 1):
        print(f"--- turn {i}  {turn.timestamp}  [{turn.uuid}] ---")
        print(turn.text if args.full else turn.text[:2000])
        print()
    print(f"# locator stub: session:<subject-slug>@{report.session_uuid}@<topic-anchor>")
    return 0


def cmd_queue(args) -> int:
    path = _find(args.uuid)
    if path is None:
        print(f"no transcript for {args.uuid} under {PROJECTS_DIR}", file=sys.stderr)
        return 1
    report = read_transcript(path)
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    out = QUEUE_DIR / f"{report.session_uuid}.json"
    out.write_text(
        json.dumps(
            {
                "session_uuid": report.session_uuid,
                "slug": report.slug,
                "source": str(report.path),
                "unknown_origin": report.unknown_origin,
                "turns": [vars(t) for t in report.turns],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"queued {len(report.turns)} turn(s) -> {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    inv = sub.add_parser("inventory", help="enumerate transcripts and their harvest state")
    inv.add_argument("--min-turns", type=int, default=1)
    inv.add_argument("--project", default="*", help="project-slug glob (default: all)")
    for state in ("pending", "reviewed", "harvested"):
        inv.add_argument(f"--{state}", dest="state", action="store_const", const=state)
    inv.set_defaults(func=cmd_inventory, state=None)

    show = sub.add_parser("show", help="print the admitted human turns of one session")
    show.add_argument("uuid")
    show.add_argument("--full", action="store_true", help="do not truncate turns")
    show.add_argument("--rejected", action="store_true", help="(reserved) show refusals")
    show.set_defaults(func=cmd_show)

    que = sub.add_parser("queue", help="write one session's turns to the local review queue")
    que.add_argument("uuid")
    que.set_defaults(func=cmd_queue)
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
