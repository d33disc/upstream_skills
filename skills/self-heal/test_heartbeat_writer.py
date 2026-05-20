#!/usr/bin/env python3
"""Tests for the self-heal heartbeat writer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.heartbeat_writer import positive_float, write_heartbeat


def test_write_heartbeat_preserves_loop_state_and_stamps_time(tmp_path: Path) -> None:
    (tmp_path / "loop_state.json").write_text(
        json.dumps({"current_company": "Acme", "current_step": 3})
    )

    write_heartbeat(tmp_path)

    heartbeat = json.loads((tmp_path / "heartbeat.json").read_text())
    assert heartbeat["current_company"] == "Acme"
    assert heartbeat["current_step"] == 3
    assert heartbeat["ts"].endswith("Z")
    assert not (tmp_path / "heartbeat.json.tmp").exists()


def test_write_heartbeat_records_warning_for_malformed_state(tmp_path: Path) -> None:
    (tmp_path / "loop_state.json").write_text("{not json")

    write_heartbeat(tmp_path)

    heartbeat = json.loads((tmp_path / "heartbeat.json").read_text())
    assert heartbeat["_warning"] == "loop_state.json unreadable"
    assert heartbeat["ts"].endswith("Z")


def test_positive_float_rejects_zero_and_negative_values() -> None:
    assert positive_float("2.5") == 2.5
    with pytest.raises(argparse.ArgumentTypeError):
        positive_float("0")
    with pytest.raises(argparse.ArgumentTypeError):
        positive_float("-1")
