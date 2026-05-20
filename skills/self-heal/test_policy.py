#!/usr/bin/env python3
"""Tests for executable self-heal policy helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.policy import (
    PolicyError,
    blocked_paths,
    classify_risk,
    load_policy,
    score_risk,
)


def test_load_policy_accepts_repo_with_config(tmp_path: Path) -> None:
    (tmp_path / ".self-heal.toml").write_text(
        """
[paths]
state_dir = "runs"

[budget]
max_attempts_per_bug = 2
"""
    )

    policy = load_policy(tmp_path)

    assert policy["paths"]["state_dir"] == "runs"
    assert policy["budget"]["max_attempts_per_bug"] == 2
    assert policy["pipeline"]["entry"] == "src/dd_pipeline.py"


def test_load_policy_rejects_repo_without_config_or_dd_bigbio_layout(tmp_path: Path) -> None:
    with pytest.raises(PolicyError, match="requires either"):
        load_policy(tmp_path)


def test_load_policy_rejects_unknown_config_keys(tmp_path: Path) -> None:
    (tmp_path / ".self-heal.toml").write_text(
        """
[heartbeat]
interval_seconds = 15
unknown = true
"""
    )

    with pytest.raises(PolicyError, match="unknown key"):
        load_policy(tmp_path)


def test_load_policy_rejects_invalid_heartbeat_threshold(tmp_path: Path) -> None:
    (tmp_path / ".self-heal.toml").write_text(
        """
[heartbeat]
interval_seconds = 15
alert_threshold_seconds = 10
"""
    )

    with pytest.raises(PolicyError, match="alert_threshold_seconds"):
        load_policy(tmp_path)


def test_load_policy_rejects_boolean_numeric_values(tmp_path: Path) -> None:
    (tmp_path / ".self-heal.toml").write_text(
        """
[heartbeat]
interval_seconds = true
"""
    )

    with pytest.raises(PolicyError, match="interval_seconds"):
        load_policy(tmp_path)


def test_blocked_paths_reports_builtin_and_configured_matches(tmp_path: Path) -> None:
    (tmp_path / ".self-heal.toml").write_text(
        """
[hard_blocked_paths]
extra_globs = ["generated/**"]
"""
    )
    policy = load_policy(tmp_path)

    matches = blocked_paths(
        [
            "src/dd_schemas.py",
            "generated/report.json",
            "docs/ok.md",
            "skills/self-heal/SKILL.md",
        ],
        policy,
    )

    assert [(match.path, match.pattern) for match in matches] == [
        ("src/dd_schemas.py", "src/dd_schemas.py"),
        ("generated/report.json", "generated/**"),
        ("skills/self-heal/SKILL.md", "skills/self-heal/**"),
    ]


def test_risk_score_classification() -> None:
    safe_score = score_risk(
        {
            "failing_test_exists": True,
            "pure_function": True,
            "reversible": True,
        }
    )
    hard_score = score_risk(
        {
            "hot_path": True,
            "schema_migration": True,
            "signature_change": True,
            "blast_radius": 100,
            "lines_changed": 1000,
            "recent_churn_bucket": 2,
        }
    )

    assert classify_risk(safe_score) == "safe"
    assert classify_risk(hard_score) == "hard"
    assert hard_score >= 6
