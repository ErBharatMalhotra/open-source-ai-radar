"""Scale configuration loader — reads config/scale.yml."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = Path(__file__).parent.parent.parent.parent / "config" / "scale.yml"


def load_scale_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or DEFAULT_CONFIG
    defaults: dict[str, Any] = {
        "tiers": {
            1: {"min_stars": 1000, "interval_hours": 24, "priority": 1},
            2: {"min_stars": 100, "interval_hours": 72, "priority": 2},
            3: {"min_stars": 10, "interval_hours": 168, "priority": 3},
            4: {"min_stars": 0, "interval_hours": 720, "priority": 4},
        },
        "batch": {"size": 700, "max_api_calls": 800, "delay_between_requests": 0.1},
        "rate_limit": {
            "hourly_budget": 1000, "safety_threshold": 0.80,
            "cooldown_on_limit": True, "persist_on_cooldown": True,
        },
        "retention": {
            "default_keep_days": 365,
            "tier_keep_days": {1: 730, 2: 365, 3: 180, 4: 90},
            "dry_run": True, "cleanup_batch_size": 10000,
        },
        "retries": {"max_attempts": 3, "backoff_base_seconds": 30,
                    "backoff_max_seconds": 600},
        "monitoring": {"alert_on_failure": True, "log_api_usage": True,
                       "status_page_repo_limit": 100},
    }
    if not config_path.exists():
        logger.warning(f"Scale config not found at {config_path}, using defaults")
        return defaults
    try:
        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        config = defaults.copy()
        for key in raw:
            if key in config and isinstance(config[key], dict):
                config[key] = {**config[key], **raw[key]}
            else:
                config[key] = raw[key]
        if "tiers" in config:
            config["tiers"] = {int(k): v for k, v in config["tiers"].items()}
        return config
    except Exception as e:
        logger.error(f"Failed to load scale config: {e}")
        return defaults


def get_tier_for_stars(stars: int, config: dict[str, Any] | None = None) -> int:
    cfg = config or load_scale_config()
    tiers = cfg.get("tiers", {})
    sorted_tiers = sorted(tiers.items(), key=lambda x: x[1].get("min_stars", 0), reverse=True)
    for tier_num, tier_cfg in sorted_tiers:
        if stars >= tier_cfg.get("min_stars", 0):
            return tier_num
    return 4


def get_interval_hours(tier: int, config: dict[str, Any] | None = None) -> int:
    cfg = config or load_scale_config()
    tiers = cfg.get("tiers", {})
    return tiers.get(tier, tiers.get(4, {})).get("interval_hours", 720)
