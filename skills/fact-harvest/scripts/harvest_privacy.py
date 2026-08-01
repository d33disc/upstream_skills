"""Refuse-only privacy scan -- the deterministic net under the harvest's judgment.

WHY THIS EXISTS. The pre-commit wall guard is real (verified 2026-08-01: it blocks a
staged clinical term) but NARROW -- a clinical/crisis deny-list. For estate, financial,
third-party and kid-related material there was no deterministic backstop at all, leaving
an LLM's judgment as the only thing between a transcript and a repo that pushes to
GitHub. Cross-family adversary (DeepSeek V4-pro, 2026-08-01) rated that Critical.

WHAT IT IS. A scan that runs between the local candidate queue and the write, and can
only ever REFUSE. It never approves, never upgrades, never overrides a human SKIP --
the same shape as the law's reject-only semantic judge (A2 / R6'): a judge may reject,
never rescue. A clean scan therefore means "found nothing", NEVER "safe to write".

THE PATTERN/SECRET PROBLEM. A search pattern for a secret IS the secret: a deny-list
naming Chris's kids, his counsel, or an account number would itself leak the moment it
was committed. So this module ships ONLY structural shapes (things whose FORM is
recognisable -- account digits, SSNs, currency) and loads named terms from a
git-ignored local file, exactly as the wall guard keeps its own list uncommitted.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import NamedTuple

# Named terms live OUTSIDE git. Same rationale as .git/hooks/pre-commit's deny-list.
TERMS_FILE = Path(
    os.environ.get(
        "HARVEST_PRIVACY_TERMS",
        Path.home() / ".claude" / "state" / "harvest-privacy-terms.txt",
    )
)


class Hit(NamedTuple):
    """One reason to refuse. `excerpt` is redacted -- never echo the raw match."""

    rule: str
    excerpt: str

    def __str__(self) -> str:
        return f"{self.rule}: {self.excerpt}"


# CALIBRATION (2026-08-01, and the reason these rules look narrow).
# A first cut carried DOMAIN rules -- estate-instrument, legal-strategy, currency-amount --
# and refused 493/2133 = 23.1% of the ALREADY-ADMITTED, gate-green corpus: a quitclaim
# deed, a $4,889.25 villa rental, a six-month severance. Those are facts Chris tracks on
# purpose. The rules were detecting SUBJECT, not SECRECY, and the same measurement is what
# retired the v2.25 name-floor (609/2008 = 30.3%).
#
# A scan that cries wolf on a quarter of the corpus trains an override reflex, and an
# override reflex disarms the true positives too -- strictly worse than no scan. So:
# structural shape AND identifier context. Topic alone never refuses.
#
# `\b(?:\d[ -]?){9,}\b` alone was worse than useless: it matched the engine's OWN block
# ids (`^f-20260622-7301`) and public census GEOIDs, so it would have flagged every atom.
# \b on BOTH sides is load-bearing: without it `card` matched inside "scorecard" and
# `ein` inside any German loanword, which is what the residual 37 false positives were.
_ID_CONTEXT = (
    r"\b(?:account|acct|policy|member|routing|card|iban|swift|ssn|"
    r"social security|tax ?id|ein|licen[cs]e|passport)\b"
)

_STRUCTURAL: dict[str, re.Pattern[str]] = {
    # A long digit run only counts when an identifier word sits next to it.
    "identified-account-number": re.compile(
        rf"{_ID_CONTEXT}\D{{0,20}}\b(?:\d[ -]?){{6,}}\b|\b(?:\d[ -]?){{6,}}\D{{0,12}}{_ID_CONTEXT}",
        re.IGNORECASE,
    ),
    "ssn-shape": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "routing-or-card": re.compile(r"\b(?:\d{4}[ -]){3}\d{4}\b"),
    # Credentials are secret by form regardless of subject matter.
    "credential-shape": re.compile(
        r"\b(password|passphrase|api[_ -]?key|secret[_ -]?key|bearer token|"
        r"private[_ -]?key|seed phrase|client[_ -]?secret)\b",
        re.IGNORECASE,
    ),
}

# Atom metadata is engine syntax, never content: the block id and the locator address
# are not things a human said, so they must not be scanned.
_ATOM_META = re.compile(r"\^f-\d{8}-[0-9a-f]{4}|\[src:[^;]*;")


def _redact(text: str, start: int, end: int, width: int = 24) -> str:
    """Show enough context to judge, never enough to leak. The match itself is masked."""
    left = text[max(0, start - width) : start].replace("\n", " ")
    right = text[end : end + width].replace("\n", " ")
    return f"...{left}[REDACTED:{end - start}ch]{right}..."


def load_terms(path: Path = TERMS_FILE) -> list[str]:
    """Named sensitive terms from the git-ignored local file. Missing file = no terms."""
    if not path.exists():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _scan_terms(text: str, terms: list[str]) -> list[Hit]:
    """Named-term pass. Terms are matched case-insensitively as whole words."""
    hits = []
    for term in terms:
        m = re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE)
        if m:
            hits.append(Hit("named-term", _redact(text, m.start(), m.end())))
    return hits


def scan(text: str, terms: list[str] | None = None) -> list[Hit]:
    """Every reason to refuse this text. Empty list means FOUND NOTHING, not SAFE.

    The distinction is the whole contract: this scan is a floor under human judgment,
    never a substitute for it. A caller that treats [] as approval has reintroduced
    exactly the gap the scan was built to close.
    """
    body = _ATOM_META.sub(" ", text)
    hits = [
        Hit(rule, _redact(body, m.start(), m.end()))
        for rule, pattern in _STRUCTURAL.items()
        if (m := pattern.search(body))
    ]
    return hits + _scan_terms(body, terms if terms is not None else load_terms())


def refuses(text: str, terms: list[str] | None = None) -> bool:
    """True if the text must NOT be written to a git-tracked sink."""
    return bool(scan(text, terms))
