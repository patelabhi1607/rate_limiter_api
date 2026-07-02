from abc import ABC, abstractmethod
from dataclasses import dataclass

import redis.asyncio as aioredis


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    reset_at: int       # Unix timestamp
    retry_after: int    # seconds; 0 if allowed


class BaseRateLimiter(ABC):
    def __init__(self, client: aioredis.Redis) -> None:
        self.client = client

    @abstractmethod
    async def check(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        burst_multiplier: float = 1.0,
    ) -> RateLimitResult:
        """Atomically check and update the rate limit counter."""
        ...
