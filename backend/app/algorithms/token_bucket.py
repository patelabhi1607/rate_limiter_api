import uuid

import redis.asyncio as aioredis

from app.algorithms.base import BaseRateLimiter, RateLimitResult
from app.core.redis_client import evalsha_with_fallback, get_redis_time


class TokenBucketLimiter(BaseRateLimiter):
    def __init__(self, client: aioredis.Redis) -> None:
        super().__init__(client)

    async def check(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        burst_multiplier: float = 1.0,
    ) -> RateLimitResult:
        now_sec, now_usec = await get_redis_time(self.client)
        result = await evalsha_with_fallback(
            self.client,
            "token_bucket",
            keys=[key],
            args=[limit, window_seconds, now_sec, now_usec, burst_multiplier, str(uuid.uuid4())],
        )
        return RateLimitResult(
            allowed=bool(int(result[0])),
            remaining=int(result[1]),
            reset_at=int(result[2]),
            retry_after=int(result[3]),
        )
