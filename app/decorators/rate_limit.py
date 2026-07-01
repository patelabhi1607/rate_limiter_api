"""
Per-endpoint rate limiting via decorator or FastAPI dependency.

Usage as decorator:
    @router.get("/endpoint")
    @rate_limit(limit=10, window_seconds=60, algorithm="token_bucket")
    async def endpoint(request: Request): ...

Usage as dependency:
    async def endpoint(request: Request, _=Depends(RateLimiterDep(limit=10, window=60))):
        ...
"""
import uuid
from functools import wraps
from typing import Optional

from fastapi import Depends, HTTPException, Request

from app.algorithms.base import RateLimitResult
from app.algorithms.fixed_window import FixedWindowLimiter
from app.algorithms.leaky_bucket import LeakyBucketLimiter
from app.algorithms.sliding_window import SlidingWindowLimiter
from app.algorithms.token_bucket import TokenBucketLimiter
from app.core.config import get_settings
from app.core.ip_utils import extract_client_ip
from app.core.redis_client import get_redis

_ALGO_MAP = {
    "fixed_window": FixedWindowLimiter,
    "sliding_window": SlidingWindowLimiter,
    "token_bucket": TokenBucketLimiter,
    "leaky_bucket": LeakyBucketLimiter,
}


def _attach(response, result: RateLimitResult, limit: int) -> None:
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(max(0, result.remaining))
    response.headers["X-RateLimit-Reset"] = str(result.reset_at)
    if not result.allowed:
        response.headers["X-RateLimit-Retry-After"] = str(result.retry_after)


class RateLimiterDep:
    """FastAPI dependency for per-endpoint rate limiting."""

    def __init__(
        self,
        limit: int,
        window_seconds: int,
        algorithm: Optional[str] = None,
        burst_multiplier: float = 1.0,
        dimension: str = "ip",
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.algorithm = algorithm
        self.burst_multiplier = burst_multiplier
        self.dimension = dimension

    async def __call__(self, request: Request) -> None:
        settings = get_settings()
        algo = self.algorithm or settings.default_algorithm

        client_ip = extract_client_ip(request)
        identifier = client_ip if self.dimension == "ip" else "global"

        key = f"rl:{algo}:{self.dimension}:{identifier}:{request.url.path}"
        redis_client = get_redis()
        limiter = _ALGO_MAP[algo](redis_client)

        try:
            result = await limiter.check(key, self.limit, self.window_seconds, self.burst_multiplier)
        except Exception:
            if settings.redis_fail_open:
                return
            raise HTTPException(status_code=503, detail="Rate limiter unavailable")

        if not result.allowed:
            raise HTTPException(
                status_code=429,
                detail={"message": "Too Many Requests", "retry_after": result.retry_after},
                headers={
                    "Retry-After": str(result.retry_after),
                    "X-RateLimit-Limit": str(self.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(result.reset_at),
                },
            )


def rate_limit(
    limit: int,
    window_seconds: int,
    algorithm: Optional[str] = None,
    burst_multiplier: float = 1.0,
    dimension: str = "ip",
):
    """Decorator for per-endpoint rate limiting on FastAPI route functions."""
    dep = RateLimiterDep(limit, window_seconds, algorithm, burst_multiplier, dimension)

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request: Optional[Request] = kwargs.get("request") or next(
                (a for a in args if isinstance(a, Request)), None
            )
            if request:
                await dep(request)
            return await func(*args, **kwargs)

        return wrapper

    return decorator
