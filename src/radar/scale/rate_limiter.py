"""Adaptive rate limiter for GitHub API.

Reads actual remaining/reset from response headers.
Adapts delay based on budget consumption.
Stops batch when rate limited (does not waste time retrying)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from radar.scale.config import load_scale_config

logger = logging.getLogger(__name__)


@dataclass
class RateLimitState:
    remaining: int = 1000
    limit: int = 1000
    reset_at: float = 0.0
    used_this_window: int = 0
    window_start: float = 0.0
    cost_per_request: int = 1

    @property
    def is_throttled(self) -> bool:
        return self.remaining <= 0

    @property
    def budget_exhausted(self) -> bool:
        safety = 0.80
        return self.used_this_window >= int(self.limit * safety)

    @property
    def seconds_until_reset(self) -> float:
        return max(0.0, self.reset_at - time.time())

    @property
    def adaptive_delay(self) -> float:
        ratio = self.used_this_window / max(self.limit, 1)
        return min(0.1 + ratio * 2.0, 10.0)

    def update_from_headers(self, headers: dict[str, str]) -> None:
        if 'x-ratelimit-remaining' in headers:
            self.remaining = int(headers['x-ratelimit-remaining'])
        if 'x-ratelimit-limit' in headers:
            self.limit = int(headers['x-ratelimit-limit'])
        if 'x-ratelimit-reset' in headers:
            self.reset_at = float(headers['x-ratelimit-reset'])
        self.used_this_window = self.limit - self.remaining

    def update_from_graphql(self, data: dict[str, Any]) -> None:
        if 'rateLimit' in data:
            rl = data['rateLimit']
            self.remaining = rl.get('remaining', self.remaining)
            self.limit = rl.get('limit', self.limit)
            cost = rl.get('cost', 1)
            self.used_this_window += cost
            if 'resetAt' in rl:
                from datetime import datetime
                try:
                    reset_dt = datetime.fromisoformat(rl['resetAt'].replace('Z', '+00:00'))
                    self.reset_at = reset_dt.timestamp()
                except (ValueError, TypeError):
                    pass

    def reset_window(self) -> None:
        self.used_this_window = 0
        self.window_start = time.time()


class AdaptiveRateLimiter:
    def __init__(self, config: dict[str, Any] | None = None):
        cfg = config or load_scale_config()
        rl_cfg = cfg.get('rate_limit', {})
        self.hourly_budget = rl_cfg.get('hourly_budget', 1000)
        self.safety_threshold = rl_cfg.get('safety_threshold', 0.80)
        self.cooldown_on_limit = rl_cfg.get('cooldown_on_limit', True)
        self.persist_on_cooldown = rl_cfg.get('persist_on_cooldown', True)
        self.max_calls = int(self.hourly_budget * self.safety_threshold)
        self.state = RateLimitState(remaining=self.hourly_budget, limit=self.hourly_budget)
        self._calls_this_run = 0
        self._stopped = False

    @property
    def stopped(self) -> bool:
        return self._stopped

    @property
    def calls_remaining(self) -> int:
        return max(0, self.max_calls - self._calls_this_run)

    async def wait_if_needed(self) -> bool:
        if self._stopped:
            return False
        if self._calls_this_run >= self.max_calls:
            logger.warning(f"Budget exhausted: {self._calls_this_run}/{self.max_calls} calls used")
            self._stopped = True
            return False
        if self.state.is_throttled:
            wait = self.state.seconds_until_reset + 5
            if wait > 600:
                logger.error(f"Rate limited with {wait:.0f}s reset -- stopping batch")
                self._stopped = True
                return False
            logger.info(f"Rate limited, waiting {wait:.0f}s for reset")
            import asyncio
            await asyncio.sleep(wait)
            self.state.reset_window()
        elif self.state.remaining < 200:
            wait = self.state.seconds_until_reset + 2
            if wait > 0 and wait < 300:
                import asyncio
                await asyncio.sleep(wait)
                self.state.reset_window()
        return True

    def record_request(self, cost: int = 1) -> None:
        self._calls_this_run += cost
        self.state.used_this_window += cost
        self.state.remaining = max(0, self.state.remaining - cost)

    def get_delay(self) -> float:
        return self.state.adaptive_delay

    def get_stats(self) -> dict[str, Any]:
        return {
            'calls_this_run': self._calls_this_run,
            'max_calls': self.max_calls,
            'calls_remaining': self.calls_remaining,
            'rate_remaining': self.state.remaining,
            'rate_limit': self.state.limit,
            'budget_exhausted': self.state.budget_exhausted,
            'stopped': self._stopped,
        }
