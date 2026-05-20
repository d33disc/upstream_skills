#!/usr/bin/env python3
"""Heartbeat daemon for the self-heal loop's liveness invariant.

The loop's liveness invariant requires `reports/_runs/heartbeat.json`
updated every 15s. The main Claude session is request/response and
cannot tick on a fixed cadence; this daemon does the ticking.

Separation of concerns:

- Orchestrator writes `reports/_runs/loop_state.json` whenever state
  changes (iteration, current_company, current_step,
  last_invariant_check_ts).
- This daemon reads loop_state.json every `--interval` seconds, stamps
  it with the current ISO 8601 ms UTC timestamp, and writes
  `reports/_runs/heartbeat.json` atomically (tmp + rename).
- External monitors poll heartbeat.json and alert when
  `now - ts > 45s` (3 missed ticks).

Usage:
    # Foreground, defaults
    python3 scripts/heartbeat_writer.py

    # Custom state dir / interval
    python3 scripts/heartbeat_writer.py --state-dir reports/_runs --interval 15

    # Background
    python3 scripts/heartbeat_writer.py --state-dir reports/_runs &
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def iso_now() -> str:
    """ISO 8601 with millisecond precision in UTC.

    Matches the dd-bigbio convention recorded in
    `feedback_iso_8601_ms_timestamps`.
    """
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def write_heartbeat(state_dir: Path) -> None:
    """Read loop_state.json (or empty), stamp ts, atomically write heartbeat.json."""
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "loop_state.json"
    heartbeat_file = state_dir / "heartbeat.json"

    state: dict = {}
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {"_warning": "loop_state.json unreadable"}

    state["ts"] = iso_now()

    tmp = heartbeat_file.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    tmp.replace(heartbeat_file)


def positive_float(raw: str) -> float:
    """Parse a strictly positive float for argparse."""
    try:
        value = float(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid float: {raw}") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError("value must be greater than 0")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=Path("reports/_runs"),
        help="Dir containing loop_state.json; heartbeat.json written here.",
    )
    parser.add_argument(
        "--interval",
        type=positive_float,
        default=15.0,
        help="Seconds between heartbeats (default 15).",
    )
    args = parser.parse_args()

    running = [True]

    def stop(_sig, _frame):
        running[0] = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    while running[0]:
        try:
            write_heartbeat(args.state_dir)
        except OSError as exc:
            print(f"heartbeat write failed: {exc}", file=sys.stderr)
        time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
