"""Configuration loading for CodePulse.

Loads [tool.codepulse] section from pyproject.toml or .codepulse.toml.
Provides defaults when config is missing.
"""

from __future__ import annotations

import importlib
import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

try:
    _toml = importlib.import_module("tomllib")
except ImportError:
    _toml = importlib.import_module("tomli")  # Python < 3.11


# Default configuration
DEFAULT_CONFIG = {
    "weights": {
        "security": 0.25,
        "complexity": 0.20,
        "testing": 0.20,
        "documentation": 0.15,
        "dependencies": 0.10,
        "structure": 0.10,
    },
    "thresholds": {
        "complexity": 10,      # cyclomatic complexity > 10 = issue
        "max_file_lines": 500,  # file length > 500 = issue
        "max_params": 7,        # function params > 7 = issue
        "min_test_ratio": 0.25, # test/source ratio threshold
    },
    "exclusions": {
        "patterns": [
            "migrations/",
            "generated/",
            "*.pb.py",
            "*.generated.py",
        ],
    },
    "output": {
        "default_format": "text",  # text | html | json
        "color_output": True,
    },
    "security": {
        "skip_test_files_for_secrets": True,
        "secret_severity_in_tests": "high",  # critical | high | medium | low
    },
}


def _find_config_file(start_path: Path) -> Path | None:
    """Find pyproject.toml or .codepulse.toml walking up from start_path."""
    for path in [start_path] + list(start_path.parents):
        for name in ("pyproject.toml", ".codepulse.toml"):
            candidate = path / name
            if candidate.exists():
                return candidate
    return None


def _load_toml_config(config_path: Path) -> dict[str, Any]:
    """Load and parse TOML config file, returning [tool.codepulse] section."""
    try:
        with open(config_path, "rb") as f:
            data = _toml.load(f)
        return data.get("tool", {}).get("codepulse", {})
    except (OSError, _toml.TOMLDecodeError):
        return {}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge two dicts, with override taking precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    """Accept the documented flat keys as well as grouped configuration."""
    normalized = config.copy()
    thresholds = dict(normalized.get("thresholds", {}))
    for key in ("complexity", "max_file_lines", "max_params", "min_test_ratio"):
        if key in normalized:
            thresholds[key] = normalized[key]
    if thresholds:
        normalized["thresholds"] = thresholds

    if "exclude_patterns" in normalized:
        exclusions = dict(normalized.get("exclusions", {}))
        exclusions["patterns"] = normalized["exclude_patterns"]
        normalized["exclusions"] = exclusions
    return normalized


def load_config(repo_path: Path | None = None) -> dict[str, Any]:
    """Load configuration from pyproject.toml or .codepulse.toml.

    Args:
        repo_path: Repository root path. Defaults to current working directory.

    Returns:
        Merged configuration dict with defaults applied.
    """
    if repo_path is None:
        repo_path = Path.cwd()

    config = deepcopy(DEFAULT_CONFIG)

    # Try to load from pyproject.toml or .codepulse.toml
    config_file = _find_config_file(Path(repo_path).resolve())
    if config_file:
        file_config = _normalize_config(_load_toml_config(config_file))
        config = _deep_merge(config, file_config)

    # Override with environment variables (for CI)
    if os.environ.get("CODEPULSE_WEIGHTS"):
        try:
            config["weights"] = json.loads(os.environ["CODEPULSE_WEIGHTS"])
        except json.JSONDecodeError:
            pass

    if os.environ.get("CODEPULSE_THRESHOLDS"):
        try:
            config["thresholds"] = json.loads(os.environ["CODEPULSE_THRESHOLDS"])
        except json.JSONDecodeError:
            pass

    return config


def get_weights(config: dict | None = None) -> dict[str, float]:
    """Get dimension weights from config."""
    if config is None:
        config = load_config()
    return config.get("weights", DEFAULT_CONFIG["weights"])


def get_thresholds(config: dict | None = None) -> dict[str, Any]:
    """Get analysis thresholds from config."""
    if config is None:
        config = load_config()
    return config.get("thresholds", DEFAULT_CONFIG["thresholds"])


def get_exclusions(config: dict | None = None) -> dict[str, list[str]]:
    """Get exclusion patterns from config."""
    if config is None:
        config = load_config()
    return config.get("exclusions", DEFAULT_CONFIG["exclusions"])


def get_security_config(config: dict | None = None) -> dict[str, Any]:
    """Get security analyzer config from config."""
    if config is None:
        config = load_config()
    return config.get("security", DEFAULT_CONFIG["security"])
