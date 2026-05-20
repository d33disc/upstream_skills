#!/usr/bin/env python3
"""Tests for self-heal bug signatures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.bug_signature import compute_signature, normalize_pattern

TRACE_A = (
    'File "/tmp/abc/foo.py", line 42: KeyError at 2026-05-20T10:30:00.000Z pid=1234 0x7fff8a3c'
)
TRACE_B = (
    'File "/var/folders/xyz/foo.py", line 99: KeyError at '
    "2026-05-21T15:00:00.000Z pid=5678 0x8aaa1234"
)


def test_traceback_signature_ignores_ephemeral_fields() -> None:
    assert normalize_pattern(TRACE_A) == normalize_pattern(TRACE_B)
    assert compute_signature(
        step=3, signal_type="python_traceback", raw_pattern=TRACE_A, claim_id=None
    ) == compute_signature(
        step=3, signal_type="python_traceback", raw_pattern=TRACE_B, claim_id=None
    )


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (
            "src/app.py:12:34: RuntimeError [12345] pid:123",
            "src/app.py:98:7: RuntimeError [67890] pid=456",
        ),
        (
            "job 550e8400-e29b-41d4-a716-446655440000 sha abcdef1234567890abcdef1234567890abcdef12 token deadbeef01",
            "job f47ac10b-58cc-4372-a567-0e02b2c3d479 sha 1234567890ABCDEF1234567890ABCDEF12345678 token FACEB00C99",
        ),
        (
            "failed at 2026-05-20T10:30:00+00:00 id=aa11bb22cc",
            "failed at 2026-05-21T15:00:00-0500 id=dd33ee44ff",
        ),
    ],
)
def test_normalize_pattern_ignores_common_volatility(left: str, right: str) -> None:
    assert normalize_pattern(left) == normalize_pattern(right)


def main() -> int:
    test_traceback_signature_ignores_ephemeral_fields()
    for left, right in [
        (
            "src/app.py:12:34: RuntimeError [12345] pid:123",
            "src/app.py:98:7: RuntimeError [67890] pid=456",
        ),
        (
            "job 550e8400-e29b-41d4-a716-446655440000 sha abcdef1234567890abcdef1234567890abcdef12 token deadbeef01",
            "job f47ac10b-58cc-4372-a567-0e02b2c3d479 sha 1234567890ABCDEF1234567890ABCDEF12345678 token FACEB00C99",
        ),
        (
            "failed at 2026-05-20T10:30:00+00:00 id=aa11bb22cc",
            "failed at 2026-05-21T15:00:00-0500 id=dd33ee44ff",
        ),
    ]:
        test_normalize_pattern_ignores_common_volatility(left, right)
    print("PASS: traceback signature ignores ephemeral fields")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
