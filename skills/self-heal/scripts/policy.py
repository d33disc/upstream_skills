#!/usr/bin/env python3
"""Executable policy checks for the self-heal skill."""

from __future__ import annotations

import argparse
import copy
import fnmatch
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python <3.11 fallback message
    tomllib = None  # type: ignore[assignment]


class PolicyError(Exception):
    """Raised when a self-heal policy or configuration is invalid."""


DEFAULT_POLICY: dict[str, dict[str, Any]] = {
    "paths": {
        "state_dir": "reports/_runs",
        "report_log_prefix": "SELF_HEAL_LOG",
    },
    "truth_vector": {
        "artifact": "verified.json",
        "schema_module": "src/dd_schemas.py",
    },
    "pipeline": {
        "entry": "src/dd_pipeline.py",
        "resume_flag": "--skip-to-step",
        "audit_gate": "src/dd_audit_gate.py",
    },
    "heartbeat": {
        "interval_seconds": 15,
        "alert_threshold_seconds": 45,
    },
    "budget": {
        "max_attempts_per_bug": 3,
        "max_concurrent_subagents": 5,
    },
    "hot_paths": {
        "extra_globs": ["prompts/*.tpl.md"],
    },
    "hard_blocked_paths": {
        "extra_globs": [],
    },
}

BUILTIN_HARD_BLOCKED_PATTERNS = [
    "src/dd_audit_gate.py",
    "src/dd_schemas.py",
    "skills/self-heal/**",
    "scripts/bug_signature.py",
    "scripts/heartbeat_writer.py",
    ".self-heal/**",
]


@dataclass(frozen=True)
class BlockedPath:
    """A path that matched a hard-blocked policy pattern."""

    path: str
    pattern: str


def _read_toml(path: Path) -> dict[str, Any]:
    if tomllib is None:
        raise PolicyError("Python 3.11+ is required to parse .self-heal.toml")
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PolicyError(f"cannot read {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise PolicyError(f"invalid TOML in {path}: {exc}") from exc


def _merge_policy(
    base: dict[str, dict[str, Any]], override: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    merged = copy.deepcopy(base)
    for section, values in override.items():
        if section not in merged:
            raise PolicyError(f"unknown section: {section}")
        if not isinstance(values, dict):
            raise PolicyError(f"section must be a table: {section}")
        for key, value in values.items():
            if key not in merged[section]:
                raise PolicyError(f"unknown key: {section}.{key}")
            merged[section][key] = value
    return merged


def _is_dd_bigbio_layout(repo_root: Path) -> bool:
    return repo_root.name == "dd-bigbio" or (
        (repo_root / "src/dd_pipeline.py").exists()
        and (repo_root / "src/dd_audit_gate.py").exists()
    )


def _require_type(config: dict[str, dict[str, Any]], section: str, key: str, kind: type) -> None:
    value = config[section][key]
    if not isinstance(value, kind):
        raise PolicyError(f"{section}.{key} must be {kind.__name__}")


def _require_positive_number(config: dict[str, dict[str, Any]], section: str, key: str) -> None:
    value = config[section][key]
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        raise PolicyError(f"{section}.{key} must be a positive number")


def _require_positive_int(config: dict[str, dict[str, Any]], section: str, key: str) -> None:
    value = config[section][key]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PolicyError(f"{section}.{key} must be a positive integer")


def _require_string_list(config: dict[str, dict[str, Any]], section: str, key: str) -> None:
    value = config[section][key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise PolicyError(f"{section}.{key} must be a list of strings")


def validate_policy(config: dict[str, dict[str, Any]]) -> None:
    """Validate the merged self-heal policy."""
    for section, values in DEFAULT_POLICY.items():
        if section not in config:
            raise PolicyError(f"missing section: {section}")
        for key in values:
            if key not in config[section]:
                raise PolicyError(f"missing key: {section}.{key}")

    for section in ["paths", "truth_vector", "pipeline"]:
        for key in DEFAULT_POLICY[section]:
            _require_type(config, section, key, str)

    _require_positive_number(config, "heartbeat", "interval_seconds")
    _require_positive_number(config, "heartbeat", "alert_threshold_seconds")
    if config["heartbeat"]["alert_threshold_seconds"] <= config["heartbeat"]["interval_seconds"]:
        raise PolicyError("heartbeat.alert_threshold_seconds must be greater than interval_seconds")

    _require_positive_int(config, "budget", "max_attempts_per_bug")
    _require_positive_int(config, "budget", "max_concurrent_subagents")
    _require_string_list(config, "hot_paths", "extra_globs")
    _require_string_list(config, "hard_blocked_paths", "extra_globs")


def load_policy(repo_root: Path) -> dict[str, dict[str, Any]]:
    """Load and validate self-heal policy for a host repository."""
    repo_root = repo_root.resolve()
    config_path = repo_root / ".self-heal.toml"
    if not config_path.exists() and not _is_dd_bigbio_layout(repo_root):
        raise PolicyError(
            "self-heal requires either the dd-bigbio repo or a .self-heal.toml config"
        )

    override = _read_toml(config_path) if config_path.exists() else {}
    policy = _merge_policy(DEFAULT_POLICY, override)
    validate_policy(policy)
    return policy


def get_config_value(config: dict[str, dict[str, Any]], dotted_key: str) -> Any:
    """Return a config value by section.key path."""
    try:
        section, key = dotted_key.split(".", 1)
    except ValueError as exc:
        raise PolicyError("config key must use section.key syntax") from exc
    if section not in config or key not in config[section]:
        raise PolicyError(f"unknown config key: {dotted_key}")
    return config[section][key]


def _matches(path: str, pattern: str) -> bool:
    normalized = path.strip().lstrip("./")
    return normalized == pattern or fnmatch.fnmatchcase(normalized, pattern)


def blocked_paths(paths: list[str], config: dict[str, dict[str, Any]]) -> list[BlockedPath]:
    """Return paths that match built-in or configured hard-blocked patterns."""
    patterns = BUILTIN_HARD_BLOCKED_PATTERNS + config["hard_blocked_paths"]["extra_globs"]
    matches: list[BlockedPath] = []
    for path in paths:
        normalized = path.strip().lstrip("./")
        if not normalized:
            continue
        for pattern in patterns:
            if _matches(normalized, pattern):
                matches.append(BlockedPath(normalized, pattern))
                break
    return matches


def _bool_factor(data: dict[str, Any], key: str) -> int:
    return 1 if bool(data.get(key, False)) else 0


def _positive_number(data: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise PolicyError(f"{key} must be numeric")
    return max(float(value), 0.0)


def _log10_capped(value: float, cap: float) -> float:
    if value <= 1:
        return 0.0
    return min(math.log10(value), cap)


def score_risk(data: dict[str, Any]) -> float:
    """Calculate the documented greybeard risk score."""
    uncovered = data.get("uncovered_loc_ratio", 0.5)
    if isinstance(uncovered, bool) or not isinstance(uncovered, int | float) or uncovered < 0:
        raise PolicyError("uncovered_loc_ratio must be a non-negative number")

    recent_churn = _positive_number(data, "recent_churn_bucket", 0.0)
    if recent_churn > 2:
        raise PolicyError("recent_churn_bucket must be 0, 1, or 2")

    score = (
        3 * _bool_factor(data, "hot_path")
        + 3 * _bool_factor(data, "schema_migration")
        + 2 * _bool_factor(data, "signature_change")
        + 2 * float(uncovered)
        + _log10_capped(_positive_number(data, "blast_radius", 0.0), 2)
        + _log10_capped(_positive_number(data, "lines_changed", 0.0), 3)
        + recent_churn
        - 2 * _bool_factor(data, "failing_test_exists")
        - _bool_factor(data, "pure_function")
        - _bool_factor(data, "reversible")
    )
    return round(score, 3)


def classify_risk(score: float) -> str:
    """Return safe, review, or hard for a risk score."""
    if score <= 2:
        return "safe"
    if score < 6:
        return "review"
    return "hard"


def _cmd_validate_config(args: argparse.Namespace) -> int:
    policy = load_policy(args.repo_root)
    print(f"OK state_dir={policy['paths']['state_dir']} pipeline={policy['pipeline']['entry']}")
    return 0


def _cmd_config_value(args: argparse.Namespace) -> int:
    policy = load_policy(args.repo_root)
    value = get_config_value(policy, args.key)
    if isinstance(value, list | dict):
        print(json.dumps(value, sort_keys=True))
    else:
        print(value)
    return 0


def _cmd_blocked_paths(args: argparse.Namespace) -> int:
    policy = load_policy(args.repo_root)
    paths = list(args.paths)
    if args.stdin:
        paths.extend(sys.stdin.read().splitlines())
    matches = blocked_paths(paths, policy)
    for match in matches:
        print(f"{match.path}\t{match.pattern}")
    return 1 if matches else 0


def _cmd_risk_score(args: argparse.Namespace) -> int:
    raw = args.json if args.json is not None else sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}
    score = score_risk(data)
    print(json.dumps({"score": score, "class": classify_risk(score)}, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the policy CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-config")
    validate.add_argument("--repo-root", type=Path, default=Path.cwd())
    validate.set_defaults(func=_cmd_validate_config)

    value = subparsers.add_parser("config-value")
    value.add_argument("key")
    value.add_argument("--repo-root", type=Path, default=Path.cwd())
    value.set_defaults(func=_cmd_config_value)

    blocked = subparsers.add_parser("blocked-paths")
    blocked.add_argument("paths", nargs="*")
    blocked.add_argument("--repo-root", type=Path, default=Path.cwd())
    blocked.add_argument("--stdin", action="store_true")
    blocked.set_defaults(func=_cmd_blocked_paths)

    risk = subparsers.add_parser("risk-score")
    risk.add_argument("--json", default=None)
    risk.set_defaults(func=_cmd_risk_score)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the policy CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (PolicyError, json.JSONDecodeError) as exc:
        print(f"policy error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
