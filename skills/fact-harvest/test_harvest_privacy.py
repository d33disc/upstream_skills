"""Invariants for the refuse-only privacy scan (`bin/harvest_privacy.py`).

The scan is the deterministic floor under the harvest's LLM judgment, so its failure
modes are asymmetric and both are pinned here:

  FALSE NEGATIVE  a real identifier reaches a git-tracked note -> the leak the scan exists
                  to stop.
  FALSE POSITIVE  benign atoms get refused -> Chris learns to override the scan, and an
                  override reflex disarms the true positives too. Measured, not assumed:
                  the first cut refused 493/2133 = 23.1% of the already-admitted corpus
                  (domain rules -- estate, severance, any dollar amount), which is the
                  same order that retired the v2.25 name-floor at 30.3%.

The benign cases below are REAL atoms already committed and gate-green. If a future rule
change refuses one of them, that change is wrong.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import harvest_privacy as hp  # noqa: E402  (after sys.path patch)


class TestRefusesRealSecrets(unittest.TestCase):
    """True positives -- shapes that are secret by FORM, not by topic."""

    def test_ssn_shape(self) -> None:
        self.assertTrue(hp.refuses("his ssn is 123-45-6789", terms=[]))

    def test_identified_account_number(self) -> None:
        self.assertTrue(hp.refuses("policy number 8412 4862 9931 lapsed", terms=[]))

    def test_card_number(self) -> None:
        self.assertTrue(hp.refuses("card 4111 1111 1111 1111 was declined", terms=[]))

    def test_credential_words(self) -> None:
        for text in (
            "the api_key is in 1password",
            "seed phrase written down",
            "client_secret rotated",
        ):
            with self.subTest(text=text):
                self.assertTrue(hp.refuses(text, terms=[]))

    def test_ein_is_caught(self) -> None:
        """A real one already in the corpus -- SBIR application under EIN 36-4871243."""
        self.assertTrue(
            hp.refuses("delivered an SBIR application under EIN 36-4871243", terms=[])
        )


class TestDoesNotRefuseBenign(unittest.TestCase):
    """False positives. Every string here is drawn from a committed, gate-green atom."""

    BENIGN = (
        "received [[273-high-st-medford-ma]] via quitclaim grant as a Trustee",
        "bought the April 2024 trip villa rental, $4,889.25 for 7 nights",
        "said the original severance offer from [[mango]] was a six-month severance",
        "based-in Census Tract 3392, GEOID 25017339200",
        "authored [[calibration-scorecard]] published 2026-06-18 at bigbio.ai/research",
        "worked-at [[niimbl]] as PI/PD from 2022-12",
    )

    def test_benign_atoms_pass(self) -> None:
        for text in self.BENIGN:
            with self.subTest(text=text[:40]):
                self.assertFalse(
                    hp.refuses(text, terms=[]), f"false positive: {text!r}"
                )

    def test_topic_alone_never_refuses(self) -> None:
        """Subject matter is not secrecy. A trust existing is a fact; its number is not."""
        self.assertFalse(hp.refuses("the trust names three beneficiaries", terms=[]))
        self.assertFalse(hp.refuses("litigation settled in probate", terms=[]))

    def test_word_boundaries_on_id_context(self) -> None:
        """`card` must not match inside `scorecard` -- that bug cost 13 false positives."""
        self.assertFalse(hp.refuses("the 2026-06-18 scorecard was published", terms=[]))


class TestAtomMetadataIsNotContent(unittest.TestCase):
    """The engine's own syntax is not something a human said."""

    def test_block_id_is_not_scanned(self) -> None:
        """`^f-20260622-7301` is an engine id; scanning it flagged every atom."""
        self.assertFalse(
            hp.refuses("- [[chris-davis]] said hello. ^f-20260622-7301", terms=[])
        )


class TestContract(unittest.TestCase):
    """The scan REFUSES or is silent. It never approves."""

    def test_clean_scan_returns_empty_not_true(self) -> None:
        self.assertEqual(hp.scan("ship it", terms=[]), [])

    def test_excerpt_is_redacted(self) -> None:
        """A reason to refuse must never itself leak the secret."""
        excerpt = hp.scan("policy number 8412 4862 9931", terms=[])[0].excerpt
        self.assertIn("[REDACTED:", excerpt)
        self.assertNotIn("8412 4862 9931", excerpt)

    def test_named_terms_stay_out_of_git(self) -> None:
        """The deny-list of NAMES loads from a git-ignored path, never from this repo."""
        self.assertEqual(hp.load_terms(Path("/nonexistent/terms.txt")), [])
        self.assertNotIn(str(SKILL_ROOT), str(hp.TERMS_FILE))


if __name__ == "__main__":
    unittest.main()
