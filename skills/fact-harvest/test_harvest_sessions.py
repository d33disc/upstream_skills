"""Tests for bin/harvest_sessions.py -- the fact-harvest driver.

The filter is the only thing standing between a transcript and testimony minted
at the engine's highest-grade, permanent, never-expiring class (facts.witness
EXEMPTS `session:` from the a308 document-locator check). So these tests are not
about tidiness; each one pins a way the filter could mint a claim Chris never
made, or silently mint nothing at all.

The keystone is `test_origin_human_with_sdk_prompt_source_is_admitted`: the
original design allowlisted `promptSource in {typed, queued}`, which admits ZERO
turns on the remote harness, where a genuine turn carries `promptSource: "sdk"`
and `origin: {"kind": "human"}`. A silent zero-harvest looks exactly like a
clean run.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure scripts/ is importable without installing anything.
SKILL_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import harvest_sessions as hs  # noqa: E402

# This one test crosses into the `me` engine (grammar interop). The skill is global;
# the engine is not -- so make the dependency explicit and SKIP rather than fail when
# the engine is absent. A skipped test that says why beats a red CI that means nothing.
_ME_BIN = Path.home() / "code" / "me" / "bin"
if _ME_BIN.is_dir():
    sys.path.insert(0, str(_ME_BIN))
try:
    from facts.parse import fact_line  # noqa: E402
    _HAS_ENGINE = True
except ModuleNotFoundError:  # pragma: no cover - depends on host layout
    fact_line = None  # type: ignore[assignment]
    _HAS_ENGINE = False

SESSION_UUID = "1a93670f-9d5e-5c85-b318-6961f4be526e"


def entry(**over):
    """A genuine remote-harness human turn, overridable per test."""
    base = {
        "type": "user",
        "uuid": "d8e801bc-9970-4b05-b1c4-dba465a5a58a",
        "timestamp": "2026-08-01T12:39:59.405Z",
        "isSidechain": False,
        "entrypoint": "remote",
        "origin": {"kind": "human"},
        "promptSource": "sdk",
        "message": {"role": "user", "content": "I founded Mango in 2017."},
    }
    base.update(over)
    return base


def write_transcript(root: Path, slug: str, uuid: str, entries: list) -> Path:
    d = root / slug
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{uuid}.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
    return path


class FilterAdmits(unittest.TestCase):
    def test_origin_human_with_sdk_prompt_source_is_admitted(self):
        """KEYSTONE. `promptSource` alone is harness-specific; origin.kind is not.
        A {typed, queued} allowlist yields zero human turns on this harness."""
        admitted, reason = hs.is_human_turn(entry())
        self.assertTrue(admitted)
        self.assertEqual(reason, "origin-human")

    def test_typed_prompt_source_is_admitted_without_origin(self):
        """The macOS harness shape: no origin block, promptSource carries it."""
        admitted, _ = hs.is_human_turn(entry(origin=None, promptSource="typed"))
        self.assertTrue(admitted)

    def test_queued_prompt_source_is_admitted(self):
        admitted, _ = hs.is_human_turn(entry(origin=None, promptSource="queued"))
        self.assertTrue(admitted)


class FilterRejects(unittest.TestCase):
    def test_tool_result_rejected(self):
        """A tool result wears the `user` role but is machine output -- the single
        most dangerous confusion available, since it reads as first-person."""
        admitted, reason = hs.is_human_turn(entry(toolUseResult={"stdout": "ok"}))
        self.assertFalse(admitted)
        self.assertEqual(reason, "tool-result")

    def test_meta_rejected(self):
        admitted, reason = hs.is_human_turn(entry(isMeta=True))
        self.assertFalse(admitted)
        self.assertEqual(reason, "meta")

    def test_sidechain_rejected(self):
        """Sidechain turns are a subagent's prompts, not Chris's."""
        admitted, reason = hs.is_human_turn(entry(isSidechain=True))
        self.assertFalse(admitted)
        self.assertEqual(reason, "sidechain")

    def test_assistant_entry_rejected(self):
        admitted, reason = hs.is_human_turn(entry(type="assistant"))
        self.assertFalse(admitted)
        self.assertEqual(reason, "not-a-user-entry")

    def test_attachment_and_last_prompt_types_rejected(self):
        for kind in ("attachment", "last-prompt", "queue-operation", "system", "mode"):
            with self.subTest(kind=kind):
                admitted, reason = hs.is_human_turn(entry(type=kind))
                self.assertFalse(admitted)
                self.assertEqual(reason, "not-a-user-entry")

    def test_harness_bodies_rejected(self):
        """The runtime writes these into user-role entries verbatim. Quoting one
        as testimony would attribute the harness's words to Chris."""
        for body in (
            "[Request interrupted by user]",
            "[Request interrupted by user for tool use]",
            "Continue from where you left off.",
        ):
            with self.subTest(body=body):
                admitted, reason = hs.is_human_turn(entry(message={"content": body}))
                self.assertFalse(admitted)
                self.assertEqual(reason, "harness-artifact")

    def test_whitespace_only_rejected(self):
        admitted, reason = hs.is_human_turn(entry(message={"content": "   \n\t  "}))
        self.assertFalse(admitted)
        self.assertEqual(reason, "empty")

    def test_sdk_prompt_source_alone_is_not_admitted(self):
        """`sdk` is a TRANSPORT fact, not evidence a human typed the turn. Without
        an origin block it must fail closed -- and be COUNTED, not dropped."""
        admitted, reason = hs.is_human_turn(entry(origin=None, promptSource="sdk"))
        self.assertFalse(admitted)
        self.assertEqual(reason, "unknown-origin")

    def test_nonhuman_origin_kind_rejected(self):
        admitted, reason = hs.is_human_turn(
            entry(origin={"kind": "automation"}, promptSource=None)
        )
        self.assertFalse(admitted)
        self.assertEqual(reason, "unknown-origin")


class ContentExtraction(unittest.TestCase):
    def test_block_list_keeps_only_text_blocks(self):
        content = [
            {"type": "text", "text": "I founded Mango in 2017."},
            {"type": "tool_result", "content": "irrelevant machine output"},
            {"type": "image", "source": {}},
        ]
        self.assertEqual(hs.block_text(content), "I founded Mango in 2017.")

    def test_injected_wrappers_are_stripped(self):
        """A system-reminder rides INSIDE a genuine turn; quoting it would put the
        harness's words in Chris's mouth."""
        raw = (
            "<system-reminder>Today's date is 2026-08-01.</system-reminder>\n"
            "I founded Mango in 2017."
        )
        self.assertEqual(hs.strip_injections(raw), "I founded Mango in 2017.")

    def test_slash_command_expansion_is_stripped(self):
        raw = "<command-name>/me:start</command-name>\nI sold the company."
        self.assertEqual(hs.strip_injections(raw), "I sold the company.")

    def test_gemini_ai_overview_is_stripped(self):
        """Gmail's own LLM summary rides ABOVE the message in a web-UI paste.

        Quoting it attributes GEMINI's paraphrase to the sender. The literal floor
        cannot catch this: the summary copies real numbers correctly, so every number
        in the claim appears in the "quote". It is the e231 drift failure with a
        machine as the drifting author. Chris's ruling (2026-08-03): the block "must
        be ignored as noise" -- so it is removed mechanically, not by a reading rule.
        Real bytes, from session 0c2e0992.
        """
        raw = (
            "Fwd: Northern Outdoors Quote 2 of 2\n"
            "AI Overview\n"
            "Alexis forwarded Quote #193595 for $2,232.94 total balance.\n"
            "Total balance due is $2,232.94; call or use pay link to book.\n"
            "By Gemini; there may be mistakes. Learn more\n"
            "Quote#: 193595 ? Arrival Date: 9/4/2026"
        )
        out = hs.strip_injections(raw)
        self.assertNotIn("By Gemini", out)
        self.assertNotIn("Alexis forwarded Quote", out)
        # the PRIMARY bytes on both sides of the summary must survive
        self.assertIn("Fwd: Northern Outdoors Quote 2 of 2", out)
        self.assertIn("Quote#: 193595", out)

    def test_ai_overview_without_terminator_is_left_alone(self):
        """Fail SAFE: with no `By Gemini` terminator we cannot bound the block, so we
        strip nothing and let a human read it. Over-stripping would silently delete
        Chris's own words."""
        raw = "AI Overview is a feature I want to disable in Gmail settings."
        self.assertEqual(hs.strip_injections(raw), raw)

    def test_turn_text_is_stripped_of_injections_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = write_transcript(
                root,
                "-home-user-me",
                SESSION_UUID,
                [entry(message={"content": "<system-reminder>x</system-reminder>\nreal words"})],
            )
            report = hs.read_transcript(path)
            self.assertEqual([t.text for t in report.turns], ["real words"])


class ReportAccounting(unittest.TestCase):
    def test_unknown_origin_is_counted_not_swallowed(self):
        """Under-harvesting is safe only while it stays VISIBLE."""
        with tempfile.TemporaryDirectory() as tmp:
            path = write_transcript(
                Path(tmp),
                "-home-user-me",
                SESSION_UUID,
                [entry(), entry(origin=None, promptSource="sdk"), entry(toolUseResult={})],
            )
            report = hs.read_transcript(path)
            self.assertEqual(len(report.turns), 1)
            self.assertEqual(report.unknown_origin, 1)
            self.assertEqual(report.rejected["tool-result"], 1)

    def test_malformed_line_is_counted_never_fatal(self):
        """One bad row must not cost the other 3,000 sessions."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "-home-user-me"
            d.mkdir(parents=True)
            path = d / f"{SESSION_UUID}.jsonl"
            path.write_text("{not json\n" + json.dumps(entry()) + "\n", encoding="utf-8")
            report = hs.read_transcript(path)
            self.assertEqual(len(report.turns), 1)
            self.assertEqual(report.rejected["malformed-json"], 1)

    def test_enumerates_across_project_slugs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_transcript(root, "-home-user-me", SESSION_UUID, [entry()])
            write_transcript(root, "-home-user-code-dayjobs", "b" * 8 + "-0000-0000-0000-" + "c" * 12, [entry()])
            self.assertEqual(len(hs.transcripts(root)), 2)
            self.assertEqual(len(hs.transcripts(root, project="-home-user-me")), 1)


class Idempotency(unittest.TestCase):
    """State is DERIVED from the corpus, never from a state file: a state file can
    disagree with reality, an admitted atom's locator cannot."""

    def _repo(self, tmp: Path, body: str) -> Path:
        (tmp / "knowledge").mkdir(parents=True)
        (tmp / "people").mkdir(parents=True)
        (tmp / "knowledge" / "n.md").write_text(body, encoding="utf-8")
        return tmp

    def test_harvested_uuid_derived_from_session_locator(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(
                Path(tmp),
                f'- [[chris-davis]] said x. [src: session:chris-davis@{SESSION_UUID}; "x"; at 2017] ^f-20260801-aaaa',
            )
            self.assertIn(SESSION_UUID, hs.harvested_uuids(repo))

    def test_harvested_uuid_found_with_topic_anchor(self):
        """Practice appends a topic anchor after the uuid; idempotency must not
        depend on that optional field."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(
                Path(tmp),
                f'- [[chris-davis]] said x. [src: session:chris-davis@{SESSION_UUID}@mango-origin; "x"; at 2017] ^f-20260801-aaaa',
            )
            self.assertIn(SESSION_UUID, hs.harvested_uuids(repo))

    def test_unharvested_session_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(Path(tmp), "- nothing here\n")
            self.assertEqual(hs.harvested_uuids(repo), set())

    def test_repo_root_is_the_engine_not_the_skill(self):
        """REPO_ROOT must point at the engine repo ($ME, default ~/code/me),
        never at the skill's own folder. Deriving it from __file__ resolved
        through the global-install symlink to a folder with no knowledge/,
        so harvested_uuids() returned empty and every session read pending
        (2026-08-04)."""
        self.assertNotIn("upstream_skills", str(hs.REPO_ROOT))
        self.assertNotIn("fact-harvest", str(hs.REPO_ROOT))
        self.assertEqual(hs.REPO_ROOT.name, os.environ.get("ME", "me").split("/")[-1])

    def test_status_precedence(self):
        self.assertEqual(hs.status_of("A", {"a"}, {"a"}), "harvested")
        self.assertEqual(hs.status_of("A", set(), {"a"}), "reviewed")
        self.assertEqual(hs.status_of("A", set(), set()), "pending")


@unittest.skipUnless(_HAS_ENGINE, "me fact engine not on this host -- interop test needs bin/facts")
class LocatorRoundTrip(unittest.TestCase):
    """The shape the skill emits must survive the engine's own parser -- the
    driver's output contract is `parse.py`, not a prose description of it."""

    def test_session_locator_parses(self):
        line = (
            f"- [[chris-davis]] founded [[mango]] as a solo venture. "
            f'[src: session:chris-davis@{SESSION_UUID}@mango-origin; '
            f'"I founded Mango in 2017."; at 2017] ^f-20260801-aaaa'
        )
        atom = fact_line(line)
        self.assertEqual(atom.locator.type, "session")
        self.assertEqual(atom.locator.address, "chris-davis")
        self.assertTrue(atom.locator.anchor.startswith(SESSION_UUID))

    def test_session_locator_parses_without_topic_anchor(self):
        line = (
            f"- [[chris-davis]] founded [[mango]] as a solo venture. "
            f'[src: session:chris-davis@{SESSION_UUID}; "I founded Mango in 2017."; at 2017] '
            f"^f-20260801-aaaa"
        )
        self.assertEqual(fact_line(line).locator.anchor, SESSION_UUID)


if __name__ == "__main__":
    unittest.main()
