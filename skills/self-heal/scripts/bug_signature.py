#!/usr/bin/env python3
"""Canonical bug-signature function for the self-heal loop.

The signature is the hex SHA1 of a normalized JSON payload:
    {step, signal_type, normalized_pattern, claim_id}

Normalization strips ephemeral content (timestamps, tmp paths, PIDs,
memory addresses, UUIDs, hex IDs) so that retries of the same logical
bug collapse to a single signature. The signature keys the 3-attempt
budget in `reports/_runs/heal_attempts.json`; drift here would let
cosmetic differences reset the counter.

CLI:
    echo '{"step":3,"signal_type":"python_traceback",
           "raw_pattern":"...","claim_id":null}' \\
      | python3 scripts/bug_signature.py

Library:
    from scripts.bug_signature import compute_signature
    sig = compute_signature(step=3, signal_type="python_traceback",
                            raw_pattern=tb_text, claim_id=None)
"""

from __future__ import annotations

import hashlib
import json
import re
import sys

NORMALIZATION_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"/var/folders/[^\s\"']+"), "<TMP>"),
    (re.compile(r"/tmp/[^\s\"']+"), "<TMP>"),
    # ISO 8601 timestamps MUST precede the `:\d+:` line/column patterns;
    # otherwise `:\d+:` consumes the `:MM:` inside HH:MM:SS, fragmenting
    # the timestamp so this rule no longer matches and the date survives
    # as a literal divergence between retries.
    (re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"), "<TS>"),
    (re.compile(r'File "([^"]+)", line \d+'), r'File "\1", line <N>'),
    (re.compile(r":\d+:\d+:"), ":<L>:<C>:"),
    (re.compile(r":\d+:"), ":<L>:"),
    (re.compile(r"\bpid[=: ]+\d+\b", re.IGNORECASE), "pid=<PID>"),
    (re.compile(r"\[\d{2,7}\]"), "[<PID>]"),
    (re.compile(r"\b0x[0-9a-fA-F]{4,}\b"), "<ADDR>"),
    (
        re.compile(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
        ),
        "<UUID>",
    ),
    (re.compile(r"\b[0-9a-fA-F]{40}\b"), "<SHA1>"),
    (re.compile(r"\b[0-9a-fA-F]{8,12}\b"), "<HEX>"),
    (re.compile(r"[ \t]+"), " "),
]


def normalize_pattern(raw: str) -> str:
    """Strip ephemeral content from a raw error pattern.

    Rule ordering matters: longer/more-specific patterns first so they
    consume their input before the catch-all hex stripper sees it.
    """
    out = raw
    for pattern, replacement in NORMALIZATION_RULES:
        out = pattern.sub(replacement, out)
    return out.strip()


def compute_signature(
    *,
    step: int,
    signal_type: str,
    raw_pattern: str,
    claim_id: str | None = None,
) -> str:
    """Return the hex SHA1 signature for a bug.

    Inputs are JSON-serialized with sorted keys and stable separators
    so the same logical bug always produces the same digest across
    Python versions, machines, and subagent invocations.
    """
    payload = {
        "step": int(step),
        "signal_type": str(signal_type),
        "normalized_pattern": normalize_pattern(raw_pattern),
        "claim_id": claim_id if claim_id else None,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(serialized.encode("utf-8")).hexdigest()


def _cli() -> int:
    try:
        bug = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        print(f"invalid JSON on stdin: {exc}", file=sys.stderr)
        return 2
    required = {"step", "signal_type", "raw_pattern"}
    missing = required - set(bug)
    if missing:
        print(f"missing required fields: {sorted(missing)}", file=sys.stderr)
        return 2
    print(
        compute_signature(
            step=bug["step"],
            signal_type=bug["signal_type"],
            raw_pattern=bug["raw_pattern"],
            claim_id=bug.get("claim_id"),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
